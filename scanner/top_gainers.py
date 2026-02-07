from loguru import logger
from datetime import datetime, timezone


class TopGainersScanner:
    def __init__(self, client):
        self.client = client

    def get_top_gainers(self, limit=10):
        tickers = self.client.market.get_tickers(instType="SWAP")
        data = tickers["data"]

        result = []
        for item in data:
            if not item["instId"].endswith("USDT-SWAP"):
                continue

            open_px = float(item["open24h"])
            last_px = float(item["last"])
            high = float(item["high24h"])
            low = float(item["low24h"])

            if open_px <= 0 or high <= low:
                continue

            change = (last_px - open_px) / open_px
            position = (last_px - low) / (high - low)

            result.append({
                "instId": item["instId"],
                "change": change,
                "position": position,
                "last": last_px,
                "high": high,
                "low": low,
            })

        result.sort(key=lambda x: x["change"], reverse=True)
        top = result[:limit]

        logger.info("=== Top Gainers (24h Context) ===")
        for r in top:
            logger.info(
                f"{r['instId']} | "
                f"24小时涨跌{r['change'] * 100:.2f}% | "
                f"价格位置{r['position'] * 100:.1f}% | "
                f"最新价格{r['last']} | "
                f"最高{r['high']} | 最低{r['low']}"
            )

        return top
