"""
Channel 相关的 Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    channel_type: str = Field(..., pattern="^(openai|claude|azure|gemini|custom)$")
    api_key: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    supported_models: str = Field(..., min_length=1, description="逗号分隔的模型列表")
    model_mapping: Optional[str] = Field(default=None, description="JSON格式的模型名映射")
    priority: int = Field(default=0, ge=0, le=100)
    weight: int = Field(default=1, ge=1, le=100)
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout: int = Field(default=120, ge=10, le=600)


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    supported_models: Optional[str] = None
    model_mapping: Optional[str] = None
    priority: Optional[int] = None
    weight: Optional[int] = None
    max_retries: Optional[int] = None
    timeout: Optional[int] = None
    status: Optional[int] = Field(default=None, ge=0, le=2)


class ChannelResponse(BaseModel):
    id: int
    name: str
    channel_type: str
    api_key: str            # 只显示前8位
    base_url: str
    supported_models: str
    model_mapping: Optional[str]
    priority: int
    weight: int
    max_retries: int
    timeout: int
    status: int
    error_count: int
    last_error: Optional[str]
    last_used_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
