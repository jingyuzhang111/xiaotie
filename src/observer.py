from datetime import datetime
import time
import threading
from src.config import *
from typing import Dict, Optional
from collections import deque
import hashlib
from abc import ABC, abstractmethod
import sys
import io
import json
from src.logger import get_module_logger


class MessageObserver(ABC):

    def __init__(self,max_size = 20):
        self._lock = threading.RLock()
        self.timelist = deque(maxlen=max_size)  # 双端队列，在两端操作数据非常快,旧元素会被自动删除

    @abstractmethod
    def look(self,*args,**kwargs):
        ... # 观察者的抽象方法，必须实现


    def get_timelist(self):
        with self._lock:
            return list(self.timelist)

    def delete_timelist(self):
        if len(self.timelist) > 2:
            with self._lock:
                self.timelist.popleft()


class TimeObsever(MessageObserver):
    """观察者,存储最近max_size条消息的创建时间,与不同人发送的消息的时间"""
    def __init__(self,max_size = 20):
        self.time_dict = {}
        super().__init__(max_size)

    def look(self, msg):
        """
        每当消息类被创建,就会记录下同名消息的时间列表,从而知道指定人的最近消息与总体频率
        """
        if msg.name != BOT_NAME:
            with self._lock:
                self.timelist.append(time.time())
                if msg.name not in self.time_dict:
                    self.time_dict[msg.name] = deque(maxlen=10)
                self.time_dict[msg.name].append(time.time())

class BufferTimeObserver(MessageObserver):
    """相对独立, 不在MessageSubject里"""
    def __init__(self, max_size=20):
        super().__init__(max_size)
    def look(self):
        """每当消息类被创建,就会记录下消息的时间列表"""
        with self._lock:
            self.timelist.append(time.time())





class MessageSubject:
    """消息主题（被观察者）"""
    def __init__(self):
        self._observers: list[MessageObserver] = []
        self._lock = threading.RLock()

    def add_observer(self,observer:MessageObserver):
        with self._lock:
            self._observers.append(observer)

    def remove_observer(self,observer:MessageObserver):
        with self._lock:
            self._observers.remove(observer)

    def notify_observers(self, message):
        """通知所有观察者"""
        with self._lock:
            for observer in self._observers:
                observer.look(message)


msg_subject = MessageSubject()
time_obsever = TimeObsever()
buffer_time_observer = BufferTimeObserver()

msg_subject.add_observer(time_obsever)

