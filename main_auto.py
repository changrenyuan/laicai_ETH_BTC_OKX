"""
🚀 Laicai Funding Engine (Main Entry)
=====================================
全自动量化交易引擎总入口
负责系统的生命周期管理、组件装配与异常兜底。

[职责边界]
✅ 启动前自检 (Bootstrap)
✅ 加载配置 (Config Loader)
✅ 初始化交易所 (Exchange Init)
✅ 构建上下文 (Context Builder)
✅ 装配策略与风控 (Assembly)
✅ 启动调度与状态机 (Launch)
✅ 兜底安全退出 (Graceful Shutdown)

❌ 绝不包含策略逻辑
❌ 绝不包含风控细节
❌ 绝不直接操作下单
"""

import asyncio
import sys
import signal
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
# 2. 模块导入 (按层级)
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

# Strategy Factory (策略工厂)
from strategy import StrategyFactory

# Scripts (运维工具)
from scripts.bootstrap import BootstrapChecker

# -----------------------------------------------------------------------------
# 3. 日志配置 (Log Redirect)
# -----------------------------------------------------------------------------
LOG_DIR = ROOT_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "runtime.log", encoding='utf-8'),
        # logging.FileHandler(LOG_DIR / "error.log", level=logging.ERROR, encoding='utf-8')
    ]
)
# 屏蔽控制台噪音
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("Main")


class QuantEngine:
    """
    量化引擎主类
    负责组装各个零部件，并按顺序启动系统
    """
    def __init__(self):
        self.is_running = True
        self.config = {}
        self.components = {}
        self.strategy_instance = None

        # 注册信号处理 (Ctrl+C / Kill)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        Dashboard.log("接收到终止信号，准备安全退出...", "WARNING")
        self.is_running = False

    async def _load_configurations(self):
        """步骤 2: 加载配置"""
        Dashboard.log("正在加载配置文件...", "INFO")
        try:
            cfg_path = ROOT_DIR / "config"
            with open(cfg_path / "account.yaml", "r", encoding="utf-8") as f: ac = yaml.safe_load(f)
            with open(cfg_path / "risk.yaml", "r", encoding="utf-8") as f: ri = yaml.safe_load(f)
            with open(cfg_path / "strategy.yaml", "r", encoding="utf-8") as f: st = yaml.safe_load(f)

            # 合并为一个大字典
            self.config = {**ac, **ri, **st}

            # 激活策略检查
            active_strat = self.config.get("active_strategy", "UNKNOWN")
            Dashboard.log(f"配置加载完成 | 激活策略: [{active_strat.upper()}]", "SUCCESS")

        except Exception as e:
            Dashboard.log(f"配置文件加载失败: {e}", "ERROR")
            raise e

    async def _init_exchange(self):
        """步骤 3: 初始化交易所"""
        Dashboard.log("正在连接 OKX 交易所...", "INFO")
        sub_account = self.config.get("sub_account", "")
        client = OKXClient(sub_account)

        is_connected = await client.connect()
        if not is_connected:
            raise ConnectionError("无法连接到 OKX API，请检查网络或配置")

        self.components["client"] = client
        Dashboard.log("交易所 API 连接建立", "SUCCESS")

    async def _build_context(self):
        """步骤 4: 构建 Context 与 Core"""
        Dashboard.log("正在构建系统内核...", "INFO")

        event_bus = EventBus()
        state_machine = StateMachine(event_bus)
        context = Context()

        self.components["event_bus"] = event_bus
        self.components["state_machine"] = state_machine
        self.components["context"] = context

    async def _assemble_modules(self):
        """步骤 5: 装配策略 + 风控 + 执行"""
        Dashboard.log("正在装配策略与风控组件...", "INFO")

        cfg = self.config
        client = self.components["client"]
        ctx = self.components["context"]
        sm = self.components["state_machine"]
        bus = self.components["event_bus"]

        # 5.1 风控层 (Risk Layer)
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

        # 5.2 执行层 (Execution Layer)
        order_manager = OrderManager(client, sm, bus)
        position_manager = PositionManager(ctx)

        self.components["order_manager"] = order_manager
        self.components["position_manager"] = position_manager

        # 5.3 监控层 (Monitor Layer)
        pnl_tracker = PnLTracker(cfg)
        self.components["pnl_tracker"] = pnl_tracker

        # 5.4 策略层 (Strategy Layer) - 核心装配
        # 将风控和执行组件注入策略，但 main.py 不关心策略具体逻辑
        active_name = cfg.get("active_strategy", "futures_grid")

        try:
            strategy = StrategyFactory(
                strategy_name=active_name,
                config=cfg,
                context=ctx,
                state_machine=sm,
                order_manager=order_manager,
                # 注入额外依赖
                margin_guard=margin_guard,
                fund_guard=fund_guard
            )
            # 策略初始化 (计算网格/预挂单/自检)
            await strategy.initialize()
            self.strategy_instance = strategy
            Dashboard.log(f"策略 [{active_name}] 装配并初始化成功", "SUCCESS")

        except Exception as e:
            logger.error(traceback.format_exc())
            raise RuntimeError(f"策略装配失败: {e}")

    async def _start_scheduler(self):
        """步骤 6: 启动调度器"""
        Dashboard.log("正在启动自动化调度器...", "INFO")

        scheduler = Scheduler(
            context=self.components["context"],
            fund_guard=self.components["fund_guard"],
            pnl_tracker=self.components["pnl_tracker"],
            position_manager=self.components["position_manager"]
        )

        await scheduler.start()
        self.components["scheduler"] = scheduler

    async def _start_state_machine(self):
        """步骤 7: 启动状态机"""
        sm = self.components["state_machine"]
        if sm.get_current_state() != SystemState.IDLE:
            await sm.transition_to(SystemState.IDLE, reason="Engine Launch")
        Dashboard.log("状态机已就绪 (IDLE)", "SUCCESS")

    async def run(self):
        """
        [主入口] 全流程编排
        """
        Dashboard.print_banner()

        try:
            # Step 1: 启动前自检 (调用 scripts/bootstrap.py)
            Dashboard.log("执行 Phase 1: 启动前自检...", "INFO")
            if not BootstrapChecker():
                Dashboard.log("自检失败，禁止启动", "ERROR")
                return

            # Step 2-7: 初始化流程
            await self._load_configurations()
            await self._init_exchange()
            await self._build_context()
            await self._assemble_modules()
            await self._start_scheduler()
            await self._start_state_machine()

            Dashboard.log("⭐⭐⭐ 引擎启动完成，进入主循环 ⭐⭐⭐", "SUCCESS")
            print("-" * 80)

            # Step 8: 主循环 (The Loop)
            # main.py 只负责维持心跳和顶层异常捕获，不处理业务逻辑
            circuit = self.components["circuit_breaker"]
            ex_guard = self.components["exchange_guard"]

            while self.is_running:
                # 8.1 全局熔断检查
                if circuit.is_triggered():
                    Dashboard.log("🚫 系统熔断中，暂停策略...", "WARNING")
                    await asyncio.sleep(5)
                    continue

                # 8.2 API 健康检查
                if not ex_guard.is_healthy():
                    Dashboard.log("⚠️ 交易所 API 异常，暂停策略...", "WARNING")
                    await asyncio.sleep(5)
                    continue

                # 8.3 驱动策略 (Tick)
                # 所有的行情判断、下单、对冲都在 strategy.run_tick() 内部闭环
                await self.strategy_instance.run_tick()

                # 8.4 释放 CPU
                await asyncio.sleep(1)

        except Exception as e:
            Dashboard.log(f"引擎发生致命崩溃: {e}", "ERROR")
            logger.critical(traceback.format_exc())
        finally:
            await self.shutdown()

    async def shutdown(self):
        """
        [兜底] 安全退出流程
        """
        print("")
        Dashboard.log("正在执行安全退出程序...", "WARNING")

        # 1. 停止调度器
        if "scheduler" in self.components:
            await self.components["scheduler"].stop()

        # 2. 策略层清理 (撤单/持久化)
        if self.strategy_instance:
            try:
                await self.strategy_instance.shutdown()
            except Exception as e:
                logger.error(f"策略清理异常: {e}")

        # 3. 断开连接
        if "client" in self.components:
            await self.components["client"].disconnect()

        Dashboard.log("系统已安全关闭，数据已归档。", "SUCCESS")
        sys.exit(0)


if __name__ == "__main__":
    # 针对 Windows 的 EventLoop 策略调整
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    engine = QuantEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        # 这一步通常被 signal handler 捕获，但保留以此兜底
        pass