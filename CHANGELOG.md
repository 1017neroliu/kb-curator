# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/).

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
