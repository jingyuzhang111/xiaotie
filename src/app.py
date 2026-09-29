from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# from mongostart import *
# _mongod_process = start_mongod()

from src.mongodb import *
import time
import threading
from datetime import datetime
from src.logger import get_module_logger
from src.emood.mood import moodupdater
from src.memory.structure import net_manager
import os
from src.thread.threadmanager import thread_manager
from src.messagebuffer import message_buffer
from src.agent.tools import _TOOL_REGISTRY, tools_init

logger = get_module_logger("app")

app = Flask(__name__)
CORS(app)   # 允许跨域请求

# 初始化SocketIO
# 初始化 SocketIO，允许跨域
socketio = SocketIO(app,
                   cors_allowed_origins="*",
                   logger=False,
                   engineio_logger=False)

# 存储连接的客户端（可选）
connected_clients = {}

# WebSocket 事件处理
@socketio.on('connect')
def handle_connect(auth=None):
    """客户端连接事件"""
    logger.info("正在连接小贴大脑......")
    client_id = request.sid # type: ignore
    connected_clients[client_id] = {
        'connect_time': datetime.now(),
        'ip': request.remote_addr
    }
    logger.info(f"客户端连接: {client_id}, ip={request.remote_addr}")
    emit('connected', {
        'message': '连接成功',
        'client_id': client_id,
        'timestamp': datetime.now().isoformat()
    })

@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid # type: ignore
    connected_clients.pop(client_id, None)
    logger.info(f"客户端断开: {client_id}")

@socketio.on('message')
def handle_message(data):
    logger.debug(f'收到消息:{data}')

    # 接收消息，转为消息类
    fri_msg = FriendMsg(data)

    db_add(fri_msg) # 存入数据库

    # 消息送入缓冲池
    message_buffer.add_message_start_loop(fri_msg)

    # 检查各个线程的状态, 防止部分线程假死智斗
    thread_manager.check_in_handle_message()



@app.route('/')
def index():
    return "WebSocket Server is Running!"


def start_threads():
    """启动所有线程"""
    thread_manager.add_tasks(net_manager.memory_process, interval_sec=300)
    thread_manager.add_tasks(moodupdater.update_in_timeloop, interval_sec=2)
    thread_manager.start()

def restart_threads():
    """重启所有线程"""
    if thread_manager.is_alive():
        thread_manager.restart()


def run_app():

    tools_init()

    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or os.environ.get('WERKZEUG_RUN_MAIN') is None:
        start_threads()
        restart_threads()
        print(thread_manager.get_all_infos())
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, use_reloader=False, log_output=False, allow_unsafe_werkzeug=True)
    

    


logger.info("小贴Flask服务器启动中...")
if __name__ == '__main__':
    run_app()