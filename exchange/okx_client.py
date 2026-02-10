"""
🔌 OKX 客户端 (修复版：支持资金账户 + 交易账户)
"""

import os
import aiohttp
import logging
import hmac
import base64
import json
import urllib.parse
from typing import Optional, Dict, List
from datetime import datetime, timezone

class OKXClient:
    def __init__(self, config: dict):
        self.config = config

        # 优先从环境变量读取
        self.api_key = os.getenv("OKX_API_KEY", config.get("api_key", ""))
        self.api_secret = os.getenv("OKX_API_SECRET", config.get("api_secret", ""))
        self.api_passphrase = os.getenv("OKX_API_PASSPHRASE", config.get("api_passphrase", ""))
        self.sandbox = config.get("sandbox", False)

        # 获取代理配置
        self.proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

        self.base_url = "https://www.okx.com"
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(__name__)

        if self.proxy:
            self.logger.info(f"Using Proxy: {self.proxy}")

    async def connect(self) -> bool:
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
            return True
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            return False

    async def disconnect(self):
        if self.session:
            await self.session.close()
            self.session = None

    def _get_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(
            bytes(self.api_secret, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        return base64.b64encode(mac.digest()).decode()

    def _get_headers(self, method: str, request_path: str, body: str = "") -> Dict[str, str]:
        timestamp = self._get_timestamp()
        sign = self._sign(timestamp, method, request_path, body)
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
            "Content-Type": "application/json",
        }
        if self.sandbox:
            headers["x-simulated-trading"] = "1"
        return headers

    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Optional[Dict]:
        if not self.session:
            await self.connect()

        request_path = endpoint
        if method.upper() == "GET" and params:
            query_string = urllib.parse.urlencode(params)
            request_path = f"{endpoint}?{query_string}"

        body_str = json.dumps(data) if data else ""
        headers = self._get_headers(method, request_path, body_str)
        url = f"{self.base_url}{request_path}"

        try:
            async with self.session.request(
                method=method,
                url=url,
                data=body_str if data else None,
                headers=headers,
                proxy=self.proxy,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    self.logger.error(f"API HTTP Error {response.status}: {text}")
                    return None

                result = await response.json()
                if result.get("code") != "0":
                    self.logger.error(f"API Business Error: {result}")
                    return None

                return result.get("data")

        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            return None

    # ============ 核心查询接口 ============

    # 1. 查询交易账户 (Trading / Unified Account)
    # 这里的钱可以用来开单
    async def get_trading_balances(self):
        """查询交易账户余额"""
        return await self._request("GET", "/api/v5/account/balance")

    # 2. 查询资金账户 (Funding / Asset Account) - 新增！
    # 这里是充值默认到账的地方，不能直接开单
    async def get_funding_balances(self, ccy: str = None):
        """查询资金账户余额"""
        params = {}
        if ccy:
            params['ccy'] = ccy
        return await self._request("GET", "/api/v5/asset/balances", params=params)

    # 3. 资金划转 (资金账户 <-> 交易账户) - 为 Phase 2 准备
    async def transfer_funds(self, ccy: str, amt: float, from_type: str, to_type: str):
        """
        资金划转
        from_type/to_type: "6"(资金账户), "18"(交易账户)
        """
        data = {
            "ccy": ccy,
            "amt": str(amt),
            "from": from_type,
            "to": to_type
        }
        return await self._request("POST", "/api/v5/asset/transfer", data=data)

    async def get_positions(self, inst_type: str = "SWAP"):
        return await self._request("GET", "/api/v5/account/positions", params={"instType": inst_type})

    async def get_ticker(self, inst_id: str):
        return await self._request("GET", "/api/v5/market/ticker", params={"instId": inst_id})

    async def get_funding_rate(self, inst_id: str):
        return await self._request("GET", "/api/v5/public/funding-rate", params={"instId": inst_id})

        # 🔥 新增：获取所有行情 (用于扫描)
    async def get_tickers(self, instType: str = "SWAP") -> Optional[List[Dict]]:
        """获取某类产品的所有行情"""
        return await self._request("GET", "/api/v5/market/tickers", params={"instType": instType})

        # ... (保留原有 __init__, connect, _request 等方法) ...

    # 🔥 新增：批量下单 (Batch Orders)
    async def place_batch_orders(self, orders_data: list) -> list:
        """
        批量下单
        :param orders_data: 订单列表，每个元素是 dict
        Example:
        [
            {"instId": "BTC-USDT-SWAP", "tdMode": "cross", "side": "buy", "ordType": "limit", "px": "20000", "sz": "1"},
            ...
        ]
        """
        # OKX 限制每批最多 20 个订单
        BATCH_LIMIT = 20
        results = []

        # 分批处理
        for i in range(0, len(orders_data), BATCH_LIMIT):
            batch = orders_data[i: i + BATCH_LIMIT]
            self.logger.info(f"⚡ 批量提交订单: {len(batch)} 个")

            res = await self._request("POST", "/api/v5/trade/batch-orders", data=batch)
            if res:
                results.extend(res)
            else:
                self.logger.error("批量下单部分或全部失败")

        return results

    # 🔥 新增：批量撤单 (Batch Cancel)
    async def cancel_batch_orders(self, orders_data: list) -> list:
        """
        批量撤单
        :param orders_data: [{"instId": "...", "ordId": "..."}, ...]
        """
        BATCH_LIMIT = 20
        results = []

        for i in range(0, len(orders_data), BATCH_LIMIT):
            batch = orders_data[i: i + BATCH_LIMIT]
            res = await self._request("POST", "/api/v5/trade/cancel-batch-orders", data=batch)
            if res:
                results.extend(res)
        return results

        # ... (保留原有代码) ...

        # 🔥 新增：获取 K 线数据 (Candlesticks)
    async def get_candlesticks(self, instId: str, bar: str = "1H", limit: int = 100):
        """
        获取 K 线数据
        :param bar: 时间粒度, e.g., 1m, 1H, 4H, 1D
        :return: [[ts, o, h, l, c, vol, ...], ...]
        """
        params = {
            "instId": instId,
            "bar": bar,
            "limit": str(limit)
        }
        # OKX API: GET /api/v5/market/candles
        return await self._request("GET", "/api/v5/market/candles", params=params)

    # ... (保留 batch_orders 等其他接口) ...