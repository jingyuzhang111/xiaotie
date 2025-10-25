from datetime import datetime
from config import *
from typing import Dict, Optional
import hashlib
import sys
import io
import json
from logger import get_module_logger


class Msgbase:
    def __init__(self, msg: Optional[Dict]):
        msg = self.host_msg_complete(msg)
        self.name = msg['name']
        self.content = msg['content']
        self.chat_stream = msg['chat_stream']
        self.group_name = msg['group_name']
        self.timestamp = int(datetime.now().timestamp())
        self.time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.chat_plat = CHAT_PLAT
        self.value = {
            "name": self.name,
            "content": self.content,
            "timestamp": self.timestamp,
            "time": self.time,
            "chat_stream": self.chat_stream,
            'chat_plat': self.chat_plat,
            'group_name': self.group_name,
        }

    @staticmethod
    def string_to_hash(text, algorithm='md5'):
        """字符串转哈希"""
        hash_func = getattr(hashlib, algorithm)()
        hash_func.update(text.encode('utf-8'))
        return hash_func.hexdigest()

    def host_msg_complete(self, msg: Optional[Dict]):
        if "group_name" not in msg.keys():
            msg['group_name'] = "电脑本地"
        if "chat_stream" not in msg.keys():
            msg['chat_stream'] = self.string_to_hash(msg['group_name'])
        return msg


class ResPonse(Msgbase):
    def __init__(self, msg: Optional[Dict], response):
        super().__init__(msg)
        self.response = response
        self.Msg = Msgbase(msg)
