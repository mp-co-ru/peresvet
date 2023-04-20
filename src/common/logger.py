#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import logging
import logging.config
import os
import sys

from loguru import logger
import json

from pydantic import BaseSettings

class Settings(BaseSettings):
    LOG_LEVEL: str = "CRITICAL"
    LOG_FILE_NAME: str = "/var/log/peresvet.log"
    LOG_RETENTION: str = "1 months"
    LOG_ROTATION: str = "20 days"

settings = Settings()

class InterceptHandler(logging.Handler):
    loglevel_mapping = {
        50: 'CRITICAL',
        40: 'ERROR',
        30: 'WARNING',
        20: 'INFO',
        10: 'DEBUG',
        0: 'NOTSET',
    }

    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except AttributeError:
            level = self.loglevel_mapping[record.levelno]

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        log = logger.bind(request_id='app')
        log.opt(
            depth=depth,
            exception=record.exc_info
        ).log(level,record.getMessage())


class PrsLogger:

    @classmethod
    def make_logger(cls):
        if settings.LOG_LEVEL == "DEBUG":
            fmt = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> <level>{level: <8}</level> : {name}.{function}.{line} :: <level>{message}</level>"
        else:
            fmt = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> <level>{level: <8}</level> :: <level>{message}</level>"

        return cls.customize_logging(
            settings.LOG_FILE_NAME,
            level=settings.LOG_LEVEL,
            retention=settings.LOG_RETENTION,
            rotation=settings.LOG_ROTATION,
            format=fmt
        )

    @classmethod
    def customize_logging(cls, filepath: str, level: str, rotation: str, retention: str, format: str):

        logger.remove()
        logger.add(
            sys.stdout,
            enqueue=True,
            colorize=True,
            backtrace=True,
            level=level.upper(),
            format=format
        )
        logger.add(
            str(filepath),
            rotation=rotation,
            retention=retention,
            enqueue=True,
            backtrace=True,
            level=level.upper(),
            format=format
        )
        logging.basicConfig(handlers=[InterceptHandler()], level=0)
        logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
        for _log in ['uvicorn',
                     'uvicorn.error',
                     'fastapi'
                     ]:
            _logger = logging.getLogger(_log)
            _logger.handlers = [InterceptHandler()]

        return logger.bind(request_id=None, method=None)


    @classmethod
    def load_logging_config(cls, config_path):
        config = None
        with open(config_path) as config_file:
            config = json.load(config_file)
        return config
