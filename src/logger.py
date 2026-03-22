from loguru import logger
import sys
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
import threading

logger_initialized = False
_handler_registry = {}
_logger_lock = threading.RLock()


class LogConfig:
    def __init__(self, **kwargs):
        self.config = {
            "console_level": "DEBUG",
            "file_level": "DEBUG",
            "console_format": "<green>{time:HH:mm:ss}</green> |"
                              " <level>{level: <8}</level> |"
                              " <cyan>{extra[module]}</cyan> |"
                              " <level>{message}</level>",
            "file_format": "{time:YYYY-MM-DD HH:mm:ss} |"
                           " {level: <8} | "
                           "{extra[module]} | "
                           "{message}",
            "log_dir": "logs",
            "rotation": "00:00",
            "retention": "7 days",
            "compression": "zip",
        }
        self.config.update(kwargs)


config_dict = {
    "mongodb":LogConfig(
        console_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<fg #339af0>数据库消息</fg #339af0> | "
        "<level>{message}</level>",
        file_format="{time:YYYY-MM-DD HH:mm:ss} | 数据库 | {level} | {message}",
    ),
    "api":LogConfig(
        console_format="<black>{time:YYYY-MM-DD HH:mm:ss}</black> | "
        "<level>{level: <8}</level> | "
        "<fg #339af0>api消息</fg #339af0> | "
        "<level>{message}</level>",
        file_format="{time:YYYY-MM-DD HH:mm:ss} | api | {level} | {message}",
    )
}


def ensure_logger_initialized():
    """
    只在第一次调用时清理全局 handlers（防止热重载/多次导入导致 handlers 丢失）
    """
    global logger_initialized   # 保证只运行一次
    with _logger_lock:
        if not logger_initialized:
            logger.remove() # 移除默认的 handler
            logger_initialized = True


def get_module_logger(module: str, config: Optional[LogConfig]=None):
    ensure_logger_initialized()

    with _logger_lock:
        # 获取配置
        if config is None:
            config = config_dict.get(module, LogConfig())

        # 如果module已经添加过，先移除之前的handlers
        if module in _handler_registry:
            for handler in _handler_registry[module]:
                try:
                    logger.remove(handler)
                except Exception:
                    pass
            del _handler_registry[module]

        module_logger = logger.bind(module=module)
        handler_ids = []

        console_id = logger.add(
            sink=sys.stderr,
            level=config.config['console_level'],
            format=config.config['console_format'],
            filter=lambda record: record["extra"].get("module") == module,
            enqueue=True,
        )
        handler_ids.append(console_id)

        log_dir = Path(config.config['log_dir'])
        log_dir.mkdir(exist_ok=True)
        if module in config_dict:
            file_path = log_dir / module / "{time:YYYY-MM-DD}.log"
        else:
            file_path = log_dir / "other" / "{time:YYYY-MM-DD}.log"
        file_path.parent.mkdir(exist_ok=True)

        # YYYY-MM-DD-HH-mm-ss
        # 文件配置
        file_id = logger.add(
            sink=file_path,
            level=config.config['file_level'],
            format=config.config['file_format'],
            filter=lambda record: record["extra"].get("module") == module,
            enqueue=True,
            encoding="utf-8",
            rotation=config.config["rotation"],
        )
        handler_ids.append(file_id)

        _handler_registry[module] = handler_ids

        return module_logger

if __name__ == "__main__":
    logger = get_module_logger("mongodb")
    logger.info("正常运行")
    logger = get_module_logger("api")
    logger.info("api正常记录")
    logger = get_module_logger("app")
    logger.info("其余文件按照全局配置")