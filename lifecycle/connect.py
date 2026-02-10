"""
🔌 Connect Phase
连接交易所 & 初始状态拉取
"""

from exchange.okx_client import OKXClient
from monitor.dashboard import Dashboard


class Connect:
    """Connect 生命周期阶段 - 连接交易所"""
    
    def __init__(self, config: dict):
        self.config = config
        self.client = None
    
    async def run(self) -> OKXClient:
        """执行连接"""
        Dashboard.log("【3】连接交易所 & 拉取初始状态...", "INFO")
        
        # 1. 初始化客户端
        self.client = OKXClient(self.config.get("sub_account"))
        connected = await self.client.connect()
        
        if not connected:
            raise ConnectionError("无法连接到 OKX API")
        
        Dashboard.log("交易所 API 连接建立。", "SUCCESS")
        
        # 2. 拉取账户初始快照
        bal = await self.client.get_trading_balances()
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
        
        return self.client
