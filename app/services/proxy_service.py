"""
核心代理转发服务
负责普通请求和 SSE 流式请求的完整代理流程
"""
import json
import logging
import time
from typing import AsyncGenerator
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.core.router import channel_router
from app.core.transformer import get_transformer
from app.core.billing import calculate_cost, deduct_quota
from app.core.retry import is_retryable_error, BACKOFF_DELAYS
from app.config import settings
from app.services import log_service
from app.utils.token_counter import estimate_messages_tokens

logger = logging.getLogger(__name__)


class ProxyService:
    """AI API 代理服务"""

    async def handle_request(
        self,
        body: dict,
        token_info: dict,
        db: Session,
    ) -> dict:
        """
        非流式请求代理流程：
        选渠道 → 格式转换 → 发送请求 → 解析响应 → 计费 → 记录日志
        """
        model = body.get("model", "")
        if not model:
            raise HTTPException(status_code=400, detail={"error": {"message": "model is required", "type": "invalid_request_error"}})

        # 验证模型权限
        self._check_model_permission(model, token_info)

        failed_channel_ids = []
        max_global_attempts = 3  # 全局最多尝试 3 个不同渠道

        for attempt in range(max_global_attempts):
            channel = None
            start_ms = int(time.time() * 1000)
            try:
                # 选择渠道
                channel = channel_router.select_channel(db, model, exclude_ids=failed_channel_ids)
                actual_model = channel_router.get_actual_model(channel, model)
                transformer = get_transformer(channel.channel_type)

                # 构建上游请求
                url, headers, upstream_body = transformer.build_request(channel, body, actual_model)
                upstream_body["stream"] = False  # 确保非流式

                async with httpx.AsyncClient(timeout=channel.timeout) as client:
                    response = await client.post(url, headers=headers, json=upstream_body)

                duration_ms = int(time.time() * 1000) - start_ms

                if response.status_code == 200:
                    resp_json = response.json()
                    # 格式转换（Claude → OpenAI 兼容格式）
                    normalized = transformer.parse_response(resp_json)
                    input_tokens, output_tokens = transformer.parse_usage(resp_json)

                    # 计费扣减
                    cost = calculate_cost(model, input_tokens, output_tokens, settings.default_multiplier)
                    deduct_quota(db, token_info["token_id"], token_info["user_id"], cost)

                    # 记录日志
                    log_service.create_log(
                        db=db,
                        user_id=token_info["user_id"],
                        token_id=token_info["token_id"],
                        channel_id=channel.id,
                        request_model=model,
                        actual_model=actual_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                        multiplier=settings.default_multiplier,
                        duration_ms=duration_ms,
                        is_stream=False,
                        status_code=200,
                        client_ip=token_info["client_ip"],
                    )

                    channel_router.report_success(db, channel.id)
                    return normalized

                else:
                    # 上游错误
                    error_text = response.text[:500]
                    logger.warning(f"上游返回错误 {response.status_code}: {error_text}")
                    channel_router.report_error(db, channel.id, f"HTTP {response.status_code}: {error_text}")

                    if not is_retryable_error(response.status_code, None):
                        # 4xx 不重试，直接返回给客户端
                        try:
                            error_body = response.json()
                        except Exception:
                            error_body = {"error": {"message": error_text, "type": "upstream_error"}}
                        raise HTTPException(status_code=response.status_code, detail=error_body)

                    failed_channel_ids.append(channel.id)

            except HTTPException:
                raise
            except httpx.TimeoutException as e:
                logger.warning(f"渠道 {channel.id if channel else '?'} 超时: {e}")
                if channel:
                    channel_router.report_error(db, channel.id, f"Timeout: {e}")
                    failed_channel_ids.append(channel.id)
            except httpx.RequestError as e:
                logger.warning(f"渠道 {channel.id if channel else '?'} 连接错误: {e}")
                if channel:
                    channel_router.report_error(db, channel.id, f"RequestError: {e}")
                    failed_channel_ids.append(channel.id)
            except Exception as e:
                logger.error(f"代理请求异常: {e}", exc_info=True)
                if channel:
                    channel_router.report_error(db, channel.id, str(e))
                    failed_channel_ids.append(channel.id)

            # 等待后重试
            if attempt < max_global_attempts - 1:
                import asyncio
                await asyncio.sleep(BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)])

        raise HTTPException(
            status_code=503,
            detail={"error": {"message": "All upstream channels failed", "type": "service_unavailable"}},
        )

    def create_stream_response(
        self,
        body: dict,
        token_info: dict,
        db: Session,
    ) -> StreamingResponse:
        """
        流式请求代理：返回 StreamingResponse（SSE）
        """
        model = body.get("model", "")
        self._check_model_permission(model, token_info)

        async def stream_generator() -> AsyncGenerator[bytes, None]:
            failed_channel_ids = []
            channel = None
            start_ms = int(time.time() * 1000)
            output_tokens = 0
            input_tokens = 0
            actual_model = model
            channel_id = None
            success = False

            try:
                channel = channel_router.select_channel(db, model, exclude_ids=failed_channel_ids)
                actual_model = channel_router.get_actual_model(channel, model)
                channel_id = channel.id
                transformer = get_transformer(channel.channel_type)

                url, headers, upstream_body = transformer.build_request(channel, body, actual_model)
                upstream_body["stream"] = True

                # 预估 input tokens（用于日志）
                messages = body.get("messages", [])
                input_tokens = estimate_messages_tokens(messages, model)

                async with httpx.AsyncClient(timeout=channel.timeout) as client:
                    async with client.stream("POST", url, headers=headers, json=upstream_body) as response:
                        if response.status_code != 200:
                            error_text = await response.aread()
                            channel_router.report_error(db, channel.id, f"HTTP {response.status_code}")
                            # 将错误转换为 SSE 错误事件
                            err_msg = json.dumps({
                                "error": {
                                    "message": f"Upstream error: {response.status_code}",
                                    "type": "upstream_error",
                                }
                            })
                            yield f"data: {err_msg}\n\n".encode()
                            return

                        async for line in response.aiter_lines():
                            if not line:
                                yield b"\n"
                                continue

                            if line.startswith("data: "):
                                data_str = line[6:].strip()

                                if data_str == "[DONE]":
                                    # 流结束：计费和记录日志
                                    duration_ms = int(time.time() * 1000) - start_ms
                                    cost = calculate_cost(model, input_tokens, output_tokens, settings.default_multiplier)
                                    deduct_quota(db, token_info["token_id"], token_info["user_id"], cost)
                                    log_service.create_log(
                                        db=db,
                                        user_id=token_info["user_id"],
                                        token_id=token_info["token_id"],
                                        channel_id=channel_id,
                                        request_model=model,
                                        actual_model=actual_model,
                                        input_tokens=input_tokens,
                                        output_tokens=output_tokens,
                                        cost=cost,
                                        multiplier=settings.default_multiplier,
                                        duration_ms=duration_ms,
                                        is_stream=True,
                                        status_code=200,
                                        client_ip=token_info["client_ip"],
                                    )
                                    channel_router.report_success(db, channel_id)
                                    success = True
                                    yield b"data: [DONE]\n\n"
                                    return

                                # 解析 chunk，累计 output_tokens
                                try:
                                    chunk = json.loads(data_str)
                                    # 如果最后一个 chunk 包含精确的 usage，用精确值
                                    if "usage" in chunk and chunk["usage"]:
                                        u = chunk["usage"]
                                        if u.get("completion_tokens"):
                                            output_tokens = u["completion_tokens"]
                                        if u.get("prompt_tokens"):
                                            input_tokens = u["prompt_tokens"]
                                    else:
                                        # 简单累计：每个有 content 的 chunk +1
                                        choices = chunk.get("choices", [])
                                        for choice in choices:
                                            delta = choice.get("delta", {})
                                            if delta.get("content"):
                                                output_tokens += 1
                                except json.JSONDecodeError:
                                    pass

                                yield f"data: {data_str}\n\n".encode()
                            else:
                                # 透传其他行
                                yield f"{line}\n".encode()

            except httpx.TimeoutException as e:
                logger.warning(f"流式请求超时: {e}")
                if channel_id:
                    channel_router.report_error(db, channel_id, f"Stream timeout: {e}")
                err = json.dumps({"error": {"message": "Upstream timeout", "type": "timeout_error"}})
                yield f"data: {err}\n\n".encode()
            except Exception as e:
                logger.error(f"流式代理异常: {e}", exc_info=True)
                if channel_id and not success:
                    channel_router.report_error(db, channel_id, str(e))
                err = json.dumps({"error": {"message": "Stream error", "type": "stream_error"}})
                yield f"data: {err}\n\n".encode()
            finally:
                # 如果异常中断，仍记录一条失败日志
                if not success and input_tokens > 0:
                    try:
                        duration_ms = int(time.time() * 1000) - start_ms
                        log_service.create_log(
                            db=db,
                            user_id=token_info["user_id"],
                            token_id=token_info["token_id"],
                            channel_id=channel_id,
                            request_model=model,
                            actual_model=actual_model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost=0,
                            multiplier=settings.default_multiplier,
                            duration_ms=duration_ms,
                            is_stream=True,
                            status_code=500,
                            client_ip=token_info["client_ip"],
                            error_message="Stream interrupted",
                        )
                    except Exception:
                        pass

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 关闭 Nginx 缓冲
            },
        )

    def _check_model_permission(self, model: str, token_info: dict):
        """检查 token 是否有权限使用该模型"""
        allowed = token_info.get("allowed_models", "*")
        if allowed == "*":
            return
        allowed_list = [m.strip() for m in allowed.split(",")]
        if model not in allowed_list:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "message": f"Model '{model}' is not allowed for this token",
                        "type": "permission_denied",
                        "code": "model_not_allowed",
                    }
                },
            )


# 全局代理服务实例
proxy_service = ProxyService()
