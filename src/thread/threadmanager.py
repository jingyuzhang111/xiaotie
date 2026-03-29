import time
import threading
from typing import Callable

from src.logger import get_module_logger
logger = get_module_logger("threadmanager")



class TaskWorker:
    """
    接收一个函数,创建一个独立线程,专门管理这个函数的循环执行
    函数需要有定时执行的需求,比如定时整理记忆.

    start: 启动线程
    _loop: 线程内的循环函数
    stop: 设置线程停止的事件
    join:等待线程结束
    """
    def __init__(self, target: Callable,_args = None, _kwargs = None, interval_sec: int = 5):
        self.alive = False
        self.last_error = None
        self._args = () if _args is None else _args
        self._kwargs = {} if _kwargs is None else _kwargs
        self.target: Callable = target
        self.restart_count = 0
        self.interval_sec = interval_sec
        self.stop_event = threading.Event()     # 广播纪元( 通知所有线程下线?
        self.wait_for_stop = 2              # 线程报错后等待多久再重启,默认两秒

    def start(self):
        if self.alive:
            logger.warning("线程已开启.")
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.alive = True

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.target(*self._args, **self._kwargs)
                self.stop_event.wait(self.interval_sec)  # 等待指定时间或直到事件被设置
                self.restart_count = 0  # 成功执行一次后重置重启计数器
            except Exception as e:
                self.last_error = e
                self.restart_count += 1

                # 这里是加点延时,防止一次报错直接炸缸, 等两秒看看能不能自己复活
                self.stop_event.wait(self.wait_for_stop)
                logger.exception(f"Thread error: {e}, restarting... (restart count: {self.restart_count})")
            if self.restart_count > 5:
                logger.error("线程似透了喵")
                self.stop_event.set()  # 停止线程
                self.alive = False
        
        # 当线程退出时, 设置alive
        self.alive = False



    def stop(self):
        self.stop_event.set()  # 设置事件，通知线程停止

    def join(self, timeout = 5):
        if self.alive:
            try:
                self.thread.join(timeout=timeout)  # 等待线程结束
                if self.thread.is_alive():
                    logger.warning("线程未能在指定时间内停止.")
                self.restart_count = 0
                self.last_error = None
                self.stop_event.clear()  # 重置事件，以便下次使用
            except Exception as e:
                logger.error(f"关闭线程操作失败: {e}")



class ThreadManager:
    """管理线程"""

    def __init__(self):
        self.tasks: list[TaskWorker] = []
        self.n = 0      # 用于稀释检查频率


    def add_tasks(self, targets: list[Callable]|Callable, _args: tuple = (), _kwargs: dict = {}, interval_sec: int = 5):
        """添加线程"""
        if not isinstance(targets, list):
            targets = [targets]
        for target in targets:
            thread = TaskWorker(target=target, _args=_args, _kwargs=_kwargs, interval_sec=interval_sec)
            self.tasks.append(thread)

    def start(self):
        for task in self.tasks:
            if not task.alive:
                task.start()

    def restart(self):
        for task in self.tasks:
            if not task.alive:
                task.start()

    def is_alive(self):
        return any(task.alive for task in self.tasks)
    
    def check_in_handle_message(self):
        """在handle_message中调用,检查线程状态,如果都死了就重启"""
        self.n = self.n + 1
        if self.n > 10:
            self.restart()
            self.n = 0
            

    def stop_all(self):
        for task in self.tasks:
            task.stop()
        for task in self.tasks:
            task.join(timeout=5)  # 等待线程结束，设置超时时间防止死等

    def get_all_infos(self):
        infos = []
        for task in self.tasks:
            if getattr(task.target, '__qualname__', None):
                taskname = task.target.__qualname__
            elif getattr(task.target, '__name__', None):
                taskname = task.target.__name__
            else:
                try:
                    taskname = str(task.target)
                except Exception as e:
                    logger.error(f"获取任务名称失败: {e}")
                    taskname = "Unknown"
            info = {
                "name": taskname,
                "alive": task.alive,
                "last_error": str(task.last_error) if task.last_error else None,
                "restart_count": task.restart_count
            }
            infos.append(info)
        return infos

    def _add_one_task(self, target: Callable, _args: tuple = (), _kwargs: dict = {}, interval_sec: int = 5):
        """添加一个线程"""
        thread = TaskWorker(target=target, _args=_args, _kwargs=_kwargs, interval_sec=interval_sec)
        self.tasks.append(thread)
        thread.start()

    def __del__(self):
        self.stop_all()  # 确保在销毁时停止所有线程



_get_thread_manager = None
def get_thread_manager():
    global _get_thread_manager
    if _get_thread_manager is None:
        _get_thread_manager = ThreadManager()
    return _get_thread_manager

thread_manager = get_thread_manager()




