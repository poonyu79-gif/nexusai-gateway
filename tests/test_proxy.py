"""
代理服务测试（使用 httpx mock 模拟上游响应）
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


MOCK_OPENAI_RESPONSE = {
    "id": "chatcmpl-test123",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "gpt-4o",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def test_normal_request_no_channel(client, user_token):
    """无可用渠道时返回 503"""
    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {user_token.token_key}"},
    )
    assert r.status_code == 503


def test_models_list(client, user_token, test_channel):
    """模型列表接口"""
    r = client.get(
        "/v1/models",
        headers={"Authorization": f"Bearer {user_token.token_key}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    assert len(data["data"]) > 0
    model_ids = [m["id"] for m in data["data"]]
    assert "gpt-4o" in model_ids


def test_health(client):
    """健康检查接口"""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_calculate_cost_after_request(db, test_user, user_token, test_channel):
    """正常请求后额度被扣减"""
    from app.services.proxy_service import proxy_service
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_OPENAI_RESPONSE

    initial_used = float(user_token.used_quota or 0)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        token_info = {
            "token_id": user_token.id,
            "user_id": test_user.id,
            "token_key": user_token.token_key,
            "allowed_models": "*",
            "total_quota": float(user_token.total_quota),
            "used_quota": initial_used,
            "client_ip": "127.0.0.1",
        }
        result = await proxy_service.handle_request(
            {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            token_info,
            db,
        )

    assert result["choices"][0]["message"]["content"] == "Hello!"
    db.refresh(user_token)
    # 额度应该增加了
    assert float(user_token.used_quota) > initial_used
