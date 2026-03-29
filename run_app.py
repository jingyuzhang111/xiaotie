import os
import subprocess
import time
import sys
import socket


def get_base_dir():
    """Return base directory where bundled data are located.

    - When running under PyInstaller onefile, files added via `--add-data` are
      extracted to `sys._MEIPASS` (and `sys.frozen` is True).
    - In development, use the directory of this source file.
    - As a fallback (rare), use dirname(sys.executable).
    """
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


base_dir = get_base_dir()

# 拼接mongod.exe和local_db的路径（在打包时通过 --add-data 放到 other/ 下）
mongod_path = os.path.join(base_dir, 'other', 'mongod.exe')
local_db_path = os.path.join(base_dir, 'other', 'local_db')


def is_port_open(host='127.0.0.1', port=27017, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_mongod():
    # 若本机已有 MongoDB 在默认端口运行，直接复用，避免重复拉起导致启动失败。
    if is_port_open():
        print("检测到 MongoDB 已在 127.0.0.1:27017 运行，跳过启动")
        return True

    if not os.path.exists(mongod_path):
        print(f"mongod 未找到: {mongod_path}")
        return False
    if not os.path.exists(local_db_path):
        print(f"local_db 目录未找到 (将尝试自动创建): {local_db_path}")
        try:
            os.makedirs(local_db_path, exist_ok=True)
        except Exception as e:
            print(f"创建 local_db 失败: {e}")
            return False

    try:
        proc = subprocess.Popen(
            [mongod_path, '--dbpath', local_db_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(2)
        if proc.poll() is not None:
            # 进程已退出，但端口可用，通常表示已有实例在运行。
            if is_port_open():
                print("MongoDB 已可用，继续启动 Flask")
                return True
            stderr = proc.stderr.read().decode(errors='ignore') if proc.stderr else ''
            print(f"mongod 启动失败，进程退出: {stderr}")
            return False
        print("mongod 启动成功")
        return True
    except Exception as e:
        print(f"启动 mongod 发生异常: {e}")
        return False


if __name__ == "__main__":
    started = start_mongod()
    if not started:
        sys.exit(1)
    import src.app
    import src.api
    src.api.set_socketio(src.app.socketio)
    src.app.run_app()