import threading
import time
import numpy as np
from datetime import datetime
import random
from src.observer import time_obsever
from src.config import *
from src.emood.emotion import emotion_manager
from src.msgbase import Msgbase, Response
from src.mongodb import update_friend


from src.logger import get_module_logger
logger = get_module_logger("mood")


class MoodUpdater():
    def __init__(self):
        self.interest_value:float = 0             # 兴趣值，决定回复概率
        self.mood_value:float = 0                 # 心情值，影响回复内容和风格
        self.mood_lock = threading.RLock()  # 线程锁

        self.delta_msg:float = 0            # 当前消息与上一条消息的时差 用于消息更新心情
        self.delta_idle:float = 0           # 当前时刻与最近一条消息的时差 用于时间更新心情

        self.start_time = time.time()               # 进程启动时刻，还没收到过消息时的兜底基准
        self.last_msg_time:float | None = None      # 上一次处理消息的时刻，delta_msg 的基准


    def update_in_timeloop(self, ):
        """
        不在主线程，根据时间循环触发
        根据消息发送频率更新兴趣值,兴趣值决定回复概率
        根据消息内容和数据库好感更新心情值，心情值改变prompt
        """
        with self.mood_lock:
            # 每个循环更新一次，根据delta选取衰减率
            # delta_idle：当前时刻与最近一条消息的时差，用来判断"凉了多久"
            self.delta_idle = max(0.0, time.time() - self._last_received_time())

            if self.delta_idle > 200:
                self.interest_value = self.interest_value*INTEREST_DECAY_RATE[1]
                self.mood_value = self.mood_value * MOOD_DECAY_RATE[1]
            elif self.delta_idle >30:
                self.interest_value = self.interest_value*INTEREST_DECAY_RATE[0]
                self.mood_value = self.mood_value * MOOD_DECAY_RATE[0]

            # 保持兴趣0~100,心情-50~50

            self._clamp_values()


    def update_in_msgloop(self, response:Response):
        """根据消息触发心理更新"""

        with self.mood_lock:
            # delta_msg：本次消息与上一次消息的时差
            # 首次没有上一条基准，记 0（exp(-0) 最大），让首条消息的刺激给满
            now = time.time()
            self.delta_msg = 0.0 if self.last_msg_time is None else max(0.0, now - self.last_msg_time)
            self.last_msg_time = now
            delta_msg = self.delta_msg

            # 首次得到消息，兴趣值加的最多，往后的刺激递减
            self.interest_value +=np.exp(-delta_msg/30) * 20

        # 情感分析部分/分析结果存储在emotion_manager里
        contents = response.get_emotion_dict()      # 将消息列表转为适用于情感分析的字典格式
        emotion_manager.LLM_get_emotion(contents)   # 调用LLM
        emotion_manager.analyze_many()              # 综合分析

        mood_delta = dict(emotion_manager.mood_delta)   # 取快照，防止遍历过程中被下一轮分析覆盖

        for name, delta in mood_delta.items():

            # 总消息用于更新当前心情值
            if name == "总消息":
                with self.mood_lock:
                    self.mood_value += delta * 5
            else:
                # 个人的消息评价用于更新与此人的关系和好感度
                # 好感度与此人的言行有关
                if delta > 0.5:
                    favor_delta = 0.2
                elif delta < -0.5:
                    favor_delta = -0.1
                else:
                    favor_delta = 0.0

                # 熟悉度只与接收消息的频率有关
                # 熟悉度与好感度是相对独立的，见得多就熟悉，但不一定有好感
                # 用消息间隔 delta_msg，不是空闲时长 delta_idle
                if delta_msg < 10:
                    rel_delta = 0.1
                elif delta_msg < 60:
                    rel_delta = 0.05
                else:
                    rel_delta = 0.02

                rel_delta += max(-0.05, min(0.5, delta * 0.2))

                # 写回数据库并约束由 update_friend_metrics 完成
                try:
                    update_friend(name, favor_delta=favor_delta, relationship_delta=rel_delta)
                except Exception as e:
                    logger.error(f"更新好友熟悉度/亲近值失败: {e}")

                logger.info(f"mood_delta:{mood_delta} interest_value:{self.interest_value} favor_delta:{favor_delta} rel_delta:{rel_delta}")

        # 最终限制本地值范围
        with self.mood_lock:
            self._clamp_values()


    def _last_received_time(self) -> float:
        """
        最近一条用户消息的到达时刻
        time_obsever 记录的是消息到达时间，[-1] 恒为最新一条，不需要猜位置
        进程启动后还没收到过消息时用启动时刻兜底，等价于"从启动到现在都算空闲"
        """
        time_list = time_obsever.get_timelist()
        return time_list[-1] if time_list else self.start_time


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