from src.logger import get_module_logger

logger = get_module_logger("tools")

import inspect
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
    parameters: dict[str, Any] | None = None


_TOOL_REGISTRY: dict[str, ToolSpec] = {}

## 注册工具到_TOOL_REGISTRY
def register_tool(
    name: str,
    description: str,
    read_only: bool = True,
    exposed_to_agent: bool = True,
    requires_confirmation: bool = False,
    category: str = "general",
    parameters: dict[str, Any] | None = None,
):
    """
    parameters: 参数的 JSON Schema。不传就从函数签名自动推导。
                只有需要给参数写语义说明时才手写。
    """
    def decorator(func: Callable[..., Any]):
        _TOOL_REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            handler=func,
            read_only=read_only,
            exposed_to_agent=exposed_to_agent,
            requires_confirmation=requires_confirmation,
            category=category,
            parameters=parameters,
        )
        return func

    return decorator


def tools_init():
    logger.info("小贴正在获取tools...")

    @register_tool(
        name="get_chat_history",
        description=(
            "读取跟**当前这个人**的更多历史对话。"
            "开场已经给过你最近的记录了,只有需要看更早的才用这个。"
        ),
        category="memory",
    )
    def get_chat_history(limit: int = 20) -> str:
        """读取当前会话更多的历史对话"""
        from src.agent.state import state
        from src.memory.memory import memory_manager

        if not state.chat_stream:
            return ""

        limit = max(1, min(limit, 50))
        return memory_manager.generate_history_dialog(
            chat_stream=state.chat_stream,
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
        description=(
            "顺着一个话题往外想，把相关的旧事都捞出来。"
            "开场已经自动想起过一批了，只在你觉得还不够、想再挖一挖的时候用。"
        ),
        category="memory",
    )
    def recall_related_memory(topic: str, max_depth: int = 2) -> dict[str, Any]:

        from src.memory.memory import hit_keywords
        from src.memory.structure import net_manager

        max_depth = max(1, min(max_depth, 4))
        hits = hit_keywords(topic, set(net_manager.nodenames))
        if not hits:
            return {"hits": [], "memories": [],
                    "note": f"脑子里没有跟「{topic}」对得上的印象"}

        return {
            "hits": hits,
            "memories": net_manager.trigger_by_keywords(hits, max_depth=max_depth),
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
        name="stay_silent",
        description=(
            "决定这次不说话。"
            "适合用:对方只发了个表情、一个没头没尾的字、明显在刷屏,或者你现在确实累了不想接话。"
            "不适合用:对方问了具体问题、说了重要的事、在向你求助,"
            "或者你刚好想到了有意思的话题 —— 这些情况即使有点累也应该回复。"
        ),
        read_only=True,
        category="social",
        # 这个参数需要语义说明,所以不走自动推导,手写一份覆盖它。
        # 自动推导只能给出 {"reason": {"type": "string"}},
        # 光看 "reason" 这个名字,模型不知道要写什么。
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "用第一人称简短说明你为什么不想说话,"
                        "比如'他只是在刷屏'、'我有点累了'"
                    ),
                },
            },
        },
    )
    def stay_silent(reason: str = "") -> dict[str, Any]:
        """不回复。reason 会进日志,方便回头看它每次沉默是为什么"""
        return {"silent": True, "reason": reason}


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

"""
schema: 描述工具需要什么参数来调用。
"""
def _schema_from_signature(handler: Callable[..., Any]) -> dict[str, Any]:
    """
    从函数的类型标注推导参数的 JSON Schema
    """
    json_types: dict[Any, str] = {
        str: "string", int: "integer", float: "number", bool: "boolean",
    }

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in inspect.signature(handler).parameters.items():
        if param_name in ("self", "cls"):
            continue

        properties[param_name] = {
            "type": json_types.get(param.annotation, "string"),
        }
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def agent_tool_schemas() -> list[dict[str, Any]]:
    """
    返回 OpenAI 原生 function calling 需要的 tools 参数:
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters or _schema_from_signature(tool.handler),
            },
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
    

