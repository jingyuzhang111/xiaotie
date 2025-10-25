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
test = db['test']
db_messages = db["messages"]
def db_add(msg:Msgbase):
	"""
	data: dict,需要有键值content，name才行
	"""
	logger.debug(msg.value)
	db_messages.insert_one(msg.value)

def generate_history_dialog(chat_stream):
	history = db_messages.find({"chat_plat": CHAT_PLAT,
								"chat_stream": chat_stream})
	history_content = '\n'
	for post in history:
		one_piece = f"[{post['time']}] {post['name']}: {post['content']}\n"
		history_content += one_piece
	logger.debug(history_content)
	return history_content

if __name__ == "__main__":
	generate_history_dialog(0)