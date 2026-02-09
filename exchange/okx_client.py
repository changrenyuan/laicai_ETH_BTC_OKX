"""
🔌 OKX 客户端 (Phase 1: 只读模式)
封装只读接口：查询余额、查询持仓、查询价格
"""

import os
import aiohttp
import logging
from typing import Optional, Dict, Any
from datetime import datetime


class OKXClient:
    """
    OKX 交易所客户端（只读模式）
    仅提供查询功能，不包含交易功能
    """

    def __init__(self, config: dict):
        self.config = config

        # API 配置
        self.api_key = os.getenv("OKX_API_KEY", config.get("api_key", ""))
        self.api_secret = os.getenv("OKX_API_SECRET", config.get("api_secret", ""))
        self.api_passphrase = os.getenv("OKX_API_PASSPHRASE", config.get("api_passphrase", ""))
        self.sandbox = config.get("sandbox", False)

        # 基础URL
        if self.sandbox:
            self.base_url = "https://www.okx.com"  # 模拟环境
        else:
            self.base_url = "https://www.okx.com"

        self.session: Optional[aiohttp.ClientSession] = None

        self.logger = logging.getLogger(__name__)

    async def connect(self) -> bool:
        """
        建立连接

        Returns:
            bool: 是否连接成功
        """
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
            self.logger.info("OKX client connected")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            return False

    async def disconnect(self):
        """断开连接"""
        if self.session:
            await self.session.close()
            self.session = None
            self.logger.info("OKX client disconnected")

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法
            endpoint: API 端点
            params: 查询参数
            data: 请求体数据

        Returns:
            Dict: 响应数据
        """
        if not self.session:
            await self.connect()

        url = f"{self.base_url}{endpoint}"

        try:
            headers = self._get_headers(method, endpoint, params, data)

            async with self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                result = await response.json()

                if result.get("code") != "0":
                    self.logger.error(f"API error: {result}")
                    return None

                return result.get("data")

        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            return None

    def _get_headers(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Dict[str, str]:
        """
        生成请求头（带签名）

        注意：这是简化版本，生产环境需要完整的签名逻辑
        """
        timestamp = str(int(datetime.now().timestamp() * 1000))

        # TODO: 实现完整的 OKX 签名逻辑
        # 签名算法：base64(hmac_sha256(timestamp + method + requestPath + body, secret))
        # 暂时使用空字符串，实际使用时需要实现完整签名

        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": "",
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
            "Content-Type": "application/json",
        }

    # ============ Phase 1: 只读接口 ============

    # 1. 查询余额
    async def get_balance(self, currency: str = "USDT") -> Optional[Dict]:
        """
        获取指定货币的余额

        Args:
            currency: 货币单位，如 "USDT"

        Returns:
            Dict: 余额信息
        """
        result = await self._request(
            "GET",
            "/api/v5/account/balance",
            params={"ccy": currency},
        )
        return result

    async def get_all_balances(self) -> Optional[Dict]:
        """
        获取所有货币的余额

        Returns:
            Dict: 所有余额信息
        """
        result = await self._request(
            "GET",
            "/api/v5/account/balance",
        )
        return result

    # 2. 查询持仓
    async def get_positions(self, inst_type: str = "SWAP") -> Optional[Dict]:
        """
        获取持仓信息

        Args:
            inst_type: 产品类型，默认 "SWAP"（永续合约）

        Returns:
            Dict: 持仓信息
        """
        result = await self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instType": inst_type},
        )
        return result

    # 3. 查询价格
    async def get_ticker(self, inst_id: str) -> Optional[Dict]:
        """
        获取最新价格（行情）

        Args:
            inst_id: 产品ID，如 "BTC-USDT-SWAP"

        Returns:
            Dict: 行情数据
        """
        result = await self._request(
            "GET",
            "/api/v5/market/ticker",
            params={"instId": inst_id},
        )
        return result

    # 4. 查询账户配置
    async def get_account_config(self) -> Optional[Dict]:
        """
        获取账户配置信息

        Returns:
            Dict: 账户配置
        """
        result = await self._request(
            "GET",
            "/api/v5/account/config",
        )
        return result

    # ============ Phase 2 以后的功能（暂不实现） ============
    # 以下功能将在后续阶段实现：
    # - place_order()  # 下单
    # - cancel_order()  # 撤单
    # - transfer()  # 资金划转
    # 等...

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()
