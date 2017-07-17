# -*- coding: utf-8 -*-
'''
@author: jinweida
create: Jul 2, 2014
'''

import logging
import logging.handlers
import sys
import os

# configures
logging_console = False

logging_file = False
logging_file_name = None
logging_file_rotating_count = 10
logging_file_rotating_size = 1024 * 1024 * 10

logging_udp = False
logging_udp_ip = None
logging_udp_port = 0

logging_level = logging.DEBUG
# format_str = '%(asctime)s[lv%(levelno)s] %(module)s.%(funcName)s,L%(lineno)d %(message)-80s| P%(process)d. %(threadName)s'
format_str = '%(asctime)s|l%(levelno)s|%(module)s.%(funcName)s,L%(lineno)d|%(message)-80s'

# internal used
_configured = False
_loggers = dict()
_handler_console = None
_handler_file = None
_handler_udp = None
_formatter = None

_stdout_backup = None
_stderr_backup = None


def _update_logger(logger):
    global _handler_console
    global _handler_file
    global _handler_udp
    if not _configured:
        update_config()
    if _handler_console != None:
        logger.addHandler(_handler_console)
    if _handler_file != None:
        logger.addHandler(_handler_file)
    if _handler_udp != None:
        logger.addHandler(_handler_udp)
    logger.setLevel(logging_level)


def get_logger(name='unknown'):
    global _loggers
    if name not in _loggers.keys():
        logger = logging.getLogger(name)
        _update_logger(logger)
        _loggers[name] = logger
    return _loggers[name]


def update_config():
    global _configured
    global _loggers
    global _handler_console
    global _handler_file
    global _handler_udp
    global _formatter

    if _stdout_backup is not None:
        sys.stdout = _stdout_backup
    if _stderr_backup is not  None:
        sys.stderr = _stderr_backup

    for logger in _loggers.values():
        if _handler_console != None:
            logger.removeHandler(_handler_console)
        if _handler_file != None:
            logger.removeHandler(_handler_file)
        if _handler_udp != None:
            logger.removeHandler(_handler_udp)

    _formatter = logging.Formatter(format_str)

    if logging_console:
        _handler_console = logging.StreamHandler(sys.stdout)
        if _formatter != None:
            _handler_console.setFormatter(_formatter)
    else:
        _handler_console = None

    if logging_file:
        if not os.path.exists(os.path.dirname(logging_file_name)):
            os.makedirs(os.path.dirname(logging_file_name))

        if logging_file_rotating_count > 0:
            _handler_file = logging.handlers.RotatingFileHandler(logging_file_name, mode='a', \
                maxBytes=logging_file_rotating_size, backupCount=logging_file_rotating_count)
        else:
            _handler_file = logging.FileHandler(logging_file_name, mode='a')

        if _formatter != None:
            _handler_file.setFormatter(_formatter)
    else:
        _handler_file = None

    if logging_udp:
        _handler_udp = logging.handlers.DatagramHandler(logging_udp_ip, logging_udp_port)
        if _formatter != None:
            _handler_udp.setFormatter(_formatter)
    else:
        _handler_udp = None

    for logger in _loggers.values():
        _update_logger(logger)

    _configured = True


class _stream2logger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())


def redirect_sysout():
    # 备份，在update_config()时恢复，以免update_config()对应的logger被关闭时导致问题
    global _stdout_backup
    global _stderr_backup
    if _stdout_backup is None:
        _stdout_backup = sys.stdout
    if _stderr_backup is None:
        _stderr_backup = sys.stderr

    sys.stdout = _stream2logger(get_logger('stdout'), logging.INFO)
    sys.stderr = _stream2logger(get_logger('stderr'), logging.ERROR)
