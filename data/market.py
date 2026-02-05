from loguru import logger


class MarketService:
    def __init__(self, client):
        self.client = client

    def fetch_prices(self, symbols: list[str]) -> dict:
        prices = {}
        for symbol in symbols:
            ticker = self.client.get_ticker(symbol)
            prices[symbol] = {
                "last": float(ticker["last"]),
                "bid": float(ticker["bidPx"]),
                "ask": float(ticker["askPx"]),
                "ts": int(ticker["ts"]),
            }
            logger.info(
                f"{symbol} | last={prices[symbol]['last']} "
                f"bid买一价格={prices[symbol]['bid']} ask卖一价格={prices[symbol]['ask']}"
            )
        return prices
