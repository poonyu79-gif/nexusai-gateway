"""
用户注册 / 登录 / 个人信息接口
"""
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
import bcrypt
from jose import jwt, JWTError

from app.models.base import get_db
from app.models.user import User
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


# ─── Schemas ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 32:
            raise ValueError("Username must be 3-32 characters")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_jwt(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "quota": float(user.quota or 0),
        "used_quota": float(user.used_quota or 0),
        "balance": float((user.quota or 0) - (user.used_quota or 0)),
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def get_current_user(
    authorization: str = None,
    db: Session = None,
):
    """从 Authorization: Bearer <jwt> 中提取当前用户（依赖注入版见下方）"""
    pass


# ─── 依赖注入：从 JWT 获取当前用户 ────────────────────────────────────────────

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer(auto_error=False)


def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise credentials_exc
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
        )
        user_id = int(payload.get("sub", 0))
    except (JWTError, ValueError):
        raise credentials_exc

    user = db.query(User).filter(User.id == user_id, User.status == 1).first()
    if not user:
        raise credentials_exc
    return user


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名/邮箱唯一性
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    pw_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
    user = User(
        username=data.username,
        email=data.email,
        password_hash=pw_hash,
        role="user",
        quota=0,
        used_quota=0,
        status=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"新用户注册: {user.username} ({user.email})")

    token = _make_jwt(user.id, user.role)
    return TokenResponse(access_token=token, user=_user_dict(user))


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """用户登录（邮箱 + 密码）"""
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not bcrypt.checkpw(data.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status != 1:
        raise HTTPException(status_code=403, detail="Account disabled")

    token = _make_jwt(user.id, user.role)
    return TokenResponse(access_token=token, user=_user_dict(user))


@router.get("/me")
def me(user: User = Depends(require_user)):
    """获取当前用户信息"""
    return _user_dict(user)
