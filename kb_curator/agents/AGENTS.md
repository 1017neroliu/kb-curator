# Agent 模块 — LangGraph 状态机

## 文件

| 文件 | 说明 |
|------|------|
| `graph.py` | LangGraph 状态机定义：AgentState TypedDict + 8 个节点函数 |
| `agent_runner.py` | Agent 运行器：LangGraph 编译 + SQLite Checkpointer |

## Agent 工作流

```
ChangeEvent → ClassifyChange → ExtractKnowledge → DetectConflict
  → 无冲突: AutoApply → ExecuteUpdate → LogResult
  → 有冲突: CreateReviewTask → [interrupt] → WaitForDecision → ExecuteDecision → ExecuteUpdate
  → 冗余: Skip
```

## 设计要点

- **单 Agent + 多工具**（LangGraph 状态图驱动）
- 关键破坏性操作（删除、覆盖）必须经 Human Gate
- 使用 `interrupt_before=["wait_for_decision"]` 实现人工审核中断
- `checkpointer` 持久化状态到 SQLite
- Agent API: `/agent/run`, `/agent/resume`, `/agent/state/{thread_id}`
