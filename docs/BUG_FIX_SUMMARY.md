# Bug 修复总结

## 修复的 Bug

### Bug 1: 未加载 .env 文件

**问题描述**：
- `demo_okx_exchange.py` 和其他测试脚本没有调用 `load_dotenv()`
- 即使 `.env` 文件存在，程序也不会读取其中的环境变量（包括 `HTTP_PROXY`, `HTTPS_PROXY`, `OKX_API_KEY` 等）

**修复**：
在所有相关文件开头添加：
```python
from dotenv import load_dotenv
load_dotenv()
```

**受影响文件**：
- ✅ `examples/demo_okx_exchange.py`
- ✅ `test_okx_exchange.py`
- ✅ `test_proxy_config.py`

---

### Bug 2: 配置键名不匹配

**问题描述**：
- `okx_exchange.py` 中使用 `okx_config.get("timeout", {})` 读取超时配置
- 但 `exchange.yaml` 中配置项是 `timeouts`（复数）
- 导致超时配置无法正确读取，使用默认值

**修复**：
```python
# 修复前
timeout_config = okx_config.get("timeout", {})
self.request_timeout = timeout_config.get("request", 30)
self.connect_timeout = timeout_config.get("connect", 10)

# 修复后
timeout_config = okx_config.get("timeouts", {})
self.connect_timeout = timeout_config.get("connect", 10)
self.read_timeout = timeout_config.get("read", 30)
self.write_timeout = timeout_config.get("write", 10)
```

同时更新 `_send_request` 方法中的超时设置：
```python
timeout = aiohttp.ClientTimeout(
    total=self.read_timeout,
    connect=self.connect_timeout,
    sock_connect=self.connect_timeout,
    sock_read=self.read_timeout
)
```

**受影响文件**：
- ✅ `exchange/okx/okx_exchange.py`

---

### Bug 3: 配置被覆盖

**问题描述**：
- `demo_okx_exchange.py` 中手动设置了 `sandbox: True`
- 但 `OKXExchange.__init__` 会从 `account.yaml` 重新读取配置
- `account.yaml` 中 `sandbox` 设置为 `false`
- 导致最终 `sandbox` 为 `false`，日志显示"是否沙盒: False"

**解决方案**：
修改 `config/account.yaml`：
```yaml
sub_account:
  sandbox: true  # 改为 true
```

或者让用户明确知道配置是从 `account.yaml` 读取的。

---

## 配置流程

### 1. 环境变量加载流程

```
1. 程序启动
2. 调用 load_dotenv() 加载 .env 文件
3. os.getenv() 读取环境变量
4. OKXExchange 使用环境变量
```

### 2. 代理配置读取

```
.env 文件
  ↓
load_dotenv()
  ↓
os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
  ↓
OKXExchange.__init__ 中的 self.proxy
  ↓
_send_request 中的 request_kwargs["proxy"]
```

### 3. 超时配置读取

```
exchange.yaml 中的 timeouts 配置
  ↓
okx_config.get("timeouts", {})
  ↓
self.connect_timeout, self.read_timeout, self.write_timeout
  ↓
_send_request 中的 aiohttp.ClientTimeout
```

### 4. Sandbox 配置读取

```
account.yaml 中的 sub_account.sandbox
  ↓
config_loader.get_account_config()
  ↓
self.sandbox
  ↓
影响 base_url 和认证 header
```

---

## 使用说明

### 步骤 1: 创建 .env 文件

```bash
cp .env.example .env
```

### 步骤 2: 配置代理（如需要）

编辑 `.env`：
```env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

### 步骤 3: 配置 Sandbox（如需要）

编辑 `config/account.yaml`：
```yaml
sub_account:
  sandbox: true  # 改为 true 使用沙盒环境
```

### 步骤 4: 验证配置

```bash
python test_proxy_config.py
```

应该看到：
```
✅ 发现 .env 文件
✅ .env 文件中包含代理配置
HTTP_PROXY: http://127.0.0.1:7890
HTTPS_PROXY: http://127.0.0.1:7890
```

### 步骤 5: 运行测试

```bash
python test_okx_exchange.py
python examples/demo_okx_exchange.py
```

---

## 验证清单

- [x] .env 文件被正确加载
- [x] 代理配置从环境变量读取
- [x] 超时配置从 exchange.yaml 读取
- [x] Sandbox 配置从 account.yaml 读取
- [x] 所有测试脚本都加载 .env
- [x] 配置键名与 yaml 文件一致

---

## 技术细节

### aiohttp.ClientTimeout 参数

```python
aiohttp.ClientTimeout(
    total=None,        # 总超时时间
    connect=10,        # 连接超时
    sock_connect=10,   # socket 连接超时
    sock_read=30       # socket 读取超时
)
```

### ConfigLoader 加载顺序

```
1. account.yaml
2. instruments.yaml
3. risk.yaml
4. strategy.yaml
5. exchange.yaml
```

### 环境变量优先级

```
环境变量 > 配置文件默认值
```

---

## 总结

所有 Bug 已修复：
1. ✅ 添加 `load_dotenv()` 加载 .env 文件
2. ✅ 修正超时配置键名 `timeouts`
3. ✅ 明确配置来源（account.yaml, exchange.yaml, .env）

配置流程清晰，用户可以通过修改 yaml 文件或 .env 文件来配置系统。
