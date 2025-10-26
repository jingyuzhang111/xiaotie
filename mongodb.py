from pymongo import MongoClient
from datetime import datetime
from config import *
from typing import Dict,Optional
import hashlib
import sys
import io
import json
from logger import get_module_logger
from msgbase import Msgbase

logger = get_module_logger("mongodb")
logger.info('Connecting to MongoDB...')

client = MongoClient('mongodb://localhost:27017/')

# 选择数据库和集合
db = client['xiaotie']
db_friend = db['friend']
db_messages = db["messages"]
def db_add(msg:Msgbase):
	"""
	data: dict,需要有键值content，name才行
	"""
	logger.debug(msg.value)
	db_messages.insert_one(msg.value)
	ensure_friend(msg.name)


def ensure_friend(name):
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


def update_friend(name:str,favor_delta=0.0,relationship_delta=0.0):
	"""更新好友信息"""
	friend = ensure_friend(name)
	new_favor = friend['favor_ability'] + favor_delta
	new_relationship = friend['relationship_value'] + relationship_delta
	db_friend.update_one(
		{"name": name},
		{"$set": {
			"favor_ability": new_favor,
			"relationship_value": new_relationship
		}}
	)
	return new_favor,new_relationship


def generate_history_dialog(chat_stream):
	history = db_messages.find({"chat_plat": CHAT_PLAT,
								"chat_stream": chat_stream})
	history_content = '\n'
	for post in history:
		one_piece = f"[{post['time']}] {post['name']}: {post['content']}\n"
		history_content += one_piece
	return history_content

def history_for_emo(name):
	"""获取所有群的所有某人的信息，将消息合并进行情感分析"""
	history = db_messages.find({"chat_plat": CHAT_PLAT,
								'name':name})
	history_content = ''
	for post in history:
		one_piece = f"{post["name"]}:{post['content']}"
		history_content += one_piece
		history_content += "\n"
	return history_content


if __name__ == "__main__":
	generate_history_dialog(0)

