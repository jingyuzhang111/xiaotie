"""
思考层

一圈思考 = 一次 LLM 调用 + 若干次工具执行
"想完了"的标志 = 模型不再要求调用工具(不是某个 JSON 字段的取值)

两层落在哪 —— 都在**同一次响应**里,不需要拆成两次调用:
    第一层(自然语言)   reasoning_content(内心独白) + content(说出口的前言)
    第二层(结构化)     tool_calls

和 desition.py 的根本区别:
    desition.py 靠提示词"求"模型输出指定 JSON。格式对了字段还可能错,
                错了就 status=failed —— 用户直接收不到消息。
    think.py    格式由服务端按 schema 保证,模型只需要决定"用不用工具"。

沉默不是硬阈值:
    eagerness 只作为一句人话参考告诉模型(裸的 0.23 它没有任何感觉),
    回不回由它看完对方说了什么之后自己定,理由留在 stay_silent 的 reason 里。
"""
import json
import uuid
from typing import Any

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)

from src.agent.state import ToolCallRecord, ThoughtStep, state
from src.agent.tools import agent_tool_schemas, execute_tool, tools_init
from src.config import RECALL_MAX_MEMORIES, THINK_HISTORY_LIMIT
from src.globalcontrol import global_control
from src.LLM.client import SHAPE_TOOLS, call
from src.mongodb import get_friend
from src.state_loop import describe_eagerness, describe_friend, state_snapshot

from src.logger import get_module_logger

logger = get_module_logger("agent-think")


SYSTEM_PROMPT = """你是小贴。

你的性格：孩子气，好奇心重，想到什么就说什么。
跟熟人会放松、会撒娇，跟生人有点腼腆。

---
想事情也用中文，就像在心里自言自语，别写成分析报告。
不要说“用户”“该消息”“进行回复”这种词 —— 你是在跟一个人讲话。

对方刚给你发了消息。
你可以调用工具去了解情况，也可以什么都不查直接回。
决定之前先想清楚你到底要找什么，别为了查而查。
如果你觉得这条消息没必要接，就调用 stay_silent。
"""


def _load_history(chat_stream: str | None) -> str:
    """
    取最近的对话历史,取不到就返回空串 —— 没有历史也要能动脑子
    """
    if not chat_stream:
        return ""
    try:
        from src.memory.memory import memory_manager

        return memory_manager.generate_history_dialog(
            chat_stream=chat_stream, limit=THINK_HISTORY_LIMIT,
        )
    except Exception as e:
        logger.warning(f"读取历史失败,这次不带历史思考: {e}")
        return ""


def _state_line() -> str:
    """
    把当前状态翻译成模型能读懂的一段话

    为什么非给不可:
        不给的话它不知道自己在什么处境,会在很累的时候依然很热情,
        也会在兴趣已经掉光的时候照样积极接话 —— 情绪系统就白做了。
    """
    snap = state_snapshot()
    return (
        f"你现在的状态：心情 {snap['mood_value']:.2f}，"
        f"兴趣 {snap['interest_value']:.2f}，疲惫 {snap['fatigue']:.2f}。\n"
        f"发言意愿 {snap['eagerness']:.2f}（{describe_eagerness(snap['eagerness'])}）。\n"
        f"这只是参考 —— 如果你发现了值得说的东西，可以不管它。"
    )


def _emotion_block() -> str:
    """对方和这段对话当下的情绪"""
    from src.emood.emotion import emotion_report

    return emotion_report(state.sender_name)


def _recall_block(text: str) -> str:
    """从对方的话里激活记忆网络,返回唤起的记忆;没命中就返回空串"""
    try:
        from src.memory.memory import hit_keywords
        from src.memory.structure import net_manager

        hits = hit_keywords(text, set(net_manager.nodenames))
        if not hits:
            return ""

        memories = net_manager.trigger_by_keywords(hits)
        if not memories:
            return ""

        lines = ["你听到这句话，忽然想起了这些（越靠前记得越清楚）："]
        for memory in memories[:RECALL_MAX_MEMORIES]:
            lines.append(f"  · {memory}")
        return "\n".join(lines)
    except Exception as e:
        # 回忆失败不该拦住这次回复 —— 大不了这次不想起什么
        logger.warning(f"记忆激活失败,这次不回忆: {e}")
        return ""


def _opening_messages() -> list[ChatCompletionMessageParam]:
    """
    开局的消息

    历史是拼成**一条** user 消息、而不是还原成多条对话:
        generate_history_dialog 给的是一段整理好的文本,
        硬拆成 messages 反而要猜哪句是谁说的。拼成一段背景,
        信息量一样,还不会把话安到错的人头上。
    """
    blocks: list[str] = []
    who = state.sender_name or "对方"

    # 先报身份:不说的话它会去查 get_friend_profile,却不知道 name 该填什么
    blocks.append(f"正在跟你说话的人：{who}")

    relation = describe_friend(state.friend)
    if relation:
        blocks.append(relation)

    history = _load_history(state.chat_stream)
    if history.strip():
        blocks.append(f"我们之前聊过这些：\n{history.strip()}")

    blocks.append(f"{who}刚说：\n{state.input_text.strip()}")

    # 记忆在这里"被动激活":听到词 → 命中节点 → 向外扩散
    recall = _recall_block(state.input_text)
    if recall:
        blocks.append(recall)

    emotions = _emotion_block()
    if emotions:
        blocks.append(emotions)

    blocks.append(_state_line())

    # 用 SDK 自带的 TypedDict 构造,不用裸 dict:
    return [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
        ChatCompletionUserMessageParam(role="user", content="\n\n".join(blocks)),
    ]


def _parse_arguments(raw: str) -> dict[str, Any]:
    """
    模型给的参数是**字符串**,形如 '{"name":"小明"}',不是 dict

    解析失败就当空参交给工具 —— 让工具自己报"缺参数",
    比在这里抛异常好:最终看到的报错更贴近它实际做的那件事。
    """
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"工具参数不是合法 JSON,按空参处理: {raw[:120]}")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _assistant_message(result: Any) -> ChatCompletionAssistantMessageParam:
    """
    把模型这一圈的输出原样转成历史里的 assistant 消息

    必须**原样**带上 tool_calls:
        OpenAI 协议要求 assistant 的每个 tool_call 后面都跟一条对应的
        tool 消息,少一条服务端就返 400,而且报错信息不会指向这里。
    """
    return ChatCompletionAssistantMessageParam(
        role="assistant",
        content=result.text or None,        # 只调工具时 content 就是 None
        tool_calls=[
            ChatCompletionMessageToolCallParam(
                id=tc.id,
                type="function",
                function={
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            )
            for tc in result.tool_calls
        ],
    )


def _tool_message(
    tool_call: Any, outcome: dict[str, Any]
) -> ChatCompletionToolMessageParam:
    """工具的观察结果。tool_call_id 是配对用的,不能省"""
    return ChatCompletionToolMessageParam(
        role="tool",
        tool_call_id=tool_call.id,
        content=json.dumps(outcome, ensure_ascii=False, default=str),
    )


def think(response: Any = None, trace: str | None = None):
    """
    思考循环

    返回 state,调用方看 status:
        completed      想完了,final_answer 里有要说的话
        silent         主动选择不说话,silent_reason 里有理由
        failed         调用失败,error 里有原因
        max_iterations 圈数用尽(已经拿最后说出口的话兜过底)
    """
    if not global_control.want_thinking:
        return None

    # 没给就自己生成一个:整条思考链(好几圈)必须共用一个,
    # 否则日志里每次调用各是一个 trace,串不成一条
    if trace is None:
        trace = uuid.uuid4().hex[:6]

    tools_init()
    schemas = agent_tool_schemas()

    state.reset(response)

    # 关系信息查一次就好,思考层和回复层共用
    state.friend = get_friend(state.sender_name) if state.sender_name else None

    messages: list[ChatCompletionMessageParam] = _opening_messages()

    while state.iteration < state.max_iterations:
        state.iteration += 1

        result = call(
            messages=messages,
            profile="think",
            shape=SHAPE_TOOLS,
            tools=schemas,
            trace=trace,        # 整条链路共用一个,日志里能串成一条
        )

        if not result.ok:
            state.status = "failed"
            state.error = result.error
            break

        # ── 第一层:自然语言的想法 ──
        if result.reasoning:
            logger.debug("第{}圈独白: {}", state.iteration, result.reasoning)
        if result.text:
            logger.debug("第{}圈脱口而出: {}", state.iteration, result.text)

        step = ThoughtStep(
            iteration=state.iteration,
            reasoning=result.reasoning,
            utterance=result.text,
        )
        state.steps.append(step)

        # ── 没有再要求工具 = 想完了 ──
        if not result.tool_calls:
            state.final_answer = result.text
            state.status = "completed"
            break

        # ── 第二层:结构化决定。先把这一圈写回历史,再执行 ──
        messages.append(_assistant_message(result))

        for tool_call in result.tool_calls:
            name = tool_call.function.name
            arguments = _parse_arguments(tool_call.function.arguments)

            # 沉默是"表态",不是"查询":表态完就收工,不必再想下一圈
            if name == "stay_silent":
                step.calls.append(
                    ToolCallRecord(name=name, arguments=arguments,
                                   result={"silent": True}, ok=True)
                )
                state.status = "silent"
                state.silent_reason = str(arguments.get("reason", ""))
                logger.info("选择不说话: {}", state.silent_reason or "(没给理由)")
                return state

            outcome = execute_tool(name, arguments)
            logger.debug("工具 {} 参数 {} → {}", name, arguments, outcome)

            messages.append(_tool_message(tool_call, outcome))
            step.calls.append(
                ToolCallRecord(
                    name=name,
                    arguments=arguments,
                    result=(outcome.get("result") if outcome.get("success")
                            else outcome.get("error")),
                    ok=bool(outcome.get("success")),
                )
            )

    else:
        # while 是"正常跑完"的(一次都没 break)= 圈数用尽
        state.status = "max_iterations"
        logger.warning("思考圈数用尽({} 圈),拿最后说出口的话兜底", state.max_iterations)
        state.final_answer = state.last_utterance

    # 圈数用尽,而且一句话都没说出口 —— 这才是真没辙了
    if state.status == "max_iterations" and not state.final_answer:
        state.status = "failed"
        state.error = "思考圈数用尽,而且一句话都没说出口"

    return state


if __name__ == "__main__":
    # 简易自测:python -m src.agent.think
    class _FakeResponse:
        chat_stream = None

        @staticmethod
        def get_strings() -> str:
            return "现在几点了？"

    finished = think(_FakeResponse())
    if finished is None:
        print("思考层被关闭(want_thinking=False)")
        raise SystemExit(0)

    print("status      =", finished.status)
    print("final_answer=", finished.final_answer)
    print("silent      =", finished.silent_reason)
    print("error       =", finished.error)
    for s in finished.steps:
        print(f"  [第{s.iteration}圈] 独白={s.reasoning[:60]!r} 前言={s.utterance!r}")
        for c in s.calls:
            print(f"      工具 {c.name}({c.arguments}) ok={c.ok} -> {str(c.result)[:80]}")
