"""
疲惫值(疲劳/厌倦)

一时间接收太多消息会感觉累，就会休息。

待添加：
进行其他工作太多也会感觉累
思考链中调用文件，或者上网查东西太多，或者被让写太久代码，也会累。
"""
import math
import threading
import time

from src.observer import time_obsever
from src.msgbase import Response
from src.config import *
from src.logger import get_module_logger

logger = get_module_logger("tired")


class TiredUpdater():
    def __init__(self):
        self.fatigue: float = 0.0      # 疲惫值 0(精神) ~ 1(烦透了)
        self.rate: float = 0.0         # 最近的消息密度(条/秒),只读观测值
        self.tired_lock = threading.RLock()
        self.start_time = time.time()
        self.last_recover_time = time.time()


    # ------------------------- 密度 -------------------------
    def recent_rate(self) -> float:
        """
        用 time_obsever 里逐条消息的到达时刻,估算最近的消息密度(条/秒)

        用"最近 N 条消息的实际跨度",而不是固定时间窗口:
            密度 = (条数 - 1) / (最新时刻 - 最早时刻)
        这样即使 deque 被 maxlen 截断,依然能还原出真实密度。
        固定窗口会被 maxlen 卡住 —— 50 条刷屏和 20 条看起来一样密。

        样本太少时返回 0:进程刚启动,不该因为冷启动就累
        """
        times = time_obsever.get_timelist()
        if len(times) < DENSITY_MIN_SAMPLES:
            return 0.0
        span = times[-1] - times[0]
        if span <= 0:
            return 0.0
        return (len(times) - 1) / span


    # ------------------------- 更新 -------------------------
    def update_in_msgloop(self, response: Response) -> None:
        """
        收到消息时累加疲惫

        只有密度超出舒适区才累,正常节奏的聊天完全不累。
        增量 = 超出舒适区的程度 × 这一批的条数:
        前者说明"现在处于过载状态",后者说明"这一批具体贡献了多少"。
        """
        with self.tired_lock:
            self.rate = self.recent_rate()
            excess = max(0.0, self.rate - COMFORT_RATE) / COMFORT_RATE
            if excess <= 0:
                return
            batch_size = len(getattr(response, "Msgs", ()) or ())
            self.fatigue += FATIGUE_GAIN * excess * max(1, batch_size)
            if self.fatigue > 1.0:
                self.fatigue = 1.0
            logger.info(
                f"消息密集 rate={self.rate:.3f}/s 本批{batch_size}条 "
                f"fatigue={self.fatigue:.3f}"
            )


    def update_in_timeloop(self) -> None:
        """
        定时循环:疲惫随时间恢复

        用 exp(-Δt/τ),不是"每 tick 乘一个固定值"。
        后者会让衰减速度跟着 tick 间隔跑偏 —— 这个坑 mood.py 踩过:
        interval_sec 从 2 改成 5,衰减就快了 2.5 倍。
        """
        with self.tired_lock:
            now = time.time()
            tick = max(0.0, now - self.last_recover_time)
            self.last_recover_time = now
            self.rate = self.recent_rate()
            if tick <= 0:
                return
            self.fatigue *= math.exp(-tick / FATIGUE_RECOVER_TAU)
            if self.fatigue < 1e-3:
                self.fatigue = 0.0

tiredupdater = TiredUpdater()
