from src.mongodb import *
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
        history_content = '\n'
        for post in history_list:
            one_piece = f"[{post['time']}] {post['name']}: {post['content']}\n"
            history_content += one_piece
        return history_content

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

    words_important = dict(sorted(words_score.items(), key=lambda x: x[1], reverse=True))
    words_important = list(words_important.keys())[0:top_k]
    return words_important


if __name__ == "__main__":
    test = "并且把表情包描述字段字段字段和你现在的图像理解流程卧槽ccb对齐,1212121,4782。"

    words = text_score(test, top_k=3)

    print(words)

