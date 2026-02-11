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

# 新增：导入 Scanner 和 Regime Detector
from scanner.market_scanner import MarketScanner
from strategy.regime_detector import RegimeDetector
from strategy.strategy_manager import StrategyManager
# 新增：导入 Market Data Fetcher
from exchange.market_data import MarketDataFetcher

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

        # 1.5 组装市场数据层
        market_data_fetcher = MarketDataFetcher(client, cfg)
        self.components["market_data_fetcher"] = market_data_fetcher
        
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

        # 5. 组装市场扫描层（Scanner + Regime Detector）
        market_scan_config = cfg.get("market_scan", {})
        regime_config = cfg.get("regime", {})
        # print(f"DEBUG: market_scan_config = {market_scan_config}")
        if market_scan_config.get("enabled", False):
            try:
                # 创建 Regime Detector
                regime_detector = RegimeDetector(regime_config)
                self.components["regime_detector"] = regime_detector
                Dashboard.log("✅ Regime Detector 注册成功", "SUCCESS")

                # 创建 Market Scanner
                market_scanner = MarketScanner(
                    client=client,
                    market_data_fetcher=self.components["market_data_fetcher"] if "market_data_fetcher" in self.components else None,
                    config=market_scan_config,
                    regime_detector=regime_detector
                )
                self.components["market_scanner"] = market_scanner
                Dashboard.log("✅ Market Scanner 注册成功", "SUCCESS")
                strategy_manager = StrategyManager(cfg, ctx, sm, order_manager, bus)
                self.components["strategy_manager"] = strategy_manager
                Dashboard.log("✅ Strategy manager 注册成功", "SUCCESS")

            except Exception as e:
                logger.error(f"注册 Scanner 或 Regime Detector 失败: {e}")
                traceback.print_exc()
                Dashboard.log(f"⚠️ Scanner 或 Regime Detector 注册失败，继续运行但市场扫描功能将不可用", "WARNING")
        else:
            Dashboard.log("⚠️ 市场扫描功能未开启 (market_scan.enabled = false)", "INFO")
