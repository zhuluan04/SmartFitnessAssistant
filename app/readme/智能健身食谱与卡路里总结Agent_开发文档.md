# 智能健身食谱与卡路里总结 Agent · 开发文档

运行：
uv run python main.py cli

版本：v0.2　　日期：2026-07-03　　状态：阶段一开发中（核心代码已就绪，待联调测试）

---

## 一、项目概述

| 项目 | 内容 |
|---|---|
| 项目名称 | 智能健身食谱与卡路里总结 Agent |
| 项目目标 | 识别用户食材（图片/文字），结合网络搜索推荐健身食谱，精准计算卡路里，输出结构化营养报告 |
| 技术栈 | Python · LangChain 1.0（`create_agent`）· 阿里云百炼 Qwen3.5-Plus（多模态）· Tavily 搜索 · FastAPI · 微信小程序 |
| 交付形态 | 阶段一：命令行闭环 → 阶段四：小程序 + 后端 API |

---

## 二、系统架构

```
用户输入（图片/文字）
        │
        ▼
┌───────────────────────┐
│   LangChain Agent      │
│  （create_agent）       │
│  model: Qwen3.5-Plus    │
├───────────────────────┤
│ 工具1：web_search       │  → Tavily：检索候选食谱
│ 工具2：calculate_       │  → 本地/第三方营养数据库：
│        food_calories   │     核算卡路里，杜绝幻觉
└───────────────────────┘
        │
        ▼
   结构化 Markdown 报告
   （食谱/得分/理由/图片）
        │
        ▼
FastAPI（/generate_diet）──► 微信小程序（mp-html 渲染）
```

---

## 三、环境搭建

### 3.1 依赖安装

```bash
pip install langchain langchain-openai langchain-tavily python-dotenv fastapi uvicorn
```

> LangChain 已进入 1.0 版本，`create_agent` 是官方推荐的标准 Agent 构建方式（基于 LangGraph 运行时），替代旧版 `initialize_agent`/`AgentExecutor`。

### 3.2 `.env` 配置项

```env
# 阿里云百炼（DashScope）
DASHSCOPE_API_KEY=xxxxxxxx
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Tavily 搜索（TavilySearch 会自动从环境变量读取，无需在代码里显式传入）
TAVILY_API_KEY=xxxxxxxx

# （阶段二可选）LangSmith 链路追踪
LANGSMITH_API_KEY=xxxxxxxx
LANGSMITH_TRACING=true
```

⚠️ **注意**：`DASHSCOPE_BASE_URL` 必须是 DashScope 的 **OpenAI 兼容模式**地址，而不是原生 DashScope 接口地址，否则 `model_provider="openai"` 无法正常工作。

### 3.3 `.gitignore`

```
.env
__pycache__/
*.pyc
```

---

## 四、核心模块设计

### 4.1 模型初始化

```python
from langchain.chat_models import init_chat_model
import os

model = init_chat_model(
    model="qwen3.5-plus",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    temperature=0.3,   # 降低随机性，减少菜谱推荐的跳跃性
)
```

### 4.2 工具一：Web 搜索（已具备）

```python
from langchain_tavily import TavilySearch

web_search = TavilySearch(
    max_results=5,
    topic="general",
)
```

### 4.3 工具二：卡路里计算（阶段一待补齐，核心痛点解决方案）

> 目的：杜绝大模型对卡路里数值的"幻觉"，强制通过确定性函数或外部数据库核算。

```python
from langchain.tools import tool

# 简化版：本地食物热量表（生产环境建议接入第三方营养数据库 API，如薄荷健康/USDA FoodData Central）
FOOD_CALORIE_TABLE = {
    "鸡胸肉": 133,   # 每100g，千卡
    "西兰花": 34,
    "糙米饭": 116,
    "鸡蛋": 155,
    "牛油果": 160,
    # ... 持续补充
}

@tool
def calculate_food_calories(food_items: dict) -> dict:
    """
    根据食材及重量（单位：克）计算总卡路里。
    输入示例：{"鸡胸肉": 150, "西兰花": 100}
    输出：每种食材的卡路里明细 + 总卡路里
    """
    detail = {}
    total = 0
    for name, grams in food_items.items():
        kcal_per_100g = FOOD_CALORIE_TABLE.get(name)
        if kcal_per_100g is None:
            detail[name] = "未收录，需人工核实"
            continue
        kcal = round(kcal_per_100g * grams / 100, 1)
        detail[name] = f"{kcal} kcal"
        total += kcal
    return {"明细": detail, "总卡路里": f"{round(total, 1)} kcal"}
```

**后续优化方向**：本地表覆盖有限，建议阶段二接入第三方营养数据库 API（如薄荷健康开放接口、USDA FoodData Central），或维护一份更完整的食材热量 CSV，通过 RAG 检索匹配。

### 4.4 System Prompt（补充强制输出格式）

```python
system_prompt = """
你是一名私人厨师兼营养师。收到用户提供的食材照片或清单后，请严格按以下流程操作：

1. 识别和评估食材：若用户提供照片，首先辨识所有可见食材，基于外观状态评估新鲜度与可用量，
   整理出"当前可用食材清单"（含预估重量，单位：克）。

2. 智能食谱检索：必须调用 web_search 工具，以"可用食材清单 + 健身目标（减脂/增肌）"为核心关键词，
   查找可行菜谱。严禁在未调用工具的情况下凭空编造菜谱。

3. 精准卡路里核算：对筛选出的候选食谱，必须调用 calculate_food_calories 工具计算总卡路里，
   严禁自行估算或编造数值。

4. 多维度评估与排序：从"营养价值"和"制作难度"两个维度对候选食谱进行 1-10 分打分，
   优先推荐简单且营养丰富的食谱。

5. 结构化输出：严格按以下 Markdown 表格格式输出，不要额外发挥格式：

   | 排名 | 食谱名称 | 总卡路里 | 营养得分 | 难度得分 | 推荐理由 |
   |---|---|---|---|---|---|
   | 1 | ... | ... | ... | ... | ... |

   表格下方附上每道菜的一句话做法概述。

请严格按流程执行：先调用 web_search 搜索食谱，再调用 calculate_food_calories 核算热量，
两个工具缺一不可；搜索/计算失败时明确告知用户，而不是自行编造结果。
"""
```

### 4.5 Agent 组装

```python
from langchain.agents import create_agent

agent = create_agent(
    model=model,
    tools=[web_search, calculate_food_calories],
    system_prompt=system_prompt,
)

# 调用示例
result = agent.invoke({
    "messages": [{"role": "user", "content": "我有鸡胸肉150g、西兰花100g、糙米饭一碗，目标是减脂，帮我推荐食谱"}]
})
print(result["messages"][-1].content)
```

---

## 五、阶段性开发计划

### 阶段一：单机版 Agent 跑通 ✅ 已完成

- [x] 本地环境搭建、`.env` 配置（DashScope + Tavily 两套 key）
- [x] 编写 `calculate_food_calories` 工具（本地热量表 + Pydantic schema）
- [x] 补全 System Prompt 的输出格式约束（食物状态判断 + Markdown 表格模板）
- [x] CLI 交互入口（`uv run python main.py cli`）
- [x] 文本模型（qwen3.5-plus）+ 视觉模型（qwen-vl-plus）双 Agent 架构
- [ ] 单元测试：`calculate_food_calories`（覆盖正常计算 + "食材未收录"分支）
- [x] 终端纯文本验证："输入食材 → 搜索食谱 → 计算卡路里 → 输出表格"完整闭环
- [ ] 验证点：抓日志确认模型**确实调用了两个工具**，而非直接生成答案

### 阶段二：多模态与调试优化 ✅ 大部分完成

- [x] 接入图片输入（使用 qwen-vl-plus 视觉模型，CLI 已支持图片路径）
- [ ] 接入 LangSmith 全链路追踪，观察 Thought/Action，优化提示词
- [ ] 补充/接入第三方营养数据库，扩大食材覆盖率（当前本地热量表过渡）

### 阶段三：后端 API 封装 ✅ 已完成

- [x] FastAPI 封装（`app/api.py`）
  - [x] `GET /api/health` — 健康检查
  - [x] `POST /api/generate_diet` — 食谱生成（text/image 双模式）
  - [x] `GET /api/recommend` — 精选推荐食谱（按健身目标筛选）
- [x] CORS 中间件（支持小程序跨域请求）
- [x] Pydantic 请求/响应模型
- [ ] Swagger 文档联调验证（`http://localhost:8000/docs`）

### 阶段四：微信小程序前端 🚧 文档就绪，待开发

- [x] 前端开发文档 v2.0（清新风格设计 + 底部三栏 TabBar 导航）
- [x] 页面设计：首页（输入）/ 推荐页（精选食谱）/ 我的页（个人中心）/ 报告页
- [x] 前后端接口约定完成，与后端 API 对齐
- [ ] 小程序项目初始化（创建 miniprogram/ 目录）
- [ ] TabBar 图标设计与配置
- [ ] 首页：文字输入 + 图片上传 + 目标选择 + 提交
- [ ] 推荐页：食谱卡片列表 + 目标筛选
- [ ] 我的页：目标设置 + 功能菜单
- [ ] 报告页：mp-html 渲染 Markdown
- [ ] 前后端联调测试

---

## 六、关键注意事项

1. **API Key 安全**：严禁硬编码，统一走 `.env` + `python-dotenv`，`.env` 加入 `.gitignore`。
2. **工具调用可靠性**：国产模型走 OpenAI 兼容模式时，tool-calling 遵从度需要实测验证，
   不能假设它和原生 OpenAI/Claude 一样稳定，建议阶段一就打日志观察。
3. **卡路里数据来源**：本地表仅作为过渡方案，生产环境务必接入权威营养数据库，避免长期维护自建表。
4. **输出格式稳定性**：System Prompt 中固定 Markdown 表格模板，减少小程序端解析的不确定性。
5. **前后端职责边界**：小程序仅做展示壳，卡路里计算与搜索逻辑全部留在 Python 后端。

---

## 七、验收标准（阶段一）

| 测试项 | 通过标准 |
|---|---|
| 纯文本输入食材清单 | Agent 依次调用 web_search → calculate_food_calories，输出符合模板的表格 |
| 食材未收录热量表 | 工具返回"未收录，需人工核实"，Agent 不编造数值 |
| 搜索无结果 | Agent 明确告知用户搜索失败，而非自行编造菜谱 |
| 重复调用一致性 | 相同输入连续跑 3 次，工具调用链路稳定（均调用了两个工具） |
