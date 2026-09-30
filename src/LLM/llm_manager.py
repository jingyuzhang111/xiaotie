"""
LLM 调用(兼容壳)

真正的实现已经搬到 src/LLM/client.py + src/LLM/profiles.py。
这个文件保留是为了不动现有调用方:
    src/agent/desition.py
    src/memory/structure.py
新代码请直接用 src.LLM.client.call。
"""
from src.LLM.client import call, SHAPE_JSON
from src.logger import get_module_logger

logger = get_module_logger('llm_manager')


def chat_stream(sys_prompt, user_prompt: str = ''):
    """
    旧接口,行为保持不变:
      - 走 text 档(temperature=0.7 / max_tokens=5000 / top_p=0.9)
      - 要求模型吐 JSON,解析失败返回 None
    """
    result = call(sys_prompt, user_prompt, profile="text", shape=SHAPE_JSON)
    if not result.ok:
        logger.error(f"大模型请求或JSON解析失败: {result.error}")
        return None
    return result.data




