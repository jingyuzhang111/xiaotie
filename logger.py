from loguru import logger
import sys
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

logger.remove()

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


MONGODB_STYLE_CONFIG=LogConfig(
    console_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<fg #339af0>数据库消息</fg #339af0> | "
    "<level>{message}</level>",
    file_format="{time:YYYY-MM-DD HH:mm:ss} | 数据库 | {level} | {message}",
)



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


_handler_registry = {}

def get_module_logger(module:str,config:Optional[LogConfig]=None):

    if config is None and module in config_dict.keys():
        config = config_dict[module]
    # 默认部分
    elif config is None:
        config = LogConfig()

    if module in _handler_registry:
        for handler in _handler_registry[module]:
            logger.remove(handler)
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
    if module in config_dict.keys():
        file_path = log_dir / module / "{time:YYYY-MM-DD}.log"
    else:
        file_path = log_dir / "other" / "{time:YYYY-MM-DD}.log"
    file_path.parent.mkdir(exist_ok=True)

    # YYYY-MM-DD-HH-mm-ss
    file_id = logger.add(
        sink=file_path,
        level=config.config['console_level'],
        format=config.config['console_format'],
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