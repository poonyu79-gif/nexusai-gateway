"""
令牌表 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Numeric, TIMESTAMP, ForeignKey, Text
from sqlalchemy.sql import func
from app.models.base import Base


class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_key = Column(String(64), unique=True, nullable=False, index=True)
    # 格式: sk-xxxxx (48位随机hex)
    name = Column(String(100), nullable=False)
    total_quota = Column(Numeric(12, 6), default=-1)      # -1 表示无限额度
    used_quota = Column(Numeric(12, 6), default=0)
    rate_limit = Column(Integer, default=60)              # 每分钟最大请求数
    allowed_models = Column(Text, default="*")            # '*' 或逗号分隔的模型列表
    allowed_ips = Column(Text, default="*")               # '*' 或逗号分隔的 IP 白名单
    expires_at = Column(TIMESTAMP, nullable=True)         # NULL 表示永不过期
    status = Column(Integer, default=1)                   # 1=启用 0=禁用 -1=已删除
    created_at = Column(TIMESTAMP, server_default=func.now())
    last_used_at = Column(TIMESTAMP, nullable=True)

    def __repr__(self):
        return f"<Token id={self.id} name={self.name}>"
