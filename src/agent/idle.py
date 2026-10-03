"""
自发循环

没人找她的时候,她自己待着、自己找点事做。

每 IDLE_TICK 秒看一次,但绝大多数时候什么都不做 ——
"该不该动"全是本地判断(读几个浮点数),不花任何调用。
只有真的要动了才启动一次 think。
"""
import random
import uuid

from src.config import *
from src.emood.drive import driveupdater
from src.emood.tired import tiredupdater
from src.globalcontrol import global_control
from src.logger import get_module_logger

logger = get_module_logger("idle")


def _silent_seconds() -> float:
    """
    上次有人说话到现在过了多久

    借 mood 那份,不自己读 time_obsever —— 那个只记本次进程收到的消息,
    重启后是空的,静默时长会算成 0,于是她永远没资格自己动起来。
    """
    from src.emood.mood import moodupdater

    with moodupdater.mood_lock:
        return moodupdater.delta_idle


def _pick_someone() -> dict | None:
    """
    挑一个说话对象 —— 好感高的概率大,但不是必然

    好感(-10~10)映射成权重:讨厌的人几乎不会被选中,但也不是 0 ——
    关系是会变的,完全不给机会就永远翻不了身。

    先筛出"能送达的":db_friend 里没存聊天流,得从这人最近一条消息里找;
    找不到就说明没法把话送出去,这个人先跳过。
    """
    from src.mongodb import db_friend, db_messages

    usable = []
    for friend in db_friend.find({}):
        name = friend.get("name")
        if not name or name == BOT_NAME:
            continue        # 只排除她自己。注意 self 是"对面那个人",不是她自己

        last = db_messages.find_one({"name": name}, sort=[("timestamp", -1)])
        if not last or not last.get("chat_stream"):
            continue

        friend["chat_stream"] = last["chat_stream"]
        friend["group_name"] = last.get("group_name")
        usable.append(friend)

    if not usable:
        return None

    weights = []
    for friend in usable:
        favor = friend.get("favor_ability") or 0
        relationship = friend.get("relationship_value") or 0
        weights.append(max(0.05, (favor + 10) / 20 * 3.0 + relationship / 100 + 0.2))

    return random.choices(usable, weights=weights, k=1)[0]


def idle_tick() -> None:
    """自发循环的一次心跳"""
    if not global_control.want_thinking:
        return

    if tiredupdater.fatigue >= IDLE_FATIGUE_LIMIT:
        return              # 累了就歇着,别折腾

    if not driveupdater.can_act(_silent_seconds()):
        return              # 不无聊 / 刚聊完 / 还在冷却

    target = _pick_someone()
    if target is None:
        return

    logger.info(f"无聊到 {driveupdater.boredom:.2f},自己动起来,想找 {target['name']}")
    driveupdater.mark_action()

    from src.agent.think import think

    trace = uuid.uuid4().hex[:6]
    finished = think(idle=True, target=target, trace=trace)

    from src.agent.deliver import deliver
    from src.msgbase import Response

    response = Response()
    # Response 构造时按"电脑本地"算了个 chat_stream,这里要换成目标那条流
    response.chat_stream = target.get("chat_stream") or response.chat_stream
    response.group_name = target.get("group_name") or response.group_name
    response.value["chat_stream"] = response.chat_stream
    response.value["group_name"] = response.group_name

    # 怎么判结局、怎么发,和消息那条路共用一套(deliver)
    deliver(finished, response, trace)
