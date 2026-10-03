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

from src.agent.state import ToolCallRecord, ThoughtStep, current_state
from src.agent.tasks import TASK_SENDER
from src.agent.tools import agent_tool_schemas, execute_tool, tool_work_cost, tools_init
from src.config import RECALL_MAX_MEMORIES, THINK_HISTORY_LIMIT, WORK_COST_ROUND
from src.emood.tired import tiredupdater
from src.globalcontrol import global_control
from src.LLM.client import SHAPE_TOOLS, call
from src.mongodb import get_friend
from src.state_loop import (
    describe_boredom,
    describe_eagerness,
    describe_fatigue,
    describe_friend,
    human_duration,
    state_snapshot,
)

from src.logger import LogConfig, get_module_logger

logger = get_module_logger(
    "agent-think",
    LogConfig(console_level="INFO", file_level="DEBUG"),
)


# 人格和任务分开放:人格两种场合共用,任务随场合换
# 原先一份提示词硬套两种场合,自发模式下会看到"对方刚给你发了消息"却没消息,
# 于是它转而去"解读这份提示词"—— 出戏,而且一切回分析姿态独白就变英文
_PERSONA = """你是小贴。
小贴是你自己，不是正在跟你说话的人。

你的性格：孩子气，好奇心重，想到什么就说什么。
跟熟人会放松、会撒娇，跟生人有点腼腆。

---
思考独白必须全程使用中文，就像在心里自言自语，别写成分析报告，也不要用英文分析句式。
不要说“用户”“该消息”“进行回复”这种词 —— 你是在跟一个人讲话。
别把“现在几点”当成一句话说出来 —— 时间只有跟具体的事绑在一起才有意义
（比如“这么晚了还不睡”），单纯报数不像人说话。
"""

_REPLY_TASK = """对方刚给你发了消息。
你可以调用工具去了解情况，也可以什么都不查直接回。
决定之前先想清楚你到底要找什么，别为了查而查。
查得差不多了就直接说，不用等把每件事都弄清楚 ——
觉得累了、不想再折腾了，就拿手里已经有的东西回。
如果你觉得这条消息没必要接，就调用 stay_silent。
"""

_IDLE_TASK = """现在没有人在跟你说话，你自己待着，想干点什么就干点什么。
你可以用 run_command 看看这台电脑上有什么，
也可以在自己的工作区里捣鼓点东西 —— 写写笔记、试试小脚本、整理资料，
或者攒一个自己的小工具，下回还接着用。
也可以想到什么就去跟人说 —— 不用等人问你。
要是实在没什么想干的，就用 stay_silent 继续待着。
"""


def _system_prompt() -> str:
    """按场合挑任务段;人格段共用"""
    task = _IDLE_TASK if current_state().is_idle else _REPLY_TASK
    return f"{_PERSONA}\n{task}"

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
        f"兴趣 {snap['interest_value']:.2f}，"
        f"疲惫 {snap['fatigue']:.2f}（{describe_fatigue(snap['fatigue'])}）。\n"
        f"发言意愿 {snap['eagerness']:.2f}（{describe_eagerness(snap['eagerness'])}）。\n"
        f"这只是参考 —— 如果你发现了值得说的东西，可以不管它。"
    )


def _emotion_block() -> str:
    """对方和这段对话当下的情绪"""
    from src.emood.emotion import emotion_report

    return emotion_report(current_state().sender_name)


def _recall_block(text: str) -> str:
    """从对方的话里激活记忆网络,返回唤起的记忆;没命中就返回空串"""
    try:
        from src.memory.memory import hit_keywords
        from src.memory.structure import net_manager

        hits = hit_keywords(text, set(net_manager.nodenames))

        # 跟当前说话人有关的记忆总会想起来;补在最后,不抢文本命中话题的位置
        sender = current_state().sender_name
        if sender and sender in net_manager.nodenames and sender not in hits:
            hits.append(sender)

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


def _idle_prompt() -> str:
    """自发时的处境:没人找她,她自己待着(能干什么写在 system 里了)"""
    st = current_state()
    snap = state_snapshot()

    lines = [
        f"你已经 {human_duration(snap['delta_idle'])} 没跟人说过话了。",
        f"{describe_boredom(snap['boredom'])}。",
    ]
    if st.sender_name:
        lines.append(f"想说话的话，能找的人是：{st.sender_name}")
    return "\n".join(lines)


def _opening_messages() -> list[ChatCompletionMessageParam]:
    """
    开局的消息

    历史是拼成**一条** user 消息、而不是还原成多条对话:
        generate_history_dialog 给的是一段整理好的文本,
        硬拆成 messages 反而要猜哪句是谁说的。拼成一段背景,
        信息量一样,还不会把话安到错的人头上。
    """
    st = current_state()
    blocks: list[str] = []

    history = _load_history(st.chat_stream)
    if history.strip():
        blocks.append(f"我们之前聊过这些：\n{history.strip()}")

    if st.is_idle:
        # 自发:没人跟我说话,我自己待着
        blocks.append(_idle_prompt())
    elif st.sender_name == TASK_SENDER:
        # 后台任务的结果回来了 —— 这不是"某人说的话"
        blocks.append("你先前派出去的后台任务有结果了：")
        blocks.append(st.input_text.strip())
    else:
        who = st.sender_name or "对方"
        # 先报身份:不说的话它会去查 get_friend_profile,却不知道 name 该填什么
        blocks.append(f"正在跟你说话的人：{who}")

        relation = describe_friend(st.friend)
        if relation:
            blocks.append(relation)

        blocks.append(f"{who}刚说：\n{st.input_text.strip()}")

    # 记忆在这里"被动激活":听到词 → 命中节点 → 向外扩散
    recall = _recall_block(st.input_text)
    if recall:
        blocks.append(recall)

    emotions = _emotion_block()
    if emotions:
        blocks.append(emotions)

    blocks.append(_state_line())

    # 用 SDK 自带的 TypedDict 构造,不用裸 dict:
    return [
        ChatCompletionSystemMessageParam(role="system", content=_system_prompt()),
        ChatCompletionUserMessageParam(role="user", content="\n\n".join(blocks)),
    ]


def _round_note(rounds: int) -> ChatCompletionSystemMessageParam:
    """
    循环里每圈追一句状态

    开场那条状态行只在第一圈前拼一次,不追的话她查了一路都不知道自己在累。
    用 system 而不是 user —— user 会被当成"对面又说话了",自发模式下直接矛盾。
    """
    fatigue = state_snapshot()["fatigue"]
    return ChatCompletionSystemMessageParam(
        role="system",
        content=f"（你已经连着查了 {rounds} 轮。{describe_fatigue(fatigue)}。）",
    )


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


def _short_text(value: Any, limit: int = 900) -> str:
    """把一项工具结果压成适合继续思考的短文本"""
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def _rolling_context(st: Any) -> str:
    """根据已完成的轮次生成下一轮唯一需要的上下文"""
    lines = [
        "这是同一件事的连续思考。下面是截至目前的压缩记录，必须结合全部记录继续判断。",
        f"正在和你说话的人：{st.sender_name or '没有指定对象'}。",
    ]
    if st.is_idle:
        lines.append("这是一次自发思考，不要把内部记录原样发给对方。")
    elif st.input_text.strip():
        lines.append(f"原始消息：{st.input_text.strip()}")

    for step in st.steps:
        parts = [f"第{step.iteration}轮"]
        if step.utterance:
            parts.append(f"当时的判断：{_short_text(step.utterance, 500)}")
        for call in step.calls:
            result = "成功" if call.ok else "失败"
            parts.append(
                f"工具 {call.name}({ _short_text(call.arguments, 240) }) {result}"
            )
        lines.append("；".join(parts))

    lines.append("请在这份记录上继续思考；如果调用工具，本轮结束后会把新结果合并进下一份记录。")
    context = "\n".join(lines)
    if len(context) <= 9000:
        return context
    return context[:1800] + "\n……较早记录已压缩……\n" + context[-7000:]


def _next_round_messages(st: Any, system_message: ChatCompletionMessageParam) -> list[ChatCompletionMessageParam]:
    """丢弃旧的工具协议历史,只把已完成轮次的摘要交给下一轮"""
    return [
        system_message,
        ChatCompletionUserMessageParam(role="user", content=_rolling_context(st)),
    ]


def think(
    response: Any = None,
    trace: str | None = None,
    idle: bool = False,
    target: dict | None = None,
):
    """
    思考循环

    返回 state,调用方看 status:
        completed      想完了,final_answer 里有要说的话
        silent         主动选择不说话,silent_reason 里有理由
        failed         调用失败,error 里有原因
        max_iterations 圈数用尽(已经拿最后说出口的话兜过底)

    idle=True 是自发模式:没人找我,我自己待着。
    target 是这时候挑中的说话对象(一条 db_friend 记录)。
    """
    if not global_control.want_thinking:
        return None

    # 没给就自己生成一个:整条思考链(好几圈)必须共用一个,
    # 否则日志里每次调用各是一个 trace,串不成一条
    if trace is None:
        trace = uuid.uuid4().hex[:6]

    tools_init()
    schemas = agent_tool_schemas()

    st = current_state()
    st.reset(response)
    st.is_idle = idle

    if idle and target:
        # 自发:没人跟我说话,但我挑了个人想找他
        st.sender_name = target.get("name") or ""
        st.chat_stream = target.get("chat_stream") or None
        st.friend = target

    # 后台结果不是"人",跳过关系查询和人物节点注册
    if st.sender_name and st.sender_name != TASK_SENDER and not st.is_idle:
        st.friend = get_friend(st.sender_name)

        from src.memory.structure import net_manager

        net_manager.register_person(st.sender_name)

    messages: list[ChatCompletionMessageParam] = _opening_messages()
    system_message = messages[0]

    while st.iteration < st.max_iterations:
        st.iteration += 1

        result = call(
            messages=messages,
            profile="think",
            shape=SHAPE_TOOLS,
            tools=schemas,
            trace=trace,        # 整条链路共用一个,日志里能串成一条
        )

        if not result.ok:
            st.status = "failed"
            st.error = result.error
            break

        tiredupdater.add_workload(WORK_COST_ROUND, f"第{st.iteration}圈思考")

        # ── 第一层:自然语言的想法 ──
        if result.reasoning:
            logger.debug("第{}圈独白: {}", st.iteration, result.reasoning)
        if result.text:
            logger.debug("第{}圈脱口而出: {}", st.iteration, result.text)

        step = ThoughtStep(
            iteration=st.iteration,
            reasoning=result.reasoning,
            utterance=result.text,
        )
        st.steps.append(step)

        # ── 没有再要求工具 = 想完了 ──
        if not result.tool_calls:
            st.final_answer = result.text
            st.status = "completed"
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
                st.status = "silent"
                st.silent_reason = str(arguments.get("reason", ""))
                logger.info("选择不说话: {}", st.silent_reason or "(没给理由)")
                return st

            outcome = execute_tool(name, arguments)
            tiredupdater.add_workload(tool_work_cost(name), name)
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

        messages = _next_round_messages(st, system_message)

    else:
        # while 是"正常跑完"的(一次都没 break)= 圈数用尽
        st.status = "max_iterations"
        logger.warning("思考圈数用尽({} 圈),拿最后说出口的话兜底", st.max_iterations)
        st.final_answer = st.last_utterance

    # 圈数用尽,而且一句话都没说出口 —— 这才是真没辙了
    if st.status == "max_iterations" and not st.final_answer:
        st.status = "failed"
        st.error = "思考圈数用尽,而且一句话都没说出口"

    return st


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
