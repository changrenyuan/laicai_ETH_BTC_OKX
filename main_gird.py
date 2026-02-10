"""
🚀 LAICAI FUNDING ENGINE (MAIN ORCHESTRATOR)
============================================
全自动量化交易系统总入口
遵循 "Titan" 架构设计：只负责生命周期管理，不包含任何业务逻辑。

[流程映射]
Phase 1: Bootstrap (自检)
Phase 2: Config & Init (加载)
Phase 3: Connection (连接)
Phase 4: Context Build (构建)
Phase 5: Assembly (装配)
Phase 6: Scheduler (调度)
Phase 7: StateMachine (启动)
Phase 8: Main Loop (循环)
"""

import asyncio
import sys
import signal
import time
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv
import yaml

# -----------------------------------------------------------------------------
# 1. 环境路径注入
# -----------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv()

# -----------------------------------------------------------------------------
# 2. 模块导入 (严格按层级)
# -----------------------------------------------------------------------------
# Core (内核)
from core.context import Context
from core.state_machine import StateMachine, SystemState
from core.events import EventBus
from core.scheduler import Scheduler

# Exchange (交易所)
from exchange.okx_client import OKXClient

# Risk (风控)
from risk.margin_guard import MarginGuard
from risk.fund_guard import FundGuard
from risk.circuit_breaker import CircuitBreaker
from risk.liquidity_guard import LiquidityGuard
from risk.exchange_guard import ExchangeGuard

# Execution (执行)
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager

# Monitor (监控)
from monitor.pnl_tracker import PnLTracker
from monitor.dashboard import Dashboard

# Strategy (策略工厂)
from strategy import StrategyFactory

# Scripts (运维)
from scripts.bootstrap import run_bootstrap_checks

# -----------------------------------------------------------------------------
# 3. 日志配置 (Log Redirect - 保持控制台干净)
# -----------------------------------------------------------------------------
LOG_DIR = ROOT_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 🔥 修复部分：正确设置 Handler 和 Level
runtime_handler = logging.FileHandler(LOG_DIR / "runtime.log", encoding='utf-8')
runtime_handler.setLevel(logging.INFO)

error_handler = logging.FileHandler(LOG_DIR / "error.log", encoding='utf-8')
error_handler.setLevel(logging.ERROR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[runtime_handler, error_handler]
)

# 强行压制第三方库噪音
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("Orchestrator")


class QuantEngine:
    """
    量化引擎指挥官
    职责：组装组件 -> 建立连接 -> 启动循环 -> 安全退出
    """
    def __init__(self):
        self.is_running = True
        self.config = {}
        self.components = {}  # 组件容器
        self.strategy = None  # 当前激活的策略实例

        # 信号注册
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        Dashboard.log("接收到系统中断信号 (SIGINT/SIGTERM)...", "WARNING")
        self.is_running = False

    # =========================================================================
    # Phase 1: 启动前自检
    # =========================================================================
    def phase_1_bootstrap(self):
        Dashboard.print_banner()
        Dashboard.log("【1】启动前自检 (Bootstrap)...", "INFO")

        try:
            if not run_bootstrap_checks(ROOT_DIR):
                Dashboard.log("自检未通过，禁止启动。", "ERROR")
                sys.exit(1)
        except ImportError:
            pass

        Dashboard.log("环境自检通过。", "SUCCESS")

    # =========================================================================
    # Phase 2: 加载配置 & 初始化组件
    # =========================================================================
    def phase_2_load_config(self):
        Dashboard.log("【2】加载配置 & 初始化组件...", "INFO")
        try:
            cfg_path = ROOT_DIR / "config"
            with open(cfg_path / "account.yaml", "r", encoding="utf-8") as f: ac = yaml.safe_load(f)
            with open(cfg_path / "risk.yaml", "r", encoding="utf-8") as f: ri = yaml.safe_load(f)
            with open(cfg_path / "strategy.yaml", "r", encoding="utf-8") as f: st = yaml.safe_load(f)

            self.config = {**ac, **ri, **st}
            Dashboard.log(f"配置加载完成 | 激活策略: [{self.config.get('active_strategy', 'N/A').upper()}]", "SUCCESS")
        except Exception as e:
            Dashboard.log(f"配置文件解析失败: {e}", "ERROR")
            raise e

    # =========================================================================
    # Phase 3: 连接交易所 & 初始状态拉取
    # =========================================================================
    async def phase_3_connect(self):
        Dashboard.log("【3】连接交易所 & 拉取初始状态...", "INFO")

        # 1. 初始化客户端
        client = OKXClient(self.config.get("sub_account"))
        connected = await client.connect()
        if not connected:
            raise ConnectionError("无法连接到 OKX API")

        self.components["client"] = client
        Dashboard.log("交易所 API 连接建立。", "SUCCESS")

        # 2. 拉取账户初始快照 (用于 Dashboard 展示)
        bal = await client.get_trading_balances()
        if bal and len(bal) > 0:
            details = bal[0]['details'][0]
            info = {
                'totalEq': details.get('eq', 0),
                'availBal': details.get('availBal', 0),
                'upl': details.get('upl', 0),
                'mgnRatio': details.get('mgnRatio', 'N/A')
            }
            Dashboard.print_account_overview(info)
        else:
            Dashboard.log("无法获取账户余额，请检查 API 权限。", "WARNING")

    # =========================================================================
    # Phase 4: 构建 Context (系统快照)
    # =========================================================================
    def phase_4_build_context(self):
        Dashboard.log("【4】构建 Context (系统快照)...", "INFO")

        event_bus = EventBus()
        state_machine = StateMachine(event_bus)
        context = Context()

        # 确保初始化必要的属性
        if not hasattr(context, 'liquidity_depth'):
            context.liquidity_depth = 0.0
        if not hasattr(context, 'last_scan_time'):
            context.last_scan_time = 0.0
        if not hasattr(context, 'market_snapshot'):
            context.market_snapshot = {}
        if not hasattr(context, 'last_trade_time'):
            context.last_trade_time = 0.0
        if not hasattr(context, 'trade_history'):
            context.trade_history = []
        if not hasattr(context, 'balances'):
            context.balances = {}

        # 初始化默认余额（USDT），避免空字典错误
        from core.context import Balance
        context.balances["USDT"] = Balance(
            currency="USDT",
            available=0.0,
            frozen=0.0,
            total=0.0
        )

        self.components["event_bus"] = event_bus
        self.components["state_machine"] = state_machine
        self.components["context"] = context

    # =========================================================================
    # Phase 5: 注册策略 & 风控模块 (装配)
    # =========================================================================
    async def phase_5_assembly(self):
        Dashboard.log("【5】注册策略 & 风控模块...", "INFO")

        cfg = self.config
        client = self.components["client"]
        ctx = self.components["context"]
        sm = self.components["state_machine"]
        bus = self.components["event_bus"]

        # 0. 同步账户余额到 Context
        from core.context import Balance
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

        # 2. 组装风控层 (RiskManager)
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

        # 3. 组装策略层 (StrategyManager)
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
            # 策略初始化 (盘前分析、K线拉取、计划生成)
            await strategy.initialize()
            self.strategy = strategy
            Dashboard.log(f"策略 [{active_strat}] 装配完毕。", "SUCCESS")
        except Exception as e:
            logger.error(traceback.format_exc())
            raise RuntimeError(f"策略装配失败: {e}")

    # =========================================================================
    # Phase 6: 启动 Scheduler (调度器)
    # =========================================================================
    async def phase_6_scheduler(self):
        Dashboard.log("【6】启动 Scheduler (调度器)...", "INFO")

        pnl_tracker = PnLTracker(self.config)
        self.components["pnl_tracker"] = pnl_tracker

        scheduler = Scheduler(
            context=self.components["context"],
            fund_guard=self.components["fund_guard"],
            pnl_tracker=pnl_tracker,
            position_manager=self.components["position_manager"]
        )

        await scheduler.start()
        self.components["scheduler"] = scheduler

    # =========================================================================
    # Phase 7: 进入 StateMachine 主循环
    # =========================================================================
    async def phase_7_start_machine(self):
        Dashboard.log("【7】启动状态机...", "INFO")
        sm = self.components["state_machine"]

        # 初始化状态转换：IDLE -> INITIALIZING -> READY -> MONITORING
        current_state = sm.get_current_state()
        if current_state == SystemState.IDLE:
            # 第一步：IDLE -> INITIALIZING
            await sm.transition_to(SystemState.INITIALIZING, reason="初始化组件")
            # 第二步：INITIALIZING -> READY
            await sm.transition_to(SystemState.READY, reason="组件就绪")
            # 第三步：READY -> MONITORING
            await sm.transition_to(SystemState.MONITORING, reason="系统启动")
            Dashboard.log("✅ 状态机已启动，当前状态: MONITORING", "SUCCESS")
        else:
            Dashboard.log(f"⚠️ 状态机已在运行: {current_state.value}", "WARNING")

    # =========================================================================
    # Phase 8: 主循环 (The Loop)
    # =========================================================================
    async def phase_8_main_loop(self):
        Dashboard.log("⭐⭐⭐ 引擎启动完成，进入主循环 ⭐⭐⭐", "SUCCESS")
        print("-" * 80)

        circuit = self.components["circuit_breaker"]
        ex_guard = self.components["exchange_guard"]
        margin_guard = self.components["margin_guard"]
        liquidity_guard = self.components["liquidity_guard"]
        pnl_tracker = self.components["pnl_tracker"]
        position_manager = self.components["position_manager"]
        context = self.components["context"]
        sm = self.components["state_machine"]

        last_heartbeat = 0
        heartbeat_intv = 5
        last_scan_time = 0
        scan_interval = 60  # 市场扫描间隔（秒）

        while self.is_running:
            try:
                now = time.time()

                # ============ 步骤1: 全局风控检查 ============
                if circuit.is_triggered():
                    Dashboard.log("🚫 [熔断] 系统熔断中，暂停交易...", "WARNING")
                    await asyncio.sleep(5)
                    continue

                if not ex_guard.is_healthy():
                    Dashboard.log("⚠️ [API] 交易所连接不稳定...", "WARNING")
                    await asyncio.sleep(5)
                    continue

                # ============ 步骤2: 保证金检查 ============
                await margin_guard.check_margin_ratio(context)
                if context.margin_ratio < 1.5:  # 低于150%时报警
                    Dashboard.log(f"🚨 [保证金] 保证金率过低: {context.margin_ratio:.2f}%", "ERROR")
                    await sm.transition_to(SystemState.ERROR, reason="保证金不足")

                # ============ 步骤3: 市场扫描 (定时触发) ============
                if now - last_scan_time > scan_interval:
                    Dashboard.log("📡 [扫描] 开始市场扫描...", "INFO")
                    await self._scan_market(context)
                    last_scan_time = now
                    Dashboard.log(f"✅ [扫描] 市场扫描完成，流动性深度: {context.liquidity_depth:.2f}", "SUCCESS")

                # ============ 步骤4: 策略信号判断 ============
                # 只在 MONITORING 状态下接受新信号（系统正常监控中）
                if sm.get_current_state() == SystemState.MONITORING:
                    signal = await self.strategy.analyze_signal()

                    if signal:
                        Dashboard.log(f"🎯 [信号] 检测到交易信号: {signal}", "INFO")
                    else:
                        # 没有信号时也输出日志，让用户知道系统在工作
                        # 每分钟只输出一次，避免刷屏
                        if int(now) % 60 == 0:
                            Dashboard.log("📊 [扫描] 市场扫描中，暂无交易信号", "INFO")

                        # ============ 步骤5: 风控审批 ============
                        approval = await self._risk_approve(signal, context)

                        if not approval["approved"]:
                            Dashboard.log(f"❌ [风控] 信号被拒绝: {approval['reason']}", "WARNING")
                        else:
                            # ============ 步骤6: 执行前状态锁定 ============
                            await sm.transition_to(SystemState.OPENING_POSITION, reason="执行交易")

                            try:
                                # ============ 步骤7: 执行交易 ============
                                execution_result = await self.strategy.execute(signal, approval)

                                if execution_result["success"]:
                                    Dashboard.log("✅ [执行] 交易执行成功", "SUCCESS")

                                    # ============ 步骤8: 更新 Context & PnL ============
                                    await self._update_context_after_trade(
                                        context, position_manager, pnl_tracker, signal, execution_result
                                    )

                                    # ============ 步骤9: 恢复状态 ============
                                    await sm.transition_to(SystemState.IDLE, reason="执行完成")
                                else:
                                    Dashboard.log(f"❌ [执行] 交易失败: {execution_result['error']}", "ERROR")
                                    await sm.transition_to(SystemState.ERROR, reason="交易失败")

                            except Exception as e:
                                Dashboard.log(f"❌ [异常] 交易执行异常: {e}", "ERROR")
                                logger.error(traceback.format_exc())
                                await sm.transition_to(SystemState.ERROR, reason="执行异常")

                # ============ 步骤10: Dashboard 心跳 ============
                if now - last_heartbeat > heartbeat_intv:
                    self._print_heartbeat()
                    last_heartbeat = now

                await asyncio.sleep(1)

            except Exception as e:
                Dashboard.log(f"主循环异常: {e}", "ERROR")
                logger.error(traceback.format_exc())
                await sm.transition_to(SystemState.ERROR, reason="主循环异常")
                await asyncio.sleep(5)

    # =========================================================================
    # 辅助方法：市场扫描
    # =========================================================================
    async def _scan_market(self, context: Context):
        """
        【8】市场扫描
        - 拉取 K 线数据
        - 分析趋势
        - 检查流动性
        """
        try:
            client = self.components["client"]

            # 获取多个周期的 K 线
            periods = ["1D", "4H", "15m"]
            market_data = {}

            for period in periods:
                if hasattr(client, 'get_candlesticks'):
                    klines = await client.get_candlesticks(self.strategy.symbol, bar=period, limit=50)
                    if klines:
                        market_data[period] = klines
                        logger.debug(f"获取 {period} K线成功: {len(klines)} 条")
                    else:
                        logger.warning(f"获取 {period} K线失败: 返回空")
                else:
                    logger.warning("Client 缺少 get_candlesticks 方法，跳过K线获取")

            # 更新 Context
            context.market_snapshot = market_data
            context.last_scan_time = time.time()

            # 检查流动性
            ticker = await client.get_ticker(self.strategy.symbol)
            if ticker:
                context.liquidity_depth = float(ticker[0].get('askSz', 0))
                logger.info(f"流动性深度: {context.liquidity_depth}")
            else:
                logger.warning("获取 ticker 失败")

        except Exception as e:
            logger.error(f"市场扫描失败: {e}")
            Dashboard.log(f"⚠️ [扫描] 市场扫描异常: {e}", "WARNING")

    # =========================================================================
    # 辅助方法：风控审批
    # =========================================================================
    async def _risk_approve(self, signal: dict, context: Context) -> dict:
        """
        【10】风控审批
        - 检查熔断状态
        - 计算最大仓位
        - 设置止损止盈线
        """
        approval = {
            "approved": True,
            "reason": "",
            "max_position": 0,
            "stop_loss": 0,
            "take_profit": 0
        }

        try:
            circuit = self.components["circuit_breaker"]
            margin_guard = self.components["margin_guard"]
            liquidity_guard = self.components["liquidity_guard"]

            # 1. 检查熔断器
            if circuit.is_triggered():
                approval["approved"] = False
                approval["reason"] = "熔断器已触发"
                return approval

            # 2. 检查保证金
            if context.margin_ratio < 2.0:  # 低于200%拒绝新交易
                approval["approved"] = False
                approval["reason"] = f"保证金率过低: {context.margin_ratio:.2f}%"
                return approval

            # 3. 检查流动性
            liquidity_ok = await liquidity_guard.check_liquidity(context)
            if not liquidity_ok:
                approval["approved"] = False
                approval["reason"] = "流动性不足"
                return approval

            # 4. 计算最大仓位（基于保证金）
            usdt_balance = context.balances.get("USDT")
            max_usdt = usdt_balance.available if usdt_balance else 0.0
            max_position = max_usdt * 0.3  # 最多使用30%保证金
            approval["max_position"] = max_position

            # 5. 设置止损止盈（基于信号）
            signal_type = signal.get("type", "neutral")
            entry_price = signal.get("price", 0)

            if signal_type == "long":
                approval["stop_loss"] = entry_price * 0.97  # 止损3%
                approval["take_profit"] = entry_price * 1.05  # 止盈5%
            elif signal_type == "short":
                approval["stop_loss"] = entry_price * 1.03  # 止损3%
                approval["take_profit"] = entry_price * 0.95  # 止盈5%

            Dashboard.log("✅ [风控] 信号通过审批", "SUCCESS")

        except Exception as e:
            approval["approved"] = False
            approval["reason"] = f"风控检查异常: {e}"
            logger.error(traceback.format_exc())

        return approval

    # =========================================================================
    # 辅助方法：更新 Context & PnL
    # =========================================================================
    async def _update_context_after_trade(
        self, context: Context, position_manager, pnl_tracker, signal: dict, execution_result: dict
    ):
        """
        【13】更新 Context & PnL
        - 同步仓位信息
        - 计算浮动盈亏
        - 记录交易历史
        """
        try:
            # 获取状态机
            sm = self.components["state_machine"]

            # 1. 同步仓位
            await position_manager.sync_positions(context)

            # 2. 更新交易时间
            context.last_trade_time = time.time()

            # 3. 计算 PnL
            if "position" in execution_result:
                await pnl_tracker.update_pnl(execution_result["position"])

            # 4. 记录交易日志
            trade_record = {
                "timestamp": time.time(),
                "signal": signal,
                "execution": execution_result,
                "state": sm.get_current_state().value
            }

            if not hasattr(context, "trade_history"):
                context.trade_history = []
            context.trade_history.append(trade_record)

            Dashboard.log("✅ [Context] 上下文已更新", "SUCCESS")

        except Exception as e:
            logger.error(f"更新 Context 失败: {e}")

    def _print_heartbeat(self):
        """控制台动态心跳，显示系统运行状态"""
        try:
            import datetime

            # 获取关键信息
            sm = self.components.get("state_machine")
            context = self.components.get("context")
            sym = getattr(self.strategy, 'symbol', 'UNKNOWN')

            # 计算运行时间
            if context and hasattr(context, 'start_time'):
                uptime = datetime.datetime.now() - context.start_time
                uptime_str = str(uptime).split('.')[0]  # 去掉微秒
            else:
                uptime_str = "N/A"

            # 当前状态
            current_state = sm.get_current_state().value if sm else "N/A"

            # 最后扫描时间
            last_scan = "N/A"
            if context and hasattr(context, 'last_scan_time') and context.last_scan_time > 0:
                seconds_ago = int(time.time() - context.last_scan_time)
                last_scan = f"{seconds_ago}s ago"

            # 构建心跳信息
            heartbeat_info = (
                f"💓 [心跳] 状态: {current_state:15} | "
                f"策略: {sym:20} | "
                f"运行: {uptime_str:15} | "
                f"扫描: {last_scan:10}"
            )

            # 直接打印到控制台（不通过 Dashboard.log，因为可能被重定向到文件）
            print(f"\r{heartbeat_info}", end="", flush=True)

        except Exception as e:
            print(f"\r💓 [心跳] 系统运行中... (获取详情失败: {e})", end="", flush=True)

    # =========================================================================
    # Shutdown: 安全退出
    # =========================================================================
    async def shutdown(self):
        print("") # 换行
        Dashboard.log("正在执行安全退出程序...", "WARNING")

        if "scheduler" in self.components:
            await self.components["scheduler"].stop()

        if self.strategy:
            try:
                await self.strategy.shutdown()
            except Exception as e:
                logger.error(f"策略清理异常: {e}")

        if "client" in self.components:
            await self.components["client"].disconnect()

        Dashboard.log("系统已安全关闭，数据已归档。", "SUCCESS")
        sys.exit(0)

    # =========================================================================
    # Run: 编排入口
    # =========================================================================
    async def run(self):
        try:
            self.phase_1_bootstrap()
            self.phase_2_load_config()
            await self.phase_3_connect()
            self.phase_4_build_context()
            await self.phase_5_assembly()
            await self.phase_6_scheduler()
            await self.phase_7_start_machine()
            await self.phase_8_main_loop()
        except Exception as e:
            Dashboard.log(f"引擎启动中断: {e}", "ERROR")
            logger.critical(traceback.format_exc())
        finally:
            await self.shutdown()


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    engine = QuantEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        pass