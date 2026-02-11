"""
🔄 Runtime Phase - 核心循环
================================
完整的交易流程：
Scanner → Regime → Strategy → Portfolio → Risk → Execution → Analytics
"""

import time
import asyncio
import logging
import traceback
from typing import Dict, Optional

from core.context import Context
from core.state_machine import SystemState
from monitor.dashboard import Dashboard

logger = logging.getLogger("Runtime")


class Runtime:
    """Runtime 生命周期阶段 - 主循环"""

    def __init__(self, components: Dict, strategy, config: Dict):
        self.components = components
        self.strategy = strategy
        self.config = config
        self.is_running = True
        # self.logger = logging.getLogger("Runtime")
        # 提取组件
        self.context: Context = components["context"]
        self.state_machine = components["state_machine"]
        self.client = components["client"]
        self.circuit_breaker = components["circuit_breaker"]
        self.exchange_guard = components["exchange_guard"]
        self.margin_guard = components["margin_guard"]
        self.risk_manager = components.get("risk_manager")
        self.strategy_manager = components.get("strategy_manager")
        # 可选组件（如果已加载）
        self.market_scanner = components.get("market_scanner")
        self.regime_detector = components.get("regime_detector")

        # 配置
        self.market_scan_config = config.get("market_scan", {})
        self.regime_config = config.get("regime", {})

        # 扫描控制
        self.last_scan_time = 0
        self.scan_interval = self.market_scan_config.get("scan_interval", 60)

    async def run(self):
        """启动状态机 & 进入主循环"""
        # Phase 7: 启动状态机
        await self._start_state_machine()

        # Phase 8: 主循环
        await self._main_loop()

    async def _start_state_machine(self):
        """启动状态机"""
        Dashboard.log("【7】启动状态机...", "INFO")
        sm = self.state_machine

        # 初始化状态转换：IDLE -> INITIALIZING -> READY -> MONITORING
        if sm.get_current_state() == SystemState.IDLE:
            await sm.transition_to(SystemState.INITIALIZING, reason="初始化组件")
            await sm.transition_to(SystemState.READY, reason="组件就绪")
            await sm.transition_to(SystemState.MONITORING, reason="系统启动")
            Dashboard.log("✅ 状态机已启动，当前状态: MONITORING", "SUCCESS")
        else:
            Dashboard.log(f"⚠️ 状态机已在运行: {sm.get_current_state().value}", "WARNING")

    async def _main_loop(self):
        """
        主循环：严格执行完整流程
        【8】市场扫描 → 【9】Regime 检测 → 【10】策略判断 → 【11】风控审批 → 【12】执行 → 【13】更新 Context → 【14】Analytics
        """
        Dashboard.log("⭐⭐⭐ 引擎启动完成，进入主循环 ⭐⭐⭐", "SUCCESS")
        print("-" * 80)

        last_heartbeat = 0
        heartbeat_intv = 5

        while self.is_running:
            try:
                now = time.time()

                # --- 全局风控检查 ---
                if not await self._global_risk_check():
                    await asyncio.sleep(5)
                    continue

                # --- 【8】市场扫描 (Scanner) ---
                scan_results = []
                market_scan_enabled = self.market_scan_config.get("enabled", False)
                # print(market_scan_enabled)
                if market_scan_enabled and (now - self.last_scan_time > self.scan_interval):
                    scan_results = await self._market_scan()
                    self.last_scan_time = now

                # --- 【9】市场环境检测 (Regime Detection) ---
                if scan_results:
                    await self._regime_detection(scan_results)

                # --- 【10】策略判断 (Strategy) ---
                # 只有在监控状态下才接受新信号
                if self.state_machine.get_current_state() == SystemState.MONITORING:
                    signals = await self._strategy_analysis()

                    if signals:
                        for signal in signals:
                            # --- 【11】风控审批 (Risk Approval) ---
                            approval = await self._risk_approval(signal)

                            if approval.get("approved", False):
                                # --- 【12】执行 (Execution) ---
                                execution_result = await self._execute_trade(signal, approval)

                                # --- 【13】更新 Context ---
                                await self._update_context(signal, execution_result)

                                # --- 【14】Analytics (分析) ---
                                await self._analytics(signal, execution_result)

                                # --- 恢复状态 ---
                                if not self.state_machine.is_in_state(SystemState.ERROR):
                                    await self.state_machine.transition_to(SystemState.MONITORING, reason="交易完成")
                            else:
                                Dashboard.log(f"🛡️ [风控] 拒绝交易: {approval.get('reason')}", "WARNING")

                # 心跳维持
                if now - last_heartbeat > heartbeat_intv:
                    self._print_heartbeat()
                    last_heartbeat = now

                await asyncio.sleep(1)

            except Exception as e:
                Dashboard.log(f"主循环异常: {e}", "ERROR")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)

    async def _global_risk_check(self) -> bool:
        """全局风险检查"""
        # 熔断检查
        if self.circuit_breaker.is_triggered():
            Dashboard.log("🚫 [熔断] 系统熔断中，暂停交易...", "WARNING")
            return False

        # 交易所连接检查
        if not self.exchange_guard.is_healthy():
            Dashboard.log("⚠️ [API] 交易所连接不稳定...", "WARNING")
            return False

        # 保证金检查
        await self.margin_guard.check_margin_ratio(self.context)
        if self.context.margin_ratio < 1.5:
            Dashboard.log(f"🚨 [保证金] 保证金率过低: {self.context.margin_ratio:.2f}%", "ERROR")
            await self.state_machine.transition_to(SystemState.ERROR, reason="保证金不足")
            return False

        return True

    async def _market_scan(self):
        """
        【8】市场扫描 (Scanner)
        - 拉行情 / K 线（D / 4H / 15m / 3m）
        - 初筛标的（流动性 / 交易额 / 涨跌幅度、ADX、波动率扩张、价格分布、量价结构）
        - 生成候选列表
        """
        try:
            Dashboard.log("📡 [Scanner] 开始市场扫描...", "INFO")

            if not self.market_scanner:
                Dashboard.log("⚠️ [Scanner] 市场扫描器未加载", "WARNING")
                return []

            # 执行扫描
            scan_results = await self.market_scanner.scan()

            # 更新 Context
            self.context.update_scan_results([r.to_dict() for r in scan_results])

            # 显示扫描结果
            Dashboard.print_scan_results(scan_results)

            return scan_results

        except Exception as e:
            Dashboard.log(f"❌ [Scanner] 市场扫描失败: {e}", "ERROR")
            logger.error(traceback.format_exc())
            return []

    async def _regime_detection(self, scan_results):
        """
        【9】市场环境检测 (Regime Detection)
        - 识别市场环境：TREND / RANGE / CHAOS
        - 根据市场环境选择策略
        """
        try:
            Dashboard.log("🌊 [Regime] 开始市场环境检测...", "INFO")

            if not scan_results:
                Dashboard.log("⚠️ [Regime] 无扫描结果", "WARNING")
                return

            # 扫描结果已经包含了 regime 信息（在 market_scanner 中已计算）
            # 这里只需要选择最佳候选并更新 Context
            best_candidate = max(scan_results, key=lambda x: x.score)

            # 更新 Context
            self.context.selected_symbol = best_candidate.symbol
            self.context.market_regime = best_candidate.regime

            # 显示市场环境
            Dashboard.print_regime_analysis(best_candidate)

        except Exception as e:
            Dashboard.log(f"❌ [Regime] 市场环境检测失败: {e}", "ERROR")
            logger.error(traceback.format_exc())

    async def _strategy_analysis(self) -> list:
        """
        【10】策略判断 (Strategy)
        - 根据市场环境生成策略信号
        - 返回信号列表

        注意：这里支持多策略模式：
        1. 如果是multi_trend策略，遍历所有扫描结果生成信号
        2. 其他策略保持原有逻辑
        """
        try:
            signals = []

            # 获取当前活动策略
            active_strategy = self.config.get("active_strategy", "")

            # 执行市场扫描
            scan_results = await self._market_scan()

            if not scan_results:
                return signals

            # 如果是multi_trend策略，遍历所有扫描结果生成信号
            if active_strategy == "multi_trend":
                # 获取策略实例
                multi_trend_strategy = self.strategy

                # 遍历所有扫描结果
                for candidate in scan_results:
                    symbol = candidate.symbol
                    regime = candidate.regime

                    # 只处理TREND环境
                    if regime != "TREND":
                        continue

                    # 调用MultiTrendStrategy的generate_trend_signal方法
                    signal = await multi_trend_strategy.generate_trend_signal(symbol)

                    if signal:
                        # 注入regime信息
                        signal['regime'] = regime
                        signal['strategy'] = 'multi_trend'
                        signals.append(signal)
                        self.context.add_strategy_signal(signal)
                        Dashboard.log(f"🎯 [Strategy] 检测到交易信号: {symbol} {signal.get('side')} {signal.get('reason', '')}", "INFO")

            else:
                # 其他策略保持原有逻辑
                for candidate in scan_results:
                    symbol = candidate.symbol
                    regime = candidate.regime
                    # 调用策略的 analyze_signal 方法
                    signal = await self.strategy_manager.generate(symbol, regime)

                    if signal:
                        signals.append(signal)
                        self.context.add_strategy_signal(signal)
                        Dashboard.log(f"🎯 [Strategy] 检测到交易信号: {signal.get('reason', '')}", "INFO")

            return signals

        except Exception as e:
            Dashboard.log(f"❌ [Strategy] 策略分析失败: {e}", "ERROR")
            logger.error(traceback.format_exc())
            return []

    async def _risk_approval(self, signal: Dict) -> Dict:
        """
        【11】风控审批 (Risk Engine)
        ❌ 严禁硬编码 return True
        ✅ 必须调用 risk_manager 进行实质性检查
        """
        if not self.risk_manager:
            logger.critical("🚨 严重错误: RiskManager 未初始化，为了安全拒绝所有交易！")
            return {"approved": False, "reason": "RiskManager missing"}

        try:
            logger.info(f"🛡️ [风控] 正在审计信号: {signal.get('symbol')} {signal.get('side')}")

            # 调用风控模块的检查方法
            # 注意：请确认 risk/__init__.py 中 RiskManager 的入口方法名
            # 通常是 check_order 或 approve

            approval_result = None

            # 尝试调用 check_order (常见命名)
            if hasattr(self.risk_manager, 'check_order'):
                approval_result = await self.risk_manager.check_order(signal)
            # 尝试调用 approve (备用命名)
            elif hasattr(self.risk_manager, 'approve'):
                approval_result = await self.risk_manager.approve(signal)
            else:
                logger.error("❌ RiskManager 缺少 check_order 或 approve 方法")
                return {"approved": False, "reason": "Method missing"}

            # 处理风控返回结果
            # 假设返回结构是 {"approved": bool, "modified_size": float, "reason": str}
            # 或者直接返回 bool

            if isinstance(approval_result, bool):
                is_approved = approval_result
                reason = "Boolean return"
                modified_size = signal.get("size")
            elif isinstance(approval_result, dict):
                is_approved = approval_result.get("approved", False)
                reason = approval_result.get("reason", "")
                modified_size = approval_result.get("modified_size", signal.get("size"))
            else:
                is_approved = False
                reason = f"Unknown return type: {type(approval_result)}"
                modified_size = 0

            if is_approved:
                logger.info(f"✅ [风控] 审批通过 (Size: {modified_size})")
                return {"approved": True, "modified_size": modified_size}
            else:
                logger.warning(f"🛑 [风控] 拒绝交易: {reason}")
                return {"approved": False, "reason": reason}

        except Exception as e:
            logger.error(f"❌ 风控审批过程发生异常: {e}")
            logger.error(traceback.format_exc())
            # 发生异常时，为了安全，必须拒绝！
            return {"approved": False, "reason": f"Exception: {e}"}
    async def _execute_trade(self, signal: Dict, approval: Optional[Dict] = None):
        """
        【12】执行交易 (Execution)
        - 调用 OrderManager 执行下单
        """
        if not signal: return

        symbol = signal.get("symbol")
        side = signal.get("side")

        # ✅ 修复: 增加 await
        await self.state_machine.transition_to(SystemState.OPENING_POSITION)
        Dashboard.log(f"⚡ [Execution] 开始执行: {symbol} {side}", "INFO")

        try:
            # 1. 提取参数
            size = float(signal.get("size", 0))
            order_type = signal.get("type", "market")
            price = signal.get("price")

            # 2. 处理网格批量订单
            if "orders" in signal and isinstance(signal["orders"], list):
                self.logger.info(f"⚡ 执行批量挂单 ({len(signal['orders'])} 笔)...")
                success_count = 0
                for order in signal["orders"]:
                    ok, _ = await self.order_manager.submit_single_order(
                        symbol=order["symbol"],
                        side=order["side"],
                        size=float(order["size"]),
                        order_type=order["type"],
                        price=order.get("price")
                    )
                    if ok: success_count += 1
                    # 适当延时防止限频
                    if success_count % 10 == 0: await asyncio.sleep(0.1)

                result = {"success": success_count > 0, "message": f"挂单 {success_count} 笔"}

            # 3. 处理普通单腿订单
            else:
                success, order_id = await self.order_manager.submit_single_order(
                    symbol=symbol,
                    side=side,
                    size=size,
                    order_type=order_type,
                    price=price
                )
                result = {"success": success, "order_id": order_id}

            # 4. 结果处理
            if result["success"]:
                Dashboard.log(f"✅ 交易成功", "SUCCESS")
                self._update_context(signal, result)
            else:
                Dashboard.log(f"❌ 交易失败: {result.get('error_msg', 'Unknown')}", "ERROR")

        except Exception as e:
            self.logger.error(traceback.format_exc())
            # ✅ 修复: 增加 await
            await self.state_machine.transition_to(SystemState.ERROR)

        finally:
            # ✅ 修复: 增加 await
            await self.state_machine.transition_to(SystemState.MONITORING)
    async def _update_context(self, signal: Dict, execution_result: Dict):
        """
        【13】更新 Context
        - 更新持仓信息
        - 更新 PnL
        - 记录交易历史
        """
        try:
            if execution_result.get("success"):
                self.context.last_trade_time = time.time()

                # 记录交易
                trade_record = {
                    "timestamp": time.time(),
                    "signal": signal,
                    "execution": execution_result,
                }
                self.context.trade_history.append(trade_record)

                Dashboard.log(f"✅ [Context] Context 已更新", "SUCCESS")
            else:
                Dashboard.log(f"⚠️ [Context] 交易失败，Context 未更新", "WARNING")

        except Exception as e:
            Dashboard.log(f"❌ [Context] 更新失败: {e}", "ERROR")

    async def _analytics(self, signal: Dict, execution_result: Dict):
        """
        【14】Analytics (分析)
        - 统计胜率
        - 计算盈亏
        - 生成报告
        """
        try:
            if execution_result.get("success"):
                # 更新系统指标
                self.context.metrics.total_trades += 1
                self.context.metrics.daily_trades += 1

                Dashboard.log(f"📊 [Analytics] 交易已记录", "INFO")

        except Exception as e:
            Dashboard.log(f"❌ [Analytics] 分析失败: {e}", "ERROR")

    def _print_heartbeat(self):
        """打印心跳信息"""
        if self.context.selected_symbol:
            Dashboard.log(
                f"💓 [Heartbeat] 状态: {self.state_machine.get_current_state().value} | "
                f"交易对: {self.context.selected_symbol} | "
                f"环境: {self.context.market_regime} | "
                f"保证金: {self.context.margin_ratio:.2f}%",
                "INFO"
            )
        else:
            Dashboard.log(
                f"💓 [Heartbeat] 状态: {self.state_machine.get_current_state().value} | "
                f"保证金: {self.context.margin_ratio:.2f}%",
                "INFO"
            )
