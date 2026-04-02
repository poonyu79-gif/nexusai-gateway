"""
Token 数量估算工具
优先使用 tiktoken 精确计算，fallback 为字符数 / 4 估算
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 尝试导入 tiktoken，不可用时降级
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken 未安装，将使用字符估算模式")


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """估算文本的 token 数量"""
    if not text:
        return 0

    if _TIKTOKEN_AVAILABLE:
        try:
            # 对 Claude / Gemini 等非 OpenAI 模型用 cl100k_base 编码近似
            enc_name = "cl100k_base"
            if "gpt-3.5" in model:
                enc_name = "cl100k_base"
            elif "gpt-4" in model:
                enc_name = "cl100k_base"
            enc = tiktoken.get_encoding(enc_name)
            return len(enc.encode(text))
        except Exception:
            pass

    # fallback: 按字符数 / 4 估算
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict], model: str = "gpt-3.5-turbo") -> int:
    """估算 messages 列表的 token 数"""
    total = 0
    for msg in messages:
        # 每条消息固定开销约 4 个 token
        total += 4
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model)
        elif isinstance(content, list):
            # 多模态消息（含图片）
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += count_tokens(part.get("text", ""), model)
        total += count_tokens(role, model)
    total += 2  # 回复的起始 token
    return total
