"""
📊 Technical Indicators - 技术指标计算工具
===========================================
提供常用的技术指标计算函数，避免代码重复
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple


def calculate_ema(df: pd.DataFrame, period: int, price_col: str = "close") -> pd.Series:
    """
    计算指数移动平均线 (EMA)

    Args:
        df: K线 DataFrame
        period: 周期
        price_col: 价格列名

    Returns:
        pd.Series: EMA 值
    """
    return df[price_col].ewm(span=period, adjust=False).mean()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算真实波幅 (ATR)

    Args:
        df: K线 DataFrame (需要 open, high, low, close 列)
        period: 周期

    Returns:
        pd.Series: ATR 值
    """
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()


def calculate_rsi(df: pd.DataFrame, period: int = 14, price_col: str = "close") -> pd.Series:
    """
    计算相对强弱指标 (RSI)

    Args:
        df: K线 DataFrame
        period: 周期
        price_col: 价格列名

    Returns:
        pd.Series: RSI 值
    """
    delta = df[price_col].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2,
    price_col: str = "close"
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算布林带

    Args:
        df: K线 DataFrame
        period: 周期
        std_dev: 标准差倍数
        price_col: 价格列名

    Returns:
        Tuple: (上轨, 中轨, 下轨)
    """
    sma = df[price_col].rolling(window=period).mean()
    rolling_std = df[price_col].rolling(window=period).std()
    upper_band = sma + (rolling_std * std_dev)
    lower_band = sma - (rolling_std * std_dev)
    return upper_band, sma, lower_band


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算平均趋向指数 (ADX)

    Args:
        df: K线 DataFrame (需要 open, high, low, close 列)
        period: 周期

    Returns:
        pd.Series: ADX 值
    """
    # 计算 +DM 和 -DM
    df["+dm"] = np.where(
        (df["high"] - df["high"].shift(1)) > (df["low"].shift(1) - df["low"]),
        np.maximum(df["high"] - df["high"].shift(1), 0),
        0,
    )
    df["-dm"] = np.where(
        (df["low"].shift(1) - df["low"]) > (df["high"] - df["high"].shift(1)),
        np.maximum(df["low"].shift(1) - df["low"], 0),
        0,
    )

    # 平滑 +DM, -DM, TR
    df["+dm_smooth"] = df["+dm"].rolling(window=period).mean()
    df["-dm_smooth"] = df["-dm"].rolling(window=period).mean()

    # 计算 ATR（如果没有）
    if "atr" not in df.columns:
        df["atr"] = calculate_atr(df, period)

    # 计算 +DI 和 -DI
    df["+di"] = 100 * (df["+dm_smooth"] / df["atr"].replace(0, np.nan))
    df["-di"] = 100 * (df["-dm_smooth"] / df["atr"].replace(0, np.nan))

    # 计算 DX
    df["dx"] = 100 * np.abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"]).replace(0, np.nan)

    # 平滑 DX 得到 ADX
    return df["dx"].rolling(window=period).mean()


def calculate_macd(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    price_col: str = "close"
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算 MACD

    Args:
        df: K线 DataFrame
        fast_period: 快线周期
        slow_period: 慢线周期
        signal_period: 信号线周期
        price_col: 价格列名

    Returns:
        Tuple: (MACD, Signal, Histogram)
    """
    ema_fast = df[price_col].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df[price_col].ewm(span=slow_period, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram


def calculate_volume_profile(df: pd.DataFrame, bins: int = 20) -> Dict:
    """
    计算成交量分布

    Args:
        df: K线 DataFrame
        bins: 价格区间数量

    Returns:
        Dict: 成交量分布数据
    """
    price_range = df["high"].max() - df["low"].min()
    step = price_range / bins if price_range > 0 else 1

    volume_profile = []
    for i in range(bins):
        lower_price = df["low"].min() + i * step
        upper_price = lower_price + step

        # 计算该价格区间的成交量
        mask = ((df["low"] >= lower_price) & (df["high"] <= upper_price)) | \
               ((df["low"] < lower_price) & (df["high"] > lower_price)) | \
               ((df["low"] < upper_price) & (df["high"] > upper_price))

        volume = df[mask]["volume"].sum()
        avg_price = df[mask]["close"].mean() if volume > 0 else (lower_price + upper_price) / 2

        volume_profile.append({
            "lower_price": lower_price,
            "upper_price": upper_price,
            "volume": volume,
            "avg_price": avg_price,
        })

    return {
        "volume_profile": volume_profile,
        "poc": max(volume_profile, key=lambda x: x["volume"])["avg_price"] if volume_profile else 0,
    }


def normalize_klines(klines: List[Dict]) -> pd.DataFrame:
    """
    标准化 K 线数据为 DataFrame

    Args:
        klines: K线数据列表，每个元素包含：
            - t/o/h/l/c/vol: 时间/开/高/低/收/量

    Returns:
        pd.DataFrame: 标准化的 DataFrame
    """
    df = pd.DataFrame(klines)
    df.columns = ["timestamp", "open", "high", "low", "close", "volume", "vol_ccy", "vol_ccy_quote", "confirm"]

    # 转换为数值类型
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def calculate_all_indicators(
    klines: List[Dict],
    adx_period: int = 14,
    atr_period: int = 14,
    ema_period: int = 20,
    rsi_period: int = 14,
    bollinger_period: int = 20,
    bollinger_std: float = 2,
) -> Dict:
    """
    一次性计算所有技术指标

    Args:
        klines: K线数据
        adx_period: ADX 周期
        atr_period: ATR 周期
        ema_period: EMA 周期
        rsi_period: RSI 周期
        bollinger_period: 布林带周期
        bollinger_std: 布林带标准差

    Returns:
        Dict: 包含所有指标的字典
    """
    df = normalize_klines(klines)

    if len(df) < max(adx_period, atr_period, ema_period, rsi_period, bollinger_period) + 10:
        return {}

    # 计算所有指标
    indicators = {}

    # ATR
    indicators["atr"] = calculate_atr(df, atr_period).iloc[-1]

    # ADX
    indicators["adx"] = calculate_adx(df, adx_period).iloc[-1]

    # EMA
    indicators[f"ema_{ema_period}"] = calculate_ema(df, ema_period).iloc[-1]

    # RSI
    indicators["rsi"] = calculate_rsi(df, rsi_period).iloc[-1]

    # 布林带
    upper, middle, lower = calculate_bollinger_bands(df, bollinger_period, bollinger_std)
    indicators["bollinger_upper"] = upper.iloc[-1]
    indicators["bollinger_middle"] = middle.iloc[-1]
    indicators["bollinger_lower"] = lower.iloc[-1]
    indicators["bollinger_width"] = (upper.iloc[-1] - lower.iloc[-1]) / middle.iloc[-1] if middle.iloc[-1] > 0 else 0

    # 当前价格
    indicators["current_price"] = df["close"].iloc[-1]

    # 价格变化
    indicators["price_change_pct"] = ((df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2] * 100) if len(df) > 1 else 0

    return indicators
