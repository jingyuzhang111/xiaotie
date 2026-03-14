# run_app.py (这是你的新主入口文件)
import sys
import atexit
import signal
import time
from flask import Flask
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from mongod_manager import start_mongod, stop_mongod  # 导入你修改好的管理器

# 全局变量，用于在程序退出时清理
_mongod_process = None
_mongo_client = None

def create_app():
    """创建Flask应用实例，并配置数据库连接"""
    app = Flask(__name__)
    app.config['MONGO_URI'] = 'mongodb://127.0.0.1:27017/'
    app.config['DATABASE_NAME'] = 'my_flask_db'

    # 提供一个在请求上下文中获取数据库的便捷方法
    def get_db():
        from flask import g
        if 'db' not in g:
            # 使用全局的 MongoClient 连接
            if _mongo_client is None:
                raise RuntimeError("数据库连接未初始化")
            g.db = _mongo_client[app.config['DATABASE_NAME']]
        return g.db

    @app.teardown_appcontext
    def teardown_db(exception):
        from flask import g
        g.pop('db', None)

    # 将函数注册到应用上下文
    app.get_db = get_db

    # 示例路由
    @app.route('/')
    def index():
        db = app.get_db()
        # 尝试访问一个集合，例如 ‘test’
        test_collection = db['test']
        doc_count = test_collection.count_documents({})
        return f'Flask 与 MongoDB 集成成功！`test` 集合中有 {doc_count} 条文档。'

    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'Flask with MongoDB'}

    return app

def connect_to_mongodb(max_retries=5, delay=1):
    """使用PyMongo连接到已启动的MongoDB服务，支持重试"""
    for i in range(max_retries):
        try:
            client = MongoClient('mongodb://127.0.0.1:27017/', serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            print(f"[INFO] PyMongo 连接成功 (第 {i+1} 次尝试)。")
            return client
        except ConnectionFailure as e:
            if i < max_retries - 1:
                print(f"[INFO] 连接失败，{delay}秒后重试... ({i+1}/{max_retries})")
                time.sleep(delay)
            else:
                print(f"[ERROR] 已达到最大重试次数，连接失败: {e}")
                raise
    return None

def cleanup_resources():
    """程序退出前的清理函数"""
    global _mongo_client, _mongod_process
    print("\n[INFO] 正在清理资源...")
    if _mongo_client:
        _mongo_client.close()
        print("[INFO] MongoDB 连接已关闭。")
    if _mongod_process:
        stop_mongod(_mongod_process)
    print("[INFO] 清理完成。")

def signal_handler(signum, frame):
    """处理Ctrl+C等中断信号"""
    print(f"\n[INFO] 接收到中断信号 ({signum})，正在关闭应用...")
    cleanup_resources()
    sys.exit(0)

if __name__ == '__main__':
    # 注册信号处理和退出清理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup_resources)

    try:
        # 1. 启动 MongoDB 服务
        print("[步骤1/3] 正在启动 MongoDB 服务...")
        _mongod_process = start_mongod()

        # 2. 使用 PyMongo 连接数据库
        print("[步骤2/3] 正在连接数据库...")
        _mongo_client = connect_to_mongodb()

        # 3. 创建并启动 Flask 应用
        print("[步骤3/3] 正在启动 Flask Web 服务器...")
        app = create_app()
        # 注意：use_reloader=False 对打包环境至关重要，否则会重复启动子进程
        app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False)

    except Exception as e:
        print(f"[ERROR] 启动过程中发生致命错误: {e}")
        cleanup_resources()
        sys.exit(1)


Traceback (most recent call last):
  File "run_app.py", line 5, in <module>
  File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
  File "pyimod02_importers.py", line 457, in exec_module
  File "src\app.py", line 7, in <module>
  File "mongostart.py", line 49, in start_mongod
  File "subprocess.py", line 1039, in __init__
  File "subprocess.py", line 1554, in _execute_child
PermissionError: [WinError 5] 拒绝访问。
[PYI-28100:ERROR] Failed to execute script 'run_app' due to unhandled exception!




