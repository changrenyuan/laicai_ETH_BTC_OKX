"""
🛠 空跑脚本
模拟运行，不执行真实交易
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context import Context
from core.state_machine import StateMachine
from core.scheduler import Scheduler
from core.events import EventBus
from strategy.cash_and_carry import CashAndCarryStrategy
import yaml


class MockMarketData:
    """模拟市场数据"""

    @staticmethod
    def get_market_data(symbol: str):
        """获取模拟市场数据"""
        from core.context import MarketData

        base_price = 50000 if "BTC" in symbol else 3000

        return MarketData(
            symbol=symbol,
            spot_price=base_price,
            futures_price=base_price * 1.001,
            funding_rate=0.0001,
            next_funding_time=datetime.now(),
            volume_24h=1000000,
            depth={
                "bid_1_price": base_price * 0.9999,
                "bid_1_amount": 10.0,
                "ask_1_price": base_price * 1.0001,
                "ask_1_amount": 10.0,
            },
        )


async def main():
    """主函数"""
    print("=" * 60)
    print("🔮 空跑模式（模拟运行）")
    print("=" * 60)

    # 加载配置
    print("\n📋 加载配置...")

    config_dir = Path(__file__).parent.parent / "config"

    with open(config_dir / "account.yaml", "r", encoding="utf-8") as f:
        account_config = yaml.safe_load(f)

    with open(config_dir / "strategy.yaml", "r", encoding="utf-8") as f:
        strategy_config = yaml.safe_load(f)

    with open(config_dir / "instruments.yaml", "r", encoding="utf-8") as f:
        instruments_config = yaml.safe_load(f)

    # 创建上下文
    print("创建上下文...")
    context = Context(config_dir="config", data_dir="data")

    # 初始化账户余额
    print("初始化账户余额...")
    from core.context import Balance
    context.update_balance("USDT", 50000, 5000)

    # 创建事件总线
    event_bus = EventBus()

    # 创建状态机
    print("创建状态机...")
    state_machine = StateMachine(event_bus)

    # 创建策略（设置空跑模式）
    print("创建策略...")
    strategy = CashAndCarryStrategy(strategy_config, event_bus)
    strategy.set_dry_run(True)

    # 模拟市场数据
    print("\n📊 模拟市场数据...")

    for instrument in instruments_config["instruments"]:
        if instrument["enabled"]:
            symbol = instrument["symbol"]
            market_data = MockMarketData.get_market_data(symbol)
            context.update_market_data(market_data)
            print(f"  - {symbol}: spot=${market_data.spot_price:.2f}, funding={market_data.funding_rate:.4%}")

    # 运行策略分析
    print("\n🧠 运行策略分析...")

    for instrument in instruments_config["instruments"]:
        if instrument["enabled"]:
            symbol = instrument["symbol"]

            print(f"\n分析 {symbol}:")

            signal = await strategy.analyze(symbol, context)

            print(f"  信号: {signal.action}")
            print(f"  数量: {signal.quantity}")
            print(f"  信心度: {signal.confidence:.2%}")
            print(f"  原因: {signal.reason}")

            if signal.action == "open":
                print(f"  💡 建议开仓: {signal.quantity} {symbol}")

                # 模拟开仓
                from core.context import Position
                market_data = context.get_market_data(symbol)
                context.update_position(
                    Position(
                        symbol=symbol,
                        side="cash_and_carry",
                        quantity=signal.quantity,
                        entry_price=market_data.spot_price,
                        current_price=market_data.spot_price,
                        unrealized_pnl=0.0,
                        margin_used=0.0,
                        leverage=1.0,
                    )
                )
                print(f"  ✅ 已模拟开仓")

            elif signal.action == "close":
                print(f"  💡 建议平仓: {signal.quantity} {symbol}")

                # 模拟平仓
                if symbol in context.positions:
                    del context.positions[symbol]
                    print(f"  ✅ 已模拟平仓")

            elif signal.action == "hold":
                print(f"  ⏸️  保持现状")

    # 显示当前状态
    print("\n📊 当前状态:")
    print(f"  余额: ${context.get_total_balance('USDT'):.2f}")
    print(f"  持仓数: {len(context.positions)}")
    print(f"  保证金率: {context.calculate_margin_ratio():.2%}")

    if context.positions:
        print("\n  持仓明细:")
        for symbol, position in context.positions.items():
            print(f"    - {symbol}: {position.quantity} @ ${position.entry_price:.2f}")

    # 运行时间
    duration = 30  # 模拟运行30秒
    print(f"\n⏱️  模拟运行 {duration} 秒...")

    start_time = datetime.now()

    while (datetime.now() - start_time).total_seconds() < duration:
        await asyncio.sleep(5)

        # 更新模拟市场数据
        for instrument in instruments_config["instruments"]:
            if instrument["enabled"]:
                symbol = instrument["symbol"]
                market_data = MockMarketData.get_market_data(symbol)
                context.update_market_data(market_data)

        # 重新分析
        for instrument in instruments_config["instruments"]:
            if instrument["enabled"]:
                symbol = instrument["symbol"]
                signal = await strategy.analyze(symbol, context)

                if signal.action != "hold":
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {symbol}: {signal.action} - {signal.reason}")

        # 检查健康状态
        from monitor.health_check import HealthChecker
        health_checker = HealthChecker({}, event_bus)
        health_status = await health_checker.check_all(context)

        print(f"  健康状态: {'✅ 正常' if all(health_status.values()) else '❌ 异常'}")

    print("\n" + "=" * 60)
    print("✅ 空跑完成")
    print("=" * 60)

    print("\n💡 提示: 这只是模拟运行，没有执行真实交易")
    print("💡 要启用真实交易，请在 config/strategy.yaml 中设置 dry_run: false")

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏸️  用户中断")
        sys.exit(0)
