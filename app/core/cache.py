"""
响应缓存模块（可选功能，当前实现内存缓存骨架）
"""
import hashlib
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ResponseCache:
    """简单的内存响应缓存（生产环境建议改用 Redis）"""

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self._store: dict[str, tuple[dict, float]] = {}  # key -> (response, expire_time)
        self._max_size = max_size
        self._ttl = ttl

    def _make_key(self, body: dict) -> str:
        """根据请求体生成缓存键（只缓存非流式、确定性请求）"""
        # 排除随机性参数
        cache_body = {k: v for k, v in body.items() if k not in ("stream",)}
        body_str = json.dumps(cache_body, sort_keys=True)
        return hashlib.md5(body_str.encode()).hexdigest()

    def get(self, body: dict) -> Optional[dict]:
        """获取缓存响应"""
        # 有 temperature > 0 的请求不缓存
        if body.get("temperature", 1.0) != 0:
            return None
        if body.get("stream"):
            return None

        key = self._make_key(body)
        if key in self._store:
            response, expire_time = self._store[key]
            if time.time() < expire_time:
                return response
            del self._store[key]
        return None

    def set(self, body: dict, response: dict):
        """存储缓存响应"""
        if body.get("temperature", 1.0) != 0 or body.get("stream"):
            return
        if len(self._store) >= self._max_size:
            # 清理最旧的缓存
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]

        key = self._make_key(body)
        self._store[key] = (response, time.time() + self._ttl)


# 全局缓存实例
response_cache = ResponseCache()
