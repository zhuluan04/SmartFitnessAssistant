"""pytest 全局配置：在导入 app 模块之前注入假环境变量。

测试环境（含 CI）没有 .env 文件，但 app.langchain 模块导入时会初始化
大模型客户端与 Tavily 工具，必须存在这些变量（仅构造，不发起网络请求）。
"""
import os

os.environ.setdefault("DASHSCOPE_API_KEY", "test-dashscope-key")
os.environ.setdefault("DASHSCOPE_BASE_URL", "https://example.com/v1")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")
os.environ.setdefault("API_AUTH_TOKEN", "test-token-123")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_PASSWORD", "")
os.environ.setdefault("DB_NAME", "fitness_db")
