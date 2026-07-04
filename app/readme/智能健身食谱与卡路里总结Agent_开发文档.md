# 智能健身食谱与卡路里总结 Agent · 开发文档

运行：
uv run python main.py api

版本：v0.3　　日期：2026-07-04　　状态：阶段一（防幻觉加固完成）

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
┌─────────────────────────────────────┐
│   LangChain Agent                    │
│  （create_agent）                     │
│  model: Qwen3.5-Plus                  │
├─────────────────────────────────────┤
│ 工具①：web_search                    │  → Tavily：检索候选食谱
│ 工具②：calculate_food_calories       │  → 本地热量表：精确计算食材卡路里
│        （仅用于原始食材）             │     返回完整性标记，杜绝编造
│ 工具③：estimate_meal_calories        │  → 估算成品食物热量
│        （仅用于成品菜肴）             │     返回"估算值+置信度+误差范围"
├─────────────────────────────────────┤
│  防幻觉加固层                         │
│  · ToolCallTracer 回调处理器          │  → 记录每次工具调用的输入/输出
│  · invoke_agent_with_trace()          │  → 调用后自动验证热量工具是否被调用
│  · 轨迹摘要追加至输出末尾              │  → 最终报告热量必须来自工具返回值
└─────────────────────────────────────┘
        │
        ▼
   结构化 Markdown 报告（含工具调用轨迹）
        │
        ▼
FastAPI（/generate_diet）──► 微信小程序（mp-html 渲染）
       │
       └── 响应体新增 tool_trace 字段，前端可校验热量来源
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

### 4.3 工具二：食材卡路里计算（v0.3 防幻觉加固）

> 目的：杜绝大模型对卡路里数值的"幻觉"，强制通过确定性函数核算。

**防幻觉设计要点**：
- 返回值增加了 `包含未收录食材`、`未收录食材列表`、`数据完整性` 三个字段。
- 未收录食材**不计入总卡路里**，并附带说明"总卡路里不完整"。
- 最终报告必须直接引用工具的返回值，不允许模型自行估算。

```python
@tool(args_schema=FoodItemsInput)
def calculate_food_calories(food_items: dict[str, float]) -> dict:
    """
    仅适用于原始食材。返回含完整性标记的精确热量数据。
    """
    detail = {}
    unlisted = []
    total = 0
    for name, grams in food_items.items():
        kcal_per_100g = FOOD_CALORIE_TABLE.get(name)
        if kcal_per_100g is None:
            detail[name] = "未收录，需人工核实"
            unlisted.append(name)
            continue
        kcal = round(kcal_per_100g * grams / 100, 1)
        detail[name] = f"{kcal} kcal（每100g {kcal_per_100g} kcal × {grams}g）"
        total += kcal

    result = {
        "明细": detail,
        "已收录食材总卡路里": f"{round(total, 1)} kcal",
        "包含未收录食材": len(unlisted) > 0,
        "未收录食材列表": unlisted,
        "数据完整性": "完整" if not unlisted else "不完整",
    }
    if unlisted:
        result["说明"] = f"以下食材未收录：{'、'.join(unlisted)}。总卡路里不完整。"
    return result
```

### 4.4 工具三：成品食物估算（v0.3 新增，防成品伪装精确值）

> 目的：成品食物无法精确计算，强制通过此工具返回"估算值 + 置信度 + 误差范围"，
> 杜绝模型伪装成精确值。

```python
@tool(args_schema=MealEstimateInput)
def estimate_meal_calories(
    meal_name: str,
    estimated_weight_g: float = 200,
    main_ingredients: list[str] = [],
) -> dict:
    """
    估算成品食物卡路里。
    返回值包含估算卡路里、置信度（高/中/低）、误差范围（±kcal）、估算依据。
    声明：此为估算值，不作为精确营养数据。
    """
    # ... 基于食材热量表或营养学通用估算 ...
    return {
        "食物名称": meal_name,
        "估计份量": f"{estimated_weight_g}g",
        "估算卡路里": f"{total_est} kcal",
        "置信度": confidence,       # "高" / "中" / "低"
        "误差范围": f"±{error_range} kcal",
        "估算依据": estimate_basis,
        "声明": "⚠️ 此为估算值，仅作参考。"
    }
```

### 4.5 ToolCallTracer：工具调用轨迹记录器（v0.3 新增，核心防幻觉设施）

> 通过 LangChain 的 `BaseCallbackHandler` 机制，在 Agent 运行过程中实时记录
> 每个工具的调用时间、输入参数、返回结果。CLI 和 API 调用结束后自动展示轨迹。

```python
class ToolCallTracer(BaseCallbackHandler):
    def on_tool_start(self, serialized, input_str, **kwargs):
        # 记录工具名称和输入
    def on_tool_end(self, output, **kwargs):
        # 记录工具输出
    def get_summary(self) -> str:
        # 生成人类可读的轨迹摘要
```

**关键作用**：
- 每次 Agent 调用后，验证 `calculate_food_calories` 或 `estimate_meal_calories` 是否被调用。
- 若未调用热量工具，CLI 显示红色警告，API 在响应中标注 `tool_trace` 字段。
- 最终用户可肉眼验证报告中的热量数值与工具返回值一致。

### 4.6 System Prompt（防幻觉版 v0.3）

**核心强化规则**（仅摘要，完整版见 `app/langchain.py`）：

```text
## 情况A：如果是【食材】
3. 精准卡路里核算：
   - 必须调用 calculate_food_calories 工具。
   - 🔴 最终报告"总卡路里"须直接取自工具返回值。
   - 若工具返回"包含未收录食材: true"，标记"⚠️ 总热量不完整"。
   - 工具未返回数值时输出"❌ 热量计算失败"。

## 情况B：如果是【成品食物】
2. 估算热量：
   - 必须调用 estimate_meal_calories 工具。
   - 🔴 输出格式为"估算值 ± 误差范围"，标注置信度。
   - 禁止输出不含误差范围的精确值。
   示例：约 350 ± 88 kcal（置信度：中）

## 第三步：附上工具调用轨迹
在报告末尾输出工具调用摘要：
---
**工具调用轨迹**
1. ✅ web_search — 搜索了关键词：[...]
2. ✅ calculate_food_calories — 返回：已收录 xxx kcal
---
```

### 4.7 Agent 组装（v0.3 更新）

```python
from langchain.agents import create_agent

_common_tools = [web_search, calculate_food_calories, estimate_meal_calories]

text_agent = create_agent(
    model=text_model,
    tools=_common_tools,
    system_prompt=system_prompt,
)

vision_agent = create_agent(
    model=vision_model,
    tools=_common_tools,
    system_prompt=system_prompt,
)

# 带轨迹记录的封装调用
def invoke_agent_with_trace(agent, message_content):
    tracer = get_tracer()
    tracer.clear()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message_content}]},
        config={"callbacks": [tracer]},
    )
    return result["messages"][-1].content, tracer.get_trace()
```

---

## 五、阶段性开发计划

### 阶段一：单机版 Agent 跑通 ✅ 已完成（v0.3 防幻觉加固）

- [x] 本地环境搭建、`.env` 配置（DashScope + Tavily 两套 key）
- [x] 编写 `calculate_food_calories` 工具（本地热量表 + Pydantic schema）
- [x] **v0.3** 改造返回值，增加 `包含未收录食材`/`未收录食材列表`/`数据完整性` 字段
- [x] **v0.3** 新增 `estimate_meal_calories` 成品食物估算工具（返回"估算值+置信度+误差范围"）
- [x] **v0.3** 新增 `ToolCallTracer` 回调处理器，记录每次工具调用的输入/输出
- [x] **v0.3** 新增 `invoke_agent_with_trace()` 封装，自动验证热量工具是否被调用
- [x] **v0.3** 重写 System Prompt，强制热量数值必须来自工具返回值
- [x] **v0.3** 更新 API 响应体 `DietResponse`，新增 `tool_trace` 字段
- [ ] 单元测试：`calculate_food_calories`（覆盖正常计算 + "食材未收录"分支）
- [x] CLI 交互入口（`uv run python main.py cli`）
- [x] 终端纯文本验证："输入食材 → 搜索食谱 → 计算卡路里 → 输出表格"完整闭环
- [x] **v0.3** CLI 结束后显示工具调用轨迹摘要，并验证热量工具是否被调用

### 阶段二：多模态与调试优化 ✅ 大部分完成

- [x] 接入图片输入（使用 qwen-vl-plus 视觉模型，CLI 已支持图片路径）
- [x] **v0.3** 内置 ToolCallTracer 替代 LangSmith，低开销实时记录工具调用
- [ ] 接入 LangSmith 全链路追踪，观察 Thought/Action，优化提示词（可选）
- [ ] 补充/接入第三方营养数据库，扩大食材覆盖率（当前本地热量表过渡）

### 阶段三：后端 API 封装 ✅ 已完成（v0.3 更新）

- [x] FastAPI 封装（`app/api.py`）
  - [x] `GET /api/health` — 健康检查
  - [x] `POST /api/generate_diet` — 食谱生成（text/image 双模式）
    - [x] **v0.3** 响应体新增 `tool_trace` 字段
    - [x] **v0.3** 未调用热量工具时自动追加警告到报告
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
6. **🔴 防卡路里幻觉三重保障（v0.3 新增）**：
   - **第一重：工具返回值完整性标记** — `calculate_food_calories` 返回 `包含未收录食材`/`未收录食材列表`/`数据完整性`，未收录食材不计入总热量。
   - **第二重：ToolCallTracer 轨迹记录** — LangChain 回调处理器实时记录每个工具的输入输出，
     调用结束后自动验证热量工具是否被调用。
   - **第三重：System Prompt 硬约束** — 强制要求热量数值必须来自工具返回值，禁止模型自行估算。
     成品食物只允许输出"估算值 + 置信度 + 误差范围"。

---

## 七、验收标准（阶段一 v0.3 防幻觉版）

| 测试项 | 通过标准 |
|---|---|
| 纯文本输入食材清单 | Agent 依次调用 web_search → calculate_food_calories，输出符合模板的表格 |
| 食材未收录热量表 | 工具返回"未收录食材列表"，总热量标记"不完整"，Agent 不编造数值 |
| 搜索无结果 | Agent 明确告知用户搜索失败，而非自行编造菜谱 |
| 重复调用一致性 | 相同输入连续跑 3 次，工具调用链路稳定（均调用了两个工具） |
| **工具调用轨迹验证** | CLI 输出末尾显示工具调用摘要，确认热量工具已调用 |
| **成品食物输入** | Agent 调用 estimate_meal_calories，输出含置信度和误差范围，不伪装精确值 |
| **未收录食材不计入总热量** | 热量表中没有的食材不累加，总卡路里旁标注"⚠️ 总热量不完整" |
| **API 返回 tool_trace** | `POST /api/generate_diet` 响应中包含 `tool_trace` 字段 |
