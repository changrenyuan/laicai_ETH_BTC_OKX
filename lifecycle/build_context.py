"""
🏗️ Build Context Phase
构建 Context (系统快照)
"""

from core.context import Context
from core.events import EventBus
from core.state_machine import StateMachine
from core.context import Balance
from monitor.dashboard import Dashboard


class BuildContext:
    """BuildContext 生命周期阶段 - 构建Context"""
    
    def run(self) -> dict:  # 修改返回类型为 dict
        Dashboard.log("【4】构建 Context (系统快照)...", "INFO")

        # 1. 创建核心组件
        event_bus = EventBus()
        state_machine = StateMachine(event_bus)
        context = Context()

        # 2. 确保初始化必要的属性
        if not hasattr(context, 'liquidity_depth'):
            context.liquidity_depth = 0.0
        if not hasattr(context, 'last_scan_time'):
            context.last_scan_time = 0.0
        if not hasattr(context, 'market_snapshot'):
            context.market_snapshot = {}
        if not hasattr(context, 'last_trade_time'):
            context.last_trade_time = 0.0
        if not hasattr(context, 'trade_history'):
            context.trade_history = []
        if not hasattr(context, 'balances'):
            context.balances = {}

        # 3. 初始化默认余额（USDT），避免空字典错误
        context.balances["USDT"] = Balance(
            currency="USDT",
            available=0.0,
            frozen=0.0,
            total=0.0
        )

        Dashboard.log("✅ Context 构建完成", "SUCCESS")

        # 返回组件字典，以便 main.py 注册到 self.components
        return {
            "context": context,
            "event_bus": event_bus,
            "state_machine": state_machine
        }