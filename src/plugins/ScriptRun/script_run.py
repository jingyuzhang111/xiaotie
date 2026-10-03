"""
跑工作区里的脚本

她自己写在工作区里的东西得能跑一下验证,不然写完只能猜对不对。
派给外包那个 agent 也能跑,但为跑个小脚本花 23k token 起步太亏。

边界到什么程度:脚本**必须放在工作区里**(路径走 FileOp 那套验过的校验),
cwd 也在工作区 —— 但这只是"让脚本落在看得见的地方",**不是沙箱**。
脚本内容里照样能 open('E:\\...') 写外面。跟给外包那个 agent 放行 python
是同一件事、同一个信任级别。
"""
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.config import (
    AI_WORKSPACE,
    COMMAND_OUTPUT_LIMIT,
    ENV_SECRET_PARTS,
    SCRIPT_TIMEOUT,
)
from src.logger import get_module_logger

logger = get_module_logger("script")


def _clean_env() -> dict[str, str]:
    """子进程不要看到密钥类的环境变量,否则一个 print(os.environ) 就漏了"""
    env = {
        key: value for key, value in os.environ.items()
        if not any(part in key.lower() for part in ENV_SECRET_PARTS)
    }
    # 让子进程直接吐 UTF-8,不然中文在 GBK 控制台里会变乱码
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _split_args(args: str) -> list[str]:
    """
    按 Windows 的规矩拆参数 —— 反斜杠**不是**转义符

    shlex 默认是 POSIX 模式,会把 E:\\a\\b 吃成 E:ab(实测踩过,小贴自己发现并
    写了个探针脚本验证的)。posix=False 不剥引号,所以自己补一步。
    """
    parts = shlex.split(args, posix=False)
    clean = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
            part = part[1:-1]
        clean.append(part)
    return clean


def run_script(script: str, args: str = "", timeout: float = SCRIPT_TIMEOUT) -> dict[str, Any]:
    """跑一个工作区里的 Python 脚本(相对路径,比如 scripts/check.py)"""
    from src.plugins.FileOp.fileops import resolve_in_workspace

    try:
        target = Path(resolve_in_workspace(script))
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    if not target.is_file():
        return {"ok": False, "error": f"没有这个脚本: {script}"}
    if target.suffix.lower() != ".py":
        return {"ok": False, "error": "只能跑 .py 脚本"}

    try:
        extra = _split_args(args or "")
    except ValueError as e:
        return {"ok": False, "error": f"参数没法解析: {e}"}

    timeout = max(1.0, min(timeout, SCRIPT_TIMEOUT * 4))
    logger.info(f"跑脚本 {target.name} 参数={extra} 超时={timeout:.0f}s")

    try:
        done = subprocess.run(
            [sys.executable, str(target), *extra],
            cwd=str(AI_WORKSPACE), env=_clean_env(),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"跑了 {timeout:.0f} 秒还没完,已经掐了",
                "script": script}
    except Exception as e:
        return {"ok": False, "error": f"起不来: {type(e).__name__}: {e}"}

    stdout = (done.stdout or "").strip()
    stderr = (done.stderr or "").strip()
    return {
        "ok": done.returncode == 0,
        "script": script,
        "exit_code": done.returncode,
        "stdout": stdout[:COMMAND_OUTPUT_LIMIT],
        "stderr": stderr[:COMMAND_OUTPUT_LIMIT],
        "truncated": len(stdout) > COMMAND_OUTPUT_LIMIT,
    }
