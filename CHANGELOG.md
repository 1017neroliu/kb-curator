# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/).

## 2026-11-12

### Added
- 新增项目 README：介绍主要功能、技术栈、本地启动流程、配置、使用方式和开发检查，并说明当前 Docker 部署的配置限制

## 2026-05-08

### Fixed
- WebpageAdapter 网页抓取被 403 拦截：覆盖默认 headers 使用浏览器 UA 和 Accept: text/html，health_check 改用 GET 且容忍 403，新增 cookies 配置支持需登录的网站

### Changed
- 数据源创建弹窗优化：创建后立即关闭弹窗，初始扫描改为后台执行
  - `sources.py` 使用 FastAPI `BackgroundTasks` 异步执行初始扫描，API 立即返回
  - `DataSourceTable` 新增 `scan_status` 字段（pending/scanning/completed/failed）
  - `db.py` `init_db()` 自动迁移旧表添加 `scan_status` 列
  - 前端创建成功后立即关闭弹窗，显示后台扫描进度通知（loading → 成功/失败）
  - 前端表格新增「扫描状态」列，实时显示扫描进度

### Added
- 网页链接数据源适配器 (WebpageAdapter)，支持通过公开网页 URL 创建数据源：
  - 新建 `webpage_adapter.py`：复用 `HttpAdapterMixin`，BeautifulSoup 提取正文，支持 CSS 选择器和同域链接跟随
  - `schemas.py` DataSourceCreate.source_type 新增 `"webpage"`
  - `polling.py` 工厂函数 `create_adapter()` 新增 webpage 分支
  - `sources.py` `_validate_connection_config()` 新增 `urls` 必填校验
  - 前端 `types.ts` SourceType 新增 `'webpage'`，`Sources.tsx` 新增网页链接表单和配置展示
- Wiki/Confluence/Jira 数据源适配器，解决选这三种类型时"创建成功但无数据"的问题：
  - 新建 `HttpAdapterMixin`：共享 httpx 异步客户端、Basic/Bearer 认证、3 次重试 + 429 限流等待 + 指数退避
  - 新建 `WikiAdapter`：MediaWiki Action API（allpages 分页列表、recentchanges 增量轮询、wikitext→纯文本转换）
  - 新建 `ConfluenceAdapter`：Confluence REST API v1（分页列表、CQL 增量轮询、storage HTML→纯文本转换）
  - 新建 `JiraAdapter`：Jira REST API v2（JQL 搜索、issue→markdown 文档、ADF 递归文本提取、可选评论采集）
  - `polling.py` 工厂函数 `create_adapter()` 新增 wiki/confluence/jira 三个分支
  - `sources.py` 新增 `_validate_connection_config()` 校验必填字段
  - 前端 `Sources.tsx` 创建表单新增 wiki/confluence/jira 条件字段，配置列按类型显示连接信息

## 2026-05-07

### Added
- 知识库问答（QA）功能，支持检索增强生成（RAG）：
  - 后端新增 QA schemas：`ChatMessage`、`QARequest`、`QASource`、`QAResponse`
  - 后端新增 `QASettings` 配置类（top_k、graph_expand_limit、context_max_chars、qa_temperature、streaming_enabled）
  - 后端新增 `QAService` 服务类，实现 embed→vector search→graph expand→context assembly→LLM generate 全流程
  - 后端新增 SSE 流式问答接口 `POST /api/v1/qa/ask/stream`（先发 sources 事件，再逐 token 流出）
  - 后端新增非流式问答接口 `POST /api/v1/qa/ask`
  - 前端新增 QA 类型定义（`ChatMessage`、`QARequest`、`QASource`、`QAResponse`、`QASSESourceEvent`、`QASSETokenEvent`）
  - 前端新增 `useQA` hooks（`useQAAsk` 非流式、`useQAStream` 流式 SSE 解析）
  - 前端新增聊天式问答页面（流式输出、来源引用折叠面板、清空对话）
  - 前端导航新增"知识问答"菜单项

## 2025-05-07

### Added
- CLAUDE.md 新增自动提交规则：验证通过后自动 git commit
- CLAUDE.md 新增 Changelog 规则：每次提交后同步更新 CHANGELOG.md

### Changed
- CLAUDE.md 精简重构（598 行 → 137 行），Phase 4 实现细节拆分到 5 个子模块 AGENTS.md
  - `kb_curator/agents/AGENTS.md`
  - `kb_curator/adapters/AGENTS.md`
  - `kb_curator/services/AGENTS.md`
  - `kb_curator/api/AGENTS.md`
  - `frontend/AGENTS.md`

### Fixed
- 数据源轮询全链路修复：
  - `list_data_sources` 空 kb_id 时查不到任何数据源 → 改为可选参数，为空时列出全部
  - `poll_all_sources` 只创建 ChangeEvent 不创建 Entry → 新增 `create_entries=True` 参数，自动创建条目并运行抽取流水线
  - 创建数据源后无初始扫描 → `create_source` 自动触发 `poll_data_source(create_entries=True)`
  - `FileAdapter._file_cache` 每次实例化都是空的导致重复 → 改为 `known_documents` 参数，由调用方从数据库构建去重映射
  - `since` 时间过滤从未生效 → 传入 `source.last_polled_at`
- `get_db_session` 导入错误（services/db.py 只导出 `get_session`），修复 `review.py`、`knowledge_updater.py`、`polling.py`
- `FileAdapter.poll()` 中 `change_type` 使用裸字符串 → 改用 `ChangeType.NEW_INFO` / `ChangeType.POLICY_CHANGE` 枚举

### Changed
- Entries 页面操作列优化：4 个按钮平铺 → 主按钮 + 下拉菜单
- Quality 报告详情弹窗 issues 表格：`pagination={false}` → 分页显示（每页 10 条）
