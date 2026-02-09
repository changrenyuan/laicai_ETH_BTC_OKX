"""
🔥 熔断器
连续止损 / 日熔断
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List
import logging

from core.events import EventType, RiskEvent
from core.context import Context


@dataclass
class LossRecord:
    """亏损记录"""

    timestamp: datetime
    amount: float
    reason: str


@dataclass
class CircuitBreakerState:
    """熔断器状态"""

    is_triggered: bool = False
    trigger_time: Optional[datetime] = None
    reason: str = ""
    cooldown_end_time: Optional[datetime] = None


class CircuitBreaker:
    """
    熔断器类
    监控连续亏损和日亏损，触发熔断
    """

    def __init__(self, config: dict):
        self.config = config
        self.max_consecutive_losses = config.get("max_consecutive_losses", 3)
        self.consecutive_loss_threshold = config.get("consecutive_loss_threshold", 100)
        self.daily_loss_limit = config.get("daily_loss_limit", 500)
        self.daily_profit_limit = config.get("daily_profit_limit", 2000)
        self.cooldown_period = config.get("cooldown_period", 3600)

        self.logger = logging.getLogger(__name__)

        # 状态
        self.state = CircuitBreakerState()
        self.loss_records: List[LossRecord] = []
        self.profit_records: List[LossRecord] = []

    async def check_loss(self, context: Context, amount: float, reason: str = "") -> bool:
        """
        检查亏损，判断是否需要触发熔断

        Args:
            context: 上下文
            amount: 亏损金额
            reason: 原因

        Returns:
            bool: 是否触发熔断
        """
        if amount <= 0:
            return False

        # 记录亏损
        record = LossRecord(
            timestamp=datetime.now(),
            amount=amount,
            reason=reason,
        )
        self.loss_records.append(record)

        # 检查连续亏损
        consecutive_losses = self._count_consecutive_losses()
        if consecutive_losses >= self.max_consecutive_losses:
            await self._trigger(
                context,
                f"Consecutive losses: {consecutive_losses} >= {self.max_consecutive_losses}",
            )
            return True

        # 检查日亏损限额
        daily_loss = self._get_daily_loss()
        if daily_loss >= self.daily_loss_limit:
            await self._trigger(
                context,
                f"Daily loss limit: ${daily_loss:.2f} >= ${self.daily_loss_limit:.2f}",
            )
            return True

        return False

    async def check_profit(self, context: Context, amount: float) -> bool:
        """
        检查盈利，防止过度贪婪

        Args:
            context: 上下文
            amount: 盈利金额

        Returns:
            bool: 是否触发熔断（止盈）
        """
        if amount <= 0:
            return False

        # 记录盈利
        record = LossRecord(
            timestamp=datetime.now(),
            amount=amount,
            reason="profit",
        )
        self.profit_records.append(record)

        # 检查日盈利限额
        daily_profit = self._get_daily_profit()
        if daily_profit >= self.daily_profit_limit:
            await self._trigger(
                context,
                f"Daily profit limit reached: ${daily_profit:.2f} >= ${self.daily_profit_limit:.2f}",
            )
            return True

        return False

    async def _trigger(self, context: Context, reason: str):
        """触发熔断"""
        self.state.is_triggered = True
        self.state.trigger_time = datetime.now()
        self.state.reason = reason
        self.state.cooldown_end_time = datetime.now() + timedelta(seconds=self.cooldown_period)

        context.is_emergency = True

        self.logger.warning(f"Circuit breaker triggered: {reason}")

        # TODO: 发送通知
        # TODO: 平仓或停止交易

    async def check_cooldown(self, context: Context) -> bool:
        """
        检查是否在冷却期

        Args:
            context: 上下文

        Returns:
            bool: 是否在冷却期
        """
        if not self.state.is_triggered:
            return False

        if self.state.cooldown_end_time and datetime.now() >= self.state.cooldown_end_time:
            # 冷却期结束，重置状态
            await self._reset(context)
            return False

        return True

    async def _reset(self, context: Context):
        """重置熔断器"""
        self.state.is_triggered = False
        self.state.trigger_time = None
        self.state.reason = ""
        self.state.cooldown_end_time = None

        context.is_emergency = False

        self.logger.info("Circuit breaker reset")

    def _count_consecutive_losses(self) -> int:
        """计算连续亏损次数"""
        if not self.loss_records:
            return 0

        count = 0
        now = datetime.now()

        # 从最近的记录开始向前检查
        for record in reversed(self.loss_records):
            # 检查是否在短时间内
            if (now - record.timestamp).total_seconds() > 3600:  # 1小时内
                break

            # 检查是否超过阈值
            if record.amount >= self.consecutive_loss_threshold:
                count += 1
            else:
                break

        return count

    def _get_daily_loss(self) -> float:
        """获取今日亏损总额"""
        today = datetime.now().date()
        daily_total = sum(
            r.amount
            for r in self.loss_records
            if r.timestamp.date() == today
        )
        return daily_total

    def _get_daily_profit(self) -> float:
        """获取今日盈利总额"""
        today = datetime.now().date()
        daily_total = sum(
            r.amount
            for r in self.profit_records
            if r.timestamp.date() == today
        )
        return daily_total

    def get_loss_history(self, days: int = 7) -> List[LossRecord]:
        """获取亏损历史"""
        cutoff_date = datetime.now() - timedelta(days=days)
        return [
            r
            for r in self.loss_records
            if r.timestamp >= cutoff_date
        ]

    def reset(self):
        """手动重置"""
        self.state = CircuitBreakerState()
        self.loss_records.clear()
        self.profit_records.clear()
        self.logger.info("Circuit breaker manually reset")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "is_triggered": self.state.is_triggered,
            "trigger_time": (
                self.state.trigger_time.isoformat() if self.state.trigger_time else None
            ),
            "reason": self.state.reason,
            "cooldown_end_time": (
                self.state.cooldown_end_time.isoformat()
                if self.state.cooldown_end_time
                else None
            ),
            "max_consecutive_losses": self.max_consecutive_losses,
            "daily_loss_limit": self.daily_loss_limit,
            "daily_profit_limit": self.daily_profit_limit,
            "current_daily_loss": self._get_daily_loss(),
            "current_daily_profit": self._get_daily_profit(),
            "consecutive_losses": self._count_consecutive_losses(),
        }
