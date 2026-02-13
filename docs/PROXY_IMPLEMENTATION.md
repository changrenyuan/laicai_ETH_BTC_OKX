# 代理配置实现总结

## 学习 Hummingbot 架构

通过研究 Hummingbot 项目（位于 `/workspace/projects/hummingbot`），我了解到以下关键设计：

### 1. WebAssistant 架构

Hummingbot 使用了 `WebAssistant` 框架来处理所有网络请求：

```
WebAssistantsFactory
  ├── RESTAssistant (REST API)
  ├── WSAssistant (WebSocket)
  └── ConnectionsFactory
      ├── RESTConnection
      └── WSConnection
```

### 2. 连接管理

`ConnectionsFactory` 使用共享的 `aiohttp.ClientSession`：

```python
class ConnectionsFactory:
    _shared_client: aiohttp.ClientSession | None = None
    
    async def _get_shared_client(self) -> aiohttp.ClientSession:
        if self._shared_client is None:
            self._shared_client = aiohttp.ClientSession()
        return self._shared_client
```

### 3. 超时和连接配置

Hummingbot 在 `gateway_http_client.py` 中展示了如何使用 `TCPConnector`：

```python
conn = aiohttp.TCPConnector(
    ssl=ssl_ctx,
    force_close=True,
    limit=100,
    limit_per_host=30,
)
cls._shared_client = aiohttp.ClientSession(connector=conn)
```

### 4. 代理支持

虽然 Hummingbot 本身没有内置代理配置，但 `aiohttp` 支持通过环境变量（`HTTP_PROXY`, `HTTPS_PROXY`）或直接在请求时指定 `proxy` 参数。

## 本项目实现

基于 Hummingbot 的架构和项目中已有的 `okx_client.py` 实现，我完成了以下工作：

### 1. 配置文件支持

在 `config/exchange.yaml` 中添加了代理配置：

```yaml
okx:
  # 代理配置
  proxy:
    http_proxy: "http://127.0.0.1:7890"
    https_proxy: "http://127.0.0.1:7890"
    enabled: false
```

### 2. OKXExchange 代理支持

修改 `exchange/okx/okx_exchange.py`：

```python
def __init__(self, config: Dict):
    # ... 其他代码 ...
    
    # 代理配置（从配置读取或环境变量读取）
    proxy_config = okx_config.get("proxy", {})
    proxy_enabled = proxy_config.get("enabled", False)
    
    # 优先级：环境变量 > 配置文件
    self.proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    
    if not self.proxy and proxy_enabled:
        https_proxy = proxy_config.get("https_proxy", "")
        http_proxy = proxy_config.get("http_proxy", "")
        self.proxy = https_proxy or http_proxy
    
    if self.proxy:
        self.logger.info(f"✅ 启用代理: {self.proxy}")

async def _send_request(self, method, url, headers, params):
    # ... 
    request_kwargs = {
        "url": url,
        "timeout": timeout,
        "headers": headers
    }
    
    # 如果配置了代理，则添加代理参数
    if self.proxy:
        request_kwargs["proxy"] = self.proxy
    # ...
```

### 3. 测试脚本更新

在 `test_okx_exchange.py` 中添加了代理检测和提示：

```python
# 检查代理配置
proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
if proxy:
    print(f"📡 使用代理: {proxy}\n")
else:
    print("⚠️  未配置代理，可能无法连接 OKX API")
    print("   如需使用代理，请设置环境变量：")
    print("   - export HTTP_PROXY=http://127.0.0.1:7890")
    print("   - export HTTPS_PROXY=http://127.0.0.1:7890")
```

### 4. 文档和示例

创建了以下文档：
- `PROXY_GUIDE.md` - 详细的代理配置指南
- `config/proxy.example.yml` - 代理配置示例

## 配置优先级

代理配置的优先级如下：

1. **环境变量**（最高优先级）
   - `HTTP_PROXY`
   - `HTTPS_PROXY`

2. **配置文件**
   - `config/exchange.yaml` -> `okx.proxy.https_proxy`
   - `config/exchange.yaml` -> `okx.proxy.http_proxy`

3. **无代理**（默认）

## 使用方法

### 快速开始（推荐）

```bash
# 设置代理环境变量
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890

# 运行测试
python test_okx_exchange.py
```

### 配置文件方式

在 `config/exchange.yaml` 中：

```yaml
okx:
  proxy:
    http_proxy: "http://127.0.0.1:7890"
    https_proxy: "http://127.0.0.1:7890"
    enabled: true
```

## 技术要点

1. **aiohttp 代理支持**
   - aiohttp 原生支持 HTTP/HTTPS/SOCKS5 代理
   - 通过 `proxy` 参数或 `trust_env=True` 启用

2. **环境变量兼容**
   - 遵循 Unix/Linux 标准环境变量命名
   - 与 curl、wget 等工具保持一致

3. **灵活性**
   - 支持多种配置方式
   - 可以根据环境动态切换

4. **向后兼容**
   - 不影响现有代码
   - 代理是可选功能

## 文件修改清单

1. ✅ `config/exchange.yaml` - 添加代理配置项
2. ✅ `exchange/okx/okx_exchange.py` - 实现代理支持
3. ✅ `test_okx_exchange.py` - 添加代理检测
4. ✅ `PROXY_GUIDE.md` - 详细配置指南
5. ✅ `config/proxy.example.yml` - 配置示例

## 下一步

1. 测试代理连接是否正常
2. 验证 WebSocket 代理支持（如需要）
3. 根据实际网络环境优化配置

## 参考资料

- Hummingbot: `/workspace/projects/hummingbot`
- aiohttp 文档: https://docs.aiohttp.org/
- 项目历史: `exchange/okx_client.py`
