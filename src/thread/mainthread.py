from src.thread.threadmanager import TaskWorker
from typing import Callable

class MainThread(TaskWorker):
    def __init__(self, target: Callable, interval_sec: int = 5):
        super().__init__(target, interval_sec)






