"""
🔌 OKXExchange - OKX 交易所实现
================================
继承自 ExchangeBase，实现 OKX V5 API

功能：
- 统一的交易所接口
- Rate Limiting 集成
- Time Synchronization
- 订单管理
- 账户管理
- 持仓管理
- 行情数据
- WebSocket 实时推送
"""

import asyncio
import aiohttp
import hmac
import base64
import json
import urllib.parse
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from exchange.base import ExchangeBase
from core.events import Event, EventType
from core.config_loader import get_config_loader


class OKXExchange(ExchangeBase):
    """
    OKX 交易所实现
    
    继承 ExchangeBase，实现 OKX V5 API 接口
    """

    def __init__(self, config: Dict):
        super().__init__(config)
        
        # 加载配置文件
        config_loader = get_config_loader()
        
        # 从配置文件读取账户信息
        account_config = config_loader.get_account_config()
        sub_account = account_config.get("sub_account", {})
        
        self.api_key = sub_account.get("api_key", "")
        self.secret_key = sub_account.get("api_secret", "")
        self.passphrase = sub_account.get("api_passphrase", "")
        self.sandbox = sub_account.get("sandbox", False)
        
        # 从配置文件读取交易所配置
        exchange_config = config_loader.get_exchange_config()
        okx_config = exchange_config.get("okx", {})
        
        # API 基础 URL
        base_urls = okx_config.get("base_url", {})
        self.base_url = base_urls.get("mainnet", "https://www.okx.com")
        if self.sandbox:
            self.base_url = base_urls.get("testnet", "https://www.okx.com")
        
        # WebSocket URL
        ws_config = okx_config.get("websocket", {})
        self.ws_url = ws_config.get("public_url", "wss://ws.okx.com:8443/ws/v5/public")
        
        # Rate Limits（从配置读取）
        rate_limits_config = okx_config.get("rate_limits", {})
        self._rate_limits_rules = rate_limits_config
        
        # 超时配置（从配置读取）
        timeout_config = okx_config.get("timeout", {})
        self.request_timeout = timeout_config.get("request", 30)
        self.connect_timeout = timeout_config.get("connect", 10)
        
        # 代理配置（从环境变量读取）
        self.proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if self.proxy:
            self.logger.info(f"✅ 使用代理: {self.proxy}")
        
        # Session
        self.session: Optional[aiohttp.ClientSession] = None
        
        # WebSocket
        self.ws_connection = None
        self.ws_task = None
        
        # 事件总线（简单的回调机制）
        self.event_callbacks: Dict[EventType, List] = {
            EventType.TICKER: [],
            EventType.ORDER_BOOK: [],
            EventType.TRADE: [],
            EventType.ORDER_FILLED: [],
            EventType.ORDER_CANCELLED: []
        }
        
        self.logger.info(f"✅ OKXExchange 初始化完成 (Sandbox: {self.sandbox})")

    @property
    def name(self) -> str:
        return "okx"

    @property
    def rate_limits_rules(self) -> Dict:
        return self._rate_limits_rules

    # ========== 认证相关 ==========

    def _get_timestamp(self) -> str:
        """获取 UTC 时间戳"""
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    async def _generate_signature(self, method: str, path: str, params: Dict, timestamp: str) -> str:
        """
        OKX V5 签名
        
        Args:
            method: HTTP 方法
            path: 请求路径
            params: URL 参数
            timestamp: 时间戳
            
        Returns:
            str: Base64 编码的签名
        """
        # OKX V5 签名需要 method + path + body（GET 请求 body 为空）
        body = ""
        if method.upper() == "GET" and params:
            query_string = urllib.parse.urlencode(params)
            path = f"{path}?{query_string}"
        
        message = f"{timestamp}{method.upper()}{path}{body}"
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        return base64.b64encode(mac.digest()).decode()

    def _build_url(self, path: str) -> str:
        """构建请求 URL"""
        return f"{self.base_url}{path}"

    def _build_headers(
        self,
        method: str,
        path: str,
        params: Optional[Dict],
        timestamp: str,
        authenticated: bool
    ) -> Dict:
        """构建请求头"""
        headers = {
            "Content-Type": "application/json",
        }
        
        if authenticated:
            # 构建签名
            body = ""
            if method.upper() == "GET" and params:
                query_string = urllib.parse.urlencode(params)
                path = f"{path}?{query_string}"
            
            sign = self._sign(timestamp, method, path, body)
            
            headers.update({
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": sign,
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": self.passphrase,
            })
            
            if self.sandbox:
                headers["x-simulated-trading"] = "1"
        
        return headers

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """
        OKX V5 签名（内部方法）
        """
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        return base64.b64encode(mac.digest()).decode()

    async def _send_request(
            self,
            method: str,
            url: str,
            headers: Dict,
            params: Optional[Dict]
    ) -> Optional[Dict]:
        """发送 HTTP 请求 - 修复版"""
        if not self.session:
            await self.connect()

        try:
            method = method.upper()
            # 使用配置文件中的超时设置
            timeout = aiohttp.ClientTimeout(total=self.request_timeout, connect=self.connect_timeout)
            
            # 构建请求参数
            request_kwargs = {
                "url": url,
                "timeout": timeout,
                "headers": headers
            }
            
            # 如果配置了代理，则添加代理参数
            if self.proxy:
                request_kwargs["proxy"] = self.proxy
            
            # 根据方法处理参数
            if method == "GET":
                request_kwargs["params"] = params
                async with self.session.get(**request_kwargs) as response:
                    return await self._handle_response(response)
            elif method == "POST":
                request_kwargs["json"] = params
                async with self.session.post(**request_kwargs) as response:
                    return await self._handle_response(response)
            else:
                request_kwargs["data"] = params
                async with self.session.request(method, **request_kwargs) as response:
                    return await self._handle_response(response)

        except asyncio.TimeoutError as e:
            import traceback
            self.logger.error(f"❌ API 请求超时 ({method} {url}): {e}")
            self.logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
            return None
        except Exception as e:
            import traceback
            self.logger.error(f"❌ API 请求异常 ({method} {url}): {e}")
            self.logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
            return None

    async def _handle_response(self, response) -> Optional[Dict]:
        """处理 API 响应"""
        try:
            if response.status != 200:
                text = await response.text()
                self.logger.error(f"API HTTP Error {response.status}: {text}")
                return None
            
            result = await response.json()
            
            if result.get("code") != "0":
                self.logger.error(f"API Business Error: {result}")
                return None
            
            return result.get("data", [])
            
        except Exception as e:
            self.logger.error(f"处理响应失败: {e}")
            return None

    @property
    def _health_check_path(self) -> str:
        """健康检查路径"""
        return "/api/v5/public/time"

    async def authenticate(self):
        """认证"""
        try:
            # 测试连接
            await self.connect()
            
            # 获取账户信息验证
            result = await self.get_trading_balances()
            
            if result is not None:
                self.is_connected = True
                self.logger.info("✅ OKX 认证成功")
                return True
            else:
                self.logger.error("❌ OKX 认证失败")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ OKX 认证异常: {e}")
            return False

    # ========== 连接管理 ==========

    async def connect(self) -> bool:
        """创建 HTTP Session（重写 ExchangeBase 的 connect 方法）"""
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
            self.logger.info("✅ OKX HTTP Session 已创建")
            return True
        except Exception as e:
            self.logger.error(f"❌ OKX 连接失败: {e}")
            return False

    async def disconnect(self):
        """断开连接（重写 ExchangeBase 的 disconnect 方法）"""
        # 关闭 WebSocket
        if self.ws_connection:
            await self.ws_connection.close()
            self.ws_connection = None
        
        # 关闭 HTTP Session
        if self.session:
            await self.session.close()
            self.session = None
        
        self.is_connected = False
        self.logger.info("✅ OKX 已断开连接")

    # ========== 订单管理 ==========

    async def place_order(self, data: Dict) -> Tuple[bool, str, str]:
        """
        下单
        
        Args:
            data: 订单数据
                - symbol: 交易对
                - side: "buy" 或 "sell"
                - size: 数量
                - type: "market" 或 "limit"
                - price: 限价单价格（可选）
        
        Returns:
            (success, order_id, error_msg)
        """
        try:
            # 构建 OKX 订单格式
            order_data = {
                "instId": data.get("symbol"),
                "tdMode": "cross",  # 全仓模式
                "side": data.get("side"),
                "ordType": data.get("type", "market"),
                "sz": str(data.get("size"))
            }
            
            # 限价单需要价格
            if order_data["ordType"] in ["limit", "post_only"]:
                order_data["px"] = str(data.get("price", 0))
            
            self.logger.info(f"⚡ 下单: {order_data}")
            
            # 调用 ExchangeBase 的 _api_request
            # POST 数据通过 params 传递，_send_request 会将其作为 body
            result = await self._api_request("POST", "/api/v5/trade/order", params=order_data, authenticated=True)
            
            if result and len(result) > 0:
                res = result[0]
                s_code = res.get("sCode")
                
                if s_code == "0":
                    order_id = res.get("ordId")
                    self.logger.info(f"✅ 下单成功: {order_id}")
                    return True, order_id, ""
                else:
                    error_msg = f"{res.get('sMsg')} (Code: {s_code})"
                    self.logger.error(f"❌ 下单失败: {error_msg}")
                    return False, "", error_msg
            
            return False, "", "API 返回空数据"
            
        except Exception as e:
            self.logger.error(f"❌ 下单异常: {e}")
            return False, "", str(e)

    async def cancel_order(self, order_id: str, symbol: str) -> Tuple[bool, str, str]:
        """取消订单"""
        try:
            result = await self._api_request("POST", "/api/v5/trade/cancel-order", params={
                "instId": symbol,
                "ordId": order_id
            }, authenticated=True)
            
            if result and len(result) > 0:
                res = result[0]
                if res.get("sCode") == "0":
                    self.logger.info(f"✅ 取消订单成功: {order_id}")
                    return True, order_id, ""
            
            return False, order_id, "取消订单失败"
            
        except Exception as e:
            self.logger.error(f"❌ 取消订单异常: {e}")
            return False, order_id, str(e)

    async def get_order_status(self, order_id: str, symbol: str) -> Optional[Dict]:
        """获取订单状态"""
        try:
            result = await self._api_request("GET", "/api/v5/trade/order", params={
                "instId": symbol,
                "ordId": order_id
            }, authenticated=True)
            
            if result and len(result) > 0:
                return result[0]
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 获取订单状态失败: {e}")
            return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取挂单"""
        try:
            params = {"instType": "SWAP"}
            if symbol:
                params["instId"] = symbol
            
            result = await self._api_request("GET", "/api/v5/trade/orders-pending", params=params, authenticated=True)
            
            return result if result else []
            
        except Exception as e:
            self.logger.error(f"❌ 获取挂单失败: {e}")
            return []

    async def get_order_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取历史订单"""
        try:
            params = {
                "instType": "SWAP",
                "limit": str(limit)
            }
            if symbol:
                params["instId"] = symbol
            
            result = await self._api_request("GET", "/api/v5/trade/orders-history", params=params, authenticated=True)
            
            return result if result else []
            
        except Exception as e:
            self.logger.error(f"❌ 获取历史订单失败: {e}")
            return []

    # ========== 账户管理 ==========

    async def get_trading_balances(self, currency: Optional[str] = None) -> List[Dict]:
        """获取交易账户余额"""
        try:
            result = await self._api_request("GET", "/api/v5/account/balance", authenticated=True)
            
            if result and len(result) > 0:
                balances = result[0].get("details", [])
                if currency:
                    return [b for b in balances if b.get("ccy") == currency]
                return balances
            
            return []
            
        except Exception as e:
            self.logger.error(f"❌ 获取余额失败: {e}")
            return []

    async def get_funding_balances(self, currency: Optional[str] = None) -> List[Dict]:
        """获取资金账户余额"""
        try:
            params = {}
            if currency:
                params["ccy"] = currency
            
            result = await self._api_request("GET", "/api/v5/asset/balances", params=params, authenticated=True)
            
            return result if result else []
            
        except Exception as e:
            self.logger.error(f"❌ 获取资金余额失败: {e}")
            return []

    async def transfer_funds(self, currency: str, amount: float, from_account: str, to_account: str) -> bool:
        """资金划转"""
        try:
            result = await self._api_request("POST", "/api/v5/asset/transfer", params={
                "ccy": currency,
                "amt": str(amount),
                "from": from_account,
                "to": to_account
            }, authenticated=True)
            
            return bool(result)
            
        except Exception as e:
            self.logger.error(f"❌ 资金划转失败: {e}")
            return False

    # ========== 持仓管理 ==========

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取持仓"""
        try:
            params = {"instType": "SWAP"}
            if symbol:
                params["instId"] = symbol
            
            result = await self._api_request("GET", "/api/v5/account/positions", params=params, authenticated=True)
            
            return result if result else []
            
        except Exception as e:
            self.logger.error(f"❌ 获取持仓失败: {e}")
            return []

    async def get_position(self, symbol: str) -> Optional[Dict]:
        """获取单个持仓"""
        positions = await self.get_positions(symbol)
        
        for pos in positions:
            if pos.get("instId") == symbol:
                return pos
        
        return None

    async def set_leverage(self, data: Dict) -> bool:
        """设置杠杆"""
        try:
            result = await self._api_request("POST", "/api/v5/account/set-leverage", params={
                "instId": data.get("symbol"),
                "lever": str(data.get("leverage")),
                "mgnMode": "cross"
            }, authenticated=True)
            
            return bool(result)
            
        except Exception as e:
            self.logger.error(f"❌ 设置杠杆失败: {e}")
            return False

    # ========== 行情数据 ==========

    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """获取行情"""
        try:
            result = await self._api_request("GET", "/api/v5/market/ticker", params={
                "instId": symbol
            })
            
            if result and len(result) > 0:
                return result[0]
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 获取行情失败: {e}")
            return None

    async def get_order_book(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """获取订单簿"""
        try:
            result = await self._api_request("GET", "/api/v5/market/books", params={
                "instId": symbol,
                "sz": str(depth)
            })
            
            if result and len(result) > 0:
                return result[0]
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 获取订单簿失败: {e}")
            return None

    async def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """获取成交记录"""
        try:
            result = await self._api_request("GET", "/api/v5/market/trades", params={
                "instId": symbol,
                "limit": str(limit)
            })
            
            return result if result else []
            
        except Exception as e:
            self.logger.error(f"❌ 获取成交记录失败: {e}")
            return []

    async def get_candlesticks(self, symbol: str, bar: str = "1m", limit: int = 100) -> List[Dict]:
        """获取 K 线"""
        try:
            result = await self._api_request("GET", "/api/v5/market/candles", params={
                "instId": symbol,
                "bar": bar,
                "limit": str(limit)
            })
            
            return result if result else []
            
        except Exception as e:
            self.logger.error(f"❌ 获取 K 线失败: {e}")
            return []

    # ========== WebSocket 实时行情 ==========

    async def start_websocket(self, symbols: List[str]):
        """
        启动 WebSocket 实时行情
        
        Args:
            symbols: 订阅的交易对列表
        """
        if self.ws_connection:
            self.logger.warning("⚠️ WebSocket 已连接")
            return
        
        try:
            self.ws_connection = await aiohttp.ClientSession().ws_connect(self.ws_url)
            
            # 订阅行情
            subscribe_msg = {
                "op": "subscribe",
                "args": [{"channel": f"tickers", "instId": sym} for sym in symbols]
            }
            
            await self.ws_connection.send_str(json.dumps(subscribe_msg))
            
            # 启动接收任务
            self.ws_task = asyncio.create_task(self._ws_message_handler())
            
            self.logger.info(f"✅ WebSocket 已启动，订阅 {len(symbols)} 个交易对")
            
        except Exception as e:
            self.logger.error(f"❌ WebSocket 启动失败: {e}")

    async def _ws_message_handler(self):
        """处理 WebSocket 消息"""
        try:
            async for msg in self.ws_connection:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # 处理行情数据
                    if data.get("data"):
                        await self._on_ticker_message(data["data"][0])
                    
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"❌ WebSocket 错误: {msg.data}")
                    break
                    
        except Exception as e:
            self.logger.error(f"❌ WebSocket 消息处理异常: {e}")

    async def _on_ticker_message(self, data: Dict):
        """处理行情消息"""
        try:
            # 发布事件
            event = Event(
                event_type=EventType.TICKER,
                params={
                    "symbol": data.get("instId"),
                    "last_price": float(data.get("last", 0)),
                    "timestamp": int(data.get("ts", 0))
                }
            )
            
            # 触发回调
            for callback in self.event_callbacks[EventType.TICKER]:
                try:
                    await callback(event)
                except Exception as e:
                    self.logger.error(f"❌ 行情回调失败: {e}")
                    
        except Exception as e:
            self.logger.error(f"❌ 处理行情消息失败: {e}")

    # ========== 事件回调 ==========

    def add_event_callback(self, event_type: EventType, callback):
        """添加事件回调"""
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type].append(callback)

    def remove_event_callback(self, event_type: EventType, callback):
        """移除事件回调"""
        if event_type in self.event_callbacks and callback in self.event_callbacks[event_type]:
            self.event_callbacks[event_type].remove(callback)


# 导出
__all__ = ["OKXExchange"]
