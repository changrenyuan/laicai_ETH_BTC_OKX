# 代理配置指南

## 问题说明

在某些网络环境下，直接访问 OKX API 可能会遇到连接超时的问题。此时需要配置代理来正常访问交易所接口。

## 解决方案

本系统支持两种代理配置方式：

### 方式 1: 环境变量（推荐）

使用环境变量配置代理，优先级高于配置文件：

**Linux/Mac:**
```bash
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
python test_okx_exchange.py
```

**Windows (PowerShell):**
```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
python test_okx_exchange.py
```

**Windows (CMD):**
```cmd
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890
python test_okx_exchange.py
```

### 方式 2: 配置文件

在 `config/exchange.yaml` 中配置代理：

```yaml
okx:
  # ... 其他配置 ...
  
  # 代理配置
  proxy:
    http_proxy: "http://127.0.0.1:7890"   # HTTP 代理地址
    https_proxy: "http://127.0.0.1:7890"  # HTTPS 代理地址
    enabled: true  # 是否启用代理
```

## 支持的代理类型

1. **HTTP 代理**: `http://host:port`
2. **HTTPS 代理**: `https://host:port`
3. **SOCKS5 代理**: `socks5://host:port`
4. **带认证的代理**: `http://user:password@host:port`

## 常见代理工具配置

| 工具 | 默认端口 | 配置示例 |
|------|---------|---------|
| Clash | 7890 | `http://127.0.0.1:7890` |
| V2Ray | 10808 | `http://127.0.0.1:10808` |
| Shadowsocks | 1080 (需转换) | `socks5://127.0.0.1:1080` |

## 验证代理是否可用

**Linux/Mac:**
```bash
curl -x http://127.0.0.1:7890 https://www.okx.com/api/v5/public/time
```

**Windows:**
```cmd
curl -x http://127.0.0.1:7890 https://www.okx.com/api/v5/public/time
```

如果返回 JSON 数据，说明代理配置正确。

## 永久配置代理

### Linux/Mac

在 `~/.bashrc` 或 `~/.zshrc` 中添加：
```bash
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
```

然后执行：
```bash
source ~/.bashrc  # 或 source ~/.zshrc
```

### Windows

**PowerShell:**
在 `Documents\PowerShell\Microsoft.PowerShell_profile.ps1` 中添加：
```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
```

**系统环境变量:**
1. 右键"此电脑" -> "属性" -> "高级系统设置"
2. 点击"环境变量"
3. 添加以下变量：
   - HTTP_PROXY = `http://127.0.0.1:7890`
   - HTTPS_PROXY = `http://127.0.0.1:7890`

## 代码实现

代理配置已集成到 `OKXExchange` 类中：

```python
class OKXExchange(ExchangeBase):
    def __init__(self, config: Dict):
        # ... 其他初始化代码 ...
        
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

## 注意事项

1. 确保代理工具已启动并正常运行
2. 代理端口是否正确
3. 代理工具是否允许本地连接 (127.0.0.1)
4. 如果使用 VPN，请确保 VPN 工作正常
5. 某些网络环境下可能需要配置白名单或防火墙规则
6. 代理可能影响请求速度，请根据实际情况选择

## 参考

- [aiohttp 代理文档](https://docs.aiohttp.org/en/stable/client_advanced.html#proxy-support)
- [Python 环境变量](https://docs.python.org/3/library/os.html#os.getenv)
- [Hummingbot 网络配置](https://docs.hummingbot.org/)
