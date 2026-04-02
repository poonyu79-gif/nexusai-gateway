"""
/v1/models 接口：返回当前 Token 可用的模型列表
"""
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.models.channel import Channel
from app.core.auth import get_current_token

router = APIRouter(tags=["models"])


@router.get("/v1/models")
async def list_models(
    token_info: dict = Depends(get_current_token),
    db: Session = Depends(get_db),
):
    """
    返回当前 Token 可用的模型列表（兼容 OpenAI /v1/models 格式）
    """
    allowed_models = token_info.get("allowed_models", "*")

    # 查询所有启用渠道的模型
    channels = db.query(Channel).filter(Channel.status == 1).all()
    model_set = set()
    for ch in channels:
        for m in (ch.supported_models or "").split(","):
            m = m.strip()
            if m:
                model_set.add(m)

    # 根据 Token 权限过滤
    if allowed_models != "*":
        allowed_list = {m.strip() for m in allowed_models.split(",")}
        model_set = model_set & allowed_list

    now = int(time.time())
    models = [
        {
            "id": m,
            "object": "model",
            "created": now,
            "owned_by": "proxy",
        }
        for m in sorted(model_set)
    ]
    return {"object": "list", "data": models}
