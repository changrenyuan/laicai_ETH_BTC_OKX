def estimate_short_liquidation(avg_price: float, leverage: int):
    """
    极简模型：不考虑维持保证金，只估算理论爆仓线
    """
    liquidation_price = avg_price * (1 + 1 / leverage)
    return liquidation_price
