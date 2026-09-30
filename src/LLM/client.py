"""
统一的 LLM 调用入口

我的天哪蓝色肥鱼大人

"""
import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from openai import OpenAI, APIStatusError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from src.LLM.profiles import PROFILES, LLMProfile
from src.logger import get_module_logger

logger = get_module_logger("llm")


# 输出形态。只影响两件事:要不要带 tools、返回值怎么解析。
SHAPE_TEXT = "text"     # 自然语言,原样返回
SHAPE_JSON = "json"     # 要求模型吐 JSON,这里自动解析成 dict / list
SHAPE_TOOLS = "tools"   # 原生 function calling,返回 message(内含 tool_calls)

"""
shape: 检查代码的形式约束
profile: LLM调用的参数

json格式约束：
1.提示词直接说
2.shape=json只是对结果的本地审核，不改变输出结果，但是能拦截错误格式，格式不对就重新请求。
3.force_json是对于LLM请求的硬性约束，有这个，AI一定输出json格式，里面键值对不对另说。

"""

@dataclass
class LLMResult:
    """一次调用的结果。失败也是"结果",不抛异常"""

    ok: bool
    text: str = ""
    data: Any = None            # shape="json" 时的解析结果
    message: Any = None         # shape="tools" 时的原始 message,用来取 tool_calls
    error: str = ""
    elapsed: float = 0.0
    trace: str = ""
    attempts: int = 0           # 实际发起了几次请求(0 = 压根没发,比如档位名写错)
    prompt_tokens: int = 0      # 所有尝试的**合计**用量,不是最后一次
    completion_tokens: int = 0


_clients: dict[tuple[str, str], OpenAI] = {}
_client_lock = threading.Lock()


def _get_client(api_key: str, base_url: str) -> OpenAI:
    """按 (key, base_url) 缓存 client —— 全项目只在这里创建"""
    cache_key = (api_key, base_url)
    with _client_lock:
        client = _clients.get(cache_key)
        if client is None:
            client = OpenAI(api_key=api_key, base_url=base_url)
            _clients[cache_key] = client
        return client


def _build_messages(
    system: str, user: str, images: list[str] | None
) -> list[ChatCompletionMessageParam]:
    """
    组装 messages;带图片时 user 的 content 变成多模态数组。

    这里用 SDK 自带的 TypedDict 构造,而不是裸 dict:
    裸 dict 的类型是 dict[str, Any],和 SDK 要求的
    ChatCompletionMessageParam(TypedDict 联合)不兼容,
    会在 create() 那里报一长串"重载与提供的参数不匹配"。
    """
    system_msg = ChatCompletionSystemMessageParam(role="system", content=system)

    if not images:
        return [system_msg, ChatCompletionUserMessageParam(role="user", content=user)]

    parts: list[ChatCompletionContentPartParam] = [
        ChatCompletionContentPartTextParam(type="text", text=user)
    ]
    for img in images:
        parts.append(
            ChatCompletionContentPartImageParam(type="image_url", image_url={"url": img})
        )
    return [system_msg, ChatCompletionUserMessageParam(role="user", content=parts)]


def _build_kwargs(conf: LLMProfile, shape: str, tools: list[dict] | None) -> dict[str, Any]:
    """
    只把"档位里明确设了值"的参数传给服务端。
    temperature 为 None 就完全不传 —— 这样 vision 档能保持服务端默认,和以前一致。
    """
    kwargs: dict[str, Any] = {"model": conf.model}

    if conf.temperature is not None:
        kwargs["temperature"] = conf.temperature
    if conf.max_tokens is not None:
        kwargs["max_tokens"] = conf.max_tokens
    if conf.top_p is not None:
        kwargs["top_p"] = conf.top_p

    if not conf.thinking:
        # DeepSeek 关思考链必须走 extra_body,放顶层会被 SDK 拒绝
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    if conf.force_json:
        kwargs["response_format"] = {"type": "json_object"}

    if shape == SHAPE_TOOLS and tools:
        kwargs["tools"] = tools

    return kwargs


def _parse_json(result: LLMResult) -> LLMResult:
    if not result.text:
        result.ok = False
        result.error = "返回空内容"
        return result
    try:
        result.data = json.loads(result.text)
    except json.JSONDecodeError as e:
        result.ok = False
        result.error = f"不是合法 JSON: {e}"
    return result


def _log(result: LLMResult, profile: str, shape: str) -> None:
    """
    每次调用一条。一条用户消息会触发多次调用,靠 trace 串成一条链,
    这样出问题时能一眼看出是哪一层。

    次数那一列是用来判断"重试值不值"的:
        1次 ok        -> 一次就成
        2次 ok        -> 重试救回来了(但如果经常 2 次,说明源头该调)
        4次 失败      -> 重试完全无效,加大 retries 只是烧钱,该改提示词/开 force_json
    """
    tokens = f"in {result.prompt_tokens:>4} out {result.completion_tokens:>4}"
    line = (f"trace={result.trace} | {profile:>13} | {shape:<5} | "
            f"{result.elapsed:5.2f}s | {result.attempts}次 | {tokens} |")
    if result.ok:
        logger.info(f"{line} ok")
    else:
        logger.warning(f"{line} 失败: {result.error}")


def _with_correction(
    messages: list[ChatCompletionMessageParam], bad_text: str
) -> list[ChatCompletionMessageParam]:
    """
    把模型上一次的错答 + 一句纠正要求追加进对话,用来再问一次。
    """
    return messages + [
        ChatCompletionAssistantMessageParam(role="assistant", content=bad_text),
        ChatCompletionUserMessageParam(
            role="user",
            content="你上一次的输出不是合法 JSON。请只输出一个 JSON 对象,"
                    "不要任何其他文字、解释或代码块。",
        ),
    ]

def call(
    system: str,
    user: str,
    *,
    profile: str = "text",
    shape: str = SHAPE_TEXT,
    tools: list[dict[str, Any]] | None = None,
    images: list[str] | None = None,
    trace: str | None = None,
    retries: int = 1,
    timeout: float = 60.0,
) -> LLMResult:
    """
    发一次 LLM 调用

    system / user  提示词
    profile        档位名,见 src/LLM/profiles.py
    shape          text | json | tools
    tools          shape="tools" 时的工具 schema(OpenAI 原生格式)
    images         data URL 列表;给了就是多模态输入
    trace          链路标识。同一条用户消息触发的多次调用传同一个,日志就能串起来
    retries        失败后的额外重试次数(0 = 不重试)
    """
    trace = trace or uuid.uuid4().hex[:6]
    conf = PROFILES.get(profile)
    if conf is None:
        return LLMResult(ok=False, error=f"未知档位: {profile}", trace=trace)

    # 收窄成局部变量:这三个字段来自 os.getenv,类型上是 str | None。
    # 在这里一次性判完,下面才能安全地当 str 用。
    api_key, base_url = conf.key, conf.base_url
    if not (api_key and base_url and conf.model):
        return LLMResult(
            ok=False,
            error=f"档位 {profile} 的 key/url/model 没配齐(检查 .env)",
            trace=trace,
        )

    messages = _build_messages(system, user, images)
    kwargs = _build_kwargs(conf, shape, tools)

    # 用于修正格式不对的返回值
    attempt_messages = messages

    elapsed = 0.0
    last_error = ""

    total_prompt = 0
    total_completion = 0
    attempts = 0

    for attempt in range(retries + 1):
        # 放在 try 外面:进了这轮循环就一定算数,不受异常影响
        attempts = attempt + 1
        start = time.time()
        try:
            response = _get_client(api_key, base_url).chat.completions.create(
                messages=attempt_messages, timeout=timeout, **kwargs,
            )
            elapsed += time.time() - start

            message = response.choices[0].message
            used = getattr(response, "usage", None)
            total_prompt += getattr(used, "prompt_tokens", 0) or 0
            total_completion += getattr(used, "completion_tokens", 0) or 0


            result = LLMResult(
                ok=True,
                text=(message.content or "").strip(),
                message=message,
                elapsed=elapsed,
                trace=trace,
                attempts=attempts,
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
            )


            if shape == SHAPE_JSON:
                result = _parse_json(result)


            if result.ok:   
                _log(result, profile, shape)
                return result

            # 这里是json失败，用来重试的地方
            last_error = result.error
            if attempt < retries:
                attempt_messages = _with_correction(attempt_messages, result.text)



        except APIStatusError as e:
            # 带状态码的 HTTP 错误
            elapsed += time.time() - start
            last_error = f"{type(e).__name__}: {str(e)[:300]}"
            code = getattr(e, "status_code", 0) or 0
            if 400 <= code < 500 and code != 429:
                break
        except Exception as e:
            # 兜底:网络超时、连接失败、SDK 内部错误……
            elapsed += time.time() - start
            last_error = f"{type(e).__name__}: {str(e)[:300]}"

    result = LLMResult(ok=False, error=last_error, elapsed=elapsed, trace=trace,
                       attempts=attempts,
                       prompt_tokens=total_prompt, completion_tokens=total_completion)
    _log(result, profile, shape)
    return result

if __name__ == "__main__":
    r = call("Reply in plain English. Do NOT use JSON. No braces.",
         "Say hi in three words.",
         profile="text", shape=SHAPE_JSON, retries=3)
    print("elapsed =", round(r.elapsed, 2))
