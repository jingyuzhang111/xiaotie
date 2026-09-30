from src.logger import get_module_logger

logger = get_module_logger("tools")

from dataclasses import dataclass
from typing import Any, Callable
from datetime import datetime
from src.config import *
from src.state_loop import state_snapshot

@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    read_only: bool = True
    exposed_to_agent: bool = True
    requires_confirmation: bool = False
    category: str = "general"


_TOOL_REGISTRY: dict[str, ToolSpec] = {}

## 注册工具到_TOOL_REGISTRY
def register_tool(
    name: str,
    description: str,
    read_only: bool = True,
    exposed_to_agent: bool = True,
    requires_confirmation: bool = False,
    category: str = "general",
):
    def decorator(func: Callable[..., Any]):
        _TOOL_REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            handler=func,
            read_only=read_only,
            exposed_to_agent=exposed_to_agent,
            requires_confirmation=requires_confirmation,
            category=category,
        )
        return func

    return decorator


def tools_init():
    logger.info("小贴正在获取tools...")

    @register_tool(
        name="get_chat_history",
        description="读取指定聊天流的最近历史对话。",
        category="memory",
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
        exposed_to_agent=False,
        category="memory",
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
        exposed_to_agent=False,
        category="memory",
    )
    def get_memory_at_time(timestamp: float) -> str | None:
        from src.memory.memory import memory_manager

        return memory_manager.get_time_content(timestamp)


    @register_tool(
        name="recall_memory",
        description="根据一个话题或记忆节点检索相关记忆。",
        category="memory",
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
        category="relationship",
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
        description="读取当前心情、兴趣、消息间隔(delta_msg)、空闲时长(delta_idle)、疲惫(fatigue)和发言意愿(eagerness)。",
        category="state",
    )
    def get_internal_state() -> dict[str, float]:
        # 状态的读取方式统一在 state_loop.state_snapshot 里,这里只管返回
        return state_snapshot()


    @register_tool(
        name="get_emotion_analysis",
        description="读取最近一次情绪分析结果。",
        category="state",
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
        category="system",
    )
    def get_current_time() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


    @register_tool(
        name="update_friend_relationship",
        description="小幅调整用户的好感度和熟悉度。只有在确实发生关系变化时使用。",
        read_only=False,
        exposed_to_agent=False,
        requires_confirmation=True,
        category="relationship",
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

    @register_tool(
        name="speak_text",
        description="使用当前语音角色朗读一段文本。",
        read_only=False,
        exposed_to_agent=False,
        requires_confirmation=True,
        category="audio",
    )
    def speak_text(text: str) -> dict[str, Any]:
        from src.plugins.ProcessAudio.readaudio import global_speaker

        if not text.strip():
            return {"spoken": False, "reason": "文本为空"}
        global_speaker.speak(text)
        return {"spoken": True}

    @register_tool(
        name="analyze_image",
        description="分析图片内容、情绪和适合的对话场景。",
        exposed_to_agent=False,
        requires_confirmation=True,
        category="image",
    )
    def analyze_image(image_path: str) -> str | None:
        from src.plugins.images.imgmanager import chat_stream as image_chat_stream
        from src.plugins.images.imgmanager import to_data_url

        image_url = to_data_url(image_path)
        return image_chat_stream(
            content="请分析这张图片，并返回结构化的图片描述。",
            img=image_url,
            sys_prompt="只描述看得见的内容，不要臆测。",
        )

    logger.info("已注册 {} 个工具，其中 {} 个向Agent公开", len(_TOOL_REGISTRY), len(list_tools()))
    return list_tools()


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "read_only": tool.read_only,
            "requires_confirmation": tool.requires_confirmation,
            "category": tool.category,
        }
        for tool in _TOOL_REGISTRY.values()
        if tool.exposed_to_agent
    ]

## 从_TOOL_REGISTRY中执行工具
def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool = _TOOL_REGISTRY.get(name)

    if tool is None:
        return {
            "success": False,
            "error": f"工具不存在: {name}",
        }

    if not tool.exposed_to_agent:
        return {
            "success": False,
            "tool": name,
            "error": "该工具是内部能力，不能由 Agent 直接调用",
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
    

