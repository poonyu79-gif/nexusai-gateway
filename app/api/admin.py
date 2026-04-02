"""
管理后台 API：Token/Channel/User CRUD + 统计日志
所有接口需要管理员认证
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import httpx

from app.models.base import get_db
from app.models.user import User
from app.core.auth import get_admin_token
from app.schemas.token import TokenCreate, TokenUpdate
from app.schemas.channel import ChannelCreate, ChannelUpdate
from app.services import token_service, channel_service, log_service
from app.utils.helpers import mask_token_key, decrypt_api_key
import bcrypt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Token 管理 ────────────────────────────────────────────────────────────────

@router.post("/tokens")
def create_token(
    data: TokenCreate,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    """创建令牌，返回完整 token_key（仅此一次）"""
    try:
        token, full_key = token_service.create_token(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": token.id,
        "user_id": token.user_id,
        "name": token.name,
        "token_key": full_key,          # 完整密钥，仅返回一次
        "total_quota": float(token.total_quota),
        "used_quota": float(token.used_quota),
        "rate_limit": token.rate_limit,
        "allowed_models": token.allowed_models,
        "expires_at": token.expires_at,
        "status": token.status,
        "created_at": token.created_at,
        "message": "请保存好您的 Token，此后将无法再次查看完整密钥",
    }


@router.get("/tokens")
def list_tokens(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user_id: Optional[int] = None,
    status: Optional[int] = None,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    items, total = token_service.list_tokens(db, page, size, user_id, status)
    data = []
    for t in items:
        data.append({
            "id": t.id,
            "user_id": t.user_id,
            "name": t.name,
            "token_key": mask_token_key(t.token_key),  # 只显示前10位
            "total_quota": float(t.total_quota),
            "used_quota": float(t.used_quota or 0),
            "rate_limit": t.rate_limit,
            "allowed_models": t.allowed_models,
            "expires_at": t.expires_at,
            "status": t.status,
            "created_at": t.created_at,
            "last_used_at": t.last_used_at,
        })
    return {"data": data, "total": total, "page": page, "size": size}


@router.get("/tokens/{token_id}")
def get_token(
    token_id: int,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    token = token_service.get_token(db, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@router.put("/tokens/{token_id}")
def update_token(
    token_id: int,
    data: TokenUpdate,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    token = token_service.update_token(db, token_id, data)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@router.delete("/tokens/{token_id}")
def delete_token(
    token_id: int,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    if not token_service.delete_token(db, token_id):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"message": "Token deleted"}


# ─── Channel 管理 ──────────────────────────────────────────────────────────────

@router.post("/channels")
def create_channel(
    data: ChannelCreate,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    ch = channel_service.create_channel(db, data)
    return channel_service.mask_channel_key(ch)


@router.get("/channels")
def list_channels(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=200),
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    items, total = channel_service.list_channels(db, page, size)
    return {"data": [channel_service.mask_channel_key(ch) for ch in items], "total": total, "page": page, "size": size}


@router.put("/channels/{channel_id}")
def update_channel(
    channel_id: int,
    data: ChannelUpdate,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    ch = channel_service.update_channel(db, channel_id, data)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel_service.mask_channel_key(ch)


@router.delete("/channels/{channel_id}")
def delete_channel(
    channel_id: int,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    if not channel_service.delete_channel(db, channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"message": "Channel deleted"}


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: int,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    """测试渠道可用性（发送一个简单请求）"""
    ch = channel_service.get_channel(db, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    try:
        api_key = decrypt_api_key(ch.api_key)
        test_body = {
            "model": ch.supported_models.split(",")[0].strip(),
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        if ch.channel_type == "claude":
            url = f"{ch.base_url.rstrip('/')}/messages"
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        elif ch.channel_type == "azure":
            model = test_body["model"]
            url = f"{ch.base_url.rstrip('/')}/openai/deployments/{model}/chat/completions?api-version=2024-02-01"
            headers = {"api-key": api_key, "Content-Type": "application/json"}
        else:
            url = f"{ch.base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers, json=test_body)

        if resp.status_code == 200:
            # 重置错误计数
            ch.error_count = 0
            ch.status = 1
            db.commit()
            return {"success": True, "status_code": resp.status_code, "message": "渠道测试成功"}
        else:
            return {"success": False, "status_code": resp.status_code, "message": resp.text[:200]}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ─── 统计 ──────────────────────────────────────────────────────────────────────

@router.get("/stats/overview")
def stats_overview(
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    from app.models.channel import Channel
    from app.models.token import Token
    from sqlalchemy import func

    base = log_service.get_overview_stats(db)
    active_channels = db.query(func.count(Channel.id)).filter(Channel.status == 1).scalar() or 0
    active_tokens = db.query(func.count(Token.id)).filter(Token.status == 1).scalar() or 0
    base["active_channels"] = active_channels
    base["active_tokens"] = active_tokens
    return base


@router.get("/stats/models")
def stats_models(
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    return log_service.get_model_stats(db)


@router.get("/stats/daily")
def stats_daily(
    days: int = Query(default=30, ge=1, le=90),
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    return log_service.get_daily_stats(db, days)


@router.get("/stats/tokens")
def stats_tokens(
    limit: int = Query(default=10, ge=1, le=50),
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    return log_service.get_token_stats(db, limit)


# ─── 日志 ──────────────────────────────────────────────────────────────────────

@router.get("/logs")
def query_logs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    token_id: Optional[int] = None,
    model: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    items, total = log_service.query_logs(db, page, size, token_id, model, start_time, end_time)
    data = [
        {
            "id": l.id,
            "request_model": l.request_model,
            "actual_model": l.actual_model,
            "input_tokens": l.input_tokens,
            "output_tokens": l.output_tokens,
            "total_tokens": l.total_tokens,
            "cost": float(l.cost or 0),
            "duration_ms": l.duration_ms,
            "is_stream": l.is_stream,
            "status_code": l.status_code,
            "error_message": l.error_message,
            "client_ip": l.client_ip,
            "created_at": l.created_at,
        }
        for l in items
    ]
    return {"data": data, "total": total, "page": page, "size": size}


# ─── 用户管理 ──────────────────────────────────────────────────────────────────

@router.post("/users")
def create_user(
    username: str,
    password: str,
    role: str = "user",
    quota: float = 0,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(username=username, password_hash=pw_hash, role=role, quota=quota)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role, "quota": float(user.quota)}


@router.get("/users")
def list_users(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    total = q.count()
    items = q.order_by(User.id).offset((page - 1) * size).limit(size).all()
    data = [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "quota": float(u.quota or 0),
            "used_quota": float(u.used_quota or 0),
            "status": u.status,
            "created_at": u.created_at,
        }
        for u in items
    ]
    return {"data": data, "total": total, "page": page, "size": size}


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    quota: Optional[float] = None,
    status: Optional[int] = None,
    admin: dict = Depends(get_admin_token),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if quota is not None:
        user.quota = quota
    if status is not None:
        user.status = status
    db.commit()
    return {"id": user.id, "username": user.username, "quota": float(user.quota), "status": user.status}
