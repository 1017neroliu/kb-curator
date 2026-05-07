"""Agent runner with LangGraph compilation and checkpointer."""

from __future__ import annotations

import os
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from kb_curator.core.logging import get_logger
from kb_curator.agents.graph import (
    AgentState,
    receive_event,
    classify_change,
    extract_knowledge,
    detect_conflicts,
    create_review_task,
    wait_for_decision,
    apply_update,
    log_result,
    should_interrupt,
    route_after_classify,
)

log = get_logger(__name__)


class AgentRunner:
    """Runner for the LangGraph agent with checkpointer and interrupt support."""

    def __init__(self, kb_id: str, checkpointer_path: str | None = None) -> None:
        """Initialize the agent runner.

        Args:
            kb_id: Knowledge base ID.
            checkpointer_path: Path to SQLite checkpointer DB. 
                             If None, uses default path.
        """
        self.kb_id = kb_id
        self.checkpointer_path = checkpointer_path or f"/tmp/agent_{kb_id}.sqlite"
        self._graph = None
        self._checkpointer = None

    def _get_checkpointer(self):
        """Get or create the checkpointer."""
        if self._checkpointer is None:
            os.makedirs(os.path.dirname(self.checkpointer_path) or "/tmp", exist_ok=True)
            self._checkpointer = SqliteSaver.from_conn_string(
                f"sqlite:///{self.checkpointer_path}"
            )
        return self._checkpointer

    def _build_graph(self):
        """Build and compile the agent graph."""
        if self._graph is not None:
            return self._graph

        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("receive_event", receive_event)
        workflow.add_node("classify_change", classify_change)
        workflow.add_node("extract_knowledge", extract_knowledge)
        workflow.add_node("detect_conflicts", detect_conflicts)
        workflow.add_node("create_review", create_review_task)
        workflow.add_node("wait_for_decision", wait_for_decision)
        workflow.add_node("apply_update", apply_update)
        workflow.add_node("log_result", log_result)

        # Set entry point
        workflow.set_entry_point("receive_event")

        # Add edges
        workflow.add_edge("receive_event", "classify_change")
        workflow.add_conditional_edges(
            "classify_change",
            route_after_classify,
            {
                "extract_knowledge": "extract_knowledge",
                "log_result": "log_result",
            }
        )
        workflow.add_edge("extract_knowledge", "detect_conflicts")
        workflow.add_conditional_edges(
            "detect_conflicts",
            should_interrupt,
            {
                "create_review": "create_review",
                "apply_update": "apply_update",
            }
        )
        workflow.add_edge("create_review", "wait_for_decision")
        workflow.add_edge("wait_for_decision", "apply_update")
        workflow.add_edge("apply_update", "log_result")
        workflow.add_edge("log_result", END)

        # Compile with checkpointer
        self._graph = workflow.compile(
            checkpointer=self._get_checkpointer(),
            interrupt_before=["wait_for_decision"],
        )

        return self._graph

    async def run(self, config: dict[str, Any], thread_id: str | None = None) -> AgentState:
        """Run the agent with the given configuration.

        Args:
            config: Configuration including kb_id, change_event_id, etc.
            thread_id: Thread ID for checkpointer. If None, generates one.

        Returns:
            Final agent state.
        """
        graph = self._build_graph()
        thread_id = thread_id or config.get("change_event_id", "default")

        initial_state = AgentState(
            kb_id=config.get("kb_id", self.kb_id),
            change_event_id=config.get("change_event_id"),
            change_type=config.get("change_type"),
            entry_id=config.get("entry_id"),
            content=config.get("content"),
            errors=[],
            metadata=config.get("metadata", {}),
        )

        result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": thread_id}})
        return result

    async def resume(self, thread_id: str, human_decision: dict[str, Any]) -> AgentState:
        """Resume an interrupted agent with human decision.

        Args:
            thread_id: Thread ID to resume.
            human_decision: The human decision to apply.

        Returns:
            Final agent state after resuming.
        """
        graph = self._build_graph()

        resume_state = AgentState(
            kb_id=self.kb_id,
            human_decision=human_decision,
        )

        result = await graph.ainvoke(
            resume_state,
            config={"configurable": {"thread_id": thread_id}},
        )
        return result

    def get_state(self, thread_id: str) -> AgentState | None:
        """Get current state of a thread.

        Args:
            thread_id: Thread ID to get state for.

        Returns:
            Current state or None if not found.
        """
        graph = self._build_graph()
        try:
            config = {"configurable": {"thread_id": thread_id}}
            return graph.get_state(config)
        except Exception:
            return None

    def list_threads(self) -> list[str]:
        """List all active thread IDs.

        Returns:
            List of thread IDs.
        """
        # This would need implementation based on checkpointer storage
        return []


# Singleton factory
_agent_runners: dict[str, AgentRunner] = {}


def get_agent_runner(kb_id: str) -> AgentRunner:
    """Get or create an agent runner for a knowledge base.

    Args:
        kb_id: Knowledge base ID.

    Returns:
        AgentRunner instance.
    """
    if kb_id not in _agent_runners:
        _agent_runners[kb_id] = AgentRunner(kb_id=kb_id)
    return _agent_runners[kb_id]
