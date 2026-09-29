from datetime import datetime
import time
import threading
from src.config import *
from typing import Dict, Optional, List, Literal
from collections import deque
import hashlib
from src.observer import msg_subject,time_obsever
from abc import ABC, abstractmethod
import sys
import io
import json
from src.logger import get_module_logger
logger = get_module_logger('msgbase')
from dataclasses import dataclass, field



def string_to_hash(text, algorithm='md5'):
    """字符串转哈希"""
    hash_func = getattr(hashlib, algorithm)()
    hash_func.update(text.encode('utf-8'))
    return hash_func.hexdigest()


class Msgbase:
    """只作为基础类用来继承，不直接使用"""
    def __init__(self, msg: Optional[Dict],name="",content=""):
        """消息基础类

        能够自动创建的参数：
        timestamp: float, 消息时间戳
        time: str, 消息时间字符串
        chat_plat: str, 聊天平台，通过CHAT_PLAT修改
        可选参数：
        group_name: str, 群组名称,若没有群组名称，则默认为“电脑本地”
        chat_stream: str, 聊天流标识符，若没有则根据group_name生成

        一定要有的参数:
        name: str, 发送者名称
        content: str, 消息内容
        """
        msg = self.host_msg_complete(msg)
        self.name: str = name
        self.content: str = content
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

    def host_msg_complete(self, msg: Optional[Dict]) -> Dict:
        """补全参数group_name和chat_stream"""
        if msg is None:
            msg = {}
        if "group_name" not in msg.keys():
            msg['group_name'] = "电脑本地"
        if "chat_stream" not in msg.keys():
            msg['chat_stream'] = string_to_hash(msg['group_name'])
        return msg
    
    def _to_dict(self)->Dict:
        return {
            "name": self.name,
            "content": self.content,
            "timestamp": self.timestamp,
            "time": self.time,
            "chat_stream": self.chat_stream,
            'chat_plat': self.chat_plat,
            'group_name': self.group_name,
        }
    
    def _to_json(self):
        return json.dumps(self._to_dict(), ensure_ascii=False)


class FriendMsg(Msgbase):
    """
    好友的消息类

    创建时必须要有的参数：
    name: str, 发送者名称
    content: str, 消息内容
    """
    def __init__(self, msg: Optional[Dict]):
        """这里msg是接收的json转字典"""
        if msg is None:
            logger.error("FriendMsg 初始化失败，msg参数为None")
            raise ValueError("FriendMsg 初始化失败，msg参数为None")
        self.name = msg['name']
        self.content = msg['content']

        super().__init__(msg, self.name, self.content)


class Response(Msgbase):
    """
    机器人的回复消息类
    注意显式调用init函数,保证回复与消息设置一致
    """
    def __init__(self, response=""):
        """
        msg参数，是朋友的消息，用于标定要回复哪一条消息

        通过msg得到聊天流chat_stream和群组group_name，其余均自动生成，但是response需要再次获取

        先进行消息缓冲，对于部分内容进行回复时，将那些消息整合为一个消息类，再根据存储的消息类生成回复内容，
        也就是在接收消息时就生成回复类，根据buffer决断self.Msgs = []里面有多少消息，然后进行回复
        """
        self.content = response         # 回复内容
        self.name = BOT_NAME
        self.Msgs: List[Msgbase] = []   # 此次作为回复目标的消息列表
        self.sys_prompt = ""
        self.user_prompt = ""
        super().__init__(None, self.name, self.content)


    def init(self,msg: Msgbase):
        """根据消息类初始化回复类,"""
        self.Msgs.append(msg)
        self.name = BOT_NAME
        self.content = ""
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
        self.content = response
        self.value['content'] = self.content


    def add_msg(self, msg: Msgbase):
        """添加消息到回复类中"""
        self.Msgs.append(msg)

    
    def gather_from_name(self):
        """
        将消息按照名字进行字典存储与消息转换
        格式:{
        "name": time+contents
        ...
        }
        主要用于分别分析不同人的情绪状态
        """
        name_dict = {}
        for msg in self.Msgs:
            if msg.name not in name_dict.keys():
                name_dict[msg.name] = msg.content
            else:
                name_dict[msg.name] += "\n" + msg.content
        return name_dict
    
    def get_strings(self):
        """
        将消息按照 姓名+内容 拼接为一条
        """

        contents = ""
        for msg in self.Msgs:
            contents += msg.name + ": " + msg.content + "\n"
        return contents

    def get_emotion_dict(self):
        """专门给emotion的LLM吃的字符串"""
        content_dict = {}
        for msg in self.Msgs:
            content_dict[msg.name] = msg.content
        content_dict["总消息"] = self.get_strings()
        return content_dict


if __name__ == '__main__':
    res = Response()
    print(res._to_dict())