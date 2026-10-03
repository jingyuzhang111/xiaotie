"""
统一的 LLM 调用入口

我的天哪蓝色肥鱼大人

"""
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

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

    reasoning: str = ""                         # 思考链(内心独白)
    tool_calls: list[Any] = field(default_factory=list)   # 模型要求调用的工具


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

    # force_json 和 tools 是互斥的,这里让 tools 优先:
    if conf.force_json and shape != SHAPE_TOOLS:
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
    """装饰logger格式，带上 trace / profile / shape / 耗时 / 尝试次数 / token 用量"""

    tokens = f"in {result.prompt_tokens:>4} out {result.completion_tokens:>4}"
    line = (f"trace={result.trace} | {profile:>13} | {shape:<5} | "
            f"{result.elapsed:5.2f}s | {result.attempts}次 | {tokens} |")
    if not result.ok:
        logger.warning(f"{line} 失败: {result.error}")
        return

    # 工具档的 text 常常是空的(模型直接要求调工具),只写 ok 看不出它干了什么,
    # 所以把要调的工具名带上
    if result.tool_calls:
        names = ",".join(
            getattr(getattr(tc, "function", None), "name", "?")
            for tc in result.tool_calls
        )
        logger.info(f"{line} ok 工具[{names}]")
    else:
        logger.info(f"{line} ok")


def _with_correction(
    messages: list[ChatCompletionMessageParam], bad_text: str
) -> list[ChatCompletionMessageParam]:
    """
    把模型上一次的错答 + 一句纠正要求追加进对话,用来再问一次。

    措辞不特指“不是合法 JSON” —— 出错原因可能是语法,也可能是字段/层级不对。
    """
    return messages + [
        ChatCompletionAssistantMessageParam(role="assistant", content=bad_text),
        ChatCompletionUserMessageParam(
            role="user",
            content="你上一次的输出不符合要求。请严格按上面要求的格式"
                    "重新输出一个 JSON 对象,不要任何其他文字、解释或代码块。",
        ),
    ]

def call(
    system: str | None = None,
    user: str | None = None,
    *,
    messages: list[ChatCompletionMessageParam] | None = None,
    profile: str = "text",
    shape: str = SHAPE_TEXT,
    tools: list[dict[str, Any]] | None = None,
    images: list[str] | None = None,
    trace: str | None = None,
    retries: int = 1,
    timeout: float = 60.0,
    validate: Callable[[Any], bool] | None = None,
) -> LLMResult:
    """
    发一次 LLM 调用

    system / user  提示词。只在 messages 没给时才用
    messages       完整对话数组。function calling 的多轮历史必须走这个入口 ——
                   assistant 的 tool_calls 和后面的 tool 结果是一对一的,
                   用 system/user 两条消息装不下。
                   给了它,就忽略 system / user / images(图片直接写进 messages)
    profile        档位名,见 src/LLM/profiles.py
    shape          text | json | tools
    tools          shape="tools" 时的工具 schema(OpenAI 原生格式)
    images         data URL 列表;给了就是多模态输入
    trace          链路标识。同一条用户消息触发的多次调用传同一个,日志就能串起来
    retries        失败后的额外重试次数(0 = 不重试)
    validate       shape="json" 时校验解析结果的结构。返回 False 会当成失败并触发重试。
                   光靠解析只能保证“是合法 JSON”,保证不了字段对不对 ——
                   比如模型把输入的形状照抄回来,语法完全合法,结构却是错的。
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

    # 另起一个名字而不是复用 messages 参数:
    # 参数的类型是 "list | None",下面要的是确定非 None 的值
    chat_messages: list[ChatCompletionMessageParam] = (
        messages if messages is not None
        else _build_messages(system or "", user or "", images)
    )
    kwargs = _build_kwargs(conf, shape, tools)

    # 用于修正格式不对的返回值
    attempt_messages = chat_messages

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
                # 两个 getattr 都是防御性的:
                #   reasoning_content 是 DeepSeek 扩展字段,别的服务商没有
                #   不调工具时 tool_calls 是 None,不是 []
                reasoning=(getattr(message, "reasoning_content", None) or "").strip(),
                tool_calls=list(getattr(message, "tool_calls", None) or []),
                elapsed=elapsed,
                trace=trace,
                attempts=attempts,
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
            )


            if shape == SHAPE_JSON:
                result = _parse_json(result)
                if result.ok and validate is not None and not validate(result.data):
                    result.ok = False
                    result.error = "JSON 结构不符合预期"


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
