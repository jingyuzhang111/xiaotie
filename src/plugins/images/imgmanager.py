from src.LLM.client import call, SHAPE_TEXT
from src.config import *
import base64
import mimetypes
from pathlib import Path
import json

from src.logger import get_module_logger
logger = get_module_logger('imgmanager')

def to_data_url(img_path: str) -> str:
    p = Path(img_path)
    mime, _ = mimetypes.guess_type(p.name)
    print(f"图片mime类型: {mime}")
    with open(img_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    # b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
    print(f"图片base64长度: {len(b64)}")
    return f"data:{mime};base64,{b64}"



def chat_stream(content, img, sys_prompt: str | None = None):
    """
    图片分析。内部走统一的 client.call:
    档位 vision(LLM_IMAGE_*),形态 text,带一张图片作为多模态输入。

    注意这里保持了原行为:原实现没有设 temperature / max_tokens,
    所以 vision 档这两项都是 None(不往请求里传),交给服务端默认。
    """
    logger.info(f"发送给LLM的文本内容: {content}")
    result = call(sys_prompt or "", content, profile="vision",
                  shape=SHAPE_TEXT, images=[img])
    return result.text


if __name__ == "__main__":
    img=to_data_url(r"E:\Flask_project\vue-connect\src\images\srcs\佩佩.png")
    sys_prompt = "你是表情包语义解析器。你的任务是把输入图片转换为可检索的结构化文本，用于聊天机器人选择表情包。"
    user_content = """只描述看得见的内容，不要臆测具体人物身份。
如果不确定，明确写“置信度低”。
输出必须是 JSON，不要输出任何额外解释。
文案简短、可用于程序解析。
禁止输出攻击性、歧视性、露骨内容。
输出格式为:
literal_caption: 20-50字，描述画面事实
emotion_primary: 主要情绪（如无语/开心/愤怒/委屈/嘲讽）
emotion_secondary: 次要情绪，没有则填null
intensity: 1-5
tone: 语气（友好/阴阳怪气/夸张/冷幽默/崩溃）
suitable_scenes: 长度3的数组，写适合使用场景
unsuitable_scenes: 长度2的数组，写不适合场景
reply_examples: 长度3的数组，每条10-20字
confidence: 0-1 浮点数，描述对图片理解的置信度

"""
    content=chat_stream(user_content, img, sys_prompt)
    print("推理已完成，以下是结果：")
    print(content)
    content_json = json.loads(content)
    print(content_json["tone"])
