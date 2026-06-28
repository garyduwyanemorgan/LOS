"""
Learning service — continuously improves model confidence and identifies
patterns from prediction outcomes and intervention results.

Stores model confidence scores, evaluates predictions against actuals,
identifies seasonal patterns, and updates the Scientific Relationship Graph.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import statistics
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ..base import ScientificService, ServiceStatus

logger = logging.getLogger(__name__)

# Maximum history per (lagoon, parameter)
_MAX_HISTORY = 2000


class LearningService(ScientificService):
    """
    Continuous model learning and calibration service.

    Evaluates prediction accuracy, updates model confidence,
    identifies seasonal patterns, and learns from interventions.

    Loop interval: configurable (default 3600 s / 1 hour).
    """

    service_name = "learning"
    loop_name = "learning_loop"

    def __init__(
        self,
        shared_memory: Any,
        event_bus: Any,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._shared_memory = shared_memory
        self._event_bus = event_bus
        self._config = config or {}
        self._interval_seconds: float = float(self._config.get("interval_seconds", 3600))
        self._running = False
        self._task: asyncio.Task | None = None

        # Model confidence registry: (lagoon_id, model_name) → confidence [0,1]
        self._model_confidence: dict[tuple[UUID, str], float] = {}

        # Prediction accuracy history: (lagoon_id, param) → list of errors
        self._prediction_errors: dict[tuple[UUID, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=500)
        )

        # Seasonal pattern data: (lagoon_id, param) → list of (month, value)
        self._seasonal_data: dict[tuple[UUID, str], list[tuple[int, float]]] = defaultdict(list)

        # Intervention outcomes: intervention_id → outcome dict
        self._intervention_outcomes: dict[str, dict[str, Any]] = {}

        # Improvement trajectories: (lagoon_id, objective) → deque of scores
        self._improvement_trajectories: dict[tuple[UUID, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=_MAX_HISTORY)
        )

        self._status = ServiceStatus.INITIALIZING

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("LearningService starting (interval=%.0fs)", self._interval_seconds)
        self._running = True
        self._status = ServiceStatus.RUNNING
        self._task = asyncio.create_task(self._run_loop(), name="learning_loop")
        if self._event_bus is not None:
            await self._event_bus.subscribe("event.prediction_verified", self.process_event)
            await self._event_bus.subscribe("event.intervention_outcome", self.process_event)
            await self._event_bus.subscribe("scientific.ecological.state", self.process_event)
            await self._event_bus.subscribe("scientific.hydrological.state", self.process_event)

    async def stop(self) -> None:
        logger.info("LearningService stopping")
        self._running = False
        self._status = ServiceStatus.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def process_event(self, event: dict[str, Any]) -> None:
        try:
            topic: str = event.get("topic", "")
            lagoon_id_str = event.get("lagoon_id")
            data: dict[str, Any] = event.get("data", event.get("state", {}))

            if "event.prediction_verified" in topic:
                lagoon_id = UUID(str(lagoon_id_str))
                param = str(data.get("parameter", "unknown"))
                predicted = float(data.get("predicted_value", 0.0))
                actual = float(data.get("actual_value", 0.0))
                accuracy = await self.evaluate_prediction_accuracy(
                    lagoon_id, {"parameter": param, "predicted_value": predicted}, actual
                )
                model_name = data.get("model_name", "default")
                await self.update_model_confidence(
                    lagoon_id, model_name, accuracy - 0.5  # delta relative to 0.5 baseline
                )

            elif "event.intervention_outcome" in topic:
                intervention_id = str(data.get("intervention_id", ""))
                success = bool(data.get("success", False))
                evidence = data.get("evidence", {})
                if intervention_id:
                    await self.update_srg_from_outcome(intervention_id, success, evidence)

            elif lagoon_id_str and any(
                t in topic for t in ("scientific.ecological", "scientific.hydrological")
            ):
                lagoon_id = UUID(str(lagoon_id_str))
                now = datetime.now(tz=UTC)
                month = now.month
                tracked = [
                    "bloom_probability", "do_mg_l", "residence_time_days",
                    "tp_mg_l", "water_level_m",
                ]
                for param in tracked:
                    val = data.get(param)
                    if val is not None:
                        self._seasonal_data[(lagoon_id, param)].append(
                            (month, float(val))
                        )
                        # Trim to 2 years of data (assuming 1 reading/hour)
                        if len(self._seasonal_data[(lagoon_id, param)]) > 17520:
                            self._seasonal_data[(lagoon_id, param)] = (
                                self._seasonal_data[(lagoon_id, param)][-17520:]
                            )

        except Exception as exc:
            logger.warning("LearningService.process_event error: %s", exc)
            self._error_count += 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate_prediction_accuracy(
        self,
        lagoon_id: UUID,
        prediction: dict[str, Any],
        actual_outcome: float,
    ) -> float:
        """
        Evaluate prediction accuracy using normalised absolute error.

        Returns: accuracy in [0, 1] where 1 = perfect prediction.
        """
        predicted_value = float(prediction.get("predicted_value", 0.0))
        param = str(prediction.get("parameter", "unknown"))

        # Compute relative error
        scale = max(abs(actual_outcome), abs(predicted_value), 0.001)
        absolute_error = abs(predicted_value - actual_outcome)
        relative_error = absolute_error / scale

        # Accuracy = 1 - normalised error (clamped 0-1)
        accuracy = max(0.0, min(1.0, 1.0 - relative_error))

        # Store error for tracking
        self._prediction_errors[(lagoon_id, param)].append(relative_error)

        # Persist to shared memory
        if self._shared_memory is not None:
            key = f"learn:accuracy:{lagoon_id}:{param}"
            try:
                history = await self._shared_memory.get(key) or {"errors": [], "count": 0}
                errors: list[float] = history.get("errors", [])
                errors.append(relative_error)
                errors = errors[-500:]
                mean_acc = 1.0 - statistics.mean(errors) if errors else 0.5
                await self._shared_memory.set(key, {
                    "errors": errors,
                    "count": history.get("count", 0) + 1,
                    "mean_accuracy": round(mean_acc, 4),
                    "last_updated": datetime.now(tz=UTC).isoformat(),
                }, ttl_seconds=None)
            except Exception as exc:
                logger.debug("Learning accuracy persist error: %s", exc)

        logger.debug(
            "Prediction accuracy for %s.%s: predicted=%.3f actual=%.3f accuracy=%.3f",
            lagoon_id, param, predicted_value, actual_outcome, accuracy,
        )
        return round(accuracy, 4)

    async def update_model_confidence(
        self,
        lagoon_id: UUID,
        model_name: str,
        accuracy_delta: float,
    ) -> None:
        """
        Bayesian-style confidence update for a model.

        accuracy_delta: positive = model was accurate, negative = inaccurate.
        Applies exponential moving average with α = 0.1.
        """
        key = (lagoon_id, model_name)
        current = self._model_confidence.get(key, 0.70)  # start with 70% confidence

        # Exponential moving average
        alpha = 0.10
        updated = current + alpha * accuracy_delta
        updated = max(0.05, min(0.99, updated))
        self._model_confidence[key] = round(updated, 4)

        # Persist
        if self._shared_memory is not None:
            try:
                await self._shared_memory.set(
                    f"learn:confidence:{lagoon_id}:{model_name}",
                    {
                        "model_name": model_name,
                        "lagoon_id": str(lagoon_id),
                        "confidence": updated,
                        "last_updated": datetime.now(tz=UTC).isoformat(),
                    },
                    ttl_seconds=None,
                )
            except Exception as exc:
                logger.debug("Confidence persist error: %s", exc)

        logger.debug(
            "Model confidence updated: %s.%s %.3f → %.3f (delta=%.3f)",
            lagoon_id, model_name, current, updated, accuracy_delta,
        )

    async def identify_seasonal_patterns(
        self,
        lagoon_id: UUID,
        parameter: str,
        years: int = 2,
    ) -> dict[str, Any]:
        """
        Identify seasonal patterns in a parameter over the given number of years.

        Returns monthly mean, std, and peak/trough months.
        """
        data = self._seasonal_data.get((lagoon_id, parameter), [])
        if not data:
            # Try shared memory
            if self._shared_memory is not None:
                try:
                    stored = await self._shared_memory.get(
                        f"learn:seasonal:{lagoon_id}:{parameter}"
                    )
                    if stored:
                        return stored
                except Exception:
                    pass
            return {
                "parameter": parameter,
                "lagoon_id": str(lagoon_id),
                "status": "insufficient_data",
                "data_points": 0,
            }

        # Group by month
        monthly: dict[int, list[float]] = defaultdict(list)
        for month, value in data:
            monthly[month].append(value)

        monthly_stats: dict[str, Any] = {}
        for m in range(1, 13):
            vals = monthly.get(m, [])
            if vals:
                monthly_stats[str(m)] = {
                    "mean": round(statistics.mean(vals), 4),
                    "std": round(statistics.stdev(vals) if len(vals) > 1 else 0.0, 4),
                    "count": len(vals),
                    "min": round(min(vals), 4),
                    "max": round(max(vals), 4),
                }

        # Peak and trough months
        if monthly_stats:
            peak_month = max(
                monthly_stats.keys(),
                key=lambda m: monthly_stats[m]["mean"],
            )
            trough_month = min(
                monthly_stats.keys(),
                key=lambda m: monthly_stats[m]["mean"],
            )
        else:
            peak_month = "unknown"
            trough_month = "unknown"

        # Seasonality strength — ratio of inter-monthly variance to total variance
        all_values = [v for _, v in data]
        if len(all_values) > 1:
            total_variance = statistics.variance(all_values)
            monthly_means = [
                statistics.mean(monthly.get(m, [statistics.mean(all_values)]))
                for m in range(1, 13)
            ]
            inter_monthly_variance = statistics.variance(monthly_means)
            seasonality_strength = (
                inter_monthly_variance / total_variance if total_variance > 0 else 0.0
            )
        else:
            seasonality_strength = 0.0

        result = {
            "parameter": parameter,
            "lagoon_id": str(lagoon_id),
            "status": "computed",
            "data_points": len(data),
            "monthly_stats": monthly_stats,
            "peak_month": peak_month,
            "trough_month": trough_month,
            "seasonality_strength": round(seasonality_strength, 4),
            "computed_at": datetime.now(tz=UTC).isoformat(),
        }

        # Cache result
        if self._shared_memory is not None:
            with contextlib.suppress(Exception):
                await self._shared_memory.set(
                    f"learn:seasonal:{lagoon_id}:{parameter}",
                    result,
                    ttl_seconds=86400,
                )

        return result

    async def update_srg_from_outcome(
        self,
        intervention_id: str,
        success: bool,
        evidence: dict[str, Any],
    ) -> None:
        """
        Update the Scientific Relationship Graph based on intervention outcome.

        Records outcome and updates action efficacy scores.
        """
        outcome = {
            "intervention_id": intervention_id,
            "success": success,
            "evidence": evidence,
            "recorded_at": datetime.now(tz=UTC).isoformat(),
        }
        self._intervention_outcomes[intervention_id] = outcome

        # Update SRG via shared memory
        if self._shared_memory is not None:
            try:
                srg_key = f"srg:outcome:{intervention_id}"
                await self._shared_memory.set(srg_key, outcome, ttl_seconds=None)

                # Update action efficacy score
                action_type = str(evidence.get("action_category", "unknown"))
                efficacy_key = f"srg:efficacy:{action_type}"
                existing = await self._shared_memory.get(efficacy_key) or {
                    "successes": 0, "total": 0, "efficacy": 0.5
                }
                existing["total"] += 1
                if success:
                    existing["successes"] += 1
                existing["efficacy"] = round(existing["successes"] / existing["total"], 4)
                existing["last_updated"] = datetime.now(tz=UTC).isoformat()
                await self._shared_memory.set(efficacy_key, existing, ttl_seconds=None)

            except Exception as exc:
                logger.warning("SRG update error for %s: %s", intervention_id, exc)

        if self._event_bus is not None:
            with contextlib.suppress(Exception):
                await self._event_bus.publish(
                    topic="learning.srg_updated",
                    payload=outcome,
                )

        logger.info(
            "SRG updated: intervention=%s success=%s action=%s",
            intervention_id, success, evidence.get("action_category", "?"),
        )

    async def get_improvement_trajectory(
        self,
        lagoon_id: UUID,
        objective: str,
    ) -> dict[str, Any]:
        """
        Get the improvement trajectory for a specific objective/parameter.

        Returns trend direction, slope, and recent history.
        """
        key = (lagoon_id, objective)
        history = list(self._improvement_trajectories[key])

        if len(history) < 3:
            return {
                "lagoon_id": str(lagoon_id),
                "objective": objective,
                "status": "insufficient_data",
                "history_points": len(history),
            }

        # Linear slope
        n = len(history)
        x_mean = (n - 1) / 2.0
        y_mean = statistics.mean(history)
        num = sum((i - x_mean) * (history[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0.0

        if slope > 0.01:
            direction = "improving"
        elif slope < -0.01:
            direction = "deteriorating"
        else:
            direction = "stable"

        # Moving average
        window = min(12, n)
        recent_mean = statistics.mean(history[-window:])
        overall_mean = statistics.mean(history)
        improvement_vs_baseline = (recent_mean - overall_mean) / max(abs(overall_mean), 0.001)

        return {
            "lagoon_id": str(lagoon_id),
            "objective": objective,
            "status": "computed",
            "direction": direction,
            "slope_per_step": round(slope, 6),
            "current_value": round(history[-1], 4),
            "recent_mean": round(recent_mean, 4),
            "improvement_vs_baseline_pct": round(improvement_vs_baseline * 100, 2),
            "history_points": n,
            "computed_at": datetime.now(tz=UTC).isoformat(),
        }

    def record_objective_score(
        self,
        lagoon_id: UUID,
        objective: str,
        score: float,
    ) -> None:
        """Record an objective score for trajectory tracking."""
        self._improvement_trajectories[(lagoon_id, objective)].append(score)

    # ------------------------------------------------------------------
    # ScientificService interface
    # ------------------------------------------------------------------

    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        """Return current learning state summary for a lagoon."""
        model_confs = {
            f"{k[1]}": v
            for k, v in self._model_confidence.items()
            if k[0] == lagoon_id
        }
        pred_counts = {
            f"{k[1]}": len(v)
            for k, v in self._prediction_errors.items()
            if k[0] == lagoon_id
        }
        mean_accuracies = {}
        for k, errors in self._prediction_errors.items():
            if k[0] == lagoon_id and errors:
                mean_accuracies[k[1]] = round(1.0 - statistics.mean(errors), 4)

        return {
            "lagoon_id": str(lagoon_id),
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "model_confidences": model_confs,
            "prediction_counts": pred_counts,
            "mean_prediction_accuracies": mean_accuracies,
            "intervention_outcomes_count": len(self._intervention_outcomes),
        }

    async def publish_state(self, lagoon_id: UUID) -> None:
        state = await self.compute_state(lagoon_id)
        key = f"learn:state:{lagoon_id}"
        if self._shared_memory is not None:
            try:
                await self._shared_memory.set(key, state, ttl_seconds=7200)
            except Exception as exc:
                logger.debug("Learning state persist error: %s", exc)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while self._running:
            try:
                # Collect all known lagoon IDs from tracked data
                lagoon_ids: set[UUID] = set()
                for k in self._model_confidence:
                    lagoon_ids.add(k[0])
                for k in self._prediction_errors:
                    lagoon_ids.add(k[0])

                if not lagoon_ids and self._shared_memory is not None:
                    try:
                        registry = await self._shared_memory.get("lagoon:registry")
                        if registry:
                            lagoon_ids = {UUID(lid) for lid in registry.get("ids", [])}
                    except Exception:
                        pass

                for lagoon_id in lagoon_ids:
                    try:
                        await self.publish_state(lagoon_id)
                        # Refresh seasonal patterns periodically
                        for param in ("bloom_probability", "do_mg_l", "tp_mg_l"):
                            await self.identify_seasonal_patterns(lagoon_id, param)
                    except Exception as exc:
                        logger.error("LearningService loop error for %s: %s", lagoon_id, exc)
                        self._error_count += 1

                self._last_run = datetime.now(tz=UTC)
                self._run_count += 1

            except Exception as exc:
                logger.error("LearningService loop unhandled error: %s", exc)
                self._status = ServiceStatus.ERROR
                self._error_count += 1
            finally:
                await asyncio.sleep(self._interval_seconds)
