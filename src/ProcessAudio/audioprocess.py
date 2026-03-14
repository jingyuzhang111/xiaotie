import queue
import sounddevice as sd
import vosk
import json
import wave

print(sd.query_devices())

model = vosk.Model(r"E:\Flask_project\vue-connect\other\vosk-model-small-en-us-0.15")
print("模型加载完成")
# 音频队列
q = queue.Queue()

def callback(indata, frames, time, status):
    """这是一个回调函数，用于处理音频输入"""
    if status:
        print(status)
    # print("收到音频信号")
    q.put(bytes(indata))

with sd.RawInputStream(samplerate=16000, blocksize=8000, device=19,
                       dtype='int16', channels=1, callback=callback):
    rec = vosk.KaldiRecognizer(model, 16000)
    while True:
        data = q.get()
        if rec.AcceptWaveform(data):
            res = json.loads(rec.Result())
            print(res['text'])
        else:
            partial = json.loads(rec.PartialResult())
            print("\r" + partial['partial'], end='', flush=True)



