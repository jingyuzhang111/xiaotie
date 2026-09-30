import json
from typing import Any

from src.agent.state import state
from src.agent.tools import execute_tool, list_tools, tools_init
from src.LLM.client import call, SHAPE_JSON
from src.logger import get_module_logger

logger = get_module_logger("agent-desition")


def build_decision_prompt() -> tuple[str, str]:
    system_prompt = """你是一个Agent决策器。
你必须只输出JSON对象，不要输出Markdown、解释或代码块。
type只能是tool_call、final_answer或stop。
tool_call必须包含tool和arguments；final_answer必须包含content；stop可以包含reason。
"""

    user_prompt = json.dumps(
        {
            "goal": state.goal,
            "input": state.input_text,
            "iteration": state.iteration,
            "available_tools": list_tools(),
            "actions": state.actions,
            "observations": state.observations,
        },
        ensure_ascii=False,
    )
    return system_prompt, user_prompt


def request_decision() -> dict[str, Any] | None:
    system_prompt, user_prompt = build_decision_prompt()
    result = call(system_prompt, user_prompt, profile="decide", shape=SHAPE_JSON)
    if not result.ok:
        logger.error(f"Agent决策失败: {result.error}")
        return None
    if not isinstance(result.data, dict):
        logger.error(f"Agent决策结果不是JSON对象: {result.data}")
        return None
    return result.data


def handle_decision(decision: dict[str, Any]) -> None:
    decision_type = decision.get("type")

    if decision_type == "final_answer":
        state.final_answer = str(decision.get("content", ""))
        state.status = "completed"
        return

    if decision_type == "stop":
        state.status = "stopped"
        return

    if decision_type == "tool_call":
        tool_name = decision.get("tool")
        arguments = decision.get("arguments", {})
        if not isinstance(tool_name, str) or not isinstance(arguments, dict):
            state.status = "failed"
            logger.error("Agent工具决策格式错误: {}", decision)
            return

        result = execute_tool(tool_name, arguments)
        logger.debug("工具 {} 执行结果: {}", tool_name, result)
        state.actions.append(
            {
                "type": "tool_call",
                "tool": tool_name,
                "arguments": arguments,
            }
        )
        state.observations.append(result)
        return

    state.status = "failed"
    logger.error("Agent返回了未知决策类型: {}", decision_type)