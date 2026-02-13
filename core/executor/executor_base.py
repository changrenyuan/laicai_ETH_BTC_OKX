"""
🎯 Executor - 执行器基类
管理交易执行的核心组件
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List, Callable

from core.risk.triple_barrier import TripleBarrier
from core.events.event_base import Event, EventType


class ExecutorStatus(Enum):
    """执行器状态"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutorType(Enum):
    """执行器类型"""
    ORDER = "order"              # 单订单执行
    POSITION = "position"        # 持仓执行
    DCA = "dca"                  # 定投
    TWAP = "twap"                # 时间加权平均
    GRID = "grid"                # 网格


class ExecutorConfig:
    """执行器配置"""

    def __init__(
        self,
        exchange,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "limit",
        time_limit: Optional[int] = None,
        stop_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_config: Optional[Dict] = None
    ):
        self.exchange = exchange
        self.symbol = symbol
        self.side = side  # "buy" or "sell"
        self.size = size
        self.price = price
        self.order_type = order_type  # "limit", "market", "post_only", "ioc", "fok"
        self.time_limit = time_limit
        self.stop_price = stop_price
        self.take_profit_price = take_profit_price
        self.trailing_stop_config = trailing_stop_config


class ExecutorBase(ABC):
    """
    执行器基类
    
    所有执行器都必须继承此类，实现统一的执行接口
    """

    def __init__(self, config: ExecutorConfig, callback: Optional[Callable] = None):
        self.config = config
        self.callback = callback
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 状态
        self.status = ExecutorStatus.IDLE
        self.executor_id = self._generate_id()
        
        # 订单管理
        self.order_ids: List[str] = []
        self.filled_size: float = 0.0
        self.avg_fill_price: float = 0.0
        self.commission: float = 0.0
        
        # 风控
        self.triple_barrier = TripleBarrier(
            take_profit_price=config.take_profit_price,
            stop_loss_price=config.stop_price,
            time_limit_seconds=config.time_limit
        )
        
        # 追踪价格
        self.current_price: Optional[float] = None
        self.highest_price: float = 0.0
        self.lowest_price: float = float('inf')
        
        # 事件监听
        self._event_listeners: List[Callable] = []

    @property
    @abstractmethod
    def executor_type(self) -> ExecutorType:
        """执行器类型"""
        pass

    def _generate_id(self) -> str:
        """生成执行器 ID"""
        return f"{self.executor_type.value}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(self)} & 0xFFFFFF}"

    async def start(self):
        """启动执行器"""
        if self.status == ExecutorStatus.RUNNING:
            self.logger.warning(f"⚠️ 执行器 {self.executor_id} 已在运行")
            return
        
        self.status = ExecutorStatus.RUNNING
        self.logger.info(f"🚀 执行器启动: {self.executor_id} ({self.executor_type.value})")
        
        # 发送启动事件
        await self._emit_event(Event(
            type=EventType.EXECUTOR_START,
            data={
                "executor_id": self.executor_id,
                "symbol": self.config.symbol,
                "side": self.config.side,
                "size": self.config.size
            }
        ))
        
        # 启动风控监控
        asyncio.create_task(self._monitor_risk())
        
        # 执行策略
        try:
            await self.execute()
        except Exception as e:
            self.logger.error(f"❌ 执行器执行失败: {e}")
            self.status = ExecutorStatus.FAILED
            await self._emit_event(Event(
                type=EventType.EXECUTOR_FAILED,
                data={
                    "executor_id": self.executor_id,
                    "error": str(e)
                }
            ))

    @abstractmethod
    async def execute(self):
        """执行策略（子类实现）"""
        pass

    async def stop(self, reason: str = "user_cancelled"):
        """停止执行器"""
        if self.status == ExecutorStatus.RUNNING:
            # 取消所有订单
            await self._cancel_all_orders()
            
            self.status = ExecutorStatus.CANCELLED
            self.logger.info(f"🛑 执行器停止: {self.executor_id} (原因: {reason})")
            
            await self._emit_event(Event(
                type=EventType.EXECUTOR_CANCELLED,
                data={
                    "executor_id": self.executor_id,
                    "reason": reason
                }
            ))

    async def _monitor_risk(self):
        """风控监控"""
        while self.status == ExecutorStatus.RUNNING:
            try:
                # 获取当前价格
                self.current_price = await self._get_current_price()
                
                if not self.current_price:
                    await asyncio.sleep(1)
                    continue
                
                # 更新最高/最低价
                if self.current_price > self.highest_price:
                    self.highest_price = self.current_price
                if self.current_price < self.lowest_price:
                    self.lowest_price = self.current_price
                
                # 检查 Triple Barrier
                action = self.triple_barrier.check(
                    self.current_price,
                    datetime.now()
                )
                
                if action == "stop_loss":
                    self.logger.warning(f"⛔ 触发止损: {self.current_price}")
                    await self.stop("stop_loss")
                    break
                elif action == "take_profit":
                    self.logger.info(f"✅ 触发止盈: {self.current_price}")
                    await self._mark_completed("take_profit")
                    break
                elif action == "time_limit":
                    self.logger.warning(f"⏰ 触发时间限制")
                    await self.stop("time_limit")
                    break
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"❌ 风控监控错误: {e}")
                await asyncio.sleep(1)

    async def _mark_completed(self, reason: str = "completed"):
        """标记为完成"""
        self.status = ExecutorStatus.COMPLETED
        self.logger.info(f"✅ 执行器完成: {self.executor_id} (原因: {reason})")
        
        # 发送完成事件
        await self._emit_event(Event(
            type=EventType.EXECUTOR_COMPLETED,
            data={
                "executor_id": self.executor_id,
                "reason": reason,
                "filled_size": self.filled_size,
                "avg_fill_price": self.avg_fill_price,
                "commission": self.commission
            }
        ))
        
        # 回调
        if self.callback:
            await self.callback(self)

    async def _get_current_price(self) -> Optional[float]:
        """获取当前价格"""
        try:
            ticker = await self.config.exchange.get_ticker(self.config.symbol)
            return float(ticker.get("last_price", 0))
        except Exception as e:
            self.logger.error(f"❌ 获取价格失败: {e}")
            return None

    async def _cancel_all_orders(self):
        """取消所有订单"""
        for order_id in self.order_ids:
            try:
                success, _, _ = await self.config.exchange.cancel_order(
                    order_id,
                    self.config.symbol
                )
                if success:
                    self.logger.info(f"🗑️ 取消订单: {order_id}")
            except Exception as e:
                self.logger.error(f"❌ 取消订单失败 {order_id}: {e}")

    # ========== 事件系统 ==========

    def add_event_listener(self, listener: Callable):
        """添加事件监听器"""
        self._event_listeners.append(listener)

    async def _emit_event(self, event: Event):
        """发送事件"""
        for listener in self._event_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                self.logger.error(f"❌ 事件监听器错误: {e}")

    # ========== 状态查询 ==========

    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "executor_id": self.executor_id,
            "type": self.executor_type.value,
            "status": self.status.value,
            "symbol": self.config.symbol,
            "side": self.config.side,
            "target_size": self.config.size,
            "filled_size": self.filled_size,
            "avg_fill_price": self.avg_fill_price,
            "current_price": self.current_price,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price,
            "commission": self.commission,
            "triple_barrier": self.triple_barrier.get_status()
        }
