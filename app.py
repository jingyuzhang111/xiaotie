from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from api import msg_process
from mongodb import *
from config import *
from msgbase import Msgbase
from logger import get_module_logger

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

@socketio.on('message')
def handle_message(data):
    print('收到消息:', data)

    # 处理消息
    responses = msg_process(data)
    logger.info(responses)
    # 主动发送回复
    for response in responses:
        emit('message', response, broadcast=False)


@app.route('/')
def index():
    return "WebSocket Server is Running!"

# @app.route('/api/messages', methods=['POST'])
# def test():
#     msg = request.get_json()
#     response = msg_process(msg)
#
#     # 通过WebSocket主动推送
#     socketio.emit('message', response, )
#
#     return jsonify({}), 201
"""我也不知道上面这一块注释的是干啥的"""
# @app.route('/api/messages', methods=['POST'])
# def test():
#     msg = request.get_json()
#
#     response = msg_process(msg)
#     return jsonify({}), 201
#
#
# @app.route('/api/messages', methods=['GET'])
# def sendMsg():




if __name__ == '__main__':
    app.run(debug=True)
