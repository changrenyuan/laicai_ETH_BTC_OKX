"""
🧪 市场扫描功能测试脚本
=========================
测试 Regime Detector 和 Market Scanner 功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from strategy.regime_detector import RegimeDetector
from scanner.market_scanner import MarketScanner, ScanResult
from monitor.dashboard import Dashboard


def create_mock_klines(symbol="ETH-USDT-SWAP", num_klines=100):
    """创建模拟 K 线数据（OKX 格式，9 列）"""
    import random
    import time

    klines = []
    base_price = 2500.0

    for i in range(num_klines):
        timestamp = int((time.time() - (num_klines - i) * 4 * 3600) * 1000)
        open_price = base_price + random.uniform(-50, 50)
        close_price = open_price + random.uniform(-20, 20)
        high_price = max(open_price, close_price) + random.uniform(0, 10)
        low_price = min(open_price, close_price) - random.uniform(0, 10)
        volume = random.uniform(1000, 10000)
        vol_ccy = volume * close_price  # 成交额
        vol_ccy_quote = vol_ccy  # 成交额（计价货币）
        confirm = "1"  # 成交确认

        # OKX K 线格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        klines.append([
            timestamp,
            str(open_price),
            str(high_price),
            str(low_price),
            str(close_price),
            str(volume),
            str(vol_ccy),
            str(vol_ccy_quote),
            confirm
        ])

        base_price = close_price

    return klines


async def test_regime_detector():
    """测试 Regime Detector"""
    print("\n" + "=" * 80)
    print("🧪 测试 Regime Detector")
    print("=" * 80 + "\n")

    # 配置
    config = {
        "adx_threshold": 25,
        "volatility_expand": 1.5,
        "ema_period": 20,
        "rsi_period": 14,
        "atr_period": 14,
        "bollinger_period": 20,
        "bollinger_std": 2,
    }

    # 创建 Regime Detector
    detector = RegimeDetector(config)

    # 创建模拟 K 线
    klines = create_mock_klines("ETH-USDT-SWAP", 100)

    # 分析市场环境
    result = detector.analyze("ETH-USDT-SWAP", klines)

    if result:
        print(f"✅ Regime Detector 测试通过！")
        print(f"\n市场环境分析结果：")
        print(f"  交易对: {result.symbol}")
        print(f"  市场环境: {result.regime}")
        print(f"  置信度: {result.confidence:.2%}")
        print(f"  ADX: {result.adx:.2f}")
        print(f"  ATR: {result.atr:.4f}")
        print(f"  ATR 扩张: {result.atr_expansion:.2f}x")
        print(f"  EMA20: {result.ema20:.2f}")
        print(f"  当前价格: {result.current_price:.2f}")
        print(f"  布林带宽度: {result.bollinger_width:.2%}")
        print(f"  RSI: {result.rsi:.2f}")

        # 测试 Dashboard 显示
        Dashboard.print_regime_analysis(result)

        return True
    else:
        print("❌ Regime Detector 测试失败！")
        return False


async def test_market_scanner_mock():
    """测试 Market Scanner（模拟模式）"""
    print("\n" + "=" * 80)
    print("🧪 测试 Market Scanner（模拟模式）")
    print("=" * 80 + "\n")

    # 创建模拟扫描结果
    mock_results = [
        ScanResult(
            symbol="BTC-USDT-SWAP",
            volume_24h=500000000,
            price_change_24h=3.5,
            current_price=65000.0,
            high_24h=66000.0,
            low_24h=63000.0,
            score=85.5,
            regime="TREND",
            adx=32.5,
            atr=1200.0,
            atr_expansion=1.3,
            volatility_ratio=0.018,
        ),
        ScanResult(
            symbol="ETH-USDT-SWAP",
            volume_24h=300000000,
            price_change_24h=2.1,
            current_price=3500.0,
            high_24h=3600.0,
            low_24h=3400.0,
            score=78.2,
            regime="RANGE",
            adx=20.3,
            atr=85.0,
            atr_expansion=1.1,
            volatility_ratio=0.024,
        ),
        ScanResult(
            symbol="SOL-USDT-SWAP",
            volume_24h=150000000,
            price_change_24h=-4.2,
            current_price=145.0,
            high_24h=155.0,
            low_24h=140.0,
            score=65.8,
            regime="CHAOS",
            adx=28.7,
            atr=8.5,
            atr_expansion=2.1,
            volatility_ratio=0.058,
        ),
    ]

    # 测试 Dashboard 显示
    Dashboard.print_scan_results(mock_results)

    print(f"✅ Market Scanner Dashboard 测试通过！")
    return True


async def main():
    """主测试函数"""
    Dashboard.print_banner("v7.0 Scanner Test")

    # 测试 1: Regime Detector
    result1 = await test_regime_detector()

    # 测试 2: Market Scanner（模拟）
    result2 = await test_market_scanner_mock()

    # 总结
    print("\n" + "=" * 80)
    print("📊 测试总结")
    print("=" * 80)
    print(f"Regime Detector: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"Market Scanner:   {'✅ 通过' if result2 else '❌ 失败'}")
    print("=" * 80 + "\n")

    if result1 and result2:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
