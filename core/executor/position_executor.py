"""
📊 Position Executor - 持仓执行器
管理持仓，支持 DCA、TWAP、Grid 等策略
"""

import asyncio
import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict
# 在这两个文件的顶部添加/修改：
from core.executor.executor_base import ExecutorBase, ExecutorType, ExecutorConfig, ExecutorStatus
from core.executor.executor_base import ExecutorBase, ExecutorType, ExecutorConfig, ExecutorStatus
from core.events import Event, EventType


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


class PositionExecutor(ExecutorBase):
    """
    持仓执行器
    
    功能：
    - 执行入场订单
    - 管理止盈止损
    - 支持移动止损
    - 自动平仓
    """

    def __init__(
        self,
        config: ExecutorConfig,
        stop_loss: float,
        take_profit: float,
        time_limit_seconds: int = 86400,
        trailing_stop=None,
        callback=None
    ):
        super().__init__(config, callback)
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.time_limit_seconds = time_limit_seconds
        self.trailing_stop = trailing_stop
        self.entry_order_id: Optional[str] = None
        self.entry_price: Optional[float] = None
        self.exit_order_id: Optional[str] = None
        self.trailing_activated = False

    @property
    def executor_type(self) -> ExecutorType:
        return ExecutorType.POSITION

    async def execute(self):
        """执行持仓管理"""
        try:
            # 1. 下入场单
            entry_success, entry_order_id, error_msg = await self._place_order()
            
            if not entry_success:
                self.logger.error(f"❌ 入场单失败: {error_msg}")
                await self._mark_failed("entry_order_failed")
                return
            
            self.entry_order_id = entry_order_id
            self.order_ids.append(entry_order_id)
            self.logger.info(f"✅ 入场单提交: {entry_order_id}")
            
            # 2. 等待入场单成交
            await self._wait_for_fill(entry_order_id)
            
            if self.status != ExecutorStatus.RUNNING:
                return
            
            # 3. 记录入场价格
            order_info = await self.config.exchange.get_order_status(
                entry_order_id, self.config.symbol
            )
            if order_info:
                self.entry_price = float(order_info.get("avgPx", 0))
                if self.entry_price == 0:
                    self.entry_price = float(order_info.get("price", 0))
                self.logger.info(f"✅ 入场成交价格: {self.entry_price}")
            
            # 4. 开始监控持仓（止盈止损）
            await self._monitor_position()
            
        except Exception as e:
            self.logger.error(f"❌ 持仓执行错误: {e}")
            import traceback
            traceback.print_exc()
            await self._mark_failed("execution_error")

    async def _place_order(self) -> tuple:
        """下单"""
        order_data = {
            "symbol": self.config.symbol,
            "side": self.config.side,
            "size": self.config.size,
            "type": self.config.order_type
        }
        
        if self.config.order_type in ["limit", "post_only"]:
            if self.config.price:
                order_data["price"] = self.config.price
        
        return await self.config.exchange.place_order(order_data)

    async def _wait_for_fill(self, order_id: str):
        """等待订单成交"""
        while self.status == ExecutorStatus.RUNNING:
            try:
                order_info = await self.config.exchange.get_order_status(
                    order_id, self.config.symbol
                )
                
                if not order_info:
                    await asyncio.sleep(1)
                    continue
                
                status = order_info.get("status", "")
                
                if status == "filled":
                    # 计算成交信息
                    filled_size = float(order_info.get("fillSz", 0))
                    avg_price = float(order_info.get("avgPx", 0))
                    commission = float(order_info.get("fee", 0))
                    
                    self.filled_size = filled_size
                    self.avg_fill_price = avg_price
                    self.commission = commission
                    
                    self.logger.info(f"✅ 订单成交: {filled_size} @ {avg_price}")
                    break
                
                elif status in ["cancelled", "rejected"]:
                    self.logger.warning(f"⚠️ 订单被取消/拒绝: {status}")
                    await self._mark_failed("order_cancelled")
                    break
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"❌ 监控订单错误: {e}")
                await asyncio.sleep(1)

    async def _monitor_position(self):
        """监控持仓（止盈止损）"""
        start_time = datetime.now()
        
        while self.status == ExecutorStatus.RUNNING:
            try:
                # 获取当前价格
                ticker = await self.config.exchange.get_ticker(self.config.symbol)
                if not ticker:
                    await asyncio.sleep(1)
                    continue
                
                ticker_data = ticker[0] if isinstance(ticker, list) else ticker
                current_price = float(ticker_data.get("last", 0))
                if current_price == 0:
                    await asyncio.sleep(1)
                    continue
                
                # 计算盈亏
                if self.entry_price:
                    if self.config.side == "buy":
                        pnl_pct = (current_price - self.entry_price) / self.entry_price
                    else:  # sell
                        pnl_pct = (self.entry_price - current_price) / self.entry_price
                    
                    # 检查止盈
                    if self.config.side == "buy":
                        if current_price >= self.take_profit:
                            self.logger.info(f"🎯 止盈触发: {current_price:.6f}")
                            await self._close_position("take_profit")
                            break
                    else:  # sell
                        if current_price <= self.take_profit:
                            self.logger.info(f"🎯 止盈触发: {current_price:.6f}")
                            await self._close_position("take_profit")
                            break
                    
                    # 检查止损（考虑移动止损）
                    stop_loss_price = self.stop_loss
                    
                    if self.trailing_stop and not self.trailing_activated:
                        # 检查是否激活移动止损
                        if self.config.side == "buy":
                            is_activated = current_price >= self.trailing_stop.activation_price
                        else:  # sell
                            is_activated = current_price <= self.trailing_stop.activation_price
                        
                        if is_activated:
                            self.trailing_activated = True
                            self.logger.info(f"🔄 移动止损已激活")
                    
                    if self.trailing_stop and self.trailing_activated:
                        # 使用移动止损
                        if self.config.side == "buy":
                            stop_loss_price = current_price * (1 - self.trailing_stop.trailing_distance_pct)
                            stop_loss_price = max(stop_loss_price, self.entry_price)  # 锁住至少不亏损
                        else:  # sell
                            stop_loss_price = current_price * (1 + self.trailing_stop.trailing_distance_pct)
                            stop_loss_price = min(stop_loss_price, self.entry_price)  # 锁住至少不亏损
                    
                    if self.config.side == "buy":
                        if current_price <= stop_loss_price:
                            self.logger.info(f"🛑 止损触发: {current_price:.6f}")
                            await self._close_position("stop_loss")
                            break
                    else:  # sell
                        if current_price >= stop_loss_price:
                            self.logger.info(f"🛑 止损触发: {current_price:.6f}")
                            await self._close_position("stop_loss")
                            break
                    
                    # 检查时间限制
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if elapsed >= self.time_limit_seconds:
                        self.logger.info(f"⏰ 时间限制触发: {elapsed:.0f}秒")
                        await self._close_position("time_limit")
                        break
                
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"❌ 监控持仓错误: {e}")
                await asyncio.sleep(1)

    async def _close_position(self, reason: str):
        """平仓"""
        try:
            # 计算平仓方向（与入场方向相反）
            close_side = "sell" if self.config.side == "buy" else "buy"
            
            # 下市价单平仓
            order_data = {
                "symbol": self.config.symbol,
                "side": close_side,
                "size": self.filled_size,
                "type": "market"
            }
            
            success, order_id, error_msg = await self.config.exchange.place_order(order_data)
            
            if success:
                self.exit_order_id = order_id
                self.order_ids.append(order_id)
                self.logger.info(f"✅ 平仓单提交: {order_id}")
                
                # 等待平仓成交
                await self._wait_for_fill(order_id)
                
                if self.status == ExecutorStatus.RUNNING:
                    await self._mark_completed(reason)
            else:
                self.logger.error(f"❌ 平仓单失败: {error_msg}")
                await self._mark_failed("close_order_failed")
                
        except Exception as e:
            self.logger.error(f"❌ 平仓错误: {e}")
            await self._mark_failed("close_position_error")



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
