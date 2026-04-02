"""
Token 相关的 Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    user_id: int
    total_quota: float = Field(default=-1, description="-1 表示无限额度")
    rate_limit: int = Field(default=60, ge=1, le=10000)
    allowed_models: str = Field(default="*")
    allowed_ips: str = Field(default="*")
    expires_days: Optional[int] = Field(default=None, ge=1, description="过期天数，None=永不过期")


class TokenUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    total_quota: Optional[float] = None
    rate_limit: Optional[int] = Field(default=None, ge=1, le=10000)
    allowed_models: Optional[str] = None
    allowed_ips: Optional[str] = None
    status: Optional[int] = Field(default=None, ge=0, le=1)
    expires_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    id: int
    user_id: int
    token_key: str          # 列表中只显示前10位
    name: str
    total_quota: float
    used_quota: float
    rate_limit: int
    allowed_models: str
    allowed_ips: str
    expires_at: Optional[datetime]
    status: int
    created_at: datetime
    last_used_at: Optional[datetime]

    model_config = {"from_attributes": True}


class TokenCreateResponse(TokenResponse):
    """创建时返回完整 token_key，仅此一次"""
    full_token_key: str
