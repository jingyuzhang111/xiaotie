from src.mongodb import *
from src.logger import get_module_logger
# from recalltimestamp import MemoryBuildScheduler
logger = get_module_logger("memory")

class MemoryManager():
    def __init__(self):
        pass

    def generate_history_dialog(self, chat_stream, limit=20):
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
