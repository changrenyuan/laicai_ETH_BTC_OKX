"""
🧠 策略条件判断
纯逻辑层：计算价差、判断是否满足开仓/平仓标准
"""
import logging

class StrategyConditions:
    def __init__(self, config: dict):
        self.logger = logging.getLogger(__name__)

        strat_cfg = config.get("strategy", {}).get("cash_and_carry", {})
        open_cond = strat_cfg.get("open_conditions", {})
        close_cond = strat_cfg.get("close_conditions", {})

        # 核心阈值
        self.open_spread = float(open_cond.get("spread_threshold", 0.0001)) # 这里其实应该叫 spread_threshold, 先复用你的字段
        self.min_funding_rate = float(open_cond.get("min_funding_rate", 0.0001))

        self.close_spread = float(close_cond.get("spread_threshold", 0.0))

    def should_open(self, spot_price: float, swap_price: float, funding_rate: float) -> bool:
        """
        判断是否开仓
        逻辑：(合约 - 现货) / 现货 > 阈值 且 费率 > 最低要求
        """
        if spot_price <= 0: return False

        spread = swap_price - spot_price
        spread_ratio = spread / spot_price

        # 你的配置里 open_conditions 似乎混用了字段名，这里我们明确逻辑：
        # 我们希望 Spread (价差) 足够大，且 Funding Rate (费率) 是正的

        # 假设 spread 阈值是 0.1% (0.001)
        is_spread_ok = spread_ratio > 0.001
        is_funding_ok = funding_rate > self.min_funding_rate

        if is_spread_ok and is_funding_ok:
            self.logger.info(f"✅ 开仓条件满足: 价差 {spread_ratio:.4%}, 费率 {funding_rate:.4%}")
            return True

        return False

    def should_close(self, spot_price: float, swap_price: float, funding_rate: float) -> bool:
        """
        判断是否平仓
        逻辑：价差回归到 0 或 费率转负
        """
        if spot_price <= 0: return False

        spread = swap_price - spot_price
        spread_ratio = spread / spot_price

        # 平仓：价差极小 或 费率变负
        if spread_ratio <= 0.0005 or funding_rate <= 0:
            self.logger.info(f"✅ 平仓条件满足: 价差 {spread_ratio:.4%}, 费率 {funding_rate:.4%}")
            return True

        return False