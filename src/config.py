import os
from dotenv import load_dotenv

load_dotenv()

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
