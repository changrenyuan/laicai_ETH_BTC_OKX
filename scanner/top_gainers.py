from loguru import logger
from datetime import datetime, timezone


class TopGainersScanner:
    def __init__(self, client):
        self.client = client

    def get_top_gainers(self, limit=10):
        """
        获取 USDT 永续当日涨幅最大的合约
        """
        tickers = self.client.market.get_tickers(instType="SWAP")
        data = tickers["data"]

        result = []
        for item in data:
            if not item["instId"].endswith("USDT-SWAP"):
                continue

            open_px = float(item["open24h"])
            last_px = float(item["last"])
            if open_px <= 0:
                continue

            change = (last_px - open_px) / open_px
            result.append({
                "instId": item["instId"],
                "change": change,
                "last": last_px,
            })

        result.sort(key=lambda x: x["change"], reverse=True)
        top = result[:limit]

        logger.info("Top gainers:")
        for r in top:
            logger.info(f"{r['instId']} | {r['last']} | {r['change']*100:.2f}%")

        return top
