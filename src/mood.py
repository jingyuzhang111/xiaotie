import threading
import time
import numpy as np
from datetime import datetime
import random
from src.observer import time_obsever
from src.config import *
from src.emotion import emotion_manager
from src.msgbase import Msgbase
from src.mongodb import update_friend


from src.logger import get_module_logger
logger = get_module_logger("mood")


class MoodUpdater():
    def __init__(self):
        self.interest_value = 0
        self.mood_value = 0
        self.timenow = time.time()
        self.delta_time = 0
        self.mood_lock = threading.RLock()  # 线程锁
        self.msg_time = []
    def update_in_timeloop(self, ):
        """
        不在主线程，根据时间循环触发
        根据消息发送频率更新兴趣值,兴趣值决定回复概率
        根据消息内容和数据库好感更新心情值，心情值改变prompt
        """
        # with self.mood_lock:
        self.get_delta_time()
        with self.mood_lock:
            if self.delta_time > 30:
                self.interest_value = self.interest_value*INTEREST_DECAY_RATE[0]
                self.mood_value = self.mood_value * MOOD_DECAY_RATE[0]
            elif self.delta_time >200:
                self.interest_value = self.interest_value*INTEREST_DECAY_RATE[1]
                self.mood_value = self.mood_value * MOOD_DECAY_RATE[1]

            # if average_time > 10:
            #     self.mood_value = self.mood_value*MOOD_DECAY_RATE[0]
            # elif average_time > 30:
            #     self.mood_value = self.mood_value*MOOD_DECAY_RATE[1]

            # 保持兴趣0~100,心情-50~50

            self._clamp_values()
            time_obsever.delete_timelist()

    def update_in_msgloop(self, msg:Msgbase):
        """根据消息触发"""
        


        name = msg.name
        content = msg.content
        now = time.time()
        self.get_delta_time()

        # 首次得到消息，兴趣值加的最多，往后的刺激递减
        self.interest_value +=np.exp(-self.delta_time) * 20

        # 情感分析部分：
        emotion_manager.LLM_get_emotion(content)
        positive,negative,neutral,total = emotion_manager.emotion_analyze_basic() # type: ignore
        mood_delta = (positive - negative) / MOOD_INFLUENCE_FACTOR

        self.mood_value += mood_delta * 5

        if mood_delta > 0.5:
            favor_delta = 0.2
        elif mood_delta < -0.5:
            favor_delta = -0.1
        else:
            favor_delta = 0.0

        if self.delta_time < 10:
            rel_delta = 0.1
        elif self.delta_time < 60:
            rel_delta = 0.05
        else:
            rel_delta = 0.02

        rel_delta += max(-0.05, min(0.5, mood_delta * 0.2))

        # 写回数据库并约束由 update_friend_metrics 完成
        try:
            update_friend(name, favor_delta=favor_delta, relationship_delta=rel_delta)
        except Exception as e:
            logger.error(f"更新好友熟悉度/亲近值失败: {e}")

        logger.info(f"mood_delta:{mood_delta} interest_value:{self.interest_value} favor_delta:{favor_delta} rel_delta:{rel_delta}")

        # 最终限制本地值范围
        self._clamp_values()

    def get_delta_time(self):
        self.timenow = time.time()
        time_list = time_obsever.get_timelist()
        if len(time_list) == 0:
            self.delta_time = 10000
        else:
            self.delta_time = self.timenow - time_list[-1]

    def _clamp_values(self):
        if self.interest_value < 1e-5:
            self.interest_value = 0
        elif self.interest_value > 100:
            self.interest_value = 100
        if self.mood_value < -50:
            self.mood_value = -50
        elif self.mood_value > 50:
            self.mood_value = 50
        elif abs(self.mood_value) < 1e-3:
            self.mood_value = 0


moodupdater = MoodUpdater()