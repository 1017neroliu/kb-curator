# Services 模块 — 业务逻辑层

## 文件

| 文件 | 说明 |
|------|------|
| `base.py` | BaseVectorStore, BaseGraphStore 抽象基类 |
| `db.py` | SQLite 连接（`get_engine`, `get_session_factory`, `get_session`, `init_db`） |
| `crud.py` | 完整 CRUD 操作（7 组：Entry, ChangeEvent, Conflict, ReviewTask, Decision, DataSource, QualityReport） |
| `graph_store.py` | Neo4j 服务（事务写入/连接池） |
| `vector_store.py` | FAISS 服务（批量写入/持久化） |
| `llm.py` | LiteLLM 封装（重试/限流/JSON模式/批量 Embedding） |
| `fingerprinting.py` | 内容指纹计算（content hash + 语义 hash） |
| `change_classifier.py` | LLM 变化分类器（new_info/policy_change/contradiction/correction/redundant） |
| `polling.py` | 轮询调度服务 |
| `review.py` | 审核超时自动处理 |
| `chunker.py` | 文本切片器（fixed/semantic/document 三种策略） |
| `embedding_service.py` | Embedding 服务（LiteLLM 封装 + 缓存 + 相似度计算） |
| `entity_extractor.py` | LLM 实体抽取 |
| `relation_extractor.py` | LLM 关系抽取 |
| `spacy_annotator.py` | spaCy NER 预标注 |
| `entity_aligner.py` | 实体对齐（精确/模糊/语义匹配） |
| `knowledge_extractor.py` | 知识抽取流水线（chunk → extract → align → store） |
| `conflict_detector.py` | 冲突检测服务（语义/结构/时序三种类型） |
| `knowledge_updater.py` | 知识库更新执行器（两阶段写入 + 回滚） |
| `quality_inspector.py` | 质量巡检服务 |

## polling.py 关键逻辑

- `poll_data_source(session, source, classifier, create_entries=False)` — 轮询单个源
  - 从 `_build_known_documents()` 构建 `doc_id → content_hash` 映射用于去重
  - 传入 `since=source.last_polled_at` 实现增量轮询
  - `create_entries=True` 时自动创建条目 + 运行抽取流水线
  - 每次轮询后更新 `last_polled_at` 和 `last_fingerprint`
- `poll_all_sources()` — APScheduler 定时任务，轮询所有 enabled 源并创建条目
- `poll_kb_sources(kb_id)` — 轮询指定知识库的所有源

## crud.py 关键签名

- `list_data_sources(session, kb_id=None, enabled_only=False)` — `kb_id` 为空时列出所有源
- `create_entry(session, **kwargs)` — `metadata` 参数会自动序列化到 `metadata_json` 列
- `update_entry(session, entry_id, **kwargs)` — `metadata` 参数自动映射到 `metadata_json`

## db.py 会话获取

- FastAPI 路由：使用 `SessionDep`（`Annotated[AsyncSession, Depends(get_session)]`）
- 独立服务（scheduler/polling/review）：使用 `from db import get_session` + `async for session in get_session()`

## 冲突检测

- **语义冲突**: Embedding 相似度 + LLM 矛盾判断
- **结构冲突**: 实体属性值比对
- **时序冲突**: TTL 和时间戳分析

## 质量巡检

- 过期检查、低命中率统计、孤立实体检测、元数据一致性检查
- 质量评分算法基于问题严重性加权

## 审核超时

- 默认 24 小时（`schedule.review_timeout_hours`）
- 超时保守策略：保留旧知识，忽略新信息
- 每 30 分钟扫描一次过期审核任务（`auto_resolve_expired_reviews`）
