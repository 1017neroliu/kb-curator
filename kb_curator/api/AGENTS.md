# API 模块 — FastAPI 路由层

## 文件

| 文件 | 说明 |
|------|------|
| `deps.py` | FastAPI 依赖注入 + JWT Token 认证（`get_current_user`, `UserDep`, `SessionDep`） |
| `routes/system.py` | `/health` + `/ready` |
| `routes/auth.py` | `/auth/token` (JWT 签发) |
| `routes/knowledge_bases.py` | `/knowledge-bases` (知识库管理 CRUD) |
| `routes/entries.py` | `/knowledge-bases/{kb_id}/entries` + `/search` + `/count` |
| `routes/sources.py` | `/knowledge-bases/{kb_id}/sources` + `/poll` |
| `routes/events.py` | `/knowledge-bases/{kb_id}/events` |
| `routes/conflicts.py` | `/knowledge-bases/{kb_id}/conflicts` |
| `routes/reviews.py` | `/knowledge-bases/{kb_id}/reviews` + `/decisions` |
| `routes/quality.py` | `/knowledge-bases/{kb_id}/quality` |
| `routes/knowledge_graph.py` | `/knowledge-bases/{kb_id}/graph` (实体/关系/统计) |
| `routes/agent.py` | `/agent` (Agent 触发/恢复/状态) |

## API 路由 (11 组, ~40 端点)

- `/system` — 健康检查
- `/auth` — Token 认证 (JWT 签发)
- `/knowledge-bases` — 知识库管理 (list/create/get/delete)
- `/knowledge-bases/{kb_id}/entries` — 知识条目 CRUD + 语义搜索
- `/knowledge-bases/{kb_id}/sources` — 数据源管理 CRUD + 手动轮询
- `/knowledge-bases/{kb_id}/events` — 变更事件
- `/knowledge-bases/{kb_id}/conflicts` — 冲突管理
- `/knowledge-bases/{kb_id}/reviews` — 审核任务 CRUD + 决策提交
- `/knowledge-bases/{kb_id}/quality` — 质量巡检
- `/knowledge-bases/{kb_id}/graph` — 知识图谱查询 (实体/关系/统计)
- `/agent` — Agent 触发/恢复

## sources.py 特殊逻辑

- `POST /knowledge-bases/{kb_id}/sources` — 创建数据源后自动触发初始扫描（调用 `poll_data_source(create_entries=True)`）
- `POST /knowledge-bases/{kb_id}/sources/poll` — 手动轮询所有 enabled 数据源

## 认证

- `deps.py`: `get_current_user` 依赖，支持 JWT Bearer Token 验证
- `UserDep` 类型注解，`auth.enabled=False` 时自动跳过认证
- `SessionDep` = `Annotated[AsyncSession, Depends(get_session)]`
