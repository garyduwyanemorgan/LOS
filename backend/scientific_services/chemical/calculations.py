"""Chemical calculations for lagoon water quality analysis."""
import math


class RedoxClass:
    OXIC = "oxic"         # ORP > 200 mV
    SUBOXIC = "suboxic"   # ORP 0–200 mV
    ANOXIC = "anoxic"     # ORP -200–0 mV
    REDUCING = "reducing"  # ORP < -200 mV


def redox_classification(orp_mv: float) -> str:
    """Classify redox state from ORP measurement."""
    if orp_mv > 200:
        return RedoxClass.OXIC
    elif orp_mv > 0:
        return RedoxClass.SUBOXIC
    elif orp_mv > -200:
        return RedoxClass.ANOXIC
    else:
        return RedoxClass.REDUCING


def do_saturation_percent(do_mg_l: float, temp_c: float, salinity_ppt: float = 0.0) -> float:
    """
    Dissolved oxygen saturation using Benson & Krause equations.

    DO_sat (mg/L) at given temperature and salinity, then compute % saturation.
    """
    T_K = temp_c + 273.15
    # Benson & Krause (1980/1984) coefficients for DO saturation in fresh water
    ln_do_sat = (
        -139.34411
        + 157570.1 / T_K
        - 66423080.0 / T_K**2
        + 12438000000.0 / T_K**3
        - 862194900000.0 / T_K**4
    )
    do_sat_fresh = math.exp(ln_do_sat)
    # Salinity correction — Garcia & Gordon (1992) simplified
    salinity_correction = math.exp(-salinity_ppt * 0.0117 / T_K)
    do_sat = do_sat_fresh * salinity_correction
    if do_sat <= 0.0:
        return 0.0
    return round((do_mg_l / do_sat) * 100.0, 1)


def internal_loading_risk(
    orp_mv: float,
    residence_time_days: float,
    tp_mg_l: float | None = None,
) -> str:
    """
    Assess internal phosphorus loading risk.

    Under reducing conditions (low ORP) + long residence time,
    iron-bound phosphorus is released from sediment.
    """
    risk_score = 0

    if orp_mv < -100:
        risk_score += 3
    elif orp_mv < 0:
        risk_score += 2
    elif orp_mv < 100:
        risk_score += 1

    if residence_time_days > 30:
        risk_score += 2
    elif residence_time_days > 14:
        risk_score += 1

    if tp_mg_l is not None and tp_mg_l > 0.1:
        risk_score += 1

    if risk_score >= 5:
        return "critical"
    elif risk_score >= 3:
        return "high"
    elif risk_score >= 1:
        return "medium"
    return "low"


def carbonate_system(ph: float, alkalinity_meq_l: float, temp_c: float = 25.0) -> dict:
    """
    Calculate carbonate system speciation.

    Returns: HCO3-, CO3²⁻, CO2(aq), TIC in mg/L and buffer capacity
    """
    T_K = temp_c + 273.15

    # Temperature-corrected pK values (Harned & Davis, 1943; Harned & Scholes, 1941)
    pK1 = 3404.71 / T_K + 0.032786 * T_K - 14.8435
    pK2 = 2902.39 / T_K + 0.02379 * T_K - 6.498

    K1 = 10.0 ** (-pK1)
    K2 = 10.0 ** (-pK2)
    Kw = 10.0 ** (-14.0)
    H = 10.0 ** (-ph)
    OH = Kw / H

    # ALK = [HCO3⁻] + 2[CO3²⁻] + [OH⁻] - [H⁺]
    # [CO3²⁻] = K2/H * [HCO3⁻]
    # ALK - OH + H = [HCO3⁻] * (1 + 2*K2/H)
    denominator = 1.0 + 2.0 * K2 / H
    net_alkalinity = alkalinity_meq_l / 1000.0 - OH + H  # mol/L
    HCO3_mol = net_alkalinity / denominator if denominator != 0.0 else 0.0
    CO3_mol = (K2 / H) * HCO3_mol
    CO2_mol = (H / K1) * HCO3_mol

    return {
        "HCO3_mg_l": max(0.0, HCO3_mol * 61030.0),   # MW HCO3⁻ = 61.03 g/mol
        "CO3_mg_l": max(0.0, CO3_mol * 60010.0),      # MW CO3²⁻ = 60.01
        "CO2_mg_l": max(0.0, CO2_mol * 44010.0),      # MW CO2 = 44.01
        "TIC_mg_l": max(0.0, (HCO3_mol + CO3_mol + CO2_mol) * 12011.0),  # as C
        "buffer_capacity": min(10.0, alkalinity_meq_l),
    }


def nutrient_trophic_state(
    tn_mg_l: float | None,
    tp_mg_l: float | None,
    chlorophyll_ug_l: float | None,
) -> str:
    """Carlson-derived trophic state index for nitrogen/phosphorus/chlorophyll."""
    score = 0
    count = 0

    if tp_mg_l is not None:
        if tp_mg_l > 0.1:
            score += 4
        elif tp_mg_l > 0.05:
            score += 3
        elif tp_mg_l > 0.02:
            score += 2
        elif tp_mg_l > 0.01:
            score += 1
        count += 1

    if tn_mg_l is not None:
        if tn_mg_l > 2.0:
            score += 4
        elif tn_mg_l > 1.0:
            score += 3
        elif tn_mg_l > 0.5:
            score += 2
        elif tn_mg_l > 0.2:
            score += 1
        count += 1

    if chlorophyll_ug_l is not None:
        if chlorophyll_ug_l > 50:
            score += 4
        elif chlorophyll_ug_l > 25:
            score += 3
        elif chlorophyll_ug_l > 10:
            score += 2
        elif chlorophyll_ug_l > 3:
            score += 1
        count += 1

    if count == 0:
        return "unknown"

    avg = score / count
    if avg >= 3.5:
        return "hypereutrophic"
    elif avg >= 2.5:
        return "eutrophic"
    elif avg >= 1.5:
        return "mesotrophic"
    return "oligotrophic"


def nitrogen_speciation(
    nh4_mg_l: float,
    ph: float,
    temp_c: float,
) -> dict[str, float]:
    """
    Compute NH4+/NH3 speciation.

    Free ammonia (NH3) is the toxic fraction.
    pKa of NH4+ is temperature-dependent.
    """
    T_K = temp_c + 273.15
    # pKa temperature correction (Emerson et al., 1975)
    pKa = 0.09018 + 2729.92 / T_K
    Ka = 10.0 ** (-pKa)
    H = 10.0 ** (-ph)
    # NH3 fraction = Ka / (Ka + H)
    nh3_fraction = Ka / (Ka + H)
    nh4_fraction = 1.0 - nh3_fraction
    total_ammoniacal_n = nh4_mg_l  # input is TAN (total ammoniacal nitrogen)
    return {
        "NH3_mg_l": round(total_ammoniacal_n * nh3_fraction, 4),
        "NH4_mg_l": round(total_ammoniacal_n * nh4_fraction, 4),
        "free_ammonia_fraction": round(nh3_fraction, 5),
        "toxic_threshold_exceeded": total_ammoniacal_n * nh3_fraction > 0.02,
    }


def solubility_product_check(
    ca_mg_l: float,
    co3_mg_l: float,
    temp_c: float = 25.0,
) -> dict[str, float]:
    """
    Check calcium carbonate saturation index (Langelier Saturation Index).

    LSI > 0 → scaling tendency; LSI < 0 → corrosive/dissolving.
    """
    T_K = temp_c + 273.15
    # pKsp calcite temperature correction (Plummer & Busenberg, 1982 simplified)
    pKsp = 171.9065 + 0.077993 * T_K - 2839.319 / T_K - 71.595 * math.log10(T_K)
    Ksp = 10.0 ** (-pKsp)

    # Molar concentrations
    Ca_mol = ca_mg_l / 40080.0   # MW Ca = 40.08 g/mol
    CO3_mol = co3_mg_l / 60010.0  # MW CO3²⁻ = 60.01

    ion_product = Ca_mol * CO3_mol
    saturation_ratio = 0.0 if ion_product <= 0.0 else ion_product / Ksp

    LSI = math.log10(saturation_ratio) if saturation_ratio > 0 else -10.0

    return {
        "LSI": round(LSI, 3),
        "saturation_ratio": round(saturation_ratio, 4),
        "tendency": "scaling" if LSI > 0 else ("dissolving" if LSI < -0.2 else "stable"),
        "Ksp": Ksp,
    }


# ── Simplified public aliases used by tests and external callers ──────────────

def classify_redox(orp_mv: float) -> str:
    """Alias for redox_classification with standard argument name."""
    return redox_classification(orp_mv=orp_mv)


def do_saturation(temperature_c: float, salinity_ppt: float = 0.0) -> float:
    """Return equilibrium DO concentration (mg/L) using Benson & Krause (1984)."""
    T_K = temperature_c + 273.15
    # Freshwater saturation (Benson & Krause 1980)
    ln_do_sat = (
        -139.34411
        + 157570.1 / T_K
        - 66423080.0 / T_K**2
        + 12438000000.0 / T_K**3
        - 862194900000.0 / T_K**4
    )
    do_sat_fresh = math.exp(ln_do_sat)
    # Salinity correction — Benson & Krause (1984) Eq. 3
    ln_correction = salinity_ppt * (
        -0.017674 + 10.754 / T_K - 2140.7 / T_K**2
    )
    return max(0.0, do_sat_fresh * math.exp(ln_correction))


def trophic_state_index(
    chlorophyll_a_ug_l: float | None = None,
    total_phosphorus_mg_l: float | None = None,
    total_nitrogen_mg_l: float | None = None,
) -> str:
    """Trophic state using Carlson TSI formulas (log-scale thresholds)."""
    tsi_values = []
    if chlorophyll_a_ug_l is not None and chlorophyll_a_ug_l > 0:
        tsi_chl = 9.81 * math.log(chlorophyll_a_ug_l) + 30.6
        tsi_values.append(tsi_chl)
    if total_phosphorus_mg_l is not None and total_phosphorus_mg_l > 0:
        tp_ug_l = total_phosphorus_mg_l * 1000.0
        tsi_tp = 14.42 * math.log(tp_ug_l) + 4.15
        tsi_values.append(tsi_tp)
    if not tsi_values:
        return "unknown"
    tsi = sum(tsi_values) / len(tsi_values)
    if tsi >= 70:
        return "hypereutrophic"
    elif tsi >= 50:
        return "eutrophic"
    elif tsi >= 30:
        return "mesotrophic"
    return "oligotrophic"
