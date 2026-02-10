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
        # Windows/Linux 兼容
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def log(msg, level="INFO"):
        """UI 专用日志，不写文件，只打印到屏幕"""
        time_str = datetime.now().strftime('%H:%M:%S')
        if level == "INFO":
            print(f"[{time_str}] {msg}")
        elif level == "SUCCESS":
            print(f"[{time_str}] ✅ {msg}")
        elif level == "WARNING":
            print(f"[{time_str}] ⚠️ {msg}")
        elif level == "ERROR":
            print(f"[{time_str}] ❌ {msg}")

    @staticmethod
    def print_banner(version="v6.0 Ultimate"):
        Dashboard.clear_screen()
        print(Colors.CYAN + "=" * 80)
        print(f"🚀 LAICAI QUANT COMMANDER [{version}]".center(80))
        print(f"🤖 全自动量化交易引擎 | 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(80))
        print("=" * 80 + Colors.RESET + "\n")

    @staticmethod
    def _safe_float(value) -> float:
        """🔥 核心修复：安全转换浮点数，防止 float('') 崩溃"""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            if value.strip() == "":
                return 0.0
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0

    @staticmethod
    def print_account_overview(info: dict):
        """打印账户资金详情"""
        print(f"{Colors.HEADER}💰 账户资金概览 (Account Overview){Colors.RESET}")
        print("-" * 80)

        # 使用安全转换，防止报错
        total = Dashboard._safe_float(info.get('totalEq'))
        avail = Dashboard._safe_float(info.get('availBal'))
        upl = Dashboard._safe_float(info.get('upl'))

        # 保证金率处理 (可能是 "N/A" 或 "")
        raw_mgn = info.get('mgnRatio', '')
        mgn_val = Dashboard._safe_float(raw_mgn)
        mgn_str = f"{mgn_val:.2f}%" if raw_mgn else "N/A"

        # 颜色处理
        upl_color = Colors.GREEN if upl >= 0 else Colors.RED
        mgn_color = Colors.GREEN if mgn_val > 300 else Colors.YELLOW

        print(f"   💵 账户总权益 (Total Equity) : ${total:,.2f}")
        print(f"   💳 可用保证金 (Available)    : ${avail:,.2f}")
        print(f"   📈 未结盈亏 (Unrealized PnL) : {upl_color}${upl:,.2f}{Colors.RESET}")
        print(f"   🛡️ 保证金率 (Margin Ratio)   : {mgn_color}{mgn_str}{Colors.RESET} (安全线 > 300%)")
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

        # 防止 key 不存在导致报错
        d1 = analysis_data.get('1D', {})
        h4 = analysis_data.get('4H', {})
        m15 = analysis_data.get('15m', {})

        print(f"   📅 日线级别 (1D Trend)   : {_fmt_trend(d1.get('trend', 'UNKNOWN'))}")
        # print(f"      └─ MA20: {d1.get('ma20', 0):.2f} | RSI: {d1.get('rsi', 0):.1f}")

        print(f"   ⏱️ 中期级别 (4H Trend)   : {_fmt_trend(h4.get('trend', 'UNKNOWN'))}")

        print(f"   ⚡ 短线级别 (15m Trend)  : {_fmt_trend(m15.get('trend', 'UNKNOWN'))}")
        print(f"      └─ 波动率 (ATR-14)    : {m15.get('atr', 0):.2f}")

        # 微观 3m
        k_3m = analysis_data.get('3m', [])
        if k_3m:
            print(f"\n   🔬 微观结构 (3m inside 15m):")
            # 取最近5根
            recent = k_3m[-5:] if len(k_3m) >= 5 else k_3m
            k_str_list = []
            for x in recent:
                c = Dashboard._safe_float(x.get('c'))
                o = Dashboard._safe_float(x.get('o'))
                color = Colors.GREEN if c > o else Colors.RED
                k_str_list.append(f"{color}{c:.2f}{Colors.RESET}")

            print(f"      最近K线: {' -> '.join(k_str_list)}")
        print("-" * 80 + "\n")

    @staticmethod
    def print_strategy_plan(plan: dict):
        """打印作战计划"""
        print(f"{Colors.HEADER}📜 作战计划书 (Strategic Plan){Colors.RESET}")
        print("-" * 80)

        invest = Dashboard._safe_float(plan.get('investment'))
        exp_profit = Dashboard._safe_float(plan.get('expected_profit'))
        max_loss = Dashboard._safe_float(plan.get('max_loss'))

        print(f"   🎯 标的 (Target)         : {Colors.CYAN}{plan.get('symbol', 'UNKNOWN')}{Colors.RESET}")
        print(f"   💸 投入本金 (Investment) : ${invest:,.2f}")
        print(f"   📦 预计仓位 (Position)   : {plan.get('size')} 张 ({plan.get('direction')})")
        print(f"   🚀 预期盈利 (Take Profit): {Colors.GREEN}${exp_profit:,.2f} (价格: {plan.get('tp_price')}){Colors.RESET}")
        print(f"   🛑 最大止损 (Stop Loss)  : {Colors.RED}-${max_loss:,.2f} (价格: {plan.get('sl_price')}){Colors.RESET}")

        risk_reward = exp_profit / max_loss if max_loss > 0 else 0
        print(f"   ⚖️ 盈亏比 (Risk/Reward)  : {risk_reward:.2f}")
        print("-" * 80 + "\n")

    @staticmethod
    def print_execution_status(success_count: int, fail_count: int, msg: str = ""):
        if fail_count > 0:
            print(f"{Colors.YELLOW}⚠️ 执行警告: 成功 {success_count} / 失败 {fail_count}{Colors.RESET}")
            if msg: print(f"   原因: {msg}")
        else:
            print(f"{Colors.GREEN}✅ 执行完美: {success_count} 单已挂出{Colors.RESET}")