#!/usr/bin/env python
# -*- coding: utf-8 -*-
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

import utils
import log

_INFO_BEGIN = '========JSON_STREAM_INFO_BEGIN========'
_INFO_END = '========JSON_STREAM_INFO_END========'
_ERROR_BEGIN = '========JSON_STREAM_ERROR_BEGIN========'
_ERROR_END = '========JSON_STREAM_ERROR_END========'

_MAX_DURATION_DIFF = 60

logger = None
_args = None
_configs = None
_cmd_queue = Queue.Queue()
_thrd_tasks = list()

def _parse_args():
    
    #参数action有：
    #store：默认action模式，存储值到指定变量。
    #store_const：存储值在参数的const部分指定，多用于实现非布尔的命令行flag。
    #store_true / store_false：布尔开关。可以2个参数对应一个变量。
    #append：存储值到列表，该参数可以重复使用。
    #append_const：存储值到列表，存储值在参数的const部分指定。
    #version 输出版本信息然后退出。
    global _args
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-l', '--log-file', action='store', dest='log_file', default='transcode.log')
    arg_parser.add_argument('-o', '--output-dir', action='store', dest='output_dir', required=True)
    arg_parser.add_argument('--config-file', action='store', dest='config_file', default='transcode.json')
    arg_parser.add_argument('--max-tasks', action='store', dest='max_tasks', default=1, type=int)
    arg_parser.add_argument('--no-skip', action='store', dest='no_skip', default=False, type=bool)

    group = arg_parser.add_mutually_exclusive_group()
    group.add_argument('-i', '--input-dir', action='store', dest='input_dir',default='D:/wwwroot/nodejs/fuzhoucms/fuzhoucms/public/upload')
    group.add_argument('--input-list', action='store', dest='input_list')

    arg_parser.add_argument('--fix-dar', action='store', dest='fix_dar', default=False, type=bool)
    _args = arg_parser.parse_args()

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
    #logger.info('check path: %s' % filename)
    response = dict()
    response['status'] = 'error'

    out = utils.check_output_timeout(['streamparser', filename], 30)    
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

def _get_vsize(info):
    print info
    try:
        for stream in info['programs'][0]['streams']:
            if stream['type'] == 'video':
                return (stream['width'], stream['height'])
    except:
        pass
    return (None, None)
#python 类
class TaskThread(threading.Thread):
    #构造函数
    def __init__(self, index):
        super(TaskThread, self).__init__()
        self.index = index
        self.status = 0
        self.infile = ''
        self.outfiles = list()
        self._proc = None
        self._ret = None

    def run(self):
        self.status = 1
        while True:
            try:
                task = _cmd_queue.get(True, 5) #从队列取数据，等待5毫秒
                self.input_dir = task['input_dir']
                self.input_file = task['input_file']
                self.output_dir = task['output_dir']
                self.infile = os.path.join(self.input_dir, self.input_file) #合并路径
            except Queue.Empty:
                self.status = 2

            #logger.info('thread_%d begin to process input:%s' % (self.index, self.infile))
            infile_info = _get_streaminfo(self.infile)

            if infile_info['status'] != 'ok':
                logger.error('[TRANSCODE_FAILED] |%s|get streaminfo FAILED' % self.infile)
                continue

            if self._check_skip_by_vsize(infile_info):
                continue          

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
    def print_status(self):
        print '------------------------------------------------------'
        print '%d|status:%d, input:%s' % (self.index, self.status, self.infile)
        for (index, item) in self.outfiles:
            try:
                stat = os.stat(item) #获取文件的状态
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

if __name__ == '__main__':
    reload(sys)
    sys.setdefaultencoding('utf-8')    
    _parse_args();
    _log_init();
    #logger.info('args:%s' % _args.__str__())
    _configs = json.loads(utils.read_json(utils.get_full_path(_args.config_file), False))

    #将ffmpeg 加入环境变量
    os.environ['PATH'] = utils.get_full_path('bin') + ':' + os.environ['PATH']
    os.environ['LD_LIBRARY_PATH'] = utils.get_full_path('lib')
    outdir_base = utils.get_full_path(_args.output_dir)
    #输出目录不存在，创建
    if not os.path.exists(outdir_base):
        os.makedirs(outdir_base)

    if _args.input_dir is not None:        
        indir_base = utils.get_full_path(_args.input_dir)
        #判断是否为文件夹
        if not os.path.isdir(indir_base):
            print 'input (%s) is not a dir' % indir_base
            sys.exit(-1)
        #遍历目录及文件
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

                    # 目前将所有文件一次性添加到队列里，后续如果需要可考虑限制队列大小，一边转码一边添加
                    _cmd_queue.put({'input_dir': root, 'input_file': f, 'output_dir': outdir})
    else:
        logger.error('no input_dir or input_list, should not go here!')
        sys.exit(-1)
    #启动线程
    for i in range(_args.max_tasks):
        thrd = TaskThread(i)
        _thrd_tasks.append(thrd)
        thrd.setDaemon(True)
        thrd.start()#线程执行start 将启动run方法
    complete = True
    for task in _thrd_tasks:
        task.print_status()
        #task.check_timeout()
        if task.status != 2:
            complete = False
        
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             