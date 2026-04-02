"""
Token CRUD 服务层
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.token import Token
from app.models.user import User
from app.utils.helpers import generate_token_key, mask_token_key
from app.schemas.token import TokenCreate, TokenUpdate

logger = logging.getLogger(__name__)


def create_token(db: Session, data: TokenCreate) -> tuple[Token, str]:
    """
    创建令牌，返回 (token_obj, full_token_key)
    full_token_key 仅返回一次，不再明文存储
    """
    # 检查用户是否存在
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise ValueError(f"用户 user_id={data.user_id} 不存在")

    token_key = generate_token_key()

    expires_at = None
    if data.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_days)

    token = Token(
        user_id=data.user_id,
        token_key=token_key,
        name=data.name,
        total_quota=data.total_quota,
        used_quota=0,
        rate_limit=data.rate_limit,
        allowed_models=data.allowed_models,
        allowed_ips=data.allowed_ips,
        expires_at=expires_at,
        status=1,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token, token_key


def list_tokens(
    db: Session, page: int = 1, size: int = 20, user_id: int = None, status: int = None
) -> tuple[list[Token], int]:
    """列出令牌（分页）"""
    q = db.query(Token).filter(Token.status != -1)  # 排除软删除
    if user_id is not None:
        q = q.filter(Token.user_id == user_id)
    if status is not None:
        q = q.filter(Token.status == status)
    total = q.count()
    items = q.order_by(Token.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return items, total


def get_token(db: Session, token_id: int) -> Token | None:
    return db.query(Token).filter(Token.id == token_id, Token.status != -1).first()


def update_token(db: Session, token_id: int, data: TokenUpdate) -> Token | None:
    token = get_token(db, token_id)
    if not token:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(token, field, value)
    db.commit()
    db.refresh(token)
    return token


def delete_token(db: Session, token_id: int) -> bool:
    """软删除：将 status 设为 -1"""
    token = get_token(db, token_id)
    if not token:
        return False
    token.status = -1
    db.commit()
    return True
