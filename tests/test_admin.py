"""
管理后台 API 测试
"""
import pytest


def test_create_token(client, admin_token, test_user):
    """创建令牌"""
    r = client.post(
        "/admin/tokens",
        json={"name": "Test Token", "user_id": test_user.id, "total_quota": 10.0, "rate_limit": 60},
        headers={"Authorization": f"Bearer {admin_token.token_key}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "token_key" in data
    assert data["token_key"].startswith("sk-")
    assert data["name"] == "Test Token"


def test_list_tokens(client, admin_token, user_token):
    """列出令牌"""
    r = client.get(
        "/admin/tokens",
        headers={"Authorization": f"Bearer {admin_token.token_key}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "total" in data
    assert data["total"] >= 1


def test_create_channel(client, admin_token):
    """创建渠道"""
    r = client.post(
        "/admin/channels",
        json={
            "name": "Test OpenAI",
            "channel_type": "openai",
            "api_key": "sk-test-key",
            "base_url": "https://api.openai.com/v1",
            "supported_models": "gpt-4o,gpt-4o-mini",
            "priority": 0,
            "weight": 1,
            "timeout": 60,
            "max_retries": 2,
        },
        headers={"Authorization": f"Bearer {admin_token.token_key}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Test OpenAI"
    # api_key 应该被隐藏
    assert "sk-test-key" not in data["api_key"]


def test_stats_overview(client, admin_token):
    """总览统计接口"""
    r = client.get(
        "/admin/stats/overview",
        headers={"Authorization": f"Bearer {admin_token.token_key}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "total_requests" in data
    assert "today_cost" in data
    assert "active_channels" in data


def test_admin_required(client, user_token):
    """非管理员无法访问管理接口"""
    r = client.get(
        "/admin/tokens",
        headers={"Authorization": f"Bearer {user_token.token_key}"},
    )
    assert r.status_code == 403


def test_delete_token(client, admin_token, db, test_user):
    """软删除令牌"""
    from app.utils.helpers import generate_token_key
    from app.models.token import Token
    key = generate_token_key()
    t = Token(user_id=test_user.id, token_key=key, name="ToDelete", total_quota=-1, rate_limit=60, status=1)
    db.add(t)
    db.commit()

    r = client.delete(
        f"/admin/tokens/{t.id}",
        headers={"Authorization": f"Bearer {admin_token.token_key}"},
    )
    assert r.status_code == 200

    db.refresh(t)
    assert t.status == -1  # 软删除
