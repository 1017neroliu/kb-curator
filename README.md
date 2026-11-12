# KB-Curator

知识库「活文档」维护 Agent：持续监控文档源，抽取知识、检测冲突、更新知识条目与知识图谱，并通过质量巡检和人工审核维护知识库。提供 Web 管理面板及基于检索增强生成（RAG）的知识问答。

## 主要功能

- **多源接入**：支持本地文件目录、MediaWiki、Confluence、Jira 和网页 URL；创建数据源后在后台执行初始扫描，支持增量轮询和内容指纹去重。
- **知识维护**：对文档分块，抽取实体和关系，结合向量检索与知识图谱进行知识更新。
- **冲突审核**：检测新旧知识冲突，生成审核任务，通过人工决策控制更新。
- **质量巡检**：定时检查知识质量，在管理面板查看质量报告、变更事件和审核任务。
- **知识问答**：结合向量检索和图谱上下文生成回答，支持流式输出及来源引用。
- **多知识库管理**：通过 `kb_id` 区分知识库，分别管理条目、数据源和图谱。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| API | Python、FastAPI、Pydantic Settings |
| Agent | LangGraph、LangChain、LiteLLM |
| 知识抽取 | spaCy、LLM |
| 存储 | SQLite / SQLAlchemy、FAISS、Neo4j |
| 异步任务与调度 | Celery、Redis、APScheduler |
| 前端 | React、TypeScript、Vite、Ant Design、TanStack Query |

## 本地开发

### 1. 准备环境

- Python 3.11+ 和 Poetry。
- Node.js 22.12+（前端使用 Vite 8）及 npm。
- Redis 7 和 Neo4j 5 Community；也可使用 Docker Compose 启动这两个服务。
- 可调用聊天模型及 Embedding 模型的 API 凭据。

```bash
git clone https://github.com/1017neroliu/kb-curator.git
cd kb-curator
cp .env.example .env
poetry install
# 当前依赖清单尚未声明网页适配器使用的 BeautifulSoup，需补充安装
poetry run pip install beautifulsoup4
```

### 2. 配置服务

编辑 `.env`，确认 Neo4j 地址和密码与实际服务一致。嵌套配置使用双下划线 `__`：

```dotenv
KB_CURATOR_GRAPH_STORE__URI=bolt://localhost:7687
KB_CURATOR_GRAPH_STORE__USER=neo4j
KB_CURATOR_GRAPH_STORE__PASSWORD=password
KB_CURATOR_REDIS__URL=redis://localhost:6379/0
KB_CURATOR_REDIS__CELERY_BROKER_URL=redis://localhost:6379/1
KB_CURATOR_REDIS__CELERY_RESULT_BACKEND=redis://localhost:6379/2
KB_CURATOR_LLM__MODEL=gpt-4o-mini
KB_CURATOR_LLM__EMBEDDING_MODEL=text-embedding-3-small
KB_CURATOR_LLM__EMBEDDING_DIMENSIONS=1536
```

LiteLLM 使用模型供应商的凭据。以 OpenAI 为例，在运行 API 和 Worker 的终端中设置 `OPENAI_API_KEY`：

```bash
export OPENAI_API_KEY="your-api-key"
```

使用其他供应商时，按 LiteLLM 的模型命名及凭据规则配置。聊天模型和 Embedding 模型均需可用。

### 3. 启动基础设施和后端

如使用仓库中的 Compose 文件启动基础设施：

```bash
docker compose up -d redis neo4j
```

该配置中的 Neo4j 使用 host 网络，适合 Linux 主机；其他环境可自行运行 Neo4j 并调整连接地址。Compose 的 `NEO4J_PASSWORD` 与应用的 `KB_CURATOR_GRAPH_STORE__PASSWORD` 应保持一致。

在项目根目录分别打开终端运行：

```bash
# API
poetry run uvicorn kb_curator.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# 异步任务 Worker
poetry run celery -A kb_curator.worker worker -l info
```

```bash
# 定时轮询与质量巡检调度器
poetry run python -m kb_curator.scheduler
```

API 启动时会初始化数据库。默认 SQLite、向量索引等数据保存在 `data/` 下。

### 4. 启动前端

```bash
cd frontend
npm ci
npm run dev
```

打开 http://localhost:5173 。开发服务器会将 `/api` 请求代理到 `http://localhost:8000`。

| 入口 | 地址 |
| --- | --- |
| 管理面板 | http://localhost:5173 |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| 健康检查 | http://localhost:8000/api/v1/system/health |

## 使用流程

1. 在管理面板创建或选择知识库。
2. 添加数据源，填写对应的目录路径、网页 URL 或远程服务连接配置。
3. 等待后台初始扫描完成，在数据源列表查看扫描状态，在知识条目页面检查导入内容。
4. 查看知识图谱、变更事件、冲突审核和质量报告，处理需要人工决策的任务。
5. 在「知识问答」页面提问，并查看回答引用的来源。

本地文件路径必须能被后端进程访问；如果后端运行在容器中，需要先挂载相应目录。

## 常用配置

配置来源为环境变量和项目根目录的 `.env`。完整字段及默认值见 [配置代码](kb_curator/core/config.py)，基础示例见 [.env.example](.env.example)。

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `KB_CURATOR_DATABASE__SQLITE_URL` | `sqlite+aiosqlite:///./data/kb_curator.db` | 元数据库 |
| `KB_CURATOR_VECTOR_STORE__FAISS_INDEX_PATH` | `./data/faiss_indexes` | 向量索引目录 |
| `KB_CURATOR_SCHEDULE__POLL_INTERVAL_MINUTES` | `60` | 数据源轮询间隔 |
| `KB_CURATOR_SCHEDULE__REVIEW_TIMEOUT_HOURS` | `24` | 审核超时时间 |
| `KB_CURATOR_QA__TOP_K` | `5` | 问答检索分块数 |
| `KB_CURATOR_AUTH__ENABLED` | `false` | API 认证开关 |
| `KB_CURATOR_AUTH__SECRET_KEY` | `change-me-in-production` | 认证签名密钥 |
| `KB_CURATOR_LOG_LEVEL` | `INFO` | 日志级别 |

对外部署前应配置认证并更换默认密钥和数据库密码。

### Docker 部署说明

仓库提供 API、Worker、Scheduler、前端、Redis 和 Neo4j 的 [Compose 配置](docker-compose.yml)，部署细节见 [部署文档](docs/deployment.md)。当前全栈容器部署需先处理以下配置问题：

- 后端 Dockerfile 在复制应用源码和 README 前执行 `poetry install`，需调整复制顺序或先使用 `--no-root` 安装依赖。
- 网页适配器需要 `beautifulsoup4`，当前 Python 依赖清单尚未包含它。
- Compose 中部分连接配置使用旧变量名，需改为上述双下划线形式；容器中 Redis 使用主机名 `redis`，Neo4j 按现有 host 网络设计使用 `host.docker.internal`。

部署文档中的旧配置名也应以当前配置代码及本 README 为准。

## 项目结构

```text
kb_curator/
├── main.py          # FastAPI 入口
├── worker.py        # Celery Worker
├── scheduler.py     # 定时任务
├── core/            # 配置、日志等基础能力
├── models/          # 数据模型
├── adapters/        # 数据源适配器
├── agents/          # LangGraph 工作流和工具
├── services/        # 抽取、检索、更新、审核、问答等业务逻辑
└── api/             # API 路由
frontend/            # Web 管理面板
configs/             # 配置文件
scripts/             # 辅助脚本
tests/               # 单元、集成、端到端和基准测试
docs/                # 部署文档
data/                # 本地运行数据
```

## 开发检查

在项目根目录执行：

```bash
poetry run pytest tests/unit/ -v
poetry run pytest tests/ -v
poetry run ruff check kb_curator tests
```

前端构建：

```bash
cd frontend
npm run build
```

## 更多文档

- [变更记录](CHANGELOG.md)
- [部署文档](docs/deployment.md)
- [项目开发约定与架构说明](CLAUDE.md)
