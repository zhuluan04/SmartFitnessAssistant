# 智能健身食谱与卡路里总结 Agent

![CI](https://github.com/zhuluan04/SmartFitnessAssistant/actions/workflows/ci.yml/badge.svg)

基于 **LangChain 1.0 + 阿里云百炼 Qwen 系列模型** 的多模态 AI Agent 应用：识别食材（文字/图片）、联网检索健身食谱、精准核算卡路里，输出结构化营养报告，并提供 FastAPI 后端与微信小程序前端。

## ✨ 核心特性

- **双模式输入**：纯文字食材清单 / 食物照片（Qwen-VL-Plus 视觉识别）自动路由
- **防幻觉三重保障**：确定性计算工具 + 完整性标记、`BaseCallbackHandler` 工具调用轨迹追踪与自动校验、System Prompt 硬约束——热量数值强制来自工具返回值，杜绝模型编造
- **精准卡路里核算**：原始食材确定性计算（内置热量表 + 35+ 食材别名标准化）；成品食物返回"估算值 + 置信度 + 误差范围"，不伪装精确值
- **异步任务模式**：四态任务状态机（pending/running/success/failed）+ 4 个进度节点，规避 Agent 长耗时请求（10–30s）的超时风险
- **Tavily 联网检索**：实时搜索候选食谱，严禁凭空编造菜谱
- **全栈交付**：FastAPI RESTful API + 微信小程序四页面（mp-html 渲染 Markdown 报告）

## 🏗️ 系统架构

```
用户输入（图片/文字）
        │
        ▼
┌─────────────────────────────────────┐
│   LangChain Agent（create_agent）    │
│  文本：qwen3.5-plus / 视觉：qwen-vl-plus │
├─────────────────────────────────────┤
│  工具① web_search      → Tavily 检索  │
│  工具② calculate_food_calories        │
│        → 原始食材确定性热量计算        │
│  工具③ estimate_meal_calories         │
│        → 成品食物估算（置信度+误差）   │
├─────────────────────────────────────┤
│  防幻觉层：ToolCallTracer 轨迹追踪     │
│  + 调用后自动校验 + Prompt 硬约束      │
└─────────────────────────────────────┘
        │ 结构化 Markdown 报告
        ▼
FastAPI（同步 + 异步任务接口）──► 微信小程序
```

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| AI Agent | LangChain 1.0（`create_agent`，LangGraph 运行时） |
| 模型 | 阿里云百炼 Qwen3.5-Plus（文本）、Qwen-VL-Plus（多模态视觉） |
| 搜索 | Tavily Search API |
| 后端 | Python 3.13、FastAPI、Uvicorn、Pydantic |
| 前端 | 微信小程序（原生开发）、mp-html |
| 工程化 | uv、Docker、GitHub Actions CI/CD |

## 🚀 快速开始

### 环境要求

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) 依赖管理工具

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写：

```env
# 阿里云百炼（DashScope，OpenAI 兼容模式）
DASHSCOPE_API_KEY=your_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Tavily 搜索
TAVILY_API_KEY=your_key
```

### 3. 运行

```bash
# 命令行交互模式（支持图片路径输入）
uv run python main.py cli

# FastAPI 服务模式（http://localhost:8000，Swagger 文档见 /docs）
uv run python main.py api
```

## 🐳 Docker 部署

```bash
# 构建镜像（默认使用清华 PyPI 源，国内构建更快）
docker build -t smart-fitness-assistant .

# 运行容器（密钥通过环境变量注入，不写入镜像）
docker run -d -p 8000:8000 \
  -e DASHSCOPE_API_KEY=your_key \
  -e DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  -e TAVILY_API_KEY=your_key \
  smart-fitness-assistant
```

镜像说明：

- `.dockerignore` 已排除 `.env` / `.venv` 等文件，**密钥不会进入镜像**
- 依赖层与源码层分离，依赖不变时改代码重建秒级完成
- 海外环境构建可切换官方 PyPI 源：`docker build --build-arg UV_INDEX_URL=https://pypi.org/simple -t smart-fitness-assistant .`

## 🔄 CI/CD

GitHub Actions 流水线（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)），push / PR 到 main 时自动执行：

1. 依赖安装（`uv sync`，CI 环境自动切换官方 PyPI 源）
2. 语法检查（`compileall`）
3. Docker 镜像构建验证

## 📡 API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| POST | `/api/generate_diet` | 食谱生成（`text` / `image` 双模式，响应含 `tool_trace` 工具调用轨迹） |
| POST | `/api/generate_diet/task` | 创建异步任务，返回 `task_id` |
| GET | `/api/generate_diet/task/{task_id}` | 查询任务状态（pending/running/success/failed + 进度节点） |
| GET | `/api/recommend?goal=减脂` | 精选推荐食谱（按健身目标筛选） |

## 📱 微信小程序前端

`miniprogram/` 目录，原生开发：底部三栏 TabBar（首页 / 推荐 / 我的）+ 报告页；支持图片压缩上传、健身目标选择、Markdown 报告渲染。

## 📂 项目结构

```
├── app/
│   ├── api.py            # FastAPI 接口（同步 + 异步任务）
│   ├── langchain.py      # Agent 核心：工具、防幻觉层、提示词
│   ├── core/config.py    # 环境变量与模型初始化
│   └── readme/           # 开发文档
├── miniprogram/          # 微信小程序前端
├── .github/workflows/    # CI/CD 流水线
├── Dockerfile            # 容器化部署
├── main.py               # 入口（cli / api 两种模式）
└── pyproject.toml        # uv 依赖管理
```

## 📄 开发文档

- [后端开发文档](app/readme/智能健身食谱与卡路里总结Agent_开发文档.md)
- [微信小程序前端开发文档](app/readme/微信小程序前端开发文档.md)
