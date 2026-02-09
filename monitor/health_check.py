"""
👀 系统健康检查
监控系统状态和健康状况
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import logging

from core.context import Context
from core.events import EventType, Event


class HealthChecker:
    """
    健康检查器
    监控系统和各组件的健康状态
    """

    def __init__(self, config: dict, event_bus=None):
        self.config = config
        self.event_bus = event_bus

        self.logger = logging.getLogger(__name__)

        # 健康状态
        self.component_health: Dict[str, bool] = {}
        self.last_check_time: Optional[datetime] = None
        self.check_history: List[Dict] = []

    async def check_all(self, context: Context) -> Dict[str, bool]:
        """
        检查所有组件的健康状态

        Args:
            context: 上下文

        Returns:
            Dict[str, bool]: {component: is_healthy}
        """
        self.last_check_time = datetime.now()

        health_status = {}

        # 1. 检查系统运行状态
        health_status["system"] = self._check_system(context)

        # 2. 检查账户状态
        health_status["account"] = await self._check_account(context)

        # 3. 检查市场数据
        health_status["market"] = await self._check_market(context)

        # 4. 检查风险状态
        health_status["risk"] = self._check_risk(context)

        # 5. 检查持仓状态
        health_status["position"] = self._check_position(context)

        # 更新健康状态
        self.component_health = health_status

        # 记录历史
        self.check_history.append({
            "timestamp": self.last_check_time.isoformat(),
            "health": health_status,
            "overall": all(health_status.values()),
        })

        if len(self.check_history) > 100:
            self.check_history.pop(0)

        # 发布健康检查事件
        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    event_type=EventType.HEARTBEAT,
                    data={
                        "health": health_status,
                        "overall": all(health_status.values()),
                    },
                )
            )

        self.logger.info(
            f"Health check: "
            f"system={health_status['system']}, "
            f"account={health_status['account']}, "
            f"market={health_status['market']}, "
            f"risk={health_status['risk']}, "
            f"position={health_status['position']}"
        )

        return health_status

    def _check_system(self, context: Context) -> bool:
        """检查系统状态"""
        # 系统必须正在运行且未处于紧急状态
        return context.is_running and not context.is_emergency

    async def _check_account(self, context: Context) -> bool:
        """检查账户状态"""
        # 必须有余额
        total_balance = context.get_total_balance("USDT")
        if total_balance <= 0:
            return False

        # 保证金率必须合理
        margin_ratio = context.calculate_margin_ratio()
        if margin_ratio < 0.5:  # 低于50%认为不健康
            return False

        return True

    async def _check_market(self, context: Context) -> bool:
        """检查市场数据"""
        # 必须有市场数据
        if not context.market_data:
            return False

        # 所有品种都必须有有效的市场数据
        for symbol, data in context.market_data.items():
            if data.spot_price <= 0 or data.futures_price <= 0:
                return False

            # 资金费率必须在合理范围内
            if abs(data.funding_rate) > 0.01:  # 超过±1%认为异常
                return False

        return True

    def _check_risk(self, context: Context) -> bool:
        """检查风险状态"""
        # 保证金率必须安全
        margin_ratio = context.calculate_margin_ratio()
        if margin_ratio < 0.8:  # 低于80%认为有风险
            return False

        # 不能触发熔断
        if context.is_emergency:
            return False

        return True

    def _check_position(self, context: Context) -> bool:
        """检查持仓状态"""
        # 如果有持仓，必须是对冲的
        for symbol, position in context.positions.items():
            if position.quantity > 0:
                # 检查对冲是否正常
                # TODO: 实现对冲检查逻辑

                # 检查盈亏是否在合理范围内
                if abs(position.unrealized_pnl) > 1000:  # 单品种盈亏超过$1000认为异常
                    return False

        return True

    def is_healthy(self) -> bool:
        """检查整体是否健康"""
        if not self.component_health:
            return True  # 尚未检查，默认健康

        return all(self.component_health.values())

    def get_unhealthy_components(self) -> List[str]:
        """获取不健康的组件"""
        return [
            component
            for component, is_healthy in self.component_health.items()
            if not is_healthy
        ]

    def get_health_summary(self) -> Dict:
        """获取健康摘要"""
        return {
            "is_healthy": self.is_healthy(),
            "component_health": self.component_health,
            "unhealthy_components": self.get_unhealthy_components(),
            "last_check_time": (
                self.last_check_time.isoformat() if self.last_check_time else None
            ),
            "check_count": len(self.check_history),
        }

    def get_recent_history(self, limit: int = 10) -> List[Dict]:
        """获取最近的检查历史"""
        return self.check_history[-limit:]

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "health_summary": self.get_health_summary(),
            "recent_history": self.get_recent_history(5),
        }
