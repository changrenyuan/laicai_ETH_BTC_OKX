"""
✅ 风险管理测试
测试风险管理模块的功能
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context import Context, Balance, Position
from risk.margin_guard import MarginGuard
from risk.circuit_breaker import CircuitBreaker
import yaml


async def test_margin_guard():
    """测试保证金防护"""
    print("\n" + "=" * 60)
    print("🧪 保证金防护测试")
    print("=" * 60)

    # 创建配置
    config = {
        "margin_ratio_warning": 0.80,
        "margin_ratio_critical": 0.60,
        "margin_ratio_stop": 0.50,
        "auto_add_margin": True,
        "auto_reduce_position": True,
    }

    margin_guard = MarginGuard(config)
    context = Context(config_dir="config", data_dir="data")

    # 添加余额和持仓
    context.update_balance("USDT", 50000, 0)

    position = Position(
        symbol="BTC-USDT",
        side="cash_and_carry",
        quantity=1.0,
        entry_price=50000,
        current_price=50000,
        unrealized_pnl=0.0,
        margin_used=25000,  # 使用50%保证金
        leverage=1.0,
    )
    context.update_position(position)

    print("\n1️⃣  测试正常情况 (margin_ratio = 200%)")
    result = await margin_guard.check(context)
    assert not result.is_warning
    assert not result.is_critical
    assert not result.is_emergency
    print(f"  ✅ 保证金率: {result.margin_ratio:.2%} - 正常")

    print("\n2️⃣  测试警告情况 (margin_ratio = 85%)")
    position.margin_used = 58823.53  # 降低保证金率
    context.update_position(position)
    result = await margin_guard.check(context)
    assert result.is_warning
    assert not result.is_critical
    assert not result.is_emergency
    print(f"  ✅ 保证金率: {result.margin_ratio:.2%} - 警告")

    print("\n3️⃣  测试危险情况 (margin_ratio = 65%)")
    position.margin_used = 76923.08
    context.update_position(position)
    result = await margin_guard.check(context)
    assert result.is_warning
    assert result.is_critical
    assert not result.is_emergency
    print(f"  ✅ 保证金率: {result.margin_ratio:.2%} - 危险")

    print("\n4️⃣  测试紧急情况 (margin_ratio = 45%)")
    position.margin_used = 111111.11
    context.update_position(position)
    result = await margin_guard.check(context)
    assert result.is_warning
    assert result.is_critical
    assert result.is_emergency
    print(f"  ✅ 保证金率: {result.margin_ratio:.2%} - 紧急")

    print("\n✅ 保证金防护测试通过")

    return True


async def test_circuit_breaker():
    """测试熔断器"""
    print("\n" + "=" * 60)
    print("🧪 熔断器测试")
    print("=" * 60)

    # 创建配置
    config = {
        "max_consecutive_losses": 3,
        "consecutive_loss_threshold": 100,
        "daily_loss_limit": 500,
        "cooldown_period": 3600,
    }

    circuit_breaker = CircuitBreaker(config)
    context = Context(config_dir="config", data_dir="data")

    print("\n1️⃣  测试连续亏损触发熔断")
    context.metrics.daily_pnl = 0

    for i in range(3):
        should_stop = await circuit_breaker.check_loss(context, 150, f"loss_{i+1}")
        if i < 2:
            assert not should_stop
            print(f"  ✅ 第 {i+1} 次亏损: 未触发熔断")
        else:
            assert should_stop
            print(f"  ✅ 第 {i+1} 次亏损: 触发熔断")

    # 重置
    circuit_breaker.reset()
    context.metrics.daily_pnl = 0

    print("\n2️⃣  测试日亏损限额触发熔断")
    for i in range(5):
        should_stop = await circuit_breaker.check_loss(context, 150, f"loss_{i+1}")
        if context.metrics.daily_pnl < 500:
            print(f"  ✅ 日亏损 ${context.metrics.daily_pnl:.2f}: 未达到限额")
        else:
            assert should_stop
            print(f"  ✅ 日亏损 ${context.metrics.daily_pnl:.2f}: 达到限额，触发熔断")
            break

    print("\n✅ 熔断器测试通过")

    return True


async def main():
    """主函数"""
    print("=" * 60)
    print("🧪 风险管理测试套件")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(await test_margin_guard())
    results.append(await test_circuit_breaker())

    # 汇总结果
    print("\n" + "=" * 60)
    print("📋 测试结果汇总")
    print("=" * 60)

    total = len(results)
    passed = sum(results)

    print(f"\n总计: {passed}/{total} 项通过")

    if all(results):
        print("\n✅ 所有测试通过")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
