"""
📊 Position Executor - 持仓执行器
管理持仓，支持 DCA、TWAP、Grid 等策略
"""

import asyncio
import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict

from core.executor.executor_base import ExecutorBase, ExecutorType, ExecutorConfig, ExecutorStatus
from core.events.event_base import Event, EventType


class DCAExecutor(ExecutorBase):
    """
    定投执行器 (Dollar Cost Averaging)
    
    分批执行，降低市场冲击
    """

    def __init__(
        self,
        config: ExecutorConfig,
        num_orders: int = 5,
        time_interval: int = 60,
        callback=None
    ):
        super().__init__(config, callback)
        self.num_orders = num_orders  # 订单数量
        self.time_interval = time_interval  # 时间间隔（秒）
        self.batch_size = config.size / num_orders

    @property
    def executor_type(self) -> ExecutorType:
        return ExecutorType.DCA

    async def execute(self):
        """执行 DCA"""
        for i in range(self.num_orders):
            if self.status != ExecutorStatus.RUNNING:
                break
            
            try:
                # 计算批次大小
                remaining_size = self.config.size - self.filled_size
                current_batch_size = min(self.batch_size, remaining_size)
                
                if current_batch_size <= 0:
                    break
                
                # 下单
                success, order_id, error_msg = await self._place_batch_order(
                    current_batch_size
                )
                
                if success:
                    self.order_ids.append(order_id)
                    self.logger.info(
                        f"✅ DCA 下单 {i+1}/{self.num_orders}: "
                        f"{current_batch_size} @ {order_id}"
                    )
                    
                    # 监控订单
                    await self._monitor_order(order_id)
                    
                else:
                    self.logger.error(f"❌ DCA 下单失败 {i+1}: {error_msg}")
                
                # 等待间隔（最后一次不需要等待）
                if i < self.num_orders - 1 and self.status == ExecutorStatus.RUNNING:
                    await asyncio.sleep(self.time_interval)
                    
            except Exception as e:
                self.logger.error(f"❌ DCA 执行错误 {i+1}: {e}")
        
        # 检查是否完成
        if self.filled_size >= self.config.size:
            await self._mark_completed("dca_completed")
        elif self.status == ExecutorStatus.RUNNING:
            await self.stop("dca_partial")

    async def _place_batch_order(self, size: float) -> tuple:
        """下批次订单"""
        order_data = {
            "symbol": self.config.symbol,
            "side": self.config.side,
            "size": size,
            "type": self.config.order_type
        }
        
        if self.config.order_type in ["limit", "post_only"]:
            if self.config.price:
                order_data["price"] = self.config.price
        
        return await self.config.exchange.place_order(order_data)

    async def _monitor_order(self, order_id: str):
        """监控订单"""
        last_filled_size = 0.0  # 记录上次成交数量（避免重复累加）
        
        while self.status == ExecutorStatus.RUNNING:
            try:
                order_info = await self.config.exchange.get_order_status(
                    order_id,
                    self.config.symbol
                )
                
                if not order_info:
                    await asyncio.sleep(0.5)
                    continue
                
                filled_size = float(order_info.get("filled_size", 0))
                avg_price = float(order_info.get("avg_fill_price", 0))
                commission = float(order_info.get("commission", 0))
                
                # 计算增量（避免重复累加）
                filled_increment = filled_size - last_filled_size
                last_filled_size = filled_size
                
                # 只更新增量部分
                if filled_increment > 0:
                    self.filled_size += filled_increment
                    self.commission += commission
                    
                    # 计算加权平均价格
                    if self.filled_size > 0:
                        total_value = self.avg_fill_price * (self.filled_size - filled_size) + avg_price * filled_size
                        self.avg_fill_price = total_value / self.filled_size
                
                status = order_info.get("status")
                if status == "filled":
                    break
                elif status in ["cancelled", "rejected"]:
                    break
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"❌ 监控订单错误: {e}")
                await asyncio.sleep(1)


class TWAPExecutor(ExecutorBase):
    """
    时间加权平均价格执行器 (TWAP)
    
    在指定时间内均匀执行订单
    """

    def __init__(
        self,
        config: ExecutorConfig,
        duration: int = 300,
        num_orders: int = 10,
        callback=None
    ):
        super().__init__(config, callback)
        self.duration = duration  # 总时长（秒）
        self.num_orders = num_orders  # 订单数量
        self.batch_size = config.size / num_orders
        self.time_interval = duration / num_orders

    @property
    def executor_type(self) -> ExecutorType:
        return ExecutorType.TWAP

    async def execute(self):
        """执行 TWAP"""
        start_time = datetime.now()
        
        for i in range(self.num_orders):
            if self.status != ExecutorStatus.RUNNING:
                break
            
            try:
                remaining_size = self.config.size - self.filled_size
                current_batch_size = min(self.batch_size, remaining_size)
                
                if current_batch_size <= 0:
                    break
                
                # 下单
                success, order_id, error_msg = await self._place_batch_order(
                    current_batch_size
                )
                
                if success:
                    self.order_ids.append(order_id)
                    self.logger.info(
                        f"✅ TWAP 下单 {i+1}/{self.num_orders}: "
                        f"{current_batch_size} @ {order_id}"
                    )
                    
                    await self._monitor_order(order_id)
                    
                else:
                    self.logger.error(f"❌ TWAP 下单失败 {i+1}: {error_msg}")
                
                # 计算剩余时间和调整间隔
                elapsed = (datetime.now() - start_time).total_seconds()
                remaining_time = self.duration - elapsed
                orders_remaining = self.num_orders - i - 1
                
                if orders_remaining > 0 and remaining_time > 0:
                    wait_time = remaining_time / orders_remaining
                    await asyncio.sleep(min(wait_time, self.time_interval * 2))
                    
            except Exception as e:
                self.logger.error(f"❌ TWAP 执行错误 {i+1}: {e}")
        
        if self.filled_size >= self.config.size:
            await self._mark_completed("twap_completed")
        elif self.status == ExecutorStatus.RUNNING:
            await self.stop("twap_partial")

    async def _place_batch_order(self, size: float) -> tuple:
        """下批次订单"""
        order_data = {
            "symbol": self.config.symbol,
            "side": self.config.side,
            "size": size,
            "type": self.config.order_type
        }
        
        if self.config.order_type in ["limit", "post_only"]:
            if self.config.price:
                order_data["price"] = self.config.price
        
        return await self.config.exchange.place_order(order_data)

    async def _monitor_order(self, order_id: str):
        """监控订单（复用 DCA 的逻辑）"""
        last_filled_size = 0.0  # 记录上次成交数量（避免重复累加）
        
        while self.status == ExecutorStatus.RUNNING:
            try:
                order_info = await self.config.exchange.get_order_status(
                    order_id,
                    self.config.symbol
                )
                
                if not order_info:
                    await asyncio.sleep(0.5)
                    continue
                
                filled_size = float(order_info.get("filled_size", 0))
                avg_price = float(order_info.get("avg_fill_price", 0))
                commission = float(order_info.get("commission", 0))
                
                # 计算增量（避免重复累加）
                filled_increment = filled_size - last_filled_size
                last_filled_size = filled_size
                
                # 只更新增量部分
                if filled_increment > 0:
                    self.filled_size += filled_increment
                    self.commission += commission
                    
                    # 计算加权平均价格
                    if self.filled_size > 0:
                        total_value = self.avg_fill_price * (self.filled_size - filled_size) + avg_price * filled_size
                        self.avg_fill_price = total_value / self.filled_size
                
                status = order_info.get("status")
                if status == "filled":
                    break
                elif status in ["cancelled", "rejected"]:
                    break
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"❌ 监控订单错误: {e}")
                await asyncio.sleep(1)


class GridExecutor(ExecutorBase):
    """
    网格执行器
    
    在价格区间内均匀挂单
    """

    def __init__(
        self,
        config: ExecutorConfig,
        grid_upper: float,
        grid_lower: float,
        grid_count: int = 10,
        callback=None
    ):
        super().__init__(config, callback)
        self.grid_upper = grid_upper
        self.grid_lower = grid_lower
        self.grid_count = grid_count
        self.grid_step = (grid_upper - grid_lower) / grid_count
        self.batch_size = config.size / grid_count

    @property
    def executor_type(self) -> ExecutorType:
        return ExecutorType.GRID

    async def execute(self):
        """执行网格"""
        for i in range(self.grid_count):
            if self.status != ExecutorStatus.RUNNING:
                break
            
            try:
                # 计算网格价格
                if self.config.side == "buy":
                    grid_price = self.grid_lower + i * self.grid_step
                else:
                    grid_price = self.grid_upper - i * self.grid_step
                
                # 下单
                order_data = {
                    "symbol": self.config.symbol,
                    "side": self.config.side,
                    "size": self.batch_size,
                    "type": "limit",
                    "price": grid_price
                }
                
                success, order_id, error_msg = await self.config.exchange.place_order(order_data)
                
                if success:
                    self.order_ids.append(order_id)
                    self.logger.info(
                        f"✅ 网格下单 {i+1}/{self.grid_count}: "
                        f"{self.batch_size} @ {grid_price}"
                    )
                    
                    await self._monitor_order(order_id)
                    
                else:
                    self.logger.error(f"❌ 网格下单失败 {i+1}: {error_msg}")
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"❌ 网格执行错误 {i+1}: {e}")
        
        if self.filled_size >= self.config.size:
            await self._mark_completed("grid_completed")
        elif self.status == ExecutorStatus.RUNNING:
            await self.stop("grid_partial")

    async def _monitor_order(self, order_id: str):
        """监控订单（复用逻辑）"""
        last_filled_size = 0.0  # 记录上次成交数量（避免重复累加）
        
        while self.status == ExecutorStatus.RUNNING:
            try:
                order_info = await self.config.exchange.get_order_status(
                    order_id,
                    self.config.symbol
                )
                
                if not order_info:
                    await asyncio.sleep(0.5)
                    continue
                
                filled_size = float(order_info.get("filled_size", 0))
                avg_price = float(order_info.get("avg_fill_price", 0))
                commission = float(order_info.get("commission", 0))
                
                # 计算增量（避免重复累加）
                filled_increment = filled_size - last_filled_size
                last_filled_size = filled_size
                
                # 只更新增量部分
                if filled_increment > 0:
                    self.filled_size += filled_increment
                    self.commission += commission
                    
                    # 计算加权平均价格
                    if self.filled_size > 0:
                        total_value = self.avg_fill_price * (self.filled_size - filled_size) + avg_price * filled_size
                        self.avg_fill_price = total_value / self.filled_size
                
                status = order_info.get("status")
                if status == "filled":
                    break
                elif status in ["cancelled", "rejected"]:
                    break
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"❌ 监控订单错误: {e}")
                await asyncio.sleep(1)
