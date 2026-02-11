"""
🔭 Market Scanner - 市场扫描器
================================
功能：
1. 拉取所有 USDT 永续合约
2. 初筛标的（流动性、交易额、涨跌幅度、ADX、波动率扩张、价格分布、量价结构）
3. 生成候选列表
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass

from strategy.indicators import normalize_klines, calculate_atr
from strategy.regime_detector import RegimeAnalysis

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """扫描结果"""

    symbol: str
    volume_24h: float
    price_change_24h: float
    current_price: float
    high_24h: float
    low_24h: float
    score: float  # 综合评分
    regime: str  # 市场环境（TREND/RANGE/CHAOS）
    adx: float
    atr: float
    atr_expansion: float
    volatility_ratio: float

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "volume_24h": round(self.volume_24h, 2),
            "price_change_24h": round(self.price_change_24h, 2),
            "current_price": round(self.current_price, 2),
            "high_24h": round(self.high_24h, 2),
            "low_24h": round(self.low_24h, 2),
            "score": round(self.score, 2),
            "regime": self.regime,
            "adx": round(self.adx, 2),
            "atr": round(self.atr, 4),
            "atr_expansion": round(self.atr_expansion, 2),
            "volatility_ratio": round(self.volatility_ratio, 2),
        }


class MarketScanner:
    """
    市场扫描器

    核心功能：
    1️⃣ 拉市场列表（获取所有 USDT 永续）
    2️⃣ 初筛（24h成交额、振幅、ADX、ATR扩张等）
    3️⃣ 输出候选列表（包含市场环境）
    """

    def __init__(self, client, market_data_fetcher, config: Dict, regime_detector):
        """
        初始化市场扫描器

        Args:
            client: OKX 客户端实例（用于获取 K 线数据）
            market_data_fetcher: MarketDataFetcher 实例（用于获取 ticker 数据）
            config: 配置字典，包含：
                - top_n: 返回前 N 个候选
                - min_volume_24h: 最小 24h 成交额
                - min_price_change: 最小涨跌幅
                - max_price_change: 最大涨跌幅
            regime_detector: 市场环境检测器实例
        """
        self.client = client
        self.market_data_fetcher = market_data_fetcher
        self.config = config
        self.regime_detector = regime_detector

        self.top_n = config.get("top_n", 5)
        self.min_volume_24h = config.get("min_volume_24h", 10000000)  # 1000 万 USDT
        self.min_price_change = config.get("min_price_change", 1.0)  # 1%
        self.max_price_change = config.get("max_price_change", 20.0)  # 20%

        self.logger = logging.getLogger(__name__)

    async def scan(self) -> List[ScanResult]:
        """
        执行市场扫描

        Returns:
            List[ScanResult]: 扫描结果列表（按评分排序）
        """
        self.logger.info("开始市场扫描...")

        try:
            # 1. 获取所有 USDT 永续合约
            instruments = await self._fetch_instruments()

            if not instruments:
                self.logger.warning("未获取到交易品种列表")
                return []

            # 2. 获取每个品种的 Ticker 数据
            tickers = await self._fetch_tickers(instruments)

            if not tickers:
                self.logger.warning("未获取到 Ticker 数据")
                return []

            # 3. 初筛（按成交额和涨跌幅）
            filtered_tickers = self._filter_tickers(tickers)

            if not filtered_tickers:
                self.logger.warning("初筛后无候选品种")
                return []

            self.logger.info(f"初筛后候选品种数量: {len(filtered_tickers)}")

            # 4. 对每个候选品种进行技术分析（获取 K 线并计算指标）
            candidates = await self._analyze_candidates(filtered_tickers)

            if not candidates:
                self.logger.warning("技术分析后无候选品种")
                return []

            # 5. 排序并返回前 N 个
            sorted_candidates = sorted(candidates, key=lambda x: x.score, reverse=True)
            final_candidates = sorted_candidates[:self.top_n]

            self.logger.info(f"最终候选品种数量: {len(final_candidates)}")
            return final_candidates

        except Exception as e:
            self.logger.error(f"市场扫描失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _fetch_instruments(self) -> List[str]:
        """
        获取所有 USDT 永续合约

        Returns:
            List[str]: 交易对列表，如 ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
        """
        try:
            # 获取所有交易品种
            result = await self.client._request("GET", "/api/v5/public/instruments", params={"instType": "SWAP"})

            if not result or len(result) == 0:
                self.logger.error("获取交易品种失败")
                return []

            # 过滤 USDT 永续合约
            instruments = []
            for inst in result:
                inst_id = inst.get("instId", "")
                # 只取 USDT 永续合约
                if inst_id.endswith("-USDT-SWAP"):
                    # 排除杠杆太高的（如 100 倍）
                    if inst.get("state") == "live":
                        instruments.append(inst_id)

            self.logger.info(f"获取到 {len(instruments)} 个 USDT 永续合约")
            return instruments

        except Exception as e:
            self.logger.error(f"获取交易品种失败: {e}")
            return []

    async def _fetch_tickers(self, instruments: List[str]) -> List[Dict]:
        """
        获取所有品种的 Ticker 数据（使用 market_data_fetcher）

        Args:
            instruments: 交易对列表

        Returns:
            List[Dict]: Ticker 数据列表
        """
        try:
            # 使用 market_data_fetcher 获取 ticker
            tickers = await self.market_data_fetcher.get_tickers_by_symbols(instruments)

            self.logger.info(f"获取到 {len(tickers)} 个 Ticker 数据")
            return tickers

        except Exception as e:
            self.logger.error(f"获取 Ticker 数据失败: {e}")
            return []

    def _filter_tickers(self, tickers: List[Dict]) -> List[Dict]:
        """
        初筛 Ticker

        筛选条件：
        - 24h 成交额 >= min_volume_24h
        - 涨跌幅在 [min_price_change, max_price_change] 之间

        Args:
            tickers: Ticker 数据列表

        Returns:
            List[Dict]: 筛选后的 Ticker 列表
        """
        filtered = []

        for ticker in tickers:
            try:
                symbol = ticker.get("instId", "")
                vol_ccy = float(ticker.get("volCcy", 0))  # 24h 成交量
                last_price = float(ticker.get("last", 0))  # 最新价
                open_24h = float(ticker.get("open24h", 0))  # 24h 开盘价

                # 计算 24h 成交额（USDT）
                volume_24h = vol_ccy * last_price

                # 计算涨跌幅
                price_change_24h = 0.0
                if open_24h > 0:
                    price_change_24h = ((last_price - open_24h) / open_24h) * 100

                # 筛选条件
                if volume_24h >= self.min_volume_24h:
                    if abs(price_change_24h) >= self.min_price_change:
                        if abs(price_change_24h) <= self.max_price_change:
                            # 添加额外信息
                            ticker["_volume_24h"] = volume_24h
                            ticker["_price_change_24h"] = price_change_24h
                            ticker["_current_price"] = last_price
                            ticker["_high_24h"] = float(ticker.get("high24h", 0))
                            ticker["_low_24h"] = float(ticker.get("low24h", 0))

                            filtered.append(ticker)

            except Exception as e:
                self.logger.error(f"筛选 Ticker 失败: {e}")
                continue

        # 按 24h 成交额排序
        filtered.sort(key=lambda x: x.get("_volume_24h", 0), reverse=True)

        return filtered

    async def _analyze_candidates(self, tickers: List[Dict]) -> List[ScanResult]:
        """
        对候选品种进行技术分析

        Args:
            tickers: 筛选后的 Ticker 列表

        Returns:
            List[ScanResult]: 扫描结果列表
        """
        candidates = []

        for ticker in tickers:
            try:
                symbol = ticker.get("instId")

                # 获取 4H K 线（用于计算技术指标）
                klines = await self.client.get_candlesticks(symbol, bar="4H", limit=100)

                if not klines or len(klines) < 50:
                    self.logger.warning(f"{symbol} K 线数据不足，跳过")
                    continue

                # 使用 Regime Detector 判断市场环境（这会计算所有技术指标）
                regime_analysis: RegimeAnalysis = self.regime_detector.analyze(symbol, klines)

                if not regime_analysis:
                    self.logger.warning(f"{symbol} 市场环境分析失败，跳过")
                    continue

                # 计算综合评分
                score = self._calculate_score(ticker, regime_analysis)

                candidate = ScanResult(
                    symbol=symbol,
                    volume_24h=ticker.get("_volume_24h", 0),
                    price_change_24h=ticker.get("_price_change_24h", 0),
                    current_price=ticker.get("_current_price", 0),
                    high_24h=ticker.get("_high_24h", 0),
                    low_24h=ticker.get("_low_24h", 0),
                    score=score,
                    regime=regime_analysis.regime,
                    adx=regime_analysis.adx,
                    atr=regime_analysis.atr,
                    atr_expansion=regime_analysis.atr_expansion,
                    volatility_ratio=regime_analysis.volatility_ratio,
                )

                candidates.append(candidate)

            except Exception as e:
                self.logger.error(f"分析候选品种失败: {e}")
                continue

        return candidates

    def _calculate_score(self, ticker: Dict, regime_analysis: RegimeAnalysis) -> float:
        """
        计算综合评分

        评分维度：
        1. 成交额（30%）
        2. 涨跌幅（20%）
        3. 市场环境（30%）
        4. 波动率（20%）

        Args:
            ticker: Ticker 数据
            regime_analysis: 市场环境分析结果

        Returns:
            float: 综合评分（0-100）
        """
        score = 0.0

        # 1. 成交额评分（归一化）
        volume_24h = ticker.get("_volume_24h", 0)
        volume_score = min(volume_24h / 100000000, 1.0)  # 1 亿 USDT 满分
        score += volume_score * 30

        # 2. 涨跌幅评分（适中最好）
        price_change_24h = abs(ticker.get("_price_change_24h", 0))
        # 理想涨跌幅：3% - 10%
        if 3 <= price_change_24h <= 10:
            change_score = 1.0
        elif price_change_24h < 3:
            change_score = price_change_24h / 3
        else:
            change_score = max(0, 1 - (price_change_24h - 10) / 10)
        score += change_score * 20

        # 3. 市场环境评分
        regime = regime_analysis.regime
        confidence = regime_analysis.confidence
        if regime == "TREND":
            regime_score = 0.9  # 趋势适合策略
        elif regime == "RANGE":
            regime_score = 0.7  # 震荡也适合
        else:  # CHAOS
            regime_score = 0.3  # 混乱不适合
        score += regime_score * confidence * 30

        # 4. 波动率评分（适中最好）
        atr_expansion = regime_analysis.atr_expansion
        # 理想 ATR 扩张：1.0 - 1.5
        if 1.0 <= atr_expansion <= 1.5:
            volatility_score = 1.0
        elif atr_expansion < 1.0:
            volatility_score = atr_expansion
        else:
            volatility_score = max(0, 1 - (atr_expansion - 1.5) / 1.5)
        score += volatility_score * 20

        return min(score, 100.0)


# 便捷函数
async def scan_market(client, config: Dict, regime_detector) -> List[ScanResult]:
    """
    便捷函数：执行市场扫描

    Args:
        client: OKX 客户端
        config: 配置字典
        regime_detector: 市场环境检测器

    Returns:
        List[ScanResult]: 扫描结果列表
    """
    scanner = MarketScanner(client, config, regime_detector)
    return await scanner.scan()
