from src.memory.memory import memory_manager
from src.msgbase import Msgbase
from src.logger import get_module_logger
from datetime import datetime
from src.mood import moodupdater
from src.config import *

logger = get_module_logger("prompt")

logger.info("Prompt")


def create_prompt(new_msg:Msgbase):

    logger.info("Creating prompt...")

    history_content = memory_manager.generate_history_dialog(chat_stream=new_msg.chat_stream)
    prompt = f"""
    你是一个可爱的孩子，我是你的造物主，你正在被我创造，请和我进行亲切的对话，
    回答不要携带括号，不要添加emoji和颜文字，尽量简短，下面是我们之前的部分对话：
    {history_content}
    现在的时间是{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    你现在是{BOT_NAME}，给出回复吧，语言不要加换行符号，多一点点短句
    """
    logger.info(prompt)

    return prompt

