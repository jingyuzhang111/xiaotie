"""
状态心跳

所有"随时间演化"的状态在同一个 tick 里更新:
    心情/兴趣 (mood) 的衰减
    疲惫     (tired) 的恢复
以后新增的衰减类状态也注册到这里。

"""
import time

from src.config import *
from src.logger import get_module_logger

logger = get_module_logger("state")


def _state_steps():
    """
    返回 ((名字, 更新函数), ...)

    延迟导入:各状态模块不需要知道对方,编排只在这里发生
    """
    from src.emood.mood import moodupdater
    from src.emood.tired import tiredupdater

    return (
        ("mood", moodupdater.update_in_timeloop),
        ("tired", tiredupdater.update_in_timeloop),
    )


def update_all_state() -> None:
    """一个 tick 更新全部状态"""
    for name, step in _state_steps():
        # 每个状态独立兜异常:一个坏了不能拖垮其它状态的心跳
        try:
            step()
        except Exception as e:
            logger.exception(f"状态更新失败 [{name}]: {e}")

    snap = state_snapshot()
    logger.info(
        f"状态 | 兴趣 {snap['interest_value']:.2f} 心情 {snap['mood_value']:.2f} "
        f"疲惫 {snap['fatigue']:.3f} 密度 {snap['msg_rate']:.3f}/s "
        f"意愿 {snap['eagerness']:.3f}"
    )


def get_eagerness(*, fatigue: float, interest: float) -> float:
    """发言意愿 我们还原了大肥鱼偷懒的性格"""
    base = min(1.0, max(0.0, interest / INTEREST_MAX))
    return base * (1.0 - fatigue)


def state_snapshot() -> dict:
    """
    取一份完整的当前状态,供决策层和工具使用
    """
    from src.emood.mood import moodupdater
    from src.emood.tired import tiredupdater

    with moodupdater.mood_lock:
        interest_value = moodupdater.interest_value
        mood_value = moodupdater.mood_value
        delta_msg = moodupdater.delta_msg
        delta_idle = moodupdater.delta_idle

    with tiredupdater.tired_lock:
        fatigue = tiredupdater.fatigue
        msg_rate = tiredupdater.rate

    return {
        "mood_value": mood_value,
        "interest_value": interest_value,
        "delta_msg": delta_msg,
        "delta_idle": delta_idle,
        "fatigue": fatigue,
        "msg_rate": msg_rate,
        "eagerness": get_eagerness(fatigue=fatigue, interest=interest_value),
    }
