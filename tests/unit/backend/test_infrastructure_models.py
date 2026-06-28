"""Unit tests for infrastructure scientific models."""
from __future__ import annotations

import uuid

import pytest

from backend.scientific_models.infrastructure.aeration_efficiency import AerationEfficiencyModel
from backend.scientific_models.infrastructure.pump_performance import PumpPerformanceModel


LAGOON_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


class TestAerationEfficiencyModel:
    def _model(self) -> AerationEfficiencyModel:
        return AerationEfficiencyModel()

    def test_model_identity(self) -> None:
        m = self._model()
        assert m.model_name == "aeration_efficiency"
        assert m.model_version == "1.0.0"

    def test_run_with_full_inputs(self) -> None:
        m = self._model()
        result = m.run(
            {
                "do_sat_mg_l": 8.0,
                "do_field_mg_l": 3.0,
                "temperature_c": 28.0,
                "power_kw": 5.0,
                "volume_m3": 500_000.0,
                "alpha": 0.85,
                "beta": 0.95,
                "rated_sae_kg_o2_kwh": 1.5,
            },
            LAGOON_ID,
        )
        assert result.is_valid
        assert "sotr_kg_o2_h" in result.values
        assert "otr_kg_o2_h" in result.values
        assert "oae_kg_o2_kwh" in result.values
        assert result.values["sotr_kg_o2_h"] == pytest.approx(7.5, rel=0.01)

    def test_run_without_power_omits_otr(self) -> None:
        m = self._model()
        result = m.run(
            {"do_sat_mg_l": 8.0, "do_field_mg_l": 4.0, "temperature_c": 25.0},
            LAGOON_ID,
        )
        assert "sotr_kg_o2_h" not in result.values
        assert len(result.warnings) > 0

    def test_do_sat_estimated_without_input(self) -> None:
        m = self._model()
        result = m.run({"temperature_c": 25.0, "power_kw": 2.0, "volume_m3": 100_000.0}, LAGOON_ID)
        assert "do_sat_computed_mg_l" in result.values

    def test_oxygen_deficit_computed(self) -> None:
        m = self._model()
        result = m.run(
            {"do_sat_mg_l": 9.0, "do_field_mg_l": 5.0, "temperature_c": 20.0},
            LAGOON_ID,
        )
        assert result.values.get("oxygen_deficit_mg_l") == pytest.approx(4.0, rel=0.01)

    def test_pressure_correction_at_elevation(self) -> None:
        m = self._model()
        r_sea = m.run(
            {"do_sat_mg_l": 9.0, "do_field_mg_l": 5.0, "temperature_c": 20.0, "elevation_m": 0},
            LAGOON_ID,
        )
        r_high = m.run(
            {"do_sat_mg_l": 9.0, "do_field_mg_l": 5.0, "temperature_c": 20.0, "elevation_m": 2000},
            LAGOON_ID,
        )
        assert r_sea.values["pressure_correction"] > r_high.values["pressure_correction"]

    def test_confidence_reduced_with_missing_inputs(self) -> None:
        m = self._model()
        full = m.run(
            {"do_sat_mg_l": 8.0, "do_field_mg_l": 4.0, "temperature_c": 25.0,
             "power_kw": 2.0, "volume_m3": 100_000.0},
            LAGOON_ID,
        )
        partial = m.run({"temperature_c": 25.0}, LAGOON_ID)
        assert full.confidence >= partial.confidence


class TestPumpPerformanceModel:
    def _model(self) -> PumpPerformanceModel:
        return PumpPerformanceModel()

    def test_model_identity(self) -> None:
        m = self._model()
        assert m.model_name == "pump_performance"

    def test_run_at_bep(self) -> None:
        m = self._model()
        result = m.run(
            {
                "flow_rate_m3_h": 100.0,
                "head_m": 10.0,
                "power_input_kw": 5.0,
                "rated_flow_m3_h": 100.0,
                "rated_head_m": 10.0,
                "rated_power_kw": 4.8,
            },
            LAGOON_ID,
        )
        assert result.is_valid
        assert result.values.get("flow_deviation_pct") == pytest.approx(0.0, abs=0.1)
        assert result.values.get("head_deviation_pct") == pytest.approx(0.0, abs=0.1)

    def test_degradation_flag_set_when_efficiency_low(self) -> None:
        m = self._model()
        result = m.run(
            {
                "flow_rate_m3_h": 100.0,
                "head_m": 10.0,
                "power_input_kw": 10.0,  # double the rated — 50% efficiency relative
                "rated_flow_m3_h": 100.0,
                "rated_head_m": 10.0,
                "rated_power_kw": 4.8,
            },
            LAGOON_ID,
        )
        assert result.values.get("degradation_flag") is True

    def test_cavitation_risk_high_at_excess_flow(self) -> None:
        m = self._model()
        result = m.run(
            {
                "flow_rate_m3_h": 130.0,  # 30% over rated
                "head_m": 8.0,
                "rated_flow_m3_h": 100.0,
            },
            LAGOON_ID,
        )
        assert result.values.get("cavitation_risk") == "high"

    def test_cavitation_risk_low_at_bep(self) -> None:
        m = self._model()
        result = m.run(
            {
                "flow_rate_m3_h": 100.0,
                "head_m": 10.0,
                "rated_flow_m3_h": 100.0,
            },
            LAGOON_ID,
        )
        assert result.values.get("cavitation_risk") == "low"

    def test_affinity_correction_applied(self) -> None:
        m = self._model()
        result = m.run(
            {
                "flow_rate_m3_h": 80.0,
                "head_m": 10.0,
                "speed_rpm": 1450.0,
                "rated_flow_m3_h": 100.0,
                "rated_head_m": 10.0,
                "rated_speed_rpm": 1450.0,
            },
            LAGOON_ID,
        )
        assert result.is_valid

    def test_performance_index_between_0_and_1(self) -> None:
        m = self._model()
        result = m.run(
            {
                "flow_rate_m3_h": 90.0,
                "head_m": 9.5,
                "rated_flow_m3_h": 100.0,
                "rated_head_m": 10.0,
            },
            LAGOON_ID,
        )
        pi = result.values.get("performance_index")
        assert pi is not None
        assert 0.0 <= pi <= 1.0

    def test_empty_inputs_produces_error(self) -> None:
        m = self._model()
        result = m.run({}, LAGOON_ID)
        assert len(result.errors) > 0
        assert result.confidence == 0.0
