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
        if sm.get_current_state() != SystemState.IDLE:
            await sm.transition_to(SystemState.IDLE, reason="Engine Start")

    # =========================================================================
    # Phase 8: 主循环 (The Loop)
    # =========================================================================
        # =========================================================================
        # Phase 8: 主循环 (The Loop) - 严格遵循流程图
        # =========================================================================
    async def phase_8_main_loop(self):
        Dashboard.log("⭐⭐⭐ 引擎启动完成，进入主循环 ⭐⭐⭐", "SUCCESS")
        print("-" * 80)

        # 组件引用
        sm = self.components["state_machine"]
        ctx = self.components["context"]
        circuit = self.components["circuit_breaker"]
        ex_guard = self.components["exchange_guard"]
        margin_guard = self.components["margin_guard"]

        # 计时器
        last_heartbeat = 0
        heartbeat_intv = 2

        # 调度间隔 (模拟 Scheduler 触发)
        SCAN_INTERVAL = 5  # 每5秒扫描一次
        last_scan_time = 0

        while self.is_running:
            try:
                now = time.time()

                # ---------------------------------------------------------
                # 【State = IDLE】 等待调度触发
                # ---------------------------------------------------------
                if sm.get_current_state() != SystemState.IDLE:
                    # 如果状态不对（比如卡在 STOPPED），强制复位或等待
                    await asyncio.sleep(1)
                    continue

                # 检查是否到达扫描时间 (Scheduler 逻辑)
                if now - last_scan_time < SCAN_INTERVAL:
                    # --- Dashboard 心跳 (空闲时刷新) ---
                    if now - last_heartbeat > heartbeat_intv:
                        self._print_heartbeat()
                        last_heartbeat = now
                    await asyncio.sleep(0.1)
                    continue

                last_scan_time = now

                # ---------------------------------------------------------
                # 【8】市场扫描 (Scanner)
                # ---------------------------------------------------------
                # 这一步通常在 Strategy.calculate_signal 里做，
                # 但 Main 负责记录这个动作
                # Dashboard.log("正在扫描市场...", "INFO") # 可选，太频繁可注释

                # ---------------------------------------------------------
                # 【9】策略判断 (Strategy)
                # ---------------------------------------------------------
                # 获取策略信号 (这里简化为 run_tick 内部判断，但在逻辑上属于这一步)
                # 如果是震荡/无机会，策略内部直接 return，对应流程图的 (None -> IDLE)

                # ---------------------------------------------------------
                # 【10】风控审批 (Risk Gateway)
                # ---------------------------------------------------------
                # 1. 熔断检查
                if circuit.is_triggered():
                    print("")
                    Dashboard.log("🚫 [熔断] 市场波动剧烈，拒绝交易", "WARNING")
                    await asyncio.sleep(5)
                    continue

                # 2. API 健康检查
                if not ex_guard.is_healthy():
                    print("")
                    Dashboard.log("⚠️ [API] 交易所连接不稳定，拒绝交易", "WARNING")
                    await asyncio.sleep(5)
                    continue

                # 3. 保证金检查 (比如保证金率 < 300% 禁止开新仓)
                # 这里我们需要传入 Context 里的实时数据
                # if not margin_guard.check_threshold(ctx.margin_ratio):
                #     Dashboard.log("🛡️ [风控] 保证金不足，拒绝开仓", "WARNING")
                #     continue

                # ---------------------------------------------------------
                # 【11】执行前状态锁定 (State Locking)
                # ---------------------------------------------------------
                # 只有通过了风控，才允许进入执行状态
                await sm.transition_to(SystemState.RUNNING, reason="Signal Triggered")

                # ---------------------------------------------------------
                # 【12】执行层 (Execution)
                # ---------------------------------------------------------
                # 调用策略执行逻辑 (下单/补单/撤单)
                # 这里对应流程图的 "原子下单" 和 "处理跛脚"
                await self.strategy.run_tick()

                # ---------------------------------------------------------
                # 【13】更新 Context & PnL
                # ---------------------------------------------------------
                # 交易完成后，立即刷新一次账户状态
                # 实际项目中，这里可以调用 client.get_positions() 更新 context
                # await self.phase_3_connect() # 简化版：复用连接时的拉取逻辑刷新UI

                # ---------------------------------------------------------
                # 【14】恢复 State → IDLE
                # ---------------------------------------------------------
                await sm.transition_to(SystemState.IDLE, reason="Execution Complete")

            except Exception as e:
                print("")  # 换行
                Dashboard.log(f"主循环异常: {e}", "ERROR")
                logger.error(traceback.format_exc())

                # 发生异常，强制恢复 IDLE 状态，防止死锁
                await sm.transition_to(SystemState.IDLE, reason="Error Recovery")
                await asyncio.sleep(5)
    def _print_heartbeat(self):
        """控制台动态心跳，不刷屏"""
        try:
            # 尝试获取策略关注的 Symbol
            sym = getattr(self.strategy, 'symbol', 'UNKNOWN')
            # 这里简单打印，实际可扩展为刷新价格
            pass
        except:
            pass

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