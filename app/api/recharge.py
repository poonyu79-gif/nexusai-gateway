"""
充值接口：USDT (TRC20 / ERC20)
流程：
  1. 用户提交充值金额 → 后端生成订单 + 返回收款地址
  2. 用户转账到收款地址
  3. 用户提交 tx_hash → 后端标记待审核
  4. 管理员手动确认 OR Webhook 自动确认 → 到账额度
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.base import get_db
from app.models.user import User
from app.models.recharge import RechargeOrder
from app.api.auth import require_user
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recharge", tags=["recharge"])


# ─── 配置：你的收款地址（在 .env 中配置） ─────────────────────────────────────
# 简单模式：固定一个地址，用备注/memo区分用户
# 生产模式：每单生成独立地址（需要 HD wallet）
USDT_ADDRESSES = {
    "TRC20": getattr(settings, "usdt_trc20_address", "请在.env中配置USDT_TRC20_ADDRESS"),
    "ERC20": getattr(settings, "usdt_erc20_address", "请在.env中配置USDT_ERC20_ADDRESS"),
}

# 1 USDT = 1 USD 额度（可调整汇率/利润）
USDT_TO_USD_RATE = getattr(settings, "usdt_to_usd_rate", 1.0)
ORDER_EXPIRE_MINUTES = 60


# ─── Schemas ─────────────────────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    amount_usdt: float   # 充值金额（USDT）
    chain: str = "TRC20" # TRC20 | ERC20


class SubmitTxRequest(BaseModel):
    order_no: str
    tx_hash: str


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/create")
def create_order(
    data: CreateOrderRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """创建充值订单，返回收款地址"""
    if data.amount_usdt < 1:
        raise HTTPException(status_code=400, detail="Minimum recharge: 1 USDT")
    if data.chain not in USDT_ADDRESSES:
        raise HTTPException(status_code=400, detail="Unsupported chain")

    order_no = f"ORD{uuid.uuid4().hex[:16].upper()}"
    pay_address = USDT_ADDRESSES[data.chain]
    amount_usd = round(data.amount_usdt * USDT_TO_USD_RATE, 6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ORDER_EXPIRE_MINUTES)

    order = RechargeOrder(
        user_id=user.id,
        order_no=order_no,
        pay_type="usdt",
        chain=data.chain,
        pay_address=pay_address,
        amount_usdt=data.amount_usdt,
        amount_usd=amount_usd,
        status="pending",
        expires_at=expires_at,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "order_no": order_no,
        "pay_address": pay_address,
        "chain": data.chain,
        "amount_usdt": data.amount_usdt,
        "amount_usd": amount_usd,
        "memo": f"Order:{order_no}",   # 备注，用于区分用户
        "expires_at": expires_at.isoformat(),
        "note": "Please include the memo/remark when transferring so we can identify your payment.",
    }


@router.post("/submit_tx")
def submit_tx(
    data: SubmitTxRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """用户提交交易哈希，等待管理员确认"""
    order = db.query(RechargeOrder).filter(
        RechargeOrder.order_no == data.order_no,
        RechargeOrder.user_id == user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"Order is already {order.status}")

    order.tx_hash = data.tx_hash
    order.status = "confirming"
    db.commit()

    return {"message": "Transaction submitted. We will credit your balance after confirmation (usually within 30 minutes)."}


@router.get("/orders")
def my_orders(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """查看自己的充值记录"""
    q = db.query(RechargeOrder).filter(RechargeOrder.user_id == user.id)
    total = q.count()
    items = q.order_by(RechargeOrder.id.desc()).offset((page - 1) * size).limit(size).all()
    data = [
        {
            "order_no": o.order_no,
            "chain": o.chain,
            "pay_address": o.pay_address,
            "amount_usdt": float(o.amount_usdt),
            "amount_usd": float(o.amount_usd),
            "status": o.status,
            "tx_hash": o.tx_hash,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in items
    ]
    return {"data": data, "total": total, "page": page, "size": size}


# ─── 管理员确认到账 ───────────────────────────────────────────────────────────

@router.post("/admin/confirm/{order_no}")
def admin_confirm(
    order_no: str,
    db: Session = Depends(get_db),
    # 简单用 admin token header 验证（复用现有 auth）
    authorization: str = None,
):
    """管理员手动确认充值到账（在正式部署中用 Webhook 替代）"""
    from fastapi import Header
    from app.core.auth import get_admin_token

    order = db.query(RechargeOrder).filter(RechargeOrder.order_no == order_no).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == "paid":
        raise HTTPException(status_code=400, detail="Already paid")

    # 到账：给用户加额度
    user = db.query(User).filter(User.id == order.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.quota = float(user.quota or 0) + float(order.amount_usd)
    order.status = "paid"
    order.paid_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"充值到账: user={user.username} +${order.amount_usd} order={order_no}")
    return {
        "message": "Payment confirmed",
        "user_id": user.id,
        "username": user.username,
        "credited_usd": float(order.amount_usd),
        "new_quota": float(user.quota),
    }


@router.get("/admin/orders")
def admin_list_orders(
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """管理员查看所有充值记录"""
    q = db.query(RechargeOrder)
    if status:
        q = q.filter(RechargeOrder.status == status)
    total = q.count()
    items = q.order_by(RechargeOrder.id.desc()).offset((page - 1) * size).limit(size).all()
    data = [
        {
            "id": o.id,
            "order_no": o.order_no,
            "user_id": o.user_id,
            "chain": o.chain,
            "amount_usdt": float(o.amount_usdt),
            "amount_usd": float(o.amount_usd),
            "status": o.status,
            "tx_hash": o.tx_hash,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in items
    ]
    return {"data": data, "total": total}
