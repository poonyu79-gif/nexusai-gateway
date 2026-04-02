"""
重试与故障转移模块：指数退避、排除已失败渠道
"""
import asyncio
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

# 仅对这些状态码重试（服务端错误和超时），不重试 4xx 客户端错误
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}

# 指数退避等待时间（秒）
BACKOFF_DELAYS = [1, 2, 4, 8]


def is_retryable_error(status_code: int | None, exception: Exception | None) -> bool:
    """判断是否应该重试"""
    if exception is not None:
        # 超时、连接错误都可以重试
        import httpx
        if isinstance(exception, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)):
            return True
    if status_code is not None and status_code in RETRYABLE_STATUS_CODES:
        return True
    return False


async def retry_with_fallback(
    func: Callable,
    max_attempts: int,
    *args,
    **kwargs,
) -> Any:
    """
    带重试的调用包装器
    func 应该接受 attempt_index 参数，内部处理渠道选择和排除逻辑
    """
    last_exception = None
    for attempt in range(max_attempts + 1):
        try:
            return await func(attempt, *args, **kwargs)
        except Exception as e:
            last_exception = e
            # 如果是不可重试的错误（如 4xx），直接抛出
            from fastapi import HTTPException
            if isinstance(e, HTTPException) and e.status_code < 500:
                raise

            if attempt < max_attempts:
                delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                logger.warning(f"第 {attempt + 1} 次尝试失败，{delay}s 后重试：{e}")
                await asyncio.sleep(delay)

    raise last_exception
