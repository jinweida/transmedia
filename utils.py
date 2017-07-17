# -*- coding: utf-8 -*-
'''
@author: jinweida
create: Jul 14, 2014
'''
import subprocess
import threading
import time
import os
import sys
from copy import deepcopy
import log
logger = log.get_logger('utils')


class ExecptionMsg(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def check_output_timeout(url, timeout=10):
    class ThreadRun(threading.Thread):
        def __init__(self):
            super(ThreadRun, self).__init__()
            self.output = None

        def run(self):
            self.output = subprocess.check_output(url, stderr=subprocess.STDOUT)

    thrd_run = ThreadRun()
    thrd_run.start()
    while not thrd_run.output and timeout > 0:
        time.sleep(0.1)
        timeout -= 0.1
    try:
        thrd_run.proc.terminate()
    except:
        pass

    return thrd_run.output

def getpwd():
    pwd = sys.path[0]
    if os.path.isfile(pwd):
        pwd = os.path.dirname(os.path.realpath(pwd))
    return pwd

def get_full_path(path):
    base_dir = getpwd()
    path = os.path.expanduser(path)
    path = os.path.expandvars(path)
    if not os.path.isabs(path):
        path = base_dir + os.sep + path
    return path

def read_json(fullpath, show_log=False):
    '''read json file and remove comments'''
    lines = open(fullpath).readlines()
    if show_log:
        logger.debug('original %s: %s' % (fullpath, ''.join(lines)))

    for line in lines[:]:
        line_lstrip = line.lstrip()
        if line_lstrip.startswith('//'):
            lines.remove(line)
    if show_log:
        logger.debug('after remove comments %s: %s' % (fullpath, ''.join(lines)))

    return ''.join(lines)


# from https://www.xormedia.com/recursively-merge-dictionaries-in-python/
def dict_merge(a, b):
    '''recursively merges dict's. not just simple a['key'] = b['key'], if
    both a and bhave a key who's value is a dict then dict_merge is called
    on both values and the result stored in the returned dictionary.'''

    '''another solution
    http://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
    import collections
    def dict_merge(d, u):
        for k, v in u.iteritems():
            if isinstance(v, collections.Mapping):
                r = dict_merge(d.get(k, {}), v)
                d[k] = r
            else:
                d[k] = u[k]
        return d
    '''

    if not isinstance(b, dict):
        return b
    result = deepcopy(a)
    for k, v in b.iteritems():
        if k in result and isinstance(result[k], dict):
                result[k] = dict_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result
