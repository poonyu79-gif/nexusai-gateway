"""
充值记录表
"""
from sqlalchemy import Column, Integer, String, Numeric, TIMESTAMP, Text
from sqlalchemy.sql import func
from app.models.base import Base


class RechargeOrder(Base):
    __tablename__ = "recharge_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True)

    # 支付信息
    pay_type = Column(String(20), default="usdt")      # usdt / stripe
    chain = Column(String(20), nullable=True)           # TRC20 / ERC20
    pay_address = Column(String(100), nullable=True)    # 收款地址
    amount_usdt = Column(Numeric(12, 6), nullable=False)# 应付 USDT
    amount_usd = Column(Numeric(12, 6), nullable=False) # 到账额度（美元）

    # 状态：pending / paid / expired / failed
    status = Column(String(20), default="pending", index=True)
    tx_hash = Column(String(100), nullable=True)        # 链上交易哈希

    expires_at = Column(TIMESTAMP, nullable=True)       # 订单过期时间
    paid_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<RechargeOrder id={self.id} user_id={self.user_id} status={self.status}>"
