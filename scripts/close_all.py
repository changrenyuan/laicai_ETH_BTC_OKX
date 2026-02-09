"""
🛠 一键平仓脚本
紧急情况下平掉所有持仓
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.rebalancer import Rebalancer
from core.context import Context
from exchange.okx_client import OKXClient
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager
from monitor.notifier import Notifier
import yaml


async def main():
    """主函数"""
    print("=" * 60)
    print("🔥 一键平仓脚本")
    print("=" * 60)

    # 确认
    confirm = input("\n⚠️  警告：此操作将平掉所有持仓！\n确定要继续吗？(yes/no): ")

    if confirm.lower() != "yes":
        print("❌ 操作已取消")
        return 0

    print("\n开始平仓流程...")

    # 加载配置
    print("\n📋 加载配置...")

    config_dir = Path(__file__).parent.parent / "config"

    with open(config_dir / "account.yaml", "r", encoding="utf-8") as f:
        account_config = yaml.safe_load(f)

    with open(config_dir / "risk.yaml", "r", encoding="utf-8") as f:
        risk_config = yaml.safe_load(f)

    # 创建上下文
    print("创建上下文...")
    context = Context(config_dir="config", data_dir="data")

    # 创建交易所客户端
    print("连接交易所...")
    okx_client = OKXClient(account_config["sub_account"])
    await okx_client.connect()

    # 创建通知器
    notifier = Notifier(risk_config)

    # 创建订单管理器
    order_manager = OrderManager({}, okx_client)

    # 创建持仓管理器
    position_manager = PositionManager({}, order_manager, okx_client)

    # 创建再平衡器
    rebalancer = Rebalancer({}, None, position_manager, okx_client)

    try:
        # 获取当前持仓
        print("\n📊 获取当前持仓...")

        from exchange.account_data import AccountDataFetcher
        account_fetcher = AccountDataFetcher(okx_client, {})

        all_positions = await account_fetcher.get_all_positions()

        if not all_positions:
            print("✅ 当前没有持仓")
            return 0

        print(f"发现 {len(all_positions)} 个持仓:")
        for symbol, position in all_positions.items():
            print(f"  - {symbol}: {position.quantity} @ ${position.entry_price:.2f}")

        # 获取市场数据
        print("\n📊 获取市场数据...")
        from exchange.market_data import MarketDataFetcher
        market_fetcher = MarketDataFetcher(okx_client, {})

        for symbol in all_positions.keys():
            market_data = await market_fetcher.get_market_data(symbol)
            if market_data:
                context.update_market_data(market_data)

        # 更新持仓信息
        for symbol, position in all_positions.items():
            context.update_position(position)

        # 执行平仓
        print("\n🔄 执行平仓操作...")

        success = await rebalancer.emergency_close_all(context, notifier)

        if success:
            print("\n✅ 所有持仓已成功平仓")

            # 发送通知
            await notifier.send_alert("🔥 紧急平仓：所有持仓已平掉", level="critical")

            return 0
        else:
            print("\n❌ 平仓失败，请检查日志")
            return 1

    except Exception as e:
        print(f"\n❌ 平仓过程中出错: {e}")
        import traceback
        traceback.print_exc()

        await notifier.send_alert(f"🔥 紧急平仓失败: {e}", level="critical")

        return 1

    finally:
        # 断开连接
        await okx_client.disconnect()
        print("\n🔌 已断开交易所连接")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
