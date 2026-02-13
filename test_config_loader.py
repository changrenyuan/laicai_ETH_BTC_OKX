#!/usr/bin/env python3
"""测试 ConfigLoader 功能"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config_loader import get_config_loader


async def main():
    """主测试函数"""
    print("=== 测试 ConfigLoader ===\n")
    
    try:
        # 获取配置加载器实例
        loader = get_config_loader()
        
        # 测试 1: 读取账户配置
        print("1. 测试读取账户配置...")
        account_config = loader.get_account_config()
        print(f"✅ 账户配置加载成功:")
        print(f"   - API Key: {account_config.get('sub_account', {}).get('api_key', 'N/A')[:10]}...")
        print(f"   - API Secret: {account_config.get('sub_account', {}).get('api_secret', 'N/A')[:10]}...")
        print(f"   - API Passphrase: {account_config.get('sub_account', {}).get('api_passphrase', 'N/A')[:10]}...")
        print(f"   - Sandbox: {account_config.get('sub_account', {}).get('sandbox', False)}\n")
        
        # 测试 2: 读取交易所配置
        print("2. 测试读取交易所配置...")
        exchange_config = loader.get_exchange_config()
        print(f"✅ 交易所配置加载成功:")
        print(f"   - OKX Base URL: {exchange_config.get('okx', {}).get('base_url', {}).get('mainnet', 'N/A')}")
        print(f"   - OKX WebSocket URL: {exchange_config.get('okx', {}).get('websocket', {}).get('public_url', 'N/A')}\n")
        
        # 测试 3: 读取策略配置
        print("3. 测试读取策略配置...")
        strategy_config = loader.get_strategy_config()
        print(f"✅ 策略配置加载成功:")
        print(f"   - Default Strategy: {strategy_config.get('default_strategy', 'N/A')}")
        print(f"   - Enabled Strategies: {list(strategy_config.get('strategies', {}).keys())}\n")
        
        # 测试 4: 读取风险配置
        print("4. 测试读取风险配置...")
        risk_config = loader.get_risk_config()
        print(f"✅ 风险配置加载成功:")
        print(f"   - Max Position Size: {risk_config.get('position', {}).get('max_position_size', 'N/A')}")
        print(f"   - Stop Loss: {risk_config.get('position', {}).get('stop_loss', 'N/A')}\n")
        
        print("=== 所有测试通过！===\n")
        return 0
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
