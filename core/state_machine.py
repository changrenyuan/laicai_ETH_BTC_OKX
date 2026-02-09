"""
⭐⭐ 状态机（系统灵魂）
定义系统的状态转换逻辑
"""

from enum import Enum
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio

from .events import Event, EventType, EventBus


class SystemState(Enum):
    """系统状态枚举"""

    IDLE = "idle"  # 空闲
    INITIALIZING = "initializing"  # 初始化中
    READY = "ready"  # 就绪
    MONITORING = "monitoring"  # 监控中
    OPENING_POSITION = "opening_position"  # 开仓中
    CLOSING_POSITION = "closing_position"  # 平仓中
    REBALANCING = "rebalancing"  # 再平衡中
    ERROR = "error"  # 错误
    EMERGENCY = "emergency"  # 紧急状态
    SHUTDOWN = "shutdown"  # 关闭


class StateTransition(Enum):
    """状态转换枚举"""

    # 启动流程
    IDLE_TO_INITIALIZING = (SystemState.IDLE, SystemState.INITIALIZING)
    INITIALIZING_TO_READY = (SystemState.INITIALIZING, SystemState.READY)
    READY_TO_MONITORING = (SystemState.READY, SystemState.MONITORING)

    # 交易流程
    MONITORING_TO_OPENING = (SystemState.MONITORING, SystemState.OPENING_POSITION)
    OPENING_TO_MONITORING = (
        SystemState.OPENING_POSITION,
        SystemState.MONITORING,
    )
    MONITORING_TO_CLOSING = (SystemState.MONITORING, SystemState.CLOSING_POSITION)
    CLOSING_TO_MONITORING = (
        SystemState.CLOSING_POSITION,
        SystemState.MONITORING,
    )

    # 再平衡流程
    MONITORING_TO_REBALANCING = (SystemState.MONITORING, SystemState.REBALANCING)
    REBALANCING_TO_MONITORING = (
        SystemState.REBALANCING,
        SystemState.MONITORING,
    )

    # 错误处理
    ANY_TO_ERROR = "any_to_error"
    ERROR_TO_MONITORING = (SystemState.ERROR, SystemState.MONITORING)

    # 紧急处理
    ANY_TO_EMERGENCY = "any_to_emergency"
    EMERGENCY_TO_MONITORING = (SystemState.EMERGENCY, SystemState.MONITORING)

    # 关闭流程
    ANY_TO_SHUTDOWN = "any_to_shutdown"


@dataclass
class StateTransitionEvent:
    """状态转换事件"""

    from_state: SystemState
    to_state: SystemState
    timestamp: datetime
    reason: str = ""


class StateMachine:
    """
    状态机类
    管理系统的状态转换和事件处理
    """

    def __init__(self, event_bus: EventBus):
        self.current_state = SystemState.IDLE
        self.previous_state = SystemState.IDLE
        self.event_bus = event_bus
        self.state_transitions: list[StateTransitionEvent] = []

        # 状态回调函数
        self._state_callbacks: Dict[SystemState, list[Callable]] = {}
        # 转换回调函数
        self._transition_callbacks: Dict[
            tuple[SystemState, SystemState], list[Callable]
        ] = {}

    def register_state_callback(self, state: SystemState, callback: Callable):
        """注册状态回调函数"""
        if state not in self._state_callbacks:
            self._state_callbacks[state] = []
        self._state_callbacks[state].append(callback)

    def register_transition_callback(
        self,
        from_state: SystemState,
        to_state: SystemState,
        callback: Callable,
    ):
        """注册状态转换回调函数"""
        key = (from_state, to_state)
        if key not in self._transition_callbacks:
            self._transition_callbacks[key] = []
        self._transition_callbacks[key].append(callback)

    async def transition_to(
        self, new_state: SystemState, reason: str = "", **kwargs
    ):
        """
        转换到新状态
        Args:
            new_state: 目标状态
            reason: 转换原因
            **kwargs: 传递给回调的参数
        """
        from_state = self.current_state
        to_state = new_state

        # 检查转换是否合法
        if not self._is_valid_transition(from_state, to_state):
            raise ValueError(
                f"Invalid state transition: {from_state.value} -> {to_state.value}"
            )

        # 记录转换
        self.previous_state = from_state
        self.current_state = to_state

        transition_event = StateTransitionEvent(
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.now(),
            reason=reason,
        )
        self.state_transitions.append(transition_event)

        # 发布状态转换事件
        await self.event_bus.publish(
            Event(
                event_type=EventType.SYSTEM_START,
                data={
                    "from_state": from_state.value,
                    "to_state": to_state.value,
                    "reason": reason,
                },
            )
        )

        # 调用状态回调
        if to_state in self._state_callbacks:
            for callback in self._state_callbacks[to_state]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(**kwargs)
                    else:
                        callback(**kwargs)
                except Exception as e:
                    print(f"State callback error: {e}")

        # 调用转换回调
        transition_key = (from_state, to_state)
        if transition_key in self._transition_callbacks:
            for callback in self._transition_callbacks[transition_key]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(**kwargs)
                    else:
                        callback(**kwargs)
                except Exception as e:
                    print(f"Transition callback error: {e}")

    def _is_valid_transition(
        self, from_state: SystemState, to_state: SystemState
    ) -> bool:
        """检查状态转换是否合法"""
        # 定义合法的转换
        valid_transitions = {
            SystemState.IDLE: [SystemState.INITIALIZING, SystemState.SHUTDOWN],
            SystemState.INITIALIZING: [SystemState.READY, SystemState.ERROR],
            SystemState.READY: [
                SystemState.MONITORING,
                SystemState.ERROR,
                SystemState.SHUTDOWN,
            ],
            SystemState.MONITORING: [
                SystemState.OPENING_POSITION,
                SystemState.CLOSING_POSITION,
                SystemState.REBALANCING,
                SystemState.ERROR,
                SystemState.EMERGENCY,
                SystemState.SHUTDOWN,
            ],
            SystemState.OPENING_POSITION: [
                SystemState.MONITORING,
                SystemState.ERROR,
                SystemState.EMERGENCY,
                SystemState.SHUTDOWN,
            ],
            SystemState.CLOSING_POSITION: [
                SystemState.MONITORING,
                SystemState.ERROR,
                SystemState.EMERGENCY,
                SystemState.SHUTDOWN,
            ],
            SystemState.REBALANCING: [
                SystemState.MONITORING,
                SystemState.ERROR,
                SystemState.EMERGENCY,
                SystemState.SHUTDOWN,
            ],
            SystemState.ERROR: [SystemState.MONITORING, SystemState.EMERGENCY, SystemState.SHUTDOWN],
            SystemState.EMERGENCY: [
                SystemState.MONITORING,
                SystemState.ERROR,
                SystemState.SHUTDOWN,
            ],
        }

        return to_state in valid_transitions.get(from_state, [])

    def get_current_state(self) -> SystemState:
        """获取当前状态"""
        return self.current_state

    def get_previous_state(self) -> SystemState:
        """获取上一个状态"""
        return self.previous_state

    def is_in_state(self, state: SystemState) -> bool:
        """检查是否处于指定状态"""
        return self.current_state == state

    def is_in_states(self, states: list[SystemState]) -> bool:
        """检查是否处于任一指定状态"""
        return self.current_state in states

    def get_state_history(self, limit: int = 10) -> list[StateTransitionEvent]:
        """获取状态转换历史"""
        return self.state_transitions[-limit:]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "current_state": self.current_state.value,
            "previous_state": self.previous_state.value,
            "transition_count": len(self.state_transitions),
            "recent_transitions": [
                {
                    "from": t.from_state.value,
                    "to": t.to_state.value,
                    "timestamp": t.timestamp.isoformat(),
                    "reason": t.reason,
                }
                for t in self.state_transitions[-5:]
            ],
        }
