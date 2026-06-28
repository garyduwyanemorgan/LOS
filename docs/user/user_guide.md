# Lagoons Operating System — User Guide

Version: 1.0 | Audience: Lagoon Operators and Environmental Managers

---

## Overview

The Lagoons Operating System (LOS) is an environmental monitoring and decision-support platform for lagoon management. It continuously monitors water quality, runs scientific models, and generates prioritised recommendations so operators can protect lagoon ecosystems and maintain regulatory compliance.

LOS does not automate physical interventions. It generates evidence-based recommendations that qualified operators review and action.

---

## 1. Accessing the Platform

Open your browser and navigate to the LOS URL provided by your administrator.

Log in with your email address and password. Organisations using Supabase authentication can also sign in with their organisation SSO provider.

Once logged in you will land on the **Lagoon Dashboard** for your assigned lagoon or portfolio.

---

## 2. Dashboard Overview

The main dashboard has four panels:

| Panel | Description |
|-------|-------------|
| **System State** | Current status of all five scientific loops |
| **Water Quality** | Real-time chemical parameters (DO, ORP, pH, salinity, nutrients) |
| **Ecological Health** | Bloom probability, trophic state, ecological stability score |
| **Active Recommendations** | Prioritised action list from the Decision Engine |

### Status Indicators

- **Green**: Parameter within acceptable range
- **Amber**: Parameter approaching threshold — monitor closely
- **Red**: Parameter breached threshold — action required

---

## 3. Reading the Scientific Loops

LOS runs five continuous scientific loops:

### Hydrological Loop
Tracks water balance (inflow, outflow, evaporation, groundwater flux), residence time, and hydraulic connectivity. Long residence times (>15 days) increase nutrient accumulation risk.

### Chemical Loop
Monitors dissolved oxygen (DO), oxidation-reduction potential (ORP), pH, salinity, conductivity, turbidity, and nutrients (TN, TP, NH₄⁺, NO₃⁻). The chemical loop classifies redox conditions and computes trophic state using Carlson TSI.

Key thresholds:
- **DO < 4 mg/L**: Warning — biological stress beginning
- **DO < 2 mg/L**: Critical — hypoxia, regulatory breach, immediate action required
- **ORP < −100 mV**: Anoxic conditions — high internal phosphorus loading risk

### Ecological Loop
Estimates algal bloom probability (0–1), dominant community type, and cyanobacteria risk. A bloom probability above 0.5 triggers enhanced monitoring recommendations.

### Infrastructure Loop
Tracks the operational status of aerators, pumps, sensors, and dosing systems. Equipment faults trigger maintenance recommendations immediately.

### Operational Loop
Aggregates all loop outputs into a single **Health Score** (0–100). Scores below 50 indicate the lagoon requires active intervention.

---

## 4. Working with Recommendations

### Understanding a Recommendation

Each recommendation shows:

- **Action**: What should be done (e.g., "Increase aeration rate by 30%")
- **Category**: Aeration / TSE Management / Circulation / Monitoring / Maintenance / Chemical Dosing / Dredging
- **Urgency**: Immediate / Urgent / Scheduled / Routine
- **Confidence**: How confident the system is in this recommendation (0–100%)
- **Scientific Evidence**: Which measurements and models support this recommendation
- **Operating Objectives**: Which of the 7 Operating Objectives this action advances
- **Expected Outcome**: What improvement is expected and over what timeframe

### Urgency Levels

| Level | Meaning | Expected Response |
|-------|---------|-------------------|
| **Immediate** | DO < 2 mg/L, equipment critical failure, or fish kill risk | Action within hours |
| **Urgent** | Conditions deteriorating, threshold approaching | Action within 24 hours |
| **Scheduled** | Preventive action beneficial, no immediate threat | Action within 1 week |
| **Routine** | Regular maintenance or monitoring | Action within normal schedule |

### Approving a Recommendation

1. Review the scientific evidence and rationale
2. Confirm the action is operationally feasible
3. Click **Approve** to record your decision
4. Note the recommended action in your operations log

### Declining a Recommendation

If you do not proceed with a recommendation:
1. Click **Decline** and select a reason
2. The system logs your decision and continues monitoring
3. If conditions worsen, the system will escalate the recommendation

Your approval and decline decisions feed into the LOS Learning Engine, which improves future recommendation accuracy over time.

---

## 5. Observations and Sensor Data

### Viewing Current Readings

The **Observations** panel shows the latest sensor readings for each monitored parameter. Click any parameter to see its time-series history.

Quality flags indicate data reliability:
- **Good**: Sensor operating normally, data validated
- **Suspect**: Data may be affected by calibration drift or fouling — verify before acting
- **Bad**: Sensor fault — data not used in scientific models
- **Missing**: No recent reading — the system notes reduced confidence

### Adding Manual Observations

When sensors are unavailable or for laboratory data:
1. Navigate to **Observations → Add Manual Reading**
2. Select the parameter, enter the value and unit
3. Set the source to **Laboratory** or **Manual**
4. Add the measurement timestamp
5. Submit

Manual observations are weighted equally with sensor data in the scientific models.

---

## 6. Reports

LOS generates four report types:

| Report | Contents | Audience |
|--------|----------|----------|
| **Executive** | Health score, key events, management summary | Management |
| **Scientific** | Full water quality analysis, model outputs, trend analysis | Technical staff |
| **Compliance** | Regulatory parameter status vs permit thresholds | Compliance officers |
| **Operational** | Equipment status, maintenance log, sensor coverage | Operations team |

### Generating a Report

1. Navigate to **Reports** for your lagoon
2. Select the report type
3. Choose the period (default: last 30 days)
4. Select format: **Markdown** (plain text) or **HTML** (formatted)
5. Click **Generate**

Reports are archived and can be retrieved from the report history.

---

## 7. Alerts and Notifications

LOS sends alerts when conditions breach thresholds or when a recommendation requires immediate action. Alerts are delivered via:
- In-app notifications (red bell icon, top right)
- Email (if configured by your administrator)

### Common Alerts

| Alert | Meaning |
|-------|---------|
| `DO_CRITICAL` | Dissolved oxygen below 2 mg/L |
| `BLOOM_RISK_HIGH` | Bloom probability above 0.6 |
| `AERATOR_FAULT` | Aerator offline or degraded |
| `NUTRIENT_LOADING_HIGH` | TP or TN above permit threshold |
| `RESIDENCE_TIME_ELEVATED` | Residence time above 15 days |
| `ORP_ANAEROBIC` | ORP below −100 mV — anoxic conditions |

---

## 8. Multi-Lagoon Portfolio View

If you manage multiple lagoons, the **Portfolio** page shows all lagoons at a glance with their current health scores and any active critical alerts.

Click any lagoon to drill into its full dashboard.

---

## 9. Understanding Confidence Scores

The LOS system communicates its scientific confidence at every level:

- **Observation confidence**: Quality of the raw sensor data
- **Loop confidence**: How complete and consistent the data is for each scientific loop
- **Recommendation confidence**: How strongly the scientific evidence supports the recommended action

A confidence of 70%+ indicates strong scientific basis. Below 50% means data is sparse — collect more observations before acting on that recommendation.

---

## 10. Frequently Asked Questions

**Q: Why does a recommendation change between cycles?**
The Decision Engine runs every 15–60 minutes (configurable). As new sensor data arrives and conditions evolve, recommendations update to reflect the current state.

**Q: Can the system automatically implement actions?**
No. LOS generates recommendations only. All physical interventions are performed by qualified operators. Automatic approval is disabled by default in all production deployments.

**Q: What happens if a sensor fails?**
LOS flags the sensor fault, marks affected observations as "bad", and reduces confidence for the impacted loop. The system continues to operate using the remaining available data. A maintenance recommendation is generated for the sensor repair.

**Q: How long is historical data retained?**
Observation data is retained indefinitely (subject to your organisation's data policy). Scientific state snapshots are retained for 12 months by default. Event bus replay windows are configurable (default: 7 days).

**Q: Who can I contact for support?**
Contact your system administrator or raise a support ticket at the address provided in your onboarding documentation.
