import os
import sys


def get_app_data_dir() -> str:
    """获取应用数据目录，适配不同平台和打包状态"""
    if getattr(sys, 'frozen', False):
        exe_path = sys.argv[0]
        exe_dir = os.path.dirname(os.path.abspath(exe_path))
        app_data_dir = os.path.join(exe_dir, "data")
    else:
        # 文件位于 utils/ 子目录下，需上溯两层回到项目根目录
        app_data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    os.makedirs(app_data_dir, exist_ok=True)
    return app_data_dir