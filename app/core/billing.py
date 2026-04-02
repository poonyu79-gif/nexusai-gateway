"""
计费模块：维护模型价格表、计算费用、扣减额度
"""
import logging
from decimal import Decimal, ROUND_DOWN
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from app.models.token import Token
from app.models.user import User

logger = logging.getLogger(__name__)

# 模型价格表（单位：美元 / 1000 tokens）
MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI GPT 系列
    "gpt-4o":                        {"input": 0.0025,  "output": 0.01},
    "gpt-4o-mini":                   {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo":                   {"input": 0.01,    "output": 0.03},
    "gpt-4-turbo-preview":           {"input": 0.01,    "output": 0.03},
    "gpt-4":                         {"input": 0.03,    "output": 0.06},
    "gpt-3.5-turbo":                 {"input": 0.0005,  "output": 0.0015},
    "gpt-3.5-turbo-16k":             {"input": 0.003,   "output": 0.004},
    "o1":                            {"input": 0.015,   "output": 0.06},
    "o1-mini":                       {"input": 0.003,   "output": 0.012},
    "o3-mini":                       {"input": 0.0011,  "output": 0.0044},
    # Claude 系列
    "claude-3-5-sonnet-20241022":    {"input": 0.003,  "output": 0.015},
    "claude-3-5-sonnet-20240620":    {"input": 0.003,  "output": 0.015},
    "claude-3-5-haiku-20241022":     {"input": 0.001,  "output": 0.005},
    "claude-3-opus-20240229":        {"input": 0.015,  "output": 0.075},
    "claude-3-sonnet-20240229":      {"input": 0.003,  "output": 0.015},
    "claude-3-haiku-20240307":       {"input": 0.00025,"output": 0.00125},
    # Gemini 系列
    "gemini-1.5-pro":                {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash":              {"input": 0.000075,"output": 0.0003},
    "gemini-2.0-flash":              {"input": 0.0001,  "output": 0.0004},
    "gemini-1.0-pro":                {"input": 0.0005,  "output": 0.0015},
    # 未知模型默认价格
    "_default": {"input": 0.01, "output": 0.03},
}


def get_model_pricing(model: str) -> dict[str, float]:
    """获取模型价格，未知模型返回默认价格"""
    # 精确匹配
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # 前缀匹配（如 gpt-4o-2024-11-20 匹配 gpt-4o）
    for key in MODEL_PRICING:
        if key.startswith("_"):
            continue
        if model.startswith(key):
            return MODEL_PRICING[key]
    logger.warning(f"未知模型 {model}，使用默认价格")
    return MODEL_PRICING["_default"]


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    multiplier: float = 1.0,
) -> float:
    """
    计算本次请求费用（美元）
    费用 = (input_tokens/1000 * 输入单价 + output_tokens/1000 * 输出单价) * multiplier
    """
    pricing = get_model_pricing(model)
    cost = (
        input_tokens / 1000 * pricing["input"]
        + output_tokens / 1000 * pricing["output"]
    ) * multiplier
    # 保留8位小数
    return float(Decimal(str(cost)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN))


def deduct_quota(db: Session, token_id: int, user_id: int, cost: float) -> bool:
    """
    在一个事务中同时扣减 token.used_quota 和 user.used_quota
    使用行锁防止并发超扣
    返回 True 表示扣减成功
    """
    if cost <= 0:
        return True

    try:
        # 行锁查询 token（SQLite 不支持 FOR UPDATE，但使用事务已足够）
        token = db.query(Token).filter(Token.id == token_id).with_for_update().first()
        user = db.query(User).filter(User.id == user_id).with_for_update().first()

        if not token or not user:
            logger.error(f"扣减额度失败：token_id={token_id} 或 user_id={user_id} 不存在")
            return False

        cost_decimal = Decimal(str(cost))
        token.used_quota = float(Decimal(str(token.used_quota or 0)) + cost_decimal)
        user.used_quota = float(Decimal(str(user.used_quota or 0)) + cost_decimal)

        db.commit()
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"扣减额度异常：{e}")
        return False


def check_quota_sufficient(token, estimated_cost: float) -> bool:
    """预检查 token 额度是否足够（-1 表示无限）"""
    if float(token.total_quota) == -1:
        return True
    remaining = float(token.total_quota) - float(token.used_quota or 0)
    return remaining >= estimated_cost
