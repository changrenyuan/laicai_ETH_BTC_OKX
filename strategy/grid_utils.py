"""
🧠 网格策略工具箱 (AI Math Core)
负责技术指标计算 (ATR, Bollinger Bands) 和网格线生成
"""
import numpy as np
import pandas as pd


class GridUtils:

    @staticmethod
    def calculate_bollinger_bands(klines: list, period: int = 20, std_dev: float = 2.0):
        """
        计算布林带 (用于确定网格上下限)
        :param klines: OKX K线数据 [[ts, o, h, l, c, ...], ...]
        :return: (upper_band, lower_band, current_price)
        """
        # 1. 转换为 Pandas DataFrame
        df = pd.DataFrame(klines, columns=["ts", "o", "h", "l", "c", "vol", "volCcy", "volCcyQuote", "confirm"])
        df["c"] = df["c"].astype(float)

        # 2. 按照时间正序排列 (OKX 返回是倒序的)
        df = df.iloc[::-1].reset_index(drop=True)

        # 3. 计算 SMA (中轨) 和 STD (标准差)
        df["sma"] = df["c"].rolling(window=period).mean()
        df["std"] = df["c"].rolling(window=period).std()

        # 4. 计算上下轨
        df["upper"] = df["sma"] + (df["std"] * std_dev)
        df["lower"] = df["sma"] - (df["std"] * std_dev)

        # 5. 获取最新值
        latest = df.iloc[-1]

        return float(latest["upper"]), float(latest["lower"]), float(latest["c"])

    @staticmethod
    def calculate_atr(klines: list, period: int = 14):
        """
        计算 ATR (用于动态确定网格密度/止损位)
        """
        df = pd.DataFrame(klines, columns=["ts", "o", "h", "l", "c", "vol", "volCcy", "volCcyQuote", "confirm"])
        df[["h", "l", "c"]] = df[["h", "l", "c"]].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)

        df['tr0'] = abs(df['h'] - df['l'])
        df['tr1'] = abs(df['h'] - df['c'].shift())
        df['tr2'] = abs(df['l'] - df['c'].shift())
        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=period).mean()

        return float(df.iloc[-1]['atr'])

    @staticmethod
    def generate_grid_lines(lower: float, upper: float, count: int, mode: str = "arithmetic"):
        """
        生成网格价格线
        """
        if lower >= upper:
            raise ValueError(f"网格下限 {lower} >= 上限 {upper}")

        if mode == "arithmetic":
            # 等差数列
            return [round(x, 4) for x in np.linspace(lower, upper, count + 1).tolist()]
        elif mode == "geometric":
            # 等比数列
            return [round(x, 4) for x in np.geomspace(lower, upper, count + 1).tolist()]
        else:
            return []