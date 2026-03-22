

class GlobalControl:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GlobalControl, cls).__new__(cls)
            cls._instance._observers = []
        return cls._instance

    def __init__(self):
        # 是否分割消息
        self.split = True
        # 是否启用GPT_Sovits有声朗读
        self.speak = False


global_control = GlobalControl()


