from openai import OpenAI
from src.LLM.prompt import create_prompt
from mongodb import *
from split import text_split
from src.logger import get_module_logger
import time
from mood import moodupdater
from msgbase import Response, FriendMsg

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
    fri_msg = FriendMsg(msg)
    resmsg = Response(msg=fri_msg)
    moodupdater.update_in_msgloop(fri_msg)
    db_add(fri_msg)
    prompt = create_prompt(fri_msg)

    response = chat_stream(fri_msg.content,prompt)
    resmsg.alter_response(response)
    db_add(resmsg)
    response_split = text_split(response)
    logger.info(response_split)

    return response_split





if __name__ == '__main__':
    content=chat_stream("你好")
    print(content)