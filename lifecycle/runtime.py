"""
🔄 Runtime Phase
启动状态机 & 主循环
"""

import time
import asyncio
import logging
import traceback
from typing import Dict

from core.context import Context
from core.state_machine import SystemState
from monitor.dashboard import Dashboard

logger = logging.getLogger("Orchestrator")


class Runtime:
    """Runtime 生命周期阶段 - 主循环"""
    
    def __init__(self, components: Dict, strategy):
        self.components = components
        self.strategy = strategy
        self.is_running = True
    
    async def run(self):
        """启动状态机 & 进入主循环"""
        # Phase 7: 启动状态机
        await self._start_state_machine()
        
        # Phase 8: 主循环
        await self._main_loop()
    
    async def _start_state_machine(self):
        """启动状态机"""
        Dashboard.log("【7】启动状态机...", "INFO")
        sm = self.components["state_machine"]
        
        # 初始化状态转换：IDLE -> INITIALIZING -> READY -> MONITORING
        if sm.get_current_state() == SystemState.IDLE:
            await sm.transition_to(SystemState.INITIALIZING, reason="初始化组件")
            await sm.transition_to(SystemState.READY, reason="组件就绪")
            await sm.transition_to(SystemState.MONITORING, reason="系统启动")
            Dashboard.log("✅ 状态机已启动，当前状态: MONITORING", "SUCCESS")
        else:
            Dashboard.log(f"⚠️ 状态机已在运行", "WARNING")
    
    async def _main_loop(self):
        """主循环"""
        Dashboard.log("⭐⭐⭐ 引擎启动完成，进入主循环 ⭐⭐⭐", "SUCCESS")
        print("-" * 80)
        
        circuit = self.components["circuit_breaker"]
        ex_guard = self.components["exchange_guard"]
        margin_guard = self.components["margin_guard"]
        context = self.components["context"]
        sm = self.components["state_machine"]
        
        last_heartbeat = 0
        heartbeat_intv = 5
        last_scan_time = 0
        scan_interval = 60
        
        while self.is_running:
            try:
                now = time.time()
                
                # 全局风控检查
                if circuit.is_triggered():
                    Dashboard.log("🚫 [熔断] 系统熔断中，暂停交易...", "WARNING")
                    await asyncio.sleep(5)
                    continue
                
                if not ex_guard.is_healthy():
                    Dashboard.log("⚠️ [API] 交易所连接不稳定...", "WARNING")
                    await asyncio.sleep(5)
                    continue
                
                # 保证金检查
                await margin_guard.check_margin_ratio(context)
                if context.margin_ratio < 1.5:
                    Dashboard.log(f"🚨 [保证金] 保证金率过低: {context.margin_ratio:.2f}%", "ERROR")
                    await sm.transition_to(SystemState.ERROR, reason="保证金不足")
                
                # 市场扫描
                if now - last_scan_time > scan_interval:
                    Dashboard.log("📡 [扫描] 开始市场扫描...", "INFO")
                    await self._scan_market(context)
                    last_scan_time = now
                
                # 策略信号判断
                if sm.get_current_state() == SystemState.MONITORING:
                    signal = await self.strategy.analyze_signal()
                    if signal:
                        Dashboard.log(f"🎯 [信号] 检测到交易信号", "INFO")
                
                # 心跳
                if now - last_heartbeat > heartbeat_intv:
                    self._print_heartbeat()
                    last_heartbeat = now
                
                await asyncio.sleep(1)
                
            except Exception as e:
                Dashboard.log(f"主循环异常: {e}", "ERROR")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)
    
    async def _scan_market(self, context: Context):
        """市场扫描"""
        try:
            client = self.components["client"]
            periods = ["1D", "4H", "15m"]
            market_data = {}
            
            for period in periods:
                if hasattr(client, 'get_candlesticks'):
                    klines = await client.get_candlesticks(self.strategy.symbol, bar=period, limit=50)
                    if klines:
                        market_data[period] = klines
                        logger.debug(f"获取 {period} K线成功: {len(klines)} 条")
            
            context.market_snapshot = market_data
            context.last_scan_time = time.time()
            
            ticker = await client.get_ticker(self.strategy.symbol)
            if ticker:
                context.liquidity_depth = float(ticker[0].get('askSz', 0))
            
            Dashboard.log(f"✅ [扫描] 市场扫描完成，流动性深度: {context.liquidity_depth:.2f}", "SUCCESS")
            
        except Exception as e:
            logger.error(f"市场扫描失败: {e}")
            Dashboard.log(f"⚠️ [扫描] 市场扫描异常: {e}", "WARNING")
    
    def _print_heartbeat(self):
        """心跳输出"""
        try:
            import datetime
            sm = self.components["state_machine"]
            context = self.components["context"]
            sym = getattr(self.strategy, 'symbol', 'UNKNOWN')
            
            if context and hasattr(context, 'start_time'):
                uptime = datetime.datetime.now() - context.start_time
                uptime_str = str(uptime).split('.')[0]
            else:
                uptime_str = "N/A"
            
            current_state = sm.get_current_state().value if sm else "N/A"
            
            last_scan = "N/A"
            if context and hasattr(context, 'last_scan_time') and context.last_scan_time > 0:
                seconds_ago = int(time.time() - context.last_scan_time)
                last_scan = f"{seconds_ago}s ago"
            
            heartbeat_info = (
                f"💓 [心跳] 状态: {current_state:15} | "
                f"策略: {sym:20} | "
                f"运行: {uptime_str:15} | "
                f"扫描: {last_scan:10}"
            )
            
            print(f"\r{heartbeat_info}", end="", flush=True)
        except Exception as e:
            print(f"\r💓 [心跳] 系统运行中...", end="", flush=True)
