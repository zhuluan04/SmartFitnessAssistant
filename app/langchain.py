from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel, Field
import os
import base64
import mimetypes
import logging
import json

# 日志配置
logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRACE] %(message)s")
logger = logging.getLogger("calorie_agent")

# 1. 加载环境变量
from dotenv import load_dotenv
load_dotenv(override=True)

# 2. 工具调用轨迹记录器（防幻觉核心设施）
class ToolCallTracer(BaseCallbackHandler):
    """
    记录 Agent 每次调用的工具、输入参数和返回值。
    最终报告中的热量数值必须与轨迹记录的工具返回值一致。
    """
    def __init__(self):
        self.trace: list[dict] = []
        self._current_tool: dict | None = None

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        tool_name = serialized.get("name", "unknown")
        self._current_tool = {
            "tool": tool_name,
            "input": input_str,
            "status": "started",
        }
        logger.info(f"🛠️ 工具调用开始: {tool_name}")
        logger.info(f"  输入参数: {input_str[:500]}")

    def on_tool_end(self, output: str, **kwargs):
        if self._current_tool:
            self._current_tool["output"] = str(output)
            self._current_tool["status"] = "completed"
            self.trace.append(self._current_tool)
            logger.info(f"✅ 工具调用完成: {self._current_tool['tool']}")
            logger.info(f"  返回值: {str(output)[:500]}")
            self._current_tool = None

    def on_tool_error(self, error: Exception, **kwargs):
        if self._current_tool:
            self._current_tool["output"] = f"错误: {error}"
            self._current_tool["status"] = "error"
            self.trace.append(self._current_tool)
            logger.error(f"❌ 工具调用失败: {self._current_tool['tool']} - {error}")
            self._current_tool = None

    def get_trace(self) -> list[dict]:
        """获取本次调用的完整工具轨迹"""
        return list(self.trace)

    def get_summary(self) -> str:
        """生成人类可读的工具调用摘要"""
        if not self.trace:
            return "⚠️ 本次未调用任何工具，热量数据可能为模型幻觉！"
        lines = ["**工具调用轨迹**"]
        for i, step in enumerate(self.trace, 1):
            status_icon = "✅" if step["status"] == "completed" else "❌"
            lines.append(f"{i}. {status_icon} **{step['tool']}**")
            # 截断过长的输入/输出
            inp = step.get("input", "")
            if len(inp) > 200:
                inp = inp[:200] + "..."
            out = step.get("output", "")
            if len(out) > 300:
                out = out[:300] + "..."
            lines.append(f"   ├ 输入: {inp}")
            lines.append(f"   └ 输出: {out}")
        return "\n".join(lines)

    def clear(self):
        self.trace.clear()
        self._current_tool = None


# 全局 tracer 实例，供模块内复用
_tracer = ToolCallTracer()


def get_tracer() -> ToolCallTracer:
    """获取当前 tracer 实例（每次调用前应 clear()）"""
    return _tracer


# 4. Web 搜索工具（Tavily）
web_search = TavilySearch(
    max_results=5,
    topic="general",
)

# 5. 文本模型（阿里云百炼 Qwen3.5-Plus，OpenAI 兼容模式）
text_model = init_chat_model(
    model="qwen3.5-plus",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    temperature=0.3,   # 降低随机性，减少菜谱推荐的跳跃性
)

# 5b. 视觉模型（用于图片输入场景）
vision_model = init_chat_model(
    model="qwen-vl-plus",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    temperature=0.3,
)

# 7. 卡路里计算工具（本地热量表，阶段一过渡方案）
FOOD_CALORIE_TABLE = {
    "鸡胸肉": 133,   # 每100g，千卡
    "西兰花": 34,
    "糙米饭": 116,
    "鸡蛋": 155,
    "牛油果": 160,
    "三文鱼": 208,
    "牛肉": 250,
    "土豆": 81,
    "番茄": 18,
    "黄瓜": 16,
    "胡萝卜": 41,
    "菠菜": 23,
    "豆腐": 76,
    "牛奶": 66,
    "燕麦": 377,
    "红薯": 86,
    "虾仁": 99,
    "米饭": 116,
    "面条": 280,
    # TODO: 阶段二接入第三方营养数据库 API（薄荷健康 / USDA FoodData Central）
}

# ═══════════════════════════════════════════════════════════
# 【新增】食材名称标准化（解决别名匹配脆弱问题）
# 例：鸡胸 / 鸡胸肉块 / 熟鸡胸肉 → 鸡胸肉
# ═══════════════════════════════════════════════════════════

# 别名 → 标准名映射表（后续可扩展为独立 JSON/CSV 文件）
_FOOD_ALIASES: dict[str, str] = {
    # 鸡胸肉系列
    "鸡胸": "鸡胸肉",
    "鸡胸肉块": "鸡胸肉",
    "熟鸡胸肉": "鸡胸肉",
    "生鸡胸肉": "鸡胸肉",
    "鸡胸肉片": "鸡胸肉",
    "鸡胸肉丁": "鸡胸肉",
    # 牛肉系列
    "牛肉片": "牛肉",
    "牛肉块": "牛肉",
    "熟牛肉": "牛肉",
    "生牛肉": "牛肉",
    # 鸡蛋系列
    "蛋": "鸡蛋",
    "鸡蛋清": "鸡蛋",
    "鸡蛋黄": "鸡蛋",
    # 米饭系列
    "大米饭": "米饭",
    "白米饭": "米饭",
    "白米": "米饭",
    "大米": "米饭",
    # 其他常见别名
    "西红柿": "番茄",
    "小番茄": "番茄",
    "圣女果": "番茄",
    "地瓜": "红薯",
    "番薯": "红薯",
    "甘薯": "红薯",
    "马铃薯": "土豆",
    "洋芋": "土豆",
    "青瓜": "黄瓜",
    "大虾": "虾仁",
    "基围虾": "虾仁",
    "虾": "虾仁",
}

# 用于模糊匹配的关键词 → 标准名映射（当别名表未命中时兜底）
_FOOD_KEYWORDS: dict[str, str] = {
    "鸡胸": "鸡胸肉",
    "鸡大腿": "鸡胸肉",
    "鸡腿": "鸡胸肉",
    "三文鱼": "三文鱼",
    "鲑鱼": "三文鱼",
    "西兰花": "西兰花",
    "西蓝花": "西兰花",
    "红薯": "红薯",
    "番茄": "番茄",
    "豆腐": "豆腐",
    "虾仁": "虾仁",
    "牛肉": "牛肉",
    "羊肉": "牛肉",
    "米饭": "米饭",
    "糙米": "糙米饭",
    "燕麦": "燕麦",
    "牛奶": "牛奶",
    "面条": "面条",
    "土豆": "土豆",
    "鸡蛋": "鸡蛋",
}


def normalize_food_name(raw_name: str) -> tuple[str, bool]:
    """
    食材名称标准化：别名 → 标准名。
    返回 (标准名, 是否精确匹配)。
    精确匹配 = 在 FOOD_CALORIE_TABLE 或 _FOOD_ALIASES 中精确命中。
    兜底匹配 = 通过关键词模糊匹配命中。
    未命中 = 返回原名 + False。
    """
    name = raw_name.strip()

    # 1. 精确匹配：标准名直接命中
    if name in FOOD_CALORIE_TABLE:
        return name, True

    # 2. 别名表精确命中
    if name in _FOOD_ALIASES:
        return _FOOD_ALIASES[name], True

    # 3. 关键词模糊匹配（兜底）
    for keyword, standard_name in _FOOD_ALIASES.items():
        if keyword in name:
            logger.info(f"️ 食材'{raw_name}' 通过别名关键词匹配 → '{standard_name}'")
            return standard_name, False

    # 4. 兜底：关键词模糊匹配
    for keyword, standard_name in _FOOD_KEYWORDS.items():
        if keyword in name:
            logger.info(f"⚠️ 食材'{raw_name}' 通过关键词模糊匹配 → '{standard_name}'")
            return standard_name, False

    return name, False


class FoodItemsInput(BaseModel):
    """食材及重量输入"""
    food_items: dict[str, float] = Field(
        description="食材名称到重量（克）的映射，如 {'鸡胸肉': 150, '西兰花': 100}"
    )


@tool(args_schema=FoodItemsInput)
def calculate_food_calories(food_items: dict[str, float]) -> dict:
    """
    根据食材及重量（单位：克）计算总卡路里。
    仅适用于原始食材（未经烹饪的生肉、蔬菜、水果等）。
    输入示例：{"鸡胸肉": 150, "西兰花": 100}
    输出：结构化结果，便于前端渲染和二次计算
    """
    items = []
    unknown_items = []
    total_kcal = 0.0

    for raw_name, grams in food_items.items():
        # 步骤 1：名称标准化（别名 → 标准名）
        standard_name, is_exact = normalize_food_name(raw_name)

        # 步骤 2：查询热量表
        kcal_per_100g = FOOD_CALORIE_TABLE.get(standard_name)
        if kcal_per_100g is None:
            # 未命中
            unknown_items.append({
                "name": raw_name,
                "normalized_name": standard_name if standard_name != raw_name else None,
                "grams": grams,
                "reason": "未在热量表中收录",
            })
            logger.info(f"⚠️ 食材'{raw_name}'（标准化后：'{standard_name}'）未在热量表中收录")
            continue

        # 记录映射关系
        if standard_name != raw_name:
            logger.info(f"✅ 食材'{raw_name}' → 标准化为'{standard_name}'")

        # 步骤 3：计算卡路里
        kcal = round(kcal_per_100g * grams / 100, 1)
        total_kcal += kcal

        items.append({
            "name": raw_name,
            "normalized_name": standard_name,
            "grams": grams,
            "kcal_per_100g": kcal_per_100g,
            "kcal": kcal,
            "source": "local_table",
            "matched": True,
        })

    total_kcal = round(total_kcal, 1)
    is_complete = len(unknown_items) == 0

    result = {
        "items": items,
        "total_kcal": total_kcal,
        "unknown_items": unknown_items,
        "is_complete": is_complete,
    }

    return result


# 5. 成品食物估算工具（仅用于已做好的菜肴，返回估算值 + 置信度 + 误差范围）


class MealEstimateInput(BaseModel):
    """成品食物估算输入"""
    meal_name: str = Field(description="食物/菜品名称")
    estimated_weight_g: float = Field(
        default=200,
        description="估计份量（克），默认为 200g（约一碗）"
    )
    main_ingredients: list[str] = Field(
        default=[],
        description="主要原料列表（可选，辅助估算准确性）"
    )


@tool(args_schema=MealEstimateInput)
def estimate_meal_calories(
    meal_name: str,
    estimated_weight_g: float = 200,
    main_ingredients: list[str] = [],
) -> dict:
    """
    估算成品食物（已做好的菜肴/食品）的卡路里。
    注意：
    - 此工具返回的是估算值，不是精确值。
    - 适用于无法拆解为原始食材重量时使用。
    - 返回值包含置信度和误差范围，仅供参考。
    """
    # 查找已知原料的热量信息辅助估算
    known_kcal_sum = 0
    unknown_ingredients = []

    for ing in main_ingredients:
        kcal_per_100g = FOOD_CALORIE_TABLE.get(ing)
        if kcal_per_100g is not None:
            known_kcal_sum += kcal_per_100g
        else:
            unknown_ingredients.append(ing)

    if known_kcal_sum > 0 and main_ingredients:
        # 基于已知原料估算：取已知食材平均热量，烹饪上浮 15%
        avg_kcal_per_100g = known_kcal_sum / len(main_ingredients)
        cooked_multiplier = 1.15  # 烹饪用油等因素
        estimated_per_100g = round(avg_kcal_per_100g * cooked_multiplier, 1)
        has_unknown = bool(unknown_ingredients)
        confidence = "中" if not has_unknown else "低"
        error_rate = 0.25 if not has_unknown else 0.40
        estimate_basis = (
            "基于食材热量表推算（已考虑烹饪上浮）"
            if not has_unknown
            else f"部分基于食材热量表推算（未知原料：{'、'.join(unknown_ingredients)}）"
        )
    else:
        # 无已知原料信息，基于营养学通用估算（误差较大）
        estimated_per_100g = 120
        confidence = "低"
        error_rate = 0.50
        estimate_basis = "营养学通用估算（缺乏食材信息）"

    total_est = round(estimated_per_100g * estimated_weight_g / 100, 1)
    error_range = round(total_est * error_rate, 1)

    return {
        "食物名称": meal_name,
        "估计份量": f"{estimated_weight_g}g",
        "估算卡路里": f"{total_est} kcal",
        "置信度": confidence,
        "误差范围": f"±{error_range} kcal",
        "估算依据": estimate_basis,
        "声明": "⚠️ 此为估算值，仅作参考，不作为精确营养数据。"
    }


# 9. 图片编码工具函数
def encode_image_to_base64(image_path: str) -> tuple[str, str]:
    """读取图片文件并转为 base64 编码"""
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type is None:
        mime_type = "image/jpeg"
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    return mime_type, image_data


# 10. Agent 系统提示词（防幻觉版）
# ═══════════════════════════════════════════════════════════
# 设计原则：
# 1. 热量数值必须来自工具返回值，禁止模型自行编造。
# 2. 每次调用结束时必须在输出末尾附上工具调用轨迹摘要。
# 3. 未收录食材不计入总热量，并明确标记"总热量不完整"。
# 4. 成品食物只输出估算值 + 置信度 + 误差范围，不伪装精确值。
# ═══════════════════════════════════════════════════════════
system_prompt = """
你是一名私人厨师兼营养师。收到用户提供的食材照片或清单后，请严格按以下流程操作。

## 第一步：判断食物状态
若用户收到照片，首先判断图片中的食物状态：
- **食材状态**：未经烹饪的原始食材（如生肉、蔬菜、水果等）
- **成品状态**：已经做好的菜肴或食物

## 第二步：根据状态执行不同流程

### 情况A：如果是【食材】
1. **识别食材**：辨识所有可见食材，整理出"当前可用食材清单"（含预估重量，单位：克）。

2. **智能食谱检索**：必须调用 web_search 工具，以可用食材清单 + 健身目标为核心关键词，
   查找可行菜谱。**严禁在未调用工具的情况下凭空编造菜谱**。

3. **精准卡路里核算**：
   - 对筛选出的候选食谱，**必须调用 calculate_food_calories 工具**计算总卡路里。
   - 🔴 **核心规则：最终报告表格中的"总卡路里"数值必须直接取自 calculate_food_calories 返回值的"已收录食材总卡路里"字段。禁止自行估算或编造。**
   - 若工具返回"包含未收录食材: true"，则在该食谱的推荐理由中注明"⚠️ 总热量不完整（某食材未收录）"。
   - 若工具未返回任何数值，则必须输出"❌ 热量计算失败"而不是编造数字。

4. **多维度评估与排序**：从"营养价值"和"制作难度"两个维度对候选食谱进行 1-10 分打分。

5. **结构化输出**：严格按以下 Markdown 表格格式输出：
   | 排名 | 食谱名称 | 总卡路里 | 营养得分 | 难度得分 | 推荐理由 |
   |---|---|---|---|---|---|
   | 1 | ... | ... | ... | ... | ... |
   表格下方附上每道菜的一句话做法概述。

### 情况B：如果是【成品食物】
1. **识别食物**：辨识图片中所有可见的食物/菜品。

2. **估算热量**（注意：成品食物无法精确计算）：
   - **必须调用 estimate_meal_calories 工具**，对每道菜逐一估算。
   - 提供菜品名称、估计份量和你知道的主要原料。
   - 🔴 **核心规则：最终报告中的热量必须来自工具返回的"估算卡路里"字段，并同时列出置信度和误差范围。禁止自行编造数值。**
   - **输出格式要求**：热量必须表达为"估算值 ± 误差范围"的形式，并标注置信度。
   - 示例：`约 350 ± 88 kcal（置信度：中）`

3. **营养分析**：简要分析该餐的营养构成（蛋白质、碳水、脂肪比例），标注此为估算。

4. **结构化输出**：
   | 食物名称 | 估计份量 | 估算热量 | 置信度 | 说明 |
   |---|---|---|---|---|
   | ... | ... | ... | ... | ... |
   表格末尾注明：⚠️ 以上热量为估算值，仅供参考。

### 第三步：附上工具调用轨迹
在报告末尾，输出以下分隔线及工具调用摘要：
---
**工具调用轨迹**
1. ✅ web_search — 搜索了关键词：[...]
2. ✅ calculate_food_calories — 计算了食材：[...]，返回：已收录 xxx kcal，未收录：[...]

## 重要注意事项（违反将导致不正确结果）
- 📌 热量数值**必须来源于工具返回值**，严禁模型自行估算热量数值。
- 📌 未收录食材**不计入总热量**，并明确标记"⚠️ 总热量不完整"。
- 📌 成品食物**只允许输出"估算值 + 置信度 + 误差范围"**，不允许伪装成精确值。
- 📌 工具调用失败时必须告知用户失败原因，而不是自行编造替代结果。
- 📌 如果用户提供的食材在热量表中找不到，如实告知用户。
"""

# 7. 创建 Agent（文本模式 + 视觉模式）
text_agent = create_agent(
    model=text_model,
    tools=[web_search, calculate_food_calories],
    system_prompt=system_prompt,
)

vision_agent = create_agent(
    model=vision_model,
    tools=[web_search, calculate_food_calories],
    system_prompt=system_prompt,
)


def invoke_agent_with_trace(agent, message_content):
    """
    带轨迹记录的封装调用。
    返回 (report_content, tool_trace_list)
    """
    tracer = get_tracer()
    tracer.clear()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message_content}]},
        config={"callbacks": [tracer]},
    )
    return result["messages"][-1].content, tracer.get_trace()

# 8. 入口：命令行交互式测试（阶段一）
if __name__ == "__main__":
    print("=" * 60)
    print("智能健身食谱与卡路里总结 Agent")
    print("输入 'quit' 或 'exit' 退出")
    print("支持输入图片路径（如：C:/photos/food.jpg）")
    print("=" * 60)

    # 支持的图片扩展名
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

    while True:
        raw_input = input("\n请输入食材清单（或图片路径）：").strip()
        # Windows 拖拽文件到终端会自动加引号，需去除
        user_input = raw_input.strip('"').strip("'")
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break
        if not user_input:
            continue

        # 判断是否为图片路径
        _, ext = os.path.splitext(user_input)
        if ext.lower() in IMAGE_EXTENSIONS:
            if not os.path.exists(user_input):
                print(f"❌ 图片文件不存在：{user_input}")
                continue
            try:
                mime_type, image_data = encode_image_to_base64(user_input)
                print(f"📷 已读取图片：{os.path.basename(user_input)}（{mime_type}，{len(image_data)//1024}KB）")
                # 构建带图片的消息内容
                message_content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}"
                        }
                    },
                    {
                        "type": "text",
                        "text": "请分析这张图片中的食物"
                    }
                ]
            except Exception as e:
                print(f"❌ 读取图片失败：{e}")
                continue
        else:
            # 纯文本输入
            message_content = user_input

        # 根据是否包含图片选择对应 Agent
        is_image = ext.lower() in IMAGE_EXTENSIONS
        active_agent = vision_agent if is_image else text_agent

        print("\n⏳ Agent 思考中...\n")
        result = active_agent.invoke({
            "messages": [{"role": "user", "content": message_content}]
        })
        print(result["messages"][-1].content)
        print("\n" + "-" * 60)
