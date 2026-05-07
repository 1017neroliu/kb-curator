# Adapters 模块 — 文档源适配器

## 文件

| 文件 | 说明 |
|------|------|
| `base.py` | BaseDocumentSource 抽象基类 + DocumentChange / DocumentMetadata 数据类 |
| `file_adapter.py` | 文件目录监听适配器 |

## BaseDocumentSource 接口

- `poll(since, known_documents)` — 轮询变化，`known_documents` 为 `doc_id → content_hash` 映射用于去重
- `list_documents()` — 列出所有文档及元数据
- `get_content(document_id)` — 获取文档内容
- `health_check()` — 健康检查
- `compute_fingerprint()` — 计算源级别指纹（所有文档 hash 汇总）

## FileAdapter

- 监控本地文件目录，支持递归遍历、文件模式过滤、增量变化检测
- `poll()` 通过 `known_documents` 参数实现去重，不依赖内存缓存
- 默认支持扩展名：`.txt .md .markdown .rst .json .yaml .yml .xml .html .htm`
- 配置项（`connection_config`）：`base_path`, `recursive`, `file_patterns`, `encoding`

## 去重机制

`poll()` 接收 `known_documents: dict[str, str]`（`doc_id → content_hash`），由调用方（`polling.py`）从数据库已有条目的 `metadata.document_id` + `metadata.fingerprint_after` 构建。如果 `doc_id` 已存在且 hash 不变，则跳过；hash 变化则为修改文件。
