# AI API 中转站

生产可用的 AI API 中转站系统，兼容 OpenAI API 格式，支持 OpenAI / Claude / Azure / Gemini 等多种上游。

## 功能特性

- **OpenAI 兼容 API**：直接替换 `base_url`，无需修改客户端代码
- **多渠道路由**：支持多个上游，按优先级 + 加权随机负载均衡
- **自动故障转移**：上游出错自动切换到其他渠道，支持熔断机制
- **精准计费**：内置 GPT-4o / Claude / Gemini 等主流模型价格表，精确扣减额度
- **SSE 流式代理**：完整支持流式（stream=true）响应实时转发
- **令牌管理**：创建多个 Token，独立设置额度/限速/模型权限/IP 白名单
- **速率限制**：滑动窗口限流，支持 Redis 后端（高并发）
- **可视化管理面板**：深色主题单页管理面板（无需构建工具）
- **Docker 一键部署**：内置 MySQL + Redis + Nginx

---

## 快速开始（Docker 部署）

```bash
# 1. 克隆或下载项目
cd ai-api-proxy

# 2. 复制配置文件
cp .env.example .env
# 修改 .env 中的 SECRET_KEY 和 ADMIN_PASSWORD

# 3. 一键启动（包含 MySQL + Redis + Nginx）
docker-compose up -d

# 4. 查看管理员 Token（首次启动时打印）
docker-compose logs app | grep "管理员 Token"

# 5. 访问管理面板
# http://localhost/admin-panel
# 输入步骤 4 中的 Token 登录
```

---

## 手动部署（Python）

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env

# 初始化数据库和管理员账号
python scripts/init_admin.py

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 首次使用指南

1. 打开管理面板：`http://your-server/admin-panel`
2. 输入启动日志中的管理员 Token 登录
3. **添加渠道**：点击「渠道管理」→「添加渠道」，填入上游 API Key 和 Base URL
4. **创建令牌**：点击「令牌管理」→「创建令牌」，设置额度和权限
5. **复制 Token**：创建成功后立即复制（仅显示一次）
6. 使用令牌调用 API（见下方示例）

---

## 配置说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SECRET_KEY` | — | 加密密钥，**必须修改** |
| `ADMIN_USERNAME` | `admin` | 管理员用户名 |
| `ADMIN_PASSWORD` | — | 管理员密码，**必须修改** |
| `DATABASE_URL` | `sqlite:///./proxy.db` | 数据库连接（生产用 MySQL）|
| `REDIS_URL` | 无 | Redis 连接（可选，不配置则用内存限流）|
| `DEFAULT_MULTIPLIER` | `1.0` | 全局计费倍率 |
| `CIRCUIT_BREAKER_THRESHOLD` | `5` | 渠道熔断错误次数阈值 |

---

## API 使用示例

### curl

```bash
curl https://your-server/v1/chat/completions \
  -H "Authorization: Bearer sk-your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'
```

### Python（openai 库）

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-token",
    base_url="https://your-server/v1",
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "你好！"}],
    stream=True,
)
for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

### Node.js

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "sk-your-token",
  baseURL: "https://your-server/v1",
});

const stream = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Hello!" }],
  stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content || "");
}
```

---

## API 文档

启动后访问 `http://your-server/docs` 查看完整的 Swagger 文档。

---

## 常见问题

**Q: 流式响应有延迟/卡顿？**  
A: 检查 Nginx 配置中 `proxy_buffering off` 是否生效。

**Q: 渠道被自动禁用？**  
A: 连续错误次数超过 `CIRCUIT_BREAKER_THRESHOLD`（默认5次）会自动禁用渠道。在管理面板手动启用后，错误计数会重置。

**Q: 如何支持新的 AI 模型？**  
A: 在管理面板「渠道管理」中编辑渠道，在「支持模型」字段添加模型名。计费价格在 `app/core/billing.py` 中的 `MODEL_PRICING` 字典维护。

**Q: SQLite 适合生产环境吗？**  
A: 低并发（<10 QPS）可用 SQLite，高并发请使用 MySQL，修改 `.env` 中的 `DATABASE_URL` 即可。

---

## 运行测试

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```
