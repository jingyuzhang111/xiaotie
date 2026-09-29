import json
from typing import Any

from src.globalcontrol import global_control
from src.agent.state import state
from src.agent.tools import execute_tool, list_tools, tools_init
from src.LLM.llm_manager import chat_stream
from src.agent.desition import request_decision, handle_decision

from src.logger import get_module_logger
logger = get_module_logger("agent-loop")


def _get_input_text(response: Any) -> str:
    if response is None:
        return ""
    if hasattr(response, "get_strings"):
        return response.get_strings()
    return str(response)


def _reset_state(response: Any, goal: str | None) -> None:
    state.input_text = _get_input_text(response)
    state.chat_stream = getattr(response, "chat_stream", None)
    state.goal = goal or state.input_text
    state.observations.clear()
    state.actions.clear()
    state.iteration = 0
    state.status = "running"
    state.final_answer = None




def main_loop(response=None, goal: str | None = None):
    """主循环"""
    if not global_control.want_thinking:
        return None

    tools_init()
    _reset_state(response, goal)

    while state.status == "running":
        if state.iteration >= state.max_iterations:
            state.status = "max_iterations"
            logger.warning("达到最大思考次数: {}", state.max_iterations)
            break

        state.iteration += 1
        decision = request_decision()
        if decision is None:
            state.status = "failed"
            break

        logger.debug("第{}轮Agent决策: {}", state.iteration, decision)
        handle_decision(decision)

    return state
    
if __name__ == "__main__":
    pass