# 长句子分割为短句子，使其更加符合对话习惯

# AI 想分句就换行;也可以显式写这个标记
SPLIT_MARK = "||"


def text_split(text: str) -> list[str]:
    """
    按 AI 自己写的换行切句

    为什么不用标点断句:
        标点是程序在猜“哪里该停”,换行是 AI 主动说“这里我要停一下”。
        而且原来那套把空格也算断句符,“快 12 点”会被切成三段。
    """
    if SPLIT_MARK in text:
        parts = text.split(SPLIT_MARK)
    else:
        parts = text.splitlines()
    return [part.strip() for part in parts if part.strip()]


class EmotionDetacter():
    def __init__(self,):
        self.emotions={
            # 开心
            r'(≧▽≦)', r'(´∀`)', r'(●´ω`●)', r'☆⌒ヽ(*\'-\')',
            # 惊讶
            r'(◎ロ◎)', r'(°ο°)', r'(@_@)',
            # 悲伤
            r'(;_;)', r'(T_T)', r'(;ω;)',
            # 其他
            r'(-_- )', r'(´ー`)', r'(*´▽`*)',
        }



