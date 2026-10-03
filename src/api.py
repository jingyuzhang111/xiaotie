from src.LLM.llm_manager import chat_stream
from src.LLM.prompt import create_prompt
from src.mongodb import *
from src.emood.mood import moodupdater
from src.emood.tired import tiredupdater
from src.msgbase import Response, FriendMsg
from src.config import *
from src.messagebuffer import message_buffer
import uuid
from typing import Callable

from src.agent.think import think
from src.agent.deliver import deliver, set_socketio, who_said
from src.state_loop import describe_eagerness, state_snapshot

from src.logger import get_module_logger
logger = get_module_logger('api')


def msg_process(response:Response):

    # 得到随机的编码，让一条消息在多轮思考中有个统一的标识
    trace = uuid.uuid4().hex[:6]

    # messagebuffer 那边也有一道兜底,但那句"消息处理线程发生错误"
    # 看不出是哪条消息、哪个人、停在哪一步。这一道就是给日志用的。
    try:
        _reply_once(response, trace)
    except Exception as e:
        logger.exception(f"处理消息时异常 trace={trace} 来自 {who_said(response)}: {e}")


def _safely(what: str, action: Callable[[], None]) -> None:
    """状态更新只是给提示词调色的,坏了不该拦住回复"""
    try:
        action()
    except Exception as e:
        logger.exception(f"{what}失败,这次跳过: {e}")


def _reply_once(response: Response, trace: str) -> None:
    # 更新心情值和兴趣值,分析情感,对各个人的感觉记录在emotion_manager.response_contents里,
    _safely("心情/兴趣更新", lambda: moodupdater.update_in_msgloop(response))

    # 更新疲惫值:消息太密集就让发言意愿打折
    _safely("疲惫更新", lambda: tiredupdater.update_in_msgloop(response))

    # 一次拿齐全状态:拿锁口径统一,以后 eagerness 的定义变了这里也不用动
    try:
        snap = state_snapshot()
        logger.info(
            f"意愿 {snap['eagerness']:.3f}（{describe_eagerness(snap['eagerness'])}）"
            f" —— 只作为参考交给思考层,回不回由它自己判断"
        )
    except Exception as e:
        logger.warning(f"取状态快照失败,这次不记意愿: {e}")

    # 想完之后怎么判、怎么发,和自发那条路共用一套(deliver)
    deliver(think(response, trace=trace), response, trace)


message_buffer.set_handler(msg_process)


if __name__ == '__main__':
    content=chat_stream("你好")
    print(content)