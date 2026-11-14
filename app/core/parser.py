"""
大模型结构化输出解析

职责：把模型返回的自由文本稳健地解析为前端可直接渲染的 dict。
策略：围栏剥离 → 直接解析 → 花括号截取，全部失败返回 None（调用方降级展示原文）。
"""

import json
import re
import logging

logger = logging.getLogger("calorie_agent")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def extract_json(text: str) -> dict | None:
    """
    从模型输出中提取含 recipes 字段的 JSON 对象。
    依次尝试：剥离 ```json 围栏 → 原文直接解析 → 截取首个 { 到末个 }。
    全部失败返回 None，由调用方降级为纯文本展示。
    """
    if not text:
        return None

    candidates = []
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for raw in candidates:
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            return data

    logger.warning("模型输出无法解析为 JSON，降级为纯文本展示")
    return None


def _to_float(value) -> float | None:
    """兼容模型返回 246.8 / "246.8 kcal" / "约32g" 三种形态"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 1)
    if isinstance(value, str):
        matched = _NUM_RE.search(value)
        if matched:
            return round(float(matched.group()), 1)
    return None


def _to_str(value) -> str:
    return str(value).strip() if value is not None else ""


def _to_str_list(value, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def normalize_diet_report(data: dict) -> dict:
    """
    把模型 JSON 规整为前端契约：缺字段补默认值、数值转 float、列表截断。
    保证 WXML 渲染时不会因字段缺失或类型不符而报错。
    """
    recipes = []
    for raw in (data.get("recipes") or [])[:3]:
        if not isinstance(raw, dict):
            continue
        name = _to_str(raw.get("name"))
        if not name:
            continue
        recipes.append({
            "name": name,
            "calories": _to_float(raw.get("calories")),
            "protein_hint": _to_str(raw.get("protein_hint")),
            "reason": _to_str(raw.get("reason")),
            "steps": _to_str_list(raw.get("steps"), 4),
        })

    items = []
    for raw in (data.get("items") or [])[:12]:
        if not isinstance(raw, dict):
            continue
        name = _to_str(raw.get("name"))
        if not name:
            continue
        items.append({
            "name": name,
            "grams": _to_float(raw.get("grams")),
            "kcal": _to_float(raw.get("kcal")),
            "estimated": bool(raw.get("estimated")),
        })

    warning = _to_str(data.get("warning"))

    return {
        "total_calories": _to_float(data.get("total_calories")),
        "basis": _to_str(data.get("basis")),
        "items": items,
        "recipes": recipes,
        "tips": _to_str_list(data.get("tips"), 3),
        "warning": warning or None,
    }
