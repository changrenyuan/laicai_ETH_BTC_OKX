import sys
import time
import threading
from collections import deque
from okx import MarketData, Account, Trade, PublicData

from config.config import configpara
# 导入 WebSocket 模块 (需确保已安装 python-okx)
from exchange.wsclient import SimpleWsClient
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class OKXClient:
    def __init__(self, api_key, secret_key, passphrase, flag="0", rps_limit=10):
        # --- 新增：主动限流逻辑 (Token Bucket 简化版) ---
        self.rps_limit = rps_limit
        self.request_times = deque(maxlen=rps_limit)
        self.lock = threading.Lock()

        # --- 新增：WebSocket 行情缓存 ---
        self.price_cache = {}
        self._ws_client = None

        self.market = MarketData.MarketAPI(flag=flag)
        self.public = PublicData.PublicAPI(flag=flag)
        # 1. 账户模块：用于查余额、设杠杆
        self.account = Account.AccountAPI(
            api_key=api_key,
            api_secret_key=secret_key,
            passphrase=passphrase,
            flag=flag
        )
        # 2. 交易模块：用于下单、撤单 (关键修改)
        self.trade = Trade.TradeAPI(
            api_key=api_key,
            api_secret_key=secret_key,
            passphrase=passphrase,
            flag=flag
        )
        # logger.add(sys.stderr, level=configpara.console_LOG_LEVEL)

        # --- 新增：连接池配置 ---
        # 理由：SDK 默认连接池较小。在高并发请求时，通过修改底层 requests session 提升吞吐量。
        # for api in [self.market, self.public, self.account, self.trade]:
        #     adapter = api.session.get_adapter('https://')
        #     adapter._pool_connections = 20  # 增加连接池
        #     adapter._pool_maxsize = 20

    # --- 源代码注释掉 (逻辑已整合进 _request) ---
    # def get_ticker(self, inst_id: str) -> dict:
    #     """获取最新行情"""
    #     result = self.market.get_ticker(instId=inst_id)
    #     if result.get("code") != "0":
    #         raise RuntimeError(f"Ticker error: {result}")
    #     return result["data"][0]

    # --- 新版行情获取 (优先 WebSocket，无则 REST) ---
    def get_ticker(self, inst_id: str) -> dict:
        """
        改进理由：优先从 WebSocket 缓存获取，降低延迟。如果缓存无数据，则降级使用 REST 请求。
        """
        if inst_id in self.price_cache:
            return self.price_cache[inst_id]

        # 降级方案：REST 请求
        data = self._request(self.market.get_ticker, instId=inst_id)
        return data[0] if data else {}

    # --- 源代码注释掉 ---
    # def get_account_balance(self) -> dict:
    #     """获取账户余额"""
    #     result = self.account.get_account_balance()
    #     if result.get("code") != "0":
    #         raise RuntimeError(f"Balance error: {result}")
    #     return result["data"][0]

    def get_account_balance(self) -> dict:
        """改进理由：通过统一的 _request 实现全局重试和主动限流"""
        data = self._request(self.account.get_account_balance)
        return data[0] if data else {}

    # --- 源代码注释掉 ---
    # def get_instrument_info(self, inst_id: str):
    #     """获取产品精度、最小下单量等信息"""
    #     result = self.public.get_instruments(instType="SWAP", instId=inst_id)
    #     if result.get("code") == "0":
    #         return result["data"][0]
    #     return None

    def get_instrument_info(self, inst_id: str):
        """改进理由：统一 API 接口调用规范"""
        data = self._request(self.public.get_instruments, instType="SWAP", instId=inst_id)
        return data[0] if data else None

    # --- 源代码注释掉 ---
    # def place_limit_order(self, instId, side, px, sz):
    #     return self.trade.place_order(
    #         instId=instId,
    #         tdMode="cross",
    #         side=side,
    #         ordType="limit",
    #         px=str(px),
    #         sz=str(sz)
    #     )

    def place_limit_order(self, instId, side, px, sz):
        """改进理由：统一参数转换与主动流控"""
        return self._request(
            self.trade.place_order,
            instId=instId,
            tdMode="cross",
            side=side,
            ordType="limit",
            px=str(px),
            sz=str(sz)
        )

    # --- 新增：核心请求包装器 (实现全局重试与主动避限) ---
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(RuntimeError)
    )
    def _request(self, func, *args, **kwargs):
        """
        改进理由：
        1. 这里的 @retry 应用于所有方法。
        2. 内部实现了主动限流逻辑（Rate Limiting）。
        """
        # 主动限流：检查 RPS
        with self.lock:
            now = time.time()
            if len(self.request_times) >= self.rps_limit:
                wait_time = 1.0 - (now - self.request_times[0])
                if wait_time > 0:
                    logger.debug(f"主动流控：等待 {wait_time:.2f}s")
                    time.sleep(wait_time)
            self.request_times.append(time.time())

        # 执行请求
        res = func(*args, **kwargs)
        if res.get("code") != "0":
            logger.error(f"OKX API 原始错误详情: {res}")  # <-- 添加这一行

        if res.get("code") == "0":
            return res.get("data")

        # 被动处理限流
        if res.get("code") == "50011":
            logger.warning("触发 50011 限流，触发重试...")

        raise RuntimeError(f"OKX API 错误: {res}")

    # --- 新增：WebSocket 相关功能 ---
    def init_websocket(self, inst_ids: list):
        """
        改进理由：实现实时行情获取，降低 get_ticker 延迟。
        """

        def _handle_ticker(message):
            if "data" in message:
                for entry in message["data"]:
                    self.price_cache[entry["instId"]] = entry
                    # --- 🔥 新增：实时行情打印 (DEBUG 级别) ---
                    try:
                        inst_id = entry.get("instId")
                        last_px = entry.get("last")  # 最新成交价
                        ask_px = entry.get("askPx")  # 卖一价
                        bid_px = entry.get("bidPx")  # 买一价
                        vol_24h = entry.get("vol24h")  # 24h 成交量 (币)
                        open_24h = float(entry.get("open24h", 0))

                        # 计算 24h 涨跌幅
                        change_pct = 0.0
                        if open_24h != 0:
                            change_pct = (float(last_px) - open_24h) / open_24h * 100

                        logger.debug(
                            f"⚡ [WS 行情] {inst_id} | "
                            f"最新:{last_px} | "
                            f"买一/卖一:{bid_px}/{ask_px} | "
                            f"24h量:{vol_24h} | "
                            f"涨跌幅:{change_pct:+.2f}%"
                        )
                    except Exception as e:
                        # 捕获可能的转换错误，不影响主缓存逻辑
                        logger.warning(f"行情解析显示异常: {e}")
######################################################################

        url = "wss://wspap.okx.com:443/ws/v5/public" if self.market.flag == "1" else "wss://ws.okx.com:443/ws/v5/public"
        self._ws_client = SimpleWsClient(url, _handle_ticker)
        self._ws_client.start()
        # 等待连接建立的小缓冲
        time.sleep(1)

        # 订阅行情
        args = [{"channel": "tickers", "instId": i} for i in inst_ids]
        self._ws_client.subscribe(args)
        logger.info(f"WebSocket 已启动并订阅: {inst_ids}")

    # --- 原有增强函数整合 ---
    def cancel_order(self, inst_id: str, ord_id: str):
        return self._request(self.trade.cancel_order, instId=inst_id, ordId=ord_id)

    def get_positions(self, inst_id: str = None):
        kwargs = {"instType": "SWAP"}
        if inst_id: kwargs["instId"] = inst_id
        return self._request(self.account.get_positions, **kwargs)

    def set_leverage(self, inst_id: str, lever: int, mgn_mode: str = "cross"):
        return self._request(
            self.account.set_leverage,
            instId=inst_id,
            lever=str(lever),
            mgnMode=mgn_mode
        )