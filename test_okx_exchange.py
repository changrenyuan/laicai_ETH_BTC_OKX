#!/usr/bin/env python3
"""测试 OKXExchange 功能"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exchange.okx.okx_exchange import OKXExchange


async def main():
    """主测试函数"""
    print("=== 测试 OKXExchange ===\n")
    
    try:
        # 初始化 OKXExchange（配置将从配置文件读取）
        print("1. 初始化 OKXExchange...")
        config = {}  # 空配置，所有参数从配置文件读取
        exchange = OKXExchange(config)
        print("✅ OKXExchange 初始化成功\n")
        
        # 测试 2: 连接测试
        print("2. 测试连接...")
        await exchange.connect()
        print("✅ 连接成功\n")
        
        # 测试 3: 健康检查
        print("3. 测试健康检查...")
        health = await exchange.health_check()
        print(f"✅ 健康检查结果: {health}\n")
        
        # 测试 4: 获取行情数据
        print("4. 测试获取行情数据 (BTC-USDT)...")
        ticker = await exchange.get_ticker("BTC-USDT")
        if ticker:
            print(f"✅ 获取行情成功:")
            print(f"   - 交易对: {ticker.get('instId', 'N/A')}")
            print(f"   - 最新价: {ticker.get('last', 'N/A')}")
            print(f"   - 24h涨跌: {ticker.get('change24h', 'N/A')}%\n")
        else:
            print("❌ 获取行情数据失败\n")
        
        # 测试 5: 获取账户余额
        print("5. 测试获取账户余额...")
        balances = await exchange.get_trading_balances()
        if balances:
            print(f"✅ 账户余额获取成功 ({len(balances)} 个币种)")
            for balance in balances[:3]:  # 显示前3个
                print(f"   - {balance.get('ccy', 'N/A')}: {balance.get('availBal', 0)}")
        else:
            print("❌ 获取账户余额失败\n")
        
        print("=== 所有测试完成！===\n")
        return 0
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # 清理
        try:
            if 'exchange' in locals():
                await exchange.disconnect()
        except:
            pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
