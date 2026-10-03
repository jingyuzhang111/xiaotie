"""
驱动力

疲惫和无聊是**反方向**的:
    疲惫 = 被消息刷烦了(刺激太多)
    无聊 = 没人理、没事干(刺激太少)
所以不能塞进 tired.py 里合成一个值 —— 她完全可能又累又无聊。
"""
import threading
import time

from src.config import *
from src.logger import get_module_logger

logger = get_module_logger("drive")


def _idle_seconds() -> float:
    """上次有人说话到现在过了多久 —— 跟 mood 共用一份,不各自算"""
    from src.emood.mood import moodupdater

    with moodupdater.mood_lock:
        return moodupdater.delta_idle


class DriveUpdater:
    def __init__(self):
        self.boredom: float = 0.0      # 0(有聊) ~ 1(无聊透了)
        self.lock = threading.RLock()
        self.last_tick = time.time()
        self.last_action = 0.0         # 上次自己找事做的时刻,用来冷却
        self._seeded = False           # 重启后第一 tick 要先把离线那段时间补上

    def update_in_timeloop(self) -> None:
        """无聊随时间涨"""
        if not self._seeded:
            idle = _idle_seconds()
            with self.lock:
                self._seeded = True
                self.last_tick = time.time()
                self.boredom = min(1.0, idle / BOREDOM_RISE_TAU)
            logger.info(f"无聊基准取自空闲 {idle:.0f}s → {self.boredom:.2f}")
            return

        with self.lock:
            now = time.time()
            tick = max(0.0, now - self.last_tick)
            self.last_tick = now
            if tick <= 0:
                return

            self.boredom = min(1.0, self.boredom + tick / BOREDOM_RISE_TAU)

    def satisfy(self, amount: float = IDLE_SATISFY) -> None:
        """有事干了,就不那么无聊了"""
        with self.lock:
            self.boredom = max(0.0, self.boredom - amount)

    def can_act(self, silent_seconds: float) -> bool:
        """
        够不够格自己动起来

        silent_seconds 是"上次有人说话到现在过了多久"。
        """
        if self.boredom < IDLE_BOREDOM_THRESHOLD:
            return False
        if silent_seconds < IDLE_MIN_SILENCE:
            return False
        if time.time() - self.last_action < IDLE_COOLDOWN:
            return False
        return True

    def mark_action(self) -> None:
        """记下"我刚自己做了点什么" —— 降无聊 + 起冷却"""
        with self.lock:
            self.last_action = time.time()
            self.boredom = max(0.0, self.boredom - IDLE_SATISFY)


driveupdater = DriveUpdater()
