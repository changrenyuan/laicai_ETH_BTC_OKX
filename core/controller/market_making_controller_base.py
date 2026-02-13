"""
📊 MarketMakingControllerBase - 做市商控制器基类
================================================
用于实现网格交易、做市等双向策略

核心特性：
- 双向挂单（买一/卖一）
- 动态价差调整
- 库存风险管理
- 支持网格策略
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime

from core.controller.controller_base import ControllerBase, EventType
from core.events import Event
from core.executor.executor_base import ExecutorConfig, ExecutorType
from core.executor.order_executor import OrderExecutor


class MarketMakingControllerBase(ControllerBase):
    """
    做市商控制器基类
    
    适用于：
    - 网格交易策略
    - 做市策略
    - 套利策略
    """

    def __init__(
        self,
        config: Dict,
        exchanges: Dict,
        executor_orchestrator
    ):
        super().__init__(config, exchanges, executor_orchestrator)
        
        # 做市商参数
        self.symbol = config.get("trading_pair", "BTC-USDT-SWAP")
        self.spread_pct = config.get("spread_pct", 0.001)  # 价差百分比
        self.order_size = config.get("order_size", 0.001)
        self.max_orders = config.get("max_orders", 10)  # 最大订单数
        
        # 网格参数
        self.grid_levels = config.get("grid_levels", 5)
        self.grid_spacing_pct = config.get("grid_spacing_pct", 0.002)
        
        # 库存管理
        self.max_inventory_ratio = config.get("max_inventory_ratio", 0.5)  # 最大库存比例
        self.inventory_skew_enabled = config.get("inventory_skew_enabled", True)
        
        # 订单跟踪
        self.active_orders: Dict[str, Dict] = {}  # order_id -> order_info
        self.bids: List[Dict] = []  # 买单列表
        self.asks: List[Dict] = []  # 卖单列表
        
        # 统计
        self.total_filled = 0
        self.total_volume = 0.0

    @property
    def controller_type(self) -> str:
        return "market_making"

    async def _initialize_strategy_state(self):
        """初始化策略状态"""
        self.logger.info("初始化做市商策略状态...")
        
        # 计算网格价格
        await self._calculate_grid_levels()

    async def _calculate_grid_levels(self):
        """计算网格价格"""
        try:
            # 获取当前价格
            exchange = self._get_exchange()
            ticker = await exchange.get_ticker(self.symbol)
            
            if not ticker:
                return
            
            ticker_data = ticker[0] if isinstance(ticker, list) else ticker
            current_price = float(ticker_data.get("last", 0))
            
            if current_price == 0:
                return
            
            # 计算网格层级
            self.bids = []
            self.asks = []
            
            for i in range(1, self.grid_levels + 1):
                # 买单价格：向下偏移
                bid_price = current_price * (1 - i * self.grid_spacing_pct)
                self.bids.append({
                    "price": bid_price,
                    "size": self.order_size,
                    "level": i
                })
                
                # 卖单价格：向上偏移
                ask_price = current_price * (1 + i * self.grid_spacing_pct)
                self.asks.append({
                    "price": ask_price,
                    "size": self.order_size,
                    "level": i
                })
            
            self.logger.info(f"✅ 计算网格完成: 中心价格={current_price:.2f}, "
                           f"层级={self.grid_levels}")
            
        except Exception as e:
            self.logger.error(f"❌ 计算网格失败: {e}")

    async def process_tick(self, event: Event):
        """
        处理行情更新
        
        1. 更新统计信息
        2. 检查订单状态
        3. 补单（如果需要）
        4. 调整价格（如果需要）
        """
        if not self.is_active:
            return
        
        self.stats["ticks_processed"] += 1
        self.last_tick_time = datetime.now()
        
        try:
            data = event.data
            symbol = data.get("symbol")
            
            if symbol != self.symbol:
                return
            
            # 检查订单状态
            await self._check_orders()
            
            # 检查是否需要补单
            await self._replenish_orders()
            
            # 检查价格偏离
            await self._adjust_prices()
            
        except Exception as e:
            self.logger.error(f"❌ 处理 Tick 失败: {e}")

    async def _check_orders(self):
        """检查订单状态"""
        exchange = self._get_exchange()
        
        for order_id, order_info in list(self.active_orders.items()):
            try:
                order_status = await exchange.get_order_status(order_id, self.symbol)
                
                if not order_status:
                    continue
                
                status = order_status.get("status")
                
                if status == "filled":
                    # 订单成交
                    self._on_order_filled(order_id, order_info)
                    del self.active_orders[order_id]
                elif status in ["cancelled", "rejected"]:
                    # 订单被取消
                    del self.active_orders[order_id]
                    
            except Exception as e:
                self.logger.error(f"❌ 检查订单失败 {order_id}: {e}")

    def _on_order_filled(self, order_id: str, order_info: Dict):
        """
        订单成交处理
        
        Args:
            order_id: 订单ID
            order_info: 订单信息
        """
        side = order_info.get("side")
        size = order_info.get("size")
        price = order_info.get("price")
        
        self.total_filled += 1
        self.total_volume += size * price
        
        self.logger.info(f"✅ 订单成交: {side} {size} @ {price}")
        
        # 发布事件
        asyncio.create_task(self._emit_event(EventType.ORDER_FILLED, {
            "order_id": order_id,
            "symbol": self.symbol,
            "side": side,
            "size": size,
            "price": price
        }))

    async def _replenish_orders(self):
        """补单（填补空缺的订单）"""
        # 检查买单数量
        active_bids = [o for o in self.active_orders.values() if o["side"] == "buy"]
        if len(active_bids) < self.grid_levels:
            # 补买单
            await self._place_missing_orders("buy")
        
        # 检查卖单数量
        active_asks = [o for o in self.active_orders.values() if o["side"] == "sell"]
        if len(active_asks) < self.grid_levels:
            # 补卖单
            await self._place_missing_orders("sell")

    async def _place_missing_orders(self, side: str):
        """
        下缺失的订单
        
        Args:
            side: "buy" 或 "sell"
        """
        exchange = self._get_exchange()
        levels = self.bids if side == "buy" else self.asks
        
        for level_info in levels:
            # 检查该层级的订单是否存在
            existing = [
                o for o in self.active_orders.values()
                if o["side"] == side and abs(o["price"] - level_info["price"]) < 0.01
            ]
            
            if existing:
                continue  # 已存在
            
            # 下新单
            try:
                order_data = {
                    "symbol": self.symbol,
                    "side": side,
                    "size": level_info["size"],
                    "type": "limit",
                    "price": f"{level_info['price']:.6f}"
                }
                
                success, order_id, error_msg = await exchange.place_order(order_data)
                
                if success:
                    self.active_orders[order_id] = {
                        "order_id": order_id,
                        "side": side,
                        "size": level_info["size"],
                        "price": level_info["price"],
                        "level": level_info["level"]
                    }
                    self.logger.info(f"✅ 补单成功: {side} {level_info['size']} @ {level_info['price']:.6f}")
                else:
                    self.logger.error(f"❌ 补单失败: {error_msg}")
                    
            except Exception as e:
                self.logger.error(f"❌ 下单异常: {e}")

    async def _adjust_prices(self):
        """调整价格（如果偏离当前价格太远）"""
        # 定期重新计算网格
        pass

    def determine_executor_config(self, signal: Dict) -> Optional[ExecutorConfig]:
        """
        做市商策略通常不需要此方法
        做市商直接下单，不使用执行器
        """
        return None

    def _create_executor_instance(self, config: ExecutorConfig):
        """
        做市商策略通常不创建执行器
        """
        return None

    def _get_exchange(self):
        """获取交易所实例"""
        return next(iter(self.exchanges.values()), None)

    def get_market_stats(self) -> Dict:
        """
        获取做市统计
        
        Returns:
            Dict: 做市统计信息
        """
        return {
            "total_filled": self.total_filled,
            "total_volume": self.total_volume,
            "active_orders": len(self.active_orders),
            "bids_count": len([o for o in self.active_orders.values() if o["side"] == "buy"]),
            "asks_count": len([o for o in self.active_orders.values() if o["side"] == "sell"]),
            "grid_levels": self.grid_levels,
            "spread_pct": self.spread_pct
        }


# 导出
__all__ = ["MarketMakingControllerBase"]
