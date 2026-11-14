"""大模型结构化输出解析的单元测试"""

from app.core.parser import extract_json, normalize_diet_report


class TestExtractJson:
    """JSON 提取对各类模型输出的容错能力"""

    def test_plain_json(self):
        data = extract_json('{"total_calories": 246.8, "recipes": [{"name": "A"}]}')
        assert data["total_calories"] == 246.8

    def test_fenced_json(self):
        text = '```json\n{"total_calories": 100, "recipes": [{"name": "B"}]}\n```'
        assert extract_json(text)["total_calories"] == 100

    def test_json_with_surrounding_text(self):
        """模型在 JSON 前后加了解释性文字时仍能提取"""
        text = '分析如下：\n{"total_calories": 200, "recipes": [{"name": "C"}]}\n仅供参考。'
        assert extract_json(text)["total_calories"] == 200

    def test_non_json_returns_none(self):
        assert extract_json("抱歉，我无法识别这张图片中的食物。") is None

    def test_empty_input_returns_none(self):
        assert extract_json("") is None


class TestNormalizeDietReport:
    """归一化：带单位的数值、缺失字段、非法元素"""

    def test_units_and_missing_fields(self):
        raw = {
            "total_calories": "246.8 kcal",
            "recipes": [{"name": "A", "calories": "100 kcal", "protein_hint": "约32g"}],
        }
        result = normalize_diet_report(raw)

        assert result["total_calories"] == 246.8
        assert result["recipes"][0]["calories"] == 100.0
        assert result["recipes"][0]["steps"] == []
        assert result["items"] == []
        assert result["warning"] is None

    def test_invalid_recipe_skipped(self):
        """缺少 name 或非对象的条目应被丢弃，不影响其余条目"""
        raw = {"recipes": [{"calories": 100}, "不是对象", {"name": "有效", "calories": 120}]}
        result = normalize_diet_report(raw)

        assert [r["name"] for r in result["recipes"]] == ["有效"]

    def test_empty_warning_becomes_none(self):
        assert normalize_diet_report({"recipes": [], "warning": ""})["warning"] is None

    def test_steps_truncated_to_limit(self):
        raw = {"recipes": [{"name": "A", "steps": ["1", "2", "3", "4", "5"]}]}
        assert len(normalize_diet_report(raw)["recipes"][0]["steps"]) == 4
