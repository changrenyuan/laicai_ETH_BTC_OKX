import math


class ShortMartingaleStrategy:
    def __init__(
        self,
        base_size: float,
        max_orders: int = 5,
        step_pct: float = 0.0085,
        step_factor: float = 1.3,
        size_factor: float = 1.25,
    ):
        self.base_size = base_size
        self.max_orders = max_orders
        self.step_pct = step_pct
        self.step_factor = step_factor
        self.size_factor = size_factor

    def build_orders(self, entry_price: float):
        """
        根据首次价格生成限价做空订单
        """
        orders = []

        cumulative_step = 0.0
        size = self.base_size

        for i in range(self.max_orders):
            if i == 0:
                price = entry_price
            else:
                cumulative_step += self.step_pct * (self.step_factor ** (i - 1))
                price = entry_price * (1 + cumulative_step)

            orders.append({
                "index": i + 1,
                "price": round(price, 4),
                "size": round(size, 4),
            })

            size *= self.size_factor

        return orders
