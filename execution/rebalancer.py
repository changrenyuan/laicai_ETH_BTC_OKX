"""
✋ 再平衡器
数量偏差修正
"""

from dataclasses import dataclass
from typing import Dict, Optional
import logging

from core.context import Context


@dataclass
class RebalanceAction:
    """再平衡动作"""

    symbol: str
    action_type: str  # add_margin, reduce_position, adjust_hedge
    amount: float
    reason: str


class Rebalancer:
    """
    再平衡器类
    处理各种再平衡操作
    """

    def __init__(self, config: dict, fund_guard=None, position_manager=None, exchange_client=None):
        self.config = config
        self.fund_guard = fund_guard
        self.position_manager = position_manager
        self.exchange_client = exchange_client

        self.logger = logging.getLogger(__name__)

    async def rebalance_positions(
        self,
        context: Context,
        notifier=None,
    ) -> bool:
        """
        再平衡所有持仓

        Args:
            context: 上下文
            notifier: 通知器

        Returns:
            bool: 是否成功
        """
        self.logger.info("Starting position rebalancing")

        try:
            # 1. 检查保证金再平衡
            margin_rebalanced = await self._rebalance_margin(context, notifier)

            # 2. 检查对冲再平衡
            hedge_rebalanced = await self._rebalance_hedge(context, notifier)

            if margin_rebalanced or hedge_rebalanced:
                self.logger.info("Position rebalancing completed")
                if notifier:
                    await notifier.send_alert("Position rebalancing completed", level="info")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to rebalance positions: {e}")
            if notifier:
                await notifier.send_alert(f"Rebalancing failed: {e}", level="error")
            return False

    async def _rebalance_margin(
        self,
        context: Context,
        notifier=None,
    ) -> bool:
        """
        再平衡保证金

        Args:
            context: 上下文
            notifier: 通知器

        Returns:
            bool: 是否执行了再平衡
        """
        # 检查是否需要再平衡
        need_rebalance = await self.fund_guard.check_rebalance_needed(context)

        if not need_rebalance:
            return False

        # 计算划转金额
        transfer_amount = await self.fund_guard.calculate_transfer_amount(context)

        if transfer_amount <= 0:
            self.logger.info("No transfer needed")
            return False

        # 执行划转
        success = await self.fund_guard.execute_transfer(
            transfer_amount,
            context,
            self.exchange_client,
        )

        if success and notifier:
            await notifier.send_alert(
                f"Margin rebalanced: +${transfer_amount:.2f} USDT transferred",
                level="info",
            )

        return success

    async def _rebalance_hedge(
        self,
        context: Context,
        notifier=None,
    ) -> bool:
        """
        再平衡对冲

        Args:
            context: 上下文
            notifier: 通知器

        Returns:
            bool: 是否执行了再平衡
        """
        rebalanced = False

        for symbol in context.positions.keys():
            # 检查并调整对冲
            hedge_adjusted = await self.position_manager.rebalance_hedge(symbol, context)

            if hedge_adjusted:
                rebalanced = True
                self.logger.info(f"Hedge rebalanced for {symbol}")

        if rebalanced and notifier:
            await notifier.send_alert("Hedge rebalancing completed", level="info")

        return rebalanced

    async def emergency_close_all(
        self,
        context: Context,
        notifier=None,
    ) -> bool:
        """
        紧急平仓

        Args:
            context: 上下文
            notifier: 通知器

        Returns:
            bool: 是否成功
        """
        self.logger.error("EMERGENCY: Closing all positions")

        try:
            success = True

            # 平掉所有持仓
            for symbol in list(context.positions.keys()):
                close_success = await self.position_manager.close_cash_and_carry(
                    symbol,
                    context,
                )
                if not close_success:
                    success = False
                    self.logger.error(f"Failed to close position: {symbol}")

            # 取消所有订单
            await self.position_manager.order_manager.cancel_all_orders()

            if success:
                self.logger.info("All positions closed successfully")
                if notifier:
                    await notifier.send_alert(
                        "EMERGENCY: All positions closed",
                        level="critical",
                    )
            else:
                self.logger.error("Some positions failed to close")
                if notifier:
                    await notifier.send_alert(
                        "EMERGENCY: Some positions failed to close",
                        level="critical",
                    )

            return success

        except Exception as e:
            self.logger.error(f"Failed to emergency close all: {e}")
            if notifier:
                await notifier.send_alert(
                    f"EMERGENCY: Failed to close all positions: {e}",
                    level="critical",
                )
            return False

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "config": self.config,
        }
