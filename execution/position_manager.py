"""
✋ 持仓管理器
现货 ↔ 合约 对冲管理
"""

from dataclasses import dataclass
from typing import Optional, Dict
import logging

from core.context import Context, Position


class PositionManager:
    """
    持仓管理器类
    管理现货和合约的对冲持仓
    """

    def __init__(self, config: dict, order_manager=None, exchange_client=None):
        self.config = config
        self.order_manager = order_manager
        self.exchange_client = exchange_client

        self.logger = logging.getLogger(__name__)

    async def open_cash_and_carry(
        self,
        symbol: str,
        quantity: float,
        context: Context,
    ) -> bool:
        """
        开启 Cash & Carry 持仓
        同时买入现货和做空合约

        Args:
            symbol: 交易品种
            quantity: 数量
            context: 上下文

        Returns:
            bool: 是否成功
        """
        try:
            # 获取市场数据
            market_data = context.get_market_data(symbol)
            if not market_data:
                self.logger.error(f"No market data for {symbol}")
                return False

            # 1. 买入现货
            spot_order = await self.order_manager.submit_order(
                symbol=market_data.spot_symbol,
                side="buy",
                quantity=quantity,
                order_type="market",
            )

            if not spot_order:
                self.logger.error(f"Failed to buy spot: {symbol}")
                return False

            # 2. 做空合约（相同数量）
            futures_order = await self.order_manager.submit_order(
                symbol=market_data.futures_symbol,
                side="sell",
                quantity=quantity,
                order_type="market",
                reduce_only=False,
            )

            if not futures_order:
                self.logger.error(f"Failed to sell futures: {symbol}")
                # 回滚：卖出现货
                await self.order_manager.submit_order(
                    symbol=market_data.spot_symbol,
                    side="sell",
                    quantity=quantity,
                    order_type="market",
                )
                return False

            # 记录持仓
            context.update_position(
                Position(
                    symbol=symbol,
                    side="cash_and_carry",
                    quantity=quantity,
                    entry_price=market_data.spot_price,
                    current_price=market_data.spot_price,
                    unrealized_pnl=0.0,
                    margin_used=0.0,
                    leverage=1.0,
                )
            )

            self.logger.info(
                f"Opened Cash & Carry position: {symbol} {quantity} "
                f"(spot: {spot_order.order_id}, futures: {futures_order.order_id})"
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to open Cash & Carry position: {e}")
            return False

    async def close_cash_and_carry(
        self,
        symbol: str,
        context: Context,
    ) -> bool:
        """
        关闭 Cash & Carry 持仓
        同时卖出现货和平掉合约

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            bool: 是否成功
        """
        try:
            # 获取持仓
            position = context.get_position(symbol)
            if not position or position.quantity == 0:
                self.logger.warning(f"No position to close: {symbol}")
                return False

            quantity = position.quantity

            # 获取市场数据
            market_data = context.get_market_data(symbol)
            if not market_data:
                self.logger.error(f"No market data for {symbol}")
                return False

            # 1. 卖出现货
            spot_order = await self.order_manager.submit_order(
                symbol=market_data.spot_symbol,
                side="sell",
                quantity=quantity,
                order_type="market",
            )

            if not spot_order:
                self.logger.error(f"Failed to sell spot: {symbol}")
                return False

            # 2. 平掉合约（买入平空）
            futures_order = await self.order_manager.submit_order(
                symbol=market_data.futures_symbol,
                side="buy",
                quantity=quantity,
                order_type="market",
                reduce_only=True,
            )

            if not futures_order:
                self.logger.error(f"Failed to close futures: {symbol}")
                return False

            # 计算盈亏
            pnl = (market_data.spot_price - position.entry_price) * quantity
            funding_income = await context.calculate_funding_income()
            total_pnl = pnl + funding_income

            # 更新指标
            context.metrics.total_pnl += total_pnl
            context.metrics.daily_pnl += total_pnl
            context.metrics.total_trades += 1
            context.metrics.daily_trades += 1

            # 移除持仓
            if symbol in context.positions:
                del context.positions[symbol]

            self.logger.info(
                f"Closed Cash & Carry position: {symbol} {quantity} "
                f"(PnL: ${total_pnl:.2f}, Funding: ${funding_income:.2f})"
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to close Cash & Carry position: {e}")
            return False

    async def check_hedge_ratio(
        self,
        symbol: str,
        context: Context,
    ) -> float:
        """
        检查对冲比率

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            float: 对冲比率，1.0 表示完全对冲
        """
        # 获取持仓
        position = context.get_position(symbol)
        if not position or position.quantity == 0:
            return 1.0

        # 获取市场数据
        market_data = context.get_market_data(symbol)
        if not market_data:
            return 1.0

        # TODO: 从交易所获取实际的现货和合约持仓数量
        spot_quantity = position.quantity  # 假设
        futures_quantity = position.quantity  # 假设

        # 计算对冲比率
        hedge_ratio = min(spot_quantity, futures_quantity) / max(spot_quantity, futures_quantity)

        return hedge_ratio

    async def rebalance_hedge(
        self,
        symbol: str,
        context: Context,
    ) -> bool:
        """
        重新平衡对冲

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            bool: 是否成功
        """
        try:
            hedge_ratio = await self.check_hedge_ratio(symbol, context)

            # 如果对冲比率低于 99%，需要调整
            if hedge_ratio < 0.99:
                self.logger.info(f"Rebalancing hedge for {symbol}: ratio {hedge_ratio:.2%}")

                # TODO: 实现具体的再平衡逻辑
                # 计算需要调整的数量
                # 执行调整操作

                return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to rebalance hedge: {e}")
            return False

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "config": self.config,
        }
