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

from src.config import (
    MEMORY_BUFFER_TTL,
    MEMORY_EDGE_TTL,
    MEMORY_NODE_MAX_ITEMS,
    MEMORY_SPREAD_DEPTH,
)
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

    node 可以是节点名字符串,也可以是节点的完整 json
    """
    if isinstance(node, str):
        node_data = db_memory_nodes.find_one({"name": node})
    elif isinstance(node, dict):
        node_data = db_memory_nodes.find_one({"name": node["name"]})
    else:
        logger.warning(f"get_node 收到无法识别的节点类型: {type(node)}")
        return None

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
        old_nodes = [n for n in self.nodes_buffer
                     if n.buffer_time < time.time() - MEMORY_BUFFER_TTL]
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
        """
        对边做 upsert 并累加权重
        """
        known = set(self.nodenames) | set(self.nodes_buffer_names)
        valid_keywords = [k for k in keywords if k in known]

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
            # 权重越高活得越久:提过 10 次的边能撑约 330 小时,只提过 1 次的只有 100 小时
            if edge.last_updated_time + MEMORY_EDGE_TTL*np.log(edge.weight*np.e) < time.time():
                _to_delete_edges.append(edge)
        for edge in _to_delete_edges:
            self.edges.remove(edge)
            db_memory_edges.delete_one({"source": edge.source, "target": edge.target})
            if self.G.has_edge(edge.source, edge.target):
                self.G.remove_edge(edge.source, edge.target)


        for node in self.nodes:
            if self.G.degree(node.name) == 0 and node.last_updated_time + MEMORY_EDGE_TTL < time.time():
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

        if not summary or not keywords:
            logger.warning("这次没总结出内容,跳过节点更新")
            return

        for keyword in keywords:
            if keyword in self.nodenames:
                # 已有节点:把这次的总结吸收进去
                self.absorb(keyword, summary)
                continue

            k:list = keywords.copy()
            k.remove(keyword)
            new_node = Node(name=keyword, content_array=[summary],related_nodes=k)
            self.should_promote_to_node(new_node)

        # 处理边
        self.update_edges(keywords)

        # 处理遗忘
        self.forget()


    def absorb(self, keyword: str, summary: str) -> None:
        """把这次的总结追加进已有节点,并刷新时间(重复内容只刷新时间)"""
        if not summary:
            return

        node = get_node(keyword)
        if node is None:
            logger.warning(f"节点 {keyword} 取不到,跳过吸收")
            return

        if summary in node.content_array:
            # 每次抽样都落在同一批消息上时,总结出来的话往往一字不差,
            # 存第二遍只会把提示词撑长
            node.update()               # 只刷新 last_updated_time
        else:
            node.content_array.append(summary)
            if len(node.content_array) > MEMORY_NODE_MAX_ITEMS:
                node.content_array = node.content_array[-MEMORY_NODE_MAX_ITEMS:]
            node.update()
            logger.info(f"节点 {keyword} 吸收了新记忆,现有 {len(node.content_array)} 条")

        self._sync_memory_node(keyword, node)


    def _sync_memory_node(self, keyword: str, node: Node) -> None:
        """
        把数据库里那份节点同步回内存里的对象

        absorb 走的是 get_node()(从数据库新读一份),
        而 self.nodes 里那个是启动时创建的**另一个对象**。
        不对齐的话,forget() 判过期用的是内存里那份旧数据,
        刚被提起的节点会被当成垃圾删掉。
        """
        for n in self.nodes:
            if n.name == keyword:
                n.content_array = list(node.content_array)
                n.last_updated_time = node.last_updated_time
                return


    def get_related_nodes(self, node_name, max_depth=3):
        """
        从 node_name 出发向外**逐层**扩散,返回经过的节点名
        返回顺序: 层号小的在前;同层内按边权重从大到小。
        """
        if node_name not in self.G:
            return []

        visited = {node_name}
        out = [node_name]           # 第 0 层:种子节点自己
        frontier = [node_name]

        for _ in range(max_depth):
            candidates: list[tuple[float, str]] = []
            for node in frontier:
                for neighbor in self.G.neighbors(node):
                    if neighbor in visited:
                        continue
                    weight = self.G.edges[node, neighbor].get("weight", 1)
                    candidates.append((weight, neighbor))

            if not candidates:
                break       # 扩散完了,提前收工

            # 同层内按权重降序 —— 关系紧的先被想起来
            candidates.sort(key=lambda item: -item[0])

            frontier = []
            for _, neighbor in candidates:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                out.append(neighbor)
                frontier.append(neighbor)

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


    def trigger_by_keywords(
        self, keywords: list[str], max_depth: int = MEMORY_SPREAD_DEPTH
    ) -> list[str]:
        """
        听到一些词 → 命中节点 → 以它为中心向外扩散 → 返回回忆到的文本
        """
        hits = [k for k in keywords if k in self.G]
        if not hits:
            return []

        collected: list[str] = []
        seen: set[str] = set()

        for hit in hits:
            nodes = self.get_related_nodes(hit, max_depth=max_depth)
            for text in self.get_related_memory(nodes):
                if text in seen:            # 同一个关键词扩散出来的会大量重叠
                    continue
                seen.add(text)
                collected.append(text)

        logger.info(
            f"记忆激活: 命中 {hits},扩散 {max_depth} 层,唤起 {len(collected)} 条"
        )
        return collected


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