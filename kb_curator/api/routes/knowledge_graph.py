"""Knowledge graph query API routes."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import KGEntityCreate, KGEntityRead, KGRelationCreate, KGRelationRead

log = get_logger(__name__)
router = APIRouter(prefix="/knowledge-bases/{kb_id}/graph", tags=["Knowledge Graph"])


def _parse_properties(props: dict | str | None) -> dict:
    """Deserialize properties from Neo4j (may be stored as JSON string)."""
    if props is None:
        return {}
    if isinstance(props, str):
        try:
            return json.loads(props)
        except (json.JSONDecodeError, TypeError):
            return {}
    return props


def _to_datetime(value: object) -> datetime:
    """Convert Neo4j datetime to Python datetime."""
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_native"):
        return value.to_native()  # type: ignore[union-attr]
    return datetime.utcnow()


# ============================================================
# Entity endpoints
# ============================================================


@router.get("/entities", response_model=list[KGEntityRead])
async def list_entities(
    kb_id: str,
    entity_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[KGEntityRead]:
    """List entities in the knowledge graph for a knowledge base."""
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        query = "MATCH (e:Entity {kb_id: $kb_id})"
        params: dict = {"kb_id": kb_id}
        if entity_type:
            query += " WHERE e.entity_type = $entity_type"
            params["entity_type"] = entity_type
        query += " RETURN e.id AS eid, e.kb_id AS ekbid, e.name AS ename, e.entity_type AS etype, e.properties AS eprops, e.entry_ids AS eentry_ids, e.confidence AS econf, e.updated_at AS eupd, COUNT { (e)--(:Entity) } AS neighbor_count SKIP $skip LIMIT $limit"
        params["skip"] = offset
        params["limit"] = limit

        results = await store.execute_query(query, params)
        entities = []
        for r in results:
            props = _parse_properties(r.get("eprops"))
            props["_neighbor_count"] = r.get("neighbor_count", 0)
            entities.append(KGEntityRead(
                id=r.get("eid", ""),
                kb_id=r.get("ekbid", kb_id),
                name=r.get("ename", ""),
                entity_type=r.get("etype", ""),
                properties=props,
                entry_ids=r.get("eentry_ids", []),
                confidence=r.get("econf", 1.0),
                created_at=_to_datetime(r.get("eupd")),
            ))
        return entities
    except Exception as e:
        log.error("list_entities_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/entities/{entity_id}", response_model=KGEntityRead)
async def get_entity(
    kb_id: str,
    entity_id: str,
) -> KGEntityRead:
    """Get a specific entity from the knowledge graph."""
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        entity = await store.get_entity(entity_id, kb_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
        return KGEntityRead(
            id=entity.get("id", ""),
            kb_id=entity.get("kb_id", kb_id),
            name=entity.get("name", ""),
            entity_type=entity.get("entity_type", ""),
            properties=_parse_properties(entity.get("properties")),
            entry_ids=entity.get("entry_ids", []),
            confidence=entity.get("confidence", 1.0),
            created_at=_to_datetime(entity.get("updated_at")),
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("get_entity_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/entities", response_model=KGEntityRead, status_code=status.HTTP_201_CREATED)
async def create_entity(
    kb_id: str,
    body: KGEntityCreate,
) -> KGEntityRead:
    """Create or merge an entity in the knowledge graph."""
    if body.kb_id != kb_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="kb_id mismatch",
        )
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        entity_id = uuid4().hex
        await store.add_entity(
            kb_id=kb_id,
            entity_id=entity_id,
            name=body.name,
            entity_type=body.entity_type,
            properties=body.properties,
            confidence=body.confidence,
        )
        return KGEntityRead(
            id=entity_id,
            kb_id=kb_id,
            name=body.name,
            entity_type=body.entity_type,
            properties=body.properties,
            entry_ids=[],
            confidence=body.confidence,
            created_at=datetime.utcnow(),
        )
    except Exception as e:
        log.error("create_entity_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/entities/{entity_id}/neighbors")
async def get_entity_neighbors(
    kb_id: str,
    entity_id: str,
) -> dict:
    """Get neighboring entities and relations for a given entity."""
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        neighbors = await store.get_entity_neighbors(entity_id, kb_id)
        return {"entity_id": entity_id, "neighbors": neighbors}
    except Exception as e:
        log.error("get_neighbors_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/entities/{entity_id}", status_code=status.HTTP_200_OK)
async def delete_entity(
    kb_id: str,
    entity_id: str,
) -> dict:
    """Delete an entity and its relations from the knowledge graph."""
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        await store.delete_entity(entity_id, kb_id)
        return {"status": "deleted", "entity_id": entity_id}
    except Exception as e:
        log.error("delete_entity_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================
# Relation endpoints
# ============================================================


@router.get("/relations", response_model=list[KGRelationRead])
async def list_relations(
    kb_id: str,
    relation_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[KGRelationRead]:
    """List relations in the knowledge graph for a knowledge base."""
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        query = """
        MATCH (a:Entity {kb_id: $kb_id})-[r:RELATES]->(b:Entity {kb_id: $kb_id})
        """
        params: dict = {"kb_id": kb_id}
        if relation_type:
            query += " WHERE r.relation_type = $relation_type"
            params["relation_type"] = relation_type
        query += """ RETURN a.id AS source_id, b.id AS target_id,
                     r.id AS rel_id, r.relation_type AS rel_type,
                     r.properties AS rel_props, r.confidence AS rel_confidence,
                     r.updated_at AS rel_updated_at
                     SKIP $skip LIMIT $limit"""
        params["skip"] = offset
        params["limit"] = limit

        results = await store.execute_query(query, params)
        relations = []
        for r in results:
            relations.append(KGRelationRead(
                id=r.get("rel_id", ""),
                kb_id=kb_id,
                source_entity_id=r.get("source_id", ""),
                target_entity_id=r.get("target_id", ""),
                relation_type=r.get("rel_type", ""),
                properties=_parse_properties(r.get("rel_props")),
                confidence=r.get("rel_confidence", 1.0),
                created_at=_to_datetime(r.get("rel_updated_at")),
            ))
        return relations
    except Exception as e:
        log.error("list_relations_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/relations", response_model=KGRelationRead, status_code=status.HTTP_201_CREATED)
async def create_relation(
    kb_id: str,
    body: KGRelationCreate,
) -> KGRelationRead:
    """Create a relation between two entities in the knowledge graph."""
    if body.kb_id != kb_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="kb_id mismatch",
        )
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        relation_id = uuid4().hex
        await store.add_relation(
            kb_id=kb_id,
            relation_id=relation_id,
            source_entity_id=body.source_entity_id,
            target_entity_id=body.target_entity_id,
            relation_type=body.relation_type,
            properties=body.properties,
            confidence=body.confidence,
        )
        return KGRelationRead(
            id=relation_id,
            kb_id=kb_id,
            source_entity_id=body.source_entity_id,
            target_entity_id=body.target_entity_id,
            relation_type=body.relation_type,
            properties=body.properties,
            confidence=body.confidence,
            created_at=datetime.utcnow(),
        )
    except Exception as e:
        log.error("create_relation_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/relations/{relation_id}", status_code=status.HTTP_200_OK)
async def delete_relation(
    kb_id: str,
    relation_id: str,
) -> dict:
    """Delete a specific relation from the knowledge graph."""
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        await store.delete_relation(relation_id)
        return {"status": "deleted", "relation_id": relation_id}
    except Exception as e:
        log.error("delete_relation_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================
# Graph statistics
# ============================================================


@router.get("/stats")
async def get_graph_stats(
    kb_id: str,
) -> dict:
    """Get knowledge graph statistics for a knowledge base."""
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        entity_count = await store.count_entities(kb_id)
        relation_count = await store.count_relations(kb_id)
        orphans = await store.find_orphan_entities(kb_id)
        return {
            "kb_id": kb_id,
            "entity_count": entity_count,
            "relation_count": relation_count,
            "orphan_entity_count": len(orphans),
        }
    except Exception as e:
        log.error("get_stats_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
