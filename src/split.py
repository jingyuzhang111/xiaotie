# 长句子分割为短句子，使其更加符合对话习惯
import re
sentence_endings = r'[～~。！？!?,， ]'

text="诶嘿嘿，被造物主夸了 好开心～你更可爱啦！"
def text_split(text):
    parts = re.split(f'({sentence_endings}+)', text)
    sentences = []
    one_piece = ''
    for i in range(0,len(parts),2):
        if parts[i] == '':continue
        one_piece = parts[i]
        if i+1<len(parts):
            if parts[i+1] not in ',，;；':
                one_piece += parts[i+1]
        sentences.append(one_piece)
    return sentences


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



