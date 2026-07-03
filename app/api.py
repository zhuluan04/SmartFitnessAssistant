"""
智能健身食谱与卡路里总结 Agent — FastAPI 后端服务

启动：uv run python main.py api
接口：
  GET  /api/health          健康检查
  POST /api/generate_diet   食谱生成（文字/图片）
  GET  /api/recommend       精选推荐食谱
"""

import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.langchain import text_agent, vision_agent

# ──────────────────────────────────────
# FastAPI 实例
# ──────────────────────────────────────
app = FastAPI(
    title="智能健身食谱与卡路里总结 Agent",
    description="识别食材、推荐健身食谱、精准计算卡路里",
    version="0.1.0",
)

# CORS — 开发阶段允许所有来源（微信小程序需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────
# 请求/响应模型
# ──────────────────────────────────────

class DietRequest(BaseModel):
    mode: str = Field(description="输入模式：text 纯文字 / image 图片")
    content: str = Field(description="text 模式为食材文字；image 模式为 base64 编码图片（不含 data: 前缀）")
    fitness_goal: str = Field(default="减脂", description="健身目标：减脂 / 增肌 / 维持")
    mime_type: str = Field(default="image/jpeg", description="图片 MIME 类型（image 模式使用）")


class DietResponse(BaseModel):
    success: bool
    report: str | None = None
    elapsed_seconds: float | None = None
    error: str | None = None


class RecommendItem(BaseModel):
    id: int
    name: str
    calories: str
    tags: list[str]
    description: str
    nutrition_score: int
    difficulty_score: int


class RecommendResponse(BaseModel):
    success: bool
    recommendations: list[RecommendItem]


# ──────────────────────────────────────
# 精选推荐食谱（静态数据，阶段二可改为动态生成）
# ──────────────────────────────────────

RECOMMENDATIONS: list[RecommendItem] = [
    RecommendItem(
        id=1,
        name="鸡胸肉西兰花便当",
        calories="311 kcal",
        tags=["高蛋白", "低脂", "减脂推荐"],
        description="鸡胸肉切块腌制后滑炒，西兰花焯水备用，鸡蛋炒散，三者混合加蒜蓉调味翻炒均匀即可出锅。",
        nutrition_score=9,
        difficulty_score=8,
    ),
    RecommendItem(
        id=2,
        name="三文鱼牛油果沙拉",
        calories="368 kcal",
        tags=["优质脂肪", "增肌推荐", "无需烹饪"],
        description="三文鱼煎至两面金黄切块，牛油果切片，搭配混合生菜，淋柠檬汁和橄榄油即可。",
        nutrition_score=9,
        difficulty_score=9,
    ),
    RecommendItem(
        id=3,
        name="番茄虾仁豆腐汤",
        calories="193 kcal",
        tags=["低卡", "高蛋白", "减脂推荐"],
        description="番茄切块炒出汁水，加水煮沸后放入豆腐块和虾仁，煮至虾仁变色，盐和胡椒调味。",
        nutrition_score=8,
        difficulty_score=9,
    ),
    RecommendItem(
        id=4,
        name="糙米饭牛肉碗",
        calories="366 kcal",
        tags=["碳水补充", "增肌推荐", "饱腹感强"],
        description="牛肉切片腌制快炒，搭配糙米饭、焯水的菠菜和胡萝卜丝，浇上低盐酱油汁。",
        nutrition_score=8,
        difficulty_score=7,
    ),
    RecommendItem(
        id=5,
        name="红薯燕麦能量碗",
        calories="463 kcal",
        tags=["早餐推荐", "膳食纤维", "慢释放碳水"],
        description="红薯蒸熟切丁，燕麦用牛奶煮软，加入红薯丁和少许蜂蜜，撒上坚果碎。",
        nutrition_score=8,
        difficulty_score=10,
    ),
    RecommendItem(
        id=6,
        name="黄瓜鸡胸肉凉面",
        calories="249 kcal",
        tags=["低卡", "夏日推荐", "清爽"],
        description="鸡胸肉煮熟撕丝，黄瓜切丝，荞麦面煮熟过凉水，淋芝麻酱和醋汁拌匀。",
        nutrition_score=7,
        difficulty_score=8,
    ),
]


# ──────────────────────────────────────
# 接口实现
# ──────────────────────────────────────

@app.get("/api/health")
async def health():
    """健康检查，前端启动时调用检测后端是否在线"""
    return {"status": "ok", "model": "qwen3.5-plus + qwen-vl-plus"}


@app.post("/api/generate_diet")
def generate_diet(req: DietRequest):
    """
    食谱生成接口
    - text 模式：使用 text_agent（qwen3.5-plus）
    - image 模式：使用 vision_agent（qwen-vl-plus）
    """
    start = time.time()

    try:
        if req.mode == "image":
            # 构建带图片的多模态消息
            message_content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{req.mime_type};base64,{req.content}"
                    }
                },
                {
                    "type": "text",
                    "text": f"请分析这张图片中的食物。健身目标：{req.fitness_goal}"
                }
            ]
            agent = vision_agent
        else:
            # 纯文本输入，附加健身目标
            message_content = f"{req.content}。健身目标：{req.fitness_goal}"
            agent = text_agent

        result = agent.invoke({
            "messages": [{"role": "user", "content": message_content}]
        })
        report = result["messages"][-1].content
        elapsed = round(time.time() - start, 1)

        return DietResponse(success=True, report=report, elapsed_seconds=elapsed)

    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return DietResponse(
            success=False,
            error=f"分析失败：{str(e)}",
            elapsed_seconds=elapsed
        )


@app.get("/api/recommend")
async def recommend(goal: str = "减脂"):
    """
    精选推荐食谱
    - 可按健身目标过滤：减脂 / 增肌 / 维持
    """
    if goal == "增肌":
        filtered = [r for r in RECOMMENDATIONS if "增肌推荐" in r.tags]
    elif goal == "减脂":
        filtered = [r for r in RECOMMENDATIONS if "减脂推荐" in r.tags]
    else:
        filtered = RECOMMENDATIONS

    return RecommendResponse(success=True, recommendations=filtered)
