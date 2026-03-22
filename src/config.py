# 用于搞配置，高级的咱不会(懒得学)，偷个懒直接py硬搞吧。

BOT_NAME="小贴"


# 聊天平台，可选'host'与'weixin'
CHAT_PLAT="host"

DATABASE_NAME='xiaotie'

LLM_TEXT_URL='https://api.siliconflow.cn/v1/'
LLM_TEXT_NAME="deepseek-ai/DeepSeek-V3.2-Exp"
LLM_TEXT_KEY='sk-uvsmlcbwngsfyrfusxebvlzageqpfpoatfgcasdvzbxmlgmk'

LLM_EMOTION_URL='https://api.siliconflow.cn/v1/'
LLM_EMOTION_NAME='deepseek-ai/DeepSeek-V3.2-Exp'
LLM_EMOTION_KEY='sk-uvsmlcbwngsfyrfusxebvlzageqpfpoatfgcasdvzbxmlgmk'



# 心情衰减率 兴趣衰减率
MOOD_DECAY_RATE=[0.9,0.8]
INTEREST_DECAY_RATE=[0.9,0.8]

MOOD_INFLUENCE_FACTOR=5  # 情感分析对心情值的影响因子
