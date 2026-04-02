"""
用户表 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Numeric, TIMESTAMP, Boolean
from sqlalchemy.sql import func
from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(10), default="user")          # 'admin' | 'user'
    quota = Column(Numeric(12, 6), default=0)           # 总额度（美元）
    used_quota = Column(Numeric(12, 6), default=0)      # 已用额度
    status = Column(Integer, default=1)                 # 1=启用 0=禁用
    invite_code = Column(String(20), nullable=True)     # 邀请码（预留）
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User id={self.id} username={self.username} role={self.role}>"
