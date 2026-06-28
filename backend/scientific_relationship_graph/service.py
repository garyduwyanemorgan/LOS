"""
Scientific Relationship Graph service using Neo4j.

The SRG is the reasoning network of the Lagoons Operating System.
It stores and maintains scientific cause-effect relationships,
enabling the Decision Engine to explain WHY conditions occur.

Node labels: ScientificConcept
Relationship types: INFLUENCES | INHIBITS | TRIGGERS | CORRELATES_WITH

Properties on relationships:
  confidence      float   0.0-1.0
  feedback_type   str     positive | negative
  mechanism       str     scientific description
  evidence        list    supporting sources
  lag_days        float   typical time delay
  observation_count int   how often observed
  loop            str     owning scientific loop
  last_updated    str     ISO timestamp
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from backend.scientific_relationship_graph.models import (
    CausalPathway,
    Hypothesis,
    ScientificRelationship,
)

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)

try:
    from neo4j import AsyncGraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logger.warning(
        "neo4j driver not installed. ScientificRelationshipGraph will operate in degraded mode. "
        "Install with: pip install neo4j"
    )


class ScientificRelationshipGraph:
    """
    Neo4j-backed Scientific Relationship Graph.

    When Neo4j is unavailable, falls back to an in-memory store that
    preserves core functionality with reduced persistence.
    """

    def __init__(self, uri: str, username: str, password: str) -> None:
        self._uri = uri
        self._username = username
        self._password = password
        self._driver: Any = None
        self._fallback_store: dict[str, Any] = {}  # in-memory fallback
        self._connected = False

    # ──────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish Neo4j connection. Falls back gracefully if unavailable."""
        if not NEO4J_AVAILABLE:
            logger.warning("SRG running in degraded mode (neo4j not installed)")
            self._connected = False
            return
        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=(self._username, self._password),
                max_connection_pool_size=20,
                connection_timeout=10,
            )
            await self._driver.verify_connectivity()
            self._connected = True
            logger.info("SRG connected to Neo4j: %s", self._uri)
            await self._create_constraints()
        except Exception as exc:
            logger.error(
                "SRG could not connect to Neo4j: %s — running in degraded mode", exc
            )
            self._connected = False

    async def disconnect(self) -> None:
        """Close Neo4j driver."""
        if self._driver:
            await self._driver.close()
        logger.info("SRG disconnected from Neo4j")

    async def _create_constraints(self) -> None:
        """Ensure uniqueness constraints exist on node names."""
        async with self._driver.session() as session:
            await session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:ScientificConcept) "
                "REQUIRE n.name IS UNIQUE"
            )

    # ──────────────────────────────────────────────────────────────────────
    # Write Operations
    # ──────────────────────────────────────────────────────────────────────

    async def create_relationship(
        self,
        cause: str,
        effect: str,
        loop: str,
        confidence: float,
        evidence: list[str],
        feedback_type: str = "positive",
        mechanism: str | None = None,
        lag_days: float | None = None,
        relationship_type: str = "INFLUENCES",
    ) -> str:
        """
        Create or update a scientific relationship in the SRG.

        Uses MERGE to avoid duplicates — updates confidence and evidence
        if the relationship already exists.

        Returns: relationship ID (or key for fallback mode).
        """
        if self._connected:
            return await self._neo4j_create_relationship(
                cause=cause,
                effect=effect,
                loop=loop,
                confidence=confidence,
                evidence=evidence,
                feedback_type=feedback_type,
                mechanism=mechanism,
                lag_days=lag_days,
                relationship_type=relationship_type,
            )
        else:
            key = f"{cause}→{effect}"
            self._fallback_store[key] = {
                "cause": cause,
                "effect": effect,
                "loop": loop,
                "confidence": confidence,
                "evidence": evidence,
                "feedback_type": feedback_type,
                "mechanism": mechanism,
                "relationship_type": relationship_type,
            }
            return key

    async def _neo4j_create_relationship(self, **kwargs: Any) -> str:
        """Neo4j implementation of create_relationship."""
        cause = kwargs["cause"]
        effect = kwargs["effect"]
        loop = kwargs["loop"]
        confidence = kwargs["confidence"]
        evidence = kwargs["evidence"]
        feedback_type = kwargs.get("feedback_type", "positive")
        mechanism = kwargs.get("mechanism", "")
        lag_days = kwargs.get("lag_days")
        relationship_type = kwargs.get("relationship_type", "INFLUENCES")

        cypher = f"""
        MERGE (c:ScientificConcept {{name: $cause}})
        ON CREATE SET c.loop = $loop, c.created_at = $now
        MERGE (e:ScientificConcept {{name: $effect}})
        ON CREATE SET e.loop = $loop, e.created_at = $now
        MERGE (c)-[r:{relationship_type}]->(e)
        ON CREATE SET
            r.confidence = $confidence,
            r.evidence = $evidence,
            r.feedback_type = $feedback_type,
            r.mechanism = $mechanism,
            r.lag_days = $lag_days,
            r.loop = $loop,
            r.observation_count = 1,
            r.created_at = $now,
            r.last_updated = $now
        ON MATCH SET
            r.confidence = $confidence,
            r.evidence = $evidence,
            r.feedback_type = $feedback_type,
            r.mechanism = CASE WHEN $mechanism IS NOT NULL THEN $mechanism ELSE r.mechanism END,
            r.observation_count = r.observation_count + 1,
            r.last_updated = $now
        RETURN elementId(r) AS rel_id
        """
        async with self._driver.session() as session:
            result = await session.run(
                cypher,
                cause=cause,
                effect=effect,
                loop=loop,
                confidence=confidence,
                evidence=evidence,
                feedback_type=feedback_type,
                mechanism=mechanism or "",
                lag_days=lag_days,
                now=datetime.now(tz=UTC).isoformat(),
            )
            record = await result.single()
            return record["rel_id"] if record else f"{cause}→{effect}"

    async def update_confidence(
        self,
        cause: str,
        effect: str,
        new_confidence: float,
        outcome_description: str,
        relationship_type: str = "INFLUENCES",
    ) -> None:
        """Update relationship confidence based on intervention outcome."""
        if not self._connected:
            key = f"{cause}→{effect}"
            if key in self._fallback_store:
                self._fallback_store[key]["confidence"] = new_confidence
            return

        cypher = f"""
        MATCH (c:ScientificConcept {{name: $cause}})-[r:{relationship_type}]->(e:ScientificConcept {{name: $effect}})
        SET r.confidence = $confidence,
            r.last_updated = $now,
            r.observation_count = r.observation_count + 1
        """
        async with self._driver.session() as session:
            await session.run(
                cypher,
                cause=cause,
                effect=effect,
                confidence=new_confidence,
                now=datetime.now(tz=UTC).isoformat(),
            )
        logger.debug("SRG confidence updated: %s→%s = %.2f", cause, effect, new_confidence)

    # ──────────────────────────────────────────────────────────────────────
    # Read Operations
    # ──────────────────────────────────────────────────────────────────────

    async def find_causal_pathways(
        self,
        effect_node: str,
        max_depth: int = 5,
        min_confidence: float = 0.3,
    ) -> list[CausalPathway]:
        """
        Find all causal pathways leading to a given effect node.

        Returns pathways ordered by overall confidence (highest first).
        """
        if not self._connected:
            return self._fallback_find_pathways(effect_node, min_confidence)

        cypher = """
        MATCH path = (cause:ScientificConcept)-[:INFLUENCES|TRIGGERS*1..{max_depth}]->(effect:ScientificConcept {{name: $effect}})
        WHERE ALL(r IN relationships(path) WHERE r.confidence >= $min_confidence)
        WITH path,
             reduce(conf = 1.0, r IN relationships(path) | conf * r.confidence) AS path_confidence
        ORDER BY path_confidence DESC
        LIMIT 10
        RETURN
            nodes(path)[0].name AS root_cause,
            [r IN relationships(path) | {{
                cause: startNode(r).name,
                effect: endNode(r).name,
                confidence: r.confidence,
                mechanism: r.mechanism,
                evidence: r.evidence
            }}] AS steps,
            path_confidence,
            length(path) AS path_length
        """.replace("{max_depth}", str(max_depth))

        pathways: list[CausalPathway] = []
        async with self._driver.session() as session:
            result = await session.run(
                cypher, effect=effect_node, min_confidence=min_confidence
            )
            async for record in result:
                relationships = [
                    ScientificRelationship(
                        id=f"{step['cause']}→{step['effect']}",
                        cause=step["cause"],
                        effect=step["effect"],
                        relationship_type="INFLUENCES",
                        confidence=step["confidence"],
                        evidence=step["evidence"] or [],
                        mechanism=step.get("mechanism"),
                    )
                    for step in record["steps"]
                ]
                pathways.append(
                    CausalPathway(
                        root_cause=record["root_cause"],
                        effect=effect_node,
                        relationships=relationships,
                        overall_confidence=record["path_confidence"],
                        total_length=record["path_length"],
                    )
                )
        return pathways

    def _fallback_find_pathways(
        self, effect_node: str, min_confidence: float
    ) -> list[CausalPathway]:
        """In-memory fallback for causal pathway search."""
        pathways: list[CausalPathway] = []
        for key, rel_data in self._fallback_store.items():
            if rel_data.get("effect") == effect_node and rel_data.get("confidence", 0) >= min_confidence:
                rel = ScientificRelationship(
                    id=key,
                    cause=rel_data["cause"],
                    effect=rel_data["effect"],
                    relationship_type=rel_data.get("relationship_type", "INFLUENCES"),
                    confidence=rel_data["confidence"],
                    evidence=rel_data.get("evidence", []),
                )
                pathways.append(
                    CausalPathway(
                        root_cause=rel_data["cause"],
                        effect=effect_node,
                        relationships=[rel],
                        overall_confidence=rel_data["confidence"],
                        total_length=1,
                    )
                )
        return sorted(pathways, key=lambda p: p.overall_confidence, reverse=True)

    async def generate_hypotheses(
        self,
        condition: str,
        lagoon_id: UUID,
        top_n: int = 5,
    ) -> list[Hypothesis]:
        """
        Generate ranked hypotheses explaining an observed condition.

        Searches the SRG for all causal pathways leading to the condition,
        ranks them by confidence, and returns them as hypotheses.
        """
        pathways = await self.find_causal_pathways(condition, max_depth=4, min_confidence=0.2)

        hypotheses: list[Hypothesis] = []
        for rank, pathway in enumerate(pathways[:top_n], start=1):
            h = Hypothesis(
                id=f"{condition}:{pathway.root_cause}:{rank}",
                condition_observed=condition,
                candidate_cause=pathway.root_cause,
                supporting_pathways=[pathway],
                confidence=pathway.overall_confidence,
                rank=rank,
                narrative=(
                    f"{pathway.root_cause} → {' → '.join(r.effect for r in pathway.relationships)}"
                    f" (confidence: {pathway.overall_confidence:.0%})"
                ),
            )
            hypotheses.append(h)
        return hypotheses

    async def get_relationships_for_node(self, node_name: str) -> list[ScientificRelationship]:
        """Return all relationships where the node is cause or effect."""
        if not self._connected:
            return [
                ScientificRelationship(
                    id=key,
                    cause=v["cause"],
                    effect=v["effect"],
                    relationship_type=v.get("relationship_type", "INFLUENCES"),
                    confidence=v["confidence"],
                    evidence=v.get("evidence", []),
                )
                for key, v in self._fallback_store.items()
                if v["cause"] == node_name or v["effect"] == node_name
            ]

        cypher = """
        MATCH (n:ScientificConcept {name: $name})-[r]->(m:ScientificConcept)
        RETURN n.name AS cause, m.name AS effect, type(r) AS rel_type,
               r.confidence AS confidence, r.evidence AS evidence,
               r.mechanism AS mechanism, elementId(r) AS rel_id
        UNION
        MATCH (m:ScientificConcept)-[r]->(n:ScientificConcept {name: $name})
        RETURN m.name AS cause, n.name AS effect, type(r) AS rel_type,
               r.confidence AS confidence, r.evidence AS evidence,
               r.mechanism AS mechanism, elementId(r) AS rel_id
        """
        relationships: list[ScientificRelationship] = []
        async with self._driver.session() as session:
            result = await session.run(cypher, name=node_name)
            async for record in result:
                relationships.append(
                    ScientificRelationship(
                        id=record["rel_id"],
                        cause=record["cause"],
                        effect=record["effect"],
                        relationship_type=record["rel_type"],
                        confidence=record["confidence"],
                        evidence=record.get("evidence") or [],
                        mechanism=record.get("mechanism"),
                    )
                )
        return relationships

    async def update_from_intervention_outcome(
        self,
        cause_action: str,
        effect_observed: str,
        success: bool,
        delta_confidence: float = 0.05,
    ) -> None:
        """
        Update relationship confidence based on a measured intervention outcome.

        Successful outcome increases confidence; failure decreases it.
        Confidence is bounded to [0.05, 0.99].
        """
        if not self._connected:
            key = f"{cause_action}→{effect_observed}"
            if key in self._fallback_store:
                current = self._fallback_store[key]["confidence"]
                if success:
                    self._fallback_store[key]["confidence"] = min(0.99, current + delta_confidence)
                else:
                    self._fallback_store[key]["confidence"] = max(0.05, current - delta_confidence)
            return

        direction = delta_confidence if success else -delta_confidence
        cypher = """
        MATCH (c:ScientificConcept {name: $cause})-[r]->(e:ScientificConcept {name: $effect})
        SET r.confidence = CASE
                WHEN r.confidence + $delta > 0.99 THEN 0.99
                WHEN r.confidence + $delta < 0.05 THEN 0.05
                ELSE r.confidence + $delta
            END,
            r.observation_count = r.observation_count + 1,
            r.last_updated = $now
        """
        async with self._driver.session() as session:
            await session.run(
                cypher,
                cause=cause_action,
                effect=effect_observed,
                delta=direction,
                now=datetime.now(tz=UTC).isoformat(),
            )

    # ──────────────────────────────────────────────────────────────────────
    # Health
    # ──────────────────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """Return SRG health status."""
        if not self._connected:
            return {
                "status": "degraded",
                "connected": False,
                "mode": "in-memory fallback",
                "relationship_count": len(self._fallback_store),
            }
        try:
            async with self._driver.session() as session:
                result = await session.run(
                    "MATCH ()-[r]->() RETURN count(r) AS rel_count, count(distinct startNode(r)) AS node_count"
                )
                record = await result.single()
                return {
                    "status": "healthy",
                    "connected": True,
                    "relationship_count": record["rel_count"] if record else 0,
                    "node_count": record["node_count"] if record else 0,
                }
        except Exception as exc:
            return {"status": "unhealthy", "connected": False, "error": str(exc)}
