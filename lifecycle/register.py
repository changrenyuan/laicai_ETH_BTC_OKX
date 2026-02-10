"""
🔧 Register Phase
注册策略 & 风控模块
"""

import logging
import traceback
from typing import Dict

from core.context import Context, Balance
from core.state_machine import StateMachine
from core.events import EventBus

from execution.order_manager import OrderManager
from execution.position_manager import PositionManager

from risk.margin_guard import MarginGuard
from risk.fund_guard import FundGuard
from risk.circuit_breaker import CircuitBreaker
from risk.exchange_guard import ExchangeGuard
from risk.liquidity_guard import LiquidityGuard

from monitor.pnl_tracker import PnLTracker

from strategy import StrategyFactory
from monitor.dashboard import Dashboard

logger = logging.getLogger("Orchestrator")


class Register:
    """Register 生命周期阶段 - 注册模块"""
    
    def __init__(self, config: Dict, components: Dict):
        self.config = config
        self.components = components
        self.strategy = None
    
    async def run(self):
        """注册所有模块"""
        Dashboard.log("【5】注册策略 & 风控模块...", "INFO")
        
        cfg = self.config
        client = self.components["client"]
        ctx = self.components["context"]
        sm = self.components["state_machine"]
        bus = self.components["event_bus"]
        
        # 0. 同步账户余额到 Context
        bal = await client.get_trading_balances()
        if bal and len(bal) > 0:
            details = bal[0]['details']
            for detail in details:
                ccy = detail.get('ccy', 'USDT')
                avail = float(detail.get('availBal', 0))
                frozen = float(detail.get('frozenBal', 0))
                ctx.balances[ccy] = Balance(
                    currency=ccy,
                    available=avail,
                    frozen=frozen,
                    total=avail + frozen
                )
            Dashboard.log(f"✅ 已同步 {len(ctx.balances)} 种货币余额", "SUCCESS")
        
        # 1. 组装执行层
        order_manager = OrderManager(client, sm, bus)
        position_manager = PositionManager(ctx)
        self.components["order_manager"] = order_manager
        self.components["position_manager"] = position_manager
        
        # 2. 组装风控层
        margin_guard = MarginGuard(cfg)
        fund_guard = FundGuard(cfg, client)
        circuit_breaker = CircuitBreaker(cfg)
        exchange_guard = ExchangeGuard(cfg)
        liquidity_guard = LiquidityGuard(cfg)
        
        self.components.update({
            "margin_guard": margin_guard,
            "fund_guard": fund_guard,
            "circuit_breaker": circuit_breaker,
            "exchange_guard": exchange_guard,
            "liquidity_guard": liquidity_guard
        })
        
        # 3. 组装策略层
        active_strat = cfg.get("active_strategy", "futures_grid")
        try:
            strategy = StrategyFactory(
                strategy_name=active_strat,
                config=cfg,
                context=ctx,
                state_machine=sm,
                order_manager=order_manager,
                margin_guard=margin_guard,
                fund_guard=fund_guard
            )
            await strategy.initialize()
            self.strategy = strategy
            Dashboard.log(f"策略 [{active_strat}] 装配完毕。", "SUCCESS")
        except Exception as e:
            logger.error(traceback.format_exc())
            raise RuntimeError(f"策略装配失败: {e}")
        
        # 4. 组装监控层
        pnl_tracker = PnLTracker(cfg)
        self.components["pnl_tracker"] = pnl_tracker
