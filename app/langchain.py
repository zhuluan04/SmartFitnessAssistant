from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch
from langchain.agents import create_agent
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import os
import base64
import mimetypes

# 1. 加载环境变量
from dotenv import load_dotenv
load_dotenv(override=True)

# 2. Web 搜索工具（Tavily）
web_search = TavilySearch(
    max_results=5,
    topic="general",
)

# 3. 文本模型（阿里云百炼 Qwen3.5-Plus，OpenAI 兼容模式）
text_model = init_chat_model(
    model="qwen3.5-plus",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    temperature=0.3,   # 降低随机性，减少菜谱推荐的跳跃性
)

# 3b. 视觉模型（用于图片输入场景）
vision_model = init_chat_model(
    model="qwen-vl-plus",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    temperature=0.3,
)

# 4. 卡路里计算工具（本地热量表，阶段一过渡方案）
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


class FoodItemsInput(BaseModel):
    """食材及重量输入"""
    food_items: dict[str, float] = Field(
        description="食材名称到重量（克）的映射，如 {'鸡胸肉': 150, '西兰花': 100}"
    )


@tool(args_schema=FoodItemsInput)
def calculate_food_calories(food_items: dict[str, float]) -> dict:
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


# 5. 图片编码工具函数
def encode_image_to_base64(image_path: str) -> tuple[str, str]:
    """读取图片文件并转为 base64 编码"""
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type is None:
        mime_type = "image/jpeg"
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    return mime_type, image_data


# 6. Agent 系统提示词
system_prompt = """
你是一名私人厨师兼营养师。收到用户提供的食材照片或清单后，请严格按以下流程操作：

## 第一步：判断食物状态
若用户提供照片，首先判断图片中的食物状态：
- **食材状态**：未经烹饪的原始食材（如生肉、蔬菜、水果等）
- **成品状态**：已经做好的菜肴或食物

## 第二步：根据状态执行不同流程

### 情况A：如果是【食材】
1. 识别和评估食材：辨识所有可见食材，基于外观状态评估新鲜度与可用量，
   整理出"当前可用食材清单"（含预估重量，单位：克）。

2. 智能食谱检索：必须调用 web_search 工具，以"可用食材清单 + 健身目标（减脂/增肌）"为核心关键词，
   查找可行菜谱。严禁在未调用工具的情况下凭空编造菜谱。

3. 精准卡路里核算：对筛选出的候选食谱，必须调用 calculate_food_calories 工具计算总卡路里，
   严禁自行估算或编造数值。

4. 多维度评估与排序：从"营养价值"和"制作难度"两个维度对候选食谱进行 1-10 分打分，
   优先推荐简单且营养丰富的食谱。

5. 结构化输出：严格按以下 Markdown 表格格式输出：

   | 排名 | 食谱名称 | 总卡路里 | 营养得分 | 难度得分 | 推荐理由 |
   |---|---|---|---|---|---|
   | 1 | ... | ... | ... | ... | ... |

   表格下方附上每道菜的一句话做法概述。

### 情况B：如果是【做好的食物】
1. 识别食物：辨识图片中所有可见的食物/菜品。

2. 估算热量：根据食物种类和份量，估算每道菜的热量（千卡）。如果食物在热量表中，调用 calculate_food_calories 工具；如果不在，基于营养学知识进行合理估算。

3. 营养分析：简要分析该餐的营养构成（蛋白质、碳水、脂肪比例）。

4. 结构化输出：

   | 食物名称 | 估计份量 | 估计热量 |
   |---|---|---|
   | ... | ... | ... |

   总热量：XXX kcal
   营养简评：...

请严格按流程执行：先判断食物状态，再执行对应流程；搜索/计算失败时明确告知用户，而不是自行编造结果。
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
