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

import json
from typing import Dict,List,Tuple

from src.LLM.client import call, SHAPE_JSON
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
    各个数据的格式:
    analyse:[{
        "name": 人名/总消息
        "key_insights": 对于积极/消极情感倾向的粗略概述
        "overview": 情感偏积极还是消极
        "balance": 情感稳定程度
    }...]
    response_contents:[{
        "name": 人名/总消息
        "喜悦": 0-10,
        ...
        "dominant": 主导情感名称
        "intensity":情感的程度
        "content":  对于这个人的话的情绪的概述
    }...]
    """
    def __init__(self):
        self.history = []       # 分析的文本
        self.analyse = []       # 对基础情感的分析结果
        self.response_contents = []      # LLM分析的东西,json转字典,记录不同维度的情感强度
        self.combined_emotions = []     # 复合情感分析结果
        self.mood_delta = {}            # 记录对不同人的好感度与熟悉程度
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
        # 全局设置，若选择使用线程池，则不再一次性输出多个人物的情感分析结果
        if global_control.use_threadpool:
            result = analyze_many_parallel(content)
            # 赋值而不是追加:追加会让上一轮的分析结果一直堆在这里
            self.response_contents = list(result["results"].values())
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

        # 档位 emotion_batch:一次分析多人,输出的是 JSON **数组**。
        # 这个档故意不开 force_json —— json_object 模式不接受数组。
        result = call(sys_prompt, user_prompt, profile="emotion_batch", shape=SHAPE_JSON)
        if not result.ok:
            logger.error(f'大模型不懂情感: {result.error}')
            self.response_contents = []
            return
        self.response_contents = result.data



    def analyze_many(self):
        """
        对LLM_get_emotion得到的结果进行分析,得到基础情感分析和复合情感分析

        处理self.response_contents的列表,一个元素就是一个人
        """
        self.combined_emotions.clear()  # 清空之前的复合情感分析结果
        self.mood_delta.clear()  # 清空之前的好感度/熟悉度变化记录
        self.analyse.clear()     # 之前漏了这句,它只会一直长长

        if self.response_contents is None:
            return

        for res in self.response_contents:
            emotions = self.emotion_analyze_basic(res)
            if emotions is None:
                logger.warning("情感分析失败")
                return
            positive,negative,neutral,total = emotions

            mood_delta = (positive - negative) / MOOD_INFLUENCE_FACTOR
            self.mood_delta[res["name"]] = mood_delta

            self.combined_emotions.append(self.emotion_analyze_combined(res))


    def emotion_analyze_basic(self, response_content):
        """基本情感转为文本的描述语言"""


        analyse = {
            "name": response_content.get("name", None),
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
            analyse["key_insights"].append("我感到愉悦状态")
        if response_content["愤怒"] >= 6:
            analyse["key_insights"].append("检测到明显的愤怒情绪，需要谨慎处理")
        if response_content["恐惧"] >= 5:
            analyse["key_insights"].append("我表现出担忧或不安")
        if response_content["信任"] <= 2:
            analyse["key_insights"].append("信任度较低，需要建立信任关系")

        self.analyse.append(analyse)

        return positive,negative,neutral,total


    def emotion_analyze_combined(self,response_content):
        """
        寻找复合情感,以下格式存储:
        [{
        "class": "爱",   # 复合情感名称
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
                    "name": response_content.get("name", None),
                    "class": combined_name,
                    "components": [emo1, emo2],
                    "intensity": intensity,
                    "level": "强" if intensity >= 7 else "中" if intensity >= 5 else "弱"
                })

        if not combined_emotions:
            combined_emotions.append({
                "name": response_content.get("name", None),
                "class": "",
                "components": [],
                "intensity": 0,
                "level": "弱"
            })
        return combined_emotions


emotion_manager = EmotionManager()


def _strong_dims(entry: dict, threshold: float = 4.0) -> str:
    """只挑明显不为零的维度;都没超阈值就退而报主导情感"""
    strong = [
        f"{dim}{entry.get(dim, 0):.0f}"
        for dim in emotion_manager.emotions
        if isinstance(entry.get(dim), (int, float)) and entry[dim] >= threshold
    ]
    if strong:
        return "、".join(strong)

    dominant = entry.get("dominant")
    return f"{dominant}（轻微）" if dominant else "没什么起伏"


def _combined_names(groups: list) -> str:
    """复合情感的名字,比 8 个数字具体"""
    names: list[str] = []
    for group in groups or []:
        for item in group or []:
            cls = item.get("class")
            if cls and cls not in names:
                names.append(cls)
    return "、".join(names)


def emotion_report(sender: str = "") -> str:
    """把这一轮的情绪分析压成给模型看的几句话"""
    contents = emotion_manager.response_contents or []
    if not contents:
        return ""

    lines: list[str] = []
    for entry in contents:
        name = entry.get("name")
        if sender and name == sender:
            lines.append(f"{sender}此刻的情绪：{_strong_dims(entry)}")
        elif name == "总消息":
            lines.append(f"这段对话的氛围：{_strong_dims(entry)}")

    combined = _combined_names(emotion_manager.combined_emotions)
    if combined:
        lines.append(f"更具体的感受：{combined}")

    return "\n".join(lines)

if __name__ == '__main__':
    content = history_for_emo("小贴")
    # 文本分析支持的字典输入格式：
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





