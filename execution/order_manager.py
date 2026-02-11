"""
✋ 订单管理器 (通用版 - 调试增强版)
负责对接交易所 API 执行具体的下单动作，支持智能重试和自动模式切换。
"""

import asyncio
import logging
from typing import Optional, Tuple
from datetime import datetime

from exchange.okx_client import OKXClient
from core.events import EventBus, Event
from core.state_machine import StateMachine, SystemState


class OrderManager:
    """订单管理器 - 支持智能重试和自动模式切换"""

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
        price: Optional[str] = None,  # 限价单必须传价格
        pos_side: str = "net",       # 单向持仓模式通常为 net
        reduce_only: bool = False,
        stop_loss: Optional[float] = None,   # 止损价格
        take_profit: Optional[float] = None  # 止盈价格
    ) -> Tuple[bool, str, str]:
        """
        提交单腿订单 (支持自动降级重试：Long/Short -> Net)
        返回: (success, order_id, error_msg)
        """
        try:
            # 1. 数量精度处理
            final_sz = str(size)
            if "SWAP" in symbol or "FUTURES" in symbol:
                int_size = int(size)
                if int_size < 1:
                    return False, "", f"合约下单数量不足 1 张 (原始: {size})"
                final_sz = str(int_size)

            # 2. 准备止盈止损参数 (修复：增加 triggerPxType + 修复 clOrdId 格式 + 防重复)
            algo_ords = []
            if stop_loss or take_profit:
                # 🔥 修复：使用时间戳 + 微秒 + 随机数，确保唯一性
                import time
                algo_cl_ord_id = str(int(time.time() * 1000000)) + str(int(time.time() % 10000))
                algo_args = {
                    "attachAlgoClOrdId": algo_cl_ord_id,
                    "tpTriggerPxType": "last",  # 触发价格类型：最新成交价
                    "slTriggerPxType": "last"
                }
                # 只有当参数存在时才添加对应的 TriggerPx 和 OrdPx
                if take_profit:
                    algo_args["tpOrdPx"] = "-1"  # 市价止盈
                    algo_args["tpTriggerPx"] = str(take_profit)
                if stop_loss:
                    algo_args["slOrdPx"] = "-1"  # 市价止损
                    algo_args["slTriggerPx"] = str(stop_loss)

                algo_ords.append(algo_args)

            # 3. 确定持仓模式 (关键修复：正确处理平仓)
            target_pos_side = pos_side

            if ("SWAP" in symbol or "FUTURES" in symbol):
                if reduce_only:
                    # 🔥 平仓模式：方向反转
                    # sell (卖出) + reduce_only = 平多 (posSide=long)
                    # buy (买入) + reduce_only = 平空 (posSide=short)
                    if side == "sell":
                        target_pos_side = "long"  # 平多
                    else:  # side == "buy"
                        target_pos_side = "short"  # 平空
                    self.logger.info(f"🔄 [平仓模式] {side} -> posSide={target_pos_side}")
                elif pos_side == "net":
                    # 开仓模式：buy = long, sell = short
                    target_pos_side = "long" if side == "buy" else "short"
                    self.logger.info(f"📈 [开仓模式] {side} -> posSide={target_pos_side}")

            # 4. 构建请求数据
            data = {
                "instId": symbol,
                "tdMode": "cross",   # 全仓
                "side": side,
                "ordType": order_type,
                "sz": final_sz,
                "posSide": target_pos_side
            }
            if order_type == "limit" and price:
                data["px"] = str(price)
            if reduce_only:
                data["reduceOnly"] = "true"
            if algo_ords:
                data["attachAlgoOrds"] = algo_ords

            # 5. 第一次尝试
            order_type_str = "平仓" if reduce_only else "开仓"
            self.logger.info(f"⚡ 尝试{order_type_str}下单 (模式: {target_pos_side}): {symbol} {side} {final_sz} (SL/TP: {'Yes' if algo_ords else 'No'})")

            # 🔥 调用修改后的 place_order，接收 3 个返回值
            success, order_id, error_msg = await self.client.place_order(data)

            # 6. 失败重试逻辑 (尝试 Net 模式)
            if not success and ("SWAP" in symbol or "FUTURES" in symbol):
                # 如果错误是 "Position side does not match"，那么重试才有意义
                # 但为了保险，我们对大部分错误都尝试一次 Net 模式
                self.logger.warning(f"⚠️ 第一次下单失败: {error_msg} -> 尝试切换为单向持仓 (Net Mode) 重试...")

                # 修改模式为 Net
                data["posSide"] = "net"
                # 再次调用 API
                success, order_id, error_msg = await self.client.place_order(data)

                if success:
                    self.logger.info(f"✅ 重试成功 (Net Mode): ID={order_id}")

            # 7. 最终结果处理
            if success:
                self.logger.info(f"✅ 下单最终成功: {symbol} ID={order_id}")
                return True, order_id, ""
            else:
                # 🔥 这里将打印出真正的错误原因！
                self.logger.error(f"❌ 下单最终失败. 原因: {error_msg}")
                return False, "", error_msg

        except Exception as e:
            self.logger.error(f"❌ 下单异常 {symbol}: {e}")
            return False, "", str(e)

    async def execute_dual_leg(self, spot_symbol, spot_size, swap_symbol, swap_size) -> bool:
        """执行双腿套利下单"""
        self.logger.info(f"⚖️ 执行双腿交易: 买入 {spot_symbol} ({spot_size}) + 做空 {swap_symbol} ({swap_size})")

        task_spot = self.submit_single_order(spot_symbol, "buy", spot_size, "market")
        task_swap = self.submit_single_order(swap_symbol, "sell", swap_size, "market")

        results = await asyncio.gather(task_spot, task_swap, return_exceptions=True)

        def parse_res(res):
            if isinstance(res, tuple) and len(res) >= 3:
                return res[0], res[1], res[2]
            return False, "", str(res)

        res_spot = parse_res(results[0])
        res_swap = parse_res(results[1])

        spot_ok, spot_id, spot_err = res_spot
        swap_ok, swap_id, swap_err = res_swap

        if spot_ok and swap_ok:
            self.logger.info(f"✅ 双腿成交: Spot={spot_id}, Swap={swap_id}")
            return True

        if spot_ok != swap_ok:
            self.logger.critical(f"🚨🚨🚨 发生跛脚! Spot: {spot_ok} (err: {spot_err}), Swap: {swap_ok} (err: {swap_err})")
            return False

        self.logger.warning(f"⚠️ 双腿均失败 (Spot: {spot_err}, Swap: {swap_err})")
        return False

    async def cancel_all_orders(self, symbol: Optional[str] = None):
        """撤销挂单"""
        try:
            return await self.client.cancel_all_orders(inst_id=symbol)
        except Exception as e:
            self.logger.error(f"撤单失败: {e}")
            return False
