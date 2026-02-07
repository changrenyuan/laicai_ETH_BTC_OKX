import math


class ShortMartingaleStrategy:
    def __init__(
        self,
        base_size: float,
        max_orders: int = 5,
        step_pct: float = 0.0085,
        step_factor: float = 1.3,
        size_factor: float = 1.25,
        leverage: int = 7,

    ):
        self.base_size = base_size
        self.max_orders = max_orders
        self.step_pct = step_pct
        self.step_factor = step_factor
        self.size_factor = size_factor
        self.leverage = leverage

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
                "price": round(price, 6),
                "coin_size": round(size, 6),
            })

            size *= self.size_factor

        return orders

    def audit_orders(
            self,
            orders: list[dict],
            entry_price: float,
            ct_val: float,  # 每张合约代表多少币
            lot_sz: float,  # 最小下单张数
            avail_usdt: float,  # 账户可用 USDT
    ):
        """
        🔥 这是你之前完全缺失的“生死判断模块”
        """
        total_contracts = 0
        weighted_cost = 0.0
        margin_used = 0.0

        print("\n--- 马汀格尔订单审核 ---")

        for o in orders:
            # 名义币数量 → 合约张数
            contracts = o["coin_size"] / ct_val
            contracts = math.floor(contracts / lot_sz) * lot_sz

            if contracts < 1:
                print(f"#{o['index']} ❌ 张数不足，跳过")
                continue

            notional = contracts * ct_val * o["price"]
            margin = notional / self.leverage

            total_contracts += contracts
            weighted_cost += o["price"] * contracts
            margin_used += margin

            delta_pct = (o["price"] - entry_price) / entry_price * 100

            print(
                f"#{o['index']} "
                f"挂单价={o['price']} "
                f"张数={int(contracts)} "
                f"名义={notional:.2f}U "
                f"涨幅={delta_pct:.2f}%"
            )

        if total_contracts == 0:
            print("\n❌ 所有订单张数不足，策略失效")
            return None

        avg_price = weighted_cost / total_contracts
        liq_price = avg_price * (1 + 1 / self.leverage)

        print("\n--- 汇总 ---")
        print(f"总张数: {int(total_contracts)}")
        print(f"平均开仓价: {avg_price:.6f}")
        print(f"预估爆仓价: {liq_price:.6f}")
        print(f"保证金占用: {margin_used:.2f} U")
        print(f"账户可用: {avail_usdt:.2f} U")

        # 🔥 生死判断
        if margin_used > avail_usdt:
            print("🚨【致命】全成交 = 保证金不足，必死")
        elif liq_price / entry_price > 1.15:
            print("⚠️【高风险】抗拉升能力 >15%，但不安全")
        else:
            print("✅【可接受】结构尚可，允许测试")

        return {
            "avg_price": avg_price,
            "liq_price": liq_price,
            "margin_used": margin_used,
            "total_contracts": total_contracts,
        }