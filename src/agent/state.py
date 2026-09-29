from dataclasses import dataclass, field
from typing import Any

from src.logger import get_module_logger
logger = get_module_logger("agent-state")

@dataclass
class AgentState:
    input_text: str
    chat_stream: str | None = None

    goal: str = ""
    observations: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    # 循环思考次数
    iteration: int = 0
    max_iterations: int = 5
    status: str = "running"
    final_answer: str | None = None

state = AgentState(input_text="")
