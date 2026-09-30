"""
疲惫值(tired.py)离线校验

用假时钟模拟四种聊天节奏,看疲惫值和发言意愿怎么走。
不等待真实时间,不调 LLM,不连 MongoDB。

用法:
    .venv\\Scripts\\python.exe check_tired_timeline.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import src.emood.tired as tired
from src.config import COMFORT_RATE, FATIGUE_RECOVER_TAU
from src.observer import time_obsever

T0 = 2_000_000.0
FAKE_INTEREST = 60.0  # 固定兴趣值 60,方便观察意愿变化


class FakeClock:
    def __init__(self, t=T0):
        self.t = t

    def time(self):
        return self.t

    def advance(self, dt):
        self.t += dt


clock = FakeClock()


class FakeTimeModule:
    def time(self):
        return clock.time()


# 只替换 tired 模块内的 time
tired.time = FakeTimeModule()


class FakeResponse:
    """只提供 Msgs,update_in_msgloop 靠它的条数算"这批刷了多少" """

    def __init__(self, n):
        self.Msgs = [object()] * n


def reset():
    time_obsever.timelist.clear()
    clock.t = T0
    return tired.TiredUpdater()


def line(title):
    print()
    print("=" * 66)
    print(title)
    print("=" * 66)


def run_chat(u, msg_gap, batch_msgs, total_msgs):
    """
    按固定节奏模拟一段聊天

    msg_gap    : 每条消息之间的真实间隔(秒)  -> 决定密度
    batch_msgs : 多少条被缓冲合并成一批       -> 每批触发一次 update_in_msgloop
    """
    print(f"  每条间隔 {msg_gap}s -> 密度 {1 / msg_gap:.3f} 条/秒"
          f"(舒适线 {COMFORT_RATE}) | 每 {batch_msgs} 条合并成一批")
    print(f"  {'消息数':>7} {'rate':>8} {'fatigue':>9} {'eagerness':>11}")
    for i in range(1, total_msgs + 1):
        clock.advance(msg_gap)
        time_obsever.timelist.append(clock.time())
        if i % batch_msgs == 0:
            u.update_in_msgloop(FakeResponse(batch_msgs))
        if i % (batch_msgs * 2) == 0 or i == total_msgs:
            print(f"  {i:>7} {u.rate:>8.3f} {u.fatigue:>9.4f} "
                  f"{u.eagerness(FAKE_INTEREST):>11.4f}")


# ----------------------------------------------------------------------
line("1. 正常节奏:每 6 秒一条(密度 0.167 < 舒适线 0.2) -> 应该完全不累")
u = reset()
run_chat(u, msg_gap=6.0, batch_msgs=1, total_msgs=20)
print(f"  结论: fatigue={u.fatigue:.4f}  期望 0(低于舒适线不该累)")


# ----------------------------------------------------------------------
line("2. 稍微偏密:每 3 秒一条(密度 0.333,超出 67%) -> 应该缓慢上升")
u = reset()
run_chat(u, msg_gap=3.0, batch_msgs=1, total_msgs=30)


# ----------------------------------------------------------------------
line("3. 密集:每 1 秒一条(密度 1.0,超出 4 倍) -> 应该快速上升")
u = reset()
run_chat(u, msg_gap=1.0, batch_msgs=1, total_msgs=30)


# ----------------------------------------------------------------------
line("4. 刷屏:每 0.3 秒一条,且被合并成一批 11 条 -> 应该一批就接近满")
u = reset()
run_chat(u, msg_gap=0.3, batch_msgs=11, total_msgs=33)


# ----------------------------------------------------------------------
line("5. 刷屏后安静下来 -> 疲惫应随时间恢复(exp(-Δt/τ), τ=%.0fs)" % FATIGUE_RECOVER_TAU)
u = reset()
run_chat(u, msg_gap=0.3, batch_msgs=11, total_msgs=33)
print()
peak = u.fatigue
print(f"  峰值 fatigue = {peak:.4f}")
print(f"  {'安静(秒)':>9} {'fatigue':>10} {'eagerness':>11}")
for step in range(1, 13):  # 每步 60 秒,共 12 分钟
    clock.advance(60)
    u.update_in_timeloop()
    print(f"  {step * 60:>9} {u.fatigue:>10.4f} {u.eagerness(FAKE_INTEREST):>11.4f}")


# ----------------------------------------------------------------------
line("6. 回归:进程刚启动、样本太少时不累(防冷启动)")
u = reset()
time_obsever.timelist.append(clock.time())
cu = FakeResponse(1)
u.update_in_msgloop(cu)
print(f"  只有 1 条样本: rate={u.rate:.3f}  fatigue={u.fatigue:.4f}  期望 rate=0, fatigue=0")
