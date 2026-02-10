"""
👀 战情指挥中心 (Dashboard UI Layer)
====================================
负责将冰冷的数据转化为可视化的战情报告。
屏蔽底层 API 杂音，只展示交易员关心的核心指标。
"""
import os
import sys
from datetime import datetime

# 颜色常量
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'

class Dashboard:
    @staticmethod
    def clear_screen():
        """清屏，保持界面整洁"""
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def log(msg, level="INFO"):
        """UI 专用日志，不写文件，只打印到屏幕"""
        time_str = datetime.now().strftime('%H:%M:%S')
        if level == "INFO":
            print(f"{Colors.BLUE}[{time_str}]{Colors.RESET} {msg}")
        elif level == "SUCCESS":
            print(f"{Colors.GREEN}[{time_str}] ✅ {msg}{Colors.RESET}")
        elif level == "WARNING":
            print(f"{Colors.YELLOW}[{time_str}] ⚠️ {msg}{Colors.RESET}")
        elif level == "ERROR":
            print(f"{Colors.RED}[{time_str}] ❌ {msg}{Colors.RESET}")

    @staticmethod
    def print_banner(version="v6.0 Ultimate"):
        Dashboard.clear_screen()
        print(Colors.CYAN + "=" * 80)
        print(f"🚀 LAICAI QUANT COMMANDER [{version}]".center(80))
        print(f"🤖 全自动量化交易引擎 | 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(80))
        print("=" * 80 + Colors.RESET + "\n")

    @staticmethod
    def print_account_overview(info: dict):
        """打印账户资金详情"""
        print(f"{Colors.HEADER}💰 账户资金概览 (Account Overview){Colors.RESET}")
        print("-" * 80)

        # 格式化数字
        total = float(info.get('totalEq', 0))
        avail = float(info.get('availBal', 0))
        upl = float(info.get('upl', 0))
        mgn_ratio = info.get('mgnRatio', '0')

        # 颜色处理
        upl_color = Colors.GREEN if upl >= 0 else Colors.RED
        mgn_color = Colors.GREEN if float(mgn_ratio) > 300 or mgn_ratio == '' else Colors.RED

        print(f"   💵 账户总权益 (Total Equity) : ${total:,.2f}")
        print(f"   💳 可用保证金 (Available)    : ${avail:,.2f}")
        print(f"   📈 未结盈亏 (Unrealized PnL) : {upl_color}${upl:,.2f}{Colors.RESET}")
        print(f"   🛡️ 保证金率 (Margin Ratio)   : {mgn_color}{mgn_ratio}%{Colors.RESET} (安全线 > 300%)")
        print("-" * 80 + "\n")

    @staticmethod
    def print_market_sentiment(symbol, analysis_data):
        """打印多周期市场分析"""
        print(f"{Colors.HEADER}📊 市场趋势研判 (Market Intelligence) - {symbol}{Colors.RESET}")
        print("-" * 80)

        def _fmt_trend(trend):
            if trend == "BULLISH": return f"{Colors.GREEN}📈 强势看涨 (Bullish){Colors.RESET}"
            if trend == "BEARISH": return f"{Colors.RED}📉 强势看跌 (Bearish){Colors.RESET}"
            return f"{Colors.YELLOW}⚖️ 震荡整理 (Neutral){Colors.RESET}"

        # 1D / 4H / 15m
        print(f"   📅 日线级别 (1D Trend)   : {_fmt_trend(analysis_data['1D']['trend'])}")
        print(f"      └─ MA20: {analysis_data['1D']['ma20']:.2f} | RSI: {analysis_data['1D']['rsi']:.1f}")

        print(f"   ⏱️ 中期级别 (4H Trend)   : {_fmt_trend(analysis_data['4H']['trend'])}")

        print(f"   ⚡ 短线级别 (15m Trend)  : {_fmt_trend(analysis_data['15m']['trend'])}")
        print(f"      └─ 波动率 (ATR-14)    : {analysis_data['15m']['atr']:.2f}")

        # 微观 3m
        k_3m = analysis_data.get('3m', [])
        print(f"\n   🔬 微观结构 (3m inside 15m):")
        k_str = " -> ".join([f"{Colors.GREEN if x['c']>x['o'] else Colors.RED}{x['c']:.2f}{Colors.RESET}" for x in k_3m[-5:]])
        print(f"      最近5根3mK线: {k_str}")
        print("-" * 80 + "\n")

    @staticmethod
    def print_strategy_plan(plan: dict):
        """打印作战计划"""
        print(f"{Colors.HEADER}📜 作战计划书 (Strategic Plan){Colors.RESET}")
        print("-" * 80)

        print(f"   🎯 标的 (Target)         : {Colors.CYAN}{plan['symbol']}{Colors.RESET}")
        print(f"   💸 投入本金 (Investment) : ${plan['investment']:,.2f}")
        print(f"   📦 预计仓位 (Position)   : {plan['size']} 张 ({plan['direction']})")
        print(f"   🚀 预期盈利 (Take Profit): {Colors.GREEN}${plan['expected_profit']:,.2f} (价格: {plan['tp_price']}){Colors.RESET}")
        print(f"   🛑 最大止损 (Stop Loss)  : {Colors.RED}-${plan['max_loss']:,.2f} (价格: {plan['sl_price']}){Colors.RESET}")

        risk_reward = plan['expected_profit'] / plan['max_loss'] if plan['max_loss'] > 0 else 0
        print(f"   ⚖️ 盈亏比 (Risk/Reward)  : {risk_reward:.2f}")
        print("-" * 80 + "\n")