"""
回复层(说话层)

为什么要单独一层:
    Agent 决策器(desition)的 system prompt 是"你是一个Agent决策器,只输出JSON"。
    它产出的是**格式服从**,不是人话 —— 把它的 final_answer.content 直接发给用户,
    就是"人机感"的根源。

    这一层专门负责"说话":走 chat_text(不带 JSON、不带工具),把决策过程的结果
    翻译成自然的回复。

    好处是决策层可以继续严格、可解析,说话层可以放开写。
    两个任务性质不同,硬塞进同一个 prompt 会互相拖累。

失败时退回决策器给的原话 —— 说话层出问题不该让人收不到消息。
"""
import json

from src.agent.state import AgentState
from src.LLM.client import call, SHAPE_TEXT
from src.config import *
from src.state_loop import describe_friend, describe_mood, state_snapshot
from src.logger import get_module_logger

logger = get_module_logger("agent-reply")


# 人格写在前面,禁令用分隔线隔开放后面。
SYSTEM_PROMPT = """你是小贴。

你的性格：孩子气，好奇心重，想到什么就说什么。
跟熟人会放松、会撒娇，跟生人有点腼腆。

你说话的方式：短句。不用括号补充说明，不用 emoji 和颜文字。偶尔嘴硬，但心是软的。

---
下面给你的是内部记录，只作背景参考。
不要复述它们，不要提到它们的存在。
像平时聊天那样，自然地回一句。
"""


def _load_history(chat_stream: str | None) -> str:
    """
    取最近的对话历史。取不到就返回空串 —— 没有历史也要能说话。
    """
    if not chat_stream:
        return ""
    try:
        from src.memory.memory import memory_manager

        return memory_manager.generate_history_dialog(
            chat_stream=chat_stream, limit=REPLY_HISTORY_LIMIT,
        )
    except Exception as e:
        logger.warning(f"读取历史失败,这次不带历史说话: {e}")
        return "回忆失败了，呜呜呜。"


def _mood_line() -> str:
    """当前心情,给说话定语气"""
    mood_value = state_snapshot()["mood_value"]
    return f"你现在的心情：{describe_mood(mood_value)}"


def _emotion_block(sender: str) -> str:
    """对方和这段对话当下的情绪"""
    from src.emood.emotion import emotion_report

    return emotion_report(sender)


def render_thoughts(state: AgentState) -> str:
    """
    给回复层保留操作结果,不传完整内心独白
    """
    if not state.steps:
        return ""

    lines = ["这次已经完成的操作："]
    for step in state.steps:
        for tool_call in step.calls:
            args = json.dumps(tool_call.arguments, ensure_ascii=False)
            shown = "" if tool_call.result is None else str(tool_call.result).strip()
            shown = " ".join(shown.split())
            if len(shown) > 700:
                shown = shown[:700] + "..."
            if not tool_call.ok:
                lines.append(f"第{step.iteration}轮，{tool_call.name}({args})失败：{shown}")
            elif not shown:
                lines.append(f"第{step.iteration}轮，{tool_call.name}({args})返回空结果")
            else:
                lines.append(f"第{step.iteration}轮，{tool_call.name}({args})结果：{shown}")
    return "\n".join(lines)


def build_reply_prompt(state: AgentState, history: str = "") -> tuple[str, str]:
    """把"决策过程留下的东西"整理成说话层的提示词"""
    blocks = []

    relation = describe_friend(state.friend)
    if relation:
        blocks.append(relation)

    if history.strip():
        blocks.append(f"我们之前聊过这些：\n{history.strip()}")

    blocks.append(f"对方这次说：\n{state.input_text.strip()}")

    thoughts = render_thoughts(state)
    if thoughts:
        blocks.append(thoughts)

    if state.final_answer:
        blocks.append(f"你心里本来想表达的意思：\n{state.final_answer.strip()}")

    blocks.append(_mood_line())

    emotions = _emotion_block(state.sender_name)
    if emotions:
        blocks.append(emotions)

    blocks.append(
        "上面那些是你自己刚想过的，你已经知道了，"
        "所以不要复述思考过程，不要说“我查了”“我想到”这类话。\n"
        "现在说出你要说的话。只输出这句话本身。\n"
        "想分成几句发就换行，换行会变成单独发出去的一条消息；"
        "一口气说完就不要换行。"
    )
    return SYSTEM_PROMPT, "\n\n".join(blocks)


def compose_reply(
    state: AgentState,
    history: str | None = None,
    trace: str | None = None,
) -> str:
    """
    进行整个思考回复流程

    trace 沿用思考层那一个 —— 同一条消息触发的全部调用在日志里是同一条链
    """
    if not state.final_answer:
        return ""

    if history is None:
        history = _load_history(state.chat_stream)

    system_prompt, user_prompt = build_reply_prompt(state, history)
    result = call(system_prompt, user_prompt, profile="reply",
                  shape=SHAPE_TEXT, trace=trace)

    if not result.ok or not result.text.strip():
        logger.warning(f"说话层失败,退回决策器的原话: {result.error or '空回复'}")
        return state.final_answer

    return result.text.strip()
