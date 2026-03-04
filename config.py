"""
配置管理模块
从环境变量或 .env 文件读取配置信息
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    # 加载 .env 文件
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)
except ImportError:
    # 如果没有安装 python-dotenv，继续使用系统环境变量
    pass


def get_baidu_ak():
    """
    获取百度地图 API Key

    Returns:
        str: 百度地图 API Key

    Raises:
        ValueError: 如果未配置 API Key
    """
    ak = os.getenv('BAIDU_AK')
    if not ak:
        raise ValueError(
            "未找到百度地图 API Key！\n"
            "请按以下步骤配置：\n"
            "1. 复制 .env.example 为 .env\n"
            "2. 在 .env 文件中设置 BAIDU_AK=your_api_key\n"
            "或设置系统环境变量 BAIDU_AK"
        )
    return ak


# 配置示例
if __name__ == '__main__':
    try:
        ak = get_baidu_ak()
        print(f"API Key 已配置: {ak[:10]}...")
    except ValueError as e:
        print(e)
