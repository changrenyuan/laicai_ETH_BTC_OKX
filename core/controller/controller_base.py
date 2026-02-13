"""
🧠 ControllerBase - 策略大脑基类
===========================================
负责逻辑计算、信号生成和执行器调度

借鉴 Hummingbot Strategy V2 的架构：
- Controller 不直接下单，只负责计算逻辑并生成配置
- 交给 Executor 去执行实际的订单操作

核心职责：
1. 订阅市场事件（Ticker、OrderBook、Trade等）
2. 分析市场数据，生成交易信号
3. 根据信号生成 ExecutorConfig
4. 调度 Executor Orchestrator 执行
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime

from core.events import Event, EventType
from core.executor.executor_base import ExecutorConfig, ExecutorType
from core.executor.orchestrator import ExecutorOrchestrator


class ControllerBase(ABC):
    """
    策略控制器基类
    
    所有策略都必须继承此类，实现核心逻辑：
    - process_tick: 处理行情更新
    - determine_executor_config: 根据信号生成执行器配置
    """

    def __init__(
        self,
        config: Dict,
        exchanges: Dict[str, Any],
        executor_orchestrator: Optional[ExecutorOrchestrator] = None
    ):
        """
        初始化控制器
        
        Args:
            config: 策略配置
            exchanges: 交易所连接器字典 {"okx": okx_exchange}
            executor_orchestrator: 执行器编排器
        """
        self.config = config
        self.exchanges = exchanges
        self.executor_orchestrator = executor_orchestrator
        
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 控制器标识
        self.controller_id = config.get("id", "default_controller")
        self.trading_pairs = config.get("trading_pairs", [])
        
        # 状态管理
        self.is_active = False
        self.is_initialized = False
        self.last_tick_time = None
        
        # 统计信息
        self.stats = {
            "ticks_processed": 0,
            "signals_generated": 0,
            "executors_created": 0,
            "start_time": None,
            "last_update": None
        }
        
        # 事件回调
        self.event_callbacks: Dict[EventType, List] = {
            EventType.TICKER: [],
            EventType.ORDER_BOOK: [],
            EventType.TRADE: [],
            EventType.ORDER_FILLED: [],
            EventType.ORDER_CANCELLED: []
        }

    @property
    @abstractmethod
    def controller_type(self) -> str:
        """控制器类型"""
        pass

    async def initialize(self):
        """
        初始化控制器
        - 订阅市场事件
        - 初始化策略状态
        """
        self.logger.info(f"🧠 初始化 Controller: {self.controller_id} ({self.controller_type})")
        
        # 订阅市场事件
        await self._subscribe_events()
        
        # 初始化策略状态
        await self._initialize_strategy_state()
        
        self.is_initialized = True
        self.stats["start_time"] = datetime.now()
        self.stats["last_update"] = datetime.now()
        
        self.logger.info(f"✅ Controller {self.controller_id} 初始化完成")

    async def start(self):
        """启动控制器"""
        if not self.is_initialized:
            await self.initialize()
        
        self.is_active = True
        self.logger.info(f"🚀 Controller {self.controller_id} 启动")

    async def stop(self):
        """停止控制器"""
        self.is_active = False
        
        # 停止所有执行器
        if self.executor_orchestrator:
            await self.executor_orchestrator.stop_all()
        
        # 取消事件订阅
        await self._unsubscribe_events()
        
        self.logger.info(f"🛑 Controller {self.controller_id} 停止")

    async def _subscribe_events(self):
        """订阅市场事件"""
        for exchange_name, exchange in self.exchanges.items():
            # 订阅 Ticker 事件
            if hasattr(exchange, "event_bus"):
                exchange.event_bus.subscribe(EventType.TICKER, self.process_tick)
                
                # 订阅 OrderBook 事件（可选）
                # exchange.event_bus.subscribe(EventType.ORDER_BOOK, self.process_orderbook)
                
                # 订阅 Trade 事件（可选）
                # exchange.event_bus.subscribe(EventType.TRADE, self.process_trade)
                
                self.logger.info(f"📡 已订阅 {exchange_name} 的市场事件")

    async def _unsubscribe_events(self):
        """取消订阅事件"""
        for exchange_name, exchange in self.exchanges.items():
            if hasattr(exchange, "event_bus"):
                # 取消订阅
                # exchange.event_bus.unsubscribe(EventType.TICKER, self.process_tick)
                pass

    @abstractmethod
    async def _initialize_strategy_state(self):
        """初始化策略状态（由子类实现）"""
        pass

    @abstractmethod
    async def process_tick(self, event: Event):
        """
        处理行情更新（由子类实现具体逻辑）
        
        Args:
            event: Ticker 事件
        """
        pass

    @abstractmethod
    def determine_executor_config(self, signal: Dict) -> Optional[ExecutorConfig]:
        """
        根据信号生成 ExecutorConfig（由子类实现）
        
        Args:
            signal: 交易信号
            
        Returns:
            ExecutorConfig: 执行器配置
        """
        pass

    async def create_executor(self, config: ExecutorConfig) -> Optional[str]:
        """
        创建并启动执行器
        
        Args:
            config: 执行器配置
            
        Returns:
            str: 执行器ID
        """
        if not self.executor_orchestrator:
            self.logger.error("❌ ExecutorOrchestrator 未初始化")
            return None
        
        try:
            # 创建对应的执行器
            executor = self._create_executor_instance(config)
            
            if not executor:
                return None
            
            # 启动执行器
            executor_id = await self.executor_orchestrator.start_executor(executor)
            
            self.stats["executors_created"] += 1
            self.stats["last_update"] = datetime.now()
            
            self.logger.info(f"✅ 创建执行器成功: {executor_id}")
            return executor_id
            
        except Exception as e:
            self.logger.error(f"❌ 创建执行器失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    @abstractmethod
    def _create_executor_instance(self, config: ExecutorConfig):
        """
        创建执行器实例（由子类实现）
        
        Args:
            config: 执行器配置
            
        Returns:
            ExecutorBase: 执行器实例
        """
        pass

    async def _emit_event(self, event_type: EventType, data: Dict):
        """
        发布事件到回调
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        callbacks = self.event_callbacks.get(event_type, [])
        for callback in callbacks:
            try:
                await callback(event_type, data)
            except Exception as e:
                self.logger.error(f"❌ 事件回调失败: {e}")

    def add_event_callback(self, event_type: EventType, callback):
        """
        添加事件回调
        
        Args:
            event_type: 事件类型
            callback: 回调函数
        """
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type].append(callback)

    def remove_event_callback(self, event_type: EventType, callback):
        """
        移除事件回调
        
        Args:
            event_type: 事件类型
            callback: 回调函数
        """
        if event_type in self.event_callbacks and callback in self.event_callbacks[event_type]:
            self.event_callbacks[event_type].remove(callback)

    def get_stats(self) -> Dict:
        """
        获取控制器统计信息
        
        Returns:
            Dict: 统计信息
        """
        return {
            "controller_id": self.controller_id,
            "controller_type": self.controller_type,
            "is_active": self.is_active,
            "is_initialized": self.is_initialized,
            "trading_pairs": self.trading_pairs,
            "ticks_processed": self.stats["ticks_processed"],
            "signals_generated": self.stats["signals_generated"],
            "executors_created": self.stats["executors_created"],
            "start_time": self.stats["start_time"].isoformat() if self.stats["start_time"] else None,
            "last_update": self.stats["last_update"].isoformat() if self.stats["last_update"] else None,
        }

    def __repr__(self) -> str:
        return (f"ControllerBase(id={self.controller_id}, "
                f"type={self.controller_type}, "
                f"active={self.is_active})")


# 导出
__all__ = ["ControllerBase"]
