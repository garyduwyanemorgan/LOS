"""
Hydrological calculations for lagoon water balance and flow analysis.

All equations follow standard hydrological principles.
"""
import math


def water_balance_detailed(
    inflow_m3_day: float,
    outflow_m3_day: float,
    precipitation_mm_day: float,
    surface_area_m2: float,
    evaporation_mm_day: float,
    groundwater_flux_m3_day: float = 0.0,
) -> tuple[float, float]:
    """
    Compute daily water balance with mm/day precipitation inputs.

    ΔS = Qin + P*A - ET*A + Qgw_in - Qout

    Returns: (delta_storage_m3, water_balance_error_pct)
    """
    P_m3 = (precipitation_mm_day / 1000.0) * surface_area_m2
    ET_m3 = (evaporation_mm_day / 1000.0) * surface_area_m2
    delta_S = inflow_m3_day + P_m3 + groundwater_flux_m3_day - outflow_m3_day - ET_m3
    total_in = inflow_m3_day + P_m3 + max(0.0, groundwater_flux_m3_day)
    error_pct = abs(delta_S / total_in * 100) if total_in > 0 else 0.0
    return delta_S, error_pct


def residence_time_days(volume_m3: float, outflow_m3_day: float) -> float:
    """
    Mean hydraulic residence time: τ = V / Q_out

    Returns residence time in days. Returns 999 if outflow is negligible.
    """
    if outflow_m3_day < 0.001:
        return 999.0
    return volume_m3 / outflow_m3_day


def penman_monteith_reference_et(
    temp_mean_c: float,
    temp_min_c: float,
    temp_max_c: float,
    relative_humidity_pct: float,
    wind_speed_2m_ms: float,
    solar_radiation_mj_m2_day: float,
    elevation_m: float = 10.0,
) -> float:
    """
    FAO-56 Penman-Monteith reference evapotranspiration.

    Returns: ET0 in mm/day
    """
    # Atmospheric pressure (kPa)
    P = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26
    # Psychrometric constant kPa/°C
    gamma = 0.000665 * P

    # Saturation vapor pressure (kPa)
    e_s_min = 0.6108 * math.exp(17.27 * temp_min_c / (temp_min_c + 237.3))
    e_s_max = 0.6108 * math.exp(17.27 * temp_max_c / (temp_max_c + 237.3))
    e_s = (e_s_min + e_s_max) / 2.0
    e_a = e_s * relative_humidity_pct / 100.0

    # Slope of saturation vapor pressure curve (kPa/°C)
    delta = (
        4098.0
        * (0.6108 * math.exp(17.27 * temp_mean_c / (temp_mean_c + 237.3)))
        / (temp_mean_c + 237.3) ** 2
    )

    # Net radiation (MJ/m²/day) — simplified shortwave/longwave
    # 0.77 = 1 - albedo for water
    Rn = 0.77 * solar_radiation_mj_m2_day - 0.5
    G = 0.0  # soil/water heat flux negligible for daily

    # ET0 (mm/day) — FAO-56 Eq. 6
    numerator = (
        0.408 * delta * (Rn - G)
        + gamma * (900.0 / (temp_mean_c + 273.0)) * wind_speed_2m_ms * (e_s - e_a)
    )
    denominator = delta + gamma * (1.0 + 0.34 * wind_speed_2m_ms)
    ET0 = numerator / denominator
    return max(0.0, ET0)


def darcy_groundwater_flux(
    hydraulic_conductivity_m_day: float,
    hydraulic_gradient: float,
    area_m2: float,
) -> float:
    """
    Darcy's law: Q = K * i * A

    Returns: groundwater flux in m³/day (positive = into lagoon)
    """
    return hydraulic_conductivity_m_day * hydraulic_gradient * area_m2


def hydraulic_connectivity_score(
    inflow_variability: float,
    groundwater_contribution_fraction: float,
    rainfall_correlation: float,
) -> float:
    """
    Score hydraulic connectivity 0-1 based on observed connectivity indicators.

    Higher score = more connected to external water sources.
    """
    score = (
        min(inflow_variability, 1.0) * 0.4
        + min(groundwater_contribution_fraction, 1.0) * 0.4
        + min(rainfall_correlation, 1.0) * 0.2
    )
    return round(min(max(score, 0.0), 1.0), 3)


def volume_from_level(
    water_level_m: float,
    bathymetry_coefficients: dict[str, float],
) -> float:
    """
    Estimate lagoon volume from water level using a polynomial bathymetry curve.

    bathymetry_coefficients: {"a0": ..., "a1": ..., "a2": ...} for V = a0 + a1*h + a2*h²

    Returns: volume in m³
    """
    a0 = bathymetry_coefficients.get("a0", 0.0)
    a1 = bathymetry_coefficients.get("a1", 0.0)
    a2 = bathymetry_coefficients.get("a2", 0.0)
    volume = a0 + a1 * water_level_m + a2 * water_level_m**2
    return max(0.0, volume)


def surface_area_from_level(
    water_level_m: float,
    area_at_design_level_m2: float,
    design_level_m: float,
    shoreline_slope: float = 5.0,
) -> float:
    """
    Estimate surface area from water level using trapezoidal lagoon geometry.

    Returns: surface area in m²
    """
    if water_level_m <= 0.0:
        return 0.0
    # Simplified — area increases with level as perimeter * delta_h / slope
    delta_h = water_level_m - design_level_m
    # Perimeter estimate from design area (square approximation)
    perimeter = 4.0 * math.sqrt(area_at_design_level_m2)
    area = area_at_design_level_m2 + perimeter * delta_h / shoreline_slope
    return max(0.0, area)


def tidal_exchange_volume(
    tidal_range_m: float,
    inlet_width_m: float,
    inlet_depth_m: float,
    tidal_period_hours: float = 12.4,
) -> float:
    """
    Estimate tidal prism exchange volume using orifice approximation.

    Q_avg ≈ 0.5 * tidal_range * surface_area (simplified for inlet-dominated systems)

    For inlet-controlled exchange via Keulegan (1951):
    V_tidal ≈ C_d * A_inlet * sqrt(2g * tidal_range) * T/2

    Returns: tidal exchange volume per cycle in m³
    """
    g = 9.81  # m/s²
    Cd = 0.6   # discharge coefficient for inlet
    A_inlet = inlet_width_m * inlet_depth_m
    # Mean velocity through inlet at peak tidal head
    v_mean = Cd * math.sqrt(2.0 * g * tidal_range_m)
    # Duration of half tidal cycle
    T_half_seconds = (tidal_period_hours * 3600.0) / 2.0
    # Exchange volume
    V_exchange = A_inlet * v_mean * T_half_seconds
    return V_exchange


def flow_rate_from_weir(
    water_level_above_crest_m: float,
    weir_length_m: float,
    weir_type: str = "broad_crested",
) -> float:
    """
    Compute flow rate over a weir.

    Broad crested: Q = 1.67 * L * H^1.5
    Sharp crested (Francis): Q = 1.84 * L * H^1.5

    Returns: flow rate in m³/s
    """
    H = max(0.0, water_level_above_crest_m)
    if H < 0.001:
        return 0.0
    Cd = 1.84 if weir_type == "sharp_crested" else 1.67
    Q = Cd * weir_length_m * H**1.5
    return Q


# ── Simplified public aliases used by tests and external callers ──────────────

def penman_monteith_et0(
    temperature_c: float,
    relative_humidity_pct: float,
    wind_speed_m_s: float,
    solar_radiation_mj_m2_day: float,
    elevation_m: float = 10.0,
) -> float:
    """FAO-56 ET0 with single temperature input (min/max estimated ±3°C)."""
    return penman_monteith_reference_et(
        temp_mean_c=temperature_c,
        temp_min_c=temperature_c - 3.0,
        temp_max_c=temperature_c + 3.0,
        relative_humidity_pct=relative_humidity_pct,
        wind_speed_2m_ms=wind_speed_m_s,
        solar_radiation_mj_m2_day=solar_radiation_mj_m2_day,
        elevation_m=elevation_m,
    )


def residence_time(volume_m3: float, outflow_m3_day: float) -> float:
    """HRT = V/Q; returns inf when outflow is zero."""
    if outflow_m3_day <= 0.0:
        return float("inf")
    return volume_m3 / outflow_m3_day


def darcy_flux(
    hydraulic_conductivity_m_day: float,
    hydraulic_gradient: float,
    cross_sectional_area_m2: float,
) -> float:
    """Alias for darcy_groundwater_flux with standard argument name."""
    return darcy_groundwater_flux(
        hydraulic_conductivity_m_day=hydraulic_conductivity_m_day,
        hydraulic_gradient=hydraulic_gradient,
        area_m2=cross_sectional_area_m2,
    )


def water_balance(
    inflow_m3_day: float,
    outflow_m3_day: float,
    precipitation_m_day: float = 0.0,
    evapotranspiration_m_day: float = 0.0,
    surface_area_m2: float = 0.0,
    groundwater_flux_m3_day: float = 0.0,
    **_kwargs: float,
) -> float:
    """Return delta storage (m³/day) with m/day precipitation and ET inputs."""
    P_m3 = precipitation_m_day * surface_area_m2
    ET_m3 = evapotranspiration_m_day * surface_area_m2
    return inflow_m3_day + P_m3 + groundwater_flux_m3_day - outflow_m3_day - ET_m3
