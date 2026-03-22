import requests
import sounddevice as sd
import numpy as np
import io
import wave
import dataclasses

from src.logger import get_module_logger
logger = get_module_logger('readaudio')


url = "http://127.0.0.1:9880//tts"


weights_paths = {
    "圣聆初雪": {
        "gpt_weights": r"E:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\圣聆初雪-e15.ckpt",
        "sovits_weights": r"E:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\圣聆初雪_e8_s208.pth",
        "text_lang": "zh",
        "ref_audio_path": r"E:\a_音视频图片等各种素材\明日方舟\圣聆初雪\完成高难行动.wav",
        "prompt_text": "圣山所见证的胜利。披挂风雪的战士啊，我们即将踏上归途。",
        "prompt_lang": "zh",
    },
    "余": {
        "gpt_weights": r"E:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\余_方言-e15.ckpt",
        "sovits_weights": r"E:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\余_方言_e8_s328.pth",
        "text_lang": "zh",
        "ref_audio_path": r"E:\a_音视频图片等各种素材\明日方舟\余\方言\闲置 (1).wav",
        "prompt_text": "没有灶火声，还有点不习惯呢。这么安静，真困啊......",
        "prompt_lang": "zh",
    }
}


class Speaker:
    def __init__(self, name):
        self.name = name
        self.init_self()
        logger.info(f"初始化完成，当前说话人: {self.name}")

    def change_speaker(self, name):
        self.name = name
        self.init_self()

    def init_self(self):
        self.weights_init(weights_paths[self.name]["gpt_weights"], weights_paths[self.name]["sovits_weights"])
        self.text_lang = weights_paths[self.name]["text_lang"]
        self.ref_audio_path = weights_paths[self.name]["ref_audio_path"]
        self.prompt_text = weights_paths[self.name]["prompt_text"]
        self.prompt_lang = weights_paths[self.name]["prompt_lang"]
    def weights_init(self,gpt_weights_path,sovits_weights_path):
        gpt_weights_path = f"http://127.0.0.1:9880/set_gpt_weights?weights_path={gpt_weights_path}"
        sovits_weights_path = f"http://127.0.0.1:9880/set_sovits_weights?weights_path={sovits_weights_path}"
        requests.get(gpt_weights_path)
        requests.get(sovits_weights_path)


    def speak(self,text):
        """
        将文本转为语音并立即播放（不保存文件）
        """
        # 请求参数
        params = {
            "text": text,                   # str.(required) text to be synthesized
            "text_lang": self.text_lang,               # zh汉语 en英语 ja日语等 str.(required) language of the input text
            "ref_audio_path": self.ref_audio_path,         # str.(required) 参考音频路径
            "aux_ref_audio_paths": [],    # list.(optional) 不懂,但是应该用不到
            "prompt_text": self.prompt_text,            # str.(optional) 参考音频的文本
            "prompt_lang": self.prompt_lang,            # str.(required) 参考音频的语言
            "top_k": 5,                   # int. top k sampling
            "top_p": 1,                   # float. top p sampling
            "temperature": 1,             # float. temperature for sampling
            "text_split_method": "cut0",  # str. text split method, see text_segmentation_method.py for details.
            "batch_size": 1,              # int. batch size for inference
            "batch_threshold": 0.75,      # float. threshold for batch splitting.
            "split_bucket": True,          # bool. whether to split the batch into multiple buckets.
            "speed_factor":1.0,           # float. control the speed of the synthesized audio.
            "streaming_mode": False,      # bool. whether to return a streaming response.
            "seed": -1,                   # int. random seed for reproducibility.
            "parallel_infer": True,       # bool. whether to use parallel inference.
            "repetition_penalty": 1.35,    # float. repetition penalty for T2S model.
            "sample_steps": 32,           # int. number of sampling steps for VITS model V3.
            "super_sampling": False,       # bool. whether to use super-sampling for audio when using VITS model V3.
        }

        # 发送请求
        response = requests.get(url, params=params)
        if response.status_code != 200:
            logger.error(f"合成失败，状态码: {response.status_code}, 响应内容: {response.text}")
            return

        # 从返回的字节数据中读取 WAV 格式音频
        with io.BytesIO(response.content) as wav_io:
            with wave.open(wav_io, 'rb') as wf:
                sample_rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                # 假设采样位深为 16-bit
                audio_np = np.frombuffer(frames, dtype=np.int16)

        # 播放音频（阻塞直到播放完毕）
        sd.play(audio_np, samplerate=sample_rate)
        sd.wait()


global_speaker = Speaker("圣聆初雪")


# 测试
if __name__ == "__main__":
    speaker = Speaker("圣聆初雪")
    speaker.speak("小逼崽子")       # 听初雪骂人多是一件美事(

