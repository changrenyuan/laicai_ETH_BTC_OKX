"""
🔌 市场数据获取
行情 / 资金费率
"""

from typing import Optional, List
import logging
from datetime import datetime

from core.context import MarketData
from exchange.okx_client import OKXClient


class MarketDataFetcher:
    """
    市场数据获取器
    从交易所获取行情和资金费率数据
    """

    def __init__(self, okx_client: OKXClient, config: dict):
        self.okx_client = okx_client
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """
        获取市场数据

        Args:
            symbol: 交易品种（如 BTC-USDT）

        Returns:
            MarketData: 市场数据对象
        """
        try:
            # 获取现货价格
            spot_ticker = await self.okx_client.get_ticker(symbol)
            if not spot_ticker:
                return None

            spot_price = float(spot_ticker[0].get("last", 0))

            # 获取合约价格
            futures_symbol = f"{symbol}-SWAP"
            futures_ticker = await self.okx_client.get_ticker(futures_symbol)
            if not futures_ticker:
                return None

            futures_price = float(futures_ticker[0].get("last", 0))

            # 获取资金费率
            funding_rate_data = await self.okx_client.get_funding_rate(futures_symbol)
            if not funding_rate_data:
                return None

            funding_rate = float(funding_rate_data[0].get("fundingRate", 0))
            next_funding_time_str = funding_rate_data[0].get("nextFundingTime")

            next_funding_time = None
            if next_funding_time_str:
                try:
                    next_funding_time = datetime.fromisoformat(next_funding_time_str.replace("Z", "+00:00"))
                except:
                    pass

            # 获取订单簿深度
            order_book = await self.okx_client.get_order_book(futures_symbol, sz=1)
            depth = {}

            if order_book and len(order_book) > 0:
                bids = order_book[0].get("bids", [])
                asks = order_book[0].get("asks", [])

                if bids:
                    depth["bid_1_price"] = float(bids[0][0])
                    depth["bid_1_amount"] = float(bids[0][1])

                if asks:
                    depth["ask_1_price"] = float(asks[0][0])
                    depth["ask_1_amount"] = float(asks[0][1])

            # 获取24h成交量
            volume_24h = float(futures_ticker[0].get("volCcy24h", 0))

            # 构建市场数据对象
            market_data = MarketData(
                symbol=symbol,
                spot_price=spot_price,
                futures_price=futures_price,
                funding_rate=funding_rate,
                next_funding_time=next_funding_time,
                volume_24h=volume_24h,
                depth=depth,
            )

            self.logger.info(
                f"Market data for {symbol}: "
                f"spot=${spot_price:.2f}, futures=${futures_price:.2f}, "
                f"funding={funding_rate:.4%}"
            )

            return market_data

        except Exception as e:
            self.logger.error(f"Failed to get market data for {symbol}: {e}")
            return None

    async def get_multiple_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        """
        获取多个品种的市场数据

        Args:
            symbols: 交易品种列表

        Returns:
            dict: {symbol: MarketData}
        """
        market_data_dict = {}

        for symbol in symbols:
            data = await self.get_market_data(symbol)
            if data:
                market_data_dict[symbol] = data

        return market_data_dict

    async def get_funding_rate_history(
        self,
        symbol: str,
        limit: int = 10,
    ) -> list[dict]:
        """
        获取资金费率历史

        Args:
            symbol: 交易品种
            limit: 数量

        Returns:
            list: 资金费率历史
        """
        try:
            futures_symbol = f"{symbol}-SWAP"
            result = await self.okx_client.get_funding_rate(futures_symbol)

            if not result:
                return []

            # 转换为标准格式
            history = []
            for item in result[:limit]:
                history.append({
                    "timestamp": item.get("fundingTime"),
                    "funding_rate": float(item.get("fundingRate", 0)),
                })

            return history

        except Exception as e:
            self.logger.error(f"Failed to get funding rate history for {symbol}: {e}")
            return []

    async def get_all_tickers(self) -> List[dict]:
        """
        获取所有永续合约的 Ticker 数据

        Returns:
            List[Dict]: Ticker 数据列表
        """
        try:
            result = await self.okx_client._request("GET", "/api/v5/market/tickers", params={"instType": "SWAP"})

            if not result or len(result) == 0:
                self.logger.error("获取 Ticker 数据失败")
                return []

            # 过滤 USDT 永续合约
            tickers = []
            for ticker in result:
                inst_id = ticker.get("instId", "")
                if inst_id.endswith("-USDT-SWAP"):
                    # 添加标准化字段
                    tickers.append({
                        "instId": inst_id,
                        "last": ticker.get("last", 0),
                        "high24h": ticker.get("high24h", 0),
                        "low24h": ticker.get("low24h", 0),
                        "open24h": ticker.get("open24h", 0),
                        "volCcy": ticker.get("volCcy", 0),
                        "volCcy24h": ticker.get("volCcy24h", 0),
                        "ts": ticker.get("ts", 0),
                    })

            self.logger.info(f"获取到 {len(tickers)} 个 Ticker 数据")
            return tickers

        except Exception as e:
            self.logger.error(f"获取 Ticker 数据失败: {e}")
            return []

    async def get_tickers_by_symbols(self, symbols: List[str]) -> List[dict]:
        """
        根据交易对列表获取 Ticker 数据

        Args:
            symbols: 交易对列表（如 ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]）

        Returns:
            List[Dict]: Ticker 数据列表
        """
        try:
            # 批量获取 Ticker
            inst_ids = ",".join(symbols)
            result = await self.okx_client._request("GET", "/api/v5/market/tickers", params={"instType": "SWAP", "instId": inst_ids})

            if not result or len(result) == 0:
                self.logger.error("获取 Ticker 数据失败")
                return []

            # 添加标准化字段
            tickers = []
            for ticker in result:
                tickers.append({
                    "instId": ticker.get("instId", ""),
                    "last": ticker.get("last", 0),
                    "high24h": ticker.get("high24h", 0),
                    "low24h": ticker.get("low24h", 0),
                    "open24h": ticker.get("open24h", 0),
                    "volCcy": ticker.get("volCcy", 0),
                    "volCcy24h": ticker.get("volCcy24h", 0),
                    "ts": ticker.get("ts", 0),
                })

            self.logger.info(f"获取到 {len(tickers)} 个 Ticker 数据")
            return tickers

        except Exception as e:
            self.logger.error(f"获取 Ticker 数据失败: {e}")
            return []
