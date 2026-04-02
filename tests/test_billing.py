"""
计费模块测试
"""
import pytest
from app.core.billing import calculate_cost, get_model_pricing, deduct_quota, MODEL_PRICING


def test_calculate_cost_gpt4o():
    """GPT-4o 费用计算准确"""
    # input: 1000 tokens @ $0.0025/1k = $0.0025
    # output: 1000 tokens @ $0.01/1k = $0.01
    # total = $0.0125
    cost = calculate_cost("gpt-4o", 1000, 1000)
    assert abs(cost - 0.0125) < 1e-7


def test_calculate_cost_gpt4o_mini():
    """GPT-4o-mini 费用计算"""
    cost = calculate_cost("gpt-4o-mini", 1000, 1000)
    expected = (0.00015 + 0.0006)  # per 1k each
    assert abs(cost - expected) < 1e-7


def test_calculate_cost_unknown_model():
    """未知模型使用默认价格"""
    cost = calculate_cost("unknown-model-xyz", 1000, 1000)
    default_pricing = MODEL_PRICING["_default"]
    expected = default_pricing["input"] + default_pricing["output"]
    assert abs(cost - expected) < 1e-7


def test_multiplier():
    """计费倍率正确"""
    cost_1x = calculate_cost("gpt-4o", 1000, 1000, multiplier=1.0)
    cost_2x = calculate_cost("gpt-4o", 1000, 1000, multiplier=2.0)
    assert abs(cost_2x - cost_1x * 2) < 1e-7


def test_calculate_cost_precision():
    """费用保留8位小数"""
    cost = calculate_cost("gpt-4o-mini", 100, 50)
    assert len(str(cost).split('.')[-1]) <= 8


def test_deduct_quota(db, test_user, user_token):
    """额度扣减正确"""
    initial_used = float(user_token.used_quota or 0)
    cost = 0.001

    deduct_quota(db, user_token.id, test_user.id, cost)

    db.refresh(user_token)
    db.refresh(test_user)

    assert abs(float(user_token.used_quota) - (initial_used + cost)) < 1e-7


def test_zero_cost_no_change(db, test_user, user_token):
    """cost=0 时不更改额度"""
    initial_used = float(user_token.used_quota or 0)
    deduct_quota(db, user_token.id, test_user.id, 0)
    db.refresh(user_token)
    assert float(user_token.used_quota) == initial_used


def test_model_pricing_prefix_match():
    """模型前缀匹配（如 gpt-4o-2024-11-20 匹配 gpt-4o 价格）"""
    pricing = get_model_pricing("gpt-4o-2024-11-20")
    assert pricing == MODEL_PRICING["gpt-4o"]
