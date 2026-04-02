"""
渠道表 ORM 模型（上游 AI API 配置）
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func
from app.models.base import Base


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    # 渠道类型: 'openai' | 'claude' | 'azure' | 'gemini' | 'custom'
    channel_type = Column(String(20), nullable=False)
    # 上游 API 密钥（Fernet 加密存储）
    api_key = Column(String(500), nullable=False)
    # 上游 API 基础 URL
    base_url = Column(String(255), nullable=False)
    # 逗号分隔的支持模型列表
    supported_models = Column(Text, nullable=False)
    # JSON 格式的模型名映射，如 {"gpt-4":"gpt-4o"}
    model_mapping = Column(Text, nullable=True)
    priority = Column(Integer, default=0)          # 优先级，数值越大越优先
    weight = Column(Integer, default=1)            # 负载均衡权重
    max_retries = Column(Integer, default=2)       # 最大重试次数
    timeout = Column(Integer, default=120)         # 超时时间（秒）
    status = Column(Integer, default=1)            # 1=启用 0=禁用 2=测试中
    error_count = Column(Integer, default=0)       # 连续错误次数（自动熔断用）
    last_error = Column(Text, nullable=True)       # 最后一次错误信息
    last_used_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    def __repr__(self):
        return f"<Channel id={self.id} name={self.name} type={self.channel_type}>"
