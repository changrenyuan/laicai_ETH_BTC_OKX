"""
📋 Order Executor - 单订单执行器
执行单个订单（市价单、限价单等）
"""

import asyncio
import logging
from typing import Optional, Dict
# 在这两个文件的顶部添加/修改：
from core.executor.executor_base import ExecutorBase, ExecutorType, ExecutorConfig, ExecutorStatus
from core.executor.executor_base import ExecutorBase, ExecutorType, ExecutorConfig
from core.events import Event, EventType


class OrderExecutor(ExecutorBase):
    """
    单订单执行器
    
    功能：
    - 下单
    - 监控订单状态
    - 自动更新填充信息
    """

    def __init__(self, config: ExecutorConfig, callback=None):
        super().__init__(config, callback)
        self.order_id: Optional[str] = None
        self.order_status: Optional[str] = None

    @property
    def executor_type(self) -> ExecutorType:
        return ExecutorType.ORDER

    async def execute(self):
        """执行订单"""
        try:
            # 下单
            success, order_id, error_msg = await self._place_order()
            
            if not success:
                self.logger.error(f"❌ 下单失败: {error_msg}")
                self.status = ExecutorStatus.FAILED
                return
            
            self.order_id = order_id
            self.order_ids.append(order_id)
            self.logger.info(f"✅ 下单成功: {order_id}")
            
            # 发送订单创建事件
            await self._emit_event(Event(
                event_type=EventType.ORDER_CREATED,
                data={
                    "order_id": order_id,
                    "symbol": self.config.symbol,
                    "side": self.config.side,
                    "size": self.config.size,
                    "price": self.config.price,
                    "order_type": self.config.order_type
                }
            ))
            
            # 监控订单
            await self._monitor_order()
            
        except Exception as e:
            self.logger.error(f"❌ 订单执行失败: {e}")
            self.status = ExecutorStatus.FAILED

    async def _place_order(self) -> tuple:
        """下单"""
        exchange = self.config.exchange
        
        # 构建订单参数
        order_data = {
            "symbol": self.config.symbol,
            "side": self.config.side,
            "size": self.config.size,
            "type": self.config.order_type
        }
        
        # 添加价格（限价单）
        if self.config.order_type in ["limit", "post_only", "ioc", "fok"]:
            if self.config.price:
                order_data["price"] = self.config.price
            else:
                # 获取当前价格作为参考
                ticker = await exchange.get_ticker(self.config.symbol)
                if ticker:
                    current_price = float(ticker.get("last_price", 0))
                    # 买单略低，卖单略高
                    if self.config.side == "buy":
                        order_data["price"] = current_price * 0.999
                    else:
                        order_data["price"] = current_price * 1.001
        
        # 下单
        success, order_id, error_msg = await exchange.place_order(order_data)
        
        return success, order_id, error_msg

    async def _monitor_order(self):
        """监控订单状态"""
        while self.status == ExecutorStatus.RUNNING:
            try:
                # 获取订单状态
                order_info = await self.config.exchange.get_order_status(
                    self.order_id,
                    self.config.symbol
                )
                
                if not order_info:
                    await asyncio.sleep(1)
                    continue
                
                self.order_status = order_info.get("status")
                filled_size = float(order_info.get("filled_size", 0))
                avg_price = float(order_info.get("avg_fill_price", 0))
                commission = float(order_info.get("commission", 0))
                
                # 更新填充信息
                self.filled_size = filled_size
                self.avg_fill_price = avg_price
                self.commission = commission
                
                # 检查订单状态
                if self.order_status == "filled":
                    self.logger.info(f"✅ 订单成交: {self.order_id}")
                    await self._mark_completed("order_filled")
                    break
                elif self.order_status == "cancelled":
                    self.logger.warning(f"⚠️ 订单被取消: {self.order_id}")
                    await self.stop("order_cancelled")
                    break
                elif self.order_status == "rejected":
                    self.logger.error(f"❌ 订单被拒绝: {self.order_id}")
                    self.status = ExecutorStatus.FAILED
                    break
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"❌ 监控订单错误: {e}")
                await asyncio.sleep(1)

    async def cancel_order(self):
        """取消订单"""
        if self.order_id:
            success, _, _ = await self.config.exchange.cancel_order(
                self.order_id,
                self.config.symbol
            )
            if success:
                self.logger.info(f"🗑️ 取消订单: {self.order_id}")
                await self.stop("user_cancelled")
