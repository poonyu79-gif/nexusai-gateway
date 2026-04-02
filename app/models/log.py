"""
请求日志表 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Numeric, TIMESTAMP, Boolean, Text, Index
from sqlalchemy.sql import func
from app.models.base import Base


class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    token_id = Column(Integer, nullable=True, index=True)
    channel_id = Column(Integer, nullable=True)
    request_model = Column(String(100), nullable=True, index=True)  # 用户请求的模型名
    actual_model = Column(String(100), nullable=True)               # 实际发送到上游的模型名
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost = Column(Numeric(12, 8), default=0)                        # 本次请求费用（美元）
    multiplier = Column(Numeric(4, 2), default=1.0)                 # 计费倍率
    duration_ms = Column(Integer, default=0)                        # 请求耗时（毫秒）
    is_stream = Column(Boolean, default=False)
    status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    client_ip = Column(String(45), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)

    __table_args__ = (
        Index("idx_logs_user", "user_id"),
        Index("idx_logs_token", "token_id"),
        Index("idx_logs_created", "created_at"),
        Index("idx_logs_model", "request_model"),
    )

    def __repr__(self):
        return f"<RequestLog id={self.id} model={self.request_model} cost={self.cost}>"
