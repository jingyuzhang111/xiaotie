"""
后台任务

慢工具不阻塞思考:先等一小会儿,还没完就丢到后台,
完成后把结果当成一条消息送回原来那个聊天流,由正常链路处理。

为什么要"先等一小会儿":
    大部分只读命令一秒内就完了。给它们一个宽限期,
    能同步返回的就同步返回,不折腾;只有真的慢才转后台。
"""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Callable

from src.config import MAX_PENDING_TASKS
from src.logger import get_module_logger

logger = get_module_logger("tasks")

# 先等这么久,还没完就转后台
GRACE_SECONDS = 2.0

# 任务结果以谁的身份回到对话里
TASK_SENDER = "后台"


class _Task:
    def __init__(self, task_id: str, name: str, future, chat_stream: str, group_name: str):
        self.id = task_id
        self.name = name
        self.future = future
        self.chat_stream = chat_stream
        self.group_name = group_name


class TaskRegistry:
    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=4)
        self._pending: dict[str, _Task] = {}
        self._lock = threading.Lock()

    def run(
        self,
        name: str,
        func: Callable[..., Any],
        chat_stream: str = "",
        group_name: str = "",
        **kwargs: Any,
    ) -> tuple[bool, Any]:
        """
        跑一个可能很慢的函数

        返回 (是否已完成, 结果):
            宽限期内跑完 -> (True, 返回值)
            还在跑       -> (False, {"ok": True, "status": "..."})
        """
        # 硬止损:疲惫是软的、会恢复,套娃可能在几秒内连发好几轮,
        # 疲劳还没积累够就堆了一堆进程
        if self.pending_count() >= MAX_PENDING_TASKS:
            return False, {
                "ok": False,
                "error": f"后台已经有 {self.pending_count()} 个活没跑完,先等它们出来再说",
            }

        future = self._pool.submit(func, **kwargs)
        try:
            return True, future.result(timeout=GRACE_SECONDS)
        except TimeoutError:
            pass

        task_id = uuid.uuid4().hex[:6]
        task = _Task(task_id, name, future, chat_stream, group_name)
        with self._lock:
            self._pending[task_id] = task

        # 起一条线程盯到它跑完
        threading.Thread(target=self._wait_and_deliver, args=(task,), daemon=True).start()

        logger.info(f"任务 {task_id}({name}) 超过 {GRACE_SECONDS} 秒,转后台继续跑")
        return False, {
            "ok": True,
            "status": f"这个查起来有点慢,已经放到后台了(任务号 {task_id})。"
                      f"你可以先干别的,结果出来我会告诉你。",
        }

    def _wait_and_deliver(self, task: _Task) -> None:
        try:
            result = task.future.result()
        except Exception as e:
            result = {"ok": False, "error": str(e)}

        with self._lock:
            self._pending.pop(task.id, None)

        self._deliver(task, result)

    def _deliver(self, task: _Task, result: Any) -> None:
        """把结果当成一条消息送回原来那个聊天流"""
        text = _format(result)

        # 延迟导入:messagebuffer 在导入时会创建实例,放在模块顶部容易卷进循环导入
        from src.msgbase import FriendMsg
        from src.messagebuffer import message_buffer

        msg = FriendMsg({
            "name": TASK_SENDER,
            "content": f"你先前让我查的「{task.name}」有结果了。\n{text}",
            "chat_stream": task.chat_stream,
            "group_name": task.group_name,
        })
        message_buffer.add_message_start_loop(msg)
        logger.info(f"任务 {task.id}({task.name}) 完成,结果已送回对话")

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)


def _format(result: Any) -> str:
    """把工具返回值压成一段给人看的文字"""
    if not isinstance(result, dict):
        return str(result)

    if not result.get("ok", True):
        return f"没成,出错了:{result.get('error', '原因不明')}"

    # 主要内容:不同的工具叫法不一样(dir 给 stdout,外包给 answer)
    body = ""
    for key in ("answer", "stdout", "text"):
        if result.get(key):
            body = str(result[key]).strip()
            break

    if result.get("truncated"):
        body += "\n(输出太长,截断了一部分)"
    err = str(result.get("stderr") or "").strip()
    if err:
        body += f"\n(还有错误输出:{err[:300]})"

    # 剩下的短字段当补充信息(比如工作台在哪、产出了什么)
    extras = []
    for key, value in result.items():
        if key in ("ok", "answer", "stdout", "stderr", "text", "truncated"):
            continue
        if isinstance(value, list):
            if value:
                extras.append(f"{key}: {'、'.join(str(v) for v in value)}")
        elif isinstance(value, (str, int, float)) and str(value).strip():
            extras.append(f"{key}: {value}")
    if extras:
        body += "\n(" + "; ".join(extras) + ")"

    return body or "(跑完了,但什么都没有输出)"


tasks = TaskRegistry()
