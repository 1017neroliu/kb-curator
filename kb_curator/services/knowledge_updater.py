"""Knowledge base update executor.

Handles the execution of update plans:
- Vector store updates
- Graph store updates
- Knowledge entry version management
- Two-phase commit with rollback
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import (
    DecisionType,
    KGEntityCreate,
    KGRelationCreate,
    TextChunk,
    UpdateOperation,
    UpdatePlan,
)
from kb_curator.services.crud import update_entry

log = get_logger(__name__)


class UpdateStatus(str, Enum):
    """Status of an update operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class UpdateResult:
    """Result of an update operation."""
    success: bool
    status: UpdateStatus
    operations_completed: int = 0
    operations_failed: int = 0
    errors: list[str] = field(default_factory=list)
    rollback_performed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeUpdater:
    """Executor for knowledge base update plans."""

    def __init__(
        self,
        kb_id: str,
        vector_store=None,
        graph_store=None,
    ) -> None:
        """Initialize the updater.

        Args:
            kb_id: Knowledge base ID.
            vector_store: Optional vector store instance.
            graph_store: Optional graph store instance.
        """
        self.kb_id = kb_id
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._completed_operations: list[UpdateOperation] = []

    async def execute_plan(self, plan: UpdatePlan) -> UpdateResult:
        """Execute an update plan with rollback support.

        Args:
            plan: The update plan to execute.

        Returns:
            UpdateResult with execution status.
        """
        result = UpdateResult(success=True, status=UpdateStatus.IN_PROGRESS)
        self._completed_operations = []

        try:
            for i, operation in enumerate(plan.operations):
                try:
                    await self._execute_operation(operation)
                    self._completed_operations.append(operation)
                    result.operations_completed += 1
                except Exception as e:
                    log.error("operation_failed", 
                              operation=str(operation), error=str(e))
                    result.operations_failed += 1
                    result.errors.append(f"Operation {i}: {str(e)}")
                    
                    # Rollback on failure if configured
                    if plan.requires_human_approval or result.operations_completed > 0:
                        await self._rollback(result)
                        result.rollback_performed = True
                        break

            if result.errors:
                result.success = False
                result.status = UpdateStatus.FAILED
            else:
                result.status = UpdateStatus.COMPLETED

        except Exception as e:
            log.error("plan_execution_failed", error=str(e))
            result.success = False
            result.status = UpdateStatus.FAILED
            result.errors.append(str(e))
            await self._rollback(result)
            result.rollback_performed = True

        return result

    async def _execute_operation(self, operation: UpdateOperation) -> None:
        """Execute a single update operation.

        Args:
            operation: The operation to execute.
        """
        if operation.target == "vector_store":
            await self._execute_vector_operation(operation)
        elif operation.target == "graph_store":
            await self._execute_graph_operation(operation)
        elif operation.target == "knowledge_entry":
            await self._execute_entry_operation(operation)
        else:
            raise ValueError(f"Unknown target: {operation.target}")

    async def _execute_vector_operation(self, operation: UpdateOperation) -> None:
        """Execute a vector store operation."""
        if self._vector_store is None:
            raise RuntimeError("Vector store not configured")

        data = operation.data
        strategy = operation.strategy

        if strategy == "CREATE" or strategy == "APPEND":
            # FAISSVectorStore.add_batch(chunk_ids, embeddings, metadatas)
            chunk_ids = data.get("chunk_ids", data.get("ids", []))
            embeddings = data.get("embeddings", [])
            metadatas = data.get("metadatas", [])
            self._vector_store.add_batch(chunk_ids, embeddings, metadatas)
            self._vector_store.save_index()
        elif strategy == "REPLACE":
            # Remove existing then add new
            old_chunk_ids = self._vector_store.get_chunk_ids_by_entry(operation.entry_id or "")
            if old_chunk_ids:
                self._vector_store.remove(old_chunk_ids)
            chunk_ids = data.get("chunk_ids", data.get("ids", []))
            embeddings = data.get("embeddings", [])
            metadatas = data.get("metadatas", [])
            self._vector_store.add_batch(chunk_ids, embeddings, metadatas)
            self._vector_store.save_index()
        elif strategy == "DELETE":
            if operation.entry_id:
                chunk_ids = self._vector_store.get_chunk_ids_by_entry(operation.entry_id)
                if chunk_ids:
                    self._vector_store.remove(chunk_ids)
                    self._vector_store.save_index()

    async def _execute_graph_operation(self, operation: UpdateOperation) -> None:
        """Execute a graph store operation."""
        if self._graph_store is None:
            raise RuntimeError("Graph store not configured")

        data = operation.data
        strategy = operation.strategy

        if strategy == "CREATE" or strategy == "APPEND":
            # Create entity or relation using Neo4jGraphStore API
            if "entity" in data:
                ent = data["entity"]
                await self._graph_store.add_entity(
                    kb_id=self.kb_id,
                    entity_id=operation.entity_id or ent.get("id", ""),
                    name=ent.get("name", ""),
                    entity_type=ent.get("entity_type", ""),
                    properties=ent.get("properties"),
                    entry_ids=ent.get("entry_ids"),
                    confidence=ent.get("confidence", 1.0),
                )
            elif "relation" in data:
                rel = data["relation"]
                await self._graph_store.add_relation(
                    kb_id=self.kb_id,
                    relation_id=operation.entity_id or rel.get("id", ""),
                    source_entity_id=rel.get("source_entity_id", ""),
                    target_entity_id=rel.get("target_entity_id", ""),
                    relation_type=rel.get("relation_type", ""),
                    properties=rel.get("properties"),
                    confidence=rel.get("confidence", 1.0),
                )
        elif strategy == "REPLACE":
            # MERGE (upsert) for entity
            if "entity" in data:
                ent = data["entity"]
                await self._graph_store.add_entity(
                    kb_id=self.kb_id,
                    entity_id=operation.entity_id or ent.get("id", ""),
                    name=ent.get("name", ""),
                    entity_type=ent.get("entity_type", ""),
                    properties=ent.get("properties"),
                    entry_ids=ent.get("entry_ids"),
                    confidence=ent.get("confidence", 1.0),
                )
        elif strategy == "DELETE":
            if operation.entity_id:
                await self._graph_store.delete_entity(operation.entity_id, self.kb_id)

    async def _execute_entry_operation(self, operation: UpdateOperation) -> None:
        """Execute a knowledge entry operation."""
        from kb_curator.services.db import get_session

        data = operation.data
        strategy = operation.strategy

        async for session in get_session():
            if strategy == "CREATE":
                from kb_curator.services.crud import create_entry
                await create_entry(session, **data)
            elif strategy == "REPLACE" or strategy == "APPEND":
                if operation.entry_id:
                    await update_entry(session, operation.entry_id, **data)
            elif strategy == "DELETE":
                if operation.entry_id:
                    from kb_curator.services.crud import delete_entry
                    await delete_entry(session, operation.entry_id)

    async def _rollback(self, result: UpdateResult) -> None:
        """Rollback completed operations in reverse order.

        Args:
            result: The result object to update.
        """
        log.warning("rollback_initiated", 
                   operations_to_rollback=len(self._completed_operations))

        for operation in reversed(self._completed_operations):
            try:
                # Create inverse operation
                rollback_op = self._create_rollback_operation(operation)
                await self._execute_operation(rollback_op)
                result.metadata[f"rolled_back_{operation.target}"] = True
            except Exception as e:
                log.error("rollback_operation_failed", 
                         operation=str(operation), error=str(e))
                result.errors.append(f"Rollback failed: {str(e)}")

        result.status = UpdateStatus.ROLLED_BACK

    def _create_rollback_operation(self, operation: UpdateOperation) -> UpdateOperation:
        """Create the inverse operation for rollback.

        Args:
            operation: The operation to create inverse for.

        Returns:
            The inverse operation.
        """
        from kb_curator.models.schemas import UpdateStrategy

        if operation.strategy == UpdateStrategy.CREATE:
            inverse_strategy = UpdateStrategy.DELETE
        elif operation.strategy == UpdateStrategy.DELETE:
            inverse_strategy = UpdateStrategy.CREATE
        else:
            inverse_strategy = UpdateStrategy.REPLACE

        return UpdateOperation(
            target=operation.target,
            strategy=inverse_strategy,
            entity_id=operation.entity_id,
            entry_id=operation.entry_id,
            data=operation.data.copy(),
        )


# Singleton instance factory
def create_updater(kb_id: str) -> KnowledgeUpdater:
    """Create a knowledge updater for a knowledge base.

    Injects the vector store and graph store for the given kb_id.

    Args:
        kb_id: Knowledge base ID.

    Returns:
        KnowledgeUpdater instance with stores injected.
    """
    from kb_curator.services.vector_store import get_vector_store

    vector_store = get_vector_store(kb_id)
    graph_store = None
    try:
        from kb_curator.services.graph_store import get_graph_store
        graph_store = get_graph_store()
    except Exception:
        pass  # Neo4j may not be available

    return KnowledgeUpdater(kb_id=kb_id, vector_store=vector_store, graph_store=graph_store)
