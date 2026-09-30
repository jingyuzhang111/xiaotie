import os
from dotenv import load_dotenv

load_dotenv(".env")

BOT_NAME="小贴"


# 聊天平台，可选'host'与'weixin'
CHAT_PLAT="host"

DATABASE_NAME='xiaotie'

LLM_TEXT_URL=os.getenv('LLM_TEXT_URL')
LLM_TEXT_NAME=os.getenv('LLM_TEXT_NAME')
LLM_TEXT_KEY=os.getenv('LLM_TEXT_KEY')

LLM_EMOTION_URL=os.getenv('LLM_EMOTION_URL')
LLM_EMOTION_NAME=os.getenv('LLM_EMOTION_NAME')
LLM_EMOTION_KEY=os.getenv('LLM_EMOTION_KEY')



# 心情衰减率 兴趣衰减率
MOOD_DECAY_RATE=[0.9,0.8]
INTEREST_DECAY_RATE=[0.9,0.8]

MOOD_INFLUENCE_FACTOR=5  # 情感分析对心情值的影响因子

BUFFER_NUM = 10 # 缓冲池合并消息数的上限,超过则立即将消息送出队列


# ---------------- 疲惫值(疲劳/厌倦) ----------------
INTEREST_MAX = 100          # 兴趣值上限,mood.py 的 _clamp_values 里也是这个数
COMFORT_RATE = 0.2          # 舒适的消息密度(条/秒),约每 5 秒一条;低于它完全不累
FATIGUE_GAIN = 0.02         # 超出舒适区时,每条消息带来的疲惫增量系数
FATIGUE_RECOVER_TAU = 180   # 疲惫恢复时间常数(秒),安静时约 3 分钟消退 63%
DENSITY_MIN_SAMPLES = 3     # 估算密度所需的最少消息数,样本太少时不累(防冷启动)


# ---------------- 状态心跳 ----------------
STATE_TICK = 5              # 状态线程的 tick 间隔(秒)
                            # 各状态的衰减/恢复都用 exp(-Δt/τ),所以改这个值不会改变衰减曲线
REPLY_EAGERNESS_THRESHOLD = 0.5   # 发言意愿低于它就不主动接话
                                  # 注意:目前只打日志,尚未真正拦截消息