"""
🔥 系统事件定义
定义系统中所有可能的事件类型、事件数据结构以及事件总线
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable


class EventType(Enum):
    """
    事件类型枚举
    统一使用字符串值，避免 auto() 在混合模式下的增量错误
    """

    # ========== 市场事件 ==========
    MARKET_TICK = "market_tick"           # 市场行情更新 (通用)
    TICKER = "ticker"                     # 最新成交价更新
    ORDER_BOOK = "order_book"             # 订单簿更新
    TRADE = "trade"                       # 逐笔成交更新
    FUNDING_RATE_UPDATE = "funding_rate_update"  # 资金费率更新
    PRICE_ANOMALY = "price_anomaly"       # 价格异常监控

    # ========== 账户事件 ==========
    BALANCE_UPDATE = "balance_update"     # 余额更新
    POSITION_UPDATE = "position_update"   # 持仓更新
    MARGIN_UPDATE = "margin_update"       # 保证金更新

    # ========== 策略事件 ==========
    STRATEGY_SIGNAL = "strategy_signal"   # 策略信号产生
    OPEN_POSITION = "open_position"       # 开仓信号
    CLOSE_POSITION = "close_position"     # 平仓信号
    REBALANCE = "rebalance"               # 再平衡信号

    # ========== 订单事件 ==========
    ORDER_SUBMITTED = "order_submitted"   # 订单已提交
    ORDER_CREATED = "order_created"       # 订单已创建 (交易所确认)
    ORDER_FILLED = "order_filled"         # 订单成交
    ORDER_CANCELLED = "order_cancelled"   # 订单取消
    ORDER_REJECTED = "order_rejected"     # 订单拒绝
    ORDER_FAILED = "order_failed"         # 订单失败

    # ========== 执行器事件 (Executor) ==========
    EXECUTOR_START = "executor_start"           # 执行器启动
    EXECUTOR_COMPLETED = "executor_completed"   # 执行器正常完成 (如达到止盈)
    EXECUTOR_CANCELLED = "executor_cancelled"   # 执行器被取消 (如用户手动或时间限制)
    EXECUTOR_FAILED = "executor_failed"         # 执行器异常失败

    # ========== 风险事件 ==========
    RISK_TRIGGERED = "risk_triggered"     # 风控触发 (通用)
    MARGIN_WARNING = "margin_warning"     # 保证金警告
    MARGIN_CRITICAL = "margin_critical"   # 保证金危险
    CIRCUIT_BREAKER = "circuit_breaker"   # 熔断触发
    RISK_LIMIT_EXCEEDED = "risk_limit_exceeded" # 风险限额超限

    # ========== 系统事件 ==========
    SYSTEM_START = "system_start"         # 系统启动
    SYSTEM_STOP = "system_stop"           # 系统停止
    SYSTEM_ERROR = "system_error"         # 系统错误
    HEARTBEAT = "heartbeat"               # 心跳检测


@dataclass
class Event:
    """基础事件类"""
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # 优先级，数字越大优先级越高

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，方便 UI 或日志展示"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "priority": self.priority,
        }


@dataclass
class MarketEvent(Event):
    """市场事件专有结构"""
    symbol: str = ""
    price: float = 0.0
    volume: float = 0.0


@dataclass
class FundingRateEvent(Event):
    """资金费率事件专有结构"""
    symbol: str = ""
    funding_rate: float = 0.0
    next_funding_time: Optional[datetime] = None


@dataclass
class StrategyEvent(Event):
    """策略事件专有结构"""
    symbol: str = ""
    action: str = ""  # open, close, rebalance
    quantity: float = 0.0
    confidence: float = 0.0  # 信心度 0-1


@dataclass
class RiskEvent(Event):
    """风险事件专有结构"""
    risk_type: str = ""
    level: str = ""  # warning, critical, emergency
    current_value: float = 0.0
    threshold: float = 0.0
    message: str = ""


@dataclass
class OrderEvent(Event):
    """订单事件专有结构"""
    symbol: str = ""
    order_id: str = ""
    side: str = ""  # buy, sell
    quantity: float = 0.0
    price: float = 0.0
    status: str = ""  # submitted, filled, cancelled, rejected


class EventBus:
    """
    异步事件总线
    负责系统中所有组件的解耦通信
    """

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}

    def subscribe(self, event_type: EventType, callback: Callable):
        """订阅事件"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable):
        """取消订阅"""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
            except ValueError:
                pass

    async def publish(self, event: Event):
        """
        发布事件
        支持按优先级异步调用所有订阅者
        """
        if event.event_type in self._subscribers:
            # 根据订阅者对象的 priority 属性排序（如果存在）
            callbacks = sorted(
                self._subscribers[event.event_type],
                key=lambda cb: getattr(cb, "priority", 0),
                reverse=True,
            )

            for callback in callbacks:
                try:
                    await callback(event)
                except Exception as e:
                    # 生产环境建议接入 logger
                    print(f"🔥 [EventBus] 转发事件 {event.event_type.value} 出错: {e}")