import time
from loguru import logger
from typing import Dict, List, Optional


class MarketService:
    def __init__(self, client):
        """
        :param client: OKXClient 实例
        """
        self.client = client
        # 数据有效性窗口 (秒)，超过这个时间的数据被视为陈旧数据
        self.max_latency = 10.0

    def fetch_prices(self, symbols: list[str]) -> Dict[str, dict]:
        """
        批量获取最新价格（带验证机制）
        """
        prices = {}
        now_ts = int(time.time() * 1000)

        for symbol in symbols:
            try:
                # 调用 OKXClient 的 get_ticker (优先读 WS 缓存)
                ticker = self.client.get_ticker(symbol)

                if not ticker:
                    logger.warning(f"行情缺失: {symbol}")
                    continue

                # --- 1. 数据解析 ---
                last_price = float(ticker.get("last", 0))
                bid_price = float(ticker.get("bidPx", 0))
                ask_price = float(ticker.get("askPx", 0))
                ts = int(ticker.get("ts", 0))

                # --- 2. 核心数据验证 ---
                # 检查价格是否正常
                if last_price <= 0:
                    logger.error(f"价格异常 {symbol}: last={last_price}")
                    continue

                # 检查数据时效性 (防止 WebSocket 卡死导致一直读取旧数据)
                latency = now_ts - ts
                if latency > (self.max_latency * 1000):
                    logger.warning(f"行情严重滞后 {symbol}: 延迟 {latency}ms")
                    # 在高频策略中，这里应该 continue 跳过，但趋势策略可暂时放宽

                prices[symbol] = {
                    "last": last_price,
                    "bid": bid_price,
                    "ask": ask_price,
                    "ts": ts,
                    "vol_24h": float(ticker.get("vol24h", 0))  # 新增：24h成交量
                }

                logger.info(
                    f"{symbol} | 最新价={last_price} | 买一={bid_price} | 卖一={ask_price} | 延迟={latency}ms"
                )

            except Exception as e:
                logger.error(f"获取 {symbol} 行情失败: {e}")

        return prices

    def get_history_candles(self, symbol: str, bar: str = "1m", limit: int = 100) -> List[dict]:
        """
        获取 K 线数据 (用于计算 MA, RSI 等指标)
        :param bar: 时间粒度, e.g., '1m', '5m', '1H', '1D'
        """
        try:
            # 复用 OKXClient 的 _request 方法以获得重试保护
            # 注意：get_candlesticks 属于 market 模块
            response = self.client._request(
                self.client.market.get_candlesticks,
                instId=symbol,
                bar=bar,
                limit=str(limit)
            )

            # OKX 返回格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            candles = []
            if response:
                for row in response:
                    candles.append({
                        "ts": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "vol": float(row[5])
                    })
                # 列表通常是倒序的（最新的在前面），按需反转
                # candles.reverse() 
            return candles

        except Exception as e:
            logger.error(f"获取 K 线失败 {symbol}: {e}")
            return []

    def get_orderbook(self, symbol: str, depth: int = 5) -> Optional[dict]:
        """
        获取深度盘口 (用于精确计算滑点或挂单位置)
        :param depth: 获取几档深度 (1, 5, 50, 400)
        """
        try:
            response = self.client._request(
                self.client.market.get_books,
                instId=symbol,
                sz=str(depth)
            )
            if response and response[0]:
                data = response[0]
                return {
                    "asks": [[float(p), float(s)] for p, s, _ in data["asks"]],  # 卖盘 [价格, 数量]
                    "bids": [[float(p), float(s)] for p, s, _ in data["bids"]],  # 买盘 [价格, 数量]
                    "ts": int(data["ts"])
                }
            return None
        except Exception as e:
            logger.error(f"获取深度失败 {symbol}: {e}")
            return None