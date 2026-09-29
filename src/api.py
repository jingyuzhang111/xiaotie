from src.LLM.llm_manager import chat_stream
from src.LLM.prompt import create_prompt
from src.mongodb import *
from src.split import text_split
from src.emood.mood import moodupdater
from src.msgbase import Response, FriendMsg
from src.globalcontrol import global_control
from src.config import *
from src.messagebuffer import message_buffer
from src.agent.loop import main_loop
from flask_socketio import SocketIO

socketio = None
def set_socketio(sio: SocketIO):
    global socketio
    socketio = sio


if global_control.speak:
    from src.plugins.ProcessAudio.readaudio import global_speaker

from src.logger import get_module_logger
logger = get_module_logger('api')


def msg_process(response:Response):
    
    # 更新心情值和兴趣值,分析情感,对各个人的感觉记录在emotion_manager.response_contents里,
    moodupdater.update_in_msgloop(response)

    agent_state = main_loop(response)
    if agent_state is None or agent_state.status != "completed":
        logger.warning("Agent未完成回复，状态: {}", agent_state.status if agent_state else "disabled")
        logger.warning("生成回复失败，跳过发送")
        return

    response.alter_response(agent_state.final_answer or "")
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