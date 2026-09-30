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


def describe_eagerness(value: float) -> str:
    """转化意愿值为文字描述"""
    if value >= 0.7:
        return "你现在挺想聊的"
    if value >= 0.4:
        return "你状态还行,看对方说什么"
    if value >= 0.2:
        return "你有点疲了,不太想主动接话"
    return "你现在挺累,或者刚被消息刷过屏,不太想说话"


def describe_mood(mood_value: float) -> str:
    """转化心情值为语气描述(给说话层定调)。心情范围 -50~50,0 为中性"""
    if mood_value >= 25:
        return "心情特别好，语气轻快，可以多话一点"
    if mood_value >= 10:
        return "心情不错，说话放松一些"
    if mood_value > -10:
        return "心情平平，正常说话就行"
    if mood_value > -25:
        return "心里有点闷，不太提得起劲"
    return "心情很糟，话少一点，也不用强装开心"


def describe_friend(friend: dict | None) -> str:
    """
    把好感度和熟悉度翻译成人话

    两者独立:可能很熟但不喜欢,也可能刚认识就很投缘。
    好感 -10~10(可为负);熟悉 0~100(只增不减)。
    """
    if not friend:
        return ""

    name = friend.get("name") or "对方"
    favor = friend.get("favor_ability") or 0
    relationship = friend.get("relationship_value") or 0

    if favor >= 5:
        favor_text = "你非常喜欢他"
    elif favor >= 2:
        favor_text = "你对他印象不错"
    elif favor > -2:
        favor_text = "还说不上喜不喜欢"
    elif favor > -5:
        favor_text = "你有点烦他"
    else:
        favor_text = "你挺反感他"

    if relationship >= 60:
        rel_text = "老熟人了"
    elif relationship >= 30:
        rel_text = "聊过不少次，算熟"
    elif relationship >= 10:
        rel_text = "见过几面，还不太熟"
    else:
        rel_text = "基本是生人，别太自来熟"

    return f"你跟{name}的关系：{favor_text}；{rel_text}"


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
