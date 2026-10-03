"""
图片理解

两个方向,不要混:

    describe_image   看图 —— 用中文说清画面里有什么。给**她**看,返回人话
    parse_sticker    解析 —— 吐一串结构化字段。给**程序/入库**用,返回 JSON

她拿着 JSON 没用(既不能检索表情包,也没有发表情包的通道),所以 parse_sticker
不是给她的工具 —— 留在这里是等以后的表情包库。

两个都走同一个 to_data_url:图片会整个发给服务商,所以在那一处统一把关。
"""
import base64
import mimetypes
import os
from typing import Any

from src.LLM.client import SHAPE_JSON, SHAPE_TEXT, call
from src.config import IMAGE_DESC_LIMIT, IMAGE_EXTS, IMAGE_MAX_BYTES
from src.logger import get_module_logger
from src.plugins.FileOp.fileops import resolve_readable

logger = get_module_logger("imgmanager")

def to_data_url(img_path: str) -> str:
    """
    本地图片 -> data URL。这里做三道检查,因为结果会**原样发给服务商**:

      1. 路径   复用读文件的规矩(整个电脑都能看,凭据文件除外)
      2. 后缀   必须在白名单里 —— 光看 mime 挡不住,理由见 config.py
      3. 大小   编码成 base64 之后还会再涨 1/3

    通不过就抛 ValueError,由调用方翻成能给她的说法。
    """
    target = resolve_readable(img_path)

    if not os.path.isfile(target):
        raise ValueError(f"没有这个文件: {img_path}")

    ext = os.path.splitext(target)[1].lower()
    if ext not in IMAGE_EXTS:
        raise ValueError(
            f"这不是图片({ext or '没有后缀'}),只认得 {' '.join(IMAGE_EXTS)}"
        )

    size = os.path.getsize(target)
    if size == 0:
        raise ValueError(f"{os.path.basename(target)} 是个空文件")
    if size > IMAGE_MAX_BYTES:
        raise ValueError(
            f"这张图 {size / 1024 / 1024:.1f} MB,太大了"
            f"(上限 {IMAGE_MAX_BYTES // 1024 // 1024} MB)"
        )

    mime = mimetypes.guess_type(target)[0] or ""
    if not mime.startswith("image/"):
        raise ValueError(f"认不出这是什么图片格式({mime or '未知'})")

    with open(target, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    logger.debug(f"看图 {target} {size / 1024:.0f}KB -> base64 {len(b64)} 字符")
    return f"data:{mime};base64,{b64}"


# ==================== 看图:给她 ====================

_SEE_SYS = """你是一双眼睛。

用中文说清三件事:
1. 画面里有什么 —— 什么东西、什么颜色、大概什么样子
2. 图里有没有文字 —— 有就一个字不改地抄出来。这段最有用,别省
3. 整体什么感觉 —— 亮还是暗、安静还是热闹、像什么场合

规矩:
- 只写看得见的。看不清就说看不清,别顺嘴补全。
- 别猜这是谁、别猜什么牌子、别分析作者想表达什么。
- 不要用"这张图片展示了"这种开场白,直接讲内容。
- 不要分点编号,像跟人说话那样连成一段,200 字以内。
"""


def describe_image(img_path: str) -> dict[str, Any]:
    """她看一张图:看得见什么就说什么。返回人话,她直接读"""
    try:
        url = to_data_url(img_path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    result = call(_SEE_SYS, "看看这张图里有什么。",
                  profile="vision", shape=SHAPE_TEXT, images=[url])
    if not result.ok:
        return {"ok": False, "error": f"没看成: {result.error}"}

    text = (result.text or "").strip()[:IMAGE_DESC_LIMIT]
    if not text:
        return {"ok": False, "error": "看完了,但它什么都没说"}
    return {"ok": True, "description": text}


# ==================== 解析表情包:给程序 ====================

_STICKER_SYS = ("你是表情包语义解析器。把输入图片转成可检索的结构化字段,"
                "供聊天机器人挑选表情包用。")

_STICKER_USER = """只描述看得见的内容,不要臆测具体人物身份。
不确定就写"置信度低"。禁止输出攻击性、歧视性、露骨内容。

输出一个 JSON 对象:
{
  "literal_caption":   "20-50 字,画面事实",
  "emotion_primary":   "主要情绪,如 无语/开心/愤怒/委屈/嘲讽",
  "emotion_secondary": "次要情绪,没有就 null",
  "intensity":         1 到 5 的整数,
  "tone":              "语气,如 友好/阴阳怪气/夸张/冷幽默/崩溃",
  "suitable_scenes":   ["适合用的场景", "场景", "场景"],
  "unsuitable_scenes": ["不适合的场景", "场景"],
  "reply_examples":    ["能配的回复", "回复", "回复"],
  "confidence":        0 到 1 之间的小数
}

只输出 JSON,不要解释,不要代码块。"""

_STR_FIELDS = ("literal_caption", "emotion_primary", "tone")
_LIST_FIELDS = ("suitable_scenes", "unsuitable_scenes", "reply_examples")


def _sticker_shape_ok(data: Any) -> bool:
    """
    字段结构对不对。光"能解析成 JSON"不够 —— 模型完全可能回一个
    语法合法、结构却是错的东西(比如把给它的形状照抄回来)。
    不通过会被 client.call 当成失败,自动再问一次。
    """
    if not isinstance(data, dict):
        return False
    for key in _STR_FIELDS:
        if not isinstance(data.get(key), str) or not data[key].strip():
            return False
    for key in _LIST_FIELDS:
        value = data.get(key)
        if not isinstance(value, list) or not value:
            return False
    if not isinstance(data.get("intensity"), int):
        return False
    return isinstance(data.get("confidence"), (int, float))


def parse_sticker(img_path: str) -> dict[str, Any]:
    """
    表情包入库解析器。**不是给她的工具** —— 她拿着这串字段没用。

    失败也返回 dict,不抛异常。字段不合规会自动再问一次。
    """
    try:
        url = to_data_url(img_path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    result = call(_STICKER_SYS, _STICKER_USER,
                  profile="vision", shape=SHAPE_JSON, images=[url],
                  validate=_sticker_shape_ok)
    if not result.ok:
        return {"ok": False, "error": result.error}
    return {"ok": True, "data": result.data}


__all__ = ["to_data_url", "describe_image", "parse_sticker"]
