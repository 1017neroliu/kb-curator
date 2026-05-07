"""Neo4j graph store service."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from kb_curator.core.config import get_settings
from kb_curator.core.logging import get_logger

if TYPE_CHECKING:
    from neo4j import AsyncDriver

log = get_logger(__name__)

_driver: AsyncDriver | None = None


def get_graph_store() -> Neo4jGraphStore:
    """Get or create the singleton graph store instance."""
    global _driver
    settings = get_settings()
    gs = settings.graph_store
    if _driver is None:
        from neo4j import AsyncGraphDatabase

        _driver = AsyncGraphDatabase.driver(
            gs.uri,
            auth=(gs.user, gs.password),
            max_connection_pool_size=gs.max_connection_pool_size,
            connection_acquisition_timeout=gs.connection_acquisition_timeout,
            max_transaction_retry_time=gs.max_transaction_retry_time,
        )
    return Neo4jGraphStore(_driver, database=gs.database)


class Neo4jGraphStore:
    """Neo4j knowledge graph store implementation."""

    def __init__(self, driver: AsyncDriver, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    async def verify_connection(self) -> bool:
        """Verify the Neo4j connection is working."""
        async with self._driver.session(database=self._database) as session:
            result = await session.run("RETURN 1 AS test")
            record = await result.single()
            return record is not None

    async def close(self) -> None:
        """Close the Neo4j driver connection."""
        await self._driver.close()

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute a Cypher query and return results as list of dicts."""
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, params or {})
            records = await result.data()
            return records

    async def execute_write(self, query: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute a write Cypher query within a transaction.

        Use this for all mutation operations to ensure transactional safety.
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.execute_write(
                self._run_tx, query, params or {}
            )
            return result

    @staticmethod
    async def _run_tx(tx: Any, query: str, params: dict[str, Any]) -> list[dict]:
        """Run a query within a transaction."""
        result = await tx.run(query, params)
        records = await result.data()
        return records

    async def add_entity(self, kb_id: str, entity_id: str, name: str,
                         entity_type: str, properties: dict | None = None,
                         entry_ids: list[str] | None = None,
                         confidence: float = 1.0) -> None:
        """Add or merge an entity node in the knowledge graph."""
        query = """
        MERGE (e:Entity {id: $entity_id, kb_id: $kb_id})
        SET e.name = $name,
            e.entity_type = $entity_type,
            e.properties = $properties,
            e.entry_ids = $entry_ids,
            e.confidence = $confidence,
            e.updated_at = datetime()
        """
        await self.execute_write(query, {
            "entity_id": entity_id,
            "kb_id": kb_id,
            "name": name,
            "entity_type": entity_type,
            "properties": json.dumps(properties or {}, ensure_ascii=False),
            "entry_ids": entry_ids or [],
            "confidence": confidence,
        })

    async def add_relation(self, kb_id: str, relation_id: str,
                           source_entity_id: str, target_entity_id: str,
                           relation_type: str, properties: dict | None = None,
                           confidence: float = 1.0) -> None:
        """Add a relation edge between two entities."""
        query = """
        MATCH (a:Entity {id: $source_id, kb_id: $kb_id})
        MATCH (b:Entity {id: $target_id, kb_id: $kb_id})
        MERGE (a)-[r:RELATES {id: $relation_id}]->(b)
        SET r.relation_type = $relation_type,
            r.properties = $properties,
            r.confidence = $confidence,
            r.updated_at = datetime()
        """
        await self.execute_write(query, {
            "relation_id": relation_id,
            "kb_id": kb_id,
            "source_id": source_entity_id,
            "target_id": target_entity_id,
            "relation_type": relation_type,
            "properties": json.dumps(properties or {}, ensure_ascii=False),
            "confidence": confidence,
        })

    async def get_entity(self, entity_id: str, kb_id: str) -> dict | None:
        """Get an entity by ID within a knowledge base."""
        query = "MATCH (e:Entity {id: $entity_id, kb_id: $kb_id}) RETURN e"
        results = await self.execute_query(query, {"entity_id": entity_id, "kb_id": kb_id})
        if results:
            return results[0].get("e")
        return None

    async def find_entity_by_name(self, name: str, entity_type: str,
                                  kb_id: str) -> dict | None:
        """Find an entity by name and type within a knowledge base."""
        query = """
        MATCH (e:Entity {name: $name, entity_type: $entity_type, kb_id: $kb_id})
        RETURN e LIMIT 1
        """
        results = await self.execute_query(query, {
            "name": name,
            "entity_type": entity_type,
            "kb_id": kb_id,
        })
        if results:
            return results[0].get("e")
        return None

    async def get_entities_by_entry(self, entry_id: str, kb_id: str) -> list[dict]:
        """Get all entities associated with a knowledge entry."""
        query = """
        MATCH (e:Entity {kb_id: $kb_id})
        WHERE $entry_id IN e.entry_ids
        RETURN e
        """
        return await self.execute_query(query, {"entry_id": entry_id, "kb_id": kb_id})

    async def get_entity_neighbors(self, entity_id: str, kb_id: str) -> list[dict]:
        """Get neighboring entities and relations."""
        query = """
        MATCH (e:Entity {id: $entity_id, kb_id: $kb_id})-[r]-(n:Entity)
        RETURN n.id AS neighbor_id, n.name AS neighbor_name, n.entity_type AS neighbor_type,
               r.relation_type AS relation_type, r.confidence AS confidence
        """
        return await self.execute_query(query, {"entity_id": entity_id, "kb_id": kb_id})

    async def find_orphan_entities(self, kb_id: str) -> list[dict]:
        """Find entities with no relations."""
        query = """
        MATCH (e:Entity {kb_id: $kb_id})
        WHERE NOT (e)--()
        RETURN e
        """
        return await self.execute_query(query, {"kb_id": kb_id})

    async def update_entity_properties(self, entity_id: str, kb_id: str,
                                       properties: dict) -> None:
        """Update properties on an existing entity."""
        query = """
        MATCH (e:Entity {id: $entity_id, kb_id: $kb_id})
        SET e.properties = $properties,
            e.updated_at = datetime()
        """
        await self.execute_write(query, {
            "entity_id": entity_id,
            "kb_id": kb_id,
            "properties": json.dumps(properties, ensure_ascii=False),
        })

    async def delete_entity(self, entity_id: str, kb_id: str) -> None:
        """Delete an entity and its relations."""
        query = """
        MATCH (e:Entity {id: $entity_id, kb_id: $kb_id})
        DETACH DELETE e
        """
        await self.execute_write(query, {"entity_id": entity_id, "kb_id": kb_id})

    async def delete_relation(self, relation_id: str) -> None:
        """Delete a specific relation by its ID."""
        query = """
        MATCH ()-[r:RELATES {id: $relation_id}]->()
        DELETE r
        """
        await self.execute_write(query, {"relation_id": relation_id})

    async def count_entities(self, kb_id: str) -> int:
        """Count total entities in a knowledge base."""
        query = "MATCH (e:Entity {kb_id: $kb_id}) RETURN count(e) AS cnt"
        results = await self.execute_query(query, {"kb_id": kb_id})
        return results[0]["cnt"] if results else 0

    async def count_relations(self, kb_id: str) -> int:
        """Count total relations in a knowledge base."""
        query = """
        MATCH (:Entity {kb_id: $kb_id})-[r:RELATES]->(:Entity {kb_id: $kb_id})
        RETURN count(r) AS cnt
        """
        results = await self.execute_query(query, {"kb_id": kb_id})
        return results[0]["cnt"] if results else 0
