"""
✋ 订单管理器 (Phase 4 最终版)
严防“跛脚”风险：原子化执行现货买入 + 合约做空
"""

import asyncio
import logging
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from datetime import datetime

from exchange.okx_client import OKXClient
from core.events import EventBus, Event, EventType
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
        self.logger = logging.getLogger(__name__)

    async def submit_single_order(self, symbol: str, side: str, size: float, pos_side: str = "net") -> OrderResult:
        """
        提交单腿订单 (底层原子方法)
        """
        try:
            inst_id = symbol

            data = {
                "instId": inst_id,
                "tdMode": "cross",  # 全仓
                "side": side,       # buy / sell
                "ordType": "market",# 市价单 (套利必须要快)
                "sz": str(size),    # 数量
            }

            # 如果是合约，需要指定开平仓方向
            if "SWAP" in inst_id:
                data["posSide"] = pos_side # short / long

            self.logger.info(f"🚀 发送下单请求: {inst_id} {side} {size}")

            # 调用 OKXClient 的 _request
            result = await self.client._request("POST", "/api/v5/trade/order", data=data)

            if result and len(result) > 0:
                ord_id = result[0].get("ordId")
                code = result[0].get("sCode", "0")
                if ord_id and code == "0":
                    self.logger.info(f"✅ 订单提交成功: {inst_id} ID:{ord_id}")
                    return OrderResult(success=True, order_id=ord_id)
                else:
                    msg = result[0].get("sMsg", "Unknown Error")
                    return OrderResult(success=False, error_msg=msg)
            else:
                return OrderResult(success=False, error_msg="API返回空")

        except Exception as e:
            self.logger.error(f"❌ 下单异常 {symbol}: {e}")
            return OrderResult(success=False, error_msg=str(e))

    async def execute_dual_leg(self,
                             spot_symbol: str, spot_size: float,
                             swap_symbol: str, swap_size: float) -> bool:
        """
        🔥 核心：双腿原子化下单 (Spot Buy + Swap Short)
        严格风控：任何一腿失败，立即熔断！
        """
        # 1. 再次确认状态
        if not self.sm.is_in_state(SystemState.OPENING_POSITION):
            self.logger.error("❌ 拒绝下单：系统状态不是 OPENING_POSITION")
            return False

        self.logger.info(f"⚡ 开始双腿执行: 买入 {spot_symbol} ({spot_size}) + 做空 {swap_symbol} ({swap_size})")

        # 2. 并发执行 (Concurrency)
        # 使用 asyncio.gather 同时发出两个请求，最大程度减少时间差
        spot_task = self.submit_single_order(spot_symbol, "buy", spot_size)
        swap_task = self.submit_single_order(swap_symbol, "sell", swap_size, pos_side="short")

        results = await asyncio.gather(spot_task, swap_task, return_exceptions=True)
        res_spot = results[0]
        res_swap = results[1]

        # 3. 结果判定与生死决策

        # 情况A: 完美成功
        if isinstance(res_spot, OrderResult) and res_spot.success and \
           isinstance(res_swap, OrderResult) and res_swap.success:
            self.logger.info("🎉 双腿成交：完美套利锁仓完成")
            if self.bus:
                await self.bus.publish(Event(EventType.ORDER_FILLED, {"type": "dual_leg", "status": "success"}))
            return True

        # 情况B: 全部失败 (虽然没赚钱，但至少没亏钱，算安全)
        spot_failed = not isinstance(res_spot, OrderResult) or not res_spot.success
        swap_failed = not isinstance(res_swap, OrderResult) or not res_swap.success

        if spot_failed and swap_failed:
            self.logger.warning("⚠️ 双腿均失败：未开仓，系统安全")
            # 可以安全返回，等待下一次机会
            return False

        # 情况C: 🔥 跛脚 (最危险的情况)
        # 一边成了，一边挂了。必须立即报警并熔断！
        self.logger.critical("🚨🚨🚨 发生跛脚 (Legged Risk) 🚨🚨🚨")

        error_details = []
        if not spot_failed:
            error_details.append(f"现货买入成功 (ID: {res_spot.order_id})")
        else:
            error_details.append(f"现货买入失败: {res_spot.error_msg if isinstance(res_spot, OrderResult) else res_spot}")

        if not swap_failed:
            error_details.append(f"合约做空成功 (ID: {res_swap.order_id})")
        else:
            error_details.append(f"合约做空失败: {res_swap.error_msg if isinstance(res_swap, OrderResult) else res_swap}")

        self.logger.critical(f"详情: {'; '.join(error_details)}")

        # 4. 🔥 触发死刑判决：系统熔断 (这里必须用 await transition_to)
        await self.sm.transition_to(SystemState.ERROR, reason="Legged Trade")

        if self.bus:
            await self.bus.publish(Event(EventType.RISK_ALERT, {
                "level": "critical",
                "message": f"跛脚成交！请立即检查！{error_details}"
            }))

        return False