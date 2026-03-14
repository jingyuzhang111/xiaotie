# build.py
import os
import shutil
import PyInstaller.__main__

project_root = os.path.dirname(os.path.abspath(__file__))
# 清理之前的构建文件
shutil.rmtree('build', ignore_errors=True)
shutil.rmtree('dist', ignore_errors=True)

mongod_exe_path = os.path.join(project_root, 'other', 'mongod.exe')
local_db_dir = os.path.join(project_root, 'other', 'local_db')
app_file = os.path.join(project_root, 'run_app.py')

# 构建打包参数
args = [
    'run_app.py',  # 使用run_app.py作为入口
    '--name=MyFlaskApp',
    '--onefile',
    # 添加mongod.exe
    f'--add-data={os.path.join("other", "mongod.exe")};other',  # 打包到exe同级的other目录
    f'--add-data={os.path.join("other", "local_db")};other/local_db',  # 打包local_db到other目录
    # Flask-SocketIO相关隐藏导入
    '--hidden-import=engineio.async_drivers.threading',
    '--hidden-import=engineio.async_drivers.gevent',
    '--hidden-import=engineio.async_drivers.eventlet',
    '--hidden-import=flask_socketio',
    '--hidden-import=flask_cors',
    # MongoDB相关
    '--hidden-import=pymongo',
    '--hidden-import=bson',
    # Flask相关
    '--hidden-import=flask',
    '--hidden-import=jinja2',
]

PyInstaller.__main__.run(args)
print("打包完成！可执行文件在 dist 目录下。")