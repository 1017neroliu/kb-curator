"""Knowledge extraction pipeline.

Orchestrates the complete knowledge extraction pipeline:
1. Chunk text
2. Extract entities
3. Extract relations
4. Align with existing KG
5. Convert to KG models
6. Store results in vector store + graph store
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import (
    KGEntityCreate,
    KGRelationCreate,
    TextChunk,
)
from kb_curator.services.entity_extractor import (
    ExtractedEntity,
    get_entity_extractor,
)
from kb_curator.services.entity_aligner import (
    AlignmentResult,
    get_entity_aligner,
)
from kb_curator.services.relation_extractor import (
    ExtractedRelation,
    get_relation_extractor,
)
from kb_curator.services.chunker import Chunk, create_chunker
from kb_curator.services.embedding_service import get_embedding_service

log = get_logger(__name__)


@dataclass
class ExtractionResult:
    """Complete extraction result."""
    kb_id: str
    source_id: str
    text_chunks: list[TextChunk] = field(default_factory=list)
    entities: list[KGEntityCreate] = field(default_factory=list)
    relations: list[KGRelationCreate] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class KnowledgeExtractor:
    """Complete knowledge extraction pipeline."""
    
    def __init__(
        self,
        kb_id: str,
        source_id: str,
        chunking_strategy: str = "semantic",
        chunk_size: int = 1000,
        use_spacy: bool = False,
    ) -> None:
        """Initialize the extractor.
        
        Args:
            kb_id: Knowledge base ID.
            source_id: Data source ID.
            chunking_strategy: Chunking strategy (fixed/semantic/document).
            chunk_size: Target chunk size.
            use_spacy: Whether to use spaCy pre-annotation.
        """
        self.kb_id = kb_id
        self.source_id = source_id
        self.chunker = create_chunker(chunking_strategy, chunk_size=chunk_size)
        self.entity_extractor = get_entity_extractor()
        self.relation_extractor = get_relation_extractor()
        self.entity_aligner = get_entity_aligner()
        self.embedding_service = get_embedding_service()
        self.use_spacy = use_spacy
        
        if use_spacy:
            from kb_curator.services.spacy_annotator import get_spacy_annotator
            self.spacy_annotator = get_spacy_annotator()
        else:
            self.spacy_annotator = None
    
    async def extract(self, text: str) -> ExtractionResult:
        """Extract knowledge from text.
        
        Args:
            text: Input text to extract from.
            
        Returns:
            ExtractionResult with chunks, entities, and relations.
        """
        result = ExtractionResult(kb_id=self.kb_id, source_id=self.source_id)
        
        try:
            # Step 1: Chunk the text
            chunks = self.chunker.chunk(text)
            log.info("text_chunks", count=len(chunks))
            
            # Step 2: Extract entities and relations for each chunk
            all_entities: list[ExtractedEntity] = []
            all_relations: list[ExtractedRelation] = []
            
            for chunk in chunks:
                try:
                    # Optional spaCy pre-annotation
                    if self.spacy_annotator:
                        annotation = self.spacy_annotator.annotate(chunk.content)
                        if annotation:
                            chunk.metadata["spacy_entities"] = [
                                {"text": e.text, "type": e.label}
                                for e in annotation.entities
                            ]
                    
                    # Extract entities
                    entities = await self.entity_extractor.extract(chunk.content)
                    all_entities.extend(entities)
                    
                    # Extract relations with entities
                    if entities:
                        relations = await self.relation_extractor.extract(chunk.content, entities)
                        all_relations.extend(relations)
                    
                except Exception as e:
                    log.error("chunk_extraction_error", error=str(e))
                    result.errors.append(f"Chunk {chunk.chunk_index}: {str(e)}")
            
            log.info("entities_extracted", count=len(all_entities))
            log.info("relations_extracted", count=len(all_relations))
            
            # Step 3: Align entities with existing KG (placeholder - would need actual existing entities)
            # For now, create all entities as new
            aligned_entities: dict[str, KGEntityCreate] = {}
            for ent in all_entities:
                entity_id = f"ent_{uuid4().hex[:12]}"
                kg_entity = ent.to_kg_entity(self.kb_id, entity_id=entity_id)
                aligned_entities[ent.name.lower()] = kg_entity
                result.entities.append(kg_entity)
            
            # Step 4: Create TextChunks with embeddings
            for chunk in chunks:
                emb = await self.embedding_service.embed(chunk.content)
                text_chunk = TextChunk(
                    kb_id=self.kb_id,
                    entry_id=self.source_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    embedding=emb,
                    metadata=chunk.metadata,
                )
                result.text_chunks.append(text_chunk)
            
            # Step 5: Convert relations to KG relations
            entity_name_to_id = {e.name.lower(): getattr(e, 'id', None) for e in result.entities}
            for rel in all_relations:
                source_id = entity_name_to_id.get(rel.source_entity.lower())
                target_id = entity_name_to_id.get(rel.target_entity.lower())
                if source_id and target_id:
                    kg_rel = rel.to_kg_relation(self.kb_id, source_id, target_id)
                    result.relations.append(kg_rel)
            
            result.metadata = {
                "chunking_strategy": type(self.chunker).__name__,
                "total_chunks": len(chunks),
                "total_entities": len(all_entities),
                "total_relations": len(all_relations),
            }

        except Exception as e:
            log.error("extraction_pipeline_error", error=str(e))
            result.errors.append(str(e))

        return result

    async def extract_and_store(
        self,
        text: str,
        entry_id: str,
    ) -> ExtractionResult:
        """Extract knowledge from text and store results in vector store + graph store.

        This is a convenience method that runs the full extraction pipeline
        and then persists chunks to FAISS and entities/relations to Neo4j.

        Args:
            text: Input text to extract from.
            entry_id: The knowledge entry ID this content belongs to.

        Returns:
            ExtractionResult with chunks, entities, and relations.
        """
        result = await self.extract(text)

        if result.errors and not result.text_chunks:
            return result

        try:
            # Store text chunks in FAISS
            from kb_curator.services.vector_store import get_vector_store

            vector_store = get_vector_store(self.kb_id)
            chunk_ids = []
            embeddings = []
            metadatas = []
            for chunk in result.text_chunks:
                if chunk.embedding is not None:
                    chunk_ids.append(chunk.id)
                    embeddings.append(chunk.embedding)
                    metadatas.append({
                        "kb_id": self.kb_id,
                        "entry_id": entry_id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                    })

            if chunk_ids:
                vector_store.add_batch(chunk_ids, embeddings, metadatas)
                vector_store.save_index()
                log.info("chunks_stored_in_faiss", count=len(chunk_ids))

            # Store entities and relations in Neo4j
            try:
                from kb_curator.services.graph_store import get_graph_store

                graph_store = get_graph_store()

                for entity in result.entities:
                    entity_id = entity.id or f"ent_{uuid4().hex[:12]}"
                    await graph_store.add_entity(
                        kb_id=self.kb_id,
                        entity_id=entity_id,
                        name=entity.name,
                        entity_type=entity.entity_type,
                        properties=entity.properties,
                        entry_ids=[entry_id],
                        confidence=entity.confidence,
                    )

                for relation in result.relations:
                    rel_id = f"rel_{uuid4().hex[:12]}"
                    await graph_store.add_relation(
                        kb_id=self.kb_id,
                        relation_id=rel_id,
                        source_entity_id=relation.source_entity_id,
                        target_entity_id=relation.target_entity_id,
                        relation_type=relation.relation_type,
                        properties=relation.properties,
                        confidence=relation.confidence,
                    )

                log.info(
                    "kg_stored_in_neo4j",
                    entities=len(result.entities),
                    relations=len(result.relations),
                )
            except Exception as e:
                log.warning("graph_store_unavailable", error=str(e))
                result.errors.append(f"Graph store error: {str(e)}")

            result.metadata["stored"] = True

        except Exception as e:
            log.error("store_failed", error=str(e))
            result.errors.append(f"Storage error: {str(e)}")

        return result


# Factory function
def create_extractor(
    kb_id: str,
    source_id: str,
    **kwargs,
) -> KnowledgeExtractor:
    return KnowledgeExtractor(kb_id, source_id, **kwargs)
