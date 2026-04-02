"""
通用辅助函数
"""
import secrets
import uuid
import hashlib
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from app.config import settings


def generate_token_key() -> str:
    """生成 sk- 前缀 + 48位随机hex 的令牌"""
    return "sk-" + secrets.token_hex(24)


def generate_request_id() -> str:
    """生成唯一请求ID"""
    return str(uuid.uuid4()).replace("-", "")


def _get_fernet() -> Fernet:
    """从 SECRET_KEY 派生 Fernet 加密密钥（32字节 base64url）"""
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    import base64
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_api_key(api_key: str) -> str:
    """加密存储 API Key"""
    f = _get_fernet()
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    """解密 API Key"""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def mask_api_key(api_key: str, visible: int = 8) -> str:
    """展示 API Key 前几位，其余用 * 隐藏"""
    if len(api_key) <= visible:
        return api_key
    return api_key[:visible] + "..." 


def mask_token_key(token_key: str, visible: int = 10) -> str:
    """展示 Token 前几位"""
    if len(token_key) <= visible:
        return token_key
    return token_key[:visible] + "..."


def now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_cost(cost: float) -> str:
    """格式化费用为美元字符串"""
    return f"${cost:.8f}"
