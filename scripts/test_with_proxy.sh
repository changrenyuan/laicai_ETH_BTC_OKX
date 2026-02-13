#!/bin/bash
# OKXExchange 测试脚本 - 支持代理配置

echo "======================================"
echo "  OKXExchange 测试脚本"
echo "======================================"
echo ""

# 检查代理环境变量
if [ -n "$HTTP_PROXY" ] || [ -n "$HTTPS_PROXY" ]; then
    echo "✅ 检测到代理配置："
    [ -n "$HTTP_PROXY" ] && echo "   HTTP_PROXY=$HTTP_PROXY"
    [ -n "$HTTPS_PROXY" ] && echo "   HTTPS_PROXY=$HTTPS_PROXY"
    echo ""
else
    echo "⚠️  未检测到代理环境变量"
    echo ""
    echo "💡 如果需要使用代理，请设置环境变量："
    echo "   export HTTP_PROXY=http://127.0.0.1:7890"
    echo "   export HTTPS_PROXY=http://127.0.0.1:7890"
    echo ""
fi

# 运行配置验证
echo "======================================"
echo "  步骤 1: 验证配置"
echo "======================================"
python test_proxy_config.py

if [ $? -ne 0 ]; then
    echo "❌ 配置验证失败"
    exit 1
fi

echo ""
read -p "按 Enter 继续运行 OKXExchange 测试..."
echo ""

# 运行 OKXExchange 测试
echo "======================================"
echo "  步骤 2: 测试 OKXExchange"
echo "======================================"
python test_okx_exchange.py

echo ""
echo "======================================"
echo "  测试完成"
echo "======================================"
