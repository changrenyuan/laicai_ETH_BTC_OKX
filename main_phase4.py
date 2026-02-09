"""
🚀 Phase 4 主程序：策略执行引擎 (修复版)
集成：连接 -> 行情 -> 状态机 -> 策略 -> 下单
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

# 引入核心组件
from exchange.okx_client import OKXClient
from core.context import Context, MarketData
from core.state_machine import StateMachine, SystemState
from core.events import EventBus
from risk.margin_guard import MarginGuard
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager
from strategy.cash_and_carry import CashAndCarryStrategy

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MainPhase4")

async def main():
    print("=" * 60)
    print("🚀 Phase 4: 策略引擎启动 (Live Mode)")
    print("=" * 60)

    # ---------------------------------------------------
    # 1. 初始化基础设施
    # ---------------------------------------------------
    print("\n[1/6] 加载配置...")
    try:
        with open("config/account.yaml", "r", encoding="utf-8") as f:
            account_cfg = yaml.safe_load(f)
        with open("config/strategy.yaml", "r", encoding="utf-8") as f:
            strategy_cfg = yaml.safe_load(f)
        with open("config/risk.yaml", "r", encoding="utf-8") as f:
            risk_cfg = yaml.safe_load(f)

        full_config = {**account_cfg, **strategy_cfg, **risk_cfg}
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
        return

    print("[2/6] 初始化核心组件...")
    event_bus = EventBus()
    state_machine = StateMachine(event_bus)
    context = Context()

    client = OKXClient(account_cfg["sub_account"])
    if not await client.connect():
        logger.error("无法连接交易所")
        return

    print("[3/6] 初始化执行与风控...")
    margin_guard = MarginGuard(risk_cfg)
    order_manager = OrderManager(client, state_machine, event_bus)
    position_manager = PositionManager(context) # 只负责审计

    print("[4/6] 初始化策略...")
    strategy = CashAndCarryStrategy(
        config=full_config,
        context=context,
        state_machine=state_machine,
        order_manager=order_manager,
        margin_guard=margin_guard
    )
    symbol = "ETH-USDT"
    strategy.symbol = symbol

    # ---------------------------------------------------
    # 2. 启动主循环
    # ---------------------------------------------------
    print(f"\n[5/6] 系统就绪，开始监控 {symbol}...")

    # 打印当前状态确认
    current_state = state_machine.get_current_state()
    logger.info(f"当前系统状态: {current_state.value}")

    if current_state != SystemState.IDLE:
        logger.warning("状态异常，尝试重置为 IDLE")
        await state_machine.transition_to(SystemState.IDLE, reason="System Start")

    try:
        while True:
            # --- A. 获取最新行情 ---
            ticker_spot = await client.get_ticker(symbol)
            ticker_swap = await client.get_ticker(f"{symbol}-SWAP")
            funding_res = await client.get_funding_rate(f"{symbol}-SWAP")

            if ticker_spot and ticker_swap and funding_res:
                spot_px = float(ticker_spot[0]['last'])
                swap_px = float(ticker_swap[0]['last'])
                funding = float(funding_res[0]['fundingRate'])

                spread = (swap_px - spot_px) / spot_px

                # 更新 Context
                # 🔥 修复点：补上了 depth={} 参数
                context.market_data[symbol] = MarketData(
                    symbol=symbol,
                    spot_price=spot_px,
                    futures_price=swap_px,
                    funding_rate=funding,
                    next_funding_time=None,
                    volume_24h=0,
                    depth={}  # <--- 之前报错就是缺了这个
                )

                # 打印看板 (使用 \r 实现单行刷新)
                status_icon = "🟢" if spread > 0.001 else "⚪"

                # 优化显示格式
                msg = (f"\r{status_icon} [监控中] "
                       f"现货:{spot_px:<8} | 合约:{swap_px:<8} | "
                       f"价差:{spread:+.4%} | 费率:{funding:+.4%}")
                sys.stdout.write(msg)
                sys.stdout.flush()

                # --- B. 执行策略 ---
                await strategy.run_tick()

            else:
                sys.stdout.write("\r⚠️ 获取行情失败，重试中...")
                sys.stdout.flush()

            await asyncio.sleep(3)

    except KeyboardInterrupt:
        print("\n\n🛑 用户手动停止")
    except Exception as e:
        logger.error(f"\n❌ 主循环异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()
        print("\n系统已安全退出")

if __name__ == "__main__":
    asyncio.run(main())