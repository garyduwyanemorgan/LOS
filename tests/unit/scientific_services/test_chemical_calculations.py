"""Unit tests for chemical calculations module."""
from __future__ import annotations

import pytest

from backend.scientific_services.chemical.calculations import (
    classify_redox,
    do_saturation,
    trophic_state_index,
)


class TestRedoxClassification:
    """ORP-based redox state classification."""

    def test_oxic(self) -> None:
        assert classify_redox(orp_mv=250.0) == "oxic"

    def test_suboxic(self) -> None:
        assert classify_redox(orp_mv=100.0) == "suboxic"

    def test_anoxic(self) -> None:
        assert classify_redox(orp_mv=-80.0) == "anoxic"

    def test_reducing(self) -> None:
        assert classify_redox(orp_mv=-250.0) == "reducing"

    def test_boundary_oxic_suboxic(self) -> None:
        result = classify_redox(orp_mv=200.0)
        assert result in ("oxic", "suboxic")  # boundary depends on implementation

    def test_all_states_valid(self) -> None:
        valid_states = {"oxic", "suboxic", "anoxic", "reducing"}
        for orp in [-300, -150, -50, 50, 150, 300]:
            state = classify_redox(orp_mv=float(orp))
            assert state in valid_states


class TestDOSaturation:
    """Dissolved oxygen saturation (Benson & Krause equations)."""

    def test_freshwater_20c(self) -> None:
        """At 20°C, freshwater DO saturation ≈ 9.1 mg/L."""
        sat = do_saturation(temperature_c=20.0, salinity_ppt=0.0)
        assert 8.8 < sat < 9.4, f"DO sat={sat} at 20°C freshwater unexpected"

    def test_seawater_25c(self) -> None:
        """Typical seawater (35 ppt) at 25°C DO saturation ≈ 7.0 mg/L."""
        sat = do_saturation(temperature_c=25.0, salinity_ppt=35.0)
        assert 6.5 < sat < 7.5, f"DO sat={sat} at 25°C seawater unexpected"

    def test_saturation_decreases_with_temperature(self) -> None:
        """DO saturation must decrease as temperature increases."""
        sat_15 = do_saturation(temperature_c=15.0, salinity_ppt=0.0)
        sat_25 = do_saturation(temperature_c=25.0, salinity_ppt=0.0)
        sat_35 = do_saturation(temperature_c=35.0, salinity_ppt=0.0)
        assert sat_15 > sat_25 > sat_35

    def test_saturation_decreases_with_salinity(self) -> None:
        """DO saturation must decrease as salinity increases (salting-out)."""
        sat_fresh = do_saturation(temperature_c=25.0, salinity_ppt=0.0)
        sat_brackish = do_saturation(temperature_c=25.0, salinity_ppt=10.0)
        sat_marine = do_saturation(temperature_c=25.0, salinity_ppt=35.0)
        assert sat_fresh > sat_brackish > sat_marine

    def test_saturation_always_positive(self) -> None:
        """DO saturation must always be positive."""
        for temp in [5.0, 15.0, 25.0, 35.0, 45.0]:
            for sal in [0.0, 10.0, 35.0]:
                assert do_saturation(temp, sal) > 0.0


class TestTrophicStateIndex:
    """Carlson-derived Trophic State Index classification."""

    def test_oligotrophic(self) -> None:
        tsi = trophic_state_index(chlorophyll_a_ug_l=1.0, total_phosphorus_mg_l=0.005)
        assert tsi in ("oligotrophic", "ultra-oligotrophic")

    def test_mesotrophic(self) -> None:
        tsi = trophic_state_index(chlorophyll_a_ug_l=5.0, total_phosphorus_mg_l=0.02)
        assert tsi == "mesotrophic"

    def test_eutrophic(self) -> None:
        tsi = trophic_state_index(chlorophyll_a_ug_l=25.0, total_phosphorus_mg_l=0.08)
        assert tsi in ("eutrophic", "hypereutrophic")

    def test_hypereutrophic(self) -> None:
        tsi = trophic_state_index(chlorophyll_a_ug_l=200.0, total_phosphorus_mg_l=0.5)
        assert tsi == "hypereutrophic"
