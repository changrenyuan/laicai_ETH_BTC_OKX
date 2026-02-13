"""
🔌 ExchangeBase - 交易所基类
统一的交易所接口，所有交易所实现都必须继承此类
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from core.rate_limiting.rate_limiter import RateLimiter
from core.time_synchronizer import TimeSynchronizer


class ExchangeBase(ABC):
    """
    交易所基类
    
    所有交易所实现都必须继承此类，实现统一的接口
    """

    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Rate Limiting
        self.rate_limiter = RateLimiter(config.get("rate_limits", {}))
        
        # Time Synchronizer
        self.time_synchronizer = TimeSynchronizer(
            sync_interval=config.get("time_sync_interval", 60)
        )
        
        # 订单缓存
        self._order_cache: Dict[str, Dict] = {}
        self._position_cache: Dict[str, Dict] = {}
        self._balance_cache: Dict[str, Dict] = {}
        
        self.is_connected = False
        self.last_sync_time = None

    @property
    @abstractmethod
    def name(self) -> str:
        """交易所名称"""
        pass

    @property
    @abstractmethod
    def rate_limits_rules(self) -> Dict:
        """API 频率限制规则"""
        pass

    # ========== 认证相关 ==========

    @abstractmethod
    async def _generate_signature(self, method: str, path: str, params: Dict, timestamp: str) -> str:
        """生成签名"""
        pass

    @abstractmethod
    async def authenticate(self):
        """认证"""
        pass

    # ========== 订单管理 ==========

    @abstractmethod
    async def place_order(self, data: Dict) -> Tuple[bool, str, str]:
        """
        下单
        
        Returns:
            (success, order_id, error_msg)
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> Tuple[bool, str, str]:
        """
        取消订单
        
        Returns:
            (success, order_id, error_msg)
        """
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str, symbol: str) -> Optional[Dict]:
        """获取订单状态"""
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取挂单"""
        pass

    @abstractmethod
    async def get_order_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取历史订单"""
        pass

    # ========== 账户管理 ==========

    @abstractmethod
    async def get_trading_balances(self, currency: Optional[str] = None) -> List[Dict]:
        """获取交易账户余额"""
        pass

    @abstractmethod
    async def get_funding_balances(self, currency: Optional[str] = None) -> List[Dict]:
        """获取资金账户余额"""
        pass

    @abstractmethod
    async def transfer_funds(
        self,
        currency: str,
        amount: float,
        from_account: str,
        to_account: str
    ) -> bool:
        """资金划转"""
        pass

    # ========== 持仓管理 ==========

    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取持仓"""
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Dict]:
        """获取单个持仓"""
        pass

    @abstractmethod
    async def set_leverage(self, data: Dict) -> bool:
        """设置杠杆"""
        pass

    # ========== 行情数据 ==========

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """获取行情"""
        pass

    @abstractmethod
    async def get_order_book(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """获取订单簿"""
        pass

    @abstractmethod
    async def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """获取成交记录"""
        pass

    @abstractmethod
    async def get_candlesticks(
        self,
        symbol: str,
        bar: str = "1m",
        limit: int = 100
    ) -> List[Dict]:
        """获取 K 线"""
        pass

    # ========== 工具方法 ==========

    async def _api_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        authenticated: bool = False
    ) -> Optional[Dict]:
        """
        统一的 API 请求方法
        
        包含：
        - Rate Limiting
        - Time Synchronization
        - Error Handling
        """
        try:
            # Rate Limiting
            await self.rate_limiter.acquire()
            
            # Time Synchronization
            timestamp = await self.time_synchronizer.get_server_time()
            
            # 构建请求
            url = self._build_url(path)
            headers = self._build_headers(method, path, params, timestamp, authenticated)
            
            # 发送请求
            response = await self._send_request(method, url, headers, params)
            
            return response
            
        except Exception as e:
            self.logger.error(f"API 请求失败: {e}")
            return None

    @abstractmethod
    def _build_url(self, path: str) -> str:
        """构建请求 URL"""
        pass

    @abstractmethod
    def _build_headers(
        self,
        method: str,
        path: str,
        params: Optional[Dict],
        timestamp: str,
        authenticated: bool
    ) -> Dict:
        """构建请求头"""
        pass

    @abstractmethod
    async def _send_request(
        self,
        method: str,
        url: str,
        headers: Dict,
        params: Optional[Dict]
    ) -> Optional[Dict]:
        """发送 HTTP 请求"""
        pass

    # ========== 生命周期管理 ==========

    async def connect(self):
        """连接到交易所"""
        if not self.is_connected:
            await self.authenticate()
            await self.time_synchronizer.start()
            self.is_connected = True
            self.logger.info(f"✅ {self.name} 连接成功")

    async def disconnect(self):
        """断开连接"""
        if self.is_connected:
            await self.time_synchronizer.stop()
            self.is_connected = False
            self.logger.info(f"🔌 {self.name} 断开连接")

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self._api_request("GET", self._health_check_path)
            return True
        except Exception:
            return False

    @property
    @abstractmethod
    def _health_check_path(self) -> str:
        """健康检查路径"""
        pass
