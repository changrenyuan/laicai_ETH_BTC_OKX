"""
🧠 策略抽象基类
所有具体策略（网格、套利）都必须继承此类
"""
from abc import ABC, abstractmethod
from core.context import Context
from core.state_machine import StateMachine
from execution.order_manager import OrderManager

class BaseStrategy(ABC):
    def __init__(self, config: dict, context: Context, state_machine: StateMachine, order_manager: OrderManager):
        self.config = config
        self.context = context
        self.state_machine = state_machine
        self.om = order_manager
        self.is_initialized = False

    @abstractmethod
    async def initialize(self):
        """策略初始化（如：计算网格线、预挂单）"""
        pass

    @abstractmethod
    async def run_tick(self):
        """每轮行情更新时的逻辑"""
        pass

    @abstractmethod
    async def shutdown(self):
        """策略停止时的清理工作（如：撤销所有挂单）"""
        pass