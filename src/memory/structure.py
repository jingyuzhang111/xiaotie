# 定义节点与边的数据结构
import time
from src.memory.memory import memory_manager, text_score
from src.mongodb import *
from src.LLM.client import call, SHAPE_JSON
from src.LLM.prompt import create_prompt_for_sum
import json
from typing import Any

import networkx as nx
import numpy as np

from src.logger import get_module_logger
logger = get_module_logger("memory-structure")



class Node:
    name: str
    related_nodes: list
    content_array: list
    created_time: float 
    last_updated_time: float

    buffer_time: float   # 记录节点被放入buffer的时间, 用于判断是否应该淘汰掉这个节点

    def __init__(self,
                 name: str = "",
                 related_nodes: list|None = None,
                 content_array: list|None = None,
                 created_time: float|None = None,
                 last_updated_time: float|None = None):
        self.name = name
        self.related_nodes = related_nodes if related_nodes is not None else []
        self.content_array = content_array if content_array is not None else []
        self.created_time = created_time if created_time is not None else time.time()
        self.last_updated_time = last_updated_time if last_updated_time is not None else time.time()
        self.buffer_time = time.time()

    def update(self):
        """更新节点"""
        self.last_updated_time = time.time()
        db_memory_nodes.update_one({"name": self.name}, {"$set":{"content_array": self.content_array,
                                                                "last_updated_time": self.last_updated_time}}
                                                        )

    def to_json(self):
        return {
            "content_array": self.content_array,
            "name": self.name,
            # "related_nodes": self.related_nodes,
            "created_time": self.created_time,
            "last_updated_time": self.last_updated_time
        }
    
    def to_db(self):
        db_memory_nodes.insert_one(self.to_json())

class Edge:
    source: str
    target: str
    weight: float
    created_time: float 
    last_updated_time: float

    def __init__(self, source: str, weight: float, target: str, 
                 created_time: float|None = None, 
                 last_updated_time: float|None = None):
        self.source, self.target = Edge.pair_sort(source, target)
        self.weight = weight
        self.created_time = created_time if created_time is not None else time.time()
        self.last_updated_time = last_updated_time if last_updated_time is not None else time.time()

    def update(self):
        """更新边"""
        self.last_updated_time = time.time()
        db_memory_edges.update_one({"source": self.source, "target": self.target}, {"$set":{"weight": self.weight,
                                                                    "last_updated_time": self.last_updated_time}}
                                                        )

    def to_json(self):
        return {
            "source": self.source,
            "target": self.target,
            "weight": self.weight,
            "created_time": self.created_time,
            "last_updated_time": self.last_updated_time
        }
    def to_db(self):
        db_memory_edges.insert_one(self.to_json())

    @classmethod
    def pair_sort(cls, source, target):
        """排序两个节点,保证唯一性"""
        if source == target:
            raise ValueError("不能连接自己")
        return tuple(sorted([source, target]))

def get_node(node):
    """
    从数据库获取节点
    node的类型:
        node名字字符串
        node完整json数据结构
    从0开始得到节点实例的右拐Node()
    """
    if isinstance(node, str):
        node_data = db_memory_nodes.find_one({"name": node})
    if isinstance(node, dict):
        node_data = db_memory_nodes.find_one({"name": node["name"]})
    
    if node_data:
        return Node(
            name=node_data["name"],
            content_array=node_data["content_array"],
            created_time=node_data["created_time"],
            last_updated_time=node_data["last_updated_time"]
        )
    return None

def get_edge(source, target):
    """数据库获取边对象"""
    source, target = Edge.pair_sort(source, target)
    edge_data = db_memory_edges.find_one({"source": source, "target": target})
    if edge_data:
        return Edge(
            source=edge_data["source"],
            target=edge_data["target"],
            weight=edge_data["weight"],
            created_time=edge_data["created_time"],
            last_updated_time=edge_data["last_updated_time"]
        )
    return None


class NetManager():

    def __init__(self):
        # 
        self.nodes: list[Node] = []         # 以Node类存储的节点列表
        self.nodes_buffer: list[Node] = []
        self.nodes_buffer_names: list[str] = []   # 只存节点名的buffer, 用于快速判断是否存在节点
        self.edges: list[Edge] = []
        self.nodenames: list[str] = []     # 只存已有的节点名
        self.G = nx.Graph()    
        self.init()

    def init(self):
        # 获取所有节点, 以node类存储在self.nodes中
        nodes = db_memory_nodes.find({})
        for node in nodes:
            n = get_node(node=node)
            if n:
                self.nodes.append(n)
            else:
                logger.warning(f"节点 {node} 获取失败")

        # 存储所有已有节点名
        for node_data in self.nodes:
            self.nodenames.append(node_data.name)
            self.G.add_node(node_data.name, content_array=node_data.content_array)

        logger.info(f"已有节点名: {self.nodenames}")

        # 获取所有边, 以edge类存储在self.edges中
        edges = db_memory_edges.find({})
        for edge in edges:
            e = get_edge(edge["source"], edge["target"])
            if e:
                self.edges.append(e)
                self.G.add_edge(e.source, e.target, weight=e.weight)
            else:
                logger.warning(f"边 {edge} 获取失败")


    def should_promote_to_node(self, node: Node):
        """
        判断是否应该将某条消息提升为节点, 并更新buffer
        由于这个函数是用来增加新节点的,所以理论上不需要对附带的边检查重复,因为节点是刚加的,不可能有与其相关的边
        """
        if node.name in self.nodenames:
            return
        
        # 提升为正式节点
        if node.name in self.nodes_buffer_names:
            logger.info(f"新节点添加: {node.name}")
            node.to_db()

            self.nodes_buffer_names.remove(node.name)

            # 不能直接remove,因为两个同名node是不同的对象, 只能通过名字找到原来的node对象再remove
            old_node = next((n for n in self.nodes_buffer if n.name == node.name), None)
            if old_node:
                self.nodes_buffer.remove(old_node)
            self.nodes.append(node)
            self.nodenames.append(node.name)
        else:
            logger.info(f"新节点候选: {node.name}")
            self.nodes_buffer.append(node)
            self.nodes_buffer_names.append(node.name)


        # 后处理,清除过期节点,防止内存爆了
        old_nodes = [n for n in self.nodes_buffer if n.buffer_time < time.time() - 36000]
        for old_node in old_nodes:
            logger.info(f"淘汰: {old_node.name}")
            if old_node.name in self.nodes_buffer_names:
                self.nodes_buffer_names.remove(old_node.name)
            if old_node in self.nodes_buffer:
                self.nodes_buffer.remove(old_node)


    def get_summary_and_keywords(self, string):
        """获取文本的摘要和关键词"""
        sys_prompt, user_prompt = create_prompt_for_sum(string)
        result = call(sys_prompt, user_prompt, profile="summarize", shape=SHAPE_JSON)
        if not result.ok or not isinstance(result.data, dict):
            logger.error(f"获取摘要和关键词失败: {result.error or result.data}")
            return {}
        return result.data


    def summarize_node(self):
        """对过去一段时间的消息文本进行随机抽样总结，并提取保存关键词"""

        # 获取时间正态分布的随机抽样
        msgs = memory_manager.get_memory_by_time()
        
        # 将抽样得到的消息内容拼接成一个字符串
        string = ""
        for msg in msgs:
            string = string + f"{msg['time']} {msg['name']}: {msg['content']}\n"
        print(f"""
=======================================================================
                    伟大的小贴正在进行大脑皮层的翻新
{string}
=======================================================================
""")

        # 喂给AI进行总结和关键词提取
        result: Any = self.get_summary_and_keywords(string)
        if not isinstance(result, dict):
            logger.error("记忆总结结果不是JSON对象: {}", result)
            return "", []

        if "summary" not in result or "keywords" not in result:
            logger.error("记忆总结结果缺少summary或keywords: {}", result)
            return "", []

        return result["summary"], result["keywords"]


    def update_edges(self, keywords):
        """对正式节点之间的边进行upsert并累加权重。"""

        # 过滤掉没用的关键词
        valid_keywords = [k for k in keywords if k in self.nodenames]

        # 遍历存在的关键词, 存储需要改动的边
        _to_change_edge = []
        for i in range(len(valid_keywords)):
            for j in range(i + 1, len(valid_keywords)):
                source, target = Edge.pair_sort(valid_keywords[i], valid_keywords[j])

                edge = get_edge(source, target)
                if edge is None:
                    edge = Edge(source=source, target=target, weight=1)
                    _to_change_edge.append(edge)
                else:
                    edge.weight += 1
                    _to_change_edge.append(edge)

        # 统一对边进行增删改
        for edge in _to_change_edge:
            if get_edge(edge.source, edge.target) is None:
                edge.to_db()
                self.edges.append(edge)
                logger.info(f"新建边 {edge.source} - {edge.target}，权重为 {edge.weight}")
            else:
                edge.update()
                found = False
                for e in self.edges:
                    if e.source == edge.source and e.target == edge.target:
                        e.weight = edge.weight
                        e.last_updated_time = edge.last_updated_time
                        found = True
                        break
                # 这个是用来解决意外的, 增强鲁棒性(
                if not found:
                    self.edges.append(edge)

                logger.info(f"边 {edge.source} - {edge.target} 权重更新为 {edge.weight}")

            self.G.add_edge(edge.source, edge.target, weight=edge.weight)



    def forget(self):
        _to_delete_edges = []
        _to_delete_nodes = []
        for edge in self.edges:
            if edge.last_updated_time + 360000*np.log(edge.weight*np.e) < time.time():
                _to_delete_edges.append(edge)
        for edge in _to_delete_edges:
            self.edges.remove(edge)
            db_memory_edges.delete_one({"source": edge.source, "target": edge.target})
            if self.G.has_edge(edge.source, edge.target):
                self.G.remove_edge(edge.source, edge.target)


        for node in self.nodes:
            if self.G.degree(node.name) == 0 and node.last_updated_time + 360000 < time.time():
                _to_delete_nodes.append(node)

        for node in _to_delete_nodes:
            self.nodenames.remove(node.name)
            self.nodes.remove(node)
            self.G.remove_node(node.name)
            db_memory_nodes.delete_one({"name": node.name})



    # 用于定时更新状态
    def memory_process(self):
        """记忆处理的主方法，所有方法都在这里集成
        回忆总结得到边和节点，更新边和节点，遗忘过期的边和节点
        """
        logger.info("进入记忆处理函数")

        # 进行一次回忆与总结
        summary, keywords = self.summarize_node()
        logger.info(f"""总结结果:{summary},\n关键词:{keywords}""")

        for keyword in keywords:
            if keyword not in self.nodenames:
                k:list = keywords.copy()
                k.remove(keyword)
                new_node = Node(name=keyword, content_array=[summary],related_nodes=k)
                self.should_promote_to_node(new_node)

        # 处理边
        self.update_edges(keywords)
                
        # 处理遗忘
        self.forget()


    def get_related_nodes(self, node_name, max_depth=3):
        """获取相邻节点"""

        if node_name not in self.G:
            return []
        
        # bfs算法
        visited = set()             # 记录已经走过的节点
        queue = [(node_name, 0)]    # 
        out = []
        while queue:
            node, d = queue.pop(0)
            if d >= max_depth:
                continue

            if node not in visited:
                visited.add(node)
                out.append(node)
            for neighbor in self.G.neighbors(node):

                if neighbor in visited:
                    continue

                queue.append((neighbor, d + 1))
        return out

    def get_related_memory(self, nodes_name):
        """根据相关节点获取相关记忆"""
        related_memory = []
        seen = set()
        # 这样能保证顺序不变,而第一条的权重应当最高
        for node_name in nodes_name:
            node = get_node(node_name)
            if not node:
                continue
            for text in node.content_array:
                if text in seen:
                    continue
                seen.add(text)
                related_memory.append(text)
        return related_memory


    # 用于触发回忆,通过关键词触发节点,最终得到记忆并进行整合
    def memory_trigger(self,node_name="测试"):
        nodes_name = self.get_related_nodes(node_name, max_depth=3)
        related_memory = self.get_related_memory(nodes_name)
        related_memory = list(set(related_memory))
        print(f"相关节点: {nodes_name}")
        print(related_memory)
        prumpt = "以下是你的回忆内容, 一般来说越靠前的回忆越重要,但相差不很大:\n"
        i= 1
        for memory in related_memory:
            prumpt = prumpt + f"第{i}条记忆:"+memory+"\n"
            i += 1
        logger.info(prumpt)


# 尝尝工厂模式的咸淡
_net_manager_instance = None

def get_net_manager():
    global _net_manager_instance
    if _net_manager_instance is None:
        _net_manager_instance = NetManager()
    return _net_manager_instance

net_manager = get_net_manager()


if __name__ == "__main__":
    text = "今天天气真好啊！我好开心！"
    important_words,words = text_score(text)

    net_manager = get_net_manager()

    ans: dict = net_manager.get_summary_and_keywords(text)
    # net_manager.memory_process()
    # net_manager.memory_process()
    # net_manager.memory_process()
    # net_manager.memory_process()
    logger.info(f"{ans["keywords"]}")
    logger.info(f"{net_manager.nodenames}")
    logger.info(f"{net_manager.G.edges(data=True)}")
    logger.info(f"{important_words}")
    for word in important_words:
        if word not in net_manager.nodenames:
            continue
        net_manager.memory_trigger(node_name=word)