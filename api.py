from openai import OpenAI
from prompt import create_prompt
import sys
import io
from msgbase import Msgbase
from mongodb import *
from split import text_split
from logger import get_module_logger
import time
from mood import moodupdater

logger = get_module_logger('api')

api_key = 'sk-uvsmlcbwngsfyrfusxebvlzageqpfpoatfgcasdvzbxmlgmk'
api_base = r'https://api.siliconflow.cn/v1/'
LLM_ds = "deepseek-ai/DeepSeek-V3.2-Exp"

client = OpenAI(
    api_key=api_key,
    base_url=api_base,
)

def chat_stream(content,prompt: str = None):
    start_time = time.time()
    response =client.chat.completions.create(
        model="deepseek-ai/DeepSeek-V3.2-Exp",  # 选择模型
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
        usage = response.usage
        print(f"Prompt Tokens: {usage.prompt_tokens}")
        print(f"Completion Tokens: {usage.completion_tokens}")
        print(f"Total Tokens: {usage.total_tokens}")
    content = response.choices[0].message.content
    return content

def create_response(name,content,chat_stream,group_name,):
    resMsg = {
        "name": name,
        "content": content,
        "chat_stream": chat_stream,
        "group_name": group_name,
    }
    return resMsg

def msg_process(msg):
    """处理消息的主方法，所有方法都在这里集成"""
    msg = Msgbase(msg)
    moodupdater.update_in_msgloop(msg)
    db_add(msg)
    prompt = create_prompt(msg)
    res_chatstream = msg.chat_stream
    res_groupname = msg.group_name
    res_name = BOT_NAME

    response = chat_stream(msg.content,prompt)
    response_split = text_split(response)
    logger.info(response_split)
    for res in response_split:
        res_dict = create_response(res_name,res,
                                   res_chatstream,res_groupname,)
        res = Msgbase(res_dict)
        db_add(res)
    return response_split





if __name__ == '__main__':
    content=chat_stream("你好")
    print(content)