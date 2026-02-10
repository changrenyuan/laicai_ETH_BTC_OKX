"""
🧠 Cash & Carry 主策略 (Phase 4 最终版)
协调者：获取数据 -> 检查条件 -> 检查风控 -> 执行交易
"""
import logging
import asyncio
from core.context import Context
from core.state_machine import StateMachine, SystemState
from strategy.base_strategy import BaseStrategy
from strategy.conditions import StrategyConditions
from execution.order_manager import OrderManager
from risk.margin_guard import MarginGuard

class CashAndCarryStrategy(BaseStrategy):
    def __init__(self,
                 config: dict,
                 context: Context,
                 state_machine: StateMachine,
                 order_manager: OrderManager,
                 margin_guard: MarginGuard):

        super().__init__(config, context, state_machine, order_manager)
        self.risk = margin_guard
        self.logger = logging.getLogger(__name__)

        self.conditions = StrategyConditions(config)

        # ⚠️ 注意：测试阶段金额较小
        self.order_amount = 10.0
        self.symbol = "ETH-USDT"

    async def initialize(self):
        """策略初始化"""
        self.logger.info("初始化资金费率套利策略...")
        self.is_initialized = True

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

    async def analyze_signal(self) -> dict:
        """
        【9】策略信号判断
        - 检查资金费率是否为正
        - 检查现货和合约价差
        返回信号字典或 None
        """
        # 获取市场数据
        market = self.context.market_data.get(self.symbol)
        if not market:
            return None

        # 检查资金费率
        if market.funding_rate <= 0:
            return None  # 费率为负，不适合套利

        # 检查价差
        price_diff = market.futures_price - market.spot_price
        price_diff_pct = price_diff / market.spot_price

        # 如果价差太大，可能有大风险
        if price_diff_pct > 0.05:  # 5%
            return None

        # 返回开仓信号
        return {
            "type": "carry",
            "symbol": self.symbol,
            "price": market.spot_price,
            "size": self.order_amount / market.spot_price,
            "funding_rate": market.funding_rate
        }

    async def execute(self, signal: dict, approval: dict) -> dict:
        """
        【12】执行交易
        - 原子下单（现货买入 + 合约做空）
        - 处理跛脚/撤单/补单
        - 对冲检查
        """
        result = {
            "success": False,
            "error": "",
            "position": None,
            "order_id": ""
        }

        try:
            # 计算数量
            qty = round(self.order_amount / signal["price"], 3)

            if qty < 0.001:
                result["error"] = "下单数量太小"
                return result

            # 执行双腿套利
            success = await self.om.execute_dual_leg(
                spot_symbol=self.symbol,
                spot_size=qty,
                swap_symbol=f"{self.symbol}-SWAP",
                swap_size=signal["size"]
            )

            result["success"] = success
            if success:
                result["position"] = {
                    "symbol": self.symbol,
                    "side": "carry",
                    "spot_size": qty,
                    "swap_size": signal["size"]
                }
            else:
                result["error"] = "双腿下单失败"

            return result

        except Exception as e:
            result["error"] = str(e)
            self.logger.error(f"执行异常: {e}")
            return result

    async def shutdown(self):
        """策略停止时的清理工作"""
        self.logger.warning("🛑 资金费率套利策略停止...")
        # TODO: 如果需要，可以在这里实现平仓逻辑