"""
渠道 CRUD 服务层
"""
import logging
from sqlalchemy.orm import Session
from app.models.channel import Channel
from app.schemas.channel import ChannelCreate, ChannelUpdate
from app.utils.helpers import encrypt_api_key, decrypt_api_key, mask_api_key

logger = logging.getLogger(__name__)


def create_channel(db: Session, data: ChannelCreate) -> Channel:
    """创建渠道，api_key 加密存储"""
    channel = Channel(
        name=data.name,
        channel_type=data.channel_type,
        api_key=encrypt_api_key(data.api_key),
        base_url=data.base_url,
        supported_models=data.supported_models,
        model_mapping=data.model_mapping,
        priority=data.priority,
        weight=data.weight,
        max_retries=data.max_retries,
        timeout=data.timeout,
        status=1,
        error_count=0,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def list_channels(db: Session, page: int = 1, size: int = 100) -> tuple[list[Channel], int]:
    q = db.query(Channel)
    total = q.count()
    items = q.order_by(Channel.priority.desc(), Channel.id).offset((page - 1) * size).limit(size).all()
    return items, total


def get_channel(db: Session, channel_id: int) -> Channel | None:
    return db.query(Channel).filter(Channel.id == channel_id).first()


def update_channel(db: Session, channel_id: int, data: ChannelUpdate) -> Channel | None:
    channel = get_channel(db, channel_id)
    if not channel:
        return None
    update_data = data.model_dump(exclude_none=True)
    # api_key 需要重新加密
    if "api_key" in update_data:
        update_data["api_key"] = encrypt_api_key(update_data["api_key"])
    for field, value in update_data.items():
        setattr(channel, field, value)
    db.commit()
    db.refresh(channel)
    return channel


def delete_channel(db: Session, channel_id: int) -> bool:
    channel = get_channel(db, channel_id)
    if not channel:
        return False
    db.delete(channel)
    db.commit()
    return True


def mask_channel_key(channel: Channel) -> dict:
    """返回渠道信息时隐藏 api_key"""
    try:
        real_key = decrypt_api_key(channel.api_key)
        masked = mask_api_key(real_key)
    except Exception:
        masked = "***"

    d = {
        "id": channel.id,
        "name": channel.name,
        "channel_type": channel.channel_type,
        "api_key": masked,
        "base_url": channel.base_url,
        "supported_models": channel.supported_models,
        "model_mapping": channel.model_mapping,
        "priority": channel.priority,
        "weight": channel.weight,
        "max_retries": channel.max_retries,
        "timeout": channel.timeout,
        "status": channel.status,
        "error_count": channel.error_count,
        "last_error": channel.last_error,
        "last_used_at": channel.last_used_at,
        "created_at": channel.created_at,
    }
    return d
