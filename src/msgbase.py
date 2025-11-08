from datetime import datetime
import time
import threading
from src.config import *
from typing import Dict, Optional
from collections import deque
import hashlib
from src.observer import msg_subject,time_obsever
from abc import ABC, abstractmethod
import sys
import io
import json
from src.logger import get_module_logger
from dataclasses import dataclass, field


def string_to_hash(text, algorithm='md5'):
    """字符串转哈希"""
    hash_func = getattr(hashlib, algorithm)()
    hash_func.update(text.encode('utf-8'))
    return hash_func.hexdigest()


class Msgbase:
    def __init__(self, msg: Optional[Dict],name,content):
        """消息基础类

        能够自动创建的参数：
        timestamp: float, 消息时间戳
        time: str, 消息时间字符串
        chat_plat: str, 聊天平台，通过CHAT_PLAT修改
        可选参数：
        group_name: str, 群组名称,若没有群组名称，则默认为“电脑本地”
        chat_stream: str, 聊天流标识符，若没有则根据group_name生成

        """
        msg = self.host_msg_complete(msg)
        self.name:str
        self.content:str
        self.chat_stream = msg['chat_stream']
        self.group_name = msg['group_name']
        self.timestamp = time.time()
        self.time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.chat_plat = CHAT_PLAT
        self.value = {
            "name": name,
            "content": content,
            "timestamp": self.timestamp,
            "time": self.time,
            "chat_stream": self.chat_stream,
            'chat_plat': self.chat_plat,
            'group_name': self.group_name,
        }
        msg_subject.notify_observers(self)

    def host_msg_complete(self, msg: Optional[Dict]):
        if "group_name" not in msg.keys():
            msg['group_name'] = "电脑本地"
        if "chat_stream" not in msg.keys():
            msg['chat_stream'] = string_to_hash(msg['group_name'])
        return msg


class FriendMsg(Msgbase):
    """
    好友的消息类

    创建时必须要有的参数：
    name: str, 发送者名称
    content: str, 消息内容
    """
    def __init__(self, msg: Optional[Dict]):
        """这里msg是接收的json转字典"""
        self.name = msg['name']
        self.content = msg['content']
        super().__init__(msg, self.name, self.content)


class Response(Msgbase):
    """机器人的回复消息类"""
    def __init__(self, msg: Msgbase, response=""):
        """
        msg参数，是朋友的消息，用于标定要回复哪一条消息

        通过msg得到聊天流chat_stream和群组group_name，其余均自动生成，但是response需要再次获取

        先进行消息缓冲，对于部分内容进行回复时，将那些消息整合为一个消息类，再根据存储的消息类生成回复内容，
        也就是在接收消息时就生成回复类，根据buffer决断self.Msgs = []里面有多少消息，然后进行回复
        """
        self.content = response
        self.name = BOT_NAME
        self.Msgs = []
        self.Msgs.append(msg)
        resmsg = {
            "name": self.name,
            "content": self.content,
        }
        # 这里保证回复消息能够与原消息在同一聊天流和群组中
        msgvalue = msg.value
        if "group_name" in msgvalue.keys():
            resmsg['group_name'] = msgvalue['group_name']
        if "chat_stream" in msgvalue.keys():
            resmsg['chat_stream'] = string_to_hash(msgvalue['group_name'])
        super().__init__(resmsg, self.name, self.content)

    def alter_response(self,response:str):
        """修改回复内容"""
        self.response = response
        self.value['content'] = self.response




if __name__ == '__main__':
    m1 = Msgbase({
        "name":1,
        "content":2,
    })
    m2 = Msgbase({
        "name": 1,
        "content": 2,
    })
    m3 = Msgbase({
        "name": 1,
        "content": 2,
    })
    print(time_obsever.get_timelist())