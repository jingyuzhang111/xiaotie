# python
# 简要说明：启动同目录下的 `mongod.exe`，保证 `local_db` 可写，等待端口就绪；提供停止函数。
import subprocess
import time
import socket
from pathlib import Path
import sys

MONGOD = Path(__file__).parent.parent / "other" / 'mongod.exe'
DBPATH = Path(__file__).parent.parent / "other" /'local_db'

def _port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            return True
        except Exception:
            return False

def get_base_dir():
    """获取正确的基目录，兼容开发环境和PyInstaller打包后环境"""
    # 如果被打包，PyInstaller会设置 _MEIPASS 属性
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).parent
    return base_dir



def start_mongod(port: int = 27017, timeout: int = 15):

    BASE_DIR = get_base_dir()
    # 根据你的目录结构调整路径，这里是示例，假设 mongod.exe 在项目的 ./other/ 下
    MONGOD = BASE_DIR / "other" / 'mongod.exe'
    DBPATH = BASE_DIR / "other" / 'local_db'

    if not MONGOD.exists():
        raise FileNotFoundError(f'{MONGOD} not found')
    DBPATH.mkdir(parents=True, exist_ok=True)
    args = [
        str(MONGOD),
        f'--dbpath={DBPATH}',
        f'--bind_ip=127.0.0.1',
        f'--port={port}',
        '--noauth'  # 根据需求调整
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.time() + timeout
    while time.time() < end:
        if _port_open('127.0.0.1', port):
            return proc
        time.sleep(0.2)
    proc.kill()
    raise RuntimeError('mongod 启动超时或端口被占用')

def stop_mongod(proc: subprocess.Popen):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()

if __name__ == '__main__':
    print(MONGOD)
    print(DBPATH)
    proc = None
    try:
        proc = start_mongod()
        print('mongod 已启动，按回车停止')
        input()
    finally:
        stop_mongod(proc)
