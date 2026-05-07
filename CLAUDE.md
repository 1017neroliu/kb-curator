# KB-Curator — 知识库"活文档"维护 Agent

## 项目概述

KB-Curator 是一个知识库自动维护 Agent，像自动化图书馆管理员一样持续监控文档源和用户对话，自动抽取新知识、检测冲突、更新知识库（向量库 + 知识图谱），并定期巡检知识质量，实现知识库的"活文档"状态。

## 技术栈

| 类别 | 选型 |
|------|------|
| 后端框架 | FastAPI |
| Agent 框架 | LangGraph (单 Agent + 多工具) |
| 向量数据库 | FAISS (原型) → Milvus (生产) |
| 知识图谱 | Neo4j 社区版 |
| LLM | LiteLLM 统一调用 |
| NLP | spaCy + LLM 混合抽取 |
| 任务队列 | Celery + Redis |
| 调度 | APScheduler |
| 元数据库 | SQLite (SQLAlchemy async) |
| 配置 | Pydantic Settings |
| 日志 | structlog (JSON) |
| 前端 | React + TypeScript + Vite |
| 包管理 | Poetry |
| 代码风格 | Python 3.11+, Ruff |

## 项目结构

```
kb-curator/
├── kb_curator/
│   ├── main.py                    # FastAPI 入口
│   ├── worker.py                  # Celery Worker
│   ├── scheduler.py               # APScheduler
│   ├── core/                      # 配置 + 日志
│   ├── models/                    # Pydantic schemas + SQLAlchemy ORM
│   ├── agents/                    # LangGraph Agent (详见 agents/AGENTS.md)
│   ├── adapters/                  # 文档源适配器 (详见 adapters/AGENTS.md)
│   ├── services/                  # 业务逻辑层 (详见 services/AGENTS.md)
│   └── api/                       # FastAPI 路由层 (详见 api/AGENTS.md)
├── frontend/                      # React 管理面板 (详见 frontend/AGENTS.md)
└── tests/                         # 单元/集成/E2E/性能测试
```

## 架构设计要点

### Agent 工作流（LangGraph）
```
ChangeEvent → ClassifyChange → ExtractKnowledge → DetectConflict
  → 无冲突: AutoApply → ExecuteUpdate → LogResult
  → 有冲突: CreateReviewTask → [interrupt] → WaitForDecision → ExecuteDecision → ExecuteUpdate
  → 冗余: Skip
```

### 多租户
- 通过 `kb_id` 字段实现数据隔离
- 向量库按 `kb_id` 分目录存储
- 知识图谱所有节点/边均携带 `kb_id`

### 核心数据模型
- KnowledgeEntry, TextChunk, KGEntity, KGRelation
- ChangeEvent, Conflict, ReviewTask, Decision
- DataSource, QualityReport, UpdatePlan
- AgentState (LangGraph 状态)

### 数据源轮询流程
1. 创建数据源后自动触发初始扫描（`create_source` → `poll_data_source(create_entries=True)`）
2. 调度器 `poll_all_sources()` 定时轮询所有 enabled 源，自动创建条目
3. 轮询时基于 `_build_known_documents()` 构建 `doc_id → content_hash` 映射做去重
4. 传入 `since=source.last_polled_at` 实现增量轮询
5. 每次轮询后更新 `last_polled_at` 和 `last_fingerprint`

## 子模块详细文档

| 模块 | 文档 |
|------|------|
| Agent | `kb_curator/agents/AGENTS.md` |
| 适配器 | `kb_curator/adapters/AGENTS.md` |
| 服务层 | `kb_curator/services/AGENTS.md` |
| API 层 | `kb_curator/api/AGENTS.md` |
| 前端 | `frontend/AGENTS.md` |

## 关键决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 模式 | 单 Agent + 多工具 | 流程线性度高，减少通信开销，后续可升级 |
| 向量库 | FAISS | 原型轻量，换 Milvus 路径清晰 |
| 任务队列 | Celery + APScheduler 结合 | Celery 处理耗时任务，APScheduler 处理定时调度 |
| KG 方案 | Neo4j 社区版 | 直接生产级方案，避免后续迁移 |
| 配置管理 | Pydantic Settings | 与 FastAPI 生态贴合 |
| 前端 | React + TypeScript | 用户确认需要管理面板 |
| 审核超时 | 24h 保守策略 | 超时保留旧、忽略新 |
| 多租户 | kb_id 隔离 | 当前满足需求 |

## 工作规则

### 自动提交
- 每次完成新功能、bug fix、优化等变更后，验证通过（构建通过、语法检查通过等）即自动 `git commit`，无需等待用户指示
- commit message 使用中文，简洁描述变更内容，格式：`模块: 简要描述`
- 同一逻辑变更归为一个 commit，不拆分过细

## 运行方式

```bash
# 1. 复制环境变量
cp .env.example .env

# 2. 安装依赖
pip install -i https://mirrors.aliyun.com/pypi/simple/ pydantic pydantic-settings fastapi uvicorn structlog sqlalchemy aiosqlite numpy

# 3. 启动基础设施
docker-compose up -d redis neo4j

# 4. 启动 API
python3 -m uvicorn kb_curator.main:app --reload

# 5. 运行测试
python3 -m pytest tests/ -v

# 6. 启动前端开发服务器
cd frontend && npm run dev
# 访问 http://localhost:5173

# 7. Docker 全栈启动
docker-compose up -d
# 前端访问 http://localhost:3000
```

## 当前状态

- **当前阶段**: Phase 4 全部完成
- **测试状态**: 158 通过 (115 unit + 24 integration + 13 e2e + 6 benchmark)
- **前端**: React + TypeScript + Ant Design 5，`npm run build` 构建成功
- **API 文档**: Swagger UI `/docs` + ReDoc `/redoc`，含 11 个 tag 分组
- **依赖安装**: 因网络问题未通过 Poetry 安装，暂用 pip + Aliyun 镜像安装核心依赖，已安装 litellm
- **注意**: Python 版本为 3.10（环境限制），pyproject.toml 声明 3.11+，实际运行在 3.10 上暂无问题
