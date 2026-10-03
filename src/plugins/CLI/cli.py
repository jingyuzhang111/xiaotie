"""
命令行操作

只读:整个电脑都能看。要写文件请用 plugins/FileOp —— 那边才限定工作区。
"""
import subprocess
from typing import Any

from src.config import (
    COMMAND_MAX_TIMEOUT,
    COMMAND_OUTPUT_LIMIT,
    COMMAND_TIMEOUT,
    CREDENTIAL_KEYWORDS,
    PROJECT_ROOT,
)
from src.logger import get_module_logger

logger = get_module_logger("cli")


# 只读白名单。set / path 这种能打印环境变量的绝不能进来 —— 里面就有 API Key
READONLY_COMMANDS = {
    "dir", "type", "where", "tasklist", "ipconfig", "systeminfo",
    "whoami", "hostname", "ver", "echo", "tree", "findstr", "more",
    "date", "time", "vol", "help", "attrib", "chkdsk",
}

# 连接符/重定向。不拦的话 `dir & del xxx` 首词照样是 dir
CONNECTOR_CHARS = ("&", "|", ";", ">", "<", "`", "\n", "\r")


def _decode(raw: bytes) -> str:
    """Windows 上 cmd 和 PowerShell 编码不统一,挨个试"""
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def run_command(command: str, timeout: float = COMMAND_TIMEOUT) -> dict[str, Any]:
    """执行一条只读命令(白名单 + 禁止连接符 + 不碰凭据文件)"""
    command = command.strip()
    if not command:
        return {"ok": False, "error": "空命令"}

    head = command.split()[0].lower()
    if head not in READONLY_COMMANDS:
        return {
            "ok": False,
            "error": f"`{head}` 不在只读白名单里,这个工具只能查看信息",
            "allowed": sorted(READONLY_COMMANDS),
        }

    for char in CONNECTOR_CHARS:
        if char in command:
            return {"ok": False, "error": f"不能出现 `{char}`,只接受单条简单命令"}

    lowered = command.lower()
    for word in CREDENTIAL_KEYWORDS:
        if word in lowered:
            return {"ok": False, "error": f"命令里出现了 `{word}`,涉及凭据的文件不读"}

    timeout = max(1.0, min(timeout, COMMAND_MAX_TIMEOUT))
    try:
        done = subprocess.run(command, shell=True, capture_output=True,
                              timeout=timeout, cwd=PROJECT_ROOT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"命令超过 {timeout} 秒还没结束,已中断"}
    except Exception as e:
        return {"ok": False, "error": f"执行失败: {e}"}

    stdout = _decode(done.stdout)
    stderr = _decode(done.stderr)
    return {
        "ok": done.returncode == 0,
        "exit_code": done.returncode,
        "stdout": stdout[:COMMAND_OUTPUT_LIMIT],
        "stderr": stderr[:COMMAND_OUTPUT_LIMIT],
        "truncated": len(stdout) > COMMAND_OUTPUT_LIMIT,
    }
