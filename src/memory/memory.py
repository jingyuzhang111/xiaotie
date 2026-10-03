from src.mongodb import *
from src.config import HISTORY_GAP_NOTICE
from src.logger import get_module_logger
from src.memory.recalltimestamp import MemoryBuildScheduler
logger = get_module_logger("memory")



import jieba
import jieba.posseg as pseg
import re
from zhon import hanzi

######################################################
import logging
import warnings

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
)
_jieba_initialized = False
def _ensure_jieba_initialized():
    """Lazy init jieba once to avoid repeated startup noise and duplicate work."""
    global _jieba_initialized
    if _jieba_initialized:
        return

    jieba.setLogLevel(logging.ERROR)
    try:
        jieba.default_logger.setLevel(logging.ERROR)
    except Exception:
        pass

    try:
        jieba.load_userdict(r"static\userdict.txt")
    except FileNotFoundError:
        logger.warning("jieba用户词典未找到，继续使用默认词典")

    _jieba_initialized = True
_ensure_jieba_initialized()
# 获取 jieba 的 logger
jieba_logger = logging.getLogger('jieba')
jieba_logger.setLevel(logging.ERROR)  # 只显示 ERROR 及以上级别的日志
######################################################

def find_closest_chat(timestamp, length=5):
    closest_chat = db_messages.find_one(
        {"chat_plat": CHAT_PLAT, "timestamp": {"$lte": timestamp}},
        sort=[("timestamp", -1)])
    if closest_chat:
        closest_timestamp = closest_chat["timestamp"]
        chats = db_messages.find(
            {"chat_plat": CHAT_PLAT,
            #  "name":"self",
                "timestamp": {"$gte": closest_timestamp},
             "chat_stream": closest_chat["chat_stream"],
             }).sort("timestamp", 1).limit(length)
        return list(chats)
    return []


def render_history(history_list: list[dict]) -> str:
    """
    把消息列表渲染成一段背景文本

    每条带一个 HH:MM:够看出消息之间隔了多久,又不像完整时间戳那样抢眼
    (满屏的秒和日期会让她觉得"时间"是个重要信息,张口就报)。
    跨天插日期;隔得久的单独标一行,省得她自己算。
    """
    from src.state_loop import human_duration

    lines: list[str] = []
    last_date = None
    last_ts = None
    for post in history_list:
        stamp = str(post.get("time") or "")
        date = stamp[:10]
        ts = post.get("timestamp")

        if date and date != last_date:
            if lines:
                lines.append("")
            lines.append(f"--- {date} ---")
            last_date = date
        elif isinstance(last_ts, (int, float)) and isinstance(ts, (int, float)):
            if ts - last_ts >= HISTORY_GAP_NOTICE:
                lines.append(f"（隔了 {human_duration(ts - last_ts)}）")

        clock = stamp[11:16]
        lines.append(f"{clock} {post['name']}: {post['content']}" if clock
                     else f"{post['name']}: {post['content']}")
        last_ts = ts

    return "\n".join(lines)


class MemoryManager():
    def __init__(self):
        pass

    def generate_history_dialog(self, chat_stream="277f2c7aef6b4df267063467cfbff5b1", limit=20):
        """ 获取时间最近的（limit）条历史消息 """
        history = db_messages.find({"chat_plat": CHAT_PLAT,
                                    "chat_stream": chat_stream}).limit(limit)
        history.sort("timestamp", -1)
        history_list = list(history)
        history_list.reverse()
        return render_history(history_list)

    def save_memory(self, msg):
        """保存记忆到数据库"""
        db_add(msg)
        logger.debug(f"Memory saved for message from {msg.name} at {msg.time}")

    def get_resent_memory(self, limit=20):
        """获取最近的记忆, 得到最近的消息,而不是正态抽样"""
        memories = db_messages.find({"name":"小贴"}).sort("timestamp", -1).limit(limit)
        # logger.info(memories)
        memory_list = [memory for memory in memories]
        logger.debug(f"Retrieved {len(memory_list)}")
        return memory_list
    
    def get_memory_by_time(self, limit=20):
        scheduler = MemoryBuildScheduler(
        n_hours1=12,  # 第一个分布均值（12小时前）
        std_hours1=8,  # 第一个分布标准差
        weight1=0.7,  # 第一个分布权重 70%
        n_hours2=36,  # 第二个分布均值（36小时前）
        std_hours2=24,  # 第二个分布标准差
        weight2=0.3,  # 第二个分布权重 30%
        total_samples=50,  # 总共生成50个时间点
    )
        scheduler.generate_time_samples()
        timestamps = scheduler.get_timestamp_array()
        messages = []
        for timestamp in timestamps:
            msgs = find_closest_chat(timestamp=timestamp)
            messages.extend(msgs)
        
        msgs = [] 
        for msg in messages:
            if msg not in msgs:
                msgs.append(msg)
        return msgs

    def get_time_content(self, timestamp):
        """根据时间戳获取对应的消息内容"""
        chat = db_messages.find_one({"chat_plat": CHAT_PLAT, "timestamp": timestamp})
        if chat:
            return f"[{chat['time']}] {chat['name']}: {chat['content']}"
        return None


memory_manager = MemoryManager()


def text_score(text:str, top_k=3):
    """
    对文本进行打分, 目前简单统计词频, 后续可以增加情感分析等维度
    根据简单的分数计算得到前tok_k个重要词

    目前已被LLM取代，此函数仅用于对实时的聊天内容进行关键词切分

    好像关键词切分也是AI更好一些...
    """
    words_flag = {word: flag for word, flag in pseg.cut(text)}
    words_score = {}
    i = 0
    for word, flag in words_flag.items():
        score = 0
        i += 1
        if flag == "x":
            continue
        if len(word) <= 1:
            continue
        if word in words_score:
            words_score[word] += 1
            continue
        if i < len(words_flag)//3:
            score += 1
        
        words_score[word] = score

    words_dict = dict(sorted(words_score.items(), key=lambda x: x[1], reverse=True))
    words = list(words_dict.keys())
    words_important = list(words_dict.keys())[0:top_k]
    return words_important,words


def hit_keywords(text: str, known: set[str]) -> list[str]:
    """
    从文本里挑出"命中了记忆节点"的词

    为什么不直接用 text_score 的"重要词":
        这里要找的是"这句话里出现了哪个已有关键词",不是"哪个词最重要",
        判据完全不同。比如"你还记得轰炸测试吗",按重要词算可能挑出"记得",
        但真正该命中节点的是"轰炸测试"。
    """
    hits: list[str] = []

    # 一、按 jieba 切词匹配(带 static/userdict.txt 里的用户词典)
    for word in jieba.lcut(text):
        word = word.strip()
        if word and word in known and word not in hits:
            hits.append(word)

    # 二、兜底:节点名直接作为子串出现在文本里
    #    用户词典没收录"轰炸测试"这类词时,jieba 会把它切成"轰炸"+"测试",
    #    上面那一步就漏了。子串匹配慢一些,但节点是百这个量级,可以接受。
    for name in known:
        if name not in hits and name in text:
            hits.append(name)

    return hits


if __name__ == "__main__":
    test = "并且把表情包描述字段字段字段和你现在的图像理解流程卧槽ccb对齐,1212121,4782。"

    words = text_score(test, top_k=3)

    print(words)

