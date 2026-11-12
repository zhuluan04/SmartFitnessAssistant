"""热量计算核心逻辑单元测试（纯本地逻辑，不依赖网络与真实模型）"""
from app.langchain import (
    normalize_food_name,
    calculate_food_calories,
    estimate_meal_calories,
)


class TestNormalizeFoodName:
    """食材名称标准化"""

    def test_exact_match(self):
        assert normalize_food_name("鸡胸肉") == ("鸡胸肉", True)

    def test_alias_match(self):
        assert normalize_food_name("鸡胸") == ("鸡胸肉", True)
        assert normalize_food_name("西红柿") == ("番茄", True)

    def test_keyword_fuzzy_match(self):
        name, is_exact = normalize_food_name("香煎鸡胸肉片")
        assert name == "鸡胸肉"
        assert is_exact is False

    def test_unknown_returns_original(self):
        name, is_exact = normalize_food_name("榴莲")
        assert name == "榴莲"
        assert is_exact is False


class TestCalculateFoodCalories:
    """食材卡路里精确计算"""

    def test_basic_calculation(self):
        result = calculate_food_calories.invoke(
            {"food_items": {"鸡胸肉": 150, "西兰花": 100}}
        )
        assert result["total_kcal"] == 233.5  # 133*1.5 + 34*1.0
        assert result["is_complete"] is True
        assert len(result["items"]) == 2
        assert result["items"][0]["source"] == "local_table"

    def test_alias_normalized(self):
        result = calculate_food_calories.invoke({"food_items": {"鸡胸": 100}})
        assert result["total_kcal"] == 133.0
        assert result["items"][0]["normalized_name"] == "鸡胸肉"

    def test_unknown_food_excluded(self):
        result = calculate_food_calories.invoke({"food_items": {"榴莲": 100}})
        assert result["total_kcal"] == 0.0
        assert result["is_complete"] is False
        assert result["unknown_items"][0]["name"] == "榴莲"

    def test_mixed_known_and_unknown(self):
        result = calculate_food_calories.invoke(
            {"food_items": {"鸡胸肉": 100, "榴莲": 50}}
        )
        assert result["total_kcal"] == 133.0
        assert result["is_complete"] is False
        assert len(result["items"]) == 1
        assert len(result["unknown_items"]) == 1


class TestEstimateMealCalories:
    """成品菜肴热量估算"""

    def test_with_known_ingredient(self):
        result = estimate_meal_calories.invoke(
            {"meal_name": "宫保鸡丁", "estimated_weight_g": 200, "main_ingredients": ["鸡胸肉"]}
        )
        kcal = float(result["估算卡路里"].split(" ")[0])
        assert 300 <= kcal <= 310  # 133 * 1.15（烹饪上浮）* 2 ≈ 306
        assert result["置信度"] == "中"

    def test_without_ingredients(self):
        result = estimate_meal_calories.invoke({"meal_name": "神秘菜肴"})
        # 通用估算 120 kcal/100g * 200g = 240
        assert result["估算卡路里"] == "240.0 kcal"
        assert result["置信度"] == "低"
