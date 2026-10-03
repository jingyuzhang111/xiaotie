"""
疲惫值

两个来源,方向一致(都是"不想干"),所以对外合成一个值;
但内部分开记两笔账 —— 恢复速度不一样:
    chat_load  被消息刷烦了(刺激太多)   恢复快
    work_load  干活干累了  (调工具、想很多圈) 恢复慢
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
        self.chat_load: float = 0.0    # 账本一:被消息刷烦了
        self.work_load: float = 0.0    # 账本二:干活干累了
        self.rate: float = 0.0         # 最近的消息密度(条/秒),只读观测值
        self.tired_lock = threading.RLock()
        self.start_time = time.time()
        self.last_recover_time = time.time()

    @property
    def fatigue(self) -> float:
        """
        对外只有一个疲惫值

        两个来源本来就同向 —— 她不会"被刷烦了但不累",分开给模型两个词
        只会让它来回搬。要分开看的只有里面的账。
        """
        return min(1.0, self.chat_load + self.work_load)


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
            self.chat_load = min(1.0, self.chat_load + FATIGUE_GAIN * excess * max(1, batch_size))
            logger.info(
                f"消息密集 rate={self.rate:.3f}/s 本批{batch_size}条 "
                f"chat={self.chat_load:.3f} work={self.work_load:.3f} "
                f"fatigue={self.fatigue:.3f}"
            )


    def add_workload(self, amount: float, reason: str = "") -> None:
        """干了一点活 —— 思考一圈、调一次工具都算"""
        if amount <= 0:
            return
        with self.tired_lock:
            before = self.work_load
            self.work_load = min(1.0, self.work_load + amount)
            if self.work_load - before < 1e-6:
                return          # 已经到顶了,不用每次刷屏
            logger.info(
                f"干活 {reason or '?'} +{amount:.3f} "
                f"work={self.work_load:.3f} fatigue={self.fatigue:.3f}"
            )


    def update_in_timeloop(self) -> None:
        """定时循环:两笔账各自按 exp(-Δt/τ) 恢复"""
        with self.tired_lock:
            now = time.time()
            tick = max(0.0, now - self.last_recover_time)
            self.last_recover_time = now
            self.rate = self.recent_rate()
            if tick <= 0:
                return

            self.chat_load *= math.exp(-tick / FATIGUE_RECOVER_TAU)
            self.work_load *= math.exp(-tick / FATIGUE_WORK_TAU)

            if self.chat_load < 1e-3:
                self.chat_load = 0.0
            if self.work_load < 1e-3:
                self.work_load = 0.0


tiredupdater = TiredUpdater()
