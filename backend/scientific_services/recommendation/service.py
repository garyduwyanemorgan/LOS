"""
Recommendation service — generates prioritised management recommendations
from integrated scientific state.

Reads from shared memory (hydro, chem, eco, infra, predict) and applies
rule-based triage to generate actionable recommendations with rationale.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from ..base import ScientificService, ServiceStatus
from .models import (
    ActionCategory,
    Recommendation,
    RecommendationPriority,
    RecommendationSet,
)

logger = logging.getLogger(__name__)


class RecommendationService(ScientificService):
    """
    Continuous recommendation generation service.

    Loop interval: configurable (default 900 s / 15 min).
    """

    service_name = "recommendation"
    loop_name = "recommendation_loop"

    def __init__(
        self,
        shared_memory: Any,
        event_bus: Any,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._shared_memory = shared_memory
        self._event_bus = event_bus
        self._config = config or {}
        self._interval_seconds: float = float(self._config.get("interval_seconds", 900))
        self._running = False
        self._task: asyncio.Task | None = None
        self._known_lagoons: set[UUID] = set()
        self._status = ServiceStatus.INITIALIZING

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("RecommendationService starting (interval=%.0fs)", self._interval_seconds)
        self._running = True
        self._status = ServiceStatus.RUNNING
        self._task = asyncio.create_task(self._run_loop(), name="rec_loop")
        if self._event_bus is not None:
            await self._event_bus.subscribe("scientific.ecological.state", self.process_event)
            await self._event_bus.subscribe("scientific.infrastructure.state", self.process_event)

    async def stop(self) -> None:
        logger.info("RecommendationService stopping")
        self._running = False
        self._status = ServiceStatus.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def process_event(self, event: dict[str, Any]) -> None:
        try:
            lagoon_id = UUID(str(event["lagoon_id"]))
            self._known_lagoons.add(lagoon_id)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    async def _load_state(self, lagoon_id: UUID) -> dict[str, Any]:
        state: dict[str, Any] = {}
        if self._shared_memory is None:
            return state
        for prefix in ("hydro", "chem", "eco", "infra", "predict"):
            try:
                s = await self._shared_memory.get(f"{prefix}:{lagoon_id}")
                if s:
                    state.update(s)
            except Exception:
                pass
        return state

    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        rec_set = await self._generate_recommendations(lagoon_id)
        return rec_set.to_dict()

    async def _generate_recommendations(self, lagoon_id: UUID) -> RecommendationSet:
        state = await self._load_state(lagoon_id)
        now = datetime.now(tz=UTC)
        candidates: list[Recommendation] = []

        do_mg_l: float | None = state.get("do_mg_l")
        bloom_prob: float = float(state.get("bloom_probability") or 0.0)
        orp_mv: float | None = state.get("orp_mv")
        rt_days: float | None = state.get("residence_time_days")
        infra_health: float = float(state.get("infrastructure_health_score") or 1.0)
        active_aer: float = float(state.get("active_aeration_kg_hr") or 0.0)
        total_aer: float = float(state.get("total_aeration_capacity_kg_hr") or 1.0)
        overdue_maintenance: int = int(state.get("overdue_maintenance_count") or 0)
        succession: str = str(state.get("succession_stage") or "stable_diatoms")
        trophic: str = str(state.get("trophic_state") or "unknown")
        recovery: str = str(state.get("recovery_potential") or "medium")
        trajectory: str = str(state.get("overall_trajectory") or "stable")
        bloom_7d: float = float(state.get("bloom_probability_7d") or bloom_prob)
        fish_risk: str = str(state.get("fish_kill_risk") or "low")

        # ------------------------------------------------------------------
        # Rule 1: Critical DO — emergency aeration
        # ------------------------------------------------------------------
        if do_mg_l is not None and do_mg_l < 2.0:
            priority = (
                RecommendationPriority.CRITICAL
                if do_mg_l < 1.0
                else RecommendationPriority.HIGH
            )
            candidates.append(Recommendation(
                recommendation_id=str(uuid4()),
                lagoon_id=lagoon_id,
                generated_at=now,
                priority=priority,
                category=ActionCategory.AERATION,
                title="Emergency aeration — critically low dissolved oxygen",
                description=(
                    f"DO is {do_mg_l:.1f} mg/L — below critical threshold. "
                    "Deploy all available aerators at maximum capacity immediately. "
                    "Consider emergency portable aeration if fixed capacity is insufficient."
                ),
                rationale=(
                    f"DO < 2 mg/L causes fish kill within hours. "
                    f"Current succession stage: {succession}. "
                    f"Fish kill risk: {fish_risk}."
                ),
                expected_outcome="DO recovery to >4 mg/L within 4–8 hours.",
                estimated_cost_aed=None,
                estimated_duration_hours=8.0,
                confidence=0.95,
                evidence=[f"DO = {do_mg_l:.1f} mg/L", f"Fish kill risk = {fish_risk}"],
                kpis=["do_mg_l > 4.0", "do_saturation_pct > 50"],
            ))

        # ------------------------------------------------------------------
        # Rule 2: High bloom probability — pre-emptive circulation
        # ------------------------------------------------------------------
        if bloom_prob >= 0.6 or bloom_7d >= 0.65:
            candidates.append(Recommendation(
                recommendation_id=str(uuid4()),
                lagoon_id=lagoon_id,
                generated_at=now,
                priority=RecommendationPriority.HIGH if bloom_prob >= 0.75 else RecommendationPriority.MEDIUM,
                category=ActionCategory.CIRCULATION,
                title="Increase lagoon circulation to disrupt stratification",
                description=(
                    "High bloom probability detected. Increase pump circulation to reduce "
                    "thermal stratification and nutrient concentration in surface waters. "
                    "Target minimum 10–15% daily volume turnover."
                ),
                rationale=(
                    f"Bloom probability = {bloom_prob:.0%} (7-day forecast: {bloom_7d:.0%}). "
                    f"Trophic state: {trophic}. Succession stage: {succession}. "
                    "Destratification disrupts cyanobacteria light access."
                ),
                expected_outcome="Reduce bloom probability by 15–30% over 7 days.",
                estimated_cost_aed=500.0,
                estimated_duration_hours=168.0,
                confidence=0.75,
                evidence=[
                    f"Bloom probability = {bloom_prob:.2f}",
                    f"Succession = {succession}",
                ],
                kpis=["bloom_probability < 0.4", "succession_stage != active_bloom"],
            ))

        # ------------------------------------------------------------------
        # Rule 3: Aeration underperforming
        # ------------------------------------------------------------------
        aer_util = active_aer / max(total_aer, 0.001)
        if total_aer > 0 and aer_util < 0.5 and (do_mg_l is None or do_mg_l < 6.0):
            candidates.append(Recommendation(
                recommendation_id=str(uuid4()),
                lagoon_id=lagoon_id,
                generated_at=now,
                priority=RecommendationPriority.MEDIUM,
                category=ActionCategory.AERATION,
                title="Activate underutilised aeration capacity",
                description=(
                    f"Only {aer_util:.0%} of total aeration capacity is active. "
                    "Review aeration schedule and activate additional units, "
                    "particularly during peak biological oxygen demand (dusk to dawn)."
                ),
                rationale="Low aeration utilisation with suboptimal DO.",
                expected_outcome="Increase DO by 1–2 mg/L over 24–48 hours.",
                estimated_cost_aed=200.0,
                estimated_duration_hours=48.0,
                confidence=0.70,
                evidence=[f"Aeration utilisation = {aer_util:.0%}"],
                kpis=["active_aeration_kg_hr / total_aeration_capacity_kg_hr > 0.8"],
            ))

        # ------------------------------------------------------------------
        # Rule 4: Overdue maintenance
        # ------------------------------------------------------------------
        if overdue_maintenance > 0:
            priority = (
                RecommendationPriority.HIGH
                if overdue_maintenance > 3 or infra_health < 0.6
                else RecommendationPriority.MEDIUM
            )
            candidates.append(Recommendation(
                recommendation_id=str(uuid4()),
                lagoon_id=lagoon_id,
                generated_at=now,
                priority=priority,
                category=ActionCategory.MAINTENANCE,
                title=f"Complete {overdue_maintenance} overdue maintenance item(s)",
                description=(
                    f"{overdue_maintenance} equipment maintenance item(s) are overdue. "
                    "Schedule service during low-demand period to minimise DO impact. "
                    "Ensure standby equipment is operational before taking units offline."
                ),
                rationale=f"Infrastructure health score = {infra_health:.2f}.",
                expected_outcome="Restore full equipment capacity and prevent unplanned failure.",
                estimated_cost_aed=2000.0 * overdue_maintenance,
                estimated_duration_hours=6.0 * overdue_maintenance,
                confidence=0.90,
                evidence=[f"Overdue items = {overdue_maintenance}"],
                kpis=["overdue_maintenance_count == 0", "infrastructure_health_score > 0.9"],
            ))

        # ------------------------------------------------------------------
        # Rule 5: Long residence time + elevated nutrients → TSE management
        # ------------------------------------------------------------------
        if rt_days is not None and rt_days > 25 and trophic in ("eutrophic", "hypereutrophic"):
            candidates.append(Recommendation(
                recommendation_id=str(uuid4()),
                lagoon_id=lagoon_id,
                generated_at=now,
                priority=RecommendationPriority.MEDIUM,
                category=ActionCategory.TSE_MANAGEMENT,
                title="Review TSE inflow loading to reduce nutrient accumulation",
                description=(
                    f"Residence time is {rt_days:.0f} days and trophic state is {trophic}. "
                    "Review TSE input volume and quality. Consider diverting peak-nutrient TSE "
                    "flows, increasing tidal exchange, or adding constructed wetland pre-treatment."
                ),
                rationale="Long RT + high nutrients creates ideal bloom conditions.",
                expected_outcome="Reduce TP by 20–40% over 30 days.",
                estimated_cost_aed=5000.0,
                estimated_duration_hours=720.0,
                confidence=0.65,
                evidence=[f"RT = {rt_days:.0f} days", f"Trophic = {trophic}"],
                kpis=["residence_time_days < 20", "tp_mg_l < 0.05"],
            ))

        # ------------------------------------------------------------------
        # Rule 6: Strongly reducing conditions → sediment assessment
        # ------------------------------------------------------------------
        if orp_mv is not None and orp_mv < -150:
            candidates.append(Recommendation(
                recommendation_id=str(uuid4()),
                lagoon_id=lagoon_id,
                generated_at=now,
                priority=RecommendationPriority.MEDIUM,
                category=ActionCategory.DREDGING,
                title="Sediment assessment for internal phosphorus loading",
                description=(
                    f"ORP = {orp_mv:.0f} mV indicates strongly reducing sediments. "
                    "Commission sediment survey to quantify P pool and assess "
                    "dredging/capping options to address internal loading."
                ),
                rationale="Reducing sediments release iron-bound phosphorus, perpetuating blooms.",
                expected_outcome="Quantify internal loading contribution and identify mitigation.",
                estimated_cost_aed=15000.0,
                estimated_duration_hours=720.0,
                confidence=0.60,
                evidence=[f"ORP = {orp_mv:.0f} mV"],
                kpis=["orp_mv > -50", "internal_loading_risk in [low, medium]"],
            ))

        # ------------------------------------------------------------------
        # Rule 7: Monitoring recommendation (always present if bloom risk)
        # ------------------------------------------------------------------
        if bloom_prob >= 0.3:
            candidates.append(Recommendation(
                recommendation_id=str(uuid4()),
                lagoon_id=lagoon_id,
                generated_at=now,
                priority=RecommendationPriority.LOW,
                category=ActionCategory.MONITORING,
                title="Intensify monitoring — elevated bloom risk",
                description=(
                    "Increase water quality monitoring frequency to daily. "
                    "Add phycocyanin fluorometer readings for cyanobacteria early detection. "
                    "Notify stakeholders of elevated bloom risk."
                ),
                rationale=f"Bloom probability = {bloom_prob:.0%}.",
                expected_outcome="Early detection of bloom onset enabling rapid response.",
                estimated_cost_aed=300.0,
                estimated_duration_hours=720.0,
                confidence=0.80,
                evidence=[f"Bloom probability = {bloom_prob:.2f}"],
                kpis=["phycocyanin_rfu < 50", "succession_stage != active_bloom"],
            ))

        # ------------------------------------------------------------------
        # Rule 8: DO nothing baseline
        # ------------------------------------------------------------------
        candidates.append(Recommendation(
            recommendation_id=str(uuid4()),
            lagoon_id=lagoon_id,
            generated_at=now,
            priority=RecommendationPriority.LOW,
            category=ActionCategory.DO_NOTHING,
            title="Continue current management — monitor for changes",
            description=(
                "Current conditions do not require immediate active intervention. "
                "Maintain routine monitoring schedule and review again at next interval."
            ),
            rationale=(
                f"Trajectory: {trajectory}. Bloom probability: {bloom_prob:.0%}. "
                f"Recovery potential: {recovery}."
            ),
            expected_outcome="System remains within acceptable parameters.",
            estimated_cost_aed=0.0,
            estimated_duration_hours=0.0,
            confidence=0.50,
            evidence=[f"Trajectory = {trajectory}"],
            kpis=["bloom_probability < 0.3", "do_mg_l > 4.0"],
        ))

        # ---- Sort by priority ----
        priority_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
        }
        candidates.sort(key=lambda r: (priority_order[r.priority], -r.confidence))

        primary = candidates[0]
        alternatives = candidates[1:4]  # top 3 alternatives

        # Determine urgency
        if primary.priority == RecommendationPriority.CRITICAL:
            urgency = "emergency"
        elif primary.priority == RecommendationPriority.HIGH:
            urgency = "urgent"
        elif primary.priority == RecommendationPriority.MEDIUM:
            urgency = "elevated"
        else:
            urgency = "normal"

        summary = (
            f"Lagoon {lagoon_id} — {len(candidates)} options evaluated. "
            f"Primary: {primary.title}. Urgency: {urgency}. "
            f"Bloom risk: {bloom_prob:.0%}. DO: {f'{do_mg_l:.1f} mg/L' if do_mg_l is not None else 'unknown'}."
        )

        return RecommendationSet(
            lagoon_id=lagoon_id,
            generated_at=now,
            primary_recommendation=primary,
            alternatives=alternatives,
            system_summary=summary,
            urgency_level=urgency,
        )

    async def publish_state(self, lagoon_id: UUID) -> None:
        state_dict = await self.compute_state(lagoon_id)
        key = f"rec:{lagoon_id}"
        if self._shared_memory is not None:
            try:
                await self._shared_memory.set(key, state_dict, ttl_seconds=1800)
            except Exception as exc:
                logger.warning("Shared memory write failed for %s: %s", key, exc)
        if self._event_bus is not None:
            try:
                await self._event_bus.publish(
                    topic="scientific.recommendation.set",
                    payload={"lagoon_id": str(lagoon_id), "recommendation": state_dict},
                )
            except Exception as exc:
                logger.warning("Event bus publish failed for %s: %s", lagoon_id, exc)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while self._running:
            try:
                lagoon_ids = list(self._known_lagoons)
                if not lagoon_ids and self._shared_memory is not None:
                    try:
                        registry = await self._shared_memory.get("lagoon:registry")
                        if registry:
                            lagoon_ids = [UUID(lid) for lid in registry.get("ids", [])]
                    except Exception:
                        pass

                for lagoon_id in lagoon_ids:
                    try:
                        await self.publish_state(lagoon_id)
                    except Exception as exc:
                        logger.error("RecommendationService loop error for %s: %s", lagoon_id, exc)
                        self._error_count += 1

                self._last_run = datetime.now(tz=UTC)
                self._run_count += 1

            except Exception as exc:
                logger.error("RecommendationService loop unhandled error: %s", exc)
                self._status = ServiceStatus.ERROR
                self._error_count += 1
            finally:
                await asyncio.sleep(self._interval_seconds)
