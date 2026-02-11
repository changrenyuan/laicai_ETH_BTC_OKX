from .cash_and_carry import CashAndCarryStrategy
from .futures_grid import FuturesGridStrategy
from .trend_strategy import TrendRollStrategy  # 🔥 新增导入
def StrategyFactory(strategy_name, config, context, state_machine, order_manager, **kwargs):
    """
    策略工厂：根据名称返回对应的策略实例
    """
    if strategy_name == "futures_grid":
        return FuturesGridStrategy(config, context, state_machine, order_manager, **kwargs)
    
    elif strategy_name == "cash_and_carry":
        # 注意：这里需要确保 CashAndCarry 也适配了 BaseStrategy 的参数
        # 如果还没改，暂时需要手动适配
        return CashAndCarryStrategy(config, context, state_machine, order_manager, kwargs.get('margin_guard'))
    elif strategy_name == "trend_strategy":  # 🔥 新增判断分支
        # 实例化趋势滚仓策略
        return TrendRollStrategy(config, context, state_machine, order_manager, **kwargs)
    else:
        raise ValueError(f"未知策略名称: {strategy_name}")