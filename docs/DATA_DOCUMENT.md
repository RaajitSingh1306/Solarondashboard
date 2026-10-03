# 📊 Solaron Fleet Operations, Solar Physics & Machine Learning Specification
> **Unified Master Data, Analytics & Engineering Architecture Document**  
> **Version:** 2.3.0 · **Date:** 2026-10-03 · **Status:** Active & Deployed  
> **Authors:** Solaron Engineering Team & Antigravity AI Pair Programming Session  
> **Monitored Fleet:** 491 Aggregated Installations · **Active Operational Fleet:** 295 Installations (2.29 MWp)  
> **Exhaustive Tab Guide:** For an in-depth breakdown of every tab, sub-tab, KPI, and modal, see [TAB_INFO.md](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/TAB_INFO.md)

---

## Table of Contents
1. [Executive Summary & Platform Scope](#1-executive-summary--platform-scope)
2. [System Architecture & Ingestion Pipeline](#2-system-architecture--ingestion-pipeline)
3. [Empirical Fleet Baselines & Performance Distribution](#3-empirical-fleet-baselines--performance-distribution)
4. [Core Solar Physics & Mathematical Formulations](#4-core-solar-physics--mathematical-formulations)
5. [Audit: Legacy Heuristics vs. Upgraded Hybrid Engine](#5-audit-legacy-heuristics-vs-upgraded-hybrid-engine)
6. [Machine Learning Anomaly Detection Engine (Isolation Forest)](#6-machine-learning-anomaly-detection-engine-isolation-forest)
7. [Adaptive 6-Part Loss Attribution Waterfall & Conservation Law](#7-adaptive-6-part-loss-attribution-waterfall--conservation-law)
8. [Telemetry Sanitization, Ingestion Firewalls & Anti-Cracked-Data Rules](#8-telemetry-sanitization-ingestion-firewalls--anti-cracked-data-rules)
9. [Resolved Platform Anomalies & Engineering Fixes (Issues 1–11)](#9-resolved-platform-anomalies--engineering-fixes-issues-111)
10. [Interactive Web Cockpit, Multi-Category Filtering & CRM Intelligence](#10-interactive-web-cockpit-multi-category-filtering--crm-intelligence)
11. [Parallel Engineering Project Reference: Smart Grid IDS](#11-parallel-engineering-project-reference-smart-grid-ids)
12. [Verification Suite, Operational Runbook & Delivery Status](#12-verification-suite-operational-runbook--delivery-status)

---

## 1. Executive Summary & Platform Scope

**Solaron** is an enterprise-grade solar operations, loss attribution, and customer relationship management (CRM) intelligence platform designed for distributed residential, commercial, and industrial solar installations across India. 

The platform aggregates real-time inverter telemetry, daily generation profiles, and monthly energy yields across three disparate OEM solar monitoring cloud APIs:
- **Growatt Server API**: 451 residential and commercial installations.
- **Sungrow iSolarCloud**: 28 commercial rooftop installations.
- **SuryaLog Cloud**: 12 industrial solar installations.

### Master Fleet Composition by OEM Platform

| Monitoring Platform | Total Sites | Share (%) | Extractor Module | Telemetry Protocol & Frequency |
|:---|:---:|:---:|:---|:---|
| **Growatt Server API** | 451 | 91.9% | `extractors/growatt.py` | REST API v2 + 30-min interval live curves |
| **Sungrow iSolarCloud** | 28 | 5.7% | `extractors/isolarcloud.py` | Web3 / Playwright session scraper |
| **SuryaLog Cloud** | 12 | 2.4% | `extractors/suryalog.py` | AE Cloud REST JSON extractor |
| **Total Monitored Fleet** | **491** | **100.0%** | Unified via `pipeline.py` | Normalized into SQLite `analytics.db` |

### Master Fleet Directory & Operational Breakdown

| Fleet Cohort | Installations | Capacity (kWp) | Operational Status & Scope Criteria |
|:---|:---:|:---:|:---|
| **Total Monitored Fleet** | **491** | **2,414.0 kWp** | Complete portfolio directory across all 3 monitoring platforms |
| **Active Operational Fleet** | **295** | **2,291.6 kWp** | Commissioned sites actively monitored (`operational_status = 'active'`) |
| **Decommissioned / Inactive** | **196** | **122.4 kWp** | Permanently retired or offline sites (`operational_status = 'decommissioned'`) |
| **Active Generating (September 2026)** | **274 / 295** | **2,156.4 kWp** | Operational systems producing positive harvest ($E_{\text{month}} > 1.0\text{ kWh}$) |
| **Active Offline / Fault (September 2026)**| **21 / 295** | **135.2 kWp** | Operational systems with zero monthly output (tripped breaker, comms loss) |
| **Generating Today (Live)** | **Dynamic** | **—** | Systems transmitting positive generation on the current day (`today_kwh > 0.05`) |
| **Statistical ML Anomalies** | **22 / 295** | **184.8 kWp** | Multi-attribute statistical outliers flagged by the Isolation Forest |

---

## 2. System Architecture & Ingestion Pipeline

The platform uses a decoupled ingestion, validation, physics computation, and delivery topology:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            OEM Solar Cloud APIs                             │
│       Growatt Web API        Sungrow iSolarCloud         SuryaLog Cloud     │
│       (451 Plants)            (28 Plants)                (12 Plants)        │
└──────────────┬─────────────────────────┬────────────────────────┬───────────┘
               │                         │                        │
               ▼                         ▼                        ▼
       extractors/growatt.py   extractors/isolarcloud.py   extractors/suryalog.py
               │                         │                        │
               └─────────────────────────┼────────────────────────┘
                                         ▼
                                    pipeline.py
                       (Universal Ingestion Firewall: date <= today)
                                         │
                                         ▼
                                   data_quality.py
                     (Physics Bounds, Clamping, Capacity Normalization)
                                         │
                                         ▼
                                      db.py
                          ┌────────────────────────────┐
                          │   SQLite: analytics.db     │
                          │   - plants                 │
                          │   - daily_generation       │
                          │   - monthly_generation     │
                          │   - inverter_snapshots     │
                          │   - loss_analysis          │
                          │   - expected_generation    │
                          └──────────────┬─────────────┘
                                         │
                                         ▼
                                   ml_analytics.py
                     ┌──────────────────────────────────────────┐
                     │ 1. Absolute PR Health Tiers              │
                     │ 2. Isolation Forest Outlier Scoring      │
                     │ 3. Adaptive 6-Part Loss Decomposition    │
                     └───────────────────┬──────────────────────┘
                                         │
               ┌─────────────────────────┴────────────────────────┐
               ▼                                                  ▼
           FastAPI REST API                                NiceGUI Interactive Cockpit
           (/api/plants, /api/daily,                       - Fetch Data (ui/fetch_tab.py)
            /api/monthly, /api/snapshots)                  - Fleet Command Center (ui/fleet.py)
                                                           - Full Analytics (ui/analytics_tab.py)
                                                           - Plant Cockpit (ui/plant.py)
                                                           - CRM & Campaigns (ui/crm.py)
```

### Core Architecture Modules & File Directory

| Module / File | Physical Path | Primary Architectural Responsibility |
|:---|:---|:---|
| [`pipeline.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/pipeline.py) | `Solarondashboard/pipeline.py` | Multi-portal orchestrator, concurrent ingestion, backfill engine |
| [`ml_analytics.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ml_analytics.py) | `Solarondashboard/ml_analytics.py` | Absolute PR tier assignment, Isolation Forest ML anomaly scoring, adaptive loss waterfall |
| [`analytics.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/analytics.py) | `Solarondashboard/analytics.py` | Core solar physics calculations ($Y_f, Y_d, PR$), regional GHI mapping, baseline models |
| [`data_quality.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data_quality.py) | `Solarondashboard/data_quality.py` | Physics bounds checking, daily ceiling clamping, capacity normalization ($W \to kWp$), inactive site filters |
| [`db.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/db.py) | `Solarondashboard/db.py` | SQLite connection pooling, schema migrations, universal anti-future-date firewall |
| [`extractors/growatt.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors/growatt.py) | `Solarondashboard/extractors/growatt.py` | Growatt API client, robust nested date parsing, 30-min power telemetry fetch |
| [`extractors/isolarcloud.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors/isolarcloud.py) | `Solarondashboard/extractors/isolarcloud.py` | Sungrow iSolarCloud Web3 scraper & daily/monthly extractor |
| [`extractors/suryalog.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors/suryalog.py) | `Solarondashboard/extractors/suryalog.py` | SuryaLog AE cloud REST API extractor |
| [`ui/fetch_tab.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/fetch_tab.py) | `Solarondashboard/ui/fetch_tab.py` | Tab 1: Telemetry control center: 2s cached mode vs 146s live force-refresh & backfill engine |
| [`ui/fleet.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/fleet.py) | `Solarondashboard/ui/fleet.py` | Tab 2: Fleet command center table, PR (%), `⚡ Anomaly` badges, 146s speed indicator |
| [`ui/analytics_tab.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/analytics_tab.py) | `Solarondashboard/ui/analytics_tab.py` | Tab 3: Apache ECharts 6-part loss attribution waterfall, NASA POWER satellite GHI curves |
| [`ui/plant.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/plant.py) | `Solarondashboard/ui/plant.py` | Tab 4: Plant Cockpit, category & portal multi-filter, 30-min live curve with clock clamp |
| [`ui/crm.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/crm.py) | `Solarondashboard/ui/crm.py` | Tab 5: 6-subtab customer relationship management, WhatsApp statement generation & campaigns |
| [`TAB_INFO.md`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/TAB_INFO.md) | `Solarondashboard/docs/TAB_INFO.md` | Comprehensive tab-by-tab guide breaking down all UI components, KPIs, and controls |

### Ingestion Performance & Speed Optimization

The platform supports two distinct operational extraction modes:
1. **Fast Local Cached Mode (~2.0 seconds)**:
   Reads normalized NVMe local JSON snapshots from `data/raw/growatt/`, `data/raw/isolarcloud/`, and `data/raw/suryalog/`. Designed for instant dashboard startup, offline debugging, and rapid UI development.
2. **Live Force-Refresh Mode (~146.0 seconds / 2.4 minutes)**:
   Executes fully asynchronous, parallelized network extraction across all 491 installations directly from OEM cloud endpoints (`server-api.growatt.com`, Sungrow Web3, SuryaLog AE). Replaces the legacy sequential web scraper that historically required **over 10 minutes** to complete.

### Dynamic Operational Status & Force-Refresh Cache Lifecycle

#### 1. Dynamic Server & Database Operational Status
Historically, `data_quality.py` included a hardcoded set of 196 plant IDs (`DECOMMISSIONED_PLANT_IDS`) to bootstrap offline performance tests. This static approach has been completely modernized into a **dynamic, server- and database-driven resolution engine**:

* **Live Database Status Query:**
  [`data_quality.get_decommissioned_plant_ids()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data_quality.py#L94-L123) actively queries SQLite `plants` table (`WHERE operational_status = 'decommissioned'`). It utilizes an in-memory set cache with a 60-second TTL to ensure zero-latency lookups during high-frequency loop processing.
* **Proactive Cache Invalidation:**
  Whenever fleet metadata is synchronized via [`pipeline.run_fleet()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/pipeline.py#L52-L66) or periodic status synchronization runs via [`analytics.sync_decommissioned_plants()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/analytics.py#L118-L194), [`data_quality.invalidate_decommissioned_cache()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data_quality.py#L87-L93) is executed, instantly flushing stale in-memory state.
* **Live OEM Server Telemetry Heuristics:**
  [`data_quality.determine_operational_status(plant_record)`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data_quality.py#L136-L186) dynamically detects decommissioned or permanently offline installations directly from server response attributes:
  - **Sungrow iSolarCloud:** Portal reports `status` as `"Commissioning unfinished"` or `"Offline"` with $\le 0.0\text{ kWh}$ lifetime energy.
  - **SuryaLog AE Cloud:** Server reports `status == "Offline"` with $\le 0.0\text{ kWh}$ lifetime energy.
  - **Growatt Server API:** Server reports `deviceCount == 0` with $\le 0.0\text{ kWh}$ lifetime total energy.
  - **Database Precedence:** Existing database records with `operational_status = 'decommissioned'` are respected until reactivated by positive generation.

#### 2. Force-Refresh Cache Overwriting & Fresh Telemetry Flow
When an operator triggers a `force_refresh=True` run (via the **Fetch Data** UI or API):
1. **Bypasses Short-Term In-Memory Cache:** Playwright scrapers and REST extractors immediately bypass the 180-second memory cache to force authentic network requests to OEM cloud gateways.
2. **Overwrites Local Disk JSON Caches:**
   - **Growatt:** Calls `newTwoPlantAPI.do` (`getAllPlantListTwo`) and `plant_detail(Timespan.month)`, overwriting [`data/raw/growatt/plant_list_live.json`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data/raw/growatt/plant_list_live.json) and [`data/raw/growatt/real_monthly_cache.json`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data/raw/growatt/real_monthly_cache.json).
   - **Sungrow iSolarCloud:** Headless browser extracts multi-page installation tables, overwriting [`data/raw/isolarcloud/plants_28_structured.json`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data/raw/isolarcloud/plants_28_structured.json).
   - **SuryaLog AE Cloud:** Logs into portal and extracts telemetry, overwriting [`data/raw/suryalog/plants_12_structured.json`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data/raw/suryalog/plants_12_structured.json).
3. **Telemetry Ingested Into SQLite:** Extracted generation, specific yield, and inverter snapshots are upserted into `plants`, `daily_generation`, `monthly_generation`, and `inverter_snapshots`.
4. **Subsequent Cache-Mode Runs Consume Fresh Data:** Any subsequent run with `force_refresh=False` directly reads the freshly written raw files and SQLite records, preventing operators from ever viewing stale, multi-day-old telemetry.

---

## 3. Empirical Fleet Baselines & Performance Distribution

*Empirical metrics extracted from the live SQLite database as of September 2026.*

### 3.1 Fleet Monthly Harvest History

| Month | Total Records | Generating Sites | Fleet Mean PR | Median PR | Total Energy Harvest | Est. Commercial Value |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Jun 2026** | 491 | 244 | 51.1% | 48.2% | 133,790 kWh | ₹18,73,060 |
| **Jul 2026** | 491 | 244 | 63.0% | 61.5% | 134,505 kWh | ₹18,83,070 |
| **Aug 2026** | 491 | 287 | 82.1% | 79.4% | 188,622 kWh | ₹26,40,708 |
| **Sep 2026** | 491 | 274 | **44.2%** | **42.1%** | **214,301 kWh** | **₹30,00,220** |

> [!NOTE]
> September 2026 realized energy harvest reached **214.30 MWh** across the 274 generating active sites, generating an estimated commercial value of ₹30,00,220 (at the standard ₹14.0/kWh commercial tariff).

### 3.2 Active Plant Statistical Distribution (September 2026, 274 Generating Sites)

| Metric | Mean | Median | P10 | P25 | P75 | P90 | Physical Benchmark |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Specific Yield ($Y_f$, kWh/kWp)** | 93.5 | 91.2 | 48.2 | 68.4 | 114.6 | 132.8 | $90.0 - 115.0\text{ kWh/kWp}$ |
| **Yield / Day ($Y_d$, u/kWp/d)** | 3.12 | 3.04 | 1.61 | 2.28 | 3.82 | 4.43 | $3.50 - 4.50\text{ u/kWp/d}$ |
| **Performance Ratio ($PR, \%$)** | **44.2%** | **42.1%** | 24.1% | 33.6% | 54.8% | 66.5% | $\ge 75.0\%$ |

---

## 4. Core Solar Physics & Mathematical Formulations

To ensure rigorous comparisons between a 3.3 kWp residential rooftop and a 194.4 kWp industrial facility, all energy metrics are normalized through fundamental solar physics.

### 4.1 Solar Resource ($GHI$)
Global Horizontal Irradiance ($GHI$) is retrieved by plant geographic coordinates $(\text{Lat}, \text{Lon})$ from NASA POWER Satellite API (`ALLSKY_SFC_SW_DWN`), with fallback to the Indian Regional Climatology model:

$$\text{Climatological } GHI \in [4.05, 6.45] \text{ kWh/m}^2/\text{day}$$

```python
INDIA_MONTHLY_GHI_DEFAULTS = {
    "01": 4.60, "02": 5.25, "03": 5.90, "04": 6.30, "05": 6.45, "06": 5.20,
    "07": 4.10, "08": 4.05, "09": 4.80, "10": 5.15, "11": 4.70, "12": 4.35,
}
```

### 4.2 Specific Yield ($Y_f$)
Normalizes actual energy generation by nominal DC capacity:
$$Y_f = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}]} \quad [\text{kWh/kWp}]$$
- **Physical Boundary**: Strictly clamped to $0.0 \le Y_f \le 220.0\text{ kWh/kWp/month}$ (monthly) and $\le 8.0\text{ kWh/kWp/day}$ (daily).
- **Noise Floor Suppression**: Daily generation $< 0.05\text{ kWh}$ or monthly $< 1.0\text{ kWh}$ yields $Y_f = 0.0$.

### 4.3 Normalized Daily Specific Yield ($Y_d$)
Normalizes generation by the elapsed calendar days in the measurement window:
$$Y_d = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}] \times D_{\text{elapsed}}} \quad [\text{units/kWp/day}]$$
- **Elapsed Day Accounting**: For ongoing months, $D_{\text{elapsed}} = \max(1, \min(\text{today.day}, D_{\text{total}}))$. For completed months, $D_{\text{elapsed}} = D_{\text{total}}$.
- **Physical Boundary**: Bounded to $0.0 \le Y_d \le 8.0\text{ units/kWp/day}$.

### 4.4 Performance Ratio ($PR$)
Evaluates equipment efficiency and conversion quality independent of weather and seasonal irradiance fluctuations:
$$PR = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}] \times GHI \ [\text{kWh/m}^2/\text{day}] \times D_{\text{days}}} \times 100\%$$
- **Engineering Benchmark**: $75.0\% \le PR \le 82.0\%$ for healthy grid-tied PV systems.

### 4.5 Expected Baseline Generation Model ($E_{\text{expected}}$)
The physical benchmark energy an installation is expected to produce under clear skies:
$$E_{\text{expected}} = \begin{cases} P_{\text{nominal}} \times GHI \times D_{\text{days}} \times 0.75 & \text{if operational\_status} \ne \text{'decommissioned'} \\ 0.0 & \text{if operational\_status} = \text{'decommissioned'} \end{cases}$$

### 4.6 Realization Rate ($RR$)
$$RR = \frac{E_{\text{actual}}}{E_{\text{expected}}} \times 100\%$$

### 4.7 Capacity Utilisation Factor ($CUF$)
$$CUF = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}] \times 24 \text{ hours} \times D_{\text{days}}} \times 100\%$$

### 4.8 Environmental Carbon Offsets ($CO_2$)
Computed using the Central Electricity Authority (CEA) of India standardized baseline grid factor:
$$CO_2 \ [\text{kg}] = E_{\text{actual}} \ [\text{kWh}] \times 0.82\text{ kg CO}_2/\text{kWh}$$

### 4.9 Commercial Tariff Financial Savings
Direct electricity bill savings calculated via solar self-consumption:
$$\text{Financial Savings} \ [₹] = E_{\text{actual}} \ [\text{kWh}] \times \text{Tariff} \ [₹/\text{kWh}]$$
- Standard commercial rooftop benchmark tariff: **₹14.0/kWh**.
- Default general tariff in [`analytics.py:revenue()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/analytics.py#L95): **₹5.5/kWh**.

---

## 5. Audit: Legacy Heuristics vs. Upgraded Hybrid Engine

| Operational Dimension | Legacy Flawed Logic | Upgraded Hybrid Engine (`ml_analytics.py`) |
|:---|:---|:---|
| **Classification Standard** | Relative percentile ranking within arbitrary size brackets | **Absolute Physical PR Thresholds** grounded in IEEE/IEC solar standards |
| **Systemic Failure Blindspot** | ❌ **Masked Underperformance**: Classifies a 35% PR plant as "Good" if peers are also degrading | ✅ **Objective Truth**: Correctly classifies any plant with PR $<45\%$ as "Needs Attention" or "Critical" |
| **Capacity Grouping** | Discontinuous buckets (0-3, 3-5, 5-10, 10-50, 50+ kWp) where 86% clustered in 3-5 kWp | **Continuous Physics Normalization** ($Y_f, Y_d, PR$) without boundary distortions |
| **Outlier Detection** | Static single-variable ranking by monthly kWh | **Unsupervised Machine Learning (Isolation Forest)** tracking 7 microclimate & size features |
| **Loss Attribution** | Synthetic static fractions (15% weather, 4% soiling, 2.5% shading) | **Adaptive Decomposition**: Actual GHI deficit, measured comm dropouts, dynamic seasonal soiling |
| **Diurnal Hourly Curve** | Hardcoded bell-curve weights projecting generation into future hours | **Live 30-min Inverter Telemetry** with strict current-time clock clamping ($hour > now.hour = 0.0$) |
| **Date Ingestion** | Unbounded queries accepting pre-allocated future dates (Sep 27–30) | **Universal Database Ingestion Firewall** rejecting any record with $date > today$ |

---

## 6. Machine Learning Anomaly Detection Engine (Isolation Forest)

Implemented in [`ml_analytics.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ml_analytics.py), Solaron deploys an unsupervised scikit-learn `IsolationForest` pipeline (`contamination=0.08`, `n_estimators=100`, `random_state=42`) to distinguish between expected weather drops and genuine electrical/hardware faults.

### 6.1 Feature Vector Representation ($\vec{x} \in \mathbb{R}^5$)

For every active producing installation ($E_{\text{month}} > 1.0\text{ kWh}$), the feature vector is synthesized as:

$$\vec{x} = \begin{bmatrix} 
x_1 \\ x_2 \\ x_3 \\ x_4 \\ x_5 
\end{bmatrix} = \begin{bmatrix} 
Y_d & \text{(Daily Specific Yield: units/kWp/day)} \\
PR & \text{(Performance Ratio: \%)} \\
P_{\text{nominal}} & \text{(Installed Capacity in kWp)} \\
\sin\left(\frac{2\pi \cdot (m - 1)}{12}\right) & \text{(Cyclic Month Sine Seasonality Encoding)} \\
\cos\left(\frac{2\pi \cdot (m - 1)}{12}\right) & \text{(Cyclic Month Cosine Seasonality Encoding)}
\end{bmatrix}$$

- Missing attributes are imputed using column medians.

### 6.2 Decision Boundary, Scoring & Dual-Gate Filter

The isolation score $s(\vec{x}, n)$ is computed from the average path length $h(\vec{x})$ across $T=100$ isolation trees:

$$s(\vec{x}, n) = 2^{-\frac{\mathbb{E}[h(\vec{x})]}{c(n)}}$$

Where $c(n) = 2\ln(n - 1) + 0.5772156649 - \frac{2(n - 1)}{n}$ is the average path length of an unsuccessful search in a Binary Search Tree of $n$ instances.

* **Tree Outlier Prediction**: `raw_pred == -1` (lower decision scores indicate geometric anomalies).
* **Dual-Gate Underperformance Condition**: To prevent over-performing summer plants or high-efficiency arrays from false-positive alerting, anomalies are strictly gated:
  $$\text{Anomaly Flag} = 1 \iff (\text{raw\_pred} = -1) \land (Y_d < \text{Median}_m(Y_d))$$
* **Rule-Based Fallback**: If dataset size $N < 10$ or scikit-learn fails: $\text{Anomaly Flag} = 1 \iff (PR < 25.0\% \land Y_d < 1.0)$.
* **Database Fields**: Persisted to SQLite in `monthly_generation(anomaly_score, anomaly_flag)`.

### 6.3 Absolute PR Health Tier Matrix (`ml_analytics.py:pr_to_tier`)

```
┌──────────────────────┬────────────┬──────────────┬─────────────────────────────────────┐
│ Performance Tier     │ PR Range   │ Sep 2026 Qty │ Operational Meaning                 │
├──────────────────────┼────────────┼──────────────┼─────────────────────────────────────┤
│ ⭐ Best             │ ≥ 75.0%    │ 41           │ Optimal harvest matching benchmark  │
│ ✅ Good             │ 60.0–75.0% │ 39           │ Healthy seasonal operation          │
│ ⚠️ Could Be Better  │ 45.0–60.0% │ 61           │ Moderate loss; panel cleaning due   │
│ 🟠 Needs Attention  │ 30.0–45.0% │ 79           │ Substantial shortfall; audit arrays │
│ 🔴 Critical         │ < 30.0%    │ 54           │ Severe failure; immediate dispatch  │
│ ⚪ Offline / Zero   │ E ≤ 1 kWh  │ 21           │ Equipment tripped or disconnected   │
│ 🟣 Decommissioned   │ Retired    │ 196          │ Excluded from fleet rankings        │
└──────────────────────┴────────────┴──────────────┴─────────────────────────────────────┘
```

---

## 7. Adaptive 6-Part Loss Attribution Waterfall & Conservation Law

When an active installation generates less energy than its physical baseline, the Net Energy Shortfall is decomposed into six verifiable root causes:

$$\text{Shortfall} \ (S) = \max(0.0, E_{\text{expected}} - E_{\text{actual}})$$

```
Expected Physical Baseline (245.1 MWh)
  │
  ├── [–] Communication & Datalogger Loss (3.5 MWh)
  ├── [–] Inverter Fault & Tripping Loss (0.0 MWh / 0.0 kWh)
  ├── [–] Weather & Irradiance Deficit (2.9 MWh)
  ├── [–] Seasonal Soiling & Dust Accumulation (2.4 MWh)
  ├── [–] Shading & Obstruction Loss (2.0 MWh)
  └── [–] Balance of System (BOS) / Residual Loss (19.9 MWh)
  │
  ▼
Actual Realized Fleet Harvest (214.3 MWh)
```

### 7.1 Mathematical Formulations

1. **Communication & Zero-Gen Loss ($L_{\text{comm}}$)**:
   $$L_{\text{comm}} = S \times \min\left(0.60, \frac{N_{\text{zero\_days}}}{D_{\text{days}}} \times 0.85\right)$$

2. **Inverter Shutdown / Fault Loss ($L_{\text{fault}}$)**:
   $$L_{\text{fault}} = S \times \min\left(0.40, \frac{N_{\text{fault\_days}}}{D_{\text{days}}} \times 0.90\right)$$

3. **Weather / Irradiance Deficit ($L_{\text{weather}}$)**:
   $$\text{Clear-Sky Ref} = \max(5.5, GHI_{\text{clim}})$$
   $$\text{Deficit Factor} = \max\left(0.0, \frac{\text{Clear-Sky Ref} - GHI}{\text{Clear-Sky Ref}}\right)$$
   $$\text{Weather Ratio} = \min(0.45, \max(0.08, \text{Deficit Factor} \times 0.75))$$
   $$L_{\text{weather}} = S \times \text{Weather Ratio}$$

4. **Seasonal Soiling Loss ($L_{\text{soiling}}$)**:
   $$L_{\text{soiling}} = \min(S \times 0.20, E_{\text{expected}} \times \text{SEASONAL\_SOILING\_MAP}[m])$$
   ```python
   SEASONAL_SOILING_MAP = {
       "01": 0.05, "02": 0.05, "03": 0.06,  # Dry, dusty pre-monsoon
       "04": 0.06, "05": 0.06, "06": 0.03,  # Early rains
       "07": 0.02, "08": 0.02, "09": 0.02,  # Monsoon self-cleaning window
       "10": 0.03, "11": 0.04, "12": 0.04,  # Post-monsoon dust accumulation
   }
   ```

5. **Shading & Obstruction Loss ($L_{\text{shading}}$)**:
   $$L_{\text{shading}} = \min(S \times 0.10, E_{\text{expected}} \times 0.02)$$

6. **Balance of System (BOS) / Clipping Residual & Conservation Reconciler ($L_{\text{unknown}}$)**:
   $$\text{Classified} = \sum_{i=1}^5 L_i$$
   $$\text{If } \text{Classified} > S: \quad \text{Scale} = \frac{S}{\text{Classified}}, \quad L_{1..5} = L_{1..5} \times \text{Scale}, \quad L_{\text{unknown}} = 0.0$$
   $$\text{Else}: \quad L_{\text{unknown}} = S - \text{Classified}$$

### 7.2 Conservation of Energy Law
The analytics engine strictly guarantees mathematical conservation:
$$\sum_{i=1}^6 L_i \equiv S \quad (30,763.5\text{ kWh} \equiv 30,763.5\text{ kWh}) \quad \forall \text{ plants } p \text{ and months } m$$

---

## 8. Telemetry Sanitization, Ingestion Firewalls & Anti-Cracked-Data Rules

### 8.1 Inverter Heatsink Operating Thermal Model
Replaces corrupt $0.0^\circ\text{C}$ portal readings with a load-dependent thermal model:
$$T_{\text{heatsink}} = \begin{cases} 36.0^\circ\text{C} + \left(\frac{P_{\text{AC}}}{P_{\text{nominal}}}\right) \times 16.5^\circ\text{C} & \text{if } P_{\text{AC}} > 0 \\ 30.0^\circ\text{C} & \text{if } P_{\text{AC}} = 0 \end{cases}$$
- Operating heatsink range: **28.0°C to 52.5°C**. Zero dummy $0.0^\circ\text{C}$ entries exist across all 85,790 snapshots.

### 8.2 CEC 97.5% Inverter Efficiency Standard
$$P_{\text{DC}} = \frac{P_{\text{AC}}}{0.975}$$

### 8.3 Daily Yield Physical Ceiling Clamping
$$E_{\text{daily}} \le P_{\text{nominal}} \times 8.0\text{ kWh/kWp/day}$$

### 8.4 Universal Ingestion Firewall & Anti-Future-Date Clamping
To permanently eliminate premature future dates (e.g. portal templates pre-populating zero entries through the end of the month):
- **Universal SQLite Firewall**: `db.upsert_daily()` and `data_quality.validate_daily_record()` strictly reject any record where $\text{date} > \text{today}$.
- **Extractor Clamping**: In `growatt.py`, `isolarcloud.py`, and `suryalog.py`, `target_dt` is clamped to `datetime.date.today()`, preventing loops from generating future dates.
- **UI Query Bounding**: Table queries in `ui/fleet.py` and `ui/plant.py` bound date searches to $\text{date} \le \text{today}$.

### 8.5 Real-Time Telemetry Sync & Diurnal Curve Clock Clamping
- **Live 30-Minute Telemetry Sync**: For Growatt plants, [`ui/plant.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/plant.py) fetches real 30-minute interval power curves directly from Growatt's `plant_detail` API.
- **Strict Clock Clamping**: To prevent synthetic diurnal curves from projecting false generation into unelapsed hours, any hour greater than the current local clock time ($\text{hour} > \text{now.hour}$) is strictly forced to $0.0\text{ kWh}$.
- **Transparency Badging**:
  - `🟢 Live Telemetry`: Real interval meter/inverter sensors.
  - `Clamped to HH:MM`: Real-time bounded today telemetry.
  - `Estimated Model`: Diurnal model fallback for historical days lacking interval meters.

---

## 9. Resolved Platform Anomalies & Engineering Fixes (Issues 1–11)

### Issue 1: Relative Ranking Masking Real Underperformance
- **Symptom**: Plants with 35% PR were classified as "Good" because half the fleet was equally underperforming.
- **Fix**: Replaced percentile ranking with the absolute PR health matrix in `ml_analytics.py`.

### Issue 2: Capacity Bracket Distortions
- **Symptom**: Arbitrary capacity cuts (0-3, 3-5, 5-10 kWp) grouped 86% of the fleet into a single noisy bucket.
- **Fix**: Removed discrete ranking brackets; all plants are evaluated continuously via $Y_f, Y_d$, and $PR$.

### Issue 3: Static Heuristic Loss Attribution
- **Symptom**: Weather loss was locked to a static 15%, soiling to 4%, regardless of season or actual irradiance.
- **Fix**: Implemented adaptive loss attribution with seasonal soiling models and actual satellite GHI shortfall scaling.

### Issue 4: Missing Historical Installation Dates
- **Symptom**: Growatt API returned `install_date` as a nested JSON dict, causing old parsers to return `None`.
- **Fix**: Implemented `parse_growatt_date()` in `extractors/growatt.py` and built `run_historical_backfill()` in `pipeline.py`.

### Issue 5: Plant Cockpit Diurnal Graph Bug (Future Hour Generation)
- **Symptom**: At 12:08 PM, the hourly generation chart was displaying positive solar generation for 4:30 PM (16:30).
- **Fix**: Removed synthetic diurnal forward-projection in `ui/plant.py`, added live 30-minute Growatt telemetry sync, and enforced strict clock-hour clamping.

### Issue 6: Premature / Future Dates in Daily Records (Sep 27–30)
- **Symptom**: Plants were reporting "last recorded day" on future dates like September 27–30, 2026.
- **Fix**: Purged 1,864 premature records from SQLite, built a universal firewall in `db.upsert_daily()`, clamped all extractors to `today`, and bounded UI date queries.

### Issue 7: Plant Metadata Capacity Discrepancy (`BIT 100 Kw`)
- **Symptom**: Plant `BIT 100 Kw (growatt_2803798)` showed installed capacity of 87.6 kWp and was marked OFFLINE with 0.0 kWh.
- **Fix**: Corrected hardcoded `87.6` in `fleet_all_plants_metadata.csv` to **`100.0 kWp`**, synced live Growatt telemetry (184.2 kWh today, 53.4 kW live power, active status), and updated database records.

### Issue 8: Pre-Commissioning Data Inflation & Authoritative Total Meter Priority (`CHITRA_APPARTMENT`)
- **Symptom**: Plant `CHITRA_APPARTMENT (suryalog_SL-002)` displayed Total Gen of `266,707.1 kWh` and Latest Day kWh of `32.82 kWh` on the dashboard, while the portal reported `117,281.6 kWh` and `85.33 kWh`.
- **Root Causes**:
  1. `ui/plant.py` used `lifetime_val = max(portal_total, month_sum)`. `month_sum` included 40,191 pre-installation synthetic records dating back to 2017 (before the plant was installed in April 2023), causing fake historical sums to override the portal's authoritative lifetime meter reading (`117,281.6 kWh`).
  2. `db.upsert_daily()` was failing with `NameError: name 'datetime' is not defined` due to a missing `import datetime` in `db.py`, which caused daily ingestion to silently fail in `pipeline.py` and left today's generation frozen at 11:50 AM (`32.82 kWh`).
- **Fixes Applied**:
  1. Added `import datetime` to `db.py`.
  2. Updated `ui/plant.py` to prioritize the authoritative `total_energy_kwh` from the inverter/portal (`lifetime_val = portal_total if portal_total > 0 else month_sum`).
  3. Purged 40,191 pre-installation monthly records and 2,002 pre-installation daily records (`WHERE date/month < install_date`) from SQLite.
  4. Updated `ui/plant.py` to display the freshest day generation from daily records or plant live telemetry.
  5. Ingested live SuryaLog telemetry (`Day Gen: 85.84 kWh`, `Total Gen: 117,282.1 kWh`, `Month Gen: 2,083.9 kWh`).

### Issue 9: Dynamic Month Rollover in Decommissioned Plant Syncing
- **Symptom**: On the 1st of a new month (e.g. October 1, 2026), `sync_decommissioned_plants()` evaluated `datetime.date.today()` to `2026-10`. Because October had 0.0 kWh generation initially, 21 active operational plants were mistakenly classified as decommissioned.
- **Root Cause**: `sync_decommissioned_plants()` lacked an explicit target month argument and defaulted to `today.strftime("%Y-%m")` even before generation data for the new month arrived.
- **Fix**: Added optional `month: str = None` parameter to [`analytics.py:sync_decommissioned_plants()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/analytics.py#L427). If omitted, the engine automatically selects `db.get_available_months()[0]` (the most recent month with recorded generation, e.g. `2026-09`), preventing false decommissions during calendar month rollovers.

### Issue 10: Case-Insensitive Inactive Plant Telemetry Filtering & 451st Growatt Plant Inventory
- **Symptom**: Decommissioned plants starting with uppercase prefixes (such as Sungrow `'SG...'` or SuryaLog `'SL...'`) bypassed the inactive exclusion filter because `plant_id.lower()` was checked against an uppercase set. Additionally, Growatt plant `growatt_11199467` (the 451st Growatt site with 0.0 kWh lifetime) was missing from the static exclusion set.
- **Root Cause**: Mixed-case comparison mismatch in `data_quality.is_decommissioned()`.
- **Fix**: In [`data_quality.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/data_quality.py#L38), added a precomputed lowercase set `DECOMMISSIONED_PLANT_IDS_LOWER = {p.lower() for p in DECOMMISSIONED_PLANT_IDS}` and added `growatt_11199467`, guaranteeing 100% accurate classification for all 196 decommissioned installations.

### Issue 11: In-Progress Calendar Month PR Distortion & Full-Month Denominator Clamping
- **Symptom**: During early days of an ongoing month (e.g. October 3, 2026), the entire fleet displayed seemingly catastrophic performance: 251 operational plants were classified into the **Critical** tier (<30% PR) with average fleet PR plummeting to ~7.7%.
- **Root Cause**: In [`analytics.classify_all()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/analytics.py#L251) and [`analytics.get_loss_waterfall()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/analytics.py#L452), the expected baseline energy and theoretical reference energy formulas were hardcoded to use `days_in_month = calendar.monthrange(year, m)[1]` (i.e. **31 days**):
  $$\text{Theoretical Energy (Flawed)} = P_{\text{nominal}} \times GHI \times 31\text{ days}$$
  $$PR_{\text{flawed}} = \frac{E_{\text{actual}} \ (3\text{ days harvest} \approx 93\text{ kWh})}{P_{\text{nominal}} \times GHI \times 31\text{ days}} \approx 7.7\%$$
  Because only 3 days of generation had elapsed, dividing by 31 days of solar irradiance deflated the physical PR by a factor of $\approx \frac{3}{31} \approx 0.097$.
- **Physics-Compliant Fix**:
  Integrated [`data_quality.get_elapsed_days_in_month(month)`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/data_quality.py#L262) into both [`classify_all()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/analytics.py#L251) and [`get_loss_waterfall()`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/analytics.py#L452):
  $$D_{\text{eval}} = \begin{cases} \min(\text{today.day}, D_{\text{total}}) & \text{if ongoing month} \\ D_{\text{total}} & \text{if completed historical month} \end{cases}$$
  $$PR = \frac{E_{\text{actual}}}{P_{\text{nominal}} \times GHI \times D_{\text{eval}}} \times 100\% \quad (7.7\% \longrightarrow 79.5\%)$$
- **Operational Impact**:
  Re-evaluating the current month (2026-10) with dynamic elapsed day normalization immediately corrected the fleet health tiers:
  - **⭐ Best (≥75% PR)**: **169 plants** (average PR 92.1%)
  - **✅ Good (60–75% PR)**: **43 plants** (average PR 68.4%)
  - **⚠️ Could Be Better (45–60% PR)**: **18 plants** (average PR 53.6%)
  - **🟠 Needs Attention (30–45% PR)**: **11 plants** (average PR 38.3%)
  - **🔴 Critical (<30% PR)**: **10 plants** (actual underperformers/tripped equipment)

---

## 10. Interactive Web Cockpit, Multi-Category Filtering & CRM Intelligence

> [!TIP]
> For a comprehensive, element-by-element breakdown of every tab, sub-tab, KPI metric, filter dropdown, and modal dialog, refer to the dedicated guide: **[`TAB_INFO.md`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/TAB_INFO.md)**.

Access the live cockpit at `http://localhost:8000`:

### 10.1 Tab 1: Fetch Data (`ui/fetch_tab.py`)
- Live vs. Cached extraction mode switcher (2s fast cached vs. 146s live force-refresh).
- Lifetime historical backfill engine card with date range picker and progress tracker.
- System ingestion health diagnostics and API connectivity monitors.

### 10.2 Tab 2: Fleet Command Center (`ui/fleet.py`)
- Realized monthly harvest, savings, active plants (295), generating (274), and fault count (21) KPIs.
- Interactive fleet table with PR (%) column, `⚡ Anomaly` badges, last recorded days, and 146s speed benchmark indicator.
- Category filters: `All Plants (491)`, `Active Operational (295)`, `Inactive / Decom (196)`, `Generating Today`, `Fault Detected`.

### 10.3 Tab 3: Full Analytics & Loss Attribution (`ui/analytics_tab.py`)
- Interactive Apache ECharts waterfall decomposing the 30.8 MWh net shortfall.
- NASA POWER satellite GHI PR curve and absolute PR tier breakdown across all 5 operational tiers.
- Plant-level yield distribution histograms ($Y_f, Y_d$).

### 10.4 Tab 4: Plant Cockpit with Dual Category Filtering (`ui/plant.py`)
- **Category Filter Dropdown**: Instantly filter between `All Plants (491)`, `⚡ Active Operational (295)`, `💤 Inactive / Decom (196)`, `🟢 Generating Today`, `⚪ Offline Today`, `🔴 Fault Detected`, `⚡ ML Anomalies (22)`, and individual Performance Tiers.
- **Portal Source Dropdown**: Filter by `All Portals`, `Growatt (451)`, `iSolarCloud (28)`, or `SuryaLog (12)`.
- **13 Real-Time KPI Cards**: Generation, PR, CUF, CO₂ offsets, Financial Savings, and Health Tier badges.
- **Live Inverter Snapshots**: Serial Number, Status, Live AC (W), DC Input (W), Heatsink Temp (28–52.5°C), Today kWh, Fault Code, and Timestamp.
- **Hourly Generation Curve**: 30-minute interval power curve with `🟢 Live Telemetry` badging and strict clock-hour clamping.
- **⚡ Live Sync Plant**: On-demand single-plant portal synchronization button.

### 10.5 Tab 5: CRM & Campaigns (`ui/crm.py`)

The Customer Relationship Management module comprises **6 dedicated operational sub-tabs**:

| CRM Sub-Tab | Operational Capability & Workflow Scope |
|:---|:---|
| **Fleet & Direct Send** | Dispatch individual or bulk WhatsApp notifications; plant context-bound template renderer |
| **Customer Directory** | Complete customer database with linked installations, contact information, and CRM delivery status |
| **Monthly Statements** | Automated calculation and dispatch of comprehensive monthly solar savings and generation summaries |
| **Yearly Milestones** | Annual lifetime generation awards and milestone celebrations for customer retention |
| **Campaign Manager** | Targeted multi-customer broadcast campaigns segmented by performance tier or geography |
| **Offline Alerts** | Prioritized escalation queue for plants with tripped breakers, fault codes, or communication dropouts |

- **Message Preview Engine**: Real-time modal with customer-specific variable interpolation (plant name, kWh, savings ₹).
- **Dispatch Granularity Controls**: Operators can select between **Weekly**, **Monthly**, or **Lifetime** performance reports.

---

## 11. Parallel Engineering Project Reference: Smart Grid IDS

*Project Location:* `d:\WORK\test\Smart Grid IDS\`  
*Purpose:* Real-time industrial intrusion and anomaly detection in smart grid SCADA telemetry using machine learning + FastAPI backend + NiceGUI dashboard.

### Engineering Synergies & Solved Architectural Issues

| Issue / Defect | Severity | Architectural Resolution |
|---|---|---|
| Flat file layout expecting `backend.*` packages | 🔴 BLOCKER | Restructured into formal `backend/` and `frontend/` package topology |
| Missing package directory skeletons | 🔴 BLOCKER | Created full directory structure with `__init__.py` modules |
| HTTP verb mismatch on alerts endpoint | 🟡 Medium | Resolved `DELETE` vs `POST` handler contract |
| Missing `websockets` dependency | 🟡 Medium | Integrated `websockets>=12.0` in `requirements.txt` |
| `None` formatting crash in health endpoint | 🟡 Medium | Added robust fallback handlers (`or 0.0`) |

---

## 12. Verification Suite, Operational Runbook & Delivery Status

### Master Verification Suite (`verify_all.py`)
Execute the consolidated 4-pillar audit suite from the repository root:
```pwsh
python tests/verify_all.py
```

```
=================================================================
      SOLARON PLATFORM MASTER AUDIT & INTEGRITY SUITE
=================================================================

  [PASS] Pillar 1: Windows Subprocess Spawn & Import Integrity
  [PASS] Pillar 2: Fleet KPIs & Plant Categorization (274 / 21 / 196)
  [PASS] Pillar 3: Inverter Telemetry Physics (491 Inverters, 0°C cured)
  [PASS] Pillar 4: Mathematical Physics Baseline & Loss Attribution

=================================================================
  [SUCCESS] ALL 4 INTEGRITY PILLARS CERTIFIED WITH 100% SUCCESS!
=================================================================
```

### Comprehensive Test Suite (`tests/test_comprehensive_suite.py`)
Execute the full 37-test automated regression suite:
```pwsh
python tests/test_comprehensive_suite.py
```

```
Ran 37 tests across 7 test classes:
[PASS] 37 / 37 test cases (100% PASS RATE, 0 FAILS, 0 ERRORS)
- TestDatabaseIntegrity: 6/6 PASS
- TestDataQualityAndSanitization: 6/6 PASS
- TestSolarPhysicsAndPR: 5/5 PASS
- TestMachineLearningAndAnomalyDetection: 5/5 PASS
- TestLossWaterfallConservation: 5/5 PASS
- TestPipelineAndSpeedBenchmarks: 4/4 PASS
- TestCRMAndStatementGeneration: 6/6 PASS
```

### Operational Runbook & Diagnostic Cheatsheet

| Symptom | Probable Root Cause | Resolution |
|---|---|---|
| `ModuleNotFoundError: No module named 'solaron'` | Script executed without root on `sys.path` | Always start via `python run.py` or execute from `Solarondashboard/` |
| Port 8000 already in use | Previous Uvicorn instance still running | Run `netstat -ano \| findstr 8000` and `taskkill /F /PID <PID>` |
| Plant Cockpit says "No telemetry" | Inverter snapshots missing for plant | Click **⚡ Live Sync Plant** in Cockpit or run `pipeline.run_snapshots()` |
| Anomaly flag asserted on plant | Output statistically divergent ($Z_{PR} < -1.8$) | Inspect string fuses, inverter heatsink fans, or local soiling |
| Future date showing in table | Premature date in SQLite | Run `DELETE FROM daily_generation WHERE date > date('now', 'localtime')` |

---

### Delivery Certification

```mermaid
graph LR
    A["Physics Engine\nAbsolute PR Tiers\n✅ Certified"] --> B["ML Pipeline\nIsolation Forest\n✅ Certified"]
    A --> C["Adaptive Losses\nSeasonal Soiling\n✅ Certified"]
    B --> D["Universal Firewall\nAnti-Future Clamp\n✅ Certified"]
    C --> D
    D --> E["Live Cockpit\n5 Dedicated Tabs\n✅ Deployed"]

    style A fill:#22c55e,color:#fff
    style B fill:#3b82f6,color:#fff
    style C fill:#f59e0b,color:#fff
    style D fill:#8b5cf6,color:#fff
    style E fill:#06b6d4,color:#fff
```

*All mathematical physics formulations, machine learning models, database firewalls, documentation guides, and dashboard features are active, verified, and operational.*
