# KB-Curator 部署文档

## 目录

- [环境要求](#环境要求)
- [快速启动](#快速启动)
- [Docker Compose 部署（推荐）](#docker-compose-部署推荐)
- [手动部署](#手动部署)
- [配置说明](#配置说明)
- [API 文档](#api-文档)
- [前端部署](#前端部署)
- [生产环境注意事项](#生产环境注意事项)
- [监控与日志](#监控与日志)
- [常见问题](#常见问题)

---

## 环境要求

| 组件 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.10+ | 3.11 推荐 |
| Node.js | 18+ | 前端构建 |
| Docker | 20.10+ | 容器化部署 |
| Docker Compose | 2.0+ | 编排 |
| Redis | 7+ | Celery broker + 缓存 |
| Neo4j | 5+ Community | 知识图谱存储 |

---

## 快速启动

### 1. 克隆项目

```bash
git clone <repo-url> && cd kb-curator
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少设置以下变量：
# - KB_CURATOR_NEO4J_PASSWORD  (Neo4j 密码)
# - KB_CURATOR_AUTH_SECRET_KEY (JWT 签名密钥，生产环境必须修改)
```

### 3. 启动所有服务

```bash
docker-compose up -d
```

启动后访问：
- 前端管理面板: http://localhost:3000
- API 文档 (Swagger): http://localhost:8000/docs
- API 文档 (ReDoc): http://localhost:8000/redoc

---

## Docker Compose 部署（推荐）

### 服务架构

```
┌─────────────┐     ┌──────────────┐
│  Frontend   │────▶│  API Server  │
│  (nginx)    │     │  (FastAPI)   │
│  :3000      │     │  :8000       │
└─────────────┘     └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──┐  ┌──────▼──┐  ┌─────▼────┐
       │  Redis  │  │  Neo4j  │  │  Worker  │
       │  :6379  │  │  :7687  │  │ (Celery) │
       └─────────┘  └─────────┘  └──────────┘
                                      │
                               ┌──────▼──────┐
                               │  Scheduler  │
                               │(APScheduler)│
                               └─────────────┘
```

### 启动命令

```bash
# 启动所有服务
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f api

# 停止所有服务
docker-compose down

# 停止并删除数据卷（重置数据）
docker-compose down -v
```

### 自定义端口

通过 `.env` 或环境变量修改端口：

```bash
# API 端口（默认 8000）
KB_CURATOR_API_PORT=8080

# 前端端口（默认 3000）
KB_CURATOR_FRONTEND_PORT=8080
```

---

## 手动部署

### 1. 启动基础设施

```bash
# 仅启动 Redis 和 Neo4j
docker-compose up -d redis neo4j
```

### 2. 安装 Python 依赖

```bash
# 使用 pip（推荐用 venv）
python3 -m venv .venv
source .venv/bin/activate
pip install -i https://mirrors.aliyun.com/pypi/simple/ \
    pydantic pydantic-settings fastapi uvicorn structlog \
    sqlalchemy aiosqlite numpy httpx litellm \
    langgraph langchain-core

# 或使用 Poetry
poetry install
```

### 3. 启动 API 服务

```bash
uvicorn kb_curator.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 启动 Celery Worker

```bash
celery -A kb_curator.worker worker -l info
```

### 5. 启动 Scheduler

```bash
python -m kb_cururator.scheduler
```

### 6. 启动前端

```bash
cd frontend
npm install
npm run dev
# 开发模式访问 http://localhost:5173
```

---

## 配置说明

所有配置通过环境变量加载，前缀为 `KB_CURATOR_`。详见 `.env.example`。

### 核心配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `KB_CURATOR_DEBUG` | `false` | 调试模式 |
| `KB_CURATOR_API_HOST` | `0.0.0.0` | API 监听地址 |
| `KB_CURATOR_API_PORT` | `8000` | API 端口 |
| `KB_CURATOR_LOG_LEVEL` | `INFO` | 日志级别 |
| `KB_CURATOR_LOG_FORMAT` | `json` | 日志格式 (`json` / `console`) |

### LLM 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `KB_CURATOR_LLM_MODEL` | `gpt-4o-mini` | Chat 模型 |
| `KB_CURATOR_LLM_TEMPERATURE` | `0.0` | 生成温度 |
| `KB_CURATOR_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding 模型 |
| `KB_CURATOR_EMBEDDING_DIMENSIONS` | `1536` | Embedding 维度 |

### 存储配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `KB_CURATOR_DATABASE_SQLITE_URL` | `sqlite+aiosqlite:///./data/kb_curator.db` | 元数据库 |
| `KB_CURATOR_NEO4J_URI` | `bolt://localhost:7687` | Neo4j URI |
| `KB_CURATOR_NEO4J_PASSWORD` | `password` | Neo4j 密码 |
| `KB_CURATOR_REDIS_URL` | `redis://localhost:6379/0` | Redis URL |

### 认证配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `KB_CURATOR_AUTH_ENABLED` | `false` | 是否启用 JWT 认证 |
| `KB_CURATOR_AUTH_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| `KB_CURATOR_AUTH_TOKEN_EXPIRE_MINUTES` | `1440` | Token 有效期（分钟） |

### 调度配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `KB_CURATOR_SCHEDULE_POLL_INTERVAL_MINUTES` | `60` | 轮询间隔 |
| `KB_CURATOR_SCHEDULE_REVIEW_TIMEOUT_HOURS` | `24` | 审核超时时间 |
| `KB_CURATOR_SCHEDULE_AUTO_RESOLVE_CHECK_INTERVAL_MINUTES` | `30` | 超时检查间隔 |

---

## API 文档

启动 API 服务后，访问以下地址查看自动生成的 OpenAPI 文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### API 端点总览

| 路由组 | 端点数 | 路径前缀 |
|--------|--------|----------|
| System | 2 | `/api/v1/system` |
| Auth | 1 | `/api/v1/auth` |
| Knowledge Bases | 4 | `/api/v1/knowledge-bases` |
| Entries | 7 | `/api/v1/knowledge-bases/{kb_id}/entries` |
| Sources | 5 | `/api/v1/knowledge-bases/{kb_id}/sources` |
| Events | 3 | `/api/v1/knowledge-bases/{kb_id}/events` |
| Conflicts | 3 | `/api/v1/knowledge-bases/{kb_id}/conflicts` |
| Reviews | 6 | `/api/v1/knowledge-bases/{kb_id}/reviews` |
| Quality | 3 | `/api/v1/knowledge-bases/{kb_id}/quality` |
| Knowledge Graph | 9 | `/api/v1/knowledge-bases/{kb_id}/graph` |
| Agent | 3 | `/api/v1/agent` |

---

## 前端部署

### 开发模式

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
# API 请求自动代理到 http://localhost:8000
```

### 生产构建

```bash
cd frontend
npm run build
# 构建产物在 dist/ 目录
```

### Docker 部署（前端）

前端使用 multi-stage Docker 构建：

1. **Stage 1**: `node:20-alpine` 执行 `npm run build`
2. **Stage 2**: `nginx:alpine` 提供静态文件服务 + API 反向代理

nginx 配置（`frontend/nginx.conf`）：
- `/api/` 路径反向代理到后端 API 服务
- 其他路径回退到 `index.html`（SPA 路由）

---

## 生产环境注意事项

### 1. 安全

- **必须修改** `KB_CURATOR_AUTH_SECRET_KEY`，使用强随机字符串
- 启用认证：`KB_CURATOR_AUTH_ENABLED=true`
- 配置 HTTPS（通过反向代理如 nginx/traefik）
- 限制 API 端口仅内网访问

### 2. Neo4j

- 生产环境使用独立 Neo4j 集群
- 定期备份 Neo4j 数据
- 调整 `max_connection_pool_size` 适配并发量

### 3. 向量库迁移

原型使用 FAISS（单机文件存储），生产环境建议迁移到 Milvus：

```python
# 修改配置
KB_CURATOR_VECTOR_STORE_TYPE=milvus
KB_CURATOR_MILVUS_URI=http://milvus:19530
```

`BaseVectorStore` 抽象基类已定义标准接口，只需实现 Milvus 适配器。

### 4. 数据备份

```bash
# SQLite 备份
cp data/kb_curator.db data/kb_curator.db.bak

# Neo4j 备份
docker-compose exec neo4j neo4j-admin database dump neo4j --output-path=/backups/neo4j.dump

# Redis 持久化（已配置 appendonly）
# 数据在 redis_data 卷中
```

### 5. 性能调优

- **API Workers**: `KB_CURATOR_API_WORKERS=4`（生产环境建议 4-8）
- **LLM 限流**: `KB_CURATOR_LLM_RPM_LIMIT=60`（根据 API 配额调整）
- **Celery 并发**: `celery -A kb_curator.worker worker --concurrency=4`
- **FAISS**: 切换到 Milvus 以支持分布式向量搜索

---

## 监控与日志

### 日志格式

使用 structlog 输出 JSON 格式日志：

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "info",
  "event": "entry_created",
  "entry_id": "abc123",
  "kb_id": "kb_001"
}
```

### 健康检查

```bash
# 基础健康检查
curl http://localhost:8000/api/v1/system/health

# 就绪检查（含 Redis、Neo4j 状态）
curl http://localhost:8000/api/v1/system/ready
```

### Docker 健康检查

docker-compose 已配置 healthcheck：

- **API**: HTTP 请求 `/api/v1/system/health`
- **Redis**: `redis-cli ping`
- **Neo4j**: `cypher-shell 'RETURN 1'`

---

## 常见问题

### Q: 启动时报 `no such table` 错误

A: 数据库未初始化。API 服务首次启动时会自动创建表。如果手动测试，需先调用初始化：

```python
from kb_curator.services.db import init_db
import asyncio
asyncio.run(init_db())
```

### Q: Neo4j 连接失败

A: 检查：
1. Neo4j 服务是否启动：`docker-compose ps neo4j`
2. 密码是否匹配：`.env` 中的 `KB_CURATOR_NEO4J_PASSWORD` 与 `NEO4J_PASSWORD` 一致
3. 端口是否可达：`docker-compose exec neo4j cypher-shell -u neo4j -p password 'RETURN 1'`

### Q: LLM 调用失败

A: 检查：
1. API Key 是否配置（LiteLLM 使用 `OPENAI_API_KEY` 等标准环境变量）
2. 网络是否可达
3. `KB_CURATOR_LLM_MODEL` 配置是否正确

### Q: 前端页面空白

A: 检查：
1. 后端 API 是否正常：`curl http://localhost:8000/api/v1/system/health`
2. nginx 反向代理配置是否正确
3. 浏览器控制台是否有 CORS 错误

### Q: 如何重置所有数据

```bash
docker-compose down -v
docker-compose up -d
```

这会删除所有数据卷（SQLite、Redis、Neo4j），重新开始。

---

## 测试

```bash
# 运行全部测试
python3 -m pytest tests/ -v

# 仅运行单元测试
python3 -m pytest tests/unit/ -v

# 仅运行集成测试
python3 -m pytest tests/integration/ -v

# 运行端到端测试
python3 -m pytest tests/e2e/ -v

# 运行性能基准测试
python3 -m pytest tests/benchmark/ -v -s

# 前端构建测试
cd frontend && npm run build
```
