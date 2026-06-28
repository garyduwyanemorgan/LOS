#!/usr/bin/env python3
"""Seed the Scientific Relationship Graph with baseline lagoon science relationships.

Run once after Neo4j is initialised:
    python deployment/scripts/seed_srg.py

Or via Docker:
    docker compose exec backend python deployment/scripts/seed_srg.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    from backend.core.config.settings import settings
    from backend.scientific_relationship_graph.service import ScientificRelationshipGraph
    from backend.scientific_relationship_graph.seed_data import seed_srg

    logger.info("Connecting to Neo4j at %s...", settings.NEO4J_URI)
    srg = ScientificRelationshipGraph(
        uri=settings.NEO4J_URI,
        username=settings.NEO4J_USERNAME,
        password=settings.NEO4J_PASSWORD,
    )

    await srg.connect()

    health = await srg.health()
    if health.get("status") == "degraded":
        logger.error(
            "SRG is in degraded mode (Neo4j not connected). "
            "Cannot seed — ensure Neo4j is running."
        )
        sys.exit(1)

    logger.info("Connected. Beginning SRG seed...")
    await seed_srg(srg)

    # Verify
    final_health = await srg.health()
    logger.info("SRG after seeding: %s", final_health)

    await srg.disconnect()
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
