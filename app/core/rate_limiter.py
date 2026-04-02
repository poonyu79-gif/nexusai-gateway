"""
限流模块：滑动窗口限流器
支持 Redis 后端（生产）和内存后端（开发/单机）
"""
import asyncio
import time
import logging
from typing import Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class MemoryRateLimiter:
    """内存滑动窗口限流器（单进程使用）"""

    def __init__(self):
        self._store: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        """
        检查是否超过限流
        返回 (allowed, remaining) 元组
        """
        now = time.time()
        async with self._lock:
            # 清理过期记录
            timestamps = self._store.get(key, [])
            cutoff = now - window
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= limit:
                # 计算距下次可用的等待时间
                retry_after = int(timestamps[0] + window - now) + 1
                return False, retry_after

            timestamps.append(now)
            self._store[key] = timestamps
            remaining = limit - len(timestamps)
            return True, remaining


class RedisRateLimiter:
    """Redis 滑动窗口限流器（使用 ZSET）"""

    def __init__(self, redis_url: str):
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def check(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        now = time.time()
        pipe = self._redis.pipeline()
        zset_key = f"rl:{key}"

        # 移除过期记录，添加当前时间戳
        pipe.zremrangebyscore(zset_key, "-inf", now - window)
        pipe.zadd(zset_key, {str(now): now})
        pipe.zcard(zset_key)
        pipe.expire(zset_key, window + 10)

        results = await pipe.execute()
        count = results[2]

        if count > limit:
            # 超限，移除刚才添加的记录
            await self._redis.zrem(zset_key, str(now))
            oldest = await self._redis.zrange(zset_key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] + window - now) + 1 if oldest else window
            return False, retry_after

        remaining = limit - count
        return True, remaining


class RateLimiter:
    """限流器工厂，根据配置自动选择后端"""

    def __init__(self, redis_url: Optional[str] = None):
        if redis_url:
            try:
                self._backend = RedisRateLimiter(redis_url)
                logger.info("限流器：使用 Redis 后端")
            except Exception as e:
                logger.warning(f"Redis 连接失败，降级为内存限流器：{e}")
                self._backend = MemoryRateLimiter()
        else:
            self._backend = MemoryRateLimiter()
            logger.info("限流器：使用内存后端")

    async def check_or_raise(self, key: str, limit: int, window: int = 60):
        """检查限流，超限时抛出 429 异常"""
        allowed, value = await self._backend.check(key, limit, window)
        if not allowed:
            retry_after = value
            raise HTTPException(
                status_code=429,
                detail={
                    "error": {
                        "message": f"Rate limit exceeded. Limit: {limit} requests per {window}s",
                        "type": "rate_limit_error",
                        "code": "rate_limit_exceeded",
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )
        return value  # remaining


# 全局限流器实例（在 main.py 中初始化）
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        from app.config import settings
        _rate_limiter = RateLimiter(settings.redis_url)
    return _rate_limiter
