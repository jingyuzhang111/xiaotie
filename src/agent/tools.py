from src.logger import get_module_logger

logger = get_module_logger("tools")

from dataclasses import dataclass
from typing import Any, Callable
from datetime import datetime


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    read_only: bool = True


_TOOL_REGISTRY: dict[str, ToolSpec] = {}

## 注册工具到_TOOL_REGISTRY
def register_tool(
    name: str,
    description: str,
    read_only: bool = True,
):
    def decorator(func: Callable[..., Any]):
        _TOOL_REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            handler=func,
            read_only=read_only,
        )
        return func

    return decorator


def tools_init():
    logger.info("小贴正在获取tools...")

    @register_tool(
        name="get_chat_history",
        description="读取指定聊天流的最近历史对话。",
    )
    def get_chat_history(chat_stream: str, limit: int = 20) -> str:
        from src.memory.memory import memory_manager

        limit = max(1, min(limit, 50))
        return memory_manager.generate_history_dialog(
            chat_stream=chat_stream,
            limit=limit,
        )


    @register_tool(
        name="get_recent_memories",
        description="读取机器人最近保存的记忆。",
    )
    def get_recent_memories(limit: int = 20) -> list[dict[str, Any]]:
        from src.memory.memory import memory_manager

        limit = max(1, min(limit, 50))
        memories = memory_manager.get_resent_memory(limit=limit)
        return [
            {
                "name": memory.get("name"),
                "content": memory.get("content"),
                "time": memory.get("time"),
                "timestamp": memory.get("timestamp"),
                "chat_stream": memory.get("chat_stream"),
            }
            for memory in memories
        ]


    @register_tool(
        name="get_memory_at_time",
        description="根据时间戳读取一条历史记忆。",
    )
    def get_memory_at_time(timestamp: float) -> str | None:
        from src.memory.memory import memory_manager

        return memory_manager.get_time_content(timestamp)


    @register_tool(
        name="recall_related_memory",
        description="根据记忆节点名称，读取相关节点和关联记忆。",
    )
    def recall_related_memory(node_name: str, max_depth: int = 3) -> dict[str, Any]:
        from src.memory.structure import net_manager

        max_depth = max(1, min(max_depth, 5))
        nodes = net_manager.get_related_nodes(node_name, max_depth=max_depth)
        return {
            "nodes": nodes,
            "memories": net_manager.get_related_memory(nodes),
        }


    @register_tool(
        name="get_friend_profile",
        description="读取指定用户的好感度和熟悉度。",
    )
    def get_friend_profile(name: str) -> dict[str, Any] | None:
        from src.mongodb import db_friend

        friend = db_friend.find_one(
            {"name": name},
            {"_id": 0, "name": 1, "favor_ability": 1, "relationship_value": 1},
        )
        return friend


    @register_tool(
        name="get_internal_state",
        description="读取当前心情、兴趣和最近一次消息间隔。",
    )
    def get_internal_state() -> dict[str, float]:
        from src.emood.mood import moodupdater

        with moodupdater.mood_lock:
            return {
                "mood_value": moodupdater.mood_value,
                "interest_value": moodupdater.interest_value,
                "delta_time": moodupdater.delta_time,
            }


    @register_tool(
        name="get_emotion_analysis",
        description="读取最近一次情绪分析结果。",
    )
    def get_emotion_analysis() -> dict[str, Any]:
        from src.emood.emotion import emotion_manager

        return {
            "response_contents": emotion_manager.response_contents,
            "combined_emotions": emotion_manager.combined_emotions,
            "mood_delta": emotion_manager.mood_delta,
        }


    @register_tool(
        name="get_current_time",
        description="获取当前本地时间。",
    )
    def get_current_time() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


    @register_tool(
        name="update_friend_relationship",
        description="小幅调整用户的好感度和熟悉度。只有在确实发生关系变化时使用。",
        read_only=False,
    )
    def update_friend_relationship(
        name: str,
        favor_delta: float = 0.0,
        relationship_delta: float = 0.0,
    ) -> dict[str, Any] | None:
        from src.mongodb import update_friend

        favor_delta = max(-1.0, min(favor_delta, 1.0))
        relationship_delta = max(-1.0, min(relationship_delta, 1.0))
        result = update_friend(
            name,
            favor_delta=favor_delta,
            relationship_delta=relationship_delta,
        )
        if result is None:
            return None

        favor, relationship = result
        return {
            "name": name,
            "favor_ability": favor,
            "relationship_value": relationship,
        }

    logger.info("已注册 {} 个工具", len(_TOOL_REGISTRY))
    return list_tools()


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "read_only": tool.read_only,
        }
        for tool in _TOOL_REGISTRY.values()
    ]

## 从_TOOL_REGISTRY中执行工具
def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool = _TOOL_REGISTRY.get(name)

    if tool is None:
        return {
            "success": False,
            "error": f"工具不存在: {name}",
        }

    try:
        result = tool.handler(**arguments)
        return {
            "success": True,
            "tool": name,
            "result": result,
        }
    except Exception as error:
        return {
            "success": False,
            "tool": name,
            "error": str(error),
        }

if __name__ == "__main__":
    tools_init()
    logger.info(f"已注册工具: {list(_TOOL_REGISTRY.keys())}")
    

