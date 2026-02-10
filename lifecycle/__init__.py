"""
🔄 Lifecycle Module
系统生命周期管理 - 编排各个阶段

生命周期流程：
1. bootstrap    - 启动前自检
2. initialize   - 初始化组件
3. connect      - 连接交易所
4. build_context- 构建Context
5. register     - 注册模块
6. scheduler    - 启动调度器
7. runtime      - 主循环
8. shutdown     - 安全退出
"""

from .bootstrap import Bootstrap
from .initialize import Initialize
from .connect import Connect
from .build_context import BuildContext
from .register import Register
from .scheduler import SchedulerLifecycle
from .runtime import Runtime
from .shutdown import Shutdown

__all__ = [
    "Bootstrap",
    "Initialize",
    "Connect",
    "BuildContext",
    "Register",
    "SchedulerLifecycle",
    "Runtime",
    "Shutdown"
]
