# 市场扫描功能使用指南

## 📖 概述

市场扫描功能是量化交易系统的核心增强模块，实现了完整的交易流程：

```
Scanner → Regime → Strategy → Portfolio → Risk → Execution → Analytics
```

### 核心功能

1. **市场扫描器 (Market Scanner)**：自动扫描所有 USDT 永续合约，筛选优质交易对
2. **市场环境检测器 (Regime Detector)**：识别市场环境（趋势/震荡/混乱）
3. **智能选币**：根据流动性、成交额、涨跌幅、ADX、波动率等指标综合评分

---

## 🚀 快速开始

### 1. 配置参数

编辑 `config/strategy.yaml`：

```yaml
# 市场扫描配置
market_scan:
  enabled: true               # 是否开启市场扫描
  top_n: 5                    # 返回前 N 个候选品种
  min_volume_24h: 10000000    # 最小 24h 成交额 (1000 万 USDT)
  min_price_change: 1.0       # 最小涨跌幅 1%
  max_price_change: 20.0      # 最大涨跌幅 20%
  scan_interval: 60           # 扫描间隔（秒）

# 市场环境检测配置
regime:
  adx_threshold: 25           # ADX 阈值（趋势判断）
  volatility_expand: 1.5      # 波动率扩张阈值（混乱判断）
  ema_period: 20              # EMA 周期
  rsi_period: 14              # RSI 周期
  atr_period: 14              # ATR 周期
  bollinger_period: 20        # 布林带周期
  bollinger_std: 2            # 布林带标准差
```

### 2. 启动系统

```bash
# 安装依赖
pip install -r requirements.txt

# 启动系统
python main.py
```

### 3. 查看扫描结果

系统会自动在终端显示：

```
🔭 [Scanner] 市场扫描结果
────────────────────────────────────────────────────────────────────────────────
排名   交易对                24H成交额(USDT)   涨跌幅        市场环境       评分
────────────────────────────────────────────────────────────────────────────────
1      BTC-USDT-SWAP         5.00 亿         +3.50%       趋势          85.5
2      ETH-USDT-SWAP         3.00 亿         +2.10%       震荡          78.2
3      SOL-USDT-SWAP         1.50 亿         -4.20%       混乱          65.8
────────────────────────────────────────────────────────────────────────────────
```

---

## 🌊 市场环境说明

### TREND（趋势市）
- **特征**：ADX > 25，价格持续在 EMA20 上方或下方
- **适合策略**：趋势跟踪策略、方向性网格
- **风险**：中等

### RANGE（震荡市）
- **特征**：ADX < 25，布林带宽度收缩，RSI 在 30-70 之间
- **适合策略**：中性网格、资金费率套利
- **风险**：低

### CHAOS（混乱市）
- **特征**：波动率爆发，价格频繁穿越均线
- **适合策略**：观望、降低仓位
- **风险**：高

---

## 📊 评分标准

综合评分（0-100）基于以下维度：

| 维度 | 权重 | 说明 |
|------|------|------|
| 成交额 | 30% | 24h 成交额，反映流动性 |
| 涨跌幅 | 20% | 理想范围 3%-10% |
| 市场环境 | 30% | TREND: 0.9, RANGE: 0.7, CHAOS: 0.3 |
| 波动率 | 20% | 理想 ATR 扩张 1.0-1.5x |

---

## 🧪 测试

运行测试脚本验证功能：

```bash
python scripts/test_market_scan.py
```

测试内容：
- Regime Detector 功能测试
- Market Scanner Dashboard 显示测试

---

## 📁 文件结构

```
laicai_ETH_BTC_OKX/
├── scanner/
│   ├── __init__.py
│   └── market_scanner.py       # 市场扫描器
├── strategy/
│   └── regime_detector.py      # 市场环境检测器
├── monitor/
│   └── dashboard.py            # 仪表盘（已更新）
├── lifecycle/
│   ├── runtime.py              # 核心循环（已更新）
│   └── register.py             # 模块注册（已更新）
├── core/
│   └── context.py              # 上下文（已更新）
└── config/
    └── strategy.yaml           # 策略配置（已更新）
```

---

## 🔧 工作流程

### 完整交易流程

1. **市场扫描**
   - 获取所有 USDT 永续合约
   - 按成交额排序
   - 初筛（流动性、涨跌幅）

2. **市场环境检测**
   - 计算技术指标（ADX、ATR、EMA、RSI、布林带）
   - 判断市场环境（TREND/RANGE/CHAOS）
   - 选择最佳候选

3. **策略判断**
   - 根据市场环境选择策略
   - 生成交易信号

4. **风控审批**
   - 检查资金是否充足
   - 检查仓位是否超限

5. **执行交易**
   - 原子下单
   - 对冲检查

6. **更新 Context**
   - 记录交易
   - 更新 PnL

7. **分析报告**
   - 统计胜率
   - 生成报告

---

## ⚙️ 高级配置

### 调整扫描频率

```yaml
market_scan:
  scan_interval: 300  # 5 分钟扫描一次
```

### 严格筛选

```yaml
market_scan:
  min_volume_24h: 50000000   # 最小 5000 万成交额
  min_price_change: 3.0      # 最小涨跌幅 3%
  max_price_change: 10.0     # 最大涨跌幅 10%
```

### 调整市场环境判断阈值

```yaml
regime:
  adx_threshold: 30          # 更严格的趋势判断
  volatility_expand: 2.0     # 更严格的混乱判断
```

---

## 📝 注意事项

1. **API 限制**：OKX API 有频率限制，不要设置过短的扫描间隔
2. **数据质量**：确保 K 线数据完整，至少需要 100 根 4H K 线
3. **资源消耗**：市场扫描会消耗较多 API 配额，建议合理设置
4. **风险控制**：混乱市场（CHAOS）建议降低仓位或暂停交易

---

## 🆘 常见问题

### Q: 扫描结果为空？

A: 检查以下几点：
1. 确保 `market_scan.enabled` 为 `true`
2. 检查 `min_volume_24h` 是否设置过高
3. 检查 `min_price_change` 和 `max_price_change` 范围是否合理
4. 查看日志是否有 API 错误

### Q: 市场环境判断不准确？

A: 可以调整 `regime` 配置参数：
- `adx_threshold`：调整趋势判断阈值
- `volatility_expand`：调整混乱判断阈值

### Q: 如何禁用市场扫描？

A: 设置 `market_scan.enabled` 为 `false`，系统将使用配置中指定的交易对。

---

## 📞 支持

如有问题，请查看：
- GitHub Issues
- 项目 README.md
- 日志文件：`logs/runtime.log`

---

## 📄 许可证

MIT License
