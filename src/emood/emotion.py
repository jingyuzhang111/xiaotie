# 喜悦、悲伤、愤怒、恐惧、惊讶、厌恶（基于Paul Ekman的基本情感理论）。
"""
Plutchik的8种基本情感: 喜悦、信任、恐惧、惊讶、悲伤、厌恶、愤怒、期待。
喜悦 + 信任 = 爱
信任 + 恐惧 = 顺从
恐惧 + 惊讶 = 惊恐
惊讶 + 悲伤 = 失望
悲伤 + 厌恶 = 悔恨
厌恶 + 愤怒 = 蔑视
愤怒 + 期待 = 攻击性
期待 + 喜悦 = 乐观
"""

# complex_prompt = (f"""
# 基于Plutchik的情感轮理论分析以下文本的情感状态。
#
# Plutchik情感轮包含8种基本情感：
# - 喜悦 ↔ 悲伤
# - 愤怒 ↔ 恐惧
# - 惊讶 ↔ 期待
# - 厌恶 ↔ 信任
#
# 文本："{content}"
#
# 每种情感有三个强度层次：低、中、高。
# 复杂度也有三个层次：简单、普通、复杂
# 基本情感可以组合成更复杂的情感。
#
# 请严格按照以下JSON格式输出，不要添加任何其他内容：
# {{
#     "primary_emotions": {{
#         "喜悦": {{"score": 0, "intensity": "low"}},
#         "悲伤": {{"score": 0, "intensity": "low"}},
#         "愤怒": {{"score": 0, "intensity": "low"}},
#         "恐惧": {{"score": 0, "intensity": "low"}},
#         "惊讶": {{"score": 0, "intensity": "low"}},
#         "期待": {{"score": 0, "intensity": "low"}},
#         "厌恶": {{"score": 0, "intensity": "low"}},
#         "信任": {{"score": 0, "intensity": "low"}}
#     }},
#     "dominant_emotion": "情感名称",
#     "intensity_level": "low",
#     "combined_emotions": [],
#     "emotional_complexity": "简单"
# }}
#         """

import openai
import json
from typing import Dict,List,Tuple
import time
from src.mongodb import *
from openai.resources.containers.files import content
from src.emood.LLMrequest import analyze_many_parallel

from src.config import *
from src.globalcontrol import global_control
from src.logger import get_module_logger
logger = get_module_logger('emotion')

class EmotionManager():
    """
    LLM_get_emotion
    输入文本,输出情感分析结果
    """
    def __init__(self):
        self.history = []       # 分析的文本
        self.analyse = []       # 对基础情感的分析结果
        self.response_contents = []      # LLM分析的东西,json转字典,记录不同维度的情感强度
        self.combined_emotions = []     # 复合情感分析结果
        self.client = openai.OpenAI(
            api_key=LLM_EMOTION_KEY,
            base_url=LLM_EMOTION_URL,
        )
        self.emotions = [
            '喜悦','信任','恐惧','惊讶','悲伤','厌恶','愤怒','期待',
        ]
        self.intensity_levels = {
            "low":0.33,
            'medium':0.66,
            'high':1.0,
        }
        self.emotion_combinations = {
            ('喜悦', '信任' ): '爱',
            ('信任', '恐惧' ): '顺从',
            ('恐惧', '惊讶' ): '惊恐',
            ('惊讶', '悲伤' ): '失望',
            ('悲伤', '厌恶' ): '悔恨',
            ('厌恶', '愤怒' ): '蔑视',
            ('愤怒', '期待' ): '攻击性',
            ('期待', '喜悦' ): '乐观',
        }

    def LLM_get_emotion(self, content):
        if global_control.use_threadpool:
            result = analyze_many_parallel(content)
            for res in result["results"]:
                self.response_contents.append(result["results"][res])
            return
    
        sys_prompt = """
你是能够输出对其他人情感的机器, 你能够接收他人的消息,并输出那些消息让你感到的情感. 
你只输出JSON格式,不要增添要求之外的任何文本。情感分析基于Plutchik理论。尽量简短快速地给出分析结果,我赶时间
你收到的文本格式为: 
{
"人名1": "消息1",
"人名2": "消息2",
...
"总消息": "完整的对话上下文"
}
其中"人名"指某个人的话语,"总消息"是把所有消息不以人分类直接拼接在一起的文本。
你需要分析每个人的消息以及总消息,输出你读每段文本后的情感感受,以Plutchik理论为根据进行分析,并严格按照给定格式输出.
"""

        user_prompt = f"""
需要分析的文本如下：{json.dumps(content, ensure_ascii=False)}
请输出一个JSON数组,格式如下:
[{{
"name":"人名1",
"喜悦":0-10,"悲伤":0-10,"愤怒":0-10,"恐惧":0-10,
"惊讶":0-10,"期待":0-10,"厌恶":0-10,"信任":0-10,
"dominant":"情感","intensity":"low/medium/high",
}},
{{"name":"人名2",
"喜悦":0-10,"悲伤":0-10,"愤怒":0-10,"恐惧":0-10,
"惊讶":0-10,"期待":0-10,"厌恶":0-10,"信任":0-10,
"dominant":"情感","intensity":"low/medium/high",
}},
...
{{"name":"总消息",
"喜悦":0-10,"悲伤":0-10,"愤怒":0-10,"恐惧":0-10,
"惊讶":0-10,"期待":0-10,"厌恶":0-10,"信任":0-10,
"dominant":"情感","intensity":"low/medium/high",
"content":"你对这段文本的整体情感感受和理解,用一句话描述"}}
]
"""

        try:
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=LLM_EMOTION_NAME,  # 选择模型
                messages=[
                    {"role": "system",
                     "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            response_contents = response.choices[0].message.content.strip()
            llm_time = time.time() - start_time
            logger.debug(f"LLM推理耗时: {llm_time:.2f}s")

            self.response_contents =json.loads(response_contents)
            logger.info(self.response_contents)
        except Exception as e:
            logger.error(f'大模型不懂情感: {e}')
            self.response_contents = []




    def analyze_many(self):
        self.combined_emotions.clear()  # 清空之前的复合情感分析结果

        if self.response_contents is None:
            return

        for res in self.response_contents:
            emotions = self.emotion_analyze_basic(res)
            if emotions is None:
                logger.warning("情感分析失败")
                return
            positive,negative,neutral,total = emotions
            if res["name"] == "总消息":
                logger.info(f"整体情感分析结果 - 正面: {positive}, 负面: {negative}, 中性: {neutral}, 总体: {total}")
                self.mood_delta = (positive - negative) / MOOD_INFLUENCE_FACTOR
            self.combined_emotions.append(self.emotion_analyze_combined(res))


    def emotion_analyze_basic(self, response_content):
        """基本情感转为文本的描述语言"""


        analyse = {
            "key_insights": [],  # 初始化key_insights列表
            "overview": "",  # 情感概览
            "balance": "",   # 情感平衡度
        }
        # if not isinstance(response_content, dict):
        #     logger.error("response_content不是字典类型")
        #     return
        # 确保所有必要的情感键都存在
        for emotion in self.emotions + ["dominant", "intensity"]:
            if emotion not in response_content:
                response_content[emotion] = 0 if emotion in self.emotions else ""


        positive = response_content["喜悦"]+response_content["信任"]+response_content["期待"]
        negative = response_content["悲伤"]+response_content["愤怒"]+response_content["恐惧"]+response_content["厌恶"]
        neutral = response_content["惊讶"]
        total = positive+negative+neutral

        if positive > negative+5:
            analyse["overview"] = "积极情感主导"
        elif positive < negative-5:
            analyse["overview"] = "消极情感主导"
        else:
            analyse["overview"] = "情感相对平衡"


        balance_retio = abs(positive-negative)/total if total > 0 else 0
        if balance_retio < 0.2:
            analyse["balance"] = "高度平衡"
        elif balance_retio < 0.4:
            analyse["balance"] = "相对平衡"
        else:
            analyse["balance"] = "明显偏向"

        # 得到基本的文本描述
        if response_content["喜悦"] >= 7:
            analyse["key_insights"].append("用户处于较强的愉悦状态")
        if response_content["愤怒"] >= 6:
            analyse["key_insights"].append("检测到明显的愤怒情绪，需要谨慎处理")
        if response_content["恐惧"] >= 5:
            analyse["key_insights"].append("用户表现出担忧或不安")
        if response_content["信任"] <= 2:
            analyse["key_insights"].append("信任度较低，需要建立信任关系")

        self.analyse.append(analyse)

        return positive,negative,neutral,total


    def emotion_analyze_combined(self,response_content):
        """
        寻找复合情感,以下格式存储:
        [{
        "name": "爱",   # 复合情感名称
        "components": ["喜悦", "信任"],     # 复合情感的组成要素
        "intensity": 7,                     # 复合情感的强度（取组成要素中较弱的那个）
        "level": "强"                   # 强度等级(根据intensity划分为弱、中、强)
        }]
        
        """
        combined_emotions = []

        # 组合情感计算（基于阈值）
        emotion_combinations = {
            '爱': (('喜悦', '信任'), 5),  # 需要喜悦和信任都>=5, 以下同理
            '顺从': (('信任', '恐惧'), 4),
            '惊恐': (('恐惧', '惊讶'), 4),
            '失望': (('惊讶', '悲伤'), 4),
            '悔恨': (('悲伤', '厌恶'), 4),
            '蔑视': (('厌恶', '愤怒'), 4),
            '攻击性': (('愤怒', '期待'), 4),
            '乐观': (('期待', '喜悦'), 5)
        }

        for combined_name, ((emo1, emo2), threshold) in emotion_combinations.items():
            if response_content[emo1] >= threshold and response_content[emo2] >= threshold:
                intensity = min(response_content[emo1], response_content[emo2])

                combined_emotions.append({
                    "name": combined_name,
                    "components": [emo1, emo2],
                    "intensity": intensity,
                    "level": "强" if intensity >= 7 else "中" if intensity >= 5 else "弱"
                })

        if not combined_emotions:
            combined_emotions.append({
                "name": "无明显复合情感",
                "components": [],
                "intensity": 0,
                "level": "弱"
            })
        return combined_emotions


emotion_manager = EmotionManager()

if __name__ == '__main__':
    content = history_for_emo("小贴")
    content = {
        "小明": "我今天好开心啊！",
        "小红": "我感觉有点难过。",
        "小强": "两个傻逼",
        "总消息": "小明: 我今天好开心啊！\n小红: 我感觉有点难过。\n小强: 两个傻逼"
    }
    em = EmotionManager()
    em.LLM_get_emotion(content)
    em.analyze_many()
    logger.info(f"分析文本  为:{content}")
    logger.info(em.analyse)
    logger.info(f"复合情感分析结果: {em.combined_emotions}")





