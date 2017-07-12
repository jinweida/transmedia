#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@author: Ye Shengnan
create: Jul 28, 2014
'''
import os
import threading
import subprocess
import shlex
import Queue
import argparse
import json
import time
import select
import sys
import httplib,urllib
import utils
import log
import random

_INFO_BEGIN = '========JSON_STREAM_INFO_BEGIN========'
_INFO_END = '========JSON_STREAM_INFO_END========'
_ERROR_BEGIN = '========JSON_STREAM_ERROR_BEGIN========'
_ERROR_END = '========JSON_STREAM_ERROR_END========'
_MAX_DURATION_DIFF = 60

logger = None
_args = None
_configs = None
_cmd_queue = Queue.Queue()
_post_queue = Queue.Queue()
_all_files = set()
_thrd_tasks = list()


def _parse_args():
    global _args
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-l', '--log-file', action='store', dest='log_file', default='transcode.log')
    arg_parser.add_argument('-o', '--output-dir', action='store', dest='output_dir', required=True)
    arg_parser.add_argument('--config-file', action='store', dest='config_file', default='transcode.json')
    arg_parser.add_argument('--max-tasks', action='store', dest='max_tasks', default=1, type=int)
    #回调url
    #arg_parser.add_argument('--http',action='store', dest='http',default='fuzhou.cms.joygo.com')
    #回调port
    #arg_parser.add_argument('--port',action='store', dest='port',default='80')
    arg_parser.add_argument('--no-skip', action='store', dest='no_skip', default=False, type=bool)
    group = arg_parser.add_mutually_exclusive_group()
    group.add_argument('-i', '--input-dir', action='store', dest='input_dir')
    group.add_argument('--input-list', action='store', dest='input_list')
    arg_parser.add_argument('--fix-dar', action='store', dest='fix_dar', default=False, type=bool)
    _args = arg_parser.parse_args()
    print _args

def _log_init():
    log.logging_console = True
    log.logging_file = True
    log.logging_file_name = utils.get_full_path(_args.log_file)
    log.logging_level = 10  # logging.DEBUG
    log.format_str = '%(asctime)s,L%(lineno)d|%(message)-80s'
    log.update_config()
    log.redirect_sysout()

    global logger
    logger = log.get_logger('main')

def _get_streaminfo(filename):
    logger.info('check path: %s' % filename)
    response = dict()
    response['status'] = 'error'

    out = utils.check_output_timeout(['streamparser', filename], 30);
    if out == None:
        response['error_msg'] = 'call streamparser timeout'
        return response
#     logger.debug('out:%s' % out)

    start = out.find(_INFO_BEGIN)
    end = out.find(_INFO_END)
    if start >= 0 or end > 0:
        start += len(_INFO_BEGIN)
        info = out[start: end]
        response = json.loads(info)
        response['url'] = filename
        response['status'] = 'ok'
        return response

    start = out.find(_ERROR_BEGIN)
    end = out.find(_ERROR_END)
    if start >= 0 or end > 0:
        start += len(_ERROR_BEGIN)
        error = out[start: end]
        response = json.loads(error)
        response['status'] = 'error'
        return response
    else:
        response['error_msg'] = 'find _INFO_BEGIN (%d) or _INFO_END (%d) FAILED!\n' % (start, end)
    return response


def _get_dar(info):
    try:
        for stream in info['programs'][0]['streams']:
            if stream['type'] == 'video':
                return (stream['dar_num'], stream['dar_den'])
    except:
        pass
    return (0, 1)


def _get_vsize(info):
    try:
        for stream in info['programs'][0]['streams']:
            if stream['type'] == 'video':
                return (stream['width'], stream['height'])
    except:
        pass
    return (None, None)


def _make_cmdline(infile, infile_info, outfiles):
    cmd = list()
    cmd.append('ffmpeg')
    cmd.append('-nostats')
    cmd.append('-i "%s"' % infile)

    for (index, outfile) in outfiles:
        output = _configs['outputs'][index]

        for stream in infile_info['programs'][0]['streams']:
            # ATTENTION: subtitle可以用-scodec copy加到输出片源中，但分辨率改变时，
            # 字幕内的位置信息没有改变，会导致显示不正确，这里暂不复制字幕信息
            if stream['type'] == 'video' or stream['type'] == 'audio':
                cmd.append('-map 0:%d' % stream['index'])

        #========> video
        cmd.append('-vcodec %s' % output['vcodec'])
        if 'vprofile' in output:
            cmd.append('-profile:v %s' % output['vprofile'])
        if 'vlevel' in output:
            cmd.append('-level:v %s' % output['vlevel'])
        if 'preset' in output:
            cmd.append('-preset %s' % output['preset'])

#         if 'width' in output and 'height' in output:
#             cmd.append('-s %dx%d' % (output['width'], output['height']))

        if 'width' in output:
            in_size = _get_vsize(infile_info)
            if in_size[0] is None:
                logger.error("no dar in info input file, and get input video size FAILED!\n")
            else:
                if abs(output['width'] - in_size[0]) <= 8:
                    # input和output width差不多时, output height直接使用input height
                    height = in_size[1]
                else:
                    height = (output['width'] * in_size[1] / in_size[0] + 15) / 16 * 16
                cmd.append('-s %dx%d' % (output['width'], height))

        if 'aspect' in output:
            cmd.append('-aspect %s' % output['aspect'])
        else:
            in_dar = _get_dar(infile_info)
            if in_dar[0] == 0 or in_dar[1] == 0:
                in_dar = _get_vsize(infile_info)
            if in_dar[0] is None:
                logger.error("no dar in info input file, and get input video size FAILED!\n")
            else:
                logger.warning("no dar info in input file, force set aspect to width:height")
                cmd.append('-aspect %d:%d' % (in_dar[0], in_dar[1]))

        if 'fps' in output:
            cmd.append('-r %.2f' % float(output['fps']))

        cmd.append('-vf yadif=0:-1')  # ATTENTION
        cmd.append('-pix_fmt yuv420p')

        if 'keyint' in output:
            cmd.append('-g %d' % output['keyint'])
        if 'bframes' in output:
            cmd.append('-bf %d' % output['bframes'])
        if 'refs' in output:
            cmd.append('-refs %d' % output['refs'])
        if 'scenecut' in output:
            cmd.append('-sc_threshold %d' % output['scenecut'])

        v_bitrate = output['bitrate']
        v_bitrate *= 1000
        v_bitrate -= v_bitrate * 9 / 100  # TS overhead
        v_bitrate -= output['audio_bitrate']  # ATTENTION: 多路音频时只计算了一路
        if v_bitrate < 100000:
            v_bitrate = 100000

        rc = output['rc'] if 'rc' in output else 'crf'
        if rc == 'cbr':
            cmd.append('-minrate %dk -maxrate %dk' % (v_bitrate / 1000, v_bitrate / 1000))
        elif rc == 'abr':
            cmd.append('-b:v %dk' % (v_bitrate / 1000))
            if 'x264_ratetol' in output:
                cmd.append('-x264-params ratetol=%.2f' % output['x264_ratetol'])
        else:  # crf
            buf_size = v_bitrate * 10 / 1000
            if 'buf_size' in output:
                buf_size = output['buf_size']
            cmd.append('-maxrate %dk -bufsize %dk' % (v_bitrate / 1000, buf_size))
            if 'crf' in output:
                cmd.append('-crf %d' % output['crf'])

        #========> audio
        cmd.append('-acodec %s' % output['acodec'])
        cmd.append('-b:a %sk' % output['audio_bitrate'])
        cmd.append('-strict experimental')
        if 'audio_samplerate' in output:
            cmd.append('-ar %d' % output['audio_samplerate'])
        if 'audio_channels' in output:
            cmd.append('-ac %d' % output['audio_channels'])

        if 'audio_volume' in output:
            cmd.append('-af volume=%.1f' % (output['audio_volume'] / 100))

        #========> system
        if 'format' in output:
            if output['format'] == 'mpegts':
                cmd.append('-mpegts_flags resend_headers')
                if 'network_id' in output:
                    cmd.append('-mpegts_original_network_id 0x%04x' % output['network_id'])
                if 'stream_id' in output:
                    cmd.append('-mpegts_transport_stream_id 0x%04x' % output['stream_id'])
                if 'service_id' in output:
                    cmd.append('-mpegts_service_id 0x%04x' % output['service_id'])
                if 'pmt_start_pid' in output:
                    cmd.append('-mpegts_pmt_start_pid 0x%04x' % output['pmt_start_pid'])
                if 'start_pid' in output:
                    cmd.append('-mpegts_start_pid 0x%04x' % output['start_pid'])
                if 'meta_service_provider' in output:
                    cmd.append('-metadata service_provider="%s"' % output['meta_service_provider'])
                if 'meta_service_name' in output:
                    cmd.append('-metadata service_name="%s"' % output['meta_service_name'])
            #cmd.append('-f hls%s' % output['format'])
            #cmd.append('-f hls %s' % outfile)
        #cmd.append('-f hls -hls_list_size 1000000 -start_number  0 -hls_time 10 -y "%s"' % outfile)
        #cmd.append('-y "%s"' % outfile)

    logger.debug('cmdline for %s:%s' % (infile, ' '.join(cmd)))
    return ' '.join(cmd)


class TaskThread(threading.Thread):
    def __init__(self, index):
        super(TaskThread, self).__init__()
        self.index = index
        self.status = 0
        self.infile = ''
        self.outfiles = list()
        self._proc = None
        self._ret = None

    # 转码文件时长差大于等于60时认为转码失败
    def _check_duration(self, infile, infile_info, outfiles, write_log):
        for (index, outfile) in outfiles:
            outfile_info = _get_streaminfo(outfile)
            if outfile_info['status'] != 'ok':
                if write_log:
                    logger.error('[TRANSCODE_FAILED] |%s| get streaminfo FAILED! ret:%s' % (infile, self._ret.__str__()))
                return False

            if abs(infile_info['duration'] - outfile_info['duration']) / 1000000 > _MAX_DURATION_DIFF:
                if write_log:
                    logger.error('[TRANSCODE_FAILED] |%s|duration mismatch, ret:%s, may be ok, input:%d, output:%d, diff:%d' \
                                 % (infile, self._ret.__str__(), infile_info['duration'] / 1000000, \
                                    outfile_info['duration'] / 1000000, \
                                    (infile_info['duration'] - outfile_info['duration']) / 1000000))
                return False

        if write_log:
            logger.error('[TRANSCODE_OK] |%s' % infile)
        return True

    def _check_dar(self, infile_info, outfiles):
        for (index, outfile) in outfiles[:]:
            outfile_info = _get_streaminfo(outfile)
            if outfile_info['status'] != 'ok':
                logger.error('_get_streaminfo FAILED!')
                return False

            in_dar = _get_vsize(infile_info)
            if in_dar[0] is None:
                continue
            in_dar_get = _get_dar(infile_info)
            if in_dar_get[0] > 0:
                in_dar = in_dar_get

            out_dar = _get_vsize(outfile_info)
            if out_dar[0] is None:
                continue
            out_dar_get = _get_dar(outfile_info)
            if out_dar_get[0] > 0:
                out_dar = out_dar_get

            diff_abs = abs(float(in_dar[0]) / in_dar[1] - float(out_dar[0]) / out_dar[1])
            if diff_abs > 0.1:
                logger.error('find dar mismatch, %.3f, in:%s, out:%s, file:%s' % (diff_abs,
                    in_dar.__str__(), out_dar.__str__(), outfile))
                return False

        return True

    def _check_skip_by_vsize(self, infile_info):
        if 'min_video_width' not in _configs or 'max_video_width' not in _configs \
            or 'min_video_height' not in _configs or 'max_video_height' not in _configs:
            return False

        (width, height) = _get_vsize(infile_info)
        if width is None or height is None:
            logger.error('[TRANSCODE_SKIPED] |%s|read video width/height FAILED!' % (self.infile,))
            return True

        if width >= _configs['min_video_width'] \
            and width <= _configs['max_video_width'] \
            and height >= _configs['min_video_height'] \
            and height <= _configs['max_video_height']:
            return False
        else:
            logger.error('[TRANSCODE_SKIPED] |%s| width (%d) or height (%d) out of range' \
                         % (self.infile, width, height))
            return True

    def _run_task(self, cmd):
        self._proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        fn_stdout = self._proc.stdout.fileno()
        fn_stderr = self._proc.stderr.fileno()
        sets = [fn_stdout, fn_stderr]
        output_stdout = None
        output_stderr = None
        while True:
            ret = select.select(sets, [], [])
            for fd in ret[0]:
                if fd == fn_stdout:
                    output_stdout = self._proc.stdout.readline()
                    if output_stdout:
                        logger.debug('ffout_%d %s' % (self.index, output_stdout.rstrip()))
                if fd == fn_stderr:
                    output_stderr = self._proc.stderr.readline()
                    if output_stderr:
                        logger.debug('fferr_%d %s' % (self.index, output_stderr.rstrip()))

            self._ret = self._proc.poll()
            if self._ret != None:
                if not output_stderr and not output_stdout:
                    logger.warn('task_%d ======== ffmpeg progress exited (ret:%d)(%s) ========' \
                                % (self.index, self._ret, self.infile))
                    self._proc = None
                    break

    def _get_thumbnail(self, in_file,infile_info,out_file):
        duration=infile_info['duration']/1000000/2
        cmd = list()
        cmd.append('ffmpeg')
        cmd.append('-i %s' % in_file)
        cmd.append('-ss %s' % duration) #seek到100秒
        cmd.append('-f image2')
        cmd.append('-y %s' % out_file)
        self._run_task(' '.join(cmd))

    #转码结束回调通知远程地址
    def _set_callback(self,in_file,out_file,out_file_thumbnail):
        httpClient = None
        try:
            if not _args.http is None:
                params = urllib.urlencode({'filename': out_file, 'thumbnail': out_file_thumbnail})
                headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
                httpClient = httplib.HTTPConnection(_args.http, _args.port, timeout=30)
                httpClient.request("POST", "/admin/attachs_update_status", params, headers)

                logger.info('post file: %s' % out_file)
                logger.info('post file: %s' % out_file_thumbnail)

                response = httpClient.getresponse()
                print ''+response.read()
        except Exception, e:
            print e
        finally:
            if httpClient:
                httpClient.close()
        pass

    def run(self):
        while True:
            try:
                task = _cmd_queue.get(True, 5)
                self.input_dir = task['input_dir']
                self.input_file = task['input_file']
                self.output_dir = task['output_dir']
                self.infile = os.path.join(self.input_dir, self.input_file)
                self.status = 1
                #_all_files.remove(self.infile) #出队列后将源文件也删除
            except Queue.Empty:
                self.status = 2
                time.sleep(5)
                continue
            logger.info('thread_%d begin to process input:%s' % (self.index, self.infile))

            infile_info = _get_streaminfo(self.infile)
            if infile_info['status'] != 'ok':
                logger.error('[TRANSCODE_FAILED] |%s|get streaminfo FAILED' % self.infile)
                continue

            if self._check_skip_by_vsize(infile_info):
                continue

            self.outfiles = list()
            (width, height) = _get_vsize(infile_info)
            for index, output in enumerate(_configs['outputs']):
                try:
                    if _configs['skip_upsize'] and width is not None and height is not None:
                        if output['width'] > width:
                            logger.error('skip output for upsize, %d vs %d' % (output['width'], width))
                            continue
                except:
                    logger.exception('got exception:')

                try:
                    base, ext = os.path.splitext(self.input_file)
                    if output['name_append']:
                        outfile = self.output_dir + os.sep + base + output['name_append'] + output['file_ext']
                        logger.debug('add outfile with name_append:%s' % outfile)
                    else:
                        outfile = self.output_dir + os.sep + base + output['file_ext']
                        logger.debug('add outfile:%s' % outfile)
                except UnicodeError:
                    logger.exception('got exception:')
                    continue
                self.outfiles.append((index, outfile))

            if len(self.outfiles) <= 0:
                logger.error('[TRANSCODE_SKIPED] |%s| for upsize? %sx%s' % (self.infile, width.__str__(), height.__str__()))
                continue

            self._last_size = [0 for i in self.outfiles]

            base, ext = os.path.splitext(self.input_file)

            # 检查输出文件是否已存在，并且duration匹配，如果匹配则跳过
            if not _args.no_skip and self._check_duration(self.infile, infile_info, self.outfiles, False):
                if _args.fix_dar and not self._check_dar(infile_info, self.outfiles):
                    logger.warning('[TRANSCODE_FIXDAR] |%s| find DAR error, retranscode' % self.infile)
                else:
                    logger.error('[TRANSCODE_SKIPED] |%s|outfiles exist and duration match ok' % self.infile)
                    continue

            cmd = _make_cmdline(self.infile, infile_info, self.outfiles)
            self._run_task(cmd)
            self._check_duration(self.infile, infile_info, self.outfiles, True)

            outfile_thumnail = self.output_dir + os.sep + base + '.jpg'
            outfile =self.output_dir + os.sep +base+output['name_append']+ output['file_ext']
            #TODO: 检查缩略图是否存在，存在则跳过？
            self._get_thumbnail(self.infile, infile_info,outfile_thumnail)
            #回调
            self._set_callback(self.infile,outfile,outfile_thumnail)


    def print_status(self):
        print '--------------------------------------------------------------------------------'
        print '%d|status:%d, input:%s' % (self.index, self.status, self.infile)
        for (index, item) in self.outfiles:
            try:
                stat = os.stat(item)
                print '%d|out:%s, size:%dM, modified:%s' % (self.index, item, stat.st_size / 1024 / 1024,
                                                           time.asctime(time.localtime(stat.st_mtime)))
            except OSError, e:
                print '%d|out:%s, stat error:%s' % (self.index, item, e.__str__())

    def check_timeout(self):
        if self.status != 1 or self._proc is None:
            return
        # ATTENTION: 在任务切换期间，self.outfiles, self._last_size可能"正在"被重新初始化
        # 不确定是会产生exception，还是会导致其他问题. 如果仅产生exception没有问题。
        for (index, item) in self.outfiles:
            try:
                stat = os.stat(item)
                curr = time.time()
                if stat.st_size - self._last_size[index] < 1024 and curr - stat.st_mtime > 120:
                    logger.error('%d|transcode_timeout. in:%s, out:%s' % (self.index, self.infile, item))
                    logger.error('%d| index:%d, curr:%d, stat:%s, last_size:%s' \
                                 % (self.index, index, curr, stat.__str__(), self._last_size.__str__()))
                    self._proc.terminate()
                    # leave self._check_duration() to mark task as FAILED
                    pass
                else:
                    self._last_size[index] = stat.st_size
            except Exception, e:
                logger.warn('%d|check_timeout FAILED! %s, %s' % (self.index, item, e.__str__()))


# 目前将所有文件一次性添加到队列里，后续如果需要可考虑限制队列大小，一边转码一边添加
def _check_add_files(input_dir):
    indir_base = utils.get_full_path(input_dir)
    if not os.path.isdir(indir_base):
        print 'input (%s) is not a dir' % indir_base
        sys.exit(-1)

    list_dirs = os.walk(indir_base)
    for root, dirs, files in list_dirs:
        for f in files:
            base, ext = os.path.splitext(f)
            if ext[1:].lower() in _configs['file_types']:
                outdir = outdir_base + os.sep + root[len(indir_base):]
                try:
                    os.makedirs(outdir)
                except (OSError, IOError):
                    pass

                full_path = os.path.join(root, f)
                if full_path not in _all_files:
                    print 'add new file:%s' % full_path
                    _cmd_queue.put({'input_dir': root, 'input_file': f, 'output_dir': outdir})
                    _all_files.add(full_path)


if __name__ == '__main__':
    reload(sys)
    sys.setdefaultencoding('utf-8')

    _parse_args()
    _log_init()

    _configs = json.loads(utils.read_json(utils.get_full_path(_args.config_file), False))
    os.environ['PATH'] = utils.get_full_path('bin') + ':' + os.environ['PATH']
    os.environ['LD_LIBRARY_PATH'] = utils.get_full_path('lib')

    outdir_base = utils.get_full_path(_args.output_dir)

    if not os.path.exists(outdir_base):
        os.makedirs(outdir_base)

    if _args.input_list is not None:
        try:
            with open(utils.get_full_path(_args.input_list)) as fp:
                for line in fp:
                    line = line.strip() #删除头尾空格
                    inpath = utils.get_full_path(line)
                    if not os.path.isfile(inpath):
                        logger.error('input file does not exist: %s|%s' % (line, inpath))
                        continue

                    (indir, infile) = os.path.split(inpath)#返回一个路径的目录名和文件名
                    outdir = outdir_base + os.sep + indir
                    try:
                        os.makedirs(outdir)
                    except (OSError, IOError):
                        pass

                    print 'input_dir：'+indir+ 'input_file:'+ infile, 'output_dir:' +outdir
                    _cmd_queue.put({'input_dir': indir, 'input_file': infile, 'output_dir': outdir})

        except OSError:
            logger.exception('got exception:')
            sys.exit(-1)
    elif _args.input_dir is not None:
        pass
    else:
        logger.error('no input_dir or input_list, should not go here!')
        sys.exit(-1)

    exit(-1)
    for i in range(_args.max_tasks):
        thrd = TaskThread(i)
        _thrd_tasks.append(thrd)
        thrd.setDaemon(True)
        thrd.start()
    check_count = 0
    while True:
        if _args.input_dir is not None:
            if check_count % 5 == 0:
                _check_add_files(_args.input_dir)
            check_count += 1
        print 'queue size:%d' % _cmd_queue.qsize()

        complete = True
        for task in _thrd_tasks:
            #task.print_status()
            task.check_timeout()
            if task.status != 2:
                complete = False
        if complete:
            print '======== idle ========'
        time.sleep(30)
