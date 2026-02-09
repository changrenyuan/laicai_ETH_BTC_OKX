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

        # 状态追踪
        self.state = CircuitBreakerState()
        self.loss_records: List[LossRecord] = []
        self.profit_records: List[LossRecord] = []
        self.consecutive_loss_count = 0

    async def check_loss(self, context: Context, amount: float, reason: str) -> bool:
        """
        检查亏损 (保留原有逻辑)
        返回: 是否应该停止交易
        """
        # 记录亏损
        self.loss_records.append(
            LossRecord(
                timestamp=datetime.now(),
                amount=amount,
                reason=reason,
            )
        )

        # 更新连续亏损
        if amount > self.consecutive_loss_threshold:
            self.consecutive_loss_count += 1
        else:
            self.consecutive_loss_count = 0

        should_stop = False
        stop_reason = ""

        # 检查连续亏损
        if self.consecutive_loss_count >= self.max_consecutive_losses:
            should_stop = True
            stop_reason = f"Max consecutive losses reached: {self.consecutive_loss_count}"

        # 检查日亏损
        daily_loss = self.get_daily_loss()
        if daily_loss >= self.daily_loss_limit:
            should_stop = True
            stop_reason = f"Daily loss limit reached: {daily_loss:.2f}"

        if should_stop:
            self._trigger_break(stop_reason)

        return should_stop

    def _trigger_break(self, reason: str):
        """触发熔断"""
        self.state.is_triggered = True
        self.state.trigger_time = datetime.now()
        self.state.reason = reason
        self.state.cooldown_end_time = datetime.now() + timedelta(
            seconds=self.cooldown_period
        )
        self.logger.warning(f"Circuit breaker triggered: {reason}")

    def get_daily_loss(self) -> float:
        """获取今日亏损"""
        today = datetime.now().date()
        daily_total = sum(
            r.amount for r in self.loss_records if r.timestamp.date() == today
        )
        return daily_total

    def get_daily_profit(self) -> float:
        """获取今日盈利"""
        today = datetime.now().date()
        daily_total = sum(
            r.amount for r in self.profit_records if r.timestamp.date() == today
        )
        return daily_total

    def get_loss_history(self, days: int = 7) -> List[LossRecord]:
        """获取亏损历史"""
        cutoff_date = datetime.now() - timedelta(days=days)
        return [r for r in self.loss_records if r.timestamp >= cutoff_date]

    def reset(self):
        """手动重置"""
        self.state = CircuitBreakerState()
        self.consecutive_loss_count = 0
        # 注意：这里不清空历史记录，只重置状态，以便保留审计轨迹
        self.logger.info("Circuit breaker state reset (Cool-down finished or Manual)")

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
        }

    # ==========================================
    # 🔥 新增/补全的方法 (兼容 main_auto.py)
    # ==========================================

    def is_triggered(self) -> bool:
        """
        [兼容接口] 检查是否处于熔断状态
        包含自动冷却逻辑
        """
        # 1. 如果当前没熔断，直接返回 False
        if not self.state.is_triggered:
            return False

        # 2. 如果已经熔断，检查是否过了冷却期
        if (
            self.state.cooldown_end_time
            and datetime.now() > self.state.cooldown_end_time
        ):
            self.reset()  # 冷却结束，自动复位
            self.logger.info("✅ 熔断器冷却结束，系统自动恢复")
            return False

        return True

    def record_loss(self, amount: float, reason: str):
        """
        [兼容接口] 记录亏损 (简化版 check_loss)
        """
        # 复用已有的 check_loss 逻辑的一部分
        self.loss_records.append(
            LossRecord(
                timestamp=datetime.now(),
                amount=amount,
                reason=reason,
            )
        )

        if amount > self.consecutive_loss_threshold:
            self.consecutive_loss_count += 1
        else:
            self.consecutive_loss_count = 0

        # 触发检查
        if self.consecutive_loss_count >= self.max_consecutive_losses:
            self._trigger_break(f"Max consecutive losses: {self.consecutive_loss_count}")
            return

        daily_loss = self.get_daily_loss()
        if daily_loss >= self.daily_loss_limit:
            self._trigger_break(f"Daily loss limit: {daily_loss:.2f}")