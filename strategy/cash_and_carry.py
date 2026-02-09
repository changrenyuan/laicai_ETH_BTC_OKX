"""
🧠 Cash & Carry 策略（核心策略）
资金费率套利策略，唯一主策略
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
import logging

from core.context import Context
from core.events import Event, EventType, StrategyEvent
from .conditions import ConditionChecker, OpenCondition, CloseCondition


@dataclass
class StrategySignal:
    """策略信号"""

    action: str  # open, close, hold
    symbol: str
    quantity: float
    confidence: float  # 信心度 0-1
    reason: str
    urgency: int = 0  # 紧急程度 0-10


class CashAndCarryStrategy:
    """
    Cash & Carry 策略类
    资金费率套利策略
    """

    def __init__(self, config: dict, event_bus=None):
        self.config = config
        self.enabled = config.get("enabled", True)
        self.dry_run = config.get("dry_run", False)

        # 子模块
        self.condition_checker = ConditionChecker(
            config.get("open_conditions", {}),
        )

        # 策略配置
        self.strategy_config = config.get("cash_and_carry", {})
        self.open_conditions_config = self.strategy_config.get("open_conditions", {})
        self.close_conditions_config = self.strategy_config.get("close_conditions", {})
        self.position_management = self.strategy_config.get("position_management", {})

        self.event_bus = event_bus
        self.logger = logging.getLogger(__name__)

        # 状态
        self.active_positions: Dict[str, Dict] = {}  # {symbol: {entry_time, entry_price, quantity}}

    async def analyze(
        self,
        symbol: str,
        context: Context,
    ) -> StrategySignal:
        """
        分析市场，生成策略信号

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            StrategySignal: 策略信号
        """
        if not self.enabled:
            return StrategySignal(
                action="hold",
                symbol=symbol,
                quantity=0.0,
                confidence=0.0,
                reason="策略未启用",
            )

        # 检查是否已有持仓
        position = context.get_position(symbol)
        has_position = position is not None and position.quantity > 0

        if has_position:
            # 检查平仓条件
            return await self._check_close_conditions(symbol, context, position)
        else:
            # 检查开仓条件
            return await self._check_open_conditions(symbol, context)

    async def _check_open_conditions(
        self,
        symbol: str,
        context: Context,
    ) -> StrategySignal:
        """检查开仓条件"""
        conditions = await self.condition_checker.check_open_conditions(
            symbol,
            context,
        )

        # 判断是否应该开仓
        should_open = self.condition_checker.should_open(conditions)

        if should_open:
            # 计算开仓数量
            quantity = await self._calculate_open_quantity(symbol, context)

            # 计算信心度
            confidence = min(1.0, sum(c.confidence for c in conditions) / len(conditions))

            # 生成原因
            reason = "; ".join([c.reason for c in conditions if c.is_met])

            signal = StrategySignal(
                action="open",
                symbol=symbol,
                quantity=quantity,
                confidence=confidence,
                reason=reason,
            )

            self.logger.info(f"Open signal generated for {symbol}: {quantity} @ {confidence:.2%}")

            # 发布事件
            if self.event_bus:
                await self.event_bus.publish(
                    StrategyEvent(
                        event_type=EventType.STRATEGY_SIGNAL,
                        symbol=symbol,
                        action="open",
                        quantity=quantity,
                        confidence=confidence,
                        data={"reason": reason},
                    )
                )

            return signal
        else:
            return StrategySignal(
                action="hold",
                symbol=symbol,
                quantity=0.0,
                confidence=0.0,
                reason="开仓条件未满足: " + "; ".join([c.reason for c in conditions if not c.is_met]),
            )

    async def _check_close_conditions(
        self,
        symbol: str,
        context: Context,
        position,
    ) -> StrategySignal:
        """检查平仓条件"""
        conditions = await self.condition_checker.check_close_conditions(
            symbol,
            context,
        )

        # 判断是否应该平仓
        should_close = self.condition_checker.should_close(conditions)

        if should_close:
            # 获取平仓数量
            quantity = position.quantity

            # 获取紧急程度
            urgency = self.condition_checker.get_close_urgency(conditions)

            # 生成原因
            met_conditions = [c.reason for c in conditions if c.is_met]
            reason = "; ".join(met_conditions)

            signal = StrategySignal(
                action="close",
                symbol=symbol,
                quantity=quantity,
                confidence=1.0,  # 平仓信号信心度始终为1
                reason=reason,
                urgency=urgency,
            )

            self.logger.info(
                f"Close signal generated for {symbol}: {quantity} (urgency: {urgency})"
            )

            # 发布事件
            if self.event_bus:
                await self.event_bus.publish(
                    StrategyEvent(
                        event_type=EventType.STRATEGY_SIGNAL,
                        symbol=symbol,
                        action="close",
                        quantity=quantity,
                        confidence=1.0,
                        data={"reason": reason, "urgency": urgency},
                    )
                )

            return signal
        else:
            return StrategySignal(
                action="hold",
                symbol=symbol,
                quantity=position.quantity,
                confidence=0.0,
                reason="平仓条件未满足",
            )

    async def _calculate_open_quantity(
        self,
        symbol: str,
        context: Context,
    ) -> float:
        """
        计算开仓数量

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            float: 开仓数量
        """
        # 获取配置
        position_config = self.position_management
        initial_ratio = position_config.get("initial_position_ratio", 0.5)

        # 获取市场数据
        market_data = context.get_market_data(symbol)
        if not market_data:
            return 0.0

        # 计算可用资金
        total_balance = context.get_total_balance("USDT")
        available_capital = total_balance * initial_ratio

        # 计算最大持仓价值
        max_position_value = position_config.get("max_position_value", 50000)
        position_value = min(available_capital, max_position_value)

        # 计算数量（考虑现货和合约对冲）
        # 需要现货和合约各一半资金
        spot_value = position_value / 2
        futures_value = position_value / 2

        # 现货数量
        spot_quantity = spot_value / market_data.spot_price
        futures_quantity = futures_value / market_data.futures_price

        # 返回较小的数量（确保完全对冲）
        quantity = min(spot_quantity, futures_quantity)

        self.logger.info(
            f"Calculated open quantity for {symbol}: "
            f"{quantity:.4f} (value: ${position_value:.2f})"
        )

        return quantity

    async def check_rebalance(
        self,
        context: Context,
    ) -> bool:
        """
        检查是否需要再平衡

        Args:
            context: 上下文

        Returns:
            bool: 是否需要再平衡
        """
        # 检查保证金率
        margin_ratio = context.calculate_margin_ratio()
        margin_threshold = self.open_conditions_config.get("funding_rate_threshold", 0.0001)

        # 如果保证金率过低，需要再平衡
        if margin_ratio < 0.80:
            self.logger.info(f"Rebalance needed: margin ratio {margin_ratio:.2%} < 80%")
            return True

        # 检查持仓偏差
        for symbol, position in context.positions.items():
            market_data = context.get_market_data(symbol)
            if not market_data:
                continue

            # 计算现货和合约价值偏差
            spot_value = position.quantity * market_data.spot_price
            futures_value = position.quantity * market_data.futures_price

            deviation = abs(spot_value - futures_value) / max(spot_value, futures_value)

            # 如果偏差超过 1%，需要再平衡
            if deviation > 0.01:
                self.logger.info(
                    f"Rebalance needed for {symbol}: deviation {deviation:.2%}"
                )
                return True

        return False

    def enable(self):
        """启用策略"""
        self.enabled = True
        self.logger.info("Cash & Carry strategy enabled")

    def disable(self):
        """禁用策略"""
        self.enabled = False
        self.logger.info("Cash & Carry strategy disabled")

    def set_dry_run(self, dry_run: bool):
        """设置空跑模式"""
        self.dry_run = dry_run
        self.logger.info(f"Strategy dry run mode: {dry_run}")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "active_positions": self.active_positions,
            "config": self.config,
        }
