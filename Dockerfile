# 智能健身食谱与卡路里总结 Agent — 容器化部署
# 构建：docker build -t smart-fitness-assistant .
# 运行：docker run -p 8000:8000 -e DASHSCOPE_API_KEY=xxx -e DASHSCOPE_BASE_URL=xxx -e TAVILY_API_KEY=xxx smart-fitness-assistant
FROM python:3.13-slim

WORKDIR /app

# 依赖源可切换：默认清华源（国内构建快），海外 CI 构建时传入官方源覆盖
ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_DEFAULT_INDEX=$UV_INDEX_URL

# 先复制依赖清单，利用 Docker 层缓存：依赖不变时无需重新安装
COPY pyproject.toml uv.lock ./
RUN pip install uv --no-cache-dir && uv sync --frozen --no-dev

# 再复制源码（.dockerignore 已排除 .env / .venv 等）
COPY . .

EXPOSE 8000

# 容器内不使用 reload=True（main.py 的开发态配置），直接以生产模式启动
CMD ["uv", "run", "python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
