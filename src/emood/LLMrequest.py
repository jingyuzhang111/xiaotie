import json
from typing import Dict,List,Tuple
from src.config import *
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

from src.LLM.client import call, SHAPE_JSON
from src.logger import get_module_logger
logger = get_module_logger('LLMrequest')

def get_prompt(content:dict):
    if content.keys() != {"总消息"}:
        sys_prompt = """你是能够输出对其他人情感的机器, 你能够接收他人的消息,并输出那些消息让你感到的情感. 
你只输出JSON格式,不要增添要求之外的任何文本。情感分析基于Plutchik理论。尽量简短快速地给出分析结果
你收到的是一个 JSON 对象,每项是"某个人的名字: 他说的话"(可能只有一个人)。
你要输出的是**你读完那段话之后的感受**,不是把输入的形状搬回来。
以Plutchik理论为根据分析,并严格按下面 user 给的格式输出。
"""
        user_prompt = f"""
需要分析的文本如下：{json.dumps(content, ensure_ascii=False)}
注意:上面那对花括号只是"人名: 他的话"的标签,**不是**输出格式。
请输出一个JSON字符串,不许添加大括号内容以外的任何字符,格式如下:
{{"name":"人名","喜悦":0-10,"悲伤":0-10,"愤怒":0-10,"恐惧":0-10,"惊讶":0-10,"期待":0-10,"厌恶":0-10,"信任":0-10,"dominant":"情感","intensity":"low/medium/high","content":"你对这段文本的整体情感感受和理解,用一句话描述."}}
"""

    else:
        sys_prompt = """你是能够输出对其他人情感的机器, 你能够接收他人的消息,并输出那些消息让你感到的情感. 
你只输出JSON格式,不要增添要求之外的任何文本。尽量简短快速地给出分析结果
你收到的是整段对话的上下文,要输出你读完它之后的整体感受。
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


def _looks_like_emotion(data) -> bool:
    """
    判断返回的能不能用。

    嵌套结构({"人名": {...}})也算合格 —— 后面 _unwrap_single 会解包,
    为它再花一次调用不划算。只有彻底没法用的才重试。
    """
    if not isinstance(data, dict):
        return False
    if "name" in data:
        return True
    return len(data) == 1 and isinstance(next(iter(data.values())), dict)


def LLM_get_one_emotion(content):
    """分析单独一段文本的情感状态"""
    sys_prompt, user_prompt = get_prompt(content)

    # 档位 emotion = LLM_EMOTION_* + temperature=0.1 + max_tokens=200
    #             + 关思考链 + 服务端 json_object
    result = call(
        sys_prompt, user_prompt,
        profile="emotion", shape=SHAPE_JSON,
        validate=_looks_like_emotion,
        retries=1,
    )
    if not result.ok:
        logger.warning(f"情绪分析失败: {result.error}")
        return None
    return _unwrap_single(result.data)


def _unwrap_single(data):
    """
    模型偶尔会把输入的结构照抄回来:输入 {"人名": "文本"},
    它却输出 {"人名": {"喜悦": ...}} 而不是 {"name": "人名", "喜悦": ...}。

    在数据入口解包成统一形状,免得下游每处都要自己防。
    """
    if not isinstance(data, dict) or "name" in data or len(data) != 1:
        return data

    name, inner = next(iter(data.items()))
    if not isinstance(inner, dict):
        return data

    inner.setdefault("name", name)
    logger.info(f"情绪分析返回了嵌套结构,已解包为: {name}")
    return inner


def analyze_many_parallel(contents:Dict[str,str]):
    """分析多段文本的情感状态"""
    results = {}
    failed = []
    future_to_name = {}
    start = time.time()
    # 创建线程池，用于加速情感分析
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
    