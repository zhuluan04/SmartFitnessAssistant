"""
应用配置模块 — 集中管理环境变量、模型初始化、全局配置
"""
import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

# 加载环境变量
load_dotenv(override=True)

# ──────────────────────────────────────
# 模型配置
# ──────────────────────────────────────

# 文本模型（阿里云百炼 Qwen3.5-Plus，OpenAI 兼容模式）
text_model = init_chat_model(
    model="qwen3.5-plus",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    temperature=0.3,   # 降低随机性，减少菜谱推荐的跳跃性
)

# 视觉模型（用于图片输入场景）
vision_model = init_chat_model(
    model="qwen-vl-plus",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    temperature=0.3,
)
