from dataclasses import dataclass, field
from typing import Any

from src.config import MAX_THINK_ROUNDS
from src.logger import get_module_logger
logger = get_module_logger("agent-state")


def _read_input_text(response: Any) -> str:
    """从各种形态的 response 里抠出纯文本"""
    if response is None:
        return ""
    if hasattr(response, "get_strings"):
        return response.get_strings()
    return str(response)


@dataclass
class ToolCallRecord:
    """一次工具执行的结果"""
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    ok: bool = True


@dataclass
class ThoughtStep:
    """
    思考链里的一圈

    一圈 = 一次 LLM 调用的产物:
        独白 + 前言(第一层自然语言) + 要调的工具(第二层结构化)
    """
    iteration: int
    reasoning: str = ""                              # 内心独白(reasoning_content)
    utterance: str = ""                              # 说出口的前言(content)
    calls: list[ToolCallRecord] = field(default_factory=list)


@dataclass
class AgentState:
    input_text: str = ""
    chat_stream: str | None = None
    sender_name: str = ""           # 正在说话的人(response.name)
    friend: dict[str, Any] | None = None   # 跟这个人的好感度/熟悉度

    goal: str = ""

    # desition.py 那条老路还在用这两个(保留着好回滚)
    observations: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    # 思考层用的整条思考链
    steps: list[ThoughtStep] = field(default_factory=list)

    iteration: int = 0
    max_iterations: int = MAX_THINK_ROUNDS
    status: str = "running"          # running / completed / silent / failed / max_iterations
    final_answer: str | None = None

    error: str = ""                  # 失败原因
    silent_reason: str = ""          # 主动沉默的理由

    def reset(self, response: Any = None, goal: str | None = None) -> None:
        """
        开新一轮思考前清空上一次的痕迹

        清空动作放在 state 自己身上,而不是散在调用方:
        以后加了新字段却忘了清,上一个用户的东西就会漏到下一个用户眼前,
        而且这种 bug 只在"连续两条消息"时出现,很难复现。
        """
        self.input_text = _read_input_text(response)
        self.chat_stream = getattr(response, "chat_stream", None)
        self.sender_name = getattr(response, "name", "") or ""
        self.friend = None
        self.goal = goal or self.input_text

        self.steps.clear()
        self.observations.clear()
        self.actions.clear()

        self.iteration = 0
        self.max_iterations = MAX_THINK_ROUNDS
        self.status = "running"
        self.final_answer = None
        self.error = ""
        self.silent_reason = ""

    @property
    def last_utterance(self) -> str:
        """最后一次说出口的话(轮数用尽时拿来兜底回复)"""
        for step in reversed(self.steps):
            if step.utterance:
                return step.utterance
        return ""


state = AgentState()
