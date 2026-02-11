"""
🔭 Market Scanner - 市场扫描器
================================
功能：
1. 拉取所有 USDT 永续合约
2. 初筛标的（流动性、交易额、涨跌幅度、ADX、波动率扩张、价格分布、量价结构）
3. 生成候选列表
"""
import asyncio
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
                - trend_only: 是否只选择趋势环境合约
                - min_adx: 最小ADX（趋势强度）
                - min_atr_expansion: 最小ATR扩张
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

        # 趋势筛选配置
        self.trend_only = config.get("trend_only", False)
        self.min_adx = config.get("min_adx", 25)
        self.min_atr_expansion = config.get("min_atr_expansion", 1.2)

        self.logger = logging.getLogger(__name__)

    async def scan(self) -> List[ScanResult]:
        """
        执行市场扫描

        Returns:
            List[ScanResult]: 扫描结果列表（按评分排序）
        """
        self.logger.info("=" * 80)
        self.logger.info("🔍 开始市场扫描...")
        self.logger.info("=" * 80)
        self.logger.info(f"📋 扫描配置:")
        self.logger.info(f"   - 返回数量: {self.top_n}")
        self.logger.info(f"   - 最小成交额: {self.min_volume_24h:,} USDT")
        self.logger.info(f"   - 涨跌幅范围: {self.min_price_change}% ~ {self.max_price_change}%")
        self.logger.info(f"   - 趋势筛选: {'开启' if self.trend_only else '关闭'}")
        if self.trend_only:
            self.logger.info(f"   - 最小ADX: {self.min_adx}")
            self.logger.info(f"   - 最小ATR扩张: {self.min_atr_expansion}")
        self.logger.info("-" * 80)

        try:
            # 1. 获取所有 USDT 永续合约
            self.logger.info("📡 步骤1: 获取交易品种列表...")
            instruments = await self._fetch_instruments()

            if not instruments:
                self.logger.warning("❌ 未获取到交易品种列表")
                return []

            self.logger.info(f"✅ 获取到 {len(instruments)} 个 USDT 永续合约")

            # 2. 获取每个品种的 Ticker 数据
            self.logger.info("📡 步骤2: 获取Ticker数据...")
            tickers = await self._fetch_tickers(instruments)

            if not tickers:
                self.logger.warning("❌ 未获取到 Ticker 数据")
                return []

            self.logger.info(f"✅ 获取到 {len(tickers)} 个 Ticker 数据")

            # 3. 初筛（按成交额和涨跌幅）
            self.logger.info("🔍 步骤3: 初筛（成交额 & 涨跌幅）...")
            filtered_tickers = self._filter_tickers(tickers)

            if not filtered_tickers:
                self.logger.warning("❌ 初筛后无候选品种")
                self.logger.info("=" * 80)
                return []

            self.logger.info(f"✅ 初筛后候选品种数量: {len(filtered_tickers)}")

            # 4. 对每个候选品种进行技术分析（获取 K 线并计算指标）
            self.logger.info("🔍 步骤4: 技术分析（趋势筛选）...")
            candidates = await self._analyze_candidates(filtered_tickers)

            if not candidates:
                self.logger.warning("❌ 技术分析后无候选品种")
                self.logger.info("=" * 80)
                return []

            # 5. 排序并返回前 N 个
            self.logger.info("📊 步骤5: 排序并选择前 N 个...")
            sorted_candidates = sorted(candidates, key=lambda x: x.score, reverse=True)
            final_candidates = sorted_candidates[:self.top_n]

            self.logger.info(f"✅ 最终候选品种数量: {len(final_candidates)}")
            self.logger.info("=" * 80)
            return final_candidates

        except Exception as e:
            self.logger.error(f"❌ 市场扫描失败: {e}")
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
        reject_stats = {
            "low_volume": 0,
            "low_volatility": 0,
            "high_volatility": 0,
            "error": 0
        }

        for ticker in tickers:
            try:
                symbol = ticker.get("instId", "")
                # vol_ccy = float(ticker.get("volCcy", 0))  # 24h 成交量
                last_price = float(ticker.get("last", 0))  # 最新价
                open_24h = float(ticker.get("open24h", 0))  # 24h 开盘价
                # self.logger.info(
                #     f"Symbol: {symbol} | Raw VolCcy: {ticker.get('volCcy')} | Raw VolCcy24h: {ticker.get('volCcy24h')} | Last: {ticker.get('last')}")
                # 计算 24h 成交额（USDT）
                volume_24h = float(ticker.get("volCcy24h", 0))*last_price
                # print("marketscanner debug:24小时成交额")
                # print(volume_24h)
                # 计算涨跌幅
                price_change_24h = 0.0
                if open_24h > 0:
                    price_change_24h = ((last_price - open_24h) / open_24h) * 100
                    # 汇报每一个币种的筛选过程 (满足你的汇报需求)
                self.logger.info(
                    f"🔍 [初筛] {symbol:20s} | 成交额: {volume_24h:15,.0f} USDT | 涨跌幅: {price_change_24h:6.2f}%")

                if volume_24h < self.min_volume_24h:
                    self.logger.info(f"   ❌ 淘汰: 成交额低于门槛 ({self.min_volume_24h:,} USDT)")
                    reject_stats["low_volume"] += 1
                    continue

                if abs(price_change_24h) < self.min_price_change:
                    self.logger.info(f"   ❌ 淘汰: 涨跌幅波动不足 ({self.min_price_change}%)")
                    reject_stats["low_volatility"] += 1
                    continue

                if abs(price_change_24h) > self.max_price_change:
                    self.logger.info(f"   ❌ 淘汰: 涨跌幅过激, 风险过高 ({abs(price_change_24h):.2f}% > {self.max_price_change}%)")
                    reject_stats["high_volatility"] += 1
                    continue

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
                self.logger.error(f"❌ 筛选 {ticker.get('instId', 'Unknown')} 失败: {e}")
                reject_stats["error"] += 1
                continue

        # 按 24h 成交额排序
        filtered.sort(key=lambda x: x.get("_volume_24h", 0), reverse=True)

        # 输出淘汰统计
        self.logger.info(f"📊 初筛统计:")
        self.logger.info(f"   - 总数量: {len(tickers)}")
        self.logger.info(f"   - 通过: {len(filtered)}")
        self.logger.info(f"   - 淘汰: {len(tickers) - len(filtered)}")
        if reject_stats["low_volume"] > 0:
            self.logger.info(f"     * 成交额过低: {reject_stats['low_volume']}")
        if reject_stats["low_volatility"] > 0:
            self.logger.info(f"     * 涨跌幅过低: {reject_stats['low_volatility']}")
        if reject_stats["high_volatility"] > 0:
            self.logger.info(f"     * 涨跌幅过高: {reject_stats['high_volatility']}")
        if reject_stats["error"] > 0:
            self.logger.info(f"     * 错误: {reject_stats['error']}")

        return filtered

    async def _analyze_candidates(self, tickers: List[Dict]) -> List[ScanResult]:
        """
        并发对候选品种进行技术分析
        """
        candidates = []
        reject_stats = {
            "no_klines": 0,
            "no_regime": 0,
            "not_trend": 0,
            "low_adx": 0,
            "low_atr": 0,
            "error": 0
        }

        # 🟢 创建信号量，限制最大并发数为 20
        # OKX 公共接口限频通常较宽松，但为了安全起见限制并发
        sem = asyncio.Semaphore(5)

        async def process_ticker(ticker):
            """单个品种的处理逻辑封装"""
            async with sem:  # 获取令牌
                try:
                    symbol = ticker.get("instId")

                    # 获取 4H K 线
                    klines = await self.client.get_candlesticks(symbol, bar="4H", limit=100)

                    if not klines or len(klines) < 50:
                        self.logger.info(f"   ❌ [{symbol}] K线数据不足")
                        reject_stats["no_klines"] += 1
                        return None

                    # 市场环境分析
                    regime_analysis = self.regime_detector.analyze(symbol, klines)
                    if not regime_analysis:
                        self.logger.info(f"   ❌ [{symbol}] 市场环境分析失败")
                        reject_stats["no_regime"] += 1
                        return None

                    # 趋势筛选：如果配置了trend_only，只保留TREND环境的合约
                    if self.trend_only:
                        if regime_analysis.regime != "TREND":
                            self.logger.info(f"   ❌ [{symbol}] 市场环境为 {regime_analysis.regime}，跳过")
                            reject_stats["not_trend"] += 1
                            return None
                        # 检查ADX是否达标
                        if regime_analysis.adx < self.min_adx:
                            self.logger.info(f"   ❌ [{symbol}] ADX={regime_analysis.adx:.1f} < {self.min_adx}，趋势强度不足")
                            reject_stats["low_adx"] += 1
                            return None
                        # 检查ATR扩张是否达标
                        if regime_analysis.atr_expansion < self.min_atr_expansion:
                            self.logger.info(f"   ❌ [{symbol}] ATR扩张={regime_analysis.atr_expansion:.2f} < {self.min_atr_expansion}，波动率不足")
                            reject_stats["low_atr"] += 1
                            return None

                    # 计算分数
                    score = self._calculate_score(ticker, regime_analysis)

                    self.logger.info(f"   ✅ [{symbol}] 通过筛选 - 评分: {score:.2f} | 环境: {regime_analysis.regime} | ADX: {regime_analysis.adx:.1f}")

                    return ScanResult(
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
                except Exception as e:
                    self.logger.error(f"   ❌ [{ticker.get('instId')}] 分析失败: {e}")
                    reject_stats["error"] += 1
                    return None

        # 🟢 创建所有任务
        tasks = [process_ticker(t) for t in tickers]

        # 🟢 并发执行并等待结果
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集成功的结果
        for res in results:
            if isinstance(res, ScanResult):
                candidates.append(res)
            elif isinstance(res, Exception):
                self.logger.error(f"❌ 任务异常: {res}")
                reject_stats["error"] += 1

        # 输出趋势筛选统计
        self.logger.info(f"📊 趋势筛选统计:")
        self.logger.info(f"   - 分析数量: {len(tickers)}")
        self.logger.info(f"   - 通过: {len(candidates)}")
        self.logger.info(f"   - 淘汰: {len(tickers) - len(candidates)}")
        if reject_stats["no_klines"] > 0:
            self.logger.info(f"     * K线数据不足: {reject_stats['no_klines']}")
        if reject_stats["no_regime"] > 0:
            self.logger.info(f"     * 市场环境分析失败: {reject_stats['no_regime']}")
        if reject_stats["not_trend"] > 0:
            self.logger.info(f"     * 非趋势环境: {reject_stats['not_trend']}")
        if reject_stats["low_adx"] > 0:
            self.logger.info(f"     * ADX过低: {reject_stats['low_adx']}")
        if reject_stats["low_atr"] > 0:
            self.logger.info(f"     * ATR扩张过低: {reject_stats['low_atr']}")
        if reject_stats["error"] > 0:
            self.logger.info(f"     * 分析错误: {reject_stats['error']}")

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
