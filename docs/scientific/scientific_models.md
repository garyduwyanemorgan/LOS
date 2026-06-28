# LOS Scientific Models

## Overview

LOS uses a hybrid scientific modelling approach:

1. **Pure-Python models** — fast, dependency-free calculations for continuous loop operation
2. **Engine wrappers** — optional wrappers for industry-standard simulation engines (MODFLOW, PHREEQC, HYDRUS)

Scientific models are authoritative. The AI Orchestrator reasons across their outputs — it never modifies their computations.

## Hydrological Models

### FAO-56 Penman-Monteith ET₀

Reference evapotranspiration for lagoon water balance.

```python
from backend.scientific_services.hydrological.calculations import penman_monteith_et0

et0 = penman_monteith_et0(
    temperature_c=38.0,
    relative_humidity_pct=55.0,
    wind_speed_m_s=4.0,
    solar_radiation_mj_m2_day=25.0,
    elevation_m=5.0,
)
# Returns: ET₀ in mm/day
```

**Reference**: Allen et al. (1998) FAO Irrigation and Drainage Paper 56.

### Water Balance

```
ΔS = Q_in + P·A + Q_gw − Q_out − ET₀·A
```

Where:
- `ΔS` = change in lagoon storage (m³/day)
- `Q_in` = surface inflow (m³/day, includes TSE)
- `P` = precipitation depth (m/day)
- `A` = surface area (m²)
- `Q_gw` = groundwater exchange (m³/day, positive = inflow)
- `Q_out` = surface outflow (m³/day)
- `ET₀` = reference evapotranspiration (m/day)

### Hydraulic Residence Time

```
τ = V / Q_out
```

Where `V` = lagoon volume (m³), `Q_out` = outflow rate (m³/day).

### Darcy's Law (Groundwater Flux)

```
Q = K · i · A
```

Where `K` = hydraulic conductivity (m/day), `i` = hydraulic gradient, `A` = cross-sectional area (m²).

## Chemical Models

### Dissolved Oxygen Saturation

Benson & Krause (1984) equations with salinity correction:

```
DO_sat = f(T, S)
```

Valid for: T ∈ [0, 45°C], S ∈ [0, 40 ppt].

### Redox Classification

| ORP (mV) | Classification |
|----------|---------------|
| > +200 | Oxic |
| 0 to +200 | Suboxic |
| -200 to 0 | Anoxic |
| < -200 | Reducing |

### Trophic State Index

Carlson-derived classification:

| Chlorophyll-a (μg/L) | State |
|---------------------|-------|
| < 2 | Oligotrophic |
| 2–8 | Mesotrophic |
| 8–25 | Eutrophic |
| > 25 | Hypereutrophic |

## Ecological Models

### Bloom Probability

Multi-factor risk model combining:
- Trophic state index (0–1)
- Hydraulic residence time score (0–1)
- DO deficit factor (0–1)
- Temperature factor (0–1)

```
P_bloom = 0.35·TSI + 0.25·HRT_factor + 0.20·DO_deficit + 0.20·temp_factor
```

### Cyanobacteria Competitive Advantage

Cyanobacteria win competitive dominance under:
- High temperature (> 25°C)
- Low N:P ratio (< 15:1 by mass)
- Thermal stratification
- Low turbulence

## External Engine Wrappers (Optional)

These wrappers require the respective simulation engines to be installed.
All wrappers check for engine availability and provide clear installation instructions.

| Wrapper | Engine | Purpose |
|---------|--------|---------|
| `modflow_wrapper.py` | MODFLOW 6 via FloPy | 3D groundwater flow + subsidence |
| `phreeqc_wrapper.py` | PHREEQC via PhreeqPy | Geochemical speciation, mixing |
| `hydrus_wrapper.py` | HYDRUS-1D via Phydrus | Vadose zone transport |

### MODFLOW 6 Wrapper

```python
from backend.scientific_models.hydrogeological.modflow_wrapper import ModflowWrapper

wrapper = ModflowWrapper(workspace_dir=Path("./models/modflow"))
if wrapper.is_available():
    model = wrapper.build(lagoon_config=config)
    result = wrapper.run(model)
    settlement = wrapper.post_process(result)
```

### PHREEQC Wrapper

```python
from backend.scientific_models.chemical.phreeqc_wrapper import PhreeqcWrapper

wrapper = PhreeqcWrapper()
if wrapper.is_available():
    result = wrapper.run_mixing(
        end_member_1=tse_chemistry,
        end_member_2=groundwater_chemistry,
        fractions=[0.3, 0.7],
    )
```
