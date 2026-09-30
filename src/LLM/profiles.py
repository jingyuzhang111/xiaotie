"""
模型档位(用哪个模型、什么参数)

为什么要把这些参数收成一张表:
    之前参数散落在 4 个文件里,同一个任务(情绪分析)甚至出现了两套:
        emotion.py      temperature=0.0  max_tokens=500  无 response_format
        LLMrequest.py   temperature=0.1  max_tokens=200  有 response_format
    收拢之后,想调哪个档只改一处;想知道"到底用的是什么参数"也只在这一处看。

下面的默认值全部保持原样 —— 这一步是纯搬迁,不改行为。
"""
from dataclasses import dataclass, field

from src.config import *


@dataclass(frozen=True)
class LLMProfile:
    """一个"档位":用哪个模型 + 什么参数"""

    # 这三个都来自 os.getenv,值可能是 None(没配)。
    #
    # repr=False:阻止 dataclass 默认的 repr 把 API Key 打进终端/日志。
    key: str | None = field(repr=False)
    base_url: str | None
    model: str | None

    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None

    thinking: bool = True      # False 时显式关掉思考链(DeepSeek 要走 extra_body)
    force_json: bool = False   # True 时要求服务端返回 json_object


PROFILES: dict[str, LLMProfile] = {

    # ---- 文本档:通用文本,由 llm_manager.chat_stream 这个兼容壳使用 ----
    "text": LLMProfile(
        key=LLM_TEXT_KEY, base_url=LLM_TEXT_URL, model=LLM_TEXT_NAME,
        temperature=0.7, max_tokens=5000, top_p=0.9,
    ),

    # 决策档：
    "decide": LLMProfile(
        key=LLM_TEXT_KEY, base_url=LLM_TEXT_URL, model=LLM_TEXT_NAME,
        temperature=0.7, max_tokens=5000, top_p=0.9, force_json=True,
    ),

    # 思考档：用于mainloop中循环里的思考层
    "think": LLMProfile(
        key=LLM_TEXT_KEY, base_url=LLM_TEXT_URL, model=LLM_TEXT_NAME,
        temperature=0.7, max_tokens=5000, top_p=0.9,
        thinking=True, force_json=False,
    ),

    # ---- 摘要档:记忆压缩(把一段对话提炼成 summary + keywords)。参数也先保持原样 ----
    "summarize": LLMProfile(
        key=LLM_TEXT_KEY, base_url=LLM_TEXT_URL, model=LLM_TEXT_NAME,
        temperature=0.7, max_tokens=5000, top_p=0.9,force_json=True
    ),

    # ---- 情绪档:单人单条,输出**单个 JSON 对象** ----
    "emotion": LLMProfile(
        key=LLM_EMOTION_KEY, base_url=LLM_EMOTION_URL, model=LLM_EMOTION_NAME,
        temperature=0.1, max_tokens=200, thinking=False, force_json=True,
    ),

    # ---- 情绪批档:一次分析多人,输出的是 JSON **数组** ----
    # 注意 force_json=False 是必须的,不是遗漏:
    #   json_object 模式要求返回对象,而这个档返回的是数组,开了会被服务端拒绝。
    # 这正是原来 emotion.py 不设 response_format 的真正原因。
    "emotion_batch": LLMProfile(
        key=LLM_EMOTION_KEY, base_url=LLM_EMOTION_URL, model=LLM_EMOTION_NAME,
        temperature=0.1, max_tokens=500, thinking=False, force_json=False,
    ),

    # ---- 回复档:把决策结果说成人话 ----
    # 和 decide 的关键差别:
    #   thinking=False  —— 说话不需要长推理链,开着只会吃 max_tokens 配额、拖慢响应
    #   temperature=0.8 —— 要有活人感,不能像念稿
    #   max_tokens=500  —— 回复本来就是短句
    "reply": LLMProfile(
        key=LLM_TEXT_KEY, base_url=LLM_TEXT_URL, model=LLM_TEXT_NAME,
        temperature=0.8, max_tokens=500, thinking=False,
    ),

    # ---- 视觉档:图片理解 ----
    # 原来就没有设 temperature / max_tokens,这里也保持不传,行为不变
    "vision": LLMProfile(
        key=LLM_IMAGE_KEY, base_url=LLM_IMAGE_URL, model=LLM_IMAGE_NAME,
    ),
}
