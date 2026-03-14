from src.mongodb import *
from src.logger import get_module_logger
from src.memory.recalltimestamp import MemoryBuildScheduler
logger = get_module_logger("memory")

def find_closest_chat(length, timestamp):
    closest_chat = db_messages.find_one(
        {"chat_plat": CHAT_PLAT, "timestamp": {"$lte": timestamp}},
        sort=[("timestamp", -1)])
    if closest_chat:
        closest_timestamp = closest_chat["timestamp"]
        chats = db_messages.find(
            {"chat_plat": CHAT_PLAT,
                "timestamp": {"$gte": closest_timestamp},
             "chat_stream": closest_chat["chat_stream"],
             }).sort("timestamp", 1).limit(length)
        return list(chats)
    return []

def memory_process():
    pass


class MemoryManager():
    def __init__(self):
        pass

    def generate_history_dialog(self, chat_stream, limit=20):
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
        """获取最近的记忆"""
        memories = db_messages.find({"name":"小贴"}).sort("timestamp", -1).limit(limit)
        logger.info(memories)
        memory_list = [memory for memory in memories]
        logger.debug(f"Retrieved {len(memory_list)}")
        return memory_list

memory_manager = MemoryManager()

memories = memory_manager.get_resent_memory(limit=5)
logger.info(f"{[memory["timestamp"] for memory in memories] }")

if __name__ == "__main__":
    print(memory_manager.generate_history_dialog("277f2c7aef6b4df267063467cfbff5b1"))

    chats = find_closest_chat(1, 1763535553)
    print("chats:", chats)


    scheduler = MemoryBuildScheduler(
        n_hours1=3,  # 第一个分布均值（12小时前）
        std_hours1=8,  # 第一个分布标准差
        weight1=0.7,  # 第一个分布权重 70%
        n_hours2=36,  # 第二个分布均值（36小时前）
        std_hours2=24,  # 第二个分布标准差
        weight2=0.3,  # 第二个分布权重 30%
        total_samples=50,  # 总共生成50个时间点
    )
    timestamps = scheduler.generate_time_samples()
    timestamps = [timestamps[i].timestamp() for i in range(len(timestamps))]
    print(timestamps)
    for timestamp in timestamps:
        chats = find_closest_chat(1, timestamp)
        print("chats:", chats)