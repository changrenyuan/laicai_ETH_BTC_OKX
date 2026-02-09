"""
🧠 Cash & Carry 主策略 (Phase 4 最终版)
协调者：获取数据 -> 检查条件 -> 检查风控 -> 执行交易
"""
import logging
import asyncio
from core.context import Context
from core.state_machine import StateMachine, SystemState
from strategy.conditions import StrategyConditions
from execution.order_manager import OrderManager
from risk.margin_guard import MarginGuard

class CashAndCarryStrategy:
    def __init__(self,
                 config: dict,
                 context: Context,
                 state_machine: StateMachine,
                 order_manager: OrderManager,
                 margin_guard: MarginGuard):

        self.config = config
        self.context = context
        self.sm = state_machine
        self.om = order_manager
        self.risk = margin_guard
        self.logger = logging.getLogger(__name__)

        self.conditions = StrategyConditions(config)

        # ⚠️ 注意：测试阶段金额较小
        self.order_amount = 10.0
        self.symbol = "ETH-USDT"

    async def run_tick(self):
        """
        执行一次策略循环 (被 Scheduler 调用)
        """
        # 1. 状态检查
        if not self.sm.is_in_state(SystemState.IDLE):
            return

        # 2. 获取数据 (从 Context 快照中取)
        market = self.context.market_data.get(self.symbol)
        if not market:
            return

        spot_price = market.spot_price
        swap_price = market.futures_price
        funding_rate = market.funding_rate

        # 3. 检查开仓信号
        if self.conditions.should_open(spot_price, swap_price, funding_rate):

            # 4. 风控检查
            if self.context.is_emergency:
                self.logger.warning("策略有信号，但系统处于紧急状态")
                return

            # 5. 状态转换 -> OPENING
            # 🔥 修复：使用 await transition_to
            await self.sm.transition_to(SystemState.OPENING_POSITION, reason="Open Signal")

            try:
                # 计算数量 (简单示例，Phase 5 需加强精度控制)
                qty = round(self.order_amount / spot_price, 3)

                if qty < 0.001:
                    self.logger.warning("下单数量太小，忽略")
                    return

                # 6. 执行！(调用 OrderManager 的原子下单)
                # ⚠️ 注意：swap_size "1" 代表 1 张。
                # 请根据实际情况调整：ETH-USDT-SWAP 1张=0.1 ETH
                success = await self.om.execute_dual_leg(
                    spot_symbol=self.symbol,
                    spot_size=qty,
                    swap_symbol=f"{self.symbol}-SWAP",
                    swap_size="1"
                )

            finally:
                # 无论成功失败，如果没进 ERROR，就回 IDLE
                # 🔥 修复：使用 await transition_to
                if not self.sm.is_in_state(SystemState.ERROR):
                    await self.sm.transition_to(SystemState.IDLE, reason="Exec Done")