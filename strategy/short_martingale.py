import math
from loguru import logger  # 建议替换 print 为 logger

import config.config


class ShortMartingaleStrategy:
    def __init__(
            self,
            total_value_usdt: float,      # 初始投资额 (USDT)
            max_orders: int = 5, # 最大加仓次数 (0-100)
            entry_offset_pct: float = 0.016,  # 起始价格偏移 (比如 1% 表示现价上涨 1% 开始第一单)
            step_pct: float = 0.0085,  # 每一单之间的价格间隔 (0.85%)
            step_factor: float = 1.3,  # 价格间隔的扩大倍数 (越后面间隔越宽)
            size_factor: float = 1.25,  # 加仓倍数 (1.25倍投)
            leverage: int = 7,
            # --- 新增参数 ---
            tp_pct: float = 0.016,  # 目标止盈率 (1.2%)止盈目标 (1%)
            sl_pct: float = 0.03,  # 硬止损率 (3%) - 必须设置！
    ):
        self.total_value_usdt = total_value_usdt
        self.entry_offset_pct = entry_offset_pct
        self.max_orders = max_orders
        self.step_pct = step_pct
        self.step_factor = step_factor
        self.size_factor = size_factor
        self.leverage = leverage
        # 新增变量存储
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct

    def build_orders(self, current_price: float):
        """
        [改进]：支持起始价格偏移。
        """
        orders = []
        n = self.max_orders + 1  # 总共需要的单数
        r = self.size_factor
        # 起始价：现价上涨 offset 后才开始第一单
        first_entry_price = current_price * (1 + self.entry_offset_pct)
        # --- 核心：反推初始单金额 ---
        actual_total_notional = self.total_value_usdt * self.leverage
        if r == 1:
            initial_base = actual_total_notional / n
        else:
            # 等比数列求和公式：S = a(1-r^n)/(1-r) -> a = S(1-r)/(1-r^n)
            initial_base = actual_total_notional * (1 - r) / (1 - r ** n)

        logger.info(f"📊 预算拆分：保证金预算 {self.total_value_usdt}U |杠杆{self.leverage}倍| 对应总仓位: {actual_total_notional:.2f}U | 初始首单推算为: {initial_base:.2f}U")
        cumulative_step_pct = 0.0
        current_order_value = initial_base

        for i in range(self.max_orders + 1):
            if i == 0:
                price = first_entry_price
            else:
                # 动态差价计算
                this_step = self.step_pct * (self.step_factor ** (i - 1))
                cumulative_step_pct += this_step
                price = first_entry_price * (1 + cumulative_step_pct)
                # 动态金额计算
                current_order_value *= self.size_factor

            orders.append({
                "index": i,
                "price": round(price, 6),
                "target_usdt": current_order_value,
                "coin_size": current_order_value / price  # 临时参考
            })
        return orders

    def audit_orders(
            self,
            orders: list[dict],
            current_price: float,  # 用于计算拉升幅度
            ct_val: float,  # 每张合约代表多少币 (OKX 获取)
            lot_sz: float,  # 最小下单张数 (OKX 获取)
            avail_usdt: float,  # 账户可用 USDT
    ):
        """
        🔥 工业级审核：USDT 价值本位 + 详细日志监控 + 生死风控判断
        """
        total_contracts = 0
        weighted_cost = 0.0
        total_margin_used = 0.0

        logger.info("\n--- 🛡️ 马丁格尔策略风控大检阅 (做空) ---")

        valid_orders = []

        for o in orders:
            # 1. 计算合约张数 (向上取整，确保 base_value 极小时也能下出 1 张)
            # 公式: 币数 / 面值 / 步长 -> 取整 -> 乘以步长
            raw_contracts = o["coin_size"] / ct_val
            contracts = math.floor(raw_contracts / lot_sz) * lot_sz
            min_step_value = lot_sz * ct_val * current_price
            logger.info(f"--- 🛡️ 精度检查 ---")
            logger.info(f"该币种最小交易: {lot_sz} 张 | 最小起始价值: {min_step_value:.2f} USDT")


            # 2. 计算实际价值与保证金
            actual_notional = contracts * ct_val * o["price"]
            # logger.info(f"--- 🛡️ actual_notional{actual_notional} ---")
            margin = actual_notional / self.leverage
            # logger.info(f"--- 🛡️ margin{margin} ---")
            if o["target_usdt"]*self.leverage < min_step_value:
                # 算出如果你想跑这个币，杠杆后至少需要设多少 base_value
                logger.error(f"❌ 策略无法执行！")
                logger.error(f"原因：你设置的 总金额U 不足以买入最小单位({lot_sz}张)。")
                logger.error(f"解决：请将 首单金额 调大至 > {math.floor(min_step_value)}U，或更换面值更小的币种。")
                return None

            # 3. 统计全局数据
            total_contracts += contracts
            weighted_cost += o["price"] * contracts
            total_margin_used += margin

            # 4. 计算该单相对于当前市价的拉升幅度
            delta_pct = (o["price"] - current_price) / current_price * 100
            total_value_usdt = config.config.configpara.total_value_usdt
            if total_margin_used > total_value_usdt:  # 如果总保证金超过了你的心理阈值
                logger.error(f"🚨【预算超支】策略总需 {total_margin_used:.2f}U 保证金，超过了{total_value_usdt:.2f}U 的限制！")
                return None
            # --- 详细日志打印 (保留代码1风格) ---
            logger.info(
                f"#{o['index']} "
                f"[{o.get('type', 'Margin')}] "
                f"挂单价={o['price']:.4f} | "
                f"张数={int(contracts)} | "
                f"价值={actual_notional:.2f}U | "
                f"距现价={delta_pct:+.2f}%"
            )

            # 回写计算好的张数
            o["calc_sz"] = int(contracts)
            valid_orders.append(o)

        if total_contracts == 0:
            logger.error("\n❌ 所有订单计算张数均不足，策略无法启动")
            return None

        # --- 核心风险指标计算 ---
        avg_price = weighted_cost / total_contracts

        # [改进爆仓价]：考虑维持保证金，系数取 0.9 比 1.0 更安全
        liq_price = avg_price * (1 + 0.9 / self.leverage)

        # [改进止损价]：基于本金亏损率计算的价格点
        sl_price = avg_price * (1 + self.sl_pct / self.leverage)

        logger.info("\n--- 🚩 策略压力测试汇总 (假设全成交) ---")
        logger.info(f"总持仓数量: {int(total_contracts)} 张")
        logger.info(f"现在价格: {current_price:.6f} usdt")
        logger.info(f"全仓平均持仓成本: {avg_price:.6f}对比现价上涨{100*(avg_price/current_price-1):.6f}%")
        logger.info(f"预期硬止损价格: {sl_price:.6f} (本金损耗 {self.sl_pct * 100}%)")
        logger.info(f"预估强平爆仓价: {liq_price:.6f}")
        logger.info(f"预计总占用保证金: {total_margin_used:.2f} U")
        logger.info(f"当前账户可用余额: {avail_usdt:.2f} U")

        # --- 🔥 生死判断逻辑 ---
        is_safe = True

        # 1. 资金容量检查
        if total_margin_used > avail_usdt * 0.95:
            logger.error("🚨【致命】总需保证金超过可用余额 95%！请调低 BASE_VALUE 或加仓倍数。")
            is_safe = False

        # 2. 止损逻辑检查 (做空：止损价必须在爆仓价之下)
        elif sl_price >= liq_price:
            logger.error(
                f"🚨【风控拦截】止损价({sl_price:.2f}) >= 爆仓价({liq_price:.2f})！"
                f"这意味着你还没来得及止损就会被强平。请降低杠杆或缩小 SL_PCT。"
            )
            is_safe = False

        # 3. 容错空间评估
        elif liq_price / current_price < 1.03:
            logger.warning("⚠️【极高风险】抗拉升空间不足 3%，极易被市场波动瞬间击穿！")

        else:
            resistance = (liq_price / current_price - 1) * 100
            logger.success(f"✅【审核通过】策略结构健康。最大抗拉升幅度: {resistance:.2f}%")

        if not is_safe:
            return None

        return {
            "avg_price": avg_price,
            "liq_price": liq_price,
            "sl_price": sl_price,
            "margin_used": total_margin_used,
            "total_contracts": total_contracts,
            "orders": valid_orders
        }
    def get_exit_targets(self, avg_price: float):
        """
        [恢复并优化]：计算做空的止盈和止损价格

        逻辑说明：
        1. 止盈：基于价格波动。价格从均价下跌 tp_pct 时触发。
        2. 止损：基于本金风险。价格上涨到让本金亏损 sl_pct 时触发。
        """
        # 做空止盈价格：均价之下
        tp_price = avg_price * (1 - self.tp_pct)

        # 做空止损价格：均价之上
        # 考虑杠杆：实际止损价格位移 = sl_pct / leverage
        sl_price = avg_price * (1 + (self.sl_pct / self.leverage))

        return {
            "tp_price": tp_price,
            "sl_price": sl_price
        }

    def calculate_pnl_pct(self, current_price: float, avg_price: float) -> float:
        """
        [恢复并更名]：计算当前仓位的收益率（PnL %）

        做空逻辑：
        (均价 - 当前价) / 均价 * 杠杆
        例如：均价 100，当前价 110，杠杆 10x -> (100-110)/100 * 10 = -100% (爆仓)
        """
        if avg_price == 0:
            return 0.0

        # 做空收益率公式
        raw_pnl = (avg_price - current_price) / avg_price
        return raw_pnl * self.leverage