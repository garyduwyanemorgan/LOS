"""
Ecological calculations for lagoon ecosystem health assessment.

Covers algal bloom probability, succession dynamics, stability scoring,
and recovery potential.
"""
from __future__ import annotations


def bloom_probability(
    tp_mg_l: float | None,
    tn_mg_l: float | None,
    residence_time_days: float | None,
    temp_c: float | None,
    do_mg_l: float | None,
    orp_mv: float | None,
) -> float:
    """
    Estimate probability of algal bloom occurrence (0–1).

    Weighted multi-parameter scoring:
      - High TP    weight 0.35
      - Long RT    weight 0.25
      - Warm temp  weight 0.20
      - Low DO     weight 0.20

    Returns a probability 0.0–1.0.
    """
    score = 0.0

    # ---- Total phosphorus (0–1, weight 0.35) ----
    if tp_mg_l is not None:
        if tp_mg_l >= 0.15:
            tp_score = 1.0
        elif tp_mg_l >= 0.05:
            # Linear between 0.05 and 0.15 mg/L
            tp_score = (tp_mg_l - 0.05) / 0.10
        else:
            tp_score = 0.0
        score += tp_score * 0.35

    # ---- Residence time (0–1, weight 0.25) ----
    if residence_time_days is not None:
        if residence_time_days >= 30:
            rt_score = 1.0
        elif residence_time_days >= 7:
            rt_score = (residence_time_days - 7.0) / 23.0
        else:
            rt_score = 0.0
        score += rt_score * 0.25

    # ---- Temperature (0–1, weight 0.20) ----
    if temp_c is not None:
        if temp_c >= 28:
            temp_score = 1.0
        elif temp_c >= 15:
            temp_score = (temp_c - 15.0) / 13.0
        else:
            temp_score = 0.0
        score += temp_score * 0.20

    # ---- Dissolved oxygen (0–1, weight 0.20) ----
    # Low DO contributes to bloom risk via internal P loading
    if do_mg_l is not None:
        if do_mg_l <= 2.0:
            do_score = 1.0
        elif do_mg_l <= 6.0:
            do_score = (6.0 - do_mg_l) / 4.0
        else:
            do_score = 0.0
        score += do_score * 0.20

    # Scale up if all factors are present
    weights_used = (
        (0.35 if tp_mg_l is not None else 0.0)
        + (0.25 if residence_time_days is not None else 0.0)
        + (0.20 if temp_c is not None else 0.0)
        + (0.20 if do_mg_l is not None else 0.0)
    )
    if 0.0 < weights_used < 1.0:
        # Normalize to available information
        score = score / weights_used

    # ORP bonus — strongly reducing conditions raise bloom probability
    if orp_mv is not None and orp_mv < -100:
        score = min(score + 0.1, 1.0)

    # TN:TP ratio — low N:P favours cyanobacteria (bloom-forming)
    if tn_mg_l is not None and tp_mg_l is not None and tp_mg_l > 0:
        np_ratio = tn_mg_l / tp_mg_l
        if np_ratio < 10:
            score = min(score + 0.08, 1.0)

    return round(min(max(score, 0.0), 1.0), 3)


def cyanobacteria_competitive_advantage(
    temp_c: float | None,
    n_p_ratio: float | None,
    do_mg_l: float | None,
) -> float:
    """
    Estimate cyanobacteria competitive advantage over other phytoplankton (0–1).

    Cyanos win when:
      - temp > 25 °C (optimal growth)
      - N:P < 10 by mass (N limitation favours N-fixers)
      - DO < 5 mg/L (tolerance of low oxygen)

    Returns competitive advantage 0.0–1.0.
    """
    score = 0.0
    weight_total = 0.0

    if temp_c is not None:
        if temp_c > 30:
            t_score = 1.0
        elif temp_c > 25:
            t_score = (temp_c - 25.0) / 5.0
        elif temp_c > 15:
            t_score = 0.2
        else:
            t_score = 0.0
        score += t_score * 0.40
        weight_total += 0.40

    if n_p_ratio is not None:
        if n_p_ratio < 5:
            np_score = 1.0
        elif n_p_ratio < 10:
            np_score = (10.0 - n_p_ratio) / 5.0
        elif n_p_ratio < 16:
            np_score = 0.1  # near Redfield ratio — moderate advantage
        else:
            np_score = 0.0
        score += np_score * 0.35
        weight_total += 0.35

    if do_mg_l is not None:
        if do_mg_l < 2:
            do_score = 1.0
        elif do_mg_l < 5:
            do_score = (5.0 - do_mg_l) / 3.0
        else:
            do_score = 0.0
        score += do_score * 0.25
        weight_total += 0.25

    if weight_total == 0.0:
        return 0.0
    normalized = score / weight_total
    return round(min(max(normalized, 0.0), 1.0), 3)


def succession_stage(
    bloom_probability: float,
    do_mg_l: float | None,
    historical_bloom_count: int = 0,
) -> str:
    """
    Determine current ecological succession stage.

    Stages (in order of deterioration):
      stable_diatoms    — well-mixed, good DO, low bloom risk
      green_algae_phase — moderate nutrients, greening
      cyanobacteria_risk— conditions favour cyanobacteria
      active_bloom      — bloom underway
      post_bloom_collapse — DO crash, fish kill risk

    Returns one of the five stage strings.
    """
    # Post-bloom collapse: very low DO regardless of bloom probability
    if do_mg_l is not None and do_mg_l < 1.5:
        return "post_bloom_collapse"

    # Active bloom: high probability + evidence from history
    if bloom_probability >= 0.75 and (historical_bloom_count > 0 or do_mg_l is None):
        return "active_bloom"

    if bloom_probability >= 0.75:
        return "active_bloom"

    # Cyanobacteria risk zone
    if bloom_probability >= 0.50:
        if do_mg_l is not None and do_mg_l < 4.0:
            return "cyanobacteria_risk"
        return "cyanobacteria_risk"

    # Green algae phase
    if bloom_probability >= 0.25:
        return "green_algae_phase"

    # Stable diatom community
    return "stable_diatoms"


def ecological_stability_score(
    bloom_prob: float,
    do_saturation: float | None,
    trophic_state: str | None,
    succession: str,
) -> float:
    """
    Compute ecological stability score (0 = unstable / degraded, 1 = stable / healthy).

    Lower score = more degraded ecosystem.
    """
    score = 1.0

    # Bloom probability penalty
    score -= bloom_prob * 0.35

    # DO saturation penalty
    if do_saturation is not None:
        if do_saturation < 30:
            score -= 0.30
        elif do_saturation < 60:
            score -= 0.15
        elif do_saturation < 80:
            score -= 0.05

    # Trophic state penalty
    trophic_penalties = {
        "hypereutrophic": 0.25,
        "eutrophic": 0.15,
        "mesotrophic": 0.05,
        "oligotrophic": 0.0,
        "unknown": 0.0,
    }
    score -= trophic_penalties.get(trophic_state or "unknown", 0.0)

    # Succession stage penalty
    succession_penalties = {
        "stable_diatoms": 0.0,
        "green_algae_phase": 0.05,
        "cyanobacteria_risk": 0.10,
        "active_bloom": 0.20,
        "post_bloom_collapse": 0.30,
    }
    score -= succession_penalties.get(succession, 0.0)

    return round(min(max(score, 0.0), 1.0), 3)


def recovery_potential(
    do_mg_l: float | None,
    orp_mv: float | None,
    bloom_probability: float,
    residence_time_days: float | None,
) -> str:
    """
    Assess ecosystem recovery potential given current conditions.

    Returns: "high", "medium", or "low"
    """
    score = 0

    # Good DO → strong recovery capacity
    if do_mg_l is not None:
        if do_mg_l > 7.0:
            score += 3
        elif do_mg_l > 4.0:
            score += 2
        elif do_mg_l > 2.0:
            score += 1

    # Positive ORP → aerobic respiration active
    if orp_mv is not None:
        if orp_mv > 200:
            score += 2
        elif orp_mv > 50:
            score += 1
        elif orp_mv < -100:
            score -= 1

    # Low bloom probability → less ecological pressure
    if bloom_probability < 0.25:
        score += 2
    elif bloom_probability < 0.5:
        score += 1
    elif bloom_probability > 0.75:
        score -= 2

    # Short residence time aids recovery via dilution/flushing
    if residence_time_days is not None:
        if residence_time_days < 7:
            score += 2
        elif residence_time_days < 14:
            score += 1
        elif residence_time_days > 30:
            score -= 1

    if score >= 5:
        return "high"
    elif score >= 2:
        return "medium"
    return "low"


def macrophyte_index(
    total_cover_pct: float,
    native_species_fraction: float,
    submerged_fraction: float,
) -> float:
    """
    Compute macrophyte ecological quality index (0–1).

    High cover of native submerged macrophytes = high quality.
    """
    cover_score = min(total_cover_pct / 60.0, 1.0)  # 60% cover = ideal
    native_score = native_species_fraction
    submerged_score = submerged_fraction  # submerged > floating > emergent for water quality

    index = cover_score * 0.40 + native_score * 0.35 + submerged_score * 0.25
    return round(min(max(index, 0.0), 1.0), 3)
