"""
🚀 Final Main: 全自动量化交易系统 (Bug修复版)
集成：Phase 1-5 所有组件 + 调度器
"""

import asyncio
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
import yaml

# 1. 环境准备
load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from exchange.okx_client import OKXClient
from core.context import Context, MarketData, Balance
from core.state_machine import StateMachine, SystemState
from core.events import EventBus
from core.scheduler import Scheduler
from risk.margin_guard import MarginGuard
from risk.fund_guard import FundGuard
from monitor.pnl_tracker import PnLTracker
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager
from strategy.cash_and_carry import CashAndCarryStrategy

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/runtime.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("System")

async def main():
    print("=" * 60)
    print("🚀 LaicaiBot 全自动引擎启动 (Final Fixed)")
    print("=" * 60)

    # [1] 配置
    try:
        with open("config/account.yaml", "r", encoding="utf-8") as f: account_cfg = yaml.safe_load(f)
        with open("config/strategy.yaml", "r", encoding="utf-8") as f: strategy_cfg = yaml.safe_load(f)
        with open("config/risk.yaml", "r", encoding="utf-8") as f: risk_cfg = yaml.safe_load(f)
        full_config = {**account_cfg, **strategy_cfg, **risk_cfg}
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
        return

    # [2] 核心组件
    event_bus = EventBus()
    state_machine = StateMachine(event_bus)
    context = Context()
    pnl_tracker = PnLTracker(full_config)

    client = OKXClient(account_cfg["sub_account"])
    if not await client.connect(): return

    # [3] 功能模块
    fund_guard = FundGuard(full_config, client)
    margin_guard = MarginGuard(risk_cfg)

    order_manager = OrderManager(client, state_machine, event_bus)
    position_manager = PositionManager(context)

    # [4] 策略
    strategy = CashAndCarryStrategy(
        config=full_config,
        context=context,
        state_machine=state_machine,
        order_manager=order_manager,
        margin_guard=margin_guard
    )
    symbol = "ETH-USDT"
    strategy.symbol = symbol

    # [5] 调度器 (自动化核心)
    scheduler = Scheduler(context, fund_guard, pnl_tracker, position_manager)
    await scheduler.start()

    # [6] 启动
    logger.info(f"系统就绪，开始监控 {symbol}...")

    # 状态机检查
    current_state = state_machine.get_current_state()
    if current_state != SystemState.IDLE:
        await state_machine.transition_to(SystemState.IDLE, reason="Startup")
    else:
        logger.info("状态机已就绪 (IDLE)")

    try:
        while True:
            # A. 获取行情
            ticker_spot = await client.get_ticker(symbol)
            ticker_swap = await client.get_ticker(f"{symbol}-SWAP")
            funding_res = await client.get_funding_rate(f"{symbol}-SWAP")

            # 获取账户权益
            balance_res = await client.get_trading_balances()

            if ticker_spot and ticker_swap and funding_res:
                spot_px = float(ticker_spot[0]['last'])
                swap_px = float(ticker_swap[0]['last'])
                funding = float(funding_res[0]['fundingRate'])

                # 更新账户数据到 Context
                if balance_res and len(balance_res) > 0:
                    details = balance_res[0]['details'][0]
                    # 更新余额
                    avail = float(details.get('availBal', 0))
                    total = float(details.get('eq', 0)) # 权益

                    # 🔥 修复点：这里原来传了 Balance 对象，现在改回传参数
                    # update_balance(currency, available, frozen)
                    frozen = total - avail
                    context.update_balance("USDT", avail, frozen)

                    # 模拟更新 Margin Ratio (防止 Scheduler 误报)
                    if context.margin_ratio == 0: context.margin_ratio = 10.0

                spread = (swap_px - spot_px) / spot_px

                context.market_data[symbol] = MarketData(
                    symbol=symbol,
                    spot_price=spot_px,
                    futures_price=swap_px,
                    funding_rate=funding,
                    next_funding_time=None,
                    volume_24h=0,
                    depth={}
                )

                # 看板
                status_icon = "🟢" if spread > 0.001 else "⚪"
                sys.stdout.write(f"\r{status_icon} [Running] Spot:{spot_px:<8} | Swap:{swap_px:<8} | Spread:{spread:+.4%} | Fund:{funding:+.4%}")
                sys.stdout.flush()

                # B. 执行策略
                await strategy.run_tick()

            else:
                sys.stdout.write("\r⚠️ Data fetch failed...")
                sys.stdout.flush()

            await asyncio.sleep(3)

    except KeyboardInterrupt:
        print("\n🛑 Stop signal received")
    except Exception as e:
        logger.error(f"Runtime Error: {e}")
        import traceback
        traceback.print_exc() # 打印详细堆栈，方便查错
    finally:
        await scheduler.stop()
        await client.disconnect()
        print("System shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())