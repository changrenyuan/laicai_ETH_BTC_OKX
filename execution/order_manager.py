"""
✋ 订单管理器 (通用版)
负责对接交易所 API 执行具体的下单动作，支持市价、限价、单腿及双腿交易。
"""

import asyncio
import logging
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from datetime import datetime

# 假设 OKXClient 在 exchange 模块中
from exchange.okx_client import OKXClient
from core.events import EventBus, Event
from core.state_machine import StateMachine, SystemState

@dataclass
class OrderResult:
    success: bool
    order_id: str = ""
    error_msg: str = ""

class OrderManager:
    def __init__(self, client: OKXClient, state_machine: StateMachine, event_bus: EventBus):
        self.client = client
        self.sm = state_machine
        self.bus = event_bus
        self.logger = logging.getLogger("OrderManager")

    async def submit_single_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str = "market",  # 默认市价
        price: Optional[str] = None, # 限价单必须传价格
        pos_side: str = "net",       # 单向持仓模式通常为 net
        reduce_only: bool = False
    ) -> Tuple[bool, str]:
        """
        提交单腿订单 (通用底层方法)
        支持 Market 和 Limit 两种类型
        """
        try:
            self.logger.info(f"⚡ 准备下单: {symbol} {side} {size} ({order_type} @ {price if price else 'Market'})")

            # 1. 构建基础参数
            data = {
                "instId": symbol,
                "tdMode": "cross",   # 默认全仓，可根据 config 修改
                "side": side,        # buy / sell
                "ordType": order_type,
                "sz": str(size),
                "posSide": pos_side
            }

            # 2. 针对限价单的处理
            if order_type == "limit":
                if not price:
                    return False, "限价单必须提供 price 参数"
                data["px"] = str(price)

            # 3. 只减仓参数
            if reduce_only:
                data["reduceOnly"] = "true"

            # 4. 调用 API
            # 注意：这里假设 client.place_order 接受 **kwargs 或字典
            # 如果您的 client 是固定参数的，请相应调整
            order_id = await self.client.place_order(data)

            if order_id:
                self.logger.info(f"✅ 下单成功: {symbol} ID={order_id}")
                return True, order_id
            else:
                self.logger.error(f"❌ 下单失败: API 返回空 ID")
                return False, ""

        except Exception as e:
            self.logger.error(f"❌ 下单异常 {symbol}: {e}")
            return False, ""

    async def execute_dual_leg(
        self,
        spot_symbol: str,
        spot_size: float,
        swap_symbol: str,
        swap_size: float
    ) -> bool:
        """
        执行双腿套利下单 (原子性尝试)
        注意：网格和趋势策略通常不使用此方法，仅供套利策略使用
        """
        self.logger.info(f"⚖️ 执行双腿交易: 买入 {spot_symbol} ({spot_size}) + 做空 {swap_symbol} ({swap_size})")

        # 1. 并发下单
        # 注意：套利通常用市价单以保证成交
        task_spot = self.submit_single_order(spot_symbol, "buy", spot_size, "market")
        task_swap = self.submit_single_order(swap_symbol, "sell", swap_size, "market")

        results = await asyncio.gather(task_spot, task_swap, return_exceptions=True)

        # 解析结果 (results 是 [(success, id), (success, id)])
        res_spot = results[0] if isinstance(results[0], tuple) else (False, str(results[0]))
        res_swap = results[1] if isinstance(results[1], tuple) else (False, str(results[1]))

        spot_ok, spot_id = res_spot
        swap_ok, swap_id = res_swap

        # 2. 结果判定
        if spot_ok and swap_ok:
            self.logger.info(f"✅ 双腿成交: Spot={spot_id}, Swap={swap_id}")
            return True

        # 3. 跛脚处理 (一边成了一边没成)
        if spot_ok != swap_ok:
            self.logger.critical(f"🚨🚨🚨 发生跛脚! Spot: {spot_ok}, Swap: {swap_ok}")
            self.bus.publish(Event("RISK_ALERT", {
                "type": "legged_trade",
                "details": f"Spot:{spot_ok}, Swap:{swap_ok}"
            }))
            # 这里可以加入紧急平仓逻辑 (Emergency Close)
            return False

        self.logger.warning("⚠️ 双腿均失败")
        return False

    async def cancel_all_orders(self, symbol: Optional[str] = None):
        """撤销挂单"""
        try:
            return await self.client.cancel_all_orders(inst_id=symbol)
        except Exception as e:
            self.logger.error(f"撤单失败: {e}")
            return False