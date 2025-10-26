from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from api import msg_process
from mongodb import *
import time
import threading
from config import *
from msgbase import Msgbase
from logger import get_module_logger
from mood import moodupdater
import os


logger = get_module_logger("app")

app = Flask(__name__)
CORS(app)   # 允许跨域请求

# 初始化SocketIO
# 初始化 SocketIO，允许跨域
socketio = SocketIO(app,
                   cors_allowed_origins="*",
                   logger=True,
                   engineio_logger=False)

# 存储连接的客户端（可选）
connected_clients = {}


def mood_update_loop():
    """时间间隔更新心情"""
    n=0

    while True:
        n=n+1
        moodupdater.update_in_timeloop()

        if n > 1:
            logger.info(f"心情: {moodupdater.mood_value}   兴趣: {moodupdater.interest_value}")
            n=0
        time.sleep(5)

def start_mood_thread():
    """启动心情更新线程"""

    thread = threading.Thread(target=mood_update_loop)
    thread.daemon = True  # 设置为守护线程，这样主程序退出时该线程也会退出
    thread.start()

# WebSocket 事件处理
@socketio.on('connect')
def handle_connect():
    """客户端连接事件"""
    client_id = request.sid
    connected_clients[client_id] = {
        'connect_time': datetime.now(),
        'ip': request.remote_addr
    }
    logger.info(f"客户端连接: {client_id}")
    emit('connected', {
        'message': '连接成功',
        'client_id': client_id,
        'timestamp': datetime.now().isoformat()
    })

    start_mood_thread()

@socketio.on('message')
def handle_message(data):
    logger.info(f'收到消息:{data}')

    # 处理消息
    responses = msg_process(data)

    logger.info(f"发送消息:{responses}")
    # 主动发送回复
    for response in responses:
        emit('message', response, broadcast=False)

@app.route('/')
def index():
    return "WebSocket Server is Running!"


if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or os.environ.get('WERKZEUG_RUN_MAIN') is None:
        start_mood_thread()
    socketio.run(app, debug=True, host='0.0.0.0', port=8001)
