"""
外包给别的 agent

为什么外包:
    要翻几十个文件、跑很多轮的重活会占死她的消息队列 —— 实测一条"翻 E 盘"的消息
    堵了 20 秒,期间真人发的消息只能排着。扔到另一条进程里跑,她就空出来了。

边界靠 cwd,不靠"只读":
    实测 --permission-mode acceptEdits 下,cwd 内能写、cwd 外被**拒绝**(不是挂起)。
    但 ~/.claude/settings.json 里有 additionalDirectories 和 Bash(pip install *)
    这类预授权,而 Bash 不受 cwd 约束 —— 所以要用 --setting-sources 不加载 user
    配置,凭据单独借(只借 env,不借 permissions)。

任务书走文件,不走命令行:
    claude 在 Windows 上是 .CMD,命令行要过 cmd.exe 的代码页,中文会烂掉。
    而且实测多行参数会被截断。所以命令行只给一句英文,真正的任务写进 TASK.md。

窗口:
    不弹 agent 自己的终端(那样我们就拿不到输出),而是我们解析 stream-json、
    把渲染好的人话追加进一个日志文件,再让一个常驻窗口 tail 它。
"""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from src.config import (
    AGENT_ALLOWED_TOOLS,
    AGENT_COMMAND,
    AGENT_RESULT_LIMIT,
    AGENT_THINK_NOTICE,
    AGENT_TIMEOUT,
    AGENT_WORKBENCH,
    AI_WORKSPACE,
    CREDENTIAL_KEYWORDS,
    PROJECT_ROOT,
)
from src.logger import get_module_logger

logger = get_module_logger("agent")

LIVE_LOG = Path(PROJECT_ROOT) / "logs" / "agent" / "live.log"
WORKBENCH_ROOT = Path(AI_WORKSPACE) / AGENT_WORKBENCH

# 命令行只给这一句(英文,避免代码页问题)。真正的任务在 TASK.md 里
PROMPT = ("Read TASK.md in the current directory and do exactly what it says. "
          "When you are done, describe the result in a few sentences. "
          "Do not paste file contents or large code blocks.")

_viewer: subprocess.Popen | None = None
_viewer_lock = threading.Lock()


def _clip(text: Any, limit: int = 160) -> str:
    """压成一行短文本"""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _agent_env() -> dict[str, str]:
    """
    只借凭据,不借权限

    直接把整个 settings.json 给它读的话,里面那些 Bash(pip install *)、
    additionalDirectories 会一起生效 —— 那圈工作区围墙就被绕过去了。
    """
    env = dict(os.environ)
    setting = Path.home() / ".claude" / "settings.json"
    try:
        env.update(json.loads(setting.read_text(encoding="utf-8")).get("env") or {})
    except Exception as e:
        logger.warning(f"读 {setting} 拿凭据失败,先按现有环境跑: {e}")
    return env


def _result_text(content: Any) -> str:
    """tool_result 的 content 可能是字符串,也可能是块数组"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return " ".join(parts)
    return str(content or "")


def _describe_call(name: str, params: dict) -> str:
    """把一次工具调用说成人话"""
    path = params.get("file_path") or params.get("notebook_path")
    if path:
        return f"{name} {path}"
    if name in ("Glob", "Grep"):
        return f"{name} {params.get('pattern') or ''} {params.get('path') or ''}".strip()
    if name == "Bash":
        return f"Bash: {_clip(params.get('command'), 120)}"
    flat = ", ".join(f"{k}={_clip(v, 40)}" for k, v in list(params.items())[:3])
    return f"{name} {flat}".strip()


# ------------------------------- 窗口 -------------------------------
def _write_log(text: str) -> None:
    """追加进窗口看的那份日志"""
    try:
        LIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LIVE_LOG, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception as e:
        logger.warning(f"写窗口日志失败: {e}")


def _open_viewer() -> None:
    """复用同一个窗口:已经开着就不再弹"""
    global _viewer
    with _viewer_lock:
        if _viewer is not None and _viewer.poll() is None:
            return
        try:
            # 日志是 UTF-8,不带 -Encoding 的话 PowerShell 会按系统 ANSI 代码页读,
            # 中文全变乱码
            _viewer = subprocess.Popen(
                ["powershell", "-NoExit", "-Command",
                 f"$Host.UI.RawUI.WindowTitle = '小贴的外包台'; "
                 f"Get-Content -LiteralPath '{LIVE_LOG}' -Wait -Encoding UTF8"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=str(PROJECT_ROOT),
            )
            logger.info(f"开了她的外包台窗口 → {LIVE_LOG}")
        except Exception as e:
            logger.warning(f"开窗口失败(不影响干活): {e}")


# ------------------------------- 干活 -------------------------------
def _new_workbench() -> Path:
    """一次外包一个干净的工作台"""
    path = WORKBENCH_ROOT / time.strftime("%Y%m%d-%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_brief(bench: Path, task: str, look_at: str = "") -> None:
    """任务书写进文件 —— 命令行过不了中文,而且多行会被 .cmd 截断"""
    extra = ""
    if look_at:
        extra = (f"- 需要翻看的东西在 `{look_at}`，可以读它\n"
                 f"- 但你只有查看的能力，**写不了任何文件**，包括这块工作目录\n")
    brief = (
        "# 你被派去干一件活\n\n"
        f"## 任务\n\n{task}\n\n"
        "## 规矩\n\n"
        "- 动笔改东西**只准在这块工作目录里**\n"
        f"{extra}"
        "- 需要的东西如果找不到,就直说找不到,不要猜也不要编\n"
        # 路径黑名单挡不住"给个上层目录",加一层提示词兜一下 ——
        # 实测它是会遵守这里写的规矩的
        "- **不要读任何涉及密钥/凭据的东西**"
        "(`.env`、`id_rsa`、`*.key`、`credentials`、`.ssh`、`.aws` 这一类),"
        "翻目录时碰到也别打开\n"
        "- 做完用几句话讲清结果,**不要贴大段代码或文件内容**\n"
    )
    (bench / "TASK.md").write_text(brief, encoding="utf-8")


def _render(evt: dict) -> list[str]:
    """一条 stream-json 事件 → 给人看的几行(没用就返回空)"""
    kind = evt.get("type")

    if kind == "system":
        if evt.get("subtype") == "init":
            return [f"会话开始  模型={evt.get('model')}  权限={evt.get('permissionMode')}"]
        return []

    if kind == "assistant":
        lines = []
        blocks = (evt.get("message") or {}).get("content") or []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and str(block.get("text") or "").strip():
                lines.append(f"  说： {_clip(block['text'], 200)}")
            elif block.get("type") == "tool_use":
                lines.append(f"  > {_describe_call(block.get('name') or '?',
                                                  block.get('input') or {})}")
        return lines

    if kind == "user":
        blocks = (evt.get("message") or {}).get("content") or []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return [f"    <- {_clip(_result_text(block.get('content')), 140)}"]
        return []

    if kind == "result":
        secs = (evt.get("duration_ms") or 0) / 1000
        usage = evt.get("usage") or {}
        # 不报 total_cost_usd:它按 Anthropic 价算,而这里跑的可能是别的模型
        tokens = (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
        lines = [
            f"--- 完了  {evt.get('num_turns')} 轮 / {secs:.0f} 秒 / "
            f"in {tokens / 1000:.1f}k out {usage.get('output_tokens') or 0} tok",
        ]
        denials = evt.get("permission_denials") or []
        if denials:
            lines.append(f"  ! 被挡下 {len(denials)} 次越界尝试")
        lines.append(f"  结果：{_clip(evt.get('result'), 1500)}")
        return lines

    return []


def _add_dir_args(look_at: str) -> tuple[list[str], str]:
    """
    要翻看的东西在哪个目录 → --add-dir 参数

    她自己能全盘读,所以这里也放开;但涉及凭据的目录不给 ——
    读出来的东西会进 agent 的上下文,等于发给服务商,和她的 read_file 同一个道理。

    ⚠️ --add-dir 进来的是**读+写**(实测),所以调用方拿到非空结果后
    必须配 --tools 锁成纯只读。
    """
    look_at = (look_at or "").strip().strip('"')
    if not look_at:
        return [], ""

    lowered = look_at.lower()
    for word in CREDENTIAL_KEYWORDS:
        if word in lowered:
            return [], f"`{look_at}` 涉及凭据,不给看"

    target = Path(look_at)
    if target.is_file():
        target = target.parent
    if not target.is_dir():
        return [], f"`{look_at}` 不是个目录,看不到"

    return ["--add-dir", str(target)], ""


def run_agent(task: str, look_at: str = "", timeout: float = AGENT_TIMEOUT) -> dict[str, Any]:
    """把一件活派出去。look_at 是要翻看的目录,留空就只在自己工作台里干"""
    task = (task or "").strip()
    if not task:
        return {"ok": False, "error": "没说要干什么"}

    agent = shutil.which(AGENT_COMMAND) or shutil.which(AGENT_COMMAND + ".cmd")
    if not agent:
        return {"ok": False, "error": f"这台电脑上找不到 {AGENT_COMMAND} 这个命令"}

    add_args, problem = _add_dir_args(look_at)
    if problem:
        return {"ok": False, "error": problem}

    bench = _new_workbench()
    _write_brief(bench, task, look_at)
    rel_bench = os.path.relpath(bench, PROJECT_ROOT)

    _open_viewer()
    _write_log(f"\n{'=' * 66}\n派活：{task}")
    if add_args:
        _write_log(f"可看：{add_args[-1]}")
    _write_log(f"工作台：{rel_bench}")

    cmd = [
        agent, "-p", PROMPT,
        "--setting-sources", "project,local",   # 不加载全局配置里的预授权
        "--permission-mode", "acceptEdits",     # 允许它在工作台里写
        "--output-format", "stream-json",
        "--verbose",
        *add_args,
    ]
    if add_args:
        # 要看外面时锁成纯只读。用 --tools 而不是 --allowedTools:
        # 实测 --allowedTools 是"自动允许"(放宽),没列进去的工具照样能用;
        # --tools 才是"可用工具集"(收紧)。用白名单,以后它新加的工具会自动排除
        cmd += ["--tools", "Read Glob Grep"]
    elif AGENT_ALLOWED_TOOLS:
        # 在自己工作台干活:额外放行 python,不然写了脚本也验证不了
        # ⚠️ 这是"信任"不是防线 —— python 能跑任意代码
        cmd += ["--allowedTools", AGENT_ALLOWED_TOOLS]

    try:
        proc = subprocess.Popen(
            cmd, cwd=str(bench), env=_agent_env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
    except Exception as e:
        return {"ok": False, "error": f"起不来: {type(e).__name__}: {e}"}

    # 读管道是阻塞的,用定时器到点杀进程把它踹开
    timed_out = threading.Event()

    def _kill():
        timed_out.set()
        try:
            proc.kill()
        except Exception:
            pass

    timer = threading.Timer(timeout, _kill)
    timer.daemon = True
    timer.start()

    answer = ""
    noticed = 0
    started = time.time()
    try:
        for raw in proc.stdout or []:
            raw = raw.strip()
            if not raw:
                continue
            try:
                evt = json.loads(raw)
            except Exception:
                continue

            if evt.get("subtype") == "thinking_tokens":
                total = evt.get("estimated_tokens") or 0
                if total - noticed >= AGENT_THINK_NOTICE:
                    noticed = total
                    _write_log(f"  … 正在想（约 {total} token）")
                continue

            for line in _render(evt):
                _write_log(line)

            if evt.get("type") == "result":
                answer = str(evt.get("result") or "").strip()
    finally:
        timer.cancel()
        try:
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    if timed_out.is_set():
        _write_log(f"⚠ 超过 {timeout:.0f} 秒,掐了")
        return {
            "ok": False,
            "error": f"超过 {timeout:.0f} 秒还没干完,被我掐了。干到一半的东西在 {rel_bench}",
        }

    if not answer:
        err = ""
        try:
            if proc.stderr is not None:
                err = (proc.stderr.read() or "").strip()[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"它没给出结果。{err or ''}".strip(),
                "workbench": rel_bench}

    produced = sorted(p.name for p in bench.iterdir() if p.name != "TASK.md")
    return {
        "ok": True,
        "answer": answer[:AGENT_RESULT_LIMIT],
        "workbench": rel_bench,
        "produced": produced,
        "seconds": round(time.time() - started),
    }
