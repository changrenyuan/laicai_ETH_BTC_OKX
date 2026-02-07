import math
from loguru import logger  # 建议替换 print 为 logger


class ShortMartingaleStrategy:
    def __init__(
            self,
            base_size: float,
            max_orders: int = 5,
            step_pct: float = 0.0085,  # 每一单之间的价格间隔 (0.85%)
            step_factor: float = 1.3,  # 价格间隔的扩大倍数 (越后面间隔越宽)
            size_factor: float = 1.25,  # 加仓倍数 (1.25倍投)
            leverage: int = 7,
            # --- 新增参数 ---
            tp_pct: float = 0.012,  # 目标止盈率 (1.2%)
            sl_pct: float = 0.05,  # 硬止损率 (5%) - 必须设置！
    ):
        self.base_size = base_size
        self.max_orders = max_orders
        self.step_pct = step_pct
        self.step_factor = step_factor
        self.size_factor = size_factor
        self.leverage = leverage
        # 新增变量存储
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct

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
                # 计算下一单的挂单价格 (做空是越涨越卖，所以价格是向上的)
                # 第1单: entry
                # 第2单: entry * (1 + 0.85%)
                # 第3单: entry * (1 + 0.85% + 0.85%*1.3)
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
        🔥 增强版审核：加入止损有效性检查
        """
        total_contracts = 0
        weighted_cost = 0.0
        margin_used = 0.0

        logger.info("\n--- 马丁格尔订单风控审核 ---")

        valid_orders = []  # 存储处理后的有效订单数据

        for o in orders:
            # 名义币数量 → 合约张数
            # 比如 0.1 ETH / 0.01 (每张大小) = 10 张
            raw_contracts = o["coin_size"] / ct_val
            # 向下取整到最小下单单位的倍数
            contracts = math.floor(raw_contracts / lot_sz) * lot_sz

            if contracts < 1:
                logger.warning(f"#{o['index']} ❌ 张数不足 (需 {lot_sz} 张)，跳过此单")
                continue

            # 名义价值 (USDT) = 张数 * 面值 * 价格
            notional = contracts * ct_val * o["price"]
            # 占用保证金 = 名义价值 / 杠杆
            margin = notional / self.leverage

            total_contracts += contracts
            weighted_cost += o["price"] * contracts
            margin_used += margin

            delta_pct = (o["price"] - entry_price) / entry_price * 100

            logger.info(
                f"#{o['index']} "
                f"挂单价={o['price']:.4f} "
                f"张数={int(contracts)} "
                f"名义价值={notional:.2f}U "
                f"拉升幅度={delta_pct:.2f}%"
            )

            # 将计算好的张数回写，用于后续下单
            o["calc_sz"] = int(contracts)
            valid_orders.append(o)

        if total_contracts == 0:
            logger.error("\n❌ 所有订单张数不足，策略失效")
            return None

        # --- 核心指标计算 ---
        avg_price = weighted_cost / total_contracts

        # 做空爆仓价 ≈ 均价 * (1 + 1/杠杆)
        # (注：这是粗略计算，未包含维持保证金率，实际爆仓价会更低一点点，所以我们要留余量)
        liq_price = avg_price * (1 + 1 / self.leverage)

        # 止损价格 = 均价 * (1 + 止损率)
        sl_price = avg_price * (1 + self.sl_pct)

        logger.info("\n--- 极端情况汇总 (假设全部成交) ---")
        logger.info(f"总持仓: {int(total_contracts)} 张")
        logger.info(f"持仓均价: {avg_price:.6f}")
        logger.info(f"预估爆仓价: {liq_price:.6f}")
        logger.info(f"策略止损价: {sl_price:.6f} (止损率 {self.sl_pct * 100}%)")
        logger.info(f"保证金占用: {margin_used:.2f} U")
        logger.info(f"账户可用: {avail_usdt:.2f} U")

        # --- 🔥 生死判断逻辑 (新增) ---
        is_safe = True

        # 1. 资金是否足够
        if margin_used > avail_usdt * 0.95:  # 留 5% 缓冲
            logger.error("🚨【致命】全成交所需保证金 > 账户余额，必死无疑！请降低 Base Size 或杠杆。")
            is_safe = False

        # 2. 止损是否有效 (止损价必须 < 爆仓价，否则没机会止损就先爆了)
        # 做空：价格上涨爆仓。所以止损价必须小于爆仓价。
        elif sl_price >= liq_price:
            logger.error(
                f"🚨【无效止损】止损价 ({sl_price:.2f}) 高于 爆仓价 ({liq_price:.2f})！一旦触发止损实际上已经爆仓。请降低杠杆或缩小止损率。")
            is_safe = False

        # 3. 风险评估
        elif liq_price / entry_price < 1.05:
            logger.warning("⚠️【高风险】爆仓价距离入场价不足 5%，极易被插针爆仓。")

        else:
            logger.success(f"✅【通过】策略结构合理。抗拉升能力: {(liq_price / entry_price - 1) * 100:.2f}%")

        if not is_safe:
            return None

        return {
            "avg_price": avg_price,
            "liq_price": liq_price,
            "sl_price": sl_price,
            "margin_used": margin_used,
            "total_contracts": total_contracts,
            "orders": valid_orders  # 返回处理好的订单列表
        }

    def get_exit_targets(self, avg_price: float):
        """
        新增功能：根据当前均价，计算止盈和止损价格
        做空：
            止盈价 = 均价 * (1 - 止盈率)  (价格下跌赚钱)
            止损价 = 均价 * (1 + 止损率)  (价格上涨亏钱)
        """
        tp_price = avg_price * (1 - self.tp_pct)
        sl_price = avg_price * (1 + self.sl_pct)

        return {
            "tp_price": tp_price,
            "sl_price": sl_price
        }

    def calculate_drawdown(self, current_price: float, avg_price: float) -> float:
        """
        新增功能：计算当前浮亏百分比
        """
        if avg_price == 0:
            return 0.0
        # 做空浮亏：(当前价 - 均价) / 均价
        # 如果当前价 110，均价 100，浮亏 10%
        pnl_pct = (current_price - avg_price) / avg_price
        return pnl_pct