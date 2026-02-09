"""
✋ 订单管理器
原子化下单 / 撤单
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List
import logging


@dataclass
class Order:
    """订单"""

    order_id: str
    symbol: str
    side: str  # buy, sell
    order_type: str  # market, limit
    quantity: float
    price: float
    status: str  # pending, submitted, filled, cancelled, rejected
    filled_quantity: float
    filled_price: float
    timestamp: datetime
    reason: str = ""


class OrderManager:
    """
    订单管理器类
    管理订单的提交、取消和状态跟踪
    """

    def __init__(self, config: dict, exchange_client=None):
        self.config = config
        self.exchange_client = exchange_client

        self.logger = logging.getLogger(__name__)

        # 订单记录
        self.orders: Dict[str, Order] = {}
        self.pending_orders: List[str] = []

    async def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "market",
        reduce_only: bool = False,
        post_only: bool = False,
    ) -> Optional[Order]:
        """
        提交订单

        Args:
            symbol: 交易品种
            side: 买卖方向 buy/sell
            quantity: 数量
            price: 价格（限价单必填）
            order_type: 订单类型 market/limit
            reduce_only: 是否仅减仓
            post_only: 是否仅挂单

        Returns:
            Order: 订单对象，失败返回None
        """
        try:
            # 生成订单ID
            order_id = f"{symbol}_{side}_{int(datetime.now().timestamp() * 1000)}"

            # 创建订单对象
            order = Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price or 0.0,
                status="pending",
                filled_quantity=0.0,
                filled_price=0.0,
                timestamp=datetime.now(),
            )

            # 记录订单
            self.orders[order_id] = order
            self.pending_orders.append(order_id)

            # TODO: 调用交易所API提交订单
            # result = await self.exchange_client.place_order(
            #     instId=symbol,
            #     tdMode="cross",  # 全仓模式
            #     side=side.upper(),
            #     ordType=order_type.upper(),
            #     sz=str(quantity),
            #     px=str(price) if price else None,
            #     reduceOnly=reduce_only,
            #     postOnly=post_only,
            # )

            order.status = "submitted"
            self.logger.info(
                f"Order submitted: {order_id} {symbol} {side} {quantity} @ {price}"
            )

            return order

        except Exception as e:
            self.logger.error(f"Order submission failed: {e}")
            order.status = "rejected"
            order.reason = str(e)
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            bool: 是否成功
        """
        if order_id not in self.orders:
            self.logger.warning(f"Order not found: {order_id}")
            return False

        order = self.orders[order_id]

        if order.status not in ["pending", "submitted"]:
            self.logger.warning(f"Order cannot be cancelled: {order_id} (status: {order.status})")
            return False

        try:
            # TODO: 调用交易所API取消订单
            # await self.exchange_client.cancel_order(order_id=order_id, instId=order.symbol)

            order.status = "cancelled"

            # 从待处理列表中移除
            if order_id in self.pending_orders:
                self.pending_orders.remove(order_id)

            self.logger.info(f"Order cancelled: {order_id}")
            return True

        except Exception as e:
            self.logger.error(f"Order cancellation failed: {e}")
            return False

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        取消所有订单

        Args:
            symbol: 可选，指定交易品种

        Returns:
            int: 取消的订单数量
        """
        cancelled_count = 0

        orders_to_cancel = [
            order_id
            for order_id, order in self.orders.items()
            if order.status in ["pending", "submitted"]
            and (symbol is None or order.symbol == symbol)
        ]

        for order_id in orders_to_cancel:
            if await self.cancel_order(order_id):
                cancelled_count += 1

        self.logger.info(f"Cancelled {cancelled_count} orders")
        return cancelled_count

    def update_order_status(
        self,
        order_id: str,
        status: str,
        filled_quantity: Optional[float] = None,
        filled_price: Optional[float] = None,
    ):
        """
        更新订单状态

        Args:
            order_id: 订单ID
            status: 新状态
            filled_quantity: 成交数量
            filled_price: 成交价格
        """
        if order_id not in self.orders:
            self.logger.warning(f"Order not found: {order_id}")
            return

        order = self.orders[order_id]

        order.status = status

        if filled_quantity is not None:
            order.filled_quantity = filled_quantity

        if filled_price is not None:
            order.filled_price = filled_price

        # 如果订单已完成，从待处理列表中移除
        if status in ["filled", "cancelled", "rejected"] and order_id in self.pending_orders:
            self.pending_orders.remove(order_id)

        self.logger.info(
            f"Order status updated: {order_id} -> {status} "
            f"(filled: {filled_quantity} @ {filled_price})"
        )

    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self.orders.get(order_id)

    def get_pending_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        获取待处理订单

        Args:
            symbol: 可选，指定交易品种

        Returns:
            List[Order]: 待处理订单列表
        """
        return [
            self.orders[order_id]
            for order_id in self.pending_orders
            if symbol is None or self.orders[order_id].symbol == symbol
        ]

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "total_orders": len(self.orders),
            "pending_orders": len(self.pending_orders),
            "orders": {
                order_id: {
                    "symbol": order.symbol,
                    "side": order.side,
                    "type": order.order_type,
                    "quantity": order.quantity,
                    "price": order.price,
                    "status": order.status,
                    "filled_quantity": order.filled_quantity,
                    "filled_price": order.filled_price,
                    "timestamp": order.timestamp.isoformat(),
                }
                for order_id, order in self.orders.items()
            },
        }

    def reset(self):
        """重置"""
        self.orders.clear()
        self.pending_orders.clear()
        self.logger.info("Order manager reset")
