# 喜悦、悲伤、愤怒、恐惧、惊讶、厌恶（基于Paul Ekman的基本情感理论）。
"""
Plutchik的8种基本情感：喜悦、信任、恐惧、惊讶、悲伤、厌恶、愤怒、期待。
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
from mongodb import *
from openai.resources.containers.files import content

from config import *
from logger import get_module_logger

logger = get_module_logger('emotion')

class EmotionManager():
    def __init__(self):
        self.history = []
        self.analyse = {}
        self.response_content = {}
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
        prompt = f"""分析文本情感，输出JSON: {{
"喜悦":0-10,"悲伤":0-10,"愤怒":0-10,"恐惧":0-10,
"惊讶":0-10,"期待":0-10,"厌恶":0-10,"信任":0-10,
"dominant":"情感","intensity":"low/medium/high"
}}
文本：{content}"""

        try:
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=LLM_EMOTION_NAME,  # 选择模型
                messages=[
                    {"role": "system",
                     "content": "你只输出JSON，不解释。情感基于Plutchik理论。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            response_content = response.choices[0].message.content.strip()
            llm_time = time.time() - start_time
            logger.debug(f"LLM推理耗时: {llm_time:.2f}s")

            self.response_content =json.loads(response_content)
            logger.info(self.response_content)
        except Exception as e:
            logger.error(f'大模型不懂情感: {e}')
            self.response_content = {
              "喜悦": 0,
              "悲伤": 0,
              "愤怒": 0,
              "恐惧": 0,
              "惊讶": 0,
              "期待": 0,
              "厌恶": 0,
              "信任": 0,
              "dominant": "",
              "intensity": ""
            }


    def emotion_analyze_basic(self):
        self.analyse = {
            "key_insights": []  # 初始化key_insights列表
        }
        if not isinstance(self.response_content, dict):
            logger.error("response_content不是字典类型")
            return
        # 确保所有必要的情感键都存在
        for emotion in self.emotions + ["dominant", "intensity"]:
            if emotion not in self.response_content:
                self.response_content[emotion] = 0 if emotion in self.emotions else ""


        positive = self.response_content["喜悦"]+self.response_content["信任"]+self.response_content["期待"]
        negative = self.response_content["悲伤"]+self.response_content["愤怒"]+self.response_content["恐惧"]+self.response_content["厌恶"]
        neutral = self.response_content["惊讶"]
        total = positive+negative+neutral

        if positive > negative+5:
            self.analyse["overview"] = "积极情感主导"
        elif positive < negative-5:
            self.analyse["overview"] = "消极情感主导"
        else:
            self.analyse["overview"] = "情感相对平衡"


        balance_retio = abs(positive-negative)/total if total > 0 else 0
        if balance_retio < 0.2:
            self.analyse["balance"] = "高度平衡"
        elif balance_retio < 0.4:
            self.analyse["balance"] = "相对平衡"
        else:
            self.analyse["balance"] = "明显偏向"

        # 关键洞察
        if self.response_content["喜悦"] >= 7:
            self.analyse["key_insights"].append("用户处于较强的愉悦状态")
        if self.response_content["愤怒"] >= 6:
            self.analyse["key_insights"].append("检测到明显的愤怒情绪，需要谨慎处理")
        if self.response_content["恐惧"] >= 5:
            self.analyse["key_insights"].append("用户表现出担忧或不安")
        if self.response_content["信任"] <= 2:
            self.analyse["key_insights"].append("信任度较低，需要建立信任关系")

        return positive,negative,neutral,total

    def emotion_analyze_combined(self):
        combined_emotions = []

        # 组合情感计算（基于阈值）
        emotion_combinations = {
            '爱': (('喜悦', '信任'), 5),  # 需要喜悦和信任都>=5
            '顺从': (('信任', '恐惧'), 4),
            '惊恐': (('恐惧', '惊讶'), 4),
            '失望': (('惊讶', '悲伤'), 4),
            '悔恨': (('悲伤', '厌恶'), 4),
            '蔑视': (('厌恶', '愤怒'), 4),
            '攻击性': (('愤怒', '期待'), 4),
            '乐观': (('期待', '喜悦'), 5)
        }

        for combined_name, ((emo1, emo2), threshold) in emotion_combinations.items():
            if self.response_content[emo1] >= threshold and self.response_content[emo2] >= threshold:
                intensity = min(self.response_content[emo1], self.response_content[emo2])

                combined_emotions.append({
                    "name": combined_name,
                    "components": [emo1, emo2],
                    "intensity": intensity,
                    "level": "强" if intensity >= 7 else "中" if intensity >= 5 else "弱"
                })

        return combined_emotions


emotion_manager = EmotionManager()

if __name__ == '__main__':
    content = history_for_emo("小贴")
    shot_content = "你好呀！"
    em = EmotionManager()
    em.LLM_get_emotion(shot_content)
    em.emotion_analyze_basic()
    logger.info(f"分析文本为:{shot_content}")
    logger.info(em.analyse)

    temp = em.emotion_analyze_combined()
    for emotion in temp:
        logger.info(emotion)