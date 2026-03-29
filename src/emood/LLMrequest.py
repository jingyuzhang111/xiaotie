import openai
import json
from typing import Dict,List,Tuple
from src.config import *
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

from src.logger import get_module_logger
logger = get_module_logger('LLMrequest')

client = openai.OpenAI(
            api_key=LLM_EMOTION_KEY,
            base_url=LLM_EMOTION_URL,
        )

def get_prompt(content:dict):
    if content.keys() != {"总消息"}:
        sys_prompt = """你是能够输出对其他人情感的机器, 你能够接收他人的消息,并输出那些消息让你感到的情感. 
你只输出JSON格式,不要增添要求之外的任何文本。情感分析基于Plutchik理论。尽量简短快速地给出分析结果
你收到的文本格式为: 
{
"人名": "消息",
}
其中"人名"指某个人的话语,"总消息"是把所有消息不以人分类直接拼接在一起的文本。
你需要分析每个人的消息以及总消息,输出你读每段文本后的情感感受,以Plutchik理论为根据进行分析,并严格按照给定格式输出.
"""
        user_prompt = f"""
需要分析的文本如下：{json.dumps(content, ensure_ascii=False)}
请输出一个JSON字符串,不许添加大括号内容以外的任何字符,格式如下:
{{"name":"人名","喜悦":0-10,"悲伤":0-10,"愤怒":0-10,"恐惧":0-10,"惊讶":0-10,"期待":0-10,"厌恶":0-10,"信任":0-10,"dominant":"情感","intensity":"low/medium/high","content":"你对这段文本的整体情感感受和理解,用一句话描述."}}
"""

    else:
        sys_prompt = """你是能够输出对其他人情感的机器, 你能够接收他人的消息,并输出那些消息让你感到的情感. 
你只输出JSON格式,不要增添要求之外的任何文本。尽量简短快速地给出分析结果
你收到的文本格式为: 
{
"总消息": "完整的对话上下文"
}
"""
        user_prompt = f"""
需要分析的文本如下：{json.dumps(content, ensure_ascii=False)}
请输出一个JSON字符串,不许添加大括号内容以外的任何字符,格式如下:
{{"name":"总消息",
"喜悦":0-10,"悲伤":0-10,"愤怒":0-10,"恐惧":0-10,
"惊讶":0-10,"期待":0-10,"厌恶":0-10,"信任":0-10,
"dominant":"情感","intensity":"low/medium/high",
"content":"你对这段文本的整体情感感受和理解,用一句话描述"}}
"""
    return sys_prompt, user_prompt


def LLM_get_one_emotion(content):
    """分析单独一段文本的情感状态"""
    sys_prompt, user_prompt = get_prompt(content)

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=LLM_EMOTION_NAME,  # 选择模型
            messages=[
                {"role": "system",
                    "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=100,
        )
        response_content = response.choices[0].message.content.strip()
        llm_time = time.time() - start_time
        logger.debug(f"LLM推理耗时: {llm_time:.2f}s")

        response_content =json.loads(response_content)
        logger.info(response_content)
    except Exception as e:
        logger.error(f'大模型不懂情感: {e}')
        response_content = None

    return response_content


def analyze_many_parallel(contents:Dict[str,str]):
    """分析多段文本的情感状态"""
    results = {}
    failed = []
    future_to_name = {}
    start = time.time()
    with ThreadPoolExecutor(max_workers=5) as t:
        for name, content in contents.items():
            if not content.strip():
                failed.append(name)
                continue

            future = t.submit(LLM_get_one_emotion, {name: content})
            future_to_name[future] = name
        
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result = future.result(timeout=8)
                if result is not None:
                    logger.info(f"情感分析成功: {name}")
                    results[name] = result
                else:
                    logger.warning(f"情感分析失败: {name}")
                    failed.append(name)
            except TimeoutError:
                logger.error(f"情感分析超时: {name}")
                failed.append(name)
            except Exception as e:
                logger.error(f"情感分析异常: {name}, 错误: {e}")
                failed.append(name)

        return {
            "results": results,
            "failed": failed,
            "time": time.time() - start
        }


if __name__ == "__main__":
    batch_texts = {
        "小明": "我今天好开心啊！",
        "小红": "我感觉有点难过。",
        "小强": "两个傻逼",
        "总消息": "小明: 我今天好开心啊！\n小红: 我感觉有点难过。\n小强: 两个傻逼"
    }
    parallel_result = analyze_many_parallel(batch_texts)
    print(parallel_result)
    