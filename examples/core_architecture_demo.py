"""
🧪 核心架构使用示例

演示如何使用新架构的核心组件
"""

import asyncio
from core.executor.executor_base import ExecutorConfig
from core.executor.order_executor import OrderExecutor
from core.executor.position_executor import DCAExecutor, TWAPExecutor, GridExecutor
from core.executor.orchestrator import ExecutorOrchestrator
from core.risk.triple_barrier import TripleBarrier
from core.risk.trailing_stop import TrailingStop


async def example_1_simple_order():
    """示例 1：简单订单执行"""
    print("\n=== 示例 1：简单订单执行 ===\n")

    # 创建配置（模拟 exchange）
    class MockExchange:
        async def place_order(self, data):
            return True, "order_123", ""

        async def get_order_status(self, order_id, symbol):
            return {
                "status": "filled",
                "filled_size": 0.1,
                "avg_fill_price": 2000.0,
                "commission": 0.001
            }

        async def get_ticker(self, symbol):
            return {"last_price": 2000.0}

    exchange = MockExchange()

    # 创建 Executor 配置
    config = ExecutorConfig(
        exchange=exchange,
        symbol="ETH-USDT-SWAP",
        side="buy",
        size=0.1,
        price=2000.0,
        stop_price=1950.0,
        take_profit_price=2100.0
    )

    # 创建订单执行器
    executor = OrderExecutor(config)

    # 添加事件监听
    def on_event(event):
        print(f"📢 事件: {event.type.value}")
        print(f"   数据: {event.data}\n")

    executor.add_event_listener(on_event)

    # 启动执行器
    await executor.start()

    # 等待完成
    await asyncio.sleep(2)

    # 查询状态
    status = executor.get_status()
    print(f"📊 执行器状态: {status}\n")


async def example_2_dca_strategy():
    """示例 2：DCA 策略"""
    print("\n=== 示例 2：DCA 策略 ===\n")

    class MockExchange:
        def __init__(self):
            self.order_count = 0

        async def place_order(self, data):
            self.order_count += 1
            return True, f"order_{self.order_count}", ""

        async def get_order_status(self, order_id, symbol):
            return {
                "status": "filled",
                "filled_size": 0.02,
                "avg_fill_price": 2000.0,
                "commission": 0.0002
            }

        async def get_ticker(self, symbol):
            return {"last_price": 2000.0}

    exchange = MockExchange()

    # 创建 DCA 配置
    config = ExecutorConfig(
        exchange=exchange,
        symbol="ETH-USDT-SWAP",
        side="buy",
        size=0.1,
        price=2000.0
    )

    # 创建 DCA 执行器
    dca_executor = DCAExecutor(
        config=config,
        num_orders=5,
        time_interval=1  # 1 秒间隔
    )

    # 添加事件监听
    def on_event(event):
        print(f"📢 事件: {event.type.value}")

    dca_executor.add_event_listener(on_event)

    # 启动
    await dca_executor.start()

    # 等待完成
    await asyncio.sleep(6)

    # 查询状态
    status = dca_executor.get_status()
    print(f"\n📊 DCA 执行状态:")
    print(f"   目标数量: {config.size}")
    print(f"   已成交: {status['filled_size']}")
    print(f"   平均价格: {status['avg_fill_price']}\n")


async def example_3_triple_barrier():
    """示例 3：Triple Barrier 风控"""
    print("\n=== 示例 3：Triple Barrier 风控 ===\n")

    # 创建 Triple Barrier
    triple_barrier = TripleBarrier(
        take_profit_price=2100.0,
        stop_loss_price=1950.0,
        time_limit_seconds=3600
    )

    # 激活
    triple_barrier.activate(start_price=2000.0)

    # 模拟价格变化
    price_scenarios = [
        1980.0,  # 正常
        2100.0,  # 触发止盈
    ]

    for price in price_scenarios:
        action = triple_barrier.check(price, datetime.now())
        print(f"   价格: {price}, 动作: {action.value}")

        if action.value != "none":
            print(f"   ✅ 触发 {action.value}\n")
            break


async def example_4_trailing_stop():
    """示例 4：移动止损"""
    print("\n=== 示例 4：移动止损 ===\n")

    # 创建移动止损
    trailing_stop = TrailingStop(
        mode="percentage",
        activation_distance=0.02,  # 2%
        trailing_distance=0.01,     # 1%
        side="long"
    )

    # 激活
    trailing_stop.activate(entry_price=2000.0)

    # 模拟价格变化
    price_scenarios = [
        2000.0,  # 入场
        2020.0,  # 上涨 1%
        2040.0,  # 上涨 2%（激活移动止损）
        2060.0,  # 上涨 3%（止损位上移）
        2030.0,  # 回调
    ]

    for price in price_scenarios:
        is_triggered, stop_price, reason = trailing_stop.update(price)
        status = trailing_stop.get_status()

        print(f"   价格: {price:.1f}")
        print(f"   止损位: {stop_price:.1f if stop_price else 'N/A'}")
        print(f"   是否触发: {is_triggered}")
        print(f"   状态: {reason}\n")

        if is_triggered:
            print("   ⛔ 触发移动止损！\n")
            break


async def example_5_orchestrator():
    """示例 5：执行器编排器"""
    print("\n=== 示例 5：执行器编排器 ===\n")

    class MockExchange:
        def __init__(self):
            self.order_count = 0

        async def place_order(self, data):
            self.order_count += 1
            return True, f"order_{self.order_count}", ""

        async def get_order_status(self, order_id, symbol):
            return {
                "status": "filled",
                "filled_size": 0.1,
                "avg_fill_price": 2000.0,
                "commission": 0.001
            }

        async def get_ticker(self, symbol):
            return {"last_price": 2000.0}

    exchange = MockExchange()

    # 创建编排器
    orchestrator = ExecutorOrchestrator(max_concurrent_executors=3)

    # 添加事件监听
    def on_event(event):
        print(f"📢 编排器事件: {event.type.value}")

    orchestrator.add_event_listener(on_event)

    # 创建多个执行器
    for i in range(5):
        config = ExecutorConfig(
            exchange=exchange,
            symbol="ETH-USDT-SWAP",
            side="buy",
            size=0.1,
            price=2000.0
        )

        executor = orchestrator.create_order_executor(
            exchange=exchange,
            symbol="ETH-USDT-SWAP",
            side="buy",
            size=0.1,
            price=2000.0
        )

        orchestrator.add_executor(executor)
        print(f"➕ 添加执行器 {i+1}: {executor.executor_id}")

    # 启动编排器
    await orchestrator.start()

    # 等待
    await asyncio.sleep(3)

    # 查询状态
    status = orchestrator.get_orchestrator_status()
    print(f"\n📊 编排器状态:")
    print(f"   总执行器: {status['total_executors']}")
    print(f"   活动中: {status['active_executors']}")
    print(f"   已完成: {status['completed_executors']}")
    print(f"   失败: {status['failed_executors']}\n")

    # 停止
    await orchestrator.stop()


async def main():
    """主函数"""
    print("🚀 核心架构使用示例\n")
    print("=" * 50)

    # 示例 1：简单订单
    await example_1_simple_order()

    # 示例 2：DCA 策略
    await example_2_dca_strategy()

    # 示例 3：Triple Barrier
    from datetime import datetime
    await example_3_triple_barrier()

    # 示例 4：移动止损
    await example_4_trailing_stop()

    # 示例 5：编排器
    await example_5_orchestrator()

    print("\n✅ 所有示例执行完成！\n")


if __name__ == "__main__":
    asyncio.run(main())
