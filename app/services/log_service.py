"""
日志服务：记录和查询请求日志
"""
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from app.models.log import RequestLog

logger = logging.getLogger(__name__)


def create_log(
    db: Session,
    user_id: int,
    token_id: int,
    channel_id: int,
    request_model: str,
    actual_model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    multiplier: float,
    duration_ms: int,
    is_stream: bool,
    status_code: int,
    client_ip: str,
    error_message: str = None,
) -> RequestLog:
    """记录一条请求日志"""
    try:
        log = RequestLog(
            user_id=user_id,
            token_id=token_id,
            channel_id=channel_id,
            request_model=request_model,
            actual_model=actual_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost=cost,
            multiplier=multiplier,
            duration_ms=duration_ms,
            is_stream=is_stream,
            status_code=status_code,
            error_message=error_message,
            client_ip=client_ip,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    except Exception as e:
        db.rollback()
        logger.error(f"记录日志失败: {e}")
        return None


def query_logs(
    db: Session,
    page: int = 1,
    size: int = 20,
    token_id: int = None,
    model: str = None,
    start_time: datetime = None,
    end_time: datetime = None,
) -> tuple[list[RequestLog], int]:
    """分页查询日志"""
    q = db.query(RequestLog)
    if token_id:
        q = q.filter(RequestLog.token_id == token_id)
    if model:
        q = q.filter(RequestLog.request_model == model)
    if start_time:
        q = q.filter(RequestLog.created_at >= start_time)
    if end_time:
        q = q.filter(RequestLog.created_at <= end_time)

    total = q.count()
    items = q.order_by(RequestLog.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return items, total


def get_overview_stats(db: Session) -> dict:
    """获取总览统计"""
    today = datetime.utcnow().date()

    total_requests = db.query(func.count(RequestLog.id)).scalar() or 0
    today_requests = (
        db.query(func.count(RequestLog.id))
        .filter(func.date(RequestLog.created_at) == today)
        .scalar() or 0
    )
    total_cost = float(db.query(func.sum(RequestLog.cost)).scalar() or 0)
    today_cost = float(
        db.query(func.sum(RequestLog.cost))
        .filter(func.date(RequestLog.created_at) == today)
        .scalar() or 0
    )
    return {
        "total_requests": total_requests,
        "today_requests": today_requests,
        "total_cost": total_cost,
        "today_cost": today_cost,
    }


def get_model_stats(db: Session) -> list[dict]:
    """按模型统计"""
    rows = (
        db.query(
            RequestLog.request_model,
            func.count(RequestLog.id).label("request_count"),
            func.sum(RequestLog.input_tokens).label("input_tokens"),
            func.sum(RequestLog.output_tokens).label("output_tokens"),
            func.sum(RequestLog.cost).label("total_cost"),
        )
        .group_by(RequestLog.request_model)
        .order_by(func.count(RequestLog.id).desc())
        .all()
    )
    return [
        {
            "model": r.request_model or "unknown",
            "request_count": r.request_count,
            "input_tokens": int(r.input_tokens or 0),
            "output_tokens": int(r.output_tokens or 0),
            "total_cost": float(r.total_cost or 0),
        }
        for r in rows
    ]


def get_daily_stats(db: Session, days: int = 30) -> list[dict]:
    """获取每日统计（近 N 天）"""
    rows = (
        db.query(
            func.date(RequestLog.created_at).label("date"),
            func.count(RequestLog.id).label("request_count"),
            func.sum(RequestLog.cost).label("total_cost"),
        )
        .group_by(func.date(RequestLog.created_at))
        .order_by(func.date(RequestLog.created_at).desc())
        .limit(days)
        .all()
    )
    return [
        {
            "date": str(r.date),
            "request_count": r.request_count,
            "total_cost": float(r.total_cost or 0),
        }
        for r in reversed(rows)
    ]


def get_token_stats(db: Session, limit: int = 10) -> list[dict]:
    """按 Token 统计使用量排行"""
    from app.models.token import Token
    rows = (
        db.query(
            RequestLog.token_id,
            Token.name,
            func.count(RequestLog.id).label("request_count"),
            func.sum(RequestLog.cost).label("total_cost"),
        )
        .join(Token, Token.id == RequestLog.token_id, isouter=True)
        .group_by(RequestLog.token_id, Token.name)
        .order_by(func.sum(RequestLog.cost).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "token_id": r.token_id,
            "token_name": r.name or "unknown",
            "request_count": r.request_count,
            "total_cost": float(r.total_cost or 0),
        }
        for r in rows
    ]
