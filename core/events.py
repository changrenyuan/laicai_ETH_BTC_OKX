"""
🔥 系统事件定义
定义系统中所有可能的事件类型
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


class EventType(Enum):
    """事件类型枚举"""

    # 市场事件
    MARKET_TICK = "market_tick"  # 市场行情更新
    FUNDING_RATE_UPDATE = "funding_rate_update"  # 资金费率更新
    PRICE_ANOMALY = "price_anomaly"  # 价格异常

    # 账户事件
    BALANCE_UPDATE = "balance_update"  # 余额更新
    POSITION_UPDATE = "position_update"  # 持仓更新
    MARGIN_UPDATE = "margin_update"  # 保证金更新

    # 策略事件
    STRATEGY_SIGNAL = "strategy_signal"  # 策略信号
    OPEN_POSITION = "open_position"  # 开仓信号
    CLOSE_POSITION = "close_position"  # 平仓信号
    REBALANCE = "rebalance"  # 再平衡信号

    # 执行事件
    ORDER_SUBMITTED = "order_submitted"  # 订单提交
    ORDER_FILLED = "order_filled"  # 订单成交
    ORDER_CANCELLED = "order_cancelled"  # 订单取消
    ORDER_REJECTED = "order_rejected"  # 订单拒绝

    # 风险事件
    MARGIN_WARNING = "margin_warning"  # 保证金警告
    MARGIN_CRITICAL = "margin_critical"  # 保证金危险
    CIRCUIT_BREAKER = "circuit_breaker"  # 熔断触发
    RISK_LIMIT_EXCEEDED = "risk_limit_exceeded"  # 风险限额超限

    # 系统事件
    SYSTEM_START = "system_start"  # 系统启动
    SYSTEM_STOP = "system_stop"  # 系统停止
    SYSTEM_ERROR = "system_error"  # 系统错误
    HEARTBEAT = "heartbeat"  # 心跳


@dataclass
class Event:
    """基础事件类"""

    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # 优先级，数字越大优先级越高

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "priority": self.priority,
        }


@dataclass
class MarketEvent(Event):
    """市场事件"""

    symbol: str = ""
    price: float = 0.0
    volume: float = 0.0


@dataclass
class FundingRateEvent(Event):
    """资金费率事件"""

    symbol: str = ""
    funding_rate: float = 0.0
    next_funding_time: Optional[datetime] = None


@dataclass
class StrategyEvent(Event):
    """策略事件"""

    symbol: str = ""
    action: str = ""  # open, close, rebalance
    quantity: float = 0.0
    confidence: float = 0.0  # 信心度 0-1


@dataclass
class RiskEvent(Event):
    """风险事件"""

    risk_type: str = ""
    level: str = ""  # warning, critical, emergency
    current_value: float = 0.0
    threshold: float = 0.0
    message: str = ""


@dataclass
class OrderEvent(Event):
    """订单事件"""

    symbol: str = ""
    order_id: str = ""
    side: str = ""  # buy, sell
    quantity: float = 0.0
    price: float = 0.0
    status: str = ""  # submitted, filled, cancelled, rejected


class EventBus:
    """事件总线"""

    def __init__(self):
        self._subscribers: Dict[EventType, list] = {}

    def subscribe(self, event_type: EventType, callback):
        """订阅事件"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: EventType, callback):
        """取消订阅"""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)

    async def publish(self, event: Event):
        """发布事件"""
        if event.event_type in self._subscribers:
            # 按优先级排序
            callbacks = sorted(
                self._subscribers[event.event_type],
                key=lambda cb: getattr(cb, "priority", 0),
                reverse=True,
            )

            for callback in callbacks:
                try:
                    await callback(event)
                except Exception as e:
                    print(f"Event callback error: {e}")
