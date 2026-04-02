"""
认证模块测试
"""
import pytest
from datetime import datetime, timedelta
from app.models.token import Token
from app.utils.helpers import generate_token_key


def test_missing_token(client):
    """无 Token 返回 401"""
    r = client.post("/v1/chat/completions", json={"model": "gpt-4o", "messages": []})
    assert r.status_code == 401


def test_invalid_token(client):
    """无效 Token 返回 401"""
    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": []},
        headers={"Authorization": "Bearer sk-invalid-token"},
    )
    assert r.status_code == 401


def test_disabled_token(client, db, user_token):
    """禁用 Token 返回 403"""
    user_token.status = 0
    db.commit()

    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": []},
        headers={"Authorization": f"Bearer {user_token.token_key}"},
    )
    assert r.status_code == 403
    assert "disabled" in r.json()["detail"]["error"]["message"].lower()


def test_expired_token(client, db, test_user):
    """过期 Token 返回 403"""
    key = generate_token_key()
    token = Token(
        user_id=test_user.id,
        token_key=key,
        name="Expired",
        total_quota=-1,
        used_quota=0,
        rate_limit=60,
        allowed_models="*",
        status=1,
        expires_at=datetime.utcnow() - timedelta(days=1),  # 昨天过期
    )
    db.add(token)
    db.commit()

    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": []},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 403
    assert "expired" in r.json()["detail"]["error"]["message"].lower()


def test_quota_exceeded(client, db, test_user):
    """额度耗尽 返回 403"""
    key = generate_token_key()
    token = Token(
        user_id=test_user.id,
        token_key=key,
        name="Empty Quota",
        total_quota=1.0,
        used_quota=1.0,  # 已用完
        rate_limit=60,
        allowed_models="*",
        status=1,
    )
    db.add(token)
    db.commit()

    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": []},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 403
    assert "quota" in r.json()["detail"]["error"]["message"].lower()


def test_model_not_allowed(client, user_token):
    """请求不允许的模型 返回 403（user_token 只允许 gpt-4o,gpt-4o-mini）"""
    r = client.post(
        "/v1/chat/completions",
        json={"model": "claude-3-5-sonnet-20241022", "messages": []},
        headers={"Authorization": f"Bearer {user_token.token_key}"},
    )
    # 认证通过但模型权限被代理服务拒绝
    assert r.status_code in (403, 503)


def test_valid_token_reaches_proxy(client, user_token, test_channel):
    """有效 Token 能通过认证进入代理（上游可能失败，但认证本身通过）"""
    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {user_token.token_key}"},
    )
    # 上游是假 URL，会失败，但不是 401/403
    assert r.status_code not in (401, 403)
