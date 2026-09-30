from src.LLM.llm_manager import chat_stream
from src.LLM.prompt import create_prompt
from src.mongodb import *
from src.split import text_split
from src.emood.mood import moodupdater
from src.emood.tired import tiredupdater
from src.msgbase import Response, FriendMsg
from src.globalcontrol import global_control
from src.config import *
from src.messagebuffer import message_buffer
import uuid

from src.agent.think import think
from src.agent.reply import compose_reply
from flask_socketio import SocketIO
from src.state_loop import describe_eagerness, state_snapshot

socketio = None
def set_socketio(sio: SocketIO):
    global socketio
    socketio = sio


if global_control.speak:
    from src.plugins.ProcessAudio.readaudio import global_speaker

from src.logger import get_module_logger
logger = get_module_logger('api')


def msg_process(response:Response):
    
    # 得到随机的编码，让一条消息在多轮思考中有个统一的标识
    trace = uuid.uuid4().hex[:6]

    # 更新心情值和兴趣值,分析情感,对各个人的感觉记录在emotion_manager.response_contents里,
    moodupdater.update_in_msgloop(response)

    # 更新疲惫值:消息太密集就让发言意愿打折
    tiredupdater.update_in_msgloop(response)

    # 一次拿齐全状态:拿锁口径统一,以后 eagerness 的定义变了这里也不用动
    snap = state_snapshot()
    logger.info(
        f"意愿 {snap['eagerness']:.3f}（{describe_eagerness(snap['eagerness'])}）"
        f" —— 只作为参考交给思考层,回不回由它自己判断"
    )

    agent_state = think(response, trace=trace)

    if agent_state is None:
        logger.warning("思考层被关闭(want_thinking=False)，跳过发送")
        return

    # 主动选择不说话是一个正常结局,不是失败
    if agent_state.status == "silent":
        logger.info("这次不说话: {}", agent_state.silent_reason or "(没给理由)")
        return

    if agent_state.status != "completed":
        logger.warning(
            "思考未完成({})，跳过发送: {}",
            agent_state.status, agent_state.error or "(没有错误信息)",
        )
        return

    # 思考层给的是"心里想表达的意思"。这里过一遍说话层,
    # 连同整条思考链一起交给它,说成人话(失败会自动退回思考层的原话)。
    reply_text = compose_reply(agent_state, trace=trace)
    if not reply_text.strip():
        logger.warning("说话层给了一句空话，跳过发送")
        return

    response.alter_response(reply_text)
    db_add(response)

    response_split = [response.content]
    if global_control.split:

        response_split = text_split(response_split[0])
    if global_control.speak:
        global_speaker.speak(response)

    if socketio is None:
        logger.error("SocketIO 未初始化，无法发送消息")
        return
    for res in response_split:
        socketio.emit('message', res)


message_buffer.set_handler(msg_process)


if __name__ == '__main__':
    content=chat_stream("你好")
    print(content)