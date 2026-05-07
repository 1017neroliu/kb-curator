# Frontend 模块 — React 管理面板

## 技术栈

React 19 + TypeScript + Vite 8 + Ant Design 5 + TanStack Query + React Router 7

## 目录结构

```
src/
├── main.tsx               # 入口 (QueryClient + BrowserRouter)
├── App.tsx                # 路由配置 (7 个页面)
├── api/
│   ├── client.ts          # axios 实例 + JWT 拦截器 (401 自动跳转登录)
│   └── types.ts           # TypeScript 类型定义 (对应后端 Pydantic 模型)
├── hooks/
│   ├── useEntries.ts      # 知识条目 CRUD + 语义搜索
│   ├── useSources.ts      # 数据源 CRUD + 轮询
│   ├── useReviews.ts      # 审核任务 + 决策提交
│   ├── useEvents.ts       # 变更事件查询
│   ├── useQuality.ts      # 质量报告 + 触发巡检
│   ├── useKnowledgeBases.ts # 知识库管理 CRUD
│   └── useGraph.ts        # 知识图谱实体/关系/统计
├── layouts/
│   └── MainLayout.tsx     # 侧边栏导航 + 顶栏知识库选择器
├── pages/
│   ├── Dashboard.tsx      # 仪表盘 (统计卡片 + 质量评分 + 事件时间线)
│   ├── Entries.tsx        # 知识条目列表 + 语义搜索 + 新建 (操作列: 主按钮 + 下拉菜单)
│   ├── EntryDetail.tsx    # 条目详情 (Descriptions)
│   ├── Reviews.tsx        # 审核任务列表 + 决策表单 Modal
│   ├── Events.tsx         # 变更事件时间线 (按类型过滤)
│   ├── Sources.tsx        # 数据源管理 CRUD (启用/禁用切换 + 轮询按钮)
│   └── Quality.tsx        # 质量报告列表 + 触发巡检 + 报告详情 (分页)
└── components/
    ├── SearchBar.tsx      # 语义搜索栏
    ├── DecisionForm.tsx   # 审核决策表单 (6 种决策类型 + 合并内容)
    ├── EventTimeline.tsx  # 事件时间线
    └── QualityScore.tsx   # 质量评分仪表盘
```

## 设计约定

- 状态管理：TanStack Query 管理所有服务端状态，自动缓存和刷新
- API 客户端：axios 封装，自动附加 JWT token
- 代码分割：Vite 构建时自动拆分 vendor/antd/app 三个 chunk
- Docker：Multi-stage build (node:20-alpine → nginx:alpine)，nginx 反向代理 API

## 7 个 hooks

覆盖全部 43 个后端 API 端点
