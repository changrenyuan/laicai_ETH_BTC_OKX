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
        self.order_manager = components.get("order_manager")  # ✅ 添加 order_manager
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
        """主循环：增加持仓同步步骤"""
        Dashboard.log("⭐⭐⭐ 引擎启动完成，进入主循环 (实时监控模式) ⭐⭐⭐", "SUCCESS")
        print("-" * 80)

        last_status_print = 0
        status_print_intv = 10

        last_position_check = 0
        position_check_intv = 10

        # 新增：持仓同步时间控制
        last_sync_time = 0
        sync_interval = 5  # 每5秒同步一次持仓 (防止无限加仓的关键!)

        while self.is_running:
            try:
                now = time.time()

                # --- 0. 同步交易所持仓 (关键新增!) ---
                # 每次做决策前，必须先看一眼自己兜里到底有啥
                if now - last_sync_time > sync_interval:
                    await self._sync_positions()
                    last_sync_time = now

                # --- 1. 全局风控 ---
                if not await self._global_risk_check():
                    await asyncio.sleep(5)
                    continue

                # --- 2. 市场扫描 ---
                scan_results = []
                market_scan_enabled = self.market_scan_config.get("enabled", False)
                if market_scan_enabled and (now - self.last_scan_time > self.scan_interval):
                    scan_results = await self._market_scan()
                    self.last_scan_time = now

                # --- 3. 市场环境 ---
                if scan_results:
                    await self._regime_detection(scan_results)

                # --- 4. 策略逻辑 ---
                if self.state_machine.get_current_state() == SystemState.MONITORING:

                    # A. 入场
                    entry_signals = await self._strategy_analysis()
                    for signal in entry_signals:
                        await self._process_signal(signal)

                    # B. 离场
                    if now - last_position_check > position_check_intv:
                        exit_signals = await self._manage_positions()
                        for signal in exit_signals:
                            await self._process_signal(signal)
                        last_position_check = now

                # --- 5. 打印状态 ---
                if now - last_status_print > status_print_intv:
                    await self._print_account_status()
                    last_status_print = now

                await asyncio.sleep(1)

            except Exception as e:
                Dashboard.log(f"主循环异常: {e}", "ERROR")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)

    async def _sync_positions(self):
        """从交易所同步最新持仓到 Context (防止无限加仓的关键!)"""
        try:
            # 调用 client 获取持仓
            positions_data = await self.client.get_positions()

            if positions_data:
                valid_symbols = set()

                for p in positions_data:
                    symbol = p.get("instId")
                    quantity = float(p.get("pos", 0))

                    # 只记录有持仓的
                    if quantity != 0:
                        valid_symbols.add(symbol)

                        # 更新 Context
                        self.context.update_position(
                            symbol=symbol,
                            quantity=quantity,
                            avg_price=float(p.get("avgPx", 0)),
                            pnl=float(p.get("upl", 0))
                        )

                # 清理已平仓的持仓 (可选，但为了保持数据一致性建议清理)
                # 这里简单处理：如果 Context 中的 symbol 不在 valid_symbols 中，清空
                for symbol in list(self.context.positions.keys()):
                    if symbol not in valid_symbols:
                        # 创建空持仓
                        self.context.update_position(
                            symbol=symbol,
                            quantity=0,
                            avg_price=0,
                            pnl=0
                        )

                # Dashboard.log(f"🔄 [Sync] 持仓已同步: {len(valid_symbols)} 个活跃持仓", "DEBUG")

        except Exception as e:
            logger.error(f"持仓同步失败: {e}")
            # 暂时忽略网络错误，等待下一次同步

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
        - 🔥 新增：支持加仓（冷却时间机制）

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

                    # 🔥🔥【优化】加仓冷却检查 🔥🔥
                    # 不再因为有持仓就 continue 跳过，而是检查时间间隔
                    current_pos = self.context.get_position(symbol)

                    if current_pos and float(current_pos.quantity) != 0:
                        # 检查是否有最近的交易记录（使用 context.last_trade_time）
                        # 或者可以使用更精细的 per_symbol_cooldown 机制
                        last_trade_time = getattr(self.context, 'last_trade_time', 0)
                        cooldown_period = 900  # 15分钟冷却

                        if (time.time() - last_trade_time) < cooldown_period:
                            # Dashboard.log(f"⏳ {symbol} 处于加仓冷却期 (15min)，跳过", "DEBUG")
                            continue
                        else:
                            Dashboard.log(f"➕ {symbol} 触发加仓逻辑 (冷却期已过)", "INFO")

                    # 调用MultiTrendStrategy的generate_trend_signal方法
                    signal = await multi_trend_strategy.generate_trend_signal(symbol)

                    if signal:
                        # 🔥 新增：检查信号方向是否与持仓方向一致（避免趋势反转时同时开反向单）
                        current_pos = self.context.get_position(symbol)
                        if current_pos and float(current_pos.quantity) != 0:
                            current_is_long = float(current_pos.quantity) > 0
                            signal_is_long = signal.get("side") == "buy"

                            # 如果方向相反，跳过此信号（让离场逻辑处理平仓）
                            if current_is_long != signal_is_long:
                                Dashboard.log(f"⏳ {symbol} 趋势反转检测到，但与持仓方向相反，等待平仓", "DEBUG")
                                continue

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
        - 审计交易信息
        - 调用 OrderManager 执行下单
        - 返回执行结果
        """
        Dashboard.log(f"🔍 [Debug] _execute_trade 被调用，signal 类型: {type(signal)}", "DEBUG")

        # 初始化默认结果，防止异常时 result 未定义
        result = {"success": False, "error": "Unknown error"}

        try:
            # 1. 信号验证
            if not signal:
                Dashboard.log(f"❌ [审计] signal 为空", "ERROR")
                result = {"success": False, "error": "No signal"}
                return result

            if not isinstance(signal, dict):
                Dashboard.log(f"❌ [审计] signal 类型错误: {type(signal)}，期望 dict", "ERROR")
                Dashboard.log(f"❌ [审计] signal 内容: {signal}", "ERROR")
                result = {"success": False, "error": f"Invalid signal type: {type(signal)}"}
                return result

            Dashboard.log(f"✅ [Debug] signal 类型检查通过，开始提取字段", "DEBUG")

            symbol = signal.get("symbol")
            side = signal.get("side")

            if not symbol or not side:
                Dashboard.log(f"❌ [审计] signal 缺少必要字段: symbol={symbol}, side={side}", "ERROR")
                result = {"success": False, "error": "Missing required fields in signal"}
                return result

            # ✅ 修复: 增加 await
            await self.state_machine.transition_to(SystemState.OPENING_POSITION)
            Dashboard.log(f"⚡ [Execution] 开始执行: {symbol} {side}", "INFO")

            # 2. 提取参数（带安全检查）
            size_value = signal.get("size")
            if size_value is None:
                Dashboard.log(f"❌ [审计] signal 缺少 size 字段", "ERROR")
                result = {"success": False, "error": "Missing size in signal"}
                return result

            try:
                size = float(size_value)
            except (ValueError, TypeError) as e:
                Dashboard.log(f"❌ [审计] size 值无效: {size_value}, 错误: {e}", "ERROR")
                result = {"success": False, "error": f"Invalid size: {size_value}"}
                return result

            order_type = signal.get("type", "market")
            price = signal.get("price")
            leverage = signal.get("leverage", 1)
            stop_loss = signal.get("stop_loss")
            take_profit = signal.get("take_profit")
            reduce_only = signal.get("reduce_only", False)  # 🔥 关键修复：提取 reduce_only 参数

            Dashboard.log(f"✅ [Debug] 参数提取完成，开始审计 (reduce_only={reduce_only})", "DEBUG")

            # 3. 交易审计 - 获取当前价格
            ticker = await self.client.get_ticker(symbol)
            if not ticker:
                Dashboard.log(f"❌ [审计] 无法获取 {symbol} 当前价格", "ERROR")
                result = {"success": False, "error": "无法获取当前价格"}
                return result

            # 👇👇👇 修复代码开始 👇👇👇
            # 兼容处理：如果返回是 list，取第一个元素；如果是 dict，直接使用
            if isinstance(ticker, list) and len(ticker) > 0:
                ticker_data = ticker[0]
            elif isinstance(ticker, dict):
                ticker_data = ticker
            else:
                ticker_data = {}

            current_price = float(ticker_data.get("last", 0))
            # 👆👆👆 修复代码结束 👆👆👇

            if current_price == 0:
                Dashboard.log(f"❌ [审计] {symbol} 当前价格无效", "ERROR")
                result = {"success": False, "error": "当前价格无效"}
                return result

            # 计算订单价值
            order_value = current_price * size

            # 计算保证金
            margin = order_value / leverage

            # 获取账户信息计算保证金率
            balance = self.context.get_total_balance()
            margin_ratio = (balance / margin) * 100 if margin > 0 else 9999

            # 计算强平价格（简化公式）
            if side == "buy":
                # 做多：强平价 = 开仓价 * (1 - 1/杠杆 + 维持保证金率)
                maintenance_margin_rate = 0.005  # 假设维持保证金率 0.5%
                liquidation_price = current_price * (1 - 1/leverage + maintenance_margin_rate)
            else:
                # 做空：强平价 = 开仓价 * (1 + 1/杠杆 - 维持保证金率)
                maintenance_margin_rate = 0.005
                liquidation_price = current_price * (1 + 1/leverage - maintenance_margin_rate)

            # 4. 打印审计信息
            Dashboard.log("=" * 80, "INFO")
            Dashboard.log("📋 [交易审计] 订单信息", "INFO")
            Dashboard.log("-" * 80, "INFO")
            Dashboard.log(f"交易对:      {symbol}", "INFO")
            # 交易方向判断（考虑 reduce_only）
            is_reduce_only = signal.get("reduce_only", False)
            if is_reduce_only:
                if side == "sell":
                    direction_str = "平多 (CLOSE LONG)"
                else:  # side == "buy"
                    direction_str = "平空 (CLOSE SHORT)"
            else:
                direction_str = "开多 (LONG)" if side == "buy" else "开空 (SHORT)"

            Dashboard.log(f"交易方向:    {direction_str}", "INFO")
            Dashboard.log(f"当前价格:    {current_price:.6f} USDT", "INFO")
            Dashboard.log(f"交易数量:    {size:.6f}", "INFO")
            Dashboard.log(f"杠杆倍数:    {leverage}x", "INFO")
            Dashboard.log("-" * 80, "INFO")
            Dashboard.log(f"订单价值:    {order_value:.2f} USDT", "INFO")
            Dashboard.log(f"保证金:      {margin:.2f} USDT", "INFO")
            Dashboard.log(f"账户余额:    {balance:.2f} USDT", "INFO")
            Dashboard.log(f"保证金率:    {margin_ratio:.2f}%", "INFO")
            Dashboard.log("-" * 80, "INFO")
            Dashboard.log(f"强平价格:    {liquidation_price:.6f} USDT", "INFO")
            if stop_loss:
                stop_loss_pct = abs((stop_loss - current_price) / current_price) * 100
                Dashboard.log(f"止损价格:    {stop_loss:.6f} USDT (止损 {stop_loss_pct:.2f}%)", "INFO")
            else:
                Dashboard.log(f"止损价格:    未设置", "INFO")
            if take_profit:
                take_profit_pct = abs((take_profit - current_price) / current_price) * 100
                Dashboard.log(f"止盈价格:    {take_profit:.6f} USDT (止盈 {take_profit_pct:.2f}%)", "INFO")
            else:
                Dashboard.log(f"止盈价格:    未设置", "INFO")
            Dashboard.log("=" * 80, "INFO")

            # 5. 处理网格批量订单
            if "orders" in signal and isinstance(signal["orders"], list):
                # ✅ 检查 order_manager 是否存在
                if not hasattr(self, 'order_manager') or not self.order_manager:
                    Dashboard.log(f"❌ [Execution] OrderManager 未初始化", "ERROR")
                    result = {"success": False, "error": "OrderManager 未初始化"}
                    return result

                logger.info(f"⚡ 执行批量挂单 ({len(signal['orders'])} 笔)...")
                success_count = 0
                last_error = ""
                for order in signal["orders"]:
                    # 👇 适配新的返回值 (3个变量)
                    ok, _, err = await self.order_manager.submit_single_order(
                        symbol=order["symbol"],
                        side=order["side"],
                        size=float(order["size"]),
                        order_type=order["type"],
                        price=order.get("price")
                    )
                    if ok:
                        success_count += 1
                    else:
                        last_error = err  # 记录最后一个错误

                    if success_count % 10 == 0: await asyncio.sleep(0.1)

                result = {
                    "success": success_count > 0,
                    "message": f"挂单 {success_count} 笔",
                    "error_msg": last_error if success_count == 0 else ""  # 如果全部失败，返回错误
                }

            # 6. 处理普通单腿订单
            else:
                # ✅ 检查 order_manager 是否存在
                if not hasattr(self, 'order_manager') or not self.order_manager:
                    Dashboard.log(f"❌ [Execution] OrderManager 未初始化", "ERROR")
                    result = {"success": False, "error": "OrderManager 未初始化"}
                    return result

                Dashboard.log(f"✅ [Debug] 开始执行普通单腿订单 (含止盈止损)", "DEBUG")

                # 👇👇👇 修改调用，传入 stop_loss、take_profit 和 reduce_only 👇👇👇
                success, order_id, error_msg = await self.order_manager.submit_single_order(
                    symbol=symbol,
                    side=side,
                    size=size,
                    order_type=order_type,
                    price=price,
                    stop_loss=stop_loss,     # 🔥 传入止损
                    take_profit=take_profit, # 🔥 传入止盈
                    reduce_only=reduce_only  # 🔥 传入平仓标记
                )
                result = {"success": success, "order_id": order_id, "error_msg": error_msg}

            # 7. 结果处理
            if result["success"]:
                Dashboard.log(f"✅ [Execution] 订单提交成功", "SUCCESS")
            else:
                # 👇 这里现在能打印出真正的错误了
                error_detail = result.get('error_msg', 'Unknown')
                Dashboard.log(f"❌ [Execution] 订单提交失败: {error_detail}", "ERROR")
                result["error"] = error_detail

        except Exception as e:
            logger.error(traceback.format_exc())
            Dashboard.log(f"❌ [Execution] 交易异常: {e}", "ERROR")
            result = {"success": False, "error": str(e)}

        finally:
            # ✅ 修复：确保无论成功或失败，都切回 MONITORING 状态
            # 但如果已经在 ERROR 状态，就不要切换
            if not self.state_machine.is_in_state(SystemState.ERROR):
                await self.state_machine.transition_to(SystemState.MONITORING, reason="交易完成")

        # 🔑 核心修复：无论是否异常，都返回 result
        return result
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

    async def _print_account_status(self):
        """打印账户状态 (替代原来的 heartbeat)"""
        active_positions = [p for p in self.context.positions.values() if float(p.quantity) != 0]

        status_msg = (
            f"💓 [状态] {self.state_machine.get_current_state().value} | "
            f"保证金: {self.context.margin_ratio:.2f}% | "
            f"持仓数: {len(active_positions)}"
        )

        if self.context.selected_symbol:
            status_msg += f" | 市场: {self.context.selected_symbol} ({self.context.market_regime})"

        Dashboard.log(status_msg, "INFO")

        # 打印持仓详情
        if active_positions:
            for pos in active_positions:
                side_str = "多" if pos.side == "long" else "空"
                pnl_str = f"{pos.unrealized_pnl:+.2f}" if pos.unrealized_pnl != 0 else "0.00"
                Dashboard.log(
                    f"   📊 {pos.symbol} {side_str} {pos.quantity:.4f} | "
                    f"入场价: {pos.entry_price:.6f} | 浮动盈亏: {pnl_str} USDT",
                    "DEBUG"
                )

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

    # -------------------------------------------------------------------------
    # 🔥 新增：持仓管理和信号处理方法
    # -------------------------------------------------------------------------

    async def _manage_positions(self) -> list:
        """
        【11】持仓管理 (Exit Strategy)
        遍历当前所有持仓，调用策略判断是否需要平仓
        """
        exit_signals = []
        try:
            # 获取当前所有持仓符号
            # 假设 context.positions 是一个字典 {symbol: PositionObject}
            # 如果没有直接属性，尝试从 context.get_all_positions() 获取
            positions = []
            if hasattr(self.context, "get_all_positions"):
                positions = self.context.get_all_positions()
            elif hasattr(self.context, "positions"):
                positions = list(self.context.positions.values())
            elif hasattr(self.context, "active_signals"):
                # 从活跃信号中提取持仓符号
                for symbol, signal in self.context.active_signals.items():
                    pos = self.context.get_position(symbol)
                    if pos and float(pos.quantity) != 0:
                        positions.append(pos)

            if not positions:
                return []

            for pos in positions:
                # 跳过空仓位
                if float(pos.quantity) == 0:
                    continue

                symbol = pos.symbol

                # 🔥 关键修复：再次确认持仓（防止持仓同步延迟导致误判）
                fresh_pos = self.context.get_position(symbol)
                if not fresh_pos or float(fresh_pos.quantity) == 0:
                    Dashboard.log(f"⏳ {symbol} 持仓已清空，跳过评估", "DEBUG")
                    continue

                # 调用策略评估 (使用上一轮更新过的 evaluate_position，含趋势检测)
                # 注意：这里直接调用 strategy 实例的方法
                if hasattr(self.strategy, "evaluate_position"):
                    result = await self.strategy.evaluate_position(symbol)

                    if result and result.get("action") == "close":
                        Dashboard.log(f"🚨 [离场信号] {symbol}: {result.get('reason')}", "WARNING")

                        # 生成平仓信号
                        # 获取持仓方向，平仓则是反向
                        # 假设 pos.quantity > 0 是多头，平仓则卖出
                        is_long = float(pos.quantity) > 0
                        side = "sell" if is_long else "buy"

                        exit_signal = {
                            "symbol": symbol,
                            "side": side,
                            "type": "market",
                            "size": abs(float(pos.quantity)),  # 全平
                            "reduce_only": True,
                            "reason": f"Exit: {result.get('reason')}",
                            "is_exit": True  # 标记为离场单
                        }
                        exit_signals.append(exit_signal)

        except Exception as e:
            logger.error(f"持仓巡检失败: {e}")

        return exit_signals

    async def _process_signal(self, signal: Dict):
        """
        统一处理信号（风控 -> 执行 -> 更新）
        抽离出来供 入场 和 离场 共用
        """
        # --- 【11】风控审批 (Risk Approval) ---
        approval = await self._risk_approval(signal)

        if approval.get("approved", False):
            # --- 【12】执行 (Execution) ---
            execution_result = await self._execute_trade(signal, approval)

            if execution_result:
                # --- 【13】更新 Context ---
                await self._update_context(signal, execution_result)

                # --- 【14】Analytics (分析) ---
                await self._analytics(signal, execution_result)
        else:
            Dashboard.log(f"🛡️ [风控] 拒绝交易: {approval.get('reason')}", "WARNING")
