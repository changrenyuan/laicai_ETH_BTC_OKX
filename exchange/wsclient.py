import asyncio
import json
import threading
import ssl
import certifi
import websockets
from loguru import logger
import hmac, base64, hashlib, time

class SimpleWsClient:
    def __init__(self, url, callback, api_key=None, secret_key=None, passphrase=None):
        """
        :param url: WebSocket 地址
        :param callback: 收到数据后的回调函数 (同步函数)
        """
        self.url = url
        self.callback = callback
        self._subscriptions = []
        self.loop = None
        self.ws = None
        self.is_running = False
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        # SSL 配置
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.load_verify_locations(certifi.where())

    def _get_signature(self, timestamp):
        """生成 OKX WebSocket 登录签名"""
        message = str(timestamp) + "GET" + "/users/self/verify"
        mac = hmac.new(bytes(self.secret_key, encoding='utf8'),
                       bytes(message, encoding='utf8'), digestmod=hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    async def _login(self):
        """执行鉴权登录"""
        if not self.api_key: return
        timestamp = int(time.time())
        login_msg = {
            "op": "login",
            "args": [{
                "apiKey": self.api_key,
                "passphrase": self.passphrase,
                "timestamp": timestamp,
                "sign": self._get_signature(timestamp)
            }]
        }
        await self.ws.send(json.dumps(login_msg))
        logger.info(f"🔑 WS 发起登录鉴权: {self.url}")
    async def _run(self):
        """异步主循环，负责连接、订阅和监听"""
        while True:
            try:
                async with websockets.connect(
                    self.url,
                    ssl=self.ssl_context,
                    ping_interval=20,
                    ping_timeout=10
                ) as ws:
                    self.ws = ws
                    self.is_running = True
                    logger.success(f"OKX WebSocket 已连接: {self.url}")
                    # 私有地址需要先登录
                    if "/private" in self.url:
                        await self._login()
                        await asyncio.sleep(1)  # 等待登录响应
                    # 如果有存量订阅，自动重连订阅
                    if self._subscriptions:
                        sub_msg = {"op": "subscribe", "args": self._subscriptions}
                        await self.ws.send(json.dumps(sub_msg))
                        logger.info(f"WebSocket 自动重连订阅: {self._subscriptions}")

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            # 将异步收到的数据交给同步回调处理
                            self.callback(data)
                        except Exception as e:
                            logger.error(f"WS 数据处理异常: {e}")

            except Exception as e:
                self.is_running = False
                self.ws = None
                logger.error(f"WebSocket 连接异常: {e}，5秒后尝试重连...")
                await asyncio.sleep(5)

    def _start_loop(self):
        """启动独立的 asyncio 事件循环"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._run())

    def start(self):
        """同步启动接口：开启后台线程运行异步任务"""
        thread = threading.Thread(target=self._start_loop, daemon=True)
        thread.start()
        logger.info("WebSocket 后台异步线程已启动")

    def subscribe(self, args):
        """
        同步订阅接口：从外部调用，将订阅指令推送到异步循环中
        :param args: list, 例如 [{"channel": "tickers", "instId": "BTC-USDT-SWAP"}]
        """
        self._subscriptions.extend(args)
        if self.ws and self.is_running:
            # 使用 loop.create_task 在异步线程中执行发送任务
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({"op": "subscribe", "args": args})),
                self.loop
            )
            logger.info(f"WebSocket 订阅指令已发送: {args}")
        else:
            logger.warning("WebSocket 尚未就绪，订阅任务已存入缓存待重连")