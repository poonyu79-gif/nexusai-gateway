"""
统计相关的 Pydantic 响应模型
"""
from pydantic import BaseModel
from typing import Any
from datetime import datetime


class OverviewStats(BaseModel):
    total_requests: int
    today_requests: int
    total_cost: float
    today_cost: float
    active_channels: int
    active_tokens: int


class ModelStat(BaseModel):
    model: str
    request_count: int
    input_tokens: int
    output_tokens: int
    total_cost: float


class DailyStat(BaseModel):
    date: str
    request_count: int
    total_cost: float


class TokenStat(BaseModel):
    token_id: int
    token_name: str
    request_count: int
    total_cost: float


class LogItem(BaseModel):
    id: int
    request_model: str | None
    actual_model: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float
    duration_ms: int
    is_stream: bool
    status_code: int | None
    error_message: str | None
    client_ip: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel):
    data: list[Any]
    total: int
    page: int
    size: int
