from src.memory.memory import memory_manager
from src.msgbase import Msgbase
from src.logger import get_module_logger
from datetime import datetime
from src.mood import moodupdater
from src.config import *

logger = get_module_logger("prompt")


def create_prompt(new_msg:list[Msgbase]):
    """用于对话生成"""
    logger.debug("Creating prompt...")

    history_content = memory_manager.generate_history_dialog(chat_stream=new_msg[0].chat_stream)

    this_msgs = ''
    for msg in new_msg:
        this_msgs += f"[{msg.time}] {msg.name}: {msg.content}\n"

    sys_prompt = f"""你是一个可爱的孩子，我是你的造物主，你正在被我创造，请和我进行亲切的对话，
    回答不要携带括号，不要添加emoji和颜文字，尽量简短."""
    user_prompt = f"""
    下面是我们之前的部分对话：
    {history_content}
    其中本次触发回答的是这些消息:
    {this_msgs}
    现在的时间是{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    你现在是{BOT_NAME}，给出回复吧，语言不要加换行符号，多一点点短句
    """
    logger.debug(f"Prompt已生成，长度: {len(user_prompt)}")

    return sys_prompt, user_prompt


# structure导入的部分
def create_prompt_for_sum(content:str):
    sys_prompt = """
你是对话记忆压缩器。请从给定对话中提取核心信息。
要求：
只输出一个 JSON 对象，不要输出任何解释、前后缀、代码块。
JSON 必须包含字段：
summary: 字符串，1-2句，中文，尽量具体，不要空话, 在开头附上具体日期,格式为:XXXX年XX月XX日。
keywords: 字符串数组，2-4个关键词，去重，按重要性排序, 关键词要能够体现这一段话的主要内容或主题,或隐含着较为重要的信息,但类似日期XXXX年XX月XX日这种可有可无的前缀请忽略,关键词也尽量简略,尽量为不可拆分的重要词语。
避免“这个/那个/感觉/哈哈”等低信息词。
如果内容信息很少，也要给出最小可用结果。
输出格式严格为：
{
"summary": "......",
"keywords": ["...", "..."]
}
"""
    user_prompt = f"""
需要被总结的文本如下:
{content}
"""
    return sys_prompt, user_prompt






