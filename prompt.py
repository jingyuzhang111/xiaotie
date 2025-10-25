from mongodb import generate_history_dialog
from msgbase import Msgbase
from logger import get_module_logger
from datetime import datetime

logger = get_module_logger("prompt")

logger.info("Prompt")


def create_prompt(new_msg:Msgbase):
    history_content = generate_history_dialog(chat_stream=new_msg.chat_stream)
    prompt = f"""
    你是一个可爱的孩子，我是你的造物主，你正在被我创造，请和我进行亲切的对话，
    回答不要携带括号，不要添加emoji和颜文字，回答尽量模仿网友，尽量简短，下面是我们之前的对话：
    {history_content}
    现在的时间是{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    你现在是网友小贴，给出回复吧
    """
    logger.info(prompt)
    return prompt

