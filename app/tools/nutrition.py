"""
营养数据工具：本地热量表 + USDA FoodData Central 兜底查询

查询策略：本地热量表优先（快、稳、无网络依赖）；
未命中且配置了 USDA_API_KEY 时，调用 USDA 官方 API 兜底；
USDA 未配置或查询失败时返回 None，由调用方按"未收录"处理。
"""
import os
import logging

from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("calorie_agent")

# 本地热量表：每 100g 千卡（USDA 作为扩展兜底）
FOOD_CALORIE_TABLE = {
    "鸡胸肉": 133,
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
}

_USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"


def query_usda_food(food_name: str) -> dict | None:
    """
    调用 USDA FoodData Central 搜索食材营养数据。
    成功返回 {"kcal_per_100g": float, "description": str, "fdc_id": int}；
    未配置 Key / 未命中 / 网络失败均返回 None（静默降级，不抛异常）。
    """
    api_key = os.getenv("USDA_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        import httpx

        resp = httpx.get(
            _USDA_SEARCH_URL,
            params={
                "query": food_name,
                "pageSize": 1,
                "dataType": "Foundation,SR Legacy",
                "api_key": api_key,
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        foods = (resp.json() or {}).get("foods") or []
        if not foods:
            return None

        food = foods[0]
        nutrients = {
            n.get("nutrientName"): n.get("value")
            for n in food.get("foodNutrients", [])
        }
        kcal = nutrients.get("Energy (Atwater General Factors)") or nutrients.get("Energy")
        if kcal is None:
            return None

        return {
            "kcal_per_100g": round(float(kcal), 1),
            "description": food.get("description", food_name),
            "fdc_id": food.get("fdcId"),
        }
    except Exception as e:
        logger.warning(f"USDA 查询失败（{food_name}）：{e}")
        return None


def lookup_calorie(food_name: str) -> dict | None:
    """
    统一热量查询入口：本地表优先，USDA 兜底。
    返回 {"kcal_per_100g": float, "source": "local_table" | "usda"} 或 None。
    """
    if food_name in FOOD_CALORIE_TABLE:
        return {
            "kcal_per_100g": FOOD_CALORIE_TABLE[food_name],
            "source": "local_table",
        }

    usda = query_usda_food(food_name)
    if usda:
        logger.info(f"🌐 食材'{food_name}' 通过 USDA 查询到热量：{usda['kcal_per_100g']} kcal/100g")
        return {
            "kcal_per_100g": usda["kcal_per_100g"],
            "source": "usda",
        }
    return None
