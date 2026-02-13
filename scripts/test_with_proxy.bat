@echo off
REM OKXExchange 测试脚本 - 支持代理配置 (Windows)

echo ======================================
echo   OKXExchange 测试脚本
echo ======================================
echo.

REM 检查代理环境变量
if defined HTTP_PROXY (
    echo ✅ 检测到代理配置：
    echo    HTTP_PROXY=%HTTP_PROXY%
) else (
    echo ⚠️  HTTP_PROXY 未设置
)

if defined HTTPS_PROXY (
    echo    HTTPS_PROXY=%HTTPS_PROXY%
    echo.
) else (
    echo ⚠️  HTTPS_PROXY 未设置
    echo.
)

if not defined HTTP_PROXY if not defined HTTPS_PROXY (
    echo 💡 如果需要使用代理，请设置环境变量：
    echo    set HTTP_PROXY=http://127.0.0.1:7890
    echo    set HTTPS_PROXY=http://127.0.0.1:7890
    echo.
)

REM 运行配置验证
echo ======================================
echo   步骤 1: 验证配置
echo ======================================
python test_proxy_config.py

if errorlevel 1 (
    echo ❌ 配置验证失败
    pause
    exit /b 1
)

echo.
pause

REM 运行 OKXExchange 测试
echo ======================================
echo   步骤 2: 测试 OKXExchange
echo ======================================
python test_okx_exchange.py

echo.
echo ======================================
echo   测试完成
echo ======================================
pause
