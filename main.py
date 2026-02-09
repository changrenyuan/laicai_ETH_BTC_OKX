"""
⭐ 唯一入口
资金费率套利交易系统主程序
"""

import sys
import asyncio
import signal
import logging
from pathlib import Path
from datetime import datetime
import yaml

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class TradingSystem:
    """交易系统主类"""

    def __init__(self):
        self.config_dir = Path(__file__).parent / "config"
        self.data_dir = Path(__file__).parent / "data"
        self.logs_dir = Path(__file__).parent / "logs"

        # 确保目录存在
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 核心组件
        self.context = None
        self.event_bus = None
        self.state_machine = None
        self.scheduler = None

        # 业务模块
        self.okx_client = None
        self.strategy = None
        self.order_manager = None
        self.position_manager = None
        self.rebalancer = None

        # 风险模块
        self.margin_guard = None
        self.fund_guard = None
        self.liquidity_guard = None
        self.circuit_breaker = None
        self.exchange_guard = None

        # 监控模块
        self.health_checker = None
        self.pnl_tracker = None
        self.notifier = None

        # 系统状态
        self.is_running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        """初始化系统"""
        logger.info("=" * 60)
        logger.info("🚀 初始化交易系统")
        logger.info("=" * 60)

        try:
            # 1. 加载配置
            logger.info("\n📋 加载配置...")
            self._load_configs()

            # 2. 创建核心组件
            logger.info("🔧 创建核心组件...")
            await self._create_core_components()

            # 3. 创建业务模块
            logger.info("📦 创建业务模块...")
            await self._create_business_modules()

            # 4. 创建风险模块
            logger.info("🛡️  创建风险模块...")
            await self._create_risk_modules()

            # 5. 创建监控模块
            logger.info("👀 创建监控模块...")
            await self._create_monitor_modules()

            # 6. 连接交易所
            logger.info("🔌 连接交易所...")
            await self.okx_client.connect()

            # 7. 同步初始数据
            logger.info("📊 同步初始数据...")
            await self._sync_initial_data()

            # 8. 设置调度器任务
            logger.info("⏰ 设置调度任务...")
            self.scheduler.setup_default_tasks(
                self.context,
                self.okx_client,
                self._create_risk_manager(),
                self.strategy,
                self._create_execution_manager(),
                self.notifier,
            )

            logger.info("\n✅ 系统初始化完成")
            return True

        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def run(self):
        """运行系统"""
        logger.info("\n" + "=" * 60)
        logger.info("▶️  启动交易系统")
        logger.info("=" * 60)

        try:
            # 切换状态
            await self.state_machine.transition_to(
                SystemState.READY,
                reason="初始化完成"
            )

            # 系统启动
            await self.state_machine.transition_to(
                SystemState.MONITORING,
                reason="系统启动"
            )

            # 发送启动通知
            await self.notifier.send_startup_notification()

            # 设置上下文
            self.context.is_running = True
            self.context.start_time = datetime.now()

            # 启动调度器
            await self.scheduler.start()

            # 保存运行状态
            self.context.save_runtime_state()

            logger.info("✅ 系统已启动，开始监控市场...")
            logger.info("💡 按 Ctrl+C 停止系统")

            # 等待停止信号
            await self.shutdown_event.wait()

        except asyncio.CancelledError:
            logger.info("\n⏸️  收到停止信号")
        except Exception as e:
            logger.error(f"❌ 运行错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.shutdown()

    async def shutdown(self):
        """关闭系统"""
        logger.info("\n" + "=" * 60)
        logger.info("⏹️  关闭交易系统")
        logger.info("=" * 60)

        try:
            # 停止调度器
            if self.scheduler:
                await self.scheduler.stop()

            # 停止交易所连接
            if self.okx_client:
                await self.okx_client.disconnect()

            # 保存运行状态
            if self.context:
                self.context.is_running = False
                self.context.save_runtime_state()

            # 发送关闭通知
            if self.notifier:
                await self.notifier.send_shutdown_notification()

            logger.info("✅ 系统已关闭")

        except Exception as e:
            logger.error(f"❌ 关闭失败: {e}")

    def _load_configs(self):
        """加载配置"""
        # 加载账户配置
        with open(self.config_dir / "account.yaml", "r", encoding="utf-8") as f:
            self.account_config = yaml.safe_load(f)

        # 加载策略配置
        with open(self.config_dir / "strategy.yaml", "r", encoding="utf-8") as f:
            self.strategy_config = yaml.safe_load(f)

        # 加载风险配置
        with open(self.config_dir / "risk.yaml", "r", encoding="utf-8") as f:
            self.risk_config = yaml.safe_load(f)

        # 加载交易品种配置
        with open(self.config_dir / "instruments.yaml", "r", encoding="utf-8") as f:
            self.instruments_config = yaml.safe_load(f)

        logger.info("  ✅ 配置加载完成")

    async def _create_core_components(self):
        """创建核心组件"""
        from core.context import Context
        from core.events import EventBus
        from core.state_machine import StateMachine
        from core.scheduler import Scheduler
        from core.state_machine import SystemState

        # 创建上下文
        self.context = Context(
            config_dir=str(self.config_dir),
            data_dir=str(self.data_dir)
        )

        # 尝试加载运行状态
        self.context.load_runtime_state()

        # 创建事件总线
        self.event_bus = EventBus()

        # 创建状态机
        self.state_machine = StateMachine(self.event_bus)

        # 初始化状态
        await self.state_machine.transition_to(
            SystemState.INITIALIZING,
            reason="系统初始化"
        )

        # 创建调度器
        self.scheduler = Scheduler()

        logger.info("  ✅ 核心组件创建完成")

    async def _create_business_modules(self):
        """创建业务模块"""
        from exchange.okx_client import OKXClient
        from exchange.market_data import MarketDataFetcher
        from exchange.account_data import AccountDataFetcher
        from strategy.cash_and_carry import CashAndCarryStrategy
        from execution.order_manager import OrderManager
        from execution.position_manager import PositionManager
        from execution.rebalancer import Rebalancer

        # 创建交易所客户端
        self.okx_client = OKXClient(self.account_config["sub_account"])

        # 创建市场数据获取器
        self.market_fetcher = MarketDataFetcher(self.okx_client, {})

        # 创建账户数据获取器
        self.account_fetcher = AccountDataFetcher(self.okx_client, {})

        # 创建策略
        self.strategy = CashAndCarryStrategy(
            self.strategy_config,
            self.event_bus
        )

        # 创建订单管理器
        self.order_manager = OrderManager({}, self.okx_client)

        # 创建持仓管理器
        self.position_manager = PositionManager(
            {},
            self.order_manager,
            self.okx_client
        )

        # 创建再平衡器
        self.rebalancer = Rebalancer(
            {},
            None,  # fund_guard
            self.position_manager,
            self.okx_client
        )

        logger.info("  ✅ 业务模块创建完成")

    async def _create_risk_modules(self):
        """创建风险模块"""
        from risk.margin_guard import MarginGuard
        from risk.fund_guard import FundGuard
        from risk.liquidity_guard import LiquidityGuard
        from risk.circuit_breaker import CircuitBreaker
        from risk.exchange_guard import ExchangeGuard

        # 创建保证金防护
        self.margin_guard = MarginGuard(
            self.risk_config.get("margin_guard", {})
        )

        # 创建资金防护
        self.fund_guard = FundGuard(
            self.risk_config.get("fund_guard", {})
        )

        # 创建流动性防护
        self.liquidity_guard = LiquidityGuard(
            self.risk_config.get("liquidity_guard", {})
        )

        # 创建熔断器
        self.circuit_breaker = CircuitBreaker(
            self.risk_config.get("circuit_breaker", {})
        )

        # 创建交易所防护
        self.exchange_guard = ExchangeGuard(
            self.risk_config.get("exchange_guard", {})
        )

        logger.info("  ✅ 风险模块创建完成")

    async def _create_monitor_modules(self):
        """创建监控模块"""
        from monitor.health_check import HealthChecker
        from monitor.pnl_tracker import PnLTracker
        from monitor.notifier import Notifier

        # 创建健康检查器
        self.health_checker = HealthChecker({}, self.event_bus)

        # 创建 PnL 跟踪器
        self.pnl_tracker = PnLTracker({})

        # 创建通知器
        self.notifier = Notifier({
            "enabled": True,
            "telegram_enabled": False,
            "dingtalk_enabled": False,
        })

        logger.info("  ✅ 监控模块创建完成")

    async def _sync_initial_data(self):
        """同步初始数据"""
        # 同步余额
        all_balances = await self.account_fetcher.get_all_balances()
        for currency, balance in all_balances.items():
            self.context.update_balance(currency, balance.available, balance.frozen)

        logger.info(f"  ✅ 余额同步完成: {len(all_balances)} 种货币")

        # 同步持仓
        all_positions = await self.account_fetcher.get_all_positions()
        for symbol, position in all_positions.items():
            self.context.update_position(position)

        logger.info(f"  ✅ 持仓同步完成: {len(all_positions)} 个持仓")

        # 同步市场数据
        for instrument in self.instruments_config["instruments"]:
            if instrument["enabled"]:
                symbol = instrument["symbol"]
                market_data = await self.market_fetcher.get_market_data(symbol)
                if market_data:
                    self.context.update_market_data(market_data)

        logger.info("  ✅ 市场数据同步完成")

    def _create_risk_manager(self):
        """创建风险管理器（临时对象）"""
        class RiskManager:
            def __init__(self, margin_guard, fund_guard, liquidity_guard, circuit_breaker, exchange_guard):
                self.margin_guard = margin_guard
                self.fund_guard = fund_guard
                self.liquidity_guard = liquidity_guard
                self.circuit_breaker = circuit_breaker
                self.exchange_guard = exchange_guard

            async def check_all(self, context, notifier):
                # 检查保证金
                margin_result = await self.margin_guard.check(context)
                if margin_result.is_emergency:
                    await notifier.send_alert(
                        f"保证金紧急: {margin_result.message}",
                        level="critical"
                    )

        return RiskManager(
            self.margin_guard,
            self.fund_guard,
            self.liquidity_guard,
            self.circuit_breaker,
            self.exchange_guard
        )

    def _create_execution_manager(self):
        """创建执行管理器（临时对象）"""
        return self.rebalancer


def setup_signal_handlers(system: TradingSystem):
    """设置信号处理器"""
    def signal_handler(signum, frame):
        logger.info(f"\n收到信号 {signum}，准备关闭...")
        system.shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """主函数"""
    # 导入状态枚举
    from core.state_machine import SystemState

    # 创建系统
    system = TradingSystem()

    # 设置信号处理器
    setup_signal_handlers(system)

    # 初始化系统
    if not await system.initialize():
        logger.error("系统初始化失败，退出")
        return 1

    # 运行系统
    await system.run()

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n用户中断")
        sys.exit(0)
