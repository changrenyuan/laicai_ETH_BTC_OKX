"""
🔥 保证金防护
保证金 / 爆仓防护
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import logging

from core.events import Event, EventType, RiskEvent
from core.context import Context


@dataclass
class MarginCheckResult:
    """保证金检查结果"""

    is_warning: bool  # 是否警告
    is_critical: bool  # 是否危险
    is_emergency: bool  # 是否紧急
    margin_ratio: float  # 保证金率
    message: str  # 消息


class MarginGuard:
    """
    保证金防护类
    监控保证金率，防止爆仓
    """

    def __init__(self, config: dict):
        self.config = config
        self.margin_ratio_warning = config.get("margin_ratio_warning", 0.80)
        self.margin_ratio_critical = config.get("margin_ratio_critical", 0.60)
        self.margin_ratio_stop = config.get("margin_ratio_stop", 0.50)
        self.auto_add_margin = config.get("auto_add_margin", True)
        self.auto_reduce_position = config.get("auto_reduce_position", True)

        self.logger = logging.getLogger(__name__)

        # 状态追踪
        self.last_check_time: Optional[datetime] = None
        self.warning_triggered: bool = False
        self.critical_triggered: bool = False
        self.emergency_triggered: bool = False

    async def check(self, context: Context) -> MarginCheckResult:
        """
        检查保证金状况

        Args:
            context: 上下文

        Returns:
            MarginCheckResult: 检查结果
        """
        # 计算保证金率
        margin_ratio = context.calculate_margin_ratio()
        context.margin_ratio = margin_ratio

        # 判断风险等级
        is_warning = margin_ratio <= self.margin_ratio_warning
        is_critical = margin_ratio <= self.margin_ratio_critical
        is_emergency = margin_ratio <= self.margin_ratio_stop

        result = MarginCheckResult(
            is_warning=is_warning,
            is_critical=is_critical,
            is_emergency=is_emergency,
            margin_ratio=margin_ratio,
            message=self._generate_message(margin_ratio, is_warning, is_critical, is_emergency),
        )

        # 记录检查时间
        self.last_check_time = datetime.now()

        # 更新触发状态
        if is_warning:
            self.warning_triggered = True
        if is_critical:
            self.critical_triggered = True
        if is_emergency:
            self.emergency_triggered = True

        self.logger.info(f"Margin check: {margin_ratio:.2%} - {result.message}")

        return result

    async def check_margin_ratio(self, context: Context) -> float:
        """
        简化版保证金检查，直接返回保证金率
        主循环中快速调用此方法
        """
        # 计算保证金率
        margin_ratio = context.calculate_margin_ratio()
        context.margin_ratio = margin_ratio

        # 记录检查时间
        self.last_check_time = datetime.now()

        return margin_ratio

    def _generate_message(
        self,
        margin_ratio: float,
        is_warning: bool,
        is_critical: bool,
        is_emergency: bool,
    ) -> str:
        """生成消息"""
        if is_emergency:
            return f"EMERGENCY: Margin ratio at {margin_ratio:.2%}, immediate action required!"
        elif is_critical:
            return f"CRITICAL: Margin ratio at {margin_ratio:.2%}, action needed"
        elif is_warning:
            return f"WARNING: Margin ratio at {margin_ratio:.2%}, monitor closely"
        else:
            return f"OK: Margin ratio at {margin_ratio:.2%}"

    async def handle_warning(self, context: Context):
        """处理警告"""
        self.logger.warning(f"Margin warning triggered: {context.margin_ratio:.2%}")
        # 可以发送通知或采取轻微措施

    async def handle_critical(self, context: Context):
        """处理危险情况"""
        self.logger.critical(f"Margin critical: {context.margin_ratio:.2%}")

        if self.auto_add_margin:
            # 触发资金再平衡
            self.logger.info("Auto adding margin triggered")

    async def handle_emergency(self, context: Context):
        """处理紧急情况"""
        self.logger.error(f"Margin emergency: {context.margin_ratio:.2%}")

        # 设置紧急状态
        context.is_emergency = True

        if self.auto_reduce_position:
            # 触发减仓或平仓
            self.logger.info("Auto position reduction triggered")

    def reset(self):
        """重置状态"""
        self.warning_triggered = False
        self.critical_triggered = False
        self.emergency_triggered = False
        self.logger.info("Margin guard state reset")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "margin_ratio_warning": self.margin_ratio_warning,
            "margin_ratio_critical": self.margin_ratio_critical,
            "margin_ratio_stop": self.margin_ratio_stop,
            "auto_add_margin": self.auto_add_margin,
            "auto_reduce_position": self.auto_reduce_position,
            "last_check_time": (
                self.last_check_time.isoformat() if self.last_check_time else None
            ),
            "warning_triggered": self.warning_triggered,
            "critical_triggered": self.critical_triggered,
            "emergency_triggered": self.emergency_triggered,
        }
