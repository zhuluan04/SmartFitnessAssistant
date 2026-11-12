"""API 层参数校验与鉴权单元测试"""
import base64

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import DietRequest, verify_api_token


class TestDietRequest:
    """请求体校验（重点是图片模式）"""

    def test_text_mode_ok(self):
        req = DietRequest(mode="text", content="鸡胸肉 150 克")
        assert req.mode == "text"
        assert req.fitness_goal == "减脂"

    def test_image_mode_valid(self):
        data = base64.b64encode(b"fake-image-bytes").decode()
        req = DietRequest(mode="image", content=data, mime_type="image/png")
        assert req.mime_type == "image/png"

    def test_image_mode_invalid_base64(self):
        with pytest.raises(ValidationError):
            DietRequest(mode="image", content="!!!not-base64!!!")

    def test_image_mode_bad_mime(self):
        data = base64.b64encode(b"x").decode()
        with pytest.raises(ValidationError):
            DietRequest(mode="image", content=data, mime_type="application/pdf")

    def test_image_too_large(self, monkeypatch):
        monkeypatch.setattr("app.api.MAX_IMAGE_BYTES", 10)
        data = base64.b64encode(b"y" * 100).decode()
        with pytest.raises(ValidationError):
            DietRequest(mode="image", content=data)


class TestVerifyApiToken:
    """API Token 鉴权"""

    def test_empty_expected_skips_check(self, monkeypatch):
        monkeypatch.setenv("API_AUTH_TOKEN", "")
        assert verify_api_token("anything") is None

    def test_valid_token_passes(self, monkeypatch):
        monkeypatch.setenv("API_AUTH_TOKEN", "secret-123")
        assert verify_api_token("secret-123") is None

    def test_invalid_token_raises_401(self, monkeypatch):
        monkeypatch.setenv("API_AUTH_TOKEN", "secret-123")
        with pytest.raises(HTTPException) as exc_info:
            verify_api_token("wrong-token")
        assert exc_info.value.status_code == 401
