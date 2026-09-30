from pymongo import MongoClient
from datetime import datetime
from src.config import *
from typing import Dict,Optional
import hashlib
import sys
import io
import json
from src.logger import get_module_logger
from src.msgbase import Msgbase, FriendMsg

logger = get_module_logger("mongodb")
logger.info('Connecting to MongoDB...')

client = MongoClient('mongodb://localhost:27017/')

# 选择数据库和集合
db = client['xiaotie']
db_friend = db['friend']
db_messages = db["messages"]
db_memory_nodes = db["memory_nodes"]
db_memory_edges = db["memory_edges"]
def db_add(msg:Msgbase|dict):
	"""
	data: dict,需要有键值content，name才行
	"""
	# 使用字符串类型检查，避免循环导入问题
	if isinstance(msg, dict):
		msg = Msgbase(msg)

	logger.debug(msg.value)
	db_messages.insert_one(msg.value)
	logger.info(f"消息已存入数据库, 来自:{msg.name}")
	ensure_friend(msg.name)


def ensure_friend(name):
	"""确保数据库中有这个人的信息，没有就创建"""
	friend = db_friend.find_one({"name":name})
	if not friend:
		friend = {
			"name":name,
			"favor_ability":10 if name=="self" else 0,
			"relationship_value":0,
			"chat_plat":CHAT_PLAT,
		}
		db_friend.insert_one(friend)
	friend = db_friend.find_one({"name": name})
	return friend


def get_friend(name: str):
	"""读取好友信息,没有就返回 None(不创建)"""
	return db_friend.find_one({"name": name})


def update_friend(name:str,favor_delta=0.0,relationship_delta=0.0):
	"""更新好友信息"""
	friend = ensure_friend(name)
	if not friend:
		logger.error(f"无法找到好友{name}的信息")
		return None
	new_favor = friend['favor_ability'] + favor_delta
	new_relationship = friend['relationship_value'] + relationship_delta

	new_favor,new_relationship = clamp_values(new_favor,new_relationship)

	db_friend.update_one(
		{"name": name},
		{"$set": {
			"favor_ability": new_favor,
			"relationship_value": new_relationship
		}}
	)
	return new_favor,new_relationship


def clamp_values(favor,relationship):
	"""限制好感度和关系值在一定范围内"""
	favor = max(-10, min(10, favor))
	relationship = max(0, min(100, relationship))
	return favor, relationship


def history_for_emo(name):
	"""获取所有群的所有某人的信息，将消息合并进行情感分析"""
	history = db_messages.find({"chat_plat": CHAT_PLAT,
								'name':name})
	history_content = ''
	for post in history:
		one_piece = f"{post['name']}:{post['content']}"
		history_content += one_piece
		history_content += "\n"
	return history_content



if __name__ == "__main__":
	msg = FriendMsg({
		"name": "测试用户",
		"content": "这是一个测试消息",
		"group_name": "测试群组",
	})
	db_add(msg)
	pass

