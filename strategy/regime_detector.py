"""
🌊 Regime Detector - 市场环境检测器
=====================================
识别三种市场状态：
- TREND（趋势）：明显的上涨或下跌趋势
- RANGE（震荡）：价格在一定区间内波动
- CHAOS（混乱）：高波动、无明确方向
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# 市场环境类型
RegimeType = Literal["TREND", "RANGE", "CHAOS"]


@dataclass
class RegimeAnalysis:
    """市场环境分析结果"""

    symbol: str
    regime: RegimeType
    confidence: float  # 置信度 0-1
    adx: float
    atr: float
    atr_expansion: float  # ATR 扩张倍数
    ema20: float
    current_price: float
    bollinger_width: float  # 布林带宽度
    rsi: float
    price_vs_ema: float  # 价格相对于 EMA 的百分比
    volatility_ratio: float  # 波动率比率

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "regime": self.regime,
            "confidence": f"{self.confidence:.2%}",
            "adx": round(self.adx, 2),
            "atr": round(self.atr, 4),
            "atr_expansion": round(self.atr_expansion, 2),
            "ema20": round(self.ema20, 2),
            "current_price": round(self.current_price, 2),
            "bollinger_width": round(self.bollinger_width, 2),
            "rsi": round(self.rsi, 2),
            "price_vs_ema": round(self.price_vs_ema, 2),
            "volatility_ratio": round(self.volatility_ratio, 2),
        }


class RegimeDetector:
    """
    市场环境检测器

    判断逻辑：
    1. TREND（趋势）：
       - ADX > threshold
       - 价格持续在 EMA20 上方（上涨）或下方（下跌）
       - 波动率温和扩张

    2. RANGE（震荡）：
       - ADX < threshold
       - 布林带宽度收缩
       - RSI 在 30-70 来回

    3. CHAOS（混乱）：
       - 波动率爆发（ATR 急扩张）
       - 价格穿越均线频繁
       - 高波动但无明确方向
    """

    def __init__(self, config: Dict):
        """
        初始化 Regime Detector

        Args:
            config: 配置字典，包含：
                - adx_threshold: ADX 阈值（默认 25）
                - volatility_expand_threshold: 波动率扩张阈值（默认 1.5）
                - ema_period: EMA 周期（默认 20）
                - rsi_period: RSI 周期（默认 14）
                - atr_period: ATR 周期（默认 14）
                - bollinger_period: 布林带周期（默认 20）
                - bollinger_std: 布林带标准差（默认 2）
        """
        self.adx_threshold = config.get("adx_threshold", 25)
        self.volatility_expand_threshold = config.get("volatility_expand", 1.5)
        self.ema_period = config.get("ema_period", 20)
        self.rsi_period = config.get("rsi_period", 14)
        self.atr_period = config.get("atr_period", 14)
        self.bollinger_period = config.get("bollinger_period", 20)
        self.bollinger_std = config.get("bollinger_std", 2)

        self.logger = logging.getLogger(__name__)

    def analyze(self, symbol: str, klines: List[Dict]) -> Optional[RegimeAnalysis]:
        """
        分析市场环境

        Args:
            symbol: 交易对
            klines: K线数据列表，每个元素包含：
                - t: 时间戳
                - o: 开盘价
                - h: 最高价
                - l: 最低价
                - c: 收盘价
                - vol: 成交量

        Returns:
            RegimeAnalysis: 市场环境分析结果
        """
        if len(klines) < max(self.ema_period, self.atr_period, self.rsi_period, self.bollinger_period) + 10:
            self.logger.warning(f"{symbol} K线数据不足，无法分析市场环境")
            return None

        try:
            # 转换为 DataFrame
            df = pd.DataFrame(klines)
            df.columns = ["timestamp", "open", "high", "low", "close", "volume", "vol_ccy", "vol_ccy_quote", "confirm"]

            # 转换为数值类型
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # 计算技术指标
            df = self._calculate_indicators(df)

            # 获取最新数据
            latest = df.iloc[-1]
            recent = df.tail(20)  # 最近 20 根 K 线

            # 判断市场环境
            regime, confidence = self._detect_regime(df, latest, recent)

            # 计算 ATR 扩张倍数（相对于过去 20 根 K 线的平均 ATR）
            atr_expansion = latest["atr"] / recent["atr"].mean() if recent["atr"].mean() > 0 else 1.0

            # 计算布林带宽度
            bollinger_width = (latest["upper_band"] - latest["lower_band"]) / latest["close"]

            # 计算波动率比率
            volatility_ratio = latest["atr"] / latest["close"] if latest["close"] > 0 else 0

            # 价格相对于 EMA 的百分比
            price_vs_ema = (latest["close"] - latest[f"ema_{self.ema_period}"]) / latest[f"ema_{self.ema_period}"]

            analysis = RegimeAnalysis(
                symbol=symbol,
                regime=regime,
                confidence=confidence,
                adx=latest["adx"],
                atr=latest["atr"],
                atr_expansion=atr_expansion,
                ema20=latest[f"ema_{self.ema_period}"],
                current_price=latest["close"],
                bollinger_width=bollinger_width,
                rsi=latest["rsi"],
                price_vs_ema=price_vs_ema,
                volatility_ratio=volatility_ratio,
            )

            self.logger.info(f"{symbol} 市场环境: {regime} (置信度: {confidence:.2%})")
            return analysis

        except Exception as e:
            self.logger.error(f"{symbol} 市场环境分析失败: {e}")
            return None

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""

        # 1. EMA (指数移动平均)
        df[f"ema_{self.ema_period}"] = df["close"].ewm(span=self.ema_period, adjust=False).mean()

        # 2. ATR (真实波幅)
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=self.atr_period).mean()

        # 3. RSI (相对强弱指标)
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # 4. 布林带
        df[f"sma_{self.bollinger_period}"] = df["close"].rolling(window=self.bollinger_period).mean()
        rolling_std = df["close"].rolling(window=self.bollinger_period).std()
        df["upper_band"] = df[f"sma_{self.bollinger_period}"] + (rolling_std * self.bollinger_std)
        df["lower_band"] = df[f"sma_{self.bollinger_period}"] - (rolling_std * self.bollinger_std)

        # 5. ADX (平均趋向指数)
        df = self._calculate_adx(df)

        return df

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算 ADX 指标"""
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

        # 计算 +DI 和 -DI
        df["+di"] = 100 * (df["+dm_smooth"] / df["atr"].replace(0, np.nan))
        df["-di"] = 100 * (df["-dm_smooth"] / df["atr"].replace(0, np.nan))

        # 计算 DX
        df["dx"] = 100 * np.abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"]).replace(0, np.nan)

        # 平滑 DX 得到 ADX
        df["adx"] = df["dx"].rolling(window=period).mean()

        return df

    def _detect_regime(self, df: pd.DataFrame, latest: pd.Series, recent: pd.DataFrame) -> tuple[RegimeType, float]:
        """
        检测市场环境

        Returns:
            (regime, confidence): 市场环境和置信度
        """
        adx = latest["adx"]
        atr_expansion = latest["atr"] / recent["atr"].mean() if recent["atr"].mean() > 0 else 1.0
        bollinger_width = (latest["upper_band"] - latest["lower_band"]) / latest["close"]
        rsi = latest["rsi"]
        ema20 = latest[f"ema_{self.ema_period}"]

        # 价格在 EMA20 上方的数量（最近 20 根）
        price_above_ema = (recent["close"] > ema20).sum()
        price_below_ema = (recent["close"] < ema20).sum()

        # RSI 震荡判断（在 30-70 之间）
        rsi_in_range = ((recent["rsi"] >= 30) & (recent["rsi"] <= 70)).sum()

        # 判断逻辑
        scores = {"TREND": 0, "RANGE": 0, "CHAOS": 0}

        # === TREND 判断 ===
        if adx > self.adx_threshold:
            scores["TREND"] += 3  # ADX 强势

        if price_above_ema >= 15 or price_below_ema >= 15:
            scores["TREND"] += 2  # 价格明显在 EMA 一侧

        if 0.5 <= atr_expansion <= 1.5:
            scores["TREND"] += 1  # 波动率温和

        # === RANGE 判断 ===
        if adx < self.adx_threshold:
            scores["RANGE"] += 3  # ADX 弱势

        if rsi_in_range >= 15:
            scores["RANGE"] += 2  # RSI 在正常区间

        if bollinger_width < 0.05:  # 布林带较窄
            scores["RANGE"] += 2

        if atr_expansion < 1.2:  # 波动率较小
            scores["RANGE"] += 1

        # === CHAOS 判断 ===
        if atr_expansion > self.volatility_expand_threshold:
            scores["CHAOS"] += 3  # 波动率爆发

        if bollinger_width > 0.10:  # 布林带很宽
            scores["CHAOS"] += 2

        if adx > self.adx_threshold and price_above_ema >= 8 and price_below_ema >= 8:
            scores["CHAOS"] += 2  # 频繁穿越均线

        if rsi > 70 or rsi < 30:
            scores["CHAOS"] += 1  # 超买超卖

        # 计算置信度
        total_score = sum(scores.values())
        if total_score == 0:
            return "RANGE", 0.5  # 默认震荡

        # 选择最高分的 regime
        best_regime = max(scores, key=scores.get)
        confidence = scores[best_regime] / total_score

        return best_regime, confidence


# 便捷函数
def detect_regime(symbol: str, klines: List[Dict], config: Dict) -> Optional[RegimeAnalysis]:
    """
    便捷函数：检测市场环境

    Args:
        symbol: 交易对
        klines: K线数据
        config: 配置字典

    Returns:
        RegimeAnalysis: 市场环境分析结果
    """
    detector = RegimeDetector(config)
    return detector.analyze(symbol, klines)
