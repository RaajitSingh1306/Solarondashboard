# Solaron — Enterprise Solar Telemetry Intelligence, Physics Analytics & CRM Platform

> **Version:** 2.4.0 · **Python:** 3.10+ · **Stack:** FastAPI + NiceGUI (Quasar / Tailwind CSS) + SQLite + DuckDB/Parquet + AWS S3  
> **Integrated OEM Portals:** Growatt Server API, Sungrow iSolarCloud, SuryaLog AE Cloud  
> **Portfolio Scope:** 491 Monitored Solar Sites · **Active Operational Capacity:** 2.29 MWp (295 Installations)  
> **Test Certification:** 4/4 Master Pillars Passed · 37/37 Comprehensive Tests (100% Pass Rate)  
> **Re-creation Roadmap:** See [TASK_LIST.md](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/TASK_LIST.md) for the complete 12-phase step-by-step build guide.

---

## ⚡ Executive Summary & Problem Context

Operating distributed rooftop solar at scale across India presents severe operational and data engineering hurdles:
1. **Multi-OEM Gateway Fragmentation**: Monitoring portals span competing inverter manufacturers (Growatt, Sungrow, SuryaLog, Fronius), each with conflicting API formats, unit scales (Watts vs. kWp), and missing coordinates.
2. **The "No Pyranometer" Dilemma**: Over 95% of distributed residential rooftop installations lack expensive on-site solar irradiance sensors (pyranometers). Without local solar radiation data, operators cannot tell if a drop in harvest is caused by regional monsoon cloud cover or an electrical inverter fault.
3. **Data Quality & Sensor Anomalies**: Dataloggers frequently freeze and repeat identical daily numbers ("stuck values"), report dummy heatsink temperatures (0.0°C), or pre-populate forward calendar days with zeros.
4. **Customer Communication Gaps**: Maintenance technicians are dispatched reactively after customers discover high power bills, instead of proactively diagnosing loss causes and dispatching automated multi-lingual alerts.

**Solaron** solves these challenges through a unified, physics-grounded, multi-tiered architecture combining multi-OEM ingestion, a Bronze Medallion Lake, a virtual pyranometer peer-relative framework (RPI), mathematically conserved loss decomposition, unsupervised machine learning, and an automated 6-stage WhatsApp CRM engine.

---

## 🏛️ System Architecture & Data Flow

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    OEM SOLAR CLOUD GATEWAYS                                     │
│          Growatt ShineServer API              Sungrow iSolarCloud              SuryaLog Cloud   │
│         451 Plants (Residential/C&I)           28 Plants (Commercial)          12 Plants (C&I)  │
└───────────────────────┬─────────────────────────────────┬───────────────────────────────┬───────┘
                        │                                 │                               │
                        ▼                                 ▼                               ▼
               extractors/growatt.py           extractors/isolarcloud.py       extractors/suryalog.py
             (REST v2 + 30m live sync)         (Playwright Web3 Session)       (AE Cloud REST/Export)
                        │                                 │                               │
                        └─────────────────────────────────┼───────────────────────────────┘
                                                          ▼
                                            pipeline/bronze.py (Bronze Lake)
                              ┌───────────────────────────────────────────────────────────┐
                              │ - Partition: source={src}/ingest_date={YYYY-MM-DD}/       │
                              │ - Content Hash: {endpoint}_{time}_{sha256}.json.gz        │
                              │ - Mirroring: AWS S3 Bucket (solaron-dashboard-data)       │
                              │ - Guard: overwrite_if_empty_only = True (Immutable raw)  │
                              └───────────────────────────┬───────────────────────────────┘
                                                          │
                                                          ▼
                                            pipeline/pipeline.py & db.py
                              ┌───────────────────────────────────────────────────────────┐
                              │ - Universal Ingestion Firewall: date <= today             │
                              │ - Data Contracts & Pandera Type/Bounds Validation         │
                              │ - Capacity Normalization (Watts -> kWp)                   │
                              └───────────────────────────┬───────────────────────────────┘
                                                          │
                                ┌─────────────────────────┴─────────────────────────┐
                                ▼                                                   ▼
                     SQLite: solar_analytics.db                             SQLite: crm_data.db
             ┌─────────────────────────────────────────┐            ┌──────────────────────────────────┐
             │ • plants (491 rows, 295 active)         │            │ • customers (customer directory) │
             │ • daily_generation (~43k records)       │            │ • escalation_state (FSM state)   │
             │ • monthly_generation (~5.8k records)    │            │ • escalation_log (audit trail)   │
             │ • inverter_snapshots (~85k snapshots)   │            │ • gupshup_inbound_log (webhooks) │
             │ • loss_analysis (conserved waterfalls)  │            │ • message_queue & campaign_log   │
             └──────────────────┬──────────────────────┘            └─────────────────┬────────────────┘
                                │                                                     │
                                ▼                                                     ▼
                     core/ & engines/ Analytics                             services/crm.py & gupshup.py
             ┌─────────────────────────────────────────┐            ┌──────────────────────────────────┐
             │ • Solar Physics Engine (Yf, Yd, PR, CUF)│            │ • 6-Level Escalation Engine      │
             │ • Peer Group & RPI Engine               │            │ • Multi-lingual Statement Gen    │
             │ • Adaptive 6-Part Loss Waterfall        │            │ • Webhook Inbound Ingestion      │
             │ • Unsupervised Isolation Forest (ML)    │            │ • Automated Ticket Escalation    │
             └──────────────────┬──────────────────────┘            └─────────────────┬────────────────┘
                                │                                                     │
                                └─────────────────────────┬───────────────────────────┘
                                                          ▼
                                              app.py (FastAPI + NiceGUI)
                                ┌───────────────────────────────────────────────────────────┐
                                │ • Tab 1: Telemetry Fetch Workbench (ui/fetch_tab.py)      │
                                │ • Tab 2: Fleet Command Center (ui/fleet.py)               │
                                │ • Tab 3: Full Fleet Analytics & Losses (ui/analytics.py)  │
                                │ • Tab 4: Plant Deep-Dive Cockpit (ui/plant.py)            │
                                │ • Tab 5: CRM Operations & WhatsApp (ui/crm.py)            │
                                │ • REST API Endpoints (/api/plants, /api/daily, /export)   │
                                └───────────────────────────────────────────────────────────┘
```

---

## 📊 Core Solar Physics & Analytics Primer

To understand, modify, or rebuild this platform, you need to understand the mathematical formulas and operational principles behind each metric:

### 1. Specific Yield ($Y_f$)
Normalizes actual electrical energy output by the installed DC peak capacity of the solar array:
$$Y_f = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}]} \quad [\text{kWh/kWp}]$$
*Physical Bounds:* Daily specific yield is typically clamped to $0.0 \le Y_f \le 8.5\text{ kWh/kWp/day}$.

### 2. Normalized Daily Specific Yield ($Y_d$)
Normalizes generation by the elapsed calendar days in the measurement window, avoiding distortion during ongoing months:
$$Y_d = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}] \times D_{\text{eval}}} \quad [\text{units/kWp/day}]$$
Where $D_{\text{eval}} = \min(\text{today.day}, D_{\text{total}})$ for the current month.

### 3. Performance Ratio ($PR$)
Measures total system conversion efficiency independent of irradiance fluctuations:
$$PR = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}] \times GHI \ [\text{kWh/m}^2/\text{day}] \times D_{\text{eval}}} \times 100\%$$
*Physical Standard:* A well-designed, healthy grid-tied solar plant in India operates between $75.0\%$ and $82.0\%$ PR.

### 4. Capacity Utilisation Factor ($CUF$)
Represents the 24-hour plant load factor standard in Indian utility contracts:
$$CUF = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}] \times 24 \text{ hours} \times D_{\text{eval}}} \times 100\%$$

### 5. Environmental Carbon Offsets ($CO_2$)
Calculated using the official Central Electricity Authority (CEA) of India grid emission baseline factor:
$$CO_2 \ [\text{kg}] = E_{\text{actual}} \ [\text{kWh}] \times 0.82\text{ kg CO}_2/\text{kWh}$$

---

## 💡 The "No Pyranometer" Solution: Peer-Relative Performance Index (RPI)

When on-site pyranometers are unavailable, regional peer plants act as the collective reference:

```text
               Regional Solar Peer Group (Same City / Pincode Prefix)
       ┌──────────────────┬──────────────────┬──────────────────┐
       │     Plant A      │     Plant B      │     Plant C      │
       │   Yf = 4.2 u/kWp │   Yf = 4.4 u/kWp │   Yf = 4.1 u/kWp │
       └─────────┬────────┴─────────┬────────┴─────────┬────────┘
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    ▼
               Healthy Peer Median Reference = 4.2 u/kWp
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                   Target Plant 1        Target Plant 2
                   Yf = 4.1 u/kWp        Yf = 0.8 u/kWp
                   RPI = 4.1 / 4.2       RPI = 0.8 / 4.2
                       = 0.98                = 0.19
                 [Status: HEALTHY]     [Status: FAULT/TRIP]
```

### Mathematical Formulation
$$Y_f[i, d] = \frac{E[i, d]}{P_{\text{nominal}}[i]}$$
$$ref[G, d] = \text{Median}_{j \in G, \text{healthy}}(Y_f[j, d])$$
$$RPI[i, d] = \frac{Y_f[i, d]}{ref[G, d]}$$
$$\text{Rolling Score}_i = \text{Median}_{14\text{-day}}(RPI[i, \cdot])$$

### Diagnostic Signature of RPI Patterns
| Observed RPI Trajectory | Physical Root Cause |
|:---|:---|
| **Sudden drop to $\approx 0.0$ while peers remain normal** | Inverter trip, blown DC fuse, grid disconnection, or datalogger power failure. |
| **Gradual decay over weeks with sharp reset after rain** | Heavy dust accumulation / array soiling (sawtooth curve). |
| **Flat line between $0.60 - 0.75$ from commissioning day** | Fixed structural shading (parapet, tree), incorrect tilt/azimuth, or disconnected string. |
| **All installations in city drop simultaneously** | Regional cloud cover, storm, or monsoon rain ($RPI$ remains near $1.0$). |

---

## ⚖️ Conserved 6-Part Loss Attribution Waterfall

When a plant underperforms its clear-sky benchmark ($E_{\text{expected}} = P_{\text{nominal}} \times GHI \times D_{\text{eval}} \times 0.75$), the Net Energy Shortfall is decomposed into six strictly conserved physical components:

$$\text{Shortfall} \ (S) = \max(0.0, E_{\text{expected}} - E_{\text{actual}})$$

```text
Expected Baseline (245.1 MWh)
  │
  ├── [–] L_comm:    Datalogger / Communication Dropouts (3.5 MWh)
  ├── [–] L_fault:   Inverter Fault / Breaker Trips (0.0 MWh)
  ├── [–] L_weather: Overcast / Regional Irradiance Deficit (2.9 MWh)
  ├── [–] L_soiling: Dust & Particulate Deposition (2.4 MWh)
  ├── [–] L_shading: Parapet & Structural Obstructions (2.0 MWh)
  └── [–] L_unknown: Balance of System / Cable / Clipping Residual (19.9 MWh)
  │
  ▼
Actual Realized Fleet Harvest (214.3 MWh)
```

**First-Principles Conservation Law:**
$$\sum_{i=1}^6 L_i \equiv S \quad \forall \text{ installations and measurement months}$$

---

## 🤖 Unsupervised Machine Learning Anomaly Detection

Solaron uses an unsupervised scikit-learn `IsolationForest` pipeline (`contamination=0.08`, `n_estimators=100`, `random_state=42`) with cyclic seasonal encoding to isolate true electrical and hardware defects without human labels:

### Feature Vector Formulation ($\vec{x} \in \mathbb{R}^5$)
$$\vec{x} = \begin{bmatrix} 
Y_d & \text{(Daily Specific Yield: units/kWp/day)} \\
PR & \text{(Performance Ratio: \%)} \\
P_{\text{nominal}} & \text{(Installed Capacity in kWp)} \\
\sin\left(\frac{2\pi \cdot (m - 1)}{12}\right) & \text{(Cyclic Month Sine Seasonality)} \\
\cos\left(\frac{2\pi \cdot (m - 1)}{12}\right) & \text{(Cyclic Month Cosine Seasonality)}
\end{bmatrix}$$

### Dual-Gate Anomaly Filter
To eliminate false alarms on highly efficient, unshaded solar arrays, an anomaly flag is asserted **only when geometrically isolated in feature space AND actively underperforming relative to cohort median**:
$$\text{Anomaly Flag} = 1 \iff (\text{raw\_pred} = -1) \land (Y_d < \text{Median}_m(Y_d))$$

---

## 📱 Multi-Lingual WhatsApp CRM & 6-Stage Escalation FSM

Customer notifications and service dispatches follow a strict 6-stage finite state machine ([engines/escalation_state_machine.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/engines/escalation_state_machine.py)):

```text
[Trigger: PR < 30% or Trip]
       │
       ▼
   L1_TRIGGER  ──>  L2_INFO_SENT  ──>  L3_CHECK_SENT  ──>  L4_OFFER_SENT
 (Fault Detected)   (WhatsApp Report)   (Self-Check Tips)   (Service Offer Sent)
                                                                    │
                                            ┌───────────────────────┴───────────────────────┐
                                            ▼                                               ▼
                                      L5_DECISION: YES                                L5_DECISION: NO
                                      (Create Work Order)                             (Log Opt-Out & Grace)
                                            │
                                            ▼
                                       L6_RECHECK
                               (Verify Generation Post-Visit)
                                            │
                                            ▼
                                    RESOLVED / CLOSED
```

* **Supported Languages:** English, Hindi, and Marathi copy templates with variable substitution (`templates/escalation_messages.py`).
* **Inbound Webhook:** Captures customer button selections ("YES, INSPECT", "NO", or text replies) via Gupshup webhook endpoints.

---

## 📂 Codebase Directory Tour

| Directory / File | Description & Purpose |
|:---|:---|
| [app.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/app.py) | Main FastAPI + NiceGUI web application with shared reactive state. |
| [run.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/run.py) | Windows multiprocessing-safe launcher with Proactor event loop configuration. |
| [config.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/config.py) | Pydantic Settings reading environment variables and resolving filesystem paths. |
| [core/](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core) | Core solar physics calculations, data contracts, and ML anomaly pipelines. |
| ├── [analytics.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/analytics.py) | Solar physics formulas ($Y_f, Y_d, PR, CUF$, $CO_2$) and loss calculations. |
| ├── [analytics_lake.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/analytics_lake.py) | DuckDB in-memory OLAP query engine and Parquet exporter for Medallion Lake. |
| ├── [contracts.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/contracts.py) | Pandera DataFrame schemas enforcing strict types and physical bounds. |
| ├── [data_quality.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/data_quality.py) | Stuck-value detector, heatsink thermal model, and ghost plant resolver. |
| ├── [ml_analytics.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/ml_analytics.py) | Isolation Forest anomaly detection and absolute IEEE/IEC PR health tiers. |
| └── [peer_group.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/core/peer_group.py) | Hierarchical geographic peer clustering (City $\rightarrow$ District $\rightarrow$ State $\rightarrow$ Fleet). |
| [engines/](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/engines) | Specialized operational calculation engines. |
| ├── [escalation_state_machine.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/engines/escalation_state_machine.py) | 6-stage finite state machine for automated WhatsApp dispatches. |
| ├── [lost_revenue.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/engines/lost_revenue.py) | Financial loss attribution and revenue at risk calculations. |
| ├── [physics.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/engines/physics.py) | Solar physics calculations with temperature correction. |
| ├── [rpi.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/engines/rpi.py) | Peer-Relative Performance Index calculation. |
| └── [status_engine.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/engines/status_engine.py) | Daily operational plant status classifier (`PRODUCING`, `FAULT_SUSPECT`, etc.). |
| [extractors/](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors) | Multi-OEM cloud extractors. |
| ├── [base.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors/base.py) | `BaseExtractor` abstract interface contract. |
| ├── [growatt.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors/growatt.py) | Growatt Server API client with 30-minute interval power curves. |
| ├── [isolarcloud.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors/isolarcloud.py) | Sungrow iSolarCloud Playwright headless browser scraper. |
| ├── [suryalog.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors/suryalog.py) | SuryaLog AE Cloud REST client and parser. |
| └── [excel_parser.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/extractors/excel_parser.py) | Fallback manual monthly Excel workbook parser. |
| [pipeline/](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/pipeline) | Ingestion, validation, and database storage. |
| ├── [bronze.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/pipeline/bronze.py) | Bronze raw data lake with SHA-256 deduplication and date partitioning. |
| ├── [db.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/pipeline/db.py) | SQLite connection pooling and universal date firewall. |
| └── [pipeline.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/pipeline/pipeline.py) | Master ingestion orchestrator and historical backfill engine. |
| [services/](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/services) | Operational background services. |
| ├── [crm.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/services/crm.py) | Customer directory management, statement generator, and campaign engine. |
| ├── [geocode.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/services/geocode.py) | Indian 6-digit postal code regex extractor and Nominatim geocoder. |
| ├── [gupshup.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/services/gupshup.py) | Gupshup WhatsApp Business API connector. |
| ├── [s3_archive.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/services/s3_archive.py) | AWS S3 cloud mirroring with anti-overwrite safety guards. |
| └── [scheduler.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/services/scheduler.py) | APScheduler cron jobs for periodic snapshot sync and database backups. |
| [routes/](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/routes) | FastAPI REST API route handlers (`/api/plants`, `/api/daily`, `/api/export`, etc.). |
| [ui/](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui) | Reactive NiceGUI dashboard tab components. |
| ├── [fetch_tab.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/fetch_tab.py) | Tab 1: Telemetry Fetch Workbench & Historical Backfill. |
| ├── [fleet.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/fleet.py) | Tab 2: Fleet Command Center with search, sort, and anomaly badges. |
| ├── [analytics.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/analytics.py) | Tab 3: Full Fleet Analytics with Apache ECharts Loss Waterfall. |
| ├── [plant.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/plant.py) | Tab 4: Plant Deep-Dive Cockpit with real-time clamped diurnal curves. |
| └── [crm.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/crm.py) | Tab 5: CRM Operations & Multi-Lingual WhatsApp Dispatch. |
| [tests/](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/tests) | Multi-pillar verification and regression test suites. |
| ├── [verify_all.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/tests/verify_all.py) | 4-Pillar master audit suite certifying platform integrity. |
| └── [test_comprehensive_suite.py](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/tests/test_comprehensive_suite.py) | 37 automated unit and integration tests. |

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.10+** (Python 3.11 recommended)
- **Git**
- Modern Web Browser (Google Chrome, Microsoft Edge, Mozilla Firefox)

### 2. Environment Setup
```pwsh
# 1. Navigate to the project directory
cd c:\Users\raaji\Downloads\Solaron\Solarondashboard

# 2. Create and activate a Python virtual environment
python -m venv .venv

# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser binaries (for Sungrow scraper)
playwright install chromium
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```pwsh
cp .env.example .env
```
Key configuration parameters in `.env`:
```ini
# Portal Credentials (optional for local cache mode)
GROWATT_USER="your_growatt_username"
GROWATT_PASSWORD="your_growatt_password"
SUNGROW_USER="your_sungrow_username"
SUNGROW_PASSWORD="your_sungrow_password"
SURYALOG_USER="your_suryalog_username"
SURYALOG_PASSWORD="your_suryalog_password"

# WhatsApp CRM
GUPSHUP_API_KEY="your_gupshup_api_key"
GUPSHUP_APP_NAME="your_gupshup_app_name"

# AWS S3 Bronze Data Lake (optional for local operation)
AWS_ACCESS_KEY_ID="your_aws_key"
AWS_SECRET_ACCESS_KEY="your_aws_secret"
AWS_REGION="ap-south-1"
S3_BUCKET_NAME="solaron-dashboard-data"

# Application Settings
PRICE_PER_UNIT=14.0
PORT=8080
SCHEDULER_ENABLED=False
```

### 4. Launch the Dashboard
Run the platform launcher:
```pwsh
python run.py
```
Open your browser and navigate to: **`http://localhost:8080`**

### 5. Run the Automated Test Suites
Run the 4-Pillar Master Platform Audit:
```pwsh
python tests/verify_all.py
```
Run the 37-Test Comprehensive Regression Suite:
```pwsh
python tests/test_comprehensive_suite.py
```

---

## 🛠️ How to Re-create This Project Step-by-Step

To build this platform from scratch by yourself, follow the structured master curriculum in **[TASK_LIST.md](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/TASK_LIST.md)**.

### Recommended Study & Recreation Order:
1. **Week 1 (Foundations & Ingestion)**:
   - Study `config.py` and `pipeline/db.py` to understand the SQLite schema design.
   - Implement `extractors/base.py` and `extractors/growatt.py` to extract raw telemetry.
   - Implement `pipeline/bronze.py` to save immutable date-partitioned JSON files.
2. **Week 2 (Data Quality & Sanitization)**:
   - Build `core/contracts.py` (Pandera validation).
   - Build `services/geocode.py` (pincode geocoding) and `core/data_quality.py` (stuck sensors and thermal model).
3. **Week 3 (Solar Physics & RPI)**:
   - Build `core/analytics.py` for $Y_f, Y_d, PR, CUF$.
   - Build `core/peer_group.py` and `engines/rpi.py` to create the virtual pyranometer framework.
4. **Week 4 (Loss Attribution & ML)**:
   - Implement `engines/lost_revenue.py` (the conserved 6-part loss attribution waterfall).
   - Implement `core/ml_analytics.py` (Isolation Forest with cyclical seasonal features).
5. **Week 5 (Analytical Lake & CRM)**:
   - Implement `core/analytics_lake.py` (DuckDB + Parquet).
   - Implement `engines/escalation_state_machine.py` and `services/gupshup.py` for WhatsApp automation.
6. **Week 6 (Frontend UI & Certification)**:
   - Build `ui/fleet.py`, `ui/plant.py`, `ui/analytics.py`, `ui/crm.py`, and `ui/fetch_tab.py` with NiceGUI and Apache ECharts.
   - Run `tests/verify_all.py` to certify all 4 pillars!

---

## 📄 License & Attribution

Proprietary Software — All rights reserved © 2026 Solaron Homes Pvt Ltd.  
Engineered for distributed solar operations and customer communication across India.
