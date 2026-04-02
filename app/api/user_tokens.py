"""
用户自助 API Key 管理（用户只能管理自己的 Token）
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.base import get_db
from app.models.user import User
from app.models.token import Token
from app.api.auth import require_user
from app.services import token_service
from app.utils.helpers import mask_token_key
from app.schemas.token import TokenCreate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tokens", tags=["user-tokens"])


class UserTokenCreate(BaseModel):
    name: str = "My API Key"
    expires_days: Optional[int] = None   # None = 永不过期


@router.post("")
def create_my_token(
    data: UserTokenCreate,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """用户创建自己的 API Key"""
    # 限制普通用户最多5个Token
    count = db.query(Token).filter(Token.user_id == user.id, Token.status == 1).count()
    if count >= 5:
        raise HTTPException(status_code=400, detail="Max 5 active API keys allowed")

    from datetime import datetime, timedelta, timezone
    expires_at = None
    if data.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_days)

    create_data = TokenCreate(
        user_id=user.id,
        name=data.name,
        total_quota=float(user.quota or 0),  # 继承用户额度
        rate_limit=60,                         # 普通用户60次/分钟
        allowed_models="*",
        expires_at=expires_at,
    )
    token, full_key = token_service.create_token(db, create_data)

    return {
        "id": token.id,
        "name": token.name,
        "token_key": full_key,   # 仅返回一次完整密钥
        "total_quota": float(token.total_quota),
        "rate_limit": token.rate_limit,
        "expires_at": token.expires_at,
        "created_at": token.created_at,
        "message": "Save your API key now. It won't be shown again.",
    }


@router.get("")
def list_my_tokens(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """列出自己的 API Keys"""
    tokens = db.query(Token).filter(Token.user_id == user.id).order_by(Token.id.desc()).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "token_key": mask_token_key(t.token_key),
            "total_quota": float(t.total_quota),
            "used_quota": float(t.used_quota or 0),
            "rate_limit": t.rate_limit,
            "expires_at": t.expires_at,
            "status": t.status,
            "created_at": t.created_at,
            "last_used_at": t.last_used_at,
        }
        for t in tokens
    ]


@router.delete("/{token_id}")
def delete_my_token(
    token_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """删除自己的 API Key"""
    token = db.query(Token).filter(Token.id == token_id, Token.user_id == user.id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    db.delete(token)
    db.commit()
    return {"message": "API key deleted"}
