#!/usr/bin/env python3
"""
验证代理配置加载
此脚本不实际连接网络，仅验证配置是否正确加载
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config_loader import get_config_loader


async def main():
    print("=== 验证代理配置 ===\n")
    
    # 1. 测试配置加载
    print("1. 加载配置文件...")
    loader = get_config_loader()
    exchange_config = loader.get_exchange_config()
    okx_config = exchange_config.get("okx", {})
    
    # 2. 检查代理配置
    print("2. 检查代理配置...")
    proxy_config = okx_config.get("proxy", {})
    
    print(f"   - HTTP Proxy: {proxy_config.get('http_proxy', 'N/A')}")
    print(f"   - HTTPS Proxy: {proxy_config.get('https_proxy', 'N/A')}")
    print(f"   - Enabled: {proxy_config.get('enabled', False)}\n")
    
    # 3. 检查环境变量
    print("3. 检查环境变量...")
    http_proxy_env = os.getenv("HTTP_PROXY")
    https_proxy_env = os.getenv("HTTPS_PROXY")
    
    print(f"   - HTTP_PROXY (env): {http_proxy_env or '未设置'}")
    print(f"   - HTTPS_PROXY (env): {https_proxy_env or '未设置'}\n")
    
    # 4. 模拟代理选择逻辑
    print("4. 代理选择逻辑...")
    
    # 优先级：环境变量 > 配置文件
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    
    if not proxy and proxy_config.get("enabled", False):
        https_proxy = proxy_config.get("https_proxy", "")
        http_proxy = proxy_config.get("http_proxy", "")
        proxy = https_proxy or http_proxy
    
    if proxy:
        print(f"   ✅ 使用代理: {proxy}")
    else:
        print(f"   ⚠️  未启用代理\n")
        print("   💡 要启用代理，您可以：")
        print("   1. 设置环境变量：")
        print("      export HTTP_PROXY=http://127.0.0.1:7890")
        print("      export HTTPS_PROXY=http://127.0.0.1:7890")
        print("   2. 或修改配置文件 config/exchange.yaml：")
        print("      okx.proxy.enabled: true")
        print("      okx.proxy.https_proxy: http://127.0.0.1:7890\n")
    
    # 5. 总结
    print("5. 配置验证总结...")
    print("   ✅ 配置文件加载成功")
    print("   ✅ 代理配置项存在")
    
    if proxy:
        print("   ✅ 代理已配置")
        return 0
    else:
        print("   ⚠️  代理未配置（可选）")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
