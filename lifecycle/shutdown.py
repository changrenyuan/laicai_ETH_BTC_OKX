"""
🛑 Shutdown Phase
安全退出
"""

import sys
import logging
from monitor.dashboard import Dashboard

logger = logging.getLogger("Orchestrator")


class Shutdown:
    """Shutdown 生命周期阶段 - 安全退出"""
    
    def __init__(self, components: dict, strategy=None):
        self.components = components
        self.strategy = strategy
    
    async def run(self):
        """执行安全退出"""
        print("")
        Dashboard.log("正在执行安全退出程序...", "WARNING")
        
        try:
            # 停止调度器
            if "scheduler" in self.components:
                await self.components["scheduler"].stop()
            
            # 策略清理
            if self.strategy:
                try:
                    await self.strategy.shutdown()
                except Exception as e:
                    logger.error(f"策略清理异常: {e}")
            
            # 断开交易所连接
            if "client" in self.components:
                await self.components["client"].disconnect()
            
            Dashboard.log("系统已安全关闭，数据已归档。", "SUCCESS")
            sys.exit(0)
            
        except Exception as e:
            logger.error(f"退出异常: {e}")
            sys.exit(1)
