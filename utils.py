#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import logging.handlers
import os
import threading
from PyQt5.QtCore import QStandardPaths, QFile, QIODevice, QTextStream
from lxml import etree
from ncclient.xml_ import *

def pretty_xml(xml, pretty_print=True):
    """Reformats a given string containing an XML document (for human readable output)"""
    pretty = ""
    try:
        parser = etree.XMLParser(encoding='utf-8', remove_blank_text=True)
        tree = etree.fromstring(xml.encode('utf-8'), parser)
        # 清理只包含空格和换行内容的xml节点，RF4741规定节点必须包含非空白字符
        for elem in tree.iter():
            if elem.text and all(char.isspace() for char in elem.text) is True:
                elem.text = None
        pretty = etree.tostring(tree, pretty_print=pretty_print, encoding='unicode')
    except etree.Error as e:
        # pretty = "Error: Cannot format XML message: {}\nPlain message is:\n{}".format(
        #     str(e), xml.decode()
        # )
        pretty = xml

    return pretty

def millsecondToStr(ms: int):
    sec = int(ms / 1000)
    ms %= 1000
    hour = int(sec/3600)
    sec %= 3600
    min = int(sec / 60)
    sec %= 60

    time_str = ""
    if hour:
        time_str = f'{hour} hr '
    if min or len(time_str):
        time_str = f'{time_str}{min} min '
    if sec or len(time_str):
        time_str = f'{time_str}{sec} sec '
    time_str = f'{time_str}{ms} ms'
    return time_str

class AppInfo():
    @staticmethod
    def logdir():
        return os.path.join(QStandardPaths.standardLocations(
            QStandardPaths.GenericConfigLocation)[0], "NetconfTool/logs")

    @staticmethod
    def settingDir():
        return os.path.join(QStandardPaths.standardLocations(
            QStandardPaths.GenericConfigLocation)[0], "NetconfTool")
    @staticmethod
    def currentVerStr()->str :
        version_f = QFile(':/VERSION')
        ver_str = '0.0.0'
        if version_f.open(QIODevice.ReadOnly):
            read_str = QTextStream(version_f).readAll()
            if read_str :
                ver_str = str(read_str)
        return ver_str

    @staticmethod
    def currentVerCode()->list:
        vstr = AppInfo.currentVerStr()
        return vstr.split('.')

def singleton(cls):
    _instance_lock = threading.Lock()
    instances = {}

    def _singleton(*args, **kwargs):
        if cls not in instances:
            with _instance_lock:   # 为了保证线程安全在内部加锁
                if cls not in instances:
                    instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return _singleton

@singleton
class SingletonLogger(object):
    # 设置输出的等级
    LEVELS = {
        'NOSET': logging.NOTSET,
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL}

    def __init__(self, name: str = ''):
        self.logger = logging.getLogger(name)
        # 创建文件目录
        logs_dir = AppInfo.logdir()
        os.makedirs(logs_dir, exist_ok=True)

        # 修改log保存位置
        logfilepath = os.path.join(logs_dir, "NetconfTool.log")
        rotatingFileHandler = logging.handlers.RotatingFileHandler(filename=logfilepath,
                                                                   maxBytes=1024 * 1024 * 5,
                                                                   encoding='utf-8',
                                                                   backupCount=5)
        rotatingFileHandler.setLevel(logging.INFO)

        # 设置输出格式
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s')
        rotatingFileHandler.setFormatter(formatter)

        # 控制台句柄
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)

        # 添加内容到日志句柄中
        self.logger.addHandler(rotatingFileHandler)
        self.logger.addHandler(console)
        self.logger.setLevel(logging.NOTSET)
        self._logpath = logs_dir

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)

    def setLevel(self, level):
        self.logger.critical("Change log level to :%s", logging.getLevelName(level))
        for hander in self.logger.handlers:
            hander.setLevel(level)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s',
                    level=logging.DEBUG)
    logging.debug("AppInfo.logdir: %s", AppInfo.logdir())
    logging.debug("AppInfo.settingDir: %s", AppInfo.settingDir())
    logging.debug(f'{millsecondToStr(152330222)}')