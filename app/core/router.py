"""
渠道路由模块：负载均衡、优先级选择、熔断机制
"""
import json
import random
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.channel import Channel
from app.config import settings

logger = logging.getLogger(__name__)


class ChannelRouter:
    """渠道路由器"""

    def select_channel(self, db: Session, model: str, exclude_ids: list[int] = None) -> Channel:
        """
        选择合适的上游渠道：
        1. 过滤出支持该模型的启用渠道
        2. 排除熔断渠道和已失败渠道
        3. 按 priority 降序，同优先级按 weight 加权随机选择
        """
        exclude_ids = exclude_ids or []
        threshold = settings.circuit_breaker_threshold

        channels = db.query(Channel).filter(
            Channel.status == 1,
            Channel.error_count < threshold,
        ).all()

        # 过滤支持该模型的渠道
        available = []
        for ch in channels:
            if ch.id in exclude_ids:
                continue
            supported = [m.strip() for m in (ch.supported_models or "").split(",")]
            if "*" in supported or model in supported:
                available.append(ch)

        if not available:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "message": f"No available channel for model: {model}",
                        "type": "service_unavailable",
                        "code": "no_channel_available",
                    }
                },
            )

        # 找出最高优先级
        max_priority = max(ch.priority for ch in available)
        top_channels = [ch for ch in available if ch.priority == max_priority]

        # 按 weight 加权随机选择
        weights = [max(ch.weight, 1) for ch in top_channels]
        chosen = random.choices(top_channels, weights=weights, k=1)[0]
        return chosen

    def get_actual_model(self, channel: Channel, request_model: str) -> str:
        """
        根据渠道的模型映射，将用户请求的模型名转换为上游实际模型名
        """
        if not channel.model_mapping:
            return request_model
        try:
            mapping = json.loads(channel.model_mapping)
            return mapping.get(request_model, request_model)
        except (json.JSONDecodeError, Exception):
            return request_model

    def report_success(self, db: Session, channel_id: int):
        """报告渠道请求成功：重置错误计数"""
        try:
            channel = db.query(Channel).filter(Channel.id == channel_id).first()
            if channel:
                channel.error_count = 0
                channel.last_used_at = datetime.utcnow()
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"更新渠道成功状态失败 channel_id={channel_id}: {e}")

    def report_error(self, db: Session, channel_id: int, error_msg: str):
        """
        报告渠道请求失败：
        - 递增 error_count
        - 记录 last_error
        - 超过阈值自动禁用
        """
        try:
            channel = db.query(Channel).filter(Channel.id == channel_id).first()
            if channel:
                channel.error_count = (channel.error_count or 0) + 1
                channel.last_error = error_msg[:500]  # 截断避免太长
                threshold = settings.circuit_breaker_threshold
                if channel.error_count >= threshold:
                    channel.status = 0
                    logger.warning(
                        f"渠道 {channel.name}(id={channel_id}) 错误次数达到 {threshold}，已自动禁用"
                    )
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"更新渠道错误状态失败 channel_id={channel_id}: {e}")


# 全局路由器实例
channel_router = ChannelRouter()
