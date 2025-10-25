from loguru import logger
import sys
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

logger.remove()

# 基础配置类
class LogConfig:
    def __init__(self, **kwargs):
        self.config = {
            "console_level": "DEBUG",
            "file_level": "DEBUG",
            "console_format": "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[module]}</cyan> | <level>{message}</level>",
            "file_format": "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[module]} | {message}",
            "log_dir": "logs",
            "rotation": "00:00",
            "retention": "7 days",
            "compression": "zip",
        }
        self.config.update(kwargs)

mongodb=LogConfig(
    console_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<fg #339af0>数据库消息</fg #339af0> | "
    "<level>{message}</level>",  # 注意：这里原代码是<message>{}</message>，应该是<level>{message}</level>
    file_format="{time:YYYY-MM-DD HH:mm:ss} | 数据库 | {level} | {message}",
)

# 用于记录已经添加过处理器的模块
_registered_modules = set()

def get_module_logger(module:str, config:Optional[LogConfig]=None):
    if config is None:
        config = LogConfig()

    # 如果已经为该模块添加过处理器，则直接返回绑定的logger
    if module in _registered_modules:
        return logger.bind(module=module)

    # 控制台处理器
    logger.add(
        sink=sys.stderr,
        level=config.config['console_level'],
        format=config.config['console_format'],
        filter=lambda record: record["extra"].get("module") == module,
        enqueue=True,
    )

    log_dir = Path(config.config['log_dir'])
    log_dir.mkdir(exist_ok=True)

    # 文件处理器 - 使用按日期轮转的文件名
    log_file = log_dir / module / "{time:YYYY-MM-DD}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        sink=str(log_file),  # 使用字符串路径
        level=config.config['file_level'],  # 注意：这里原来用的是console_level，应该是file_level
        format=config.config['file_format'],
        rotation=config.config["rotation"],
        retention=config.config["retention"],
        compression=config.config["compression"],
        encoding="utf-8",
        filter=lambda record: record["extra"].get("module") == module,
        enqueue=True,
    )

    _registered_modules.add(module)
    return logger.bind(module=module)