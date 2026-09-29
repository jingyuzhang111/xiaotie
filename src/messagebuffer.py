from dataclasses import dataclass, field
from src.msgbase import FriendMsg, Response
import time
from typing import Dict, Optional, Callable
from collections import OrderedDict
import threading
from src.logger import get_module_logger
import queue
from src.observer import buffer_time_observer
from src.config import *

logger = get_module_logger("message_buffer")

# BUFFER_NUM = 10 # 紧跟新消息有10条及以上的待处理消息,则提前处理

@dataclass
class CacheMessages:
    """
    U:未处理消息
    T:已处理消息
    F:过期消息
    """
    message: FriendMsg
    Flag: str = "U" # 标定缓冲
    timestamp: float = field(default_factory=lambda: 0.0) # 时间戳

class MessageBuffer:
    def __init__(self):
        # 有序字典，防止错序，每个聊天流一个缓冲池
        self.buffer_pool: Dict[str, OrderedDict[str, CacheMessages]] = {}
        self.lock = threading.RLock()
        # 每个聊天流加一个计时器
        self.timers: Dict[str, threading.Timer] = {}


        # 消息处理线程相关
        self.msg_ready_task: Optional[Callable[[Response], None]] = None
        self.queue = queue.Queue()  # 消息处理完成后的结果队列
        self.thread = threading.Thread(target=self._process_queue, daemon=True)


    def set_handler(self, handler):
        """设置消息处理函数,添加线程"""
        logger.info("设置消息处理函数")
        if not handler:
            raise TypeError("消息处理函数不能为空")

        self.msg_ready_task = handler

        if self.thread.is_alive():
            return


        self.thread.start()

    def _process_queue(self):
        """处理完成的消息队列,调用回调函数"""
        
        while True:
            response = self.queue.get()  # 阻塞等待消息
            buffer_time_observer.look()  # 记录缓冲出队时间
            try:
                if self.msg_ready_task and response:
                    self.msg_ready_task(response)
            except Exception as e:
                logger.exception(f"消息处理线程发生错误: {e}")
            finally:
                self.queue.task_done()

    # 消息从这里进入缓冲池,自动获得UTF标签
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

            if self._process_immediately(chat_stream, new_msg_key) >= BUFFER_NUM:
                # 立即处理消息
                print("提前处理")
                self._process_messages(chat_stream)
                return

            self._start_timer(chat_stream)

    # 设置3秒内没有新的消息，就进行消息合并开始下一步处理,自动执行_process_messages
    def _start_timer(self,chat_stream):
        timer = threading.Timer(3.0, self._process_messages, [chat_stream])
        timer.daemon = True
        timer.start()
        self.timers[chat_stream] = timer

    def _process_immediately(self,chat_stream,new_msg_key):
        """连续多条消息到达存储上限,则立即处理"""
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

        
        res = self.get_out_msg()
        if res:
            self.queue.put(res)
        

    def _delete_by_flag(self, chat_stream, flags=("F", "T")):
        """删除指定聊天流中匹配标记的消息。"""
        if chat_stream not in self.buffer_pool:
            return

        messages = self.buffer_pool[chat_stream]
        delete_keys = [k for k, v in messages.items() if v.Flag in flags]
        for key in delete_keys:
            messages.pop(key, None)

        # 删除空的聊天流
        if not messages:
            self.buffer_pool.pop(chat_stream, None)
    
    def get_out_msg(self):
        """整合消息,返回Response对象,清除TF标志数组"""
        response = Response()
        with self.lock:
            for chat_stream, buffer_pool in self.buffer_pool.items():
                
                # 如果没有T,就跳过这个聊天流
                if not any(cache_msg.Flag == "T" for cache_msg in buffer_pool.values()):
                    continue

                # 得到所有T,F标志的消息
                merged_items = [m for m in buffer_pool.values() if m.Flag in ("F", "T")]
                if not merged_items:
                    continue
                
                for item in merged_items:
                    response.add_msg(item.message)

                # 取走后清理本轮已消费消息
                self._delete_by_flag(chat_stream, flags=("T", "F"))
                return response
        return None



message_buffer = MessageBuffer()

def show(msgs):
    print(f"""
{[msgs[key].Flag for key in msgs.keys() ]}
    """)


if __name__ == "__main__":
    msg = FriendMsg({
        "name": "测试用户",
        "content": "这是一个测试消息",
    })
    for i in range(5):
        msgs = message_buffer.add_message_start_loop(msg)
        time.sleep(1)
        if msgs:
            print("触发处理")
            print(msgs["merged_content"])
