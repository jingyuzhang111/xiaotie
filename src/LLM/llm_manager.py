from openai import OpenAI
from src.config import *
import time
from typing import Any

from src.logger import get_module_logger
logger = get_module_logger('llm_manager')


client = OpenAI(
    api_key=LLM_TEXT_KEY,
    base_url=LLM_TEXT_URL,
)

def chat_stream(sys_prompt,user_prompt: str = ''):
    start_time = time.time()
    if LLM_TEXT_NAME is None:
        logger.error("LLM_TEXT_NAME 是空的.")
        return ""
    response =client.chat.completions.create(
        model=LLM_TEXT_NAME,  # 选择模型
        messages=[
            {"role": "system","content": f"{sys_prompt}"},
            {"role": "user", "content": f"{user_prompt}"},
        ],
        stream=False,
        temperature=0.7,# 随机性，越大越活泼，也更不知所云
        max_tokens=5000,
        top_p=0.9,
    )
    delta_time = time.time() - start_time
    logger.info(f"调用LLM时间: {delta_time}")
    if hasattr(response, 'usage'):
        usage:Any = response.usage
        logger.info(f"Prompt Tokens: {usage.prompt_tokens}")
        logger.info(f"Completion Tokens: {usage.completion_tokens}")
        logger.info(f"Total Tokens: {usage.total_tokens}")
    content = response.choices[0].message.content
    return content



