"""
出口

从"想完了"到"发出去了"的这一段,两条入口共用:
    消息触发的   api.msg_process
    自发的       idle.idle_tick

socketio 仍旧靠注入 —— 谁创建服务器谁告诉这里。
"""
from typing import Any

from src.agent.reply import compose_reply
from src.agent.state import AgentState
from src.globalcontrol import global_control
from src.mongodb import db_add
from src.msgbase import Response
from src.split import text_split

from src.logger import get_module_logger

logger = get_module_logger("deliver")

_socketio: Any = None


def set_socketio(sio: Any) -> None:
    global _socketio
    _socketio = sio


if global_control.speak:
    from src.plugins.ProcessAudio.readaudio import global_speaker


def who_said(response: Response) -> str:
    """这条回复是冲着谁说的,只给日志用"""
    names = [msg.name for msg in getattr(response, "Msgs", None) or []]
    return "/".join(dict.fromkeys(names)) or "?"


def deliver(state: AgentState | None, response: Response,
            trace: str | None = None) -> bool:
    """
    判结局 → 说成人话 → 发出去。两条入口唯一的收尾。

    规则只在这里写一遍:除了她主动沉默,只要还有话说就该发出去。
    圈数用尽时 think 已经把最后说出口的话放进 final_answer 了,
    不能因为 status 不是 completed 就扔。

    返回是否真的发出去了(给日志和测试看)。
    """
    if state is None:
        logger.warning("思考层被关闭(want_thinking=False)，跳过发送")
        return False

    # 主动选择不说话是一个正常结局,不是失败
    if state.status == "silent":
        logger.info("这次不说话: {}", state.silent_reason or "(没给理由)")
        return False

    if state.status != "completed":
        report = logger.error if state.status == "failed" else logger.warning
        report("思考未完成({}) trace={} 来自 {}: {}",
               state.status, trace, who_said(response),
               state.error or "(没有错误信息)")

    if not (state.final_answer or "").strip():
        # 真没辙了就不回。不要给她编一句"我出错了"去盖住故障 ——
        # 那比沉默更出戏,而且会让下次排查更晚发现
        return False

    # 思考层给的是"心里想表达的意思"。这里过一遍说话层,
    # 连同整条思考链一起交给它,说成人话(失败会自动退回思考层的原话)。
    reply_text = compose_reply(state, trace=trace)
    if not reply_text.strip():
        logger.warning("说话层给了一句空话，跳过发送")
        return False

    response.alter_response(reply_text)
    return send_reply(response)


def send_reply(response: Response) -> bool:
    """存库、切分、朗读、发出去 —— 所有回复都走这里(消息触发的和自发的)"""
    if not (response.content or "").strip():
        logger.warning("内容是空的，跳过发送")
        return False

    # 存库、朗读都只是附加动作:任何一个坏了都不该连文字一起吞
    try:
        db_add(response)
    except Exception as e:
        logger.exception(f"回复存库失败(她会不记得自己说过这句): {e}")

    parts = [response.content]
    if global_control.split:
        parts = text_split(response.content)

    if _socketio is None:
        logger.error("SocketIO 未初始化，无法发送消息")
        return False

    for piece in parts:
        _socketio.emit('message', piece)

    # 朗读放在文字之后:喇叭出问题不该把文字也堵住
    if global_control.speak:
        try:
            global_speaker.speak(response)
        except Exception as e:
            logger.exception(f"朗读失败(文字已经发出去了): {e}")

    return True
