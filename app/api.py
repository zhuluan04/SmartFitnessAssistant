"""
智能健身食谱与卡路里总结 Agent — FastAPI 后端服务

启动：uv run python main.py api
接口：
  GET  /api/health                    健康检查
  POST /api/generate_diet             食谱生成（文字/图片）[原有同步接口，保留]
  POST /api/generate_diet/task        食谱生成异步任务 [新增：创建任务并返回 task_id]
  GET  /api/generate_diet/task/{task_id}  [新增：查询任务状态与结果]
  GET  /api/recommend                 精选推荐食谱
"""

import time
import uuid
import threading
import logging
import os
import base64
import json
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from langchain_core.callbacks import BaseCallbackHandler

from app.langchain import text_agent, vision_agent, invoke_agent_with_trace
from app.services.database import get_conn

logger = logging.getLogger("calorie_agent")

# ──────────────────────────────────────
# FastAPI 实例
# ──────────────────────────────────────
app = FastAPI(
    title="智能健身食谱与卡路里总结 Agent",
    description="识别食材、推荐健身食谱、精准计算卡路里",
    version="0.1.0",
)


def verify_api_token(x_api_token: str = Header(default="", alias="X-API-Token")):
    """
    API 鉴权：校验请求头 X-API-Token 与 .env 中 API_AUTH_TOKEN 是否一致。
    未配置 API_AUTH_TOKEN 时跳过校验（本地开发模式）。
    """
    expected = os.getenv("API_AUTH_TOKEN", "").strip()
    if not expected:
        return None
    if x_api_token != expected:
        raise HTTPException(status_code=401, detail="未授权的访问：API Token 无效")
    return None


# CORS — 开发阶段允许所有来源（微信小程序需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# 异步任务状态存储（MySQL 持久化：服务重启任务不丢失）
# ═══════════════════════════════════════════════════════════

# 任务状态枚举（仅 4 种）
TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_SUCCESS = "success"
TASK_FAILED = "failed"

# 进度节点标识（用于 running 状态下的前端展示）
PROGRESS_RECOGNIZING = "识别中"
PROGRESS_SEARCHING = "搜索中"
PROGRESS_CALCULATING = "计算中"
PROGRESS_GENERATING = "生成报告中"

# 任务结果保留时长（秒）
TASK_TTL_SECONDS = 3600

# UPDATE 允许的字段白名单
_TASK_FIELDS = {"status", "progress", "result", "error"}


class TaskProgressCallback(BaseCallbackHandler):
    """监听真实工具调用事件，推送进度节点（事件驱动的真进度）"""

    def __init__(self, task_id: str):
        self.task_id = task_id

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        tool_name = serialized.get("name", "")
        if tool_name == "web_search":
            _update_task(self.task_id, progress=PROGRESS_SEARCHING)
        elif tool_name in ("calculate_food_calories", "estimate_meal_calories"):
            _update_task(self.task_id, progress=PROGRESS_CALCULATING)

    def on_llm_end(self, response, **kwargs):
        _update_task(self.task_id, progress=PROGRESS_GENERATING)


def _create_task(task_id: str, status: str = "pending", progress: str | None = None,
                 result: dict | None = None, error: str | None = None) -> dict:
    """创建任务记录（写入 MySQL）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO diet_tasks (task_id, status, progress, result, error) "
                "VALUES (%s, %s, %s, %s, %s)",
                (task_id, status, progress,
                 json.dumps(result, ensure_ascii=False) if result else None,
                 error),
            )
    return {"task_id": task_id, "status": status, "progress": progress,
            "result": result, "error": error}


def _update_task(task_id: str, **kwargs):
    """更新任务字段（仅允许白名单字段，防止意外写入其他列）"""
    kwargs = {k: v for k, v in kwargs.items() if k in _TASK_FIELDS}
    if not kwargs:
        return
    if "result" in kwargs and kwargs["result"] is not None:
        kwargs["result"] = json.dumps(kwargs["result"], ensure_ascii=False)
    fields = ", ".join(f"{key} = %s" for key in kwargs)
    values = list(kwargs.values()) + [task_id]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE diet_tasks SET {fields} WHERE task_id = %s", values)


def _get_task(task_id: str) -> dict | None:
    """按 ID 查询任务，不存在返回 None"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM diet_tasks WHERE task_id = %s", (task_id,))
            row = cur.fetchone()
    if not row:
        return None
    if isinstance(row.get("result"), str):
        try:
            row["result"] = json.loads(row["result"])
        except json.JSONDecodeError:
            row["result"] = None
    return row


def _cleanup_expired_tasks():
    """删除超过 TTL 的任务记录，数据库不会无限增长"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM diet_tasks WHERE created_at < (NOW() - INTERVAL %s SECOND)",
                (TASK_TTL_SECONDS,),
            )


# ──────────────────────────────────────
# 请求/响应模型
# ──────────────────────────────────────

# 允许的图片 MIME 类型
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}
# 图片解码后最大 10MB
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class DietRequest(BaseModel):
    mode: str = Field(description="输入模式：text 纯文字 / image 图片")
    content: str = Field(description="text 模式为食材文字；image 模式为 base64 编码图片（不含 data: 前缀）")
    fitness_goal: str = Field(default="减脂", description="健身目标：减脂 / 增肌 / 维持")
    mime_type: str = Field(default="image/jpeg", description="图片 MIME 类型（image 模式使用）")

    @model_validator(mode="after")
    def validate_image(self):
        """图片模式下的格式与大小校验"""
        if self.mode == "image":
            if self.mime_type not in ALLOWED_MIME_TYPES:
                raise ValueError(f"不支持的图片格式：{self.mime_type}")
            try:
                decoded = base64.b64decode(self.content, validate=True)
            except Exception:
                raise ValueError("图片 base64 编码无效")
            if len(decoded) > MAX_IMAGE_BYTES:
                raise ValueError("图片过大：解码后不能超过 10MB")
        return self


class ToolCallInfo(BaseModel):
    """单次工具调用信息"""
    tool: str
    status: str
    input: str | None = None
    output: str | None = None


class DietResponse(BaseModel):
    success: bool
    report: str | None = None
    elapsed_seconds: float | None = None
    error: str | None = None
    tool_trace: list[ToolCallInfo] | None = None


# ═══════════════════════════════════════════════════════════
# 【新增】异步任务相关请求/响应模型
# ═══════════════════════════════════════════════════════════

class TaskCreateResponse(BaseModel):
    """创建任务后立即返回 task_id"""
    success: bool
    task_id: str
    message: str = "任务已创建，请轮询 /api/generate_diet/task/{task_id} 查询结果"


class TaskStatusResponse(BaseModel):
    """查询任务状态"""
    task_id: str
    status: str  # pending / running / success / failed
    progress: str | None = None      # 识别中 / 搜索中 / 计算中 / 生成报告中
    report: str | None = None
    elapsed_seconds: float | None = None
    error: str | None = None
    tool_trace: list[ToolCallInfo] | None = None


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
    """健康检查：服务状态 + 数据库连通性（Docker healthcheck 依赖此接口）"""
    db_ok = True
    try:
        with get_conn() as conn:
            conn.ping(reconnect=False)
    except Exception:
        db_ok = False
    return {
        "status": "ok",
        "model": "qwen3.5-plus + qwen-vl-plus",
        "database": "ok" if db_ok else "unavailable",
    }


@app.post("/api/generate_diet")
def generate_diet(req: DietRequest, _: None = Depends(verify_api_token)):
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

        report, trace = invoke_agent_with_trace(agent, message_content)
        elapsed = round(time.time() - start, 1)

        # 验证热量工具是否被调用
        calorie_tools = {"calculate_food_calories", "estimate_meal_calories"}
        called_tools = {t["tool"] for t in trace if t["status"] == "completed"}
        calorie_tool_called = bool(called_tools & calorie_tools)

        if not calorie_tool_called:
            logger.warning("⚠️ API 调用中未调用热量计算工具，热量数据可信度低！")
            report += "\n\n---\n⚠️ **注意**：本次分析未成功调用热量计算工具，热量数据可信度较低。"

        # 构造工具调用轨迹（截断过长的输入/输出）
        tool_trace = []
        for step in trace:
            inp = str(step.get("input", ""))
            out = str(step.get("output", ""))
            if len(inp) > 500:
                inp = inp[:500] + "..."
            if len(out) > 500:
                out = out[:500] + "..."
            tool_trace.append(ToolCallInfo(
                tool=step["tool"],
                status=step["status"],
                input=inp,
                output=out,
            ))

        return DietResponse(
            success=True,
            report=report,
            elapsed_seconds=elapsed,
            tool_trace=tool_trace,
        )

    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return DietResponse(
            success=False,
            error=f"分析失败：{str(e)}",
            elapsed_seconds=elapsed
        )


# ═══════════════════════════════════════════════════════════
# 【新增】异步任务：后台 worker 函数
# 将原有同步执行的完整业务逻辑移入此函数，按 4 个进度节点写入任务缓存
# ═══════════════════════════════════════════════════════════

def _run_diet_task(task_id: str, req: DietRequest):
    """
    后台异步执行原 agent.invoke 完整逻辑（图片解析、素材检索、大模型食谱生成）。
    分 4 个进度节点写入任务缓存：识别中→搜索中→计算中→生成报告中。
    处理超时、异常捕获：执行报错自动标记任务状态 failed。
    """
    start = time.time()

    try:
        # ── 节点 1：识别中 ──
        _update_task(task_id, status=TASK_RUNNING, progress=PROGRESS_RECOGNIZING)

        if req.mode == "image":
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
            message_content = f"{req.content}。健身目标：{req.fitness_goal}"
            agent = text_agent

        # ── 节点 2：搜索中（invoke 内部工具事件驱动真实进度） ──
        _update_task(task_id, progress=PROGRESS_SEARCHING)

        report, trace = invoke_agent_with_trace(
            agent, message_content,
            extra_callbacks=[TaskProgressCallback(task_id)],
        )

        # ── 节点 3：计算中（验证热量工具调用） ──
        _update_task(task_id, progress=PROGRESS_CALCULATING)

        calorie_tools = {"calculate_food_calories", "estimate_meal_calories"}
        called_tools = {t["tool"] for t in trace if t["status"] == "completed"}
        calorie_tool_called = bool(called_tools & calorie_tools)

        if not calorie_tool_called:
            logger.warning("⚠️ 异步任务中未调用热量计算工具，热量数据可信度低！")
            report += "\n\n---\n⚠️ **注意**：本次分析未成功调用热量计算工具，热量数据可信度较低。"

        # ── 节点 4：生成报告中（构造工具调用轨迹） ──
        _update_task(task_id, progress=PROGRESS_GENERATING)

        tool_trace = []
        for step in trace:
            inp = str(step.get("input", ""))
            out = str(step.get("output", ""))
            if len(inp) > 500:
                inp = inp[:500] + "..."
            if len(out) > 500:
                out = out[:500] + "..."
            tool_trace.append(ToolCallInfo(
                tool=step["tool"],
                status=step["status"],
                input=inp,
                output=out,
            ))

        elapsed = round(time.time() - start, 1)

        # ── 完成：标记 success ──
        result_dict = {
            "report": report,
            "elapsed_seconds": elapsed,
            "tool_trace": [t.model_dump() for t in tool_trace],
        }
        _update_task(task_id, status=TASK_SUCCESS, progress=None, result=result_dict, error=None)

    except Exception as e:
        logger.error(f"异步任务 {task_id} 执行失败：{e}", exc_info=True)
        elapsed = round(time.time() - start, 1)
        _update_task(task_id, status=TASK_FAILED, progress=None, error=f"分析失败：{str(e)}")


# ═══════════════════════════════════════════════════════════
# 【新增】异步任务接口 1：创建任务
# ═══════════════════════════════════════════════════════════

@app.post("/api/generate_diet/task")
def create_diet_task(req: DietRequest, _: None = Depends(verify_api_token)):
    """
    食谱生成异步任务创建接口
    - 接收前端入参，生成唯一 task_id
    - 创建任务并立即返回 task_id
    - 后台新开子线程异步执行原 agent.invoke 完整逻辑
    """
    # 每次创建新任务前，顺手清理过期任务（数据库异常不影响主流程）
    try:
        _cleanup_expired_tasks()
    except Exception as e:
        logger.warning(f"清理过期任务失败（忽略）：{e}")

    task_id = uuid.uuid4().hex

    # 创建 pending 状态的任务（写入 MySQL）
    _create_task(task_id, status=TASK_PENDING)

    # 后台新线程异步执行
    thread = threading.Thread(target=_run_diet_task, args=(task_id, req), daemon=True)
    thread.start()

    return TaskCreateResponse(success=True, task_id=task_id)


# ═══════════════════════════════════════════════════════════
# 【新增】异步任务接口 2：查询任务状态
# ═══════════════════════════════════════════════════════════

@app.get("/api/generate_diet/task/{task_id}")
def get_diet_task_status(task_id: str, _: None = Depends(verify_api_token)):
    """
    根据 task_id 查询任务状态，同步返回进度标识与结果
    - pending：任务已创建，等待执行
    - running：正在执行，progress 字段显示当前进度节点
    - success：执行成功，result 中包含 report / elapsed_seconds / tool_trace
    - failed：执行失败，error 字段包含错误信息
    """
    task = _get_task(task_id)

    if task is None:
        return {"success": False, "error": f"任务不存在：{task_id}"}

    # 构造返回体
    resp = TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress"),
        error=task.get("error"),
    )

    result = task.get("result")

    if result:
        resp.report = result.get("report")
        resp.elapsed_seconds = result.get("elapsed_seconds")
        trace_raw = result.get("tool_trace")
        if trace_raw:
            resp.tool_trace = [ToolCallInfo(**t) for t in trace_raw]

    return resp


@app.get("/api/recommend")
async def recommend(goal: str = "减脂", _: None = Depends(verify_api_token)):
    """
    精选推荐食谱（从 MySQL 读取，数据库不可用时回退静态数据）
    - 可按健身目标过滤：减脂 / 增肌 / 维持
    """
    target_tag = {"增肌": "增肌推荐", "减脂": "减脂推荐"}.get(goal)

    rows = []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if target_tag:
                    cur.execute(
                        "SELECT * FROM recommendations "
                        "WHERE JSON_CONTAINS(tags, %s) ORDER BY id",
                        (json.dumps(target_tag, ensure_ascii=False),),
                    )
                else:
                    cur.execute("SELECT * FROM recommendations ORDER BY id")
                rows = cur.fetchall()
    except Exception as e:
        logger.warning(f"数据库不可用，回退到内置静态数据：{e}")

    if rows:
        items = []
        for r in rows:
            tags = r["tags"]
            if isinstance(tags, str):
                tags = json.loads(tags)
            items.append(RecommendItem(
                id=r["id"], name=r["name"], calories=r["calories"],
                tags=tags, description=r["description"],
                nutrition_score=r["nutrition_score"],
                difficulty_score=r["difficulty_score"],
            ))
    else:
        items = _recommend_from_static(goal)

    return RecommendResponse(success=True, recommendations=items)


def _recommend_from_static(goal: str) -> list[RecommendItem]:
    """数据库不可用时的静态兜底数据"""
    if goal == "增肌":
        return [r for r in RECOMMENDATIONS if "增肌推荐" in r.tags]
    if goal == "减脂":
        return [r for r in RECOMMENDATIONS if "减脂推荐" in r.tags]
    return RECOMMENDATIONS
