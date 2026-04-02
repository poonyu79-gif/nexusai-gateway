"""
请求/响应格式转换器
适配 OpenAI、Claude、Azure OpenAI、Gemini 等不同上游 API 格式
"""
import json
import logging
import time
from typing import Any
from app.utils.helpers import decrypt_api_key

logger = logging.getLogger(__name__)


class OpenAITransformer:
    """OpenAI 格式：直接透传，无需转换"""

    def build_request(self, channel, body: dict, actual_model: str) -> tuple[str, dict, dict]:
        """
        返回 (url, headers, body)
        """
        api_key = decrypt_api_key(channel.api_key)
        url = f"{channel.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = dict(body)
        body["model"] = actual_model
        return url, headers, body

    def parse_response(self, response_json: dict) -> dict:
        """OpenAI 响应格式直接返回"""
        return response_json

    def parse_usage(self, response_json: dict) -> tuple[int, int]:
        """从响应中提取 (input_tokens, output_tokens)"""
        usage = response_json.get("usage", {})
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


class ClaudeTransformer:
    """Claude API 格式转换器（Anthropic Messages API）"""

    def build_request(self, channel, body: dict, actual_model: str) -> tuple[str, dict, dict]:
        api_key = decrypt_api_key(channel.api_key)
        url = f"{channel.base_url.rstrip('/')}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # 将 OpenAI messages 格式转换为 Claude 格式
        claude_body = self._convert_request(body, actual_model)
        return url, headers, claude_body

    def _convert_request(self, body: dict, actual_model: str) -> dict:
        messages = body.get("messages", [])
        system_content = None
        claude_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                # Claude 将 system 消息提到顶层
                system_content = content
            elif role == "user":
                claude_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                claude_messages.append({"role": "assistant", "content": content})

        claude_body = {
            "model": actual_model,
            "messages": claude_messages,
            "max_tokens": body.get("max_tokens", 4096),  # Claude 必填
        }
        if system_content:
            claude_body["system"] = system_content
        if "temperature" in body:
            claude_body["temperature"] = body["temperature"]
        if "stream" in body:
            claude_body["stream"] = body["stream"]
        return claude_body

    def parse_response(self, response_json: dict) -> dict:
        """将 Claude 响应转换为 OpenAI 兼容格式"""
        content = ""
        if response_json.get("content"):
            parts = response_json["content"]
            text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
            content = "".join(text_parts)

        return {
            "id": response_json.get("id", ""),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response_json.get("model", ""),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": response_json.get("stop_reason", "stop"),
                }
            ],
            "usage": {
                "prompt_tokens": response_json.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": response_json.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (
                    response_json.get("usage", {}).get("input_tokens", 0)
                    + response_json.get("usage", {}).get("output_tokens", 0)
                ),
            },
        }

    def parse_usage(self, response_json: dict) -> tuple[int, int]:
        usage = response_json.get("usage", {})
        return usage.get("input_tokens", 0), usage.get("output_tokens", 0)


class AzureTransformer:
    """Azure OpenAI 格式转换器"""

    def build_request(self, channel, body: dict, actual_model: str) -> tuple[str, dict, dict]:
        api_key = decrypt_api_key(channel.api_key)
        # Azure URL 格式: {base_url}/openai/deployments/{model}/chat/completions?api-version=xxx
        api_version = "2024-02-01"
        url = (
            f"{channel.base_url.rstrip('/')}/openai/deployments/"
            f"{actual_model}/chat/completions?api-version={api_version}"
        )
        headers = {
            "api-key": api_key,  # Azure 用 api-key 而非 Bearer
            "Content-Type": "application/json",
        }
        body = dict(body)
        body["model"] = actual_model
        return url, headers, body

    def parse_response(self, response_json: dict) -> dict:
        return response_json

    def parse_usage(self, response_json: dict) -> tuple[int, int]:
        usage = response_json.get("usage", {})
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


class GeminiTransformer:
    """Gemini API 格式转换器（使用 OpenAI 兼容接口）"""

    def build_request(self, channel, body: dict, actual_model: str) -> tuple[str, dict, dict]:
        api_key = decrypt_api_key(channel.api_key)
        # 如果使用 Google 的 OpenAI 兼容接口
        url = f"{channel.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = dict(body)
        body["model"] = actual_model
        return url, headers, body

    def parse_response(self, response_json: dict) -> dict:
        return response_json

    def parse_usage(self, response_json: dict) -> tuple[int, int]:
        usage = response_json.get("usage", {})
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


# 转换器注册表
_TRANSFORMERS = {
    "openai": OpenAITransformer,
    "custom": OpenAITransformer,
    "claude": ClaudeTransformer,
    "azure": AzureTransformer,
    "gemini": GeminiTransformer,
}


def get_transformer(channel_type: str):
    """根据渠道类型获取对应的转换器"""
    cls = _TRANSFORMERS.get(channel_type, OpenAITransformer)
    return cls()
