"""
代理路由：对外暴露 OpenAI 兼容 API 接口
"""
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.core.auth import get_current_token
from app.services.proxy_service import proxy_service
from app.utils.helpers import generate_request_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proxy"])


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    token_info: dict = Depends(get_current_token),
    db: Session = Depends(get_db),
):
    """
    兼容 OpenAI /v1/chat/completions 接口
    支持普通请求和 SSE 流式请求
    """
    body = await request.json()
    request_id = generate_request_id()
    is_stream = body.get("stream", False)

    if is_stream:
        # 返回 SSE StreamingResponse
        streaming_resp = proxy_service.create_stream_response(body, token_info, db)
        streaming_resp.headers["X-Request-ID"] = request_id
        return streaming_resp
    else:
        result = await proxy_service.handle_request(body, token_info, db)
        from fastapi.responses import JSONResponse
        remaining = token_info["total_quota"] - token_info["used_quota"]
        return JSONResponse(
            content=result,
            headers={
                "X-Request-ID": request_id,
                "X-Quota-Remaining": f"{remaining:.6f}",
            },
        )


@router.post("/v1/embeddings")
async def embeddings(
    request: Request,
    token_info: dict = Depends(get_current_token),
    db: Session = Depends(get_db),
):
    """代理 Embeddings 接口"""
    body = await request.json()
    model = body.get("model", "")

    from app.core.router import channel_router
    from app.core.transformer import get_transformer
    from app.utils.helpers import decrypt_api_key
    import httpx

    channel = channel_router.select_channel(db, model)
    actual_model = channel_router.get_actual_model(channel, model)
    api_key = decrypt_api_key(channel.api_key)
    url = f"{channel.base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body["model"] = actual_model

    async with httpx.AsyncClient(timeout=channel.timeout) as client:
        resp = await client.post(url, headers=headers, json=body)
    
    from fastapi.responses import JSONResponse
    return JSONResponse(content=resp.json(), status_code=resp.status_code)
