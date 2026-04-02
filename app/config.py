"""
配置管理：从环境变量或 .env 文件读取所有配置项
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    # 基础配置
    app_name: str = Field(default="AI-API-Proxy", alias="APP_NAME")
    secret_key: str = Field(default="change-this-secret-key-32chars-min", alias="SECRET_KEY")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin123", alias="ADMIN_PASSWORD")

    # 数据库
    database_url: str = Field(default="sqlite:///./proxy.db", alias="DATABASE_URL")

    # Redis（可选）
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")

    # 服务
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # 计费
    default_multiplier: float = Field(default=1.0, alias="DEFAULT_MULTIPLIER")

    # 安全
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")
    max_request_size: int = Field(default=10485760, alias="MAX_REQUEST_SIZE")

    # 熔断阈值
    circuit_breaker_threshold: int = Field(default=5, alias="CIRCUIT_BREAKER_THRESHOLD")

    # USDT 收款地址
    usdt_trc20_address: str = Field(default="", alias="USDT_TRC20_ADDRESS")
    usdt_erc20_address: str = Field(default="", alias="USDT_ERC20_ADDRESS")
    usdt_to_usd_rate: float = Field(default=1.0, alias="USDT_TO_USD_RATE")

    # 站点信息
    site_name: str = Field(default="AI Gateway", alias="SITE_NAME")
    site_url: str = Field(default="http://localhost:8000", alias="SITE_URL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",")]


# 全局单例
settings = Settings()
