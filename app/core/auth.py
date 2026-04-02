"""
认证模块：Token 验证依赖注入
"""
import logging
from datetime import datetime
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.models.token import Token
from app.models.user import User
from app.core.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


def _extract_bearer_token(request: Request) -> str:
    """从 Authorization 头中提取 Bearer Token"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Missing or invalid Authorization header. Expected: Bearer sk-xxx",
                    "type": "invalid_request_error",
                    "code": "missing_authorization",
                }
            },
        )
    token_key = auth[7:].strip()
    if not token_key:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Empty token", "type": "invalid_request_error"}},
        )
    return token_key


def _get_client_ip(request: Request) -> str:
    """获取客户端真实 IP（考虑反代）"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _check_model_allowed(token: Token, model: str) -> bool:
    """检查模型是否在允许列表中"""
    allowed = token.allowed_models or "*"
    if allowed == "*":
        return True
    allowed_list = [m.strip() for m in allowed.split(",")]
    return model in allowed_list


def _check_ip_allowed(token: Token, client_ip: str) -> bool:
    """检查客户端 IP 是否在白名单中"""
    allowed = token.allowed_ips or "*"
    if allowed == "*":
        return True
    allowed_list = [ip.strip() for ip in allowed.split(",")]
    return client_ip in allowed_list


async def get_current_token(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """
    FastAPI 依赖注入：验证 Token 并返回 token 信息字典
    """
    token_key = _extract_bearer_token(request)
    client_ip = _get_client_ip(request)

    # 查询 Token
    token = db.query(Token).filter(Token.token_key == token_key).first()
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Invalid token", "type": "invalid_request_error", "code": "invalid_api_key"}},
        )

    # 检查 Token 状态
    if token.status != 1:
        raise HTTPException(
            status_code=403,
            detail={"error": {"message": "Token is disabled", "type": "invalid_request_error", "code": "token_disabled"}},
        )

    # 检查过期时间
    if token.expires_at and token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=403,
            detail={"error": {"message": "Token has expired", "type": "invalid_request_error", "code": "token_expired"}},
        )

    # 检查额度（-1 表示无限）
    if float(token.total_quota) != -1:
        remaining = float(token.total_quota) - float(token.used_quota or 0)
        if remaining <= 0:
            raise HTTPException(
                status_code=403,
                detail={"error": {"message": "Quota exceeded", "type": "invalid_request_error", "code": "quota_exceeded"}},
            )

    # 检查 IP 白名单
    if not _check_ip_allowed(token, client_ip):
        raise HTTPException(
            status_code=403,
            detail={"error": {"message": f"IP {client_ip} not allowed", "type": "invalid_request_error", "code": "ip_not_allowed"}},
        )

    # 检查速率限制
    rate_limiter = get_rate_limiter()
    await rate_limiter.check_or_raise(
        key=token_key,
        limit=token.rate_limit or 60,
        window=60,
    )

    # 更新最后使用时间（异步更新，不阻塞主流程）
    try:
        token.last_used_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()

    return {
        "token_id": token.id,
        "user_id": token.user_id,
        "token_key": token_key,
        "allowed_models": token.allowed_models or "*",
        "total_quota": float(token.total_quota),
        "used_quota": float(token.used_quota or 0),
        "client_ip": client_ip,
    }


async def get_admin_token(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """
    管理员认证依赖：要求 role='admin' 的用户 Token
    """
    token_info = await get_current_token(request, db)

    # 查询对应用户是否是管理员
    user = db.query(User).filter(User.id == token_info["user_id"]).first()
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"error": {"message": "Admin access required", "type": "forbidden", "code": "admin_required"}},
        )

    token_info["role"] = "admin"
    return token_info
