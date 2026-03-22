from openai import OpenAI
from src.LLM.prompt import create_prompt
from src.mongodb import *
from src.split import text_split
import time
from src.mood import moodupdater
from src.msgbase import Response, FriendMsg
from src.globalcontrol import global_control
from src.config import *
from typing import Any

if global_control.speak:
    from src.plugins.ProcessAudio.readaudio import global_speaker

from src.logger import get_module_logger
logger = get_module_logger('api')



client = OpenAI(
    api_key=LLM_TEXT_KEY,
    base_url=LLM_TEXT_URL,
)

def chat_stream(content,prompt: str = ''):
    start_time = time.time()
    response =client.chat.completions.create(
        model=LLM_TEXT_NAME,  # 选择模型
        messages=[
            {"role": "system",
             "content": f"{prompt}"},
            {"role": "user", "content": f"{content}"},
        ],
        stream=False,
        temperature=0.7,# 随机性，越大越活泼，也更不知所云
        max_tokens=5000,
        top_p=0.9,
    )
    delta_time = time.time() - start_time
    logger.info(f"调用deepseek时间: {delta_time}")
    if hasattr(response, 'usage'):
        usage:Any = response.usage
        logger.info(f"Prompt Tokens: {usage.prompt_tokens}")
        logger.info(f"Completion Tokens: {usage.completion_tokens}")
        logger.info(f"Total Tokens: {usage.total_tokens}")
    content = response.choices[0].message.content
    return content

def create_response_format(name,content,chat_stream,group_name,):
    resMsg = {
        "name": name,
        "content": content,
        "chat_stream": chat_stream,
        "group_name": group_name,
    }
    return resMsg

def msg_process(msg):
    """处理消息的主方法，所有方法都在这里集成"""
    logger.info("进入消息处理函数")

    # 接收消息，转为消息类
    fri_msg = FriendMsg(msg)

    # 创建响应消息类
    resmsg = Response(msg=fri_msg)
    moodupdater.update_in_msgloop(fri_msg)
    db_add(fri_msg)
    prompt = create_prompt(fri_msg)

    response = chat_stream(fri_msg.content,prompt)
    resmsg.alter_response(response) # type: ignore
    db_add(resmsg)

    response_split = [response]
    if global_control.split:
        response_split = text_split(response)
    if global_control.speak:
        global_speaker.speak(response)

    logger.info(response_split)

    return response_split





if __name__ == '__main__':
    content=chat_stream("你好")
    print(content)