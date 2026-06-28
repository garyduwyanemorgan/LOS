"""Unit tests for the anomaly detection ML model."""
from __future__ import annotations

import uuid

import pytest

from backend.scientific_models.ml.anomaly_detection import AnomalyDetectionModel, AnomalyResult


LAGOON_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


def _make_series(values: list[float]) -> list[dict]:
    return [{"value": v, "timestamp": f"2026-01-01T{i:02d}:00:00Z"} for i, v in enumerate(values)]


class TestAnomalyDetectionModel:
    def _model(self) -> AnomalyDetectionModel:
        return AnomalyDetectionModel()

    def test_model_identity(self) -> None:
        m = self._model()
        assert m.model_name == "anomaly_detection"
        assert m.model_version == "1.0.0"

    def test_empty_series_returns_zero_anomalies(self) -> None:
        m = self._model()
        result = m.run({"series": []}, LAGOON_ID)
        assert result.values["anomaly_count"] == 0
        assert result.confidence == 0.0
        assert len(result.errors) > 0

    def test_too_few_points_returns_warning(self) -> None:
        m = self._model()
        result = m.run({"series": _make_series([1.0, 2.0, 3.0])}, LAGOON_ID)
        assert len(result.warnings) > 0

    def test_no_anomalies_in_clean_series(self) -> None:
        m = self._model()
        normal = list(range(1, 30))  # 1..29, clean linear data
        result = m.run({"series": _make_series([float(x) for x in normal])}, LAGOON_ID)
        assert result.values["anomaly_count"] == 0
        assert result.is_valid

    def test_detects_extreme_outlier(self) -> None:
        m = self._model()
        # Insert a spike at position 15
        values = [5.0] * 30
        values[15] = 500.0
        result = m.run({"series": _make_series(values)}, LAGOON_ID)
        assert result.values["anomaly_count"] >= 1
        anomalies = result.values["anomalies"]
        assert any(a["value"] == 500.0 for a in anomalies)

    def test_anomaly_severity_high_for_extreme_spike(self) -> None:
        m = self._model()
        values = [7.0] * 50
        values[25] = 1000.0
        result = m.run({"series": _make_series(values)}, LAGOON_ID)
        anomalies = result.values["anomalies"]
        extreme = [a for a in anomalies if a["value"] == 1000.0]
        assert extreme
        assert extreme[0]["severity"] == "high"

    def test_rate_of_change_detection(self) -> None:
        m = self._model()
        # Gradual series with sudden jump
        values = [5.0] * 20
        values.append(50.0)  # 45 unit jump in one step
        values += [50.0] * 9
        result = m.run(
            {
                "series": _make_series(values),
                "max_rate_per_hour": 5.0,  # max 5 units per step
            },
            LAGOON_ID,
        )
        assert result.values["anomaly_count"] >= 1
        assert any("rate_of_change" in a["method"] for a in result.values["anomalies"])

    def test_output_contains_statistics(self) -> None:
        m = self._model()
        values = [float(x) for x in range(10, 30)]
        result = m.run({"series": _make_series(values)}, LAGOON_ID)
        assert "median" in result.values
        assert "mad" in result.values
        assert "q1" in result.values
        assert "q3" in result.values
        assert "iqr" in result.values

    def test_anomaly_rate_pct_calculated(self) -> None:
        m = self._model()
        values = [5.0] * 19 + [500.0]  # 1 anomaly in 20
        result = m.run({"series": _make_series(values)}, LAGOON_ID)
        assert result.values["anomaly_rate_pct"] >= 0.0

    def test_confidence_increases_with_more_data(self) -> None:
        m = self._model()
        small = m.run({"series": _make_series([5.0] * 10)}, LAGOON_ID)
        large = m.run({"series": _make_series([5.0] * 1000)}, LAGOON_ID)
        assert large.confidence >= small.confidence

    def test_custom_z_threshold(self) -> None:
        m = self._model()
        values = [5.0] * 30
        values[10] = 8.0  # mild deviation
        # With tight threshold, should flag it
        result_tight = m.run(
            {"series": _make_series(values), "z_threshold": 0.5}, LAGOON_ID
        )
        # With default threshold (3.5), should not flag it
        result_loose = m.run(
            {"series": _make_series(values), "z_threshold": 3.5}, LAGOON_ID
        )
        assert result_tight.values["anomaly_count"] >= result_loose.values["anomaly_count"]

    def test_iqr_fence_values_present(self) -> None:
        m = self._model()
        result = m.run({"series": _make_series([float(x) for x in range(20)])}, LAGOON_ID)
        assert "iqr_fence_lo" in result.values
        assert "iqr_fence_hi" in result.values

    def test_method_used_list_populated(self) -> None:
        m = self._model()
        values = [5.0] * 30
        values[10] = 500.0
        result = m.run({"series": _make_series(values)}, LAGOON_ID)
        assert isinstance(result.values["method_used"], list)

    def test_anomaly_result_to_dict(self) -> None:
        ar = AnomalyResult(
            value=500.0,
            timestamp="2026-01-01T00:00:00Z",
            is_anomaly=True,
            method="z_score",
            score=10.5,
            threshold=3.5,
            severity="high",
        )
        d = ar.to_dict()
        assert d["is_anomaly"] is True
        assert d["severity"] == "high"
        assert d["score"] == pytest.approx(10.5)
