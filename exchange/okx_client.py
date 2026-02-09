"""
🔌 OKX 客户端
REST / WebSocket 封装
"""

import os
import aiohttp
import logging
from typing import Optional, Dict, Any
from datetime import datetime


class OKXClient:
    """
    OKX 交易所客户端
    提供 REST API 和 WebSocket 接口
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

    async def connect(self):
        """建立连接"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self.logger.info("OKX client connected")

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
        """生成请求头"""
        # TODO: 实现 OKX 签名逻辑
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": "",
            "OK-ACCESS-TIMESTAMP": str(int(datetime.now().timestamp() * 1000)),
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
            "Content-Type": "application/json",
        }

    # ============ 账户相关 ============

    async def get_balance(self, currency: str = "USDT") -> Optional[Dict]:
        """获取余额"""
        result = await self._request(
            "GET",
            "/api/v5/account/balance",
            params={"ccy": currency},
        )
        return result

    async def get_positions(self, inst_type: str = "SWAP") -> Optional[Dict]:
        """获取持仓"""
        result = await self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instType": inst_type},
        )
        return result

    async def get_account_config(self) -> Optional[Dict]:
        """获取账户配置"""
        result = await self._request(
            "GET",
            "/api/v5/account/config",
        )
        return result

    # ============ 交易相关 ============

    async def place_order(
        self,
        inst_id: str,
        td_mode: str,
        side: str,
        ord_type: str,
        sz: str,
        px: Optional[str] = None,
        reduce_only: bool = False,
        post_only: bool = False,
    ) -> Optional[Dict]:
        """
        下单

        Args:
            inst_id: 产品ID
            td_mode: 交易模式
            side: 买卖方向
            ord_type: 订单类型
            sz: 数量
            px: 价格
            reduce_only: 是否仅减仓
            post_only: 是否仅挂单

        Returns:
            Dict: 订单信息
        """
        data = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz,
        }

        if px:
            data["px"] = px

        if reduce_only:
            data["reduceOnly"] = "true"

        if post_only:
            data["postOnly"] = "true"

        result = await self._request("POST", "/api/v5/trade/order", data=data)
        return result

    async def cancel_order(self, order_id: str, inst_id: str) -> Optional[Dict]:
        """撤单"""
        result = await self._request(
            "POST",
            "/api/v5/trade/cancel-order",
            data={
                "ordId": order_id,
                "instId": inst_id,
            },
        )
        return result

    async def cancel_all_orders(self, inst_type: str = "SWAP") -> Optional[Dict]:
        """撤销所有订单"""
        result = await self._request(
            "POST",
            "/api/v5/trade/cancel-batch-orders",
            data={"instType": inst_type},
        )
        return result

    # ============ 市场数据相关 ============

    async def get_ticker(self, inst_id: str) -> Optional[Dict]:
        """获取行情"""
        result = await self._request(
            "GET",
            "/api/v5/market/ticker",
            params={"instId": inst_id},
        )
        return result

    async def get_order_book(self, inst_id: str, sz: int = 5) -> Optional[Dict]:
        """获取订单簿"""
        result = await self._request(
            "GET",
            "/api/v5/market/books",
            params={"instId": inst_id, "sz": sz},
        )
        return result

    async def get_funding_rate(self, inst_id: str) -> Optional[Dict]:
        """获取资金费率"""
        result = await self._request(
            "GET",
            "/api/v5/public/funding-rate",
            params={"instId": inst_id},
        )
        return result

    async def get_candlesticks(
        self,
        inst_id: str,
        bar: str = "1H",
        limit: int = 100,
    ) -> Optional[Dict]:
        """获取K线数据"""
        result = await self._request(
            "GET",
            "/api/v5/market/candlesticks",
            params={
                "instId": inst_id,
                "bar": bar,
                "limit": str(limit),
            },
        )
        return result

    # ============ 资金划转相关 ============

    async def transfer(
        self,
        ccy: str,
        amt: str,
        from_: str,
        to: str,
        type_: str = "1",  # 0: 币币转合约, 1: 币币转统一账户
    ) -> Optional[Dict]:
        """资金划转"""
        result = await self._request(
            "POST",
            "/api/v5/account/transfer",
            data={
                "ccy": ccy,
                "amt": amt,
                "from": from_,
                "to": to,
                "type": type_,
            },
        )
        return result

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()
