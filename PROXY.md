# 代理配置说明

## 问题描述

如果无法连接 OKX API（出现 `Connection timeout` 错误），需要配置代理。

## 解决方法

### 1. 创建 .env 文件

在项目根目录创建 `.env` 文件：

```bash
cp .env.example .env
```

### 2. 配置代理

编辑 `.env` 文件，添加代理配置：

```env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

**注意**：
- 将 `7890` 替换为您的实际代理端口
- Clash 默认端口：7890
- V2Ray 默认端口：10808
- 如果不需要代理，注释掉这两行即可

### 3. 运行程序

```bash
python examples/demo_okx_exchange.py
```

## 验证代理

```bash
curl -x http://127.0.0.1:7890 https://www.okx.com/api/v5/public/time
```

如果返回 JSON 数据，说明代理配置正确。

## 代码实现

代理从环境变量读取，无需修改代码：

```python
# exchange/okx/okx_exchange.py
self.proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
```

与 `exchange/okx_client.py` 保持一致。

## 注意事项

- 代理配置是可选的
- 如果网络可以直连 OKX，不需要配置
- 确保代理工具正在运行
- 确保端口正确
