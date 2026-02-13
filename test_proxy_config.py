#!/usr/bin/env python3
"""验证代理配置"""

import os

print("=== 代理配置检查 ===\n")

# 检查环境变量
http_proxy = os.getenv("HTTP_PROXY")
https_proxy = os.getenv("HTTPS_PROXY")

print(f"HTTP_PROXY: {http_proxy or '未设置'}")
print(f"HTTPS_PROXY: {https_proxy or '未设置'}\n")

# 检查 .env 文件
env_file = ".env"
if os.path.exists(env_file):
    print(f"✅ 发现 .env 文件")
    with open(env_file, "r", encoding="utf-8") as f:
        content = f.read()
        if "HTTP_PROXY" in content or "HTTPS_PROXY" in content:
            print("✅ .env 文件中包含代理配置")
        else:
            print("⚠️  .env 文件中未找到代理配置")
else:
    print(f"⚠️  未发现 .env 文件")
    print(f"   复制 .env.example 为 .env 并配置代理")

print("\n✅ 检查完成")
