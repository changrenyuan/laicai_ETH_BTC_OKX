"""
✅ 执行模块测试
测试订单管理和持仓管理功能
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.order_manager import OrderManager
from core.context import Context
from datetime import datetime


async def test_order_manager():
    """测试订单管理器"""
    print("\n" + "=" * 60)
    print("🧪 订单管理器测试")
    print("=" * 60)

    config = {}
    order_manager = OrderManager(config)

    print("\n1️⃣  测试提交订单")
    order = await order_manager.submit_order(
        symbol="BTC-USDT-SWAP",
        side="buy",
        quantity=0.1,
        price=50000,
        order_type="limit",
    )

    assert order is not None
    assert order.status == "submitted"
    print(f"  ✅ 订单提交成功: {order.order_id}")

    print("\n2️⃣  测试获取订单")
    retrieved_order = order_manager.get_order(order.order_id)
    assert retrieved_order == order
    print(f"  ✅ 获取订单成功")

    print("\n3️⃣  测试获取待处理订单")
    pending_orders = order_manager.get_pending_orders()
    assert len(pending_orders) == 1
    assert pending_orders[0].order_id == order.order_id
    print(f"  ✅ 待处理订单数: {len(pending_orders)}")

    print("\n4️⃣  测试取消订单")
    cancelled = await order_manager.cancel_order(order.order_id)
    assert cancelled
    print(f"  ✅ 订单取消成功")

    print("\n5️⃣  测试取消后状态")
    updated_order = order_manager.get_order(order.order_id)
    assert updated_order.status == "cancelled"
    pending_orders = order_manager.get_pending_orders()
    assert len(pending_orders) == 0
    print(f"  ✅ 订单状态已更新，无待处理订单")

    print("\n✅ 订单管理器测试通过")

    return True


async def test_context():
    """测试上下文管理器"""
    print("\n" + "=" * 60)
    print("🧪 上下文管理器测试")
    print("=" * 60)

    context = Context(config_dir="config", data_dir="data")

    print("\n1️⃣  测试余额更新")
    context.update_balance("USDT", 50000, 5000)
    balance = context.get_balance("USDT")
    assert balance is not None
    assert balance.available == 50000
    assert balance.frozen == 5000
    assert balance.total == 55000
    print(f"  ✅ 余额: ${balance.total:.2f} (可用: ${balance.available:.2f}, 冻结: ${balance.frozen:.2f})")

    print("\n2️⃣  测试持仓更新")
    from core.context import Position
    position = Position(
        symbol="BTC-USDT",
        side="long",
        quantity=1.0,
        entry_price=50000,
        current_price=51000,
        unrealized_pnl=1000,
        margin_used=25000,
        leverage=2.0,
    )
    context.update_position(position)

    retrieved_position = context.get_position("BTC-USDT")
    assert retrieved_position is not None
    assert retrieved_position.quantity == 1.0
    assert retrieved_position.unrealized_pnl == 1000
    print(f"  ✅ 持仓: {retrieved_position.quantity} BTC @ ${retrieved_position.entry_price:.2f}")

    print("\n3️⃣  测试保证金率计算")
    margin_ratio = context.calculate_margin_ratio()
    print(f"  ✅ 保证金率: {margin_ratio:.2%}")

    print("\n4️⃣  测试市场数据更新")
    from core.context import MarketData
    market_data = MarketData(
        symbol="BTC-USDT",
        spot_price=51000,
        futures_price=51010,
        funding_rate=0.0001,
        next_funding_time=None,
        volume_24h=1000000,
        depth={"bid_1_price": 50999, "ask_1_price": 51001},
    )
    context.update_market_data(market_data)

    retrieved_market_data = context.get_market_data("BTC-USDT")
    assert retrieved_market_data is not None
    assert retrieved_market_data.spot_price == 51000
    print(f"  ✅ 市场数据: 现货=${retrieved_market_data.spot_price:.2f}, 合约=${retrieved_market_data.futures_price:.2f}")

    print("\n5️⃣  测试保存和加载运行状态")
    context.save_runtime_state()
    print(f"  ✅ 运行状态已保存")

    loaded = context.load_runtime_state()
    assert loaded
    print(f"  ✅ 运行状态已加载")

    print("\n✅ 上下文管理器测试通过")

    return True


async def main():
    """主函数"""
    print("=" * 60)
    print("🧪 执行模块测试套件")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(await test_order_manager())
    results.append(await test_context())

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
