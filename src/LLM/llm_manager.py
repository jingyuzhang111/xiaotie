from openai import OpenAI
from src.config import *
import time
from typing import Any
import json

from src.logger import get_module_logger
logger = get_module_logger('llm_manager')


client = OpenAI(
    api_key=LLM_TEXT_KEY,
    base_url=LLM_TEXT_URL,
)

def chat_stream(sys_prompt,user_prompt: str = ''):

    try:
        start_time = time.time()
        if not LLM_TEXT_NAME:
            logger.error("LLM_TEXT_NAME 是空的.")
            return ""
        response = client.chat.completions.create(
            model=LLM_TEXT_NAME,
            messages=[
                {"role": "system","content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            temperature=0.7,# 随机性，越大越活泼，也更不知所云
            max_tokens=5000,
            top_p=0.9,
        )
        response_content = response.choices[0].message.content.strip()
        llm_time = time.time() - start_time
        logger.debug(f"LLM推理耗时: {llm_time:.2f}s")

        response_content = json.loads(response_content)
        logger.info(response_content)
    except Exception as e:
        logger.error("大模型请求或JSON解析失败: {}: {}", type(e).__name__, str(e)[:500])
        response_content = None

    return response_content




