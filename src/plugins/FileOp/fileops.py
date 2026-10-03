"""
文件操作

读:整个电脑都能看(凭据文件除外)。
写/删:只能在她的工作区里 —— 放脚本、笔记、自己写的 skill、干活的结果。

路径校验不能靠 startswith,也不能靠查 "..":
    startswith(工作区) 会放过 workspace_AI_evil(前缀撞名)
    查 ".."            会放过指向外面的符号链接/junction
两者都得先 realpath,再按**路径分量**比。
"""
import os
import shutil
from typing import Any

from src.config import (
    AI_WORKSPACE,
    CREDENTIAL_KEYWORDS,
    FILE_LIST_LIMIT,
    FILE_READ_LIMIT,
    FILE_WRITE_LIMIT,
)
from src.logger import get_module_logger

logger = get_module_logger("fileops")


def _decode(raw: bytes) -> str:
    """Windows 上文本编码不统一,挨个试"""
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _root() -> str:
    return os.path.realpath(AI_WORKSPACE)


def resolve_in_workspace(path: str) -> str:
    """写/删/跑脚本:解析成绝对路径,并确保落在工作区里;不通过就抛"""
    raw = (path or "").strip().strip('"')
    if not raw:
        raise ValueError("路径不能为空")

    # \\?\ 前缀会让 realpath 停止规范化,直接绕过下面所有检查
    if raw.startswith("\\\\"):
        raise ValueError("不支持 UNC 或 \\\\?\\ 这种路径")

    root = _root()
    target = os.path.realpath(os.path.join(root, raw))

    # commonpath 按路径分量比:C:\a\ws 和 C:\a\ws_evil 的公共部分是 C:\a。
    # 不同盘符时它会直接抛异常,包成"不在里面"
    try:
        inside = os.path.commonpath(
            [os.path.normcase(root), os.path.normcase(target)]
        ) == os.path.normcase(root)
    except ValueError:
        inside = False

    if not inside:
        raise ValueError("只能在自己的工作区里动")
    if os.path.normcase(target) == os.path.normcase(root):
        raise ValueError("这是工作区本身,不能整个写掉或删掉")
    return target


def resolve_readable(path: str) -> str:
    """读:整个电脑都能看,相对路径按工作区算。看图那边复用同一个规矩"""
    raw = (path or "").strip().strip('"')
    if not raw:
        raise ValueError("路径不能为空")

    lowered = raw.lower()
    for word in CREDENTIAL_KEYWORDS:
        if word in lowered:
            raise ValueError(f"路径里有 `{word}`,涉及凭据的文件不读")

    target = raw if os.path.isabs(raw) else os.path.join(AI_WORKSPACE, raw)
    return os.path.realpath(target)


def _shown(path: str) -> str:
    """工作区内显示成相对路径,看着像个自己的地盘"""
    try:
        return os.path.relpath(path, _root())
    except ValueError:
        return path


def list_files(path: str = ".") -> dict[str, Any]:
    """列目录内容"""
    try:
        target = resolve_readable(path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    if not os.path.isdir(target):
        return {"ok": False, "error": f"{path} 不是目录"}

    entries: list[dict[str, Any]] = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                entries.append({
                    "name": entry.name,
                    "dir": entry.is_dir(),
                    "size": size,
                })
    except Exception as e:
        return {"ok": False, "error": f"读目录失败: {e}"}

    entries.sort(key=lambda item: (not item["dir"], item["name"].lower()))
    return {
        "ok": True,
        "path": target,
        "count": len(entries),
        "entries": entries[:FILE_LIST_LIMIT],
        "truncated": len(entries) > FILE_LIST_LIMIT,
    }


def read_file(path: str, offset: int = 0, max_chars: int = FILE_READ_LIMIT) -> dict[str, Any]:
    """读一个文本文件。文件长的用 offset 接着往下读"""
    try:
        target = resolve_readable(path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    if os.path.isdir(target):
        return {"ok": False, "error": f"{path} 是目录,要看里面有什么请用 list_files"}
    if not os.path.isfile(target):
        return {"ok": False, "error": f"没有这个文件: {path}"}

    try:
        with open(target, "rb") as f:
            raw = f.read()
    except Exception as e:
        return {"ok": False, "error": f"读不了: {e}"}

    text = _decode(raw)
    start = max(0, int(offset))
    limit = max(200, min(int(max_chars), FILE_READ_LIMIT))
    chunk = text[start:start + limit]
    return {
        "ok": True,
        "path": target,
        "size": len(raw),
        "offset": start,
        "content": chunk,
        "truncated": start + limit < len(text),
        "next_offset": start + limit if start + limit < len(text) else None,
    }


def write_file(path: str, content: str, append: bool = False) -> dict[str, Any]:
    """写文件。父目录会自动建;append=false 是整份替换"""
    try:
        target = resolve_in_workspace(path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    if os.path.isdir(target):
        return {"ok": False, "error": f"{path} 是个目录,不能当文件写"}

    data = content or ""
    if len(data) > FILE_WRITE_LIMIT:
        return {
            "ok": False,
            "error": f"内容太长({len(data)} 字),一次最多 {FILE_WRITE_LIMIT} 字",
        }

    existed = os.path.exists(target)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        # newline="" 关掉换行符转换:否则写进去的 \n 变 \r\n,
        # 读回来再写一次就变成 \r\r\n,来回几趟文件就烂了
        with open(target, "a" if append else "w",
                  encoding="utf-8", newline="") as f:
            f.write(data)
    except Exception as e:
        return {"ok": False, "error": f"写不进去: {e}"}

    mode = "追加" if append else "覆盖"
    logger.info(f"{mode} {_shown(target)} ({len(data)} 字)")
    return {
        "ok": True,
        "path": _shown(target),
        "mode": mode,
        "existed": existed,
        "chars": len(data),
    }


def delete_path(path: str, recursive: bool = False) -> dict[str, Any]:
    """删文件或目录。目录默认只能删空的,要连内容一起删得把 recursive 设为 true"""
    try:
        target = resolve_in_workspace(path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    if not os.path.exists(target):
        return {"ok": False, "error": f"没有这个路径: {path}"}

    if os.path.isdir(target):
        if not recursive:
            try:
                os.rmdir(target)
            except OSError:
                return {
                    "ok": False,
                    "error": "目录里还有东西。真要连里面的内容一起删,把 recursive 设为 true",
                }
            logger.info(f"删掉空目录 {_shown(target)}")
            return {"ok": True, "path": _shown(target), "kind": "空目录"}

        removed = sum(len(files) + len(dirs) for _, dirs, files in os.walk(target))
        try:
            shutil.rmtree(target)
        except Exception as e:
            return {"ok": False, "error": f"删不掉: {e}"}
        logger.info(f"删掉目录 {_shown(target)} ({removed} 项)")
        return {"ok": True, "path": _shown(target), "kind": "目录", "removed": removed}

    try:
        os.remove(target)
    except Exception as e:
        return {"ok": False, "error": f"删不掉: {e}"}
    logger.info(f"删掉文件 {_shown(target)}")
    return {"ok": True, "path": _shown(target), "kind": "文件"}
