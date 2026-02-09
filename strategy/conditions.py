"""
🧠 开/平仓条件
定义策略的进入和退出条件
"""

from dataclasses import dataclass
from typing import Optional, List
import logging

from core.context import Context


@dataclass
class OpenCondition:
    """开仓条件"""

    name: str
    description: str
    is_met: bool
    confidence: float  # 信心度 0-1
    reason: str


@dataclass
class CloseCondition:
    """平仓条件"""

    name: str
    description: str
    is_met: bool
    urgency: int  # 紧急程度 0-10
    reason: str


class ConditionChecker:
    """
    条件检查器
    检查开仓和平仓条件
    """

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def check_open_conditions(
        self,
        symbol: str,
        context: Context,
    ) -> List[OpenCondition]:
        """
        检查开仓条件

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            List[OpenCondition]: 开仓条件列表
        """
        conditions = []

        # 获取配置
        open_config = self.config.get("open_conditions", {})
        funding_rate_threshold = open_config.get("funding_rate_threshold", 0.0001)
        min_funding_rate = open_config.get("min_funding_rate", 0.00005)
        max_funding_rate = open_config.get("max_funding_rate", 0.01)

        # 获取市场数据
        market_data = context.get_market_data(symbol)
        if not market_data:
            conditions.append(
                OpenCondition(
                    name="market_data",
                    description="市场数据可用性",
                    is_met=False,
                    confidence=0.0,
                    reason="无市场数据",
                )
            )
            return conditions

        # 条件1: 资金费率为正且在合理范围内
        funding_rate = market_data.funding_rate
        funding_rate_ok = (
            funding_rate > funding_rate_threshold
            and min_funding_rate <= funding_rate <= max_funding_rate
        )

        conditions.append(
            OpenCondition(
                name="funding_rate",
                description=f"资金费率 {funding_rate:.4%} > {funding_rate_threshold:.4%}",
                is_met=funding_rate_ok,
                confidence=min(1.0, funding_rate / 0.001) if funding_rate_ok else 0.0,
                reason=(
                    f"资金费率 {funding_rate:.4%}"
                    + (
                        f" 满足条件 ({min_funding_rate:.4%} - {max_funding_rate:.4%})"
                        if funding_rate_ok
                        else f" 不满足条件"
                    )
                ),
            )
        )

        # 条件2: 系统未处于紧急状态
        emergency_ok = not context.is_emergency

        conditions.append(
            OpenCondition(
                name="system_status",
                description="系统状态正常",
                is_met=emergency_ok,
                confidence=1.0 if emergency_ok else 0.0,
                reason="系统正常" if emergency_ok else "系统处于紧急状态",
            )
        )

        # 条件3: 保证金充足
        margin_ratio = context.calculate_margin_ratio()
        margin_ok = margin_ratio > 0.80

        conditions.append(
            OpenCondition(
                name="margin_sufficient",
                description=f"保证金率 {margin_ratio:.2%} > 80%",
                is_met=margin_ok,
                confidence=min(1.0, (margin_ratio - 0.8) * 5) if margin_ok else 0.0,
                reason=(
                    f"保证金充足 ({margin_ratio:.2%})"
                    if margin_ok
                    else f"保证金不足 ({margin_ratio:.2%})"
                ),
            )
        )

        # 条件4: 无该品种持仓
        position = context.get_position(symbol)
        no_position = position is None or position.quantity == 0

        conditions.append(
            OpenCondition(
                name="no_existing_position",
                description=f"无 {symbol} 持仓",
                is_met=no_position,
                confidence=1.0 if no_position else 0.0,
                reason="无持仓" if no_position else f"已有持仓 {position.quantity if position else 0}",
            )
        )

        self.logger.info(
            f"Open conditions check for {symbol}: "
            f"{sum(1 for c in conditions if c.is_met)}/{len(conditions)} met"
        )

        return conditions

    async def check_close_conditions(
        self,
        symbol: str,
        context: Context,
    ) -> List[CloseCondition]:
        """
        检查平仓条件

        Args:
            symbol: 交易品种
            context: 上下文

        Returns:
            List[CloseCondition]: 平仓条件列表
        """
        conditions = []

        # 获取配置
        close_config = self.config.get("close_conditions", {})
        funding_rate_threshold = close_config.get("funding_rate_threshold", -0.00005)
        min_profit = close_config.get("min_profit", 0.005)
        max_loss = close_config.get("max_loss", 0.02)

        # 获取市场数据
        market_data = context.get_market_data(symbol)
        if not market_data:
            return conditions

        # 获取持仓
        position = context.get_position(symbol)
        if not position or position.quantity == 0:
            return conditions

        # 计算盈亏比例
        pnl_ratio = position.unrealized_pnl / (position.quantity * position.entry_price)

        # 条件1: 资金费率转负
        funding_rate = market_data.funding_rate
        funding_rate_negative = funding_rate < funding_rate_threshold

        conditions.append(
            CloseCondition(
                name="funding_rate_negative",
                description=f"资金费率 {funding_rate:.4%} < {funding_rate_threshold:.4%}",
                is_met=funding_rate_negative,
                urgency=5,
                reason=f"资金费率转负 ({funding_rate:.4%})",
            )
        )

        # 条件2: 达到止盈
        profit_target_met = pnl_ratio >= min_profit

        conditions.append(
            CloseCondition(
                name="profit_target",
                description=f"盈利 {pnl_ratio:.2%} >= {min_profit:.2%}",
                is_met=profit_target_met,
                urgency=3,
                reason=f"达到止盈目标 ({pnl_ratio:.2%})",
            )
        )

        # 条件3: 触发止损
        loss_limit_met = pnl_ratio <= -max_loss

        conditions.append(
            CloseCondition(
                name="loss_limit",
                description=f"亏损 {abs(pnl_ratio):.2%} >= {max_loss:.2%}",
                is_met=loss_limit_met,
                urgency=10,  # 最高紧急程度
                reason=f"触发止损 ({pnl_ratio:.2%})",
            )
        )

        # 条件4: 系统紧急状态
        emergency = context.is_emergency

        conditions.append(
            CloseCondition(
                name="emergency",
                description="系统紧急状态",
                is_met=emergency,
                urgency=10,  # 最高紧急程度
                reason="系统紧急状态，立即平仓",
            )
        )

        self.logger.info(
            f"Close conditions check for {symbol}: "
            f"{sum(1 for c in conditions if c.is_met)}/{len(conditions)} met"
        )

        return conditions

    def should_open(self, conditions: List[OpenCondition]) -> bool:
        """
        判断是否应该开仓

        Args:
            conditions: 开仓条件列表

        Returns:
            bool: 是否应该开仓
        """
        # 所有条件都必须满足
        return all(c.is_met for c in conditions)

    def should_close(self, conditions: List[CloseCondition]) -> bool:
        """
        判断是否应该平仓

        Args:
            conditions: 平仓条件列表

        Returns:
            bool: 是否应该平仓
        """
        # 任一条件满足即可平仓
        return any(c.is_met for c in conditions)

    def get_close_urgency(self, conditions: List[CloseCondition]) -> int:
        """
        获取平仓紧急程度

        Args:
            conditions: 平仓条件列表

        Returns:
            int: 紧急程度 0-10
        """
        if not conditions:
            return 0

        # 返回最高紧急程度
        return max(c.urgency for c in conditions if c.is_met)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "config": self.config,
        }
