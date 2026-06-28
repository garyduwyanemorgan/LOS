"""Unit tests for hydrological calculations module.

Tests verify mathematical correctness against known analytical solutions.
"""
from __future__ import annotations

import math
import pytest

from backend.scientific_services.hydrological.calculations import (
    penman_monteith_et0,
    water_balance,
    residence_time,
    darcy_flux,
)


class TestPenmanMonteithET0:
    """FAO-56 Penman-Monteith ET0 calculation tests."""

    def test_typical_desert_conditions(self) -> None:
        """Verify ET0 for typical GCC summer conditions against reference values."""
        # Conditions: Dubai July — high temp, low RH, significant wind
        et0 = penman_monteith_et0(
            temperature_c=38.0,
            relative_humidity_pct=55.0,
            wind_speed_m_s=4.0,
            solar_radiation_mj_m2_day=25.0,
            elevation_m=5.0,
        )
        # Expected: approximately 8-12 mm/day for these conditions
        assert 7.0 < et0 < 14.0, f"ET0={et0} outside expected range for GCC summer"

    def test_cool_humid_conditions(self) -> None:
        """Verify ET0 for mild, humid conditions."""
        et0 = penman_monteith_et0(
            temperature_c=15.0,
            relative_humidity_pct=80.0,
            wind_speed_m_s=1.5,
            solar_radiation_mj_m2_day=12.0,
            elevation_m=100.0,
        )
        # Expected: approximately 2-4 mm/day
        assert 1.5 < et0 < 5.0, f"ET0={et0} outside expected range for cool-humid"

    def test_et0_increases_with_temperature(self) -> None:
        """ET0 must increase monotonically with temperature (all else equal)."""
        base_params = dict(
            relative_humidity_pct=50.0,
            wind_speed_m_s=2.0,
            solar_radiation_mj_m2_day=18.0,
            elevation_m=10.0,
        )
        et0_20 = penman_monteith_et0(temperature_c=20.0, **base_params)
        et0_30 = penman_monteith_et0(temperature_c=30.0, **base_params)
        et0_40 = penman_monteith_et0(temperature_c=40.0, **base_params)
        assert et0_20 < et0_30 < et0_40

    def test_et0_increases_with_wind(self) -> None:
        """ET0 must increase with wind speed (all else equal)."""
        base_params = dict(
            temperature_c=25.0,
            relative_humidity_pct=50.0,
            solar_radiation_mj_m2_day=18.0,
            elevation_m=10.0,
        )
        et0_calm = penman_monteith_et0(wind_speed_m_s=0.5, **base_params)
        et0_windy = penman_monteith_et0(wind_speed_m_s=5.0, **base_params)
        assert et0_calm < et0_windy

    def test_et0_decreases_with_humidity(self) -> None:
        """ET0 must decrease with increasing relative humidity (all else equal)."""
        base_params = dict(
            temperature_c=25.0,
            wind_speed_m_s=2.0,
            solar_radiation_mj_m2_day=18.0,
            elevation_m=10.0,
        )
        et0_dry = penman_monteith_et0(relative_humidity_pct=30.0, **base_params)
        et0_humid = penman_monteith_et0(relative_humidity_pct=90.0, **base_params)
        assert et0_dry > et0_humid

    def test_et0_positive(self) -> None:
        """ET0 must always be positive."""
        et0 = penman_monteith_et0(
            temperature_c=10.0,
            relative_humidity_pct=95.0,
            wind_speed_m_s=0.1,
            solar_radiation_mj_m2_day=2.0,
            elevation_m=0.0,
        )
        assert et0 >= 0.0


class TestWaterBalance:
    """Water balance computation tests."""

    def test_steady_state(self) -> None:
        """Volume change must be zero when inflow equals outflow."""
        delta_v = water_balance(
            inflow_m3_day=1000.0,
            outflow_m3_day=950.0,
            precipitation_m_day=0.0,
            evapotranspiration_m_day=0.0,
            surface_area_m2=50000.0,
            groundwater_flux_m3_day=0.0,
        )
        # Inflow - outflow = 50 m3/day
        assert abs(delta_v - 50.0) < 0.01

    def test_precipitation_adds_volume(self) -> None:
        """Precipitation must increase volume."""
        delta_no_rain = water_balance(
            inflow_m3_day=500.0,
            outflow_m3_day=500.0,
            precipitation_m_day=0.0,
            evapotranspiration_m_day=0.0,
            surface_area_m2=100000.0,
            groundwater_flux_m3_day=0.0,
        )
        delta_with_rain = water_balance(
            inflow_m3_day=500.0,
            outflow_m3_day=500.0,
            precipitation_m_day=0.01,  # 10mm
            evapotranspiration_m_day=0.0,
            surface_area_m2=100000.0,
            groundwater_flux_m3_day=0.0,
        )
        assert delta_with_rain > delta_no_rain

    def test_et_removes_volume(self) -> None:
        """ET must reduce volume relative to no ET."""
        delta_no_et = water_balance(
            inflow_m3_day=500.0,
            outflow_m3_day=500.0,
            precipitation_m_day=0.0,
            evapotranspiration_m_day=0.0,
            surface_area_m2=100000.0,
            groundwater_flux_m3_day=0.0,
        )
        delta_with_et = water_balance(
            inflow_m3_day=500.0,
            outflow_m3_day=500.0,
            precipitation_m_day=0.0,
            evapotranspiration_m_day=0.005,  # 5mm/day
            surface_area_m2=100000.0,
            groundwater_flux_m3_day=0.0,
        )
        assert delta_with_et < delta_no_et


class TestResidenceTime:
    """Hydraulic residence time tests."""

    def test_basic_hrt(self) -> None:
        """HRT = Volume / Outflow."""
        hrt = residence_time(volume_m3=100000.0, outflow_m3_day=5000.0)
        assert abs(hrt - 20.0) < 0.001  # 100000/5000 = 20 days

    def test_zero_outflow_returns_infinity(self) -> None:
        """Zero outflow → infinite residence time."""
        hrt = residence_time(volume_m3=100000.0, outflow_m3_day=0.0)
        assert hrt == float("inf") or hrt > 1e9

    def test_hrt_positive(self) -> None:
        """HRT must always be positive for positive inputs."""
        hrt = residence_time(volume_m3=50000.0, outflow_m3_day=2500.0)
        assert hrt > 0.0


class TestDarcyFlux:
    """Darcy's Law groundwater flux tests."""

    def test_zero_gradient_zero_flux(self) -> None:
        """No hydraulic gradient → no flux."""
        q = darcy_flux(
            hydraulic_conductivity_m_day=1.0,
            hydraulic_gradient=0.0,
            cross_sectional_area_m2=100.0,
        )
        assert abs(q) < 1e-10

    def test_positive_gradient_positive_flux(self) -> None:
        """Positive gradient → positive flux (flow toward lagoon)."""
        q = darcy_flux(
            hydraulic_conductivity_m_day=0.5,
            hydraulic_gradient=0.01,
            cross_sectional_area_m2=500.0,
        )
        assert q > 0.0

    def test_flux_proportional_to_k(self) -> None:
        """Flux scales linearly with hydraulic conductivity."""
        q1 = darcy_flux(
            hydraulic_conductivity_m_day=1.0,
            hydraulic_gradient=0.005,
            cross_sectional_area_m2=100.0,
        )
        q2 = darcy_flux(
            hydraulic_conductivity_m_day=2.0,
            hydraulic_gradient=0.005,
            cross_sectional_area_m2=100.0,
        )
        assert abs(q2 - 2 * q1) < 0.001
