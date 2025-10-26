from datetime import datetime
import time
import threading
from config import *
from typing import Dict, Optional
from collections import deque
import hashlib
from abc import ABC, abstractmethod
import sys
import io
import json
from logger import get_module_logger


class MessageObserver(ABC):

    @abstractmethod
    def on_message_created(self,msg):
        pass


class TimeObsever():
    def __init__(self,max_size = 20):
        self._lock = threading.RLock()
        self.timelist = deque(maxlen=max_size)  # 双端队列，在两端操作数据非常快
        self.time_dict = {}

    def on_message_created(self,msg):
        if msg.name != BOT_NAME:
            with self._lock:
                self.timelist.append(time.time())
                if msg.name not in self.time_dict:
                    self.time_dict[msg.name] = deque(maxlen=10)
                self.time_dict[msg.name].append(time.time())

        if len(self.timelist) >20:
            self.timelist.popleft()

    def get_timelist(self):
        with self._lock:
            return list(self.timelist)
    def delete_timelist(self):
        if len(self.timelist) > 2:
            with self._lock:
                self.timelist.popleft()


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
                observer.on_message_created(message)


msg_subject = MessageSubject()
time_obsever = TimeObsever()

msg_subject.add_observer(time_obsever)

