from dataclasses import dataclass, field
from msgbase import FriendMsg
import time
from typing import Dict
from collections import OrderedDict
import threading
from src.logger import get_module_logger
import sys

logger = get_module_logger("message_buffer")
logger.remove()  # 移除所有handler
logger.add(sys.stderr, level="WARNING")  # 只显示WARNING及以上级别


@dataclass
class CacheMessages:
    """
    U:未处理消息
    T:已处理消息
    F:过期消息
    """
    message:"FriendMsg"
    Flag: str = "U" # 标定缓冲
    timestamp: float = field(default_factory=lambda: 0.0) # 时间戳

class MessageBuffer:
    def __init__(self,):
        # 有序字典，防止错序，每个聊天流一个缓冲池
        self.buffer_pool: Dict[str, OrderedDict[str, CacheMessages]] = {}
        self.lock = threading.RLock()
        # 每个聊天流加一个计时器
        self.timers: Dict[str, threading.Timer] = {}

    def add_message_start_loop(self, msg: FriendMsg):
        logger.info("缓存")
        chat_stream = msg.chat_stream

        with self.lock:
            if chat_stream not in self.buffer_pool:
                self.buffer_pool[chat_stream] = OrderedDict()

            # 缓存新消息
            cache_msg = CacheMessages(message=msg, Flag="U", timestamp=time.time())
            new_msg_key = str(cache_msg.timestamp)
            self.buffer_pool[chat_stream][new_msg_key] = cache_msg

            # 标记该聊天流之前的未处理消息（跳过新消息）
            expired_count = 0
            for key, existing_cache_msg in list(self.buffer_pool[chat_stream].items()):
                # 使用对象引用比较，确保不会标记新消息
                if existing_cache_msg is cache_msg:
                    logger.info("[消息缓冲]跳过新消息标记")
                    continue

                if existing_cache_msg.Flag == "U":
                    existing_cache_msg.Flag = "F"
                    expired_count += 1

            logger.info(f"[消息缓冲]共标记了 {expired_count} 条过期消息")

            # 停止上一个计时器
            if chat_stream in self.timers:
                self.timers[chat_stream].cancel()

            if self._process_immediately(chat_stream, new_msg_key) > 3:
                # 立即处理消息
                print("提前处理")
                self._process_messages(chat_stream)
                return

            self._start_timer(chat_stream)


    # 设置3秒内没有新的消息，就进行消息合并开始下一步处理
    def _start_timer(self,chat_stream):
        timer = threading.Timer(3.0, self._process_messages, [chat_stream])
        timer.daemon = True
        timer.start()
        self.timers[chat_stream] = timer

    def _process_immediately(self,chat_stream,new_msg_key):
        messages = self.buffer_pool[chat_stream]
        show(messages)

        f_count = 0
        found_new = False
        for key in reversed(messages.keys()):
            if key == new_msg_key:
                found_new = True
                continue

            # 最后一个是新消息，计算紧跟着有多少等待处理的消息
            elif found_new and messages[key].Flag == "F":
                f_count += 1
            else:
                break

        # 如果紧跟着有3条及以上的F消息，则返回True
        logger.info(f"[消息缓冲]紧跟新消息有 {f_count} 条待处理消息")
        return f_count

    def _process_messages(self,chat_stream):
        logger.info("消息处理")
        with self.lock:
            if chat_stream not in self.buffer_pool:
                return

            if chat_stream in self.timers:
                del self.timers[chat_stream]

            messages = self.buffer_pool[chat_stream]
            if not messages:
                return

            last_msg = None
            for msg in messages.values():
                if msg.Flag == "U":
                    last_msg = msg
                    break

            if last_msg == None:
                logger.info("[消息缓冲]没有待处理消息，跳过处理")
                return

            last_msg.Flag = "T"



message_buffer = MessageBuffer()

def show(msgs):
    print(f"""
{[msgs[key].Flag for key in msgs.keys() ]}
    """)


if __name__ == "__main__":

    for i in range(8):
        msg = FriendMsg({
            "name": "测试用户",
            "content": "这是一个测试消息",
        })
        message_buffer.add_message_start_loop(msg)
        time.sleep(1)
    msg = FriendMsg({
        "name": "测试用户",
        "content": "这是一个测试消息",
    })
    message_buffer.add_message_start_loop(msg)
    time.sleep(5)
    message_buffer.add_message_start_loop(msg)
    time.sleep(2)
    message_buffer.add_message_start_loop(msg)
    time.sleep(2)
    message_buffer.add_message_start_loop(msg)
    for i in range(8):
        msg = FriendMsg({
            "name": "测试用户",
            "content": "这是一个测试消息",
        })
        message_buffer.add_message_start_loop(msg)
        time.sleep(1)

