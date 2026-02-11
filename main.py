"""
🚀 LAICAI QUANT COMMANDER (精简版)
主入口 - 生命周期编排
"""

import asyncio
import signal
import sys
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
# 添加项目根目录到路径
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from lifecycle import (
    Bootstrap,
    Initialize,
    Connect,
    BuildContext,
    Register,
    SchedulerLifecycle,
    Runtime,
    Shutdown
)


class QuantEngine:
    """量化引擎 - 极简版"""

    def __init__(self):
        self.components = {}
        self.config = {}
        self.strategy = None
        self.runtime = None
        self._shutdown_event = asyncio.Event()

        # 信号注册
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """信号处理"""
        print("\n收到停止信号...")
        if self.runtime:
            self.runtime.is_running = False
        self._shutdown_event.set()

    async def run(self):
        """按生命周期顺序执行"""
        try:
            # Phase 1: Bootstrap - 启动前自检
            bootstrap = Bootstrap()
            if not bootstrap.run():
                return

            # Phase 2: Initialize - 加载配置
            initialize = Initialize()
            self.config = initialize.run()

            # Phase 3: Connect - 连接交易所
            connect = Connect(self.config)
            self.components["client"] = await connect.run()

            # Phase 4: BuildContext - 构建Context并注入核心组件
            build_context = BuildContext()
            # 获取 context, event_bus, state_machine
            core_components = build_context.run()
            self.components.update(core_components)

            # Phase 5: Register - 注册模块 (此时 state_machine 已存在)
            register = Register(self.config, self.components)
            await register.run()
            self.strategy = register.strategy

            # Phase 6: Scheduler - 启动调度器
            scheduler = SchedulerLifecycle(self.components)
            await scheduler.run()

            # Phase 7-8: Runtime - 启动状态机 & 主循环
            self.runtime = Runtime(self.components, self.strategy, self.config)
            await self.runtime.run()

        except Exception as e:
            print(f"引擎启动失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Phase 9: Shutdown - 安全退出
            shutdown = Shutdown(self.components, self.strategy)
            await shutdown.run()


def setup_logging():
    # 确保目录存在
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 格式化器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 1. 终端输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. 文件输出 (新增：生成 runtime.log)
    file_handler = RotatingFileHandler(
        log_dir / "runtime.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

def main():
    """主函数"""
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    setup_logging()
    engine = QuantEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        print("\n程序被中断")
        sys.exit(0)


if __name__ == "__main__":
    main()