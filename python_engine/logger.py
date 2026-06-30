"""统一日志配置"""

import logging
import os
import sys


def setup_logger(name: str = "gwent", level: int = logging.DEBUG) -> logging.Logger:
    """获取或创建 logger，自动检测 GWENT_LOG_FILE 环境变量"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)-18s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    log_file = os.environ.get("GWENT_LOG_FILE")
    if log_file:
        fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(name)-18s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh.setFormatter(file_fmt)
        logger.addHandler(fh)

    return logger


def add_file_handler(logger: logging.Logger, filepath: str) -> None:
    """手动添加文件输出 handler"""
    fh = logging.FileHandler(filepath, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)-18s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)


log = setup_logger()
