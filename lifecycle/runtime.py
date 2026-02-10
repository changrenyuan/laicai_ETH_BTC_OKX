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
        """主循环：严格执行流程图【8】-【14】步骤"""
        Dashboard.log("⭐⭐⭐ 引擎启动完成，进入主循环 ⭐⭐⭐", "SUCCESS")
        print("-" * 80)

        # 核心组件解包
        circuit = self.components["circuit_breaker"]
        ex_guard = self.components["exchange_guard"]
        margin_guard = self.components["margin_guard"]
        risk_manager = self.components.get("risk_manager")  # 【10】风控审批
        context = self.components["context"]
        sm = self.components["state_machine"]

        last_heartbeat = 0
        heartbeat_intv = 5
        last_scan_time = 0
        scan_interval = 60  # 扫描频率

        while self.is_running:
            try:
                now = time.time()

                # --- 全局风控检查 ---
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

                # --- 【8】市场扫描 (Scanner) ---
                if now - last_scan_time > scan_interval:
                    Dashboard.log("📡 [扫描] 开始市场扫描...", "INFO")
                    # 执行扫描并捕获快照
                    snapshot = await self._scan_market(context)
                    last_scan_time = now

                # --- 【9】策略判断 (Strategy) ---
                # 只有在监控状态下才接受新信号
                if sm.get_current_state() == SystemState.MONITORING:
                    # 获取策略信号（建议策略返回包含 'reason' 的字典）
                    signal = await self.strategy.analyze_signal()

                    if signal:
                        Dashboard.log(f"🎯 [信号] 检测到交易信号: {signal.get('reason', '触发策略逻辑')}", "INFO")

                        # --- 【10】风控审批 (Risk Approval) ---
                        is_approved = True
                        approval_data = {"reason": "直接通过"}
                        if risk_manager:
                            is_approved, approval_data = await risk_manager.check_order(signal)

                        if is_approved:
                            # --- 【11】执行前状态锁定 ---
                            await sm.transition_to(SystemState.EXECUTING, reason="信号审批通过，冻结新信号")

                            # --- 【12】执行层 (Execution) ---
                            Dashboard.log("⚡ [执行] 正在下达原子订单...", "INFO")
                            exec_res = await self.strategy.execute(signal, approval_data)

                            # --- 【13】更新 Context & PnL ---
                            if exec_res.get("success"):
                                context.last_trade_time = time.time()
                                # 此处可扩展调用 context.update_pnl() 或记录交易日志
                                Dashboard.log(f"✅ [成交] 指令执行成功: {exec_res.get('order_id', '')}", "SUCCESS")
                            else:
                                Dashboard.log(f"❌ [失败] 指令执行失败: {exec_res.get('error')}", "ERROR")

                            # --- 【14】恢复状态 ---
                            await sm.transition_to(SystemState.MONITORING, reason="交易序列处理完成")
                        else:
                            Dashboard.log(f"🛡️ [风控] 拒绝交易: {approval_data.get('reason')}", "WARNING")

                # 心跳维持
                if now - last_heartbeat > heartbeat_intv:
                    self._print_heartbeat()
                    last_heartbeat = now

                await asyncio.sleep(1)

            except Exception as e:
                Dashboard.log(f"主循环异常: {e}", "ERROR")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)
    async def _scan_market(self, context: Context):
        """
        🔍 深度市场扫描
        修改点：将所有 print 替换为 Dashboard.log，并丰富打印内容
        """
        try:
            client = self.components["client"]
            symbol = self.strategy.symbol

            # 1. 获取行情数据 (Ticker & KLines)
            ticker = await client.get_ticker(symbol)
            periods = ["1D", "4H", "15m"]
            market_data = {}
            for period in periods:
                klines = await client.get_candlesticks(symbol, bar=period, limit=50)
                if klines:
                    market_data[period] = klines

            # 2. 获取实时持仓与挂单 (用于看板展示)
            pos = await client.get_positions()
            # 使用通用请求获取当前活跃挂单数量
            pending_orders = await client._request("GET", "/api/v5/trade/orders-pending", params={"instId": symbol})

            # 3. 更新 Context
            context.market_snapshot = market_data
            context.last_scan_time = time.time()

            if ticker:
                t = ticker[0]
                last_price = t.get('last', 'N/A')
                high_24h = t.get('high24h', 'N/A')
                low_24h = t.get('low24h', 'N/A')
                context.liquidity_depth = float(t.get('askSz', 0))

                # 4. 构建硬核看板字符串
                # 我们将信息组合在一起，一次性通过 Dashboard.log 输出
                grid_range = f"{min(self.strategy.grids)} ~ {max(self.strategy.grids)}" if hasattr(self.strategy,
                                                                                                   'grids') and self.strategy.grids else "未计算"

                panel = [
                    f"\n" + "═" * 60,
                    f"📊 实时行情看板 | {symbol}",
                    "─" * 60,
                    f"  当前价格: {last_price:<12} | 24H最高: {high_24h}",
                    f"  网格区间: {grid_range:<12} | 24H最低: {low_24h}",
                    "─" * 60,
                    f"  当前挂单: {len(pending_orders) if pending_orders else 0:<12} | 当前持仓: {len(pos) if pos else 0}",
                    f"  流动性深度: {context.liquidity_depth:<10.2f} | 状态: MONITORING",
                    "═" * 60
                ]

                # 将列表合并为一个大字符串发送给 Dashboard
                Dashboard.log("\n".join(panel), "INFO")
                Dashboard.log(f"✅ [扫描] 深度扫描完成，价格重心: {last_price}", "SUCCESS")

            else:
                Dashboard.log(f"⚠️ [扫描] 无法获取 {symbol} Ticker 数据", "WARNING")

        except Exception as e:
            Dashboard.log(f"❌ [扫描] 过程出错: {str(e)}", "ERROR")
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
