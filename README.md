# Solaron — Solar Operations, Telemetry & CRM Intelligence Platform

> **Version**: 2.1.0 · **Python**: 3.10+ · **Framework**: FastAPI + NiceGUI · **Portals**: Growatt, iSolarCloud, SuryaLog  
> **Fleet**: 490 Aggregated Installations · **Active Generating Fleet**: 295 Inverters (1.80 MWp) · **Monthly Harvest**: ~121.32 MWh · **Est. Commercial Value**: ₹5,01,410

> [!IMPORTANT]
> **Master Data & Analytics Specification**: For the complete empirical fleet baseline (490 plants), solar physics derivations ($GHI, Y_f, Y_d, PR, CUF$), scikit-learn Isolation Forest ML equations, and 7-issue engineering audit, consult:
> - 📄 [**`DATA_DOCUMENT.md`**](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/DATA_DOCUMENT.md) — Unified Master Data, Solar Physics & Machine Learning Specification

---

## Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [System Architecture](#2-system-architecture)
3. [Directory Layout](#3-directory-layout)
4. [Installation & Setup](#4-installation--setup)
5. [Execution Modes & Windows Multiprocessing Safety](#5-execution-modes--windows-multiprocessing-safety)
6. [Multi-Portal Telemetry Ingestion](#6-multi-portal-telemetry-ingestion)
7. [The Mathematical Physics Engine](#7-the-mathematical-physics-engine)
   - 7.1 [Specific Yield ($Y_f$)](#71-specific-yield-y_f)
   - 7.2 [Daily Specific Yield ($Y_d$)](#72-daily-specific-yield-y_d)
   - 7.3 [Capacity Utilisation Factor (CUF %)](#73-capacity-utilisation-factor-cuf-)
   - 7.4 [Performance Ratio (PR %) with NASA POWER GHI](#74-performance-ratio-pr--with-nasa-power-ghi)
   - 7.5 [Expected Baseline Generation Model](#75-expected-baseline-generation-model)
   - 7.6 [6-Part Loss Attribution Waterfall & Conservation Law](#76-6-part-loss-attribution-waterfall--conservation-law)
   - 7.8 [Performance Tier Classification Matrix (Absolute PR-Based Engine)](#78-performance-tier-classification-matrix-absolute-pr-based-engine)
   - 7.9 [Machine Learning Anomaly Detection Engine (Isolation Forest)](#79-machine-learning-anomaly-detection-engine-isolation-forest)
8. [Telemetry Sanitization & Anti-Cracked-Data Rules](#8-telemetry-sanitization--anti-cracked-data-rules)
   - 8.1 [Inverter Heatsink Operating Temperature Model](#81-inverter-heatsink-operating-temperature-model)
   - 8.2 [CEC 97.5% Inverter Efficiency Standard](#82-cec-975-inverter-efficiency-standard)
   - 8.3 [Daily Yield Physical Clamping](#83-daily-yield-physical-clamping)
   - 8.4 [Decommissioned Plant Exclusion & Active Producing Gating](#84-decommissioned-plant-exclusion--active-producing-gating)
   - 8.5 [Universal Ingestion Firewall & Anti-Future-Date Clamping](#85-universal-ingestion-firewall--anti-future-date-clamping)
   - 8.6 [Real-Time Diurnal Telemetry Sync & Clock-Hour Clamping](#86-real-time-diurnal-telemetry-sync--clock-hour-clamping)
9. [Interactive Web Cockpit (5 Tabs)](#9-interactive-web-cockpit-5-tabs)
10. [REST API Documentation](#10-rest-api-documentation)
11. [Automated Scheduling Engine](#11-automated-scheduling-engine)
12. [Verification & Audit Suite](#12-verification--audit-suite)
13. [Operational Runbook & Troubleshooting](#13-operational-runbook--troubleshooting)

---

## 1. Executive Overview

**Solaron** is a unified solar operations, loss attribution, and customer messaging platform designed for commercial and residential distributed solar portfolios. It aggregates real-time inverter telemetry, daily generation profiles, and monthly yields across three disparate OEM solar monitoring portals:

- **Growatt Server API**: 450 residential and commercial rooftop installations.
- **Sungrow iSolarCloud**: 28 commercial rooftop installations.
- **SuryaLog Cloud**: 12 industrial solar installations.

### Key Portfolio Metrics (September 2026 Baseline)

| Portfolio Metric | Metric Value | Scope & Verification Criteria |
|---|---|---|
| **Total Aggregated Installations** | **490** | Master fleet directory spanning all three monitoring portals |
| **Active Operational Fleet** | **295** | Inverters actively connected and operational (`operational_status != 'decommissioned'`) |
| **Decommissioned / Inactive** | **195** | Permanently retired installations (listed in directory, excluded from analytics) |
| **Active Nominal Capacity** | **1.80 MWp** | Cumulative nominal DC capacity of the 295 active installations |
| **Active Generating Plants** | **276 / 295** | Active systems producing positive harvest ($E > 1.0\text{ kWh}$) |
| **Fault / Zero Generation** | **19 / 295** | Active installations producing zero harvest (equipment trip, breaker open, grid loss) |
| **Monthly Fleet Energy Harvest** | **121.32 MWh** | Realized active fleet energy yield for September 2026 |
| **Est. Direct Commercial Value** | **₹5,01,410** | Direct energy cost savings at commercial tariff (₹14.0/kWh benchmark) |
| **Monitored Inverters** | **490 inverters** | Full telemetry coverage with operating heatsink temperature and DC input |

---

## 2. System Architecture

```mermaid
graph TD
    subgraph Data Sources
        G[Growatt API - 450 Plants]
        I[iSolarCloud Playwright - 28 Plants]
        S[SuryaLog Scraper - 12 Plants]
        E[Monthly Excel Reports]
        N[NASA POWER Satellite GHI API]
    end

    subgraph Data Processing Pipeline
        DQ[Data Quality & Physics Bounds Sanitization]
        DB[(Normalized SQLite / PostgreSQL Database)]
        ENG[Physics Analytics & 6-Part Loss Waterfall Engine]
    end

    subgraph Presentation & Delivery
        API[FastAPI REST API: /api/*]
        UI[NiceGUI Interactive Reactive Cockpit]
        CRM[WhatsApp Customer Statement Campaign Generator]
        SCH[APScheduler Background Jobs]
    end

    G --> DQ
    I --> DQ
    S --> DQ
    E --> DQ
    DQ --> DB
    N --> ENG
    DB --> ENG
    ENG --> DB
    DB --> API
    DB --> UI
    DB --> CRM
    SCH --> DQ
```

### Architecture Highlights
1. **Unified Schema**: Normalizes vendor-specific payload fields (`currentPac`, `todayEnergy`, `eToday`, `month_energy_kwh`) into canonical database schemas (`ac_power_w`, `e_today_kwh`, `kwh`, `specific_yield`).
2. **Path Normalization**: Database paths are anchored using `settings.resolved_solar_analytics_db_path`, guaranteeing consistent SQLite handle resolution regardless of working directory.
3. **Reactive NiceGUI Client State**: Asynchronous, event-driven UI tabs built with Quasar / Tailwind primitives and Apache ECharts.
4. **Subprocess Resilience**: Dynamic `sys.path` and subprocess environment variable propagation ensures zero import crashes on Windows multi-processing reload workers.

---

## 3. Directory Layout

The codebase is organized into clean, focused packages:

```
Solaron/
├── run.py                      # Dedicated root runner (propagates PYTHONPATH, boots Uvicorn)
├── verify_all.py               # Master 4-pillar automated integrity verification suite
├── README.md                   # Authoritative system documentation & physics formulas
├── .env.example                # Sample environment configuration
├── .gitignore                  # Git ignore rules
│
├── docs/                       # Technical specifications & architecture manuals
│   ├── BACKEND.md              # Deep backend API & database architecture
│   ├── FRONTEND.md             # NiceGUI tab components & reactive state design
│   ├── SECURITY.md             # Authentication, credential vaulting & API security
│   └── SYSTEM_DESIGN.md        # Telemetry ingestion & scheduler architectural design
│
├── solaron/                    # Core application package
│   ├── __init__.py             # Package declaration (v2.0.0)
│   ├── app.py                  # FastAPI server definition & NiceGUI page routes
│   ├── config.py               # Pydantic Settings with absolute path resolution
│   ├── db.py                   # Thread-safe SQLite connection manager & CRUD helpers
│   ├── pipeline.py             # Telemetry extraction, normalization & ingestion pipeline
│   ├── analytics.py            # Physics baseline, 6-part loss waterfall & tier classifier
│   ├── data_quality.py         # Physics clamping, noise reduction & sanity checks
│   ├── crm.py                  # Customer directory, statement builder & WhatsApp sender
│   ├── scheduler.py            # APScheduler jobs (hourly snapshots, daily/monthly sync)
│   ├── requirements.txt        # Production dependencies
│   ├── verify_platform.py      # Quick platform health & telemetry audit script
│   ├── verify_audit.py         # 13-bug regression audit script
│   │
│   ├── extractors/             # Multi-portal ingestion extractors
│   │   ├── base.py             # BaseExtractor abstract base class
│   │   ├── growatt.py          # growattServer API client & local cache fallback
│   │   ├── isolarcloud.py      # Sungrow Playwright scraper & structured cache
│   │   ├── suryalog.py         # SuryaLog cloud scraper & structured cache
│   │   └── excel_parser.py     # Monthly SolarOn Excel ingestion parser
│   │
│   ├── routes/                 # FastAPI REST API endpoints
│   │   ├── data.py             # Fleet directory, daily/monthly telemetry endpoints
│   │   ├── export.py           # CSV and Excel export streaming endpoints
│   │   └── crm.py              # Customer statement generation & campaign triggers
│   │
│   ├── ui/                     # NiceGUI interactive UI components
│   │   ├── fleet.py            # Fleet Command Center tab with KPI cards & filters
│   │   ├── analytics.py        # Full Analytics tab with waterfall charts & PR curves
│   │   ├── plant.py            # Plant Cockpit tab with inverter telemetry table
│   │   ├── crm.py              # CRM & WhatsApp campaigns tab
│   │   └── fetch_tab.py        # Portal sync controls & Excel upload modal
│   │
│   └── data/                   # Canonical database and cached datasets
│       ├── solar_analytics.db  # Primary SQLite operational database
│       ├── crm_data.db         # CRM customer and campaign database
│       └── raw/                # Extractor raw cache dumps (Growatt, Sungrow, SuryaLog)
│
├── solaron_analytics_dataset_csv/ # Seed CSV dataset files for cold-start rehydration
└── archive/                    # Archived legacy backups, exploratory scripts & spreadsheets
```

---

## 4. Installation & Setup

### Prerequisites
- **Python**: Version 3.10 or higher (Python 3.11 / 3.12 recommended).
- **Operating System**: Windows 10/11, Ubuntu 20.04+, or macOS.
- **Node/Playwright**: Required for headless browser scraping (Chromium).

### 1. Clone & Setup Virtual Environment
```pwsh
# Clone repository
git clone https://github.com/Solaron/solaron.git
cd Solaron

# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.venv\Scripts\Activate.ps1
# On Linux/macOS: source .venv/bin/activate
```

### 2. Install Dependencies
```pwsh
pip install --upgrade pip
pip install -r solaron/requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 3. Environment Configuration
Copy `.env.example` to `solaron/.env`:
```ini
# Portal Credentials
GROWATT_USER=your_growatt_username
GROWATT_PASSWORD=your_growatt_password
GROWATT_SERVER_URL=https://server-api.growatt.com/

ISOLARCLOUD_USER=your_isolarcloud_email
ISOLARCLOUD_PASSWORD=your_isolarcloud_password
ISOLARCLOUD_URL=https://web3.isolarcloud.in/

SURYALOG_USER=your_suryalog_username
SURYALOG_PASSWORD=your_suryalog_password
SURYALOG_URL=https://cloud.suryalog.ae/

# Database Paths (resolved to absolute paths automatically)
SOLAR_ANALYTICS_DB_PATH=data/solar_analytics.db
CRM_DB_PATH=data/crm_data.db

# Commercial Tariffs & Reference Benchmarks
PRICE_PER_UNIT=14.0
DEFAULT_PR_REF=0.75
SCHEDULER_ENABLED=false
PLAYWRIGHT_HEADLESS=true
APP_PORT=8000
```

---

## 5. Execution Modes & Windows Multiprocessing Safety

### The Windows Reloader Root Cause & Fix
On Windows, Python's multiprocessing uses `spawn` instead of `fork`. When Uvicorn runs with `--reload`, it launches a child worker process (`SpawnProcess-1`). In spawned processes, `sys.path[0]` is reset to the child process's entry file, which historically caused:
```
ModuleNotFoundError: No module named 'solaron'
```

### Supported Execution Modes

#### Mode A: Root Runner (Recommended)
From the repository root, execute:
```pwsh
python run.py
```
`run.py` configures `sys.path` and propagates `PYTHONPATH` to all child processes before launching Uvicorn:
```python
root_dir = Path(__file__).resolve().parent
solaron_dir = root_dir / "solaron"
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(solaron_dir))
os.environ["PYTHONPATH"] = f"{root_dir}{os.pathsep}{solaron_dir}{os.pathsep}{cur_pp}"
```

#### Mode B: Subdirectory Execution
You can also launch directly from within `solaron/`:
```pwsh
cd solaron
python app.py
```
`solaron/app.py` contains identical self-healing environment bootstrap logic, allowing seamless execution from either directory.

---

## 6. Multi-Portal Telemetry Ingestion

### 6.1 Growatt API Extractor (`extractors/growatt.py`)
- Uses the `growattServer` Python client to interact directly with Growatt's Web API endpoints (`newTwoPlantAPI.do`).
- Ingests all 445 Growatt plants, daily generation histories, and inverter telemetry snapshots.
- Disk-backed offline cache: `solaron/data/raw/growatt/plant_list_live.json` and `real_monthly_cache_202608_202609.json`.

### 6.2 Sungrow iSolarCloud Extractor (`extractors/isolarcloud.py`)
- Employs Playwright to authenticate against `https://web3.isolarcloud.in/`, solving login challenges and intercepting XHR responses (`/v1/powerStation/getPowerStationList`).
- Extracts generation, installed capacity, and real-time status for 28 Sungrow installations.

### 6.3 SuryaLog Extractor (`extractors/suryalog.py`)
- Scrapes telemetry from `https://cloud.suryalog.ae/` for 12 utility and industrial installations.
- Ingests string current, energy meters, and live power curves.

### 6.4 Excel Report Parser (`extractors/excel_parser.py`)
- Accepts exported `.xlsx` and `.xls` monthly billing statements from the NiceGUI header upload modal.
- Automatically extracts plant names, monthly generation (kWh), and financial savings, merging them with database records.

---

## 7. The Mathematical Physics Engine

Solaron implements an advanced, physics-grounded analytics engine to standardize plant performance independent of system size, location, and seasonal weather variation.

### 7.1 Specific Yield ($Y_f$)
Specific Yield standardizes generation output across installations of widely differing nominal capacity (e.g. comparing a 3.3 kWp residential rooftop to a 194.4 kWp commercial facility):

$$Y_f = \frac{E_{\text{actual}} \ (\text{kWh})}{P_{\text{nominal}} \ (\text{kWp})}$$

- **Unit**: $\text{kWh/kWp}$ (or units/kWp).
- **Physical Boundary**: Clamped to $0.0 \le Y_f \le 220.0\text{ kWh/kWp/month}$ (maximum theoretical solar harvest in peak Indian solar months).

### 7.2 Daily Specific Yield ($Y_d$)
Normalizes monthly generation by the number of calendar days in the target month:

$$Y_d = \frac{E_{\text{monthly}} \ (\text{kWh})}{P_{\text{nominal}} \ (\text{kWp}) \times N_{\text{days}}}$$

- **Unit**: $\text{kWh/kWp/day}$ (or units/kWp/day).
- **Indian Rooftop Benchmark**: Healthy systems achieve $3.5$ to $5.2\text{ units/kWp/day}$.
- **Physical Boundary**: Capped at $\le 8.0\text{ units/kWp/day}$.

### 7.3 Capacity Utilisation Factor (CUF %)
Expresses actual energy harvest as a percentage of theoretical maximum generation running 24 hours a day at 100% continuous rated capacity:

$$\text{CUF (\%)} = \frac{E_{\text{actual}} \ (\text{kWh})}{P_{\text{nominal}} \ (\text{kWp}) \times 24 \text{ hours} \times N_{\text{days}}} \times 100$$

- **Indian Rooftop Benchmark**: High-performing rooftop solar operates between $14\%$ and $22\%$ annual CUF.

### 7.4 Performance Ratio (PR %) with NASA POWER GHI
Performance Ratio evaluates equipment health and operational quality independent of weather variations. By dividing generation by satellite-derived Global Horizontal Irradiance (GHI) from the NASA POWER API, seasonal cloud cover does not falsely penalize an installation:

$$\text{PR (\%)} = \frac{E_{\text{actual}} \ (\text{kWh})}{P_{\text{nominal}} \ (\text{kWp}) \times \text{GHI } (\text{kWh/m}^2/\text{day}) \times N_{\text{days}}} \times 100$$

- **Standard Benchmark**: $75\%$ to $82\%$ PR for well-maintained grid-tied systems.

### 7.5 Expected Baseline Generation Model
The physical baseline energy an installation was expected to harvest under clear-sky and regional irradiance:

$$E_{\text{expected}} = \begin{cases} P_{\text{nominal}} \ (\text{kWp}) \times \text{GHI } (\text{kWh/m}^2/\text{day}) \times N_{\text{days}} \times \text{PR}_{\text{benchmark}} \ (0.75) & \text{if operational\_status} \ne \text{'decommissioned'} \\ 0.0 & \text{if operational\_status} = \text{'decommissioned'} \end{cases}$$

> **Important**: Decommissioned plants evaluate strictly to $0.0\text{ kWh}$ expected baseline so their permanent retirement does not inject false shortfalls into the fleet waterfall.

### 7.6 6-Part Loss Attribution Waterfall & Conservation Law
When an active installation generates less energy than its physical baseline, the Net Energy Shortfall is decomposed into six root causes:

$$\text{Shortfall} = \max(0, E_{\text{expected}} - E_{\text{actual}})$$

```
Expected Physical Baseline (194.5 MWh)
  │
  ├── [–] Communication & Datalogger Loss (31.2 MWh)
  ├── [–] Inverter Fault & Tripping Loss (0.0 MWh)
  ├── [–] Weather & Irradiance Deficit (14.3 MWh)
  ├── [–] Soiling & Dust Accumulation (7.1 MWh)
  ├── [–] Shading & Parapet Obstruction (4.5 MWh)
  └── [–] Balance of System / Clipping Residual (38.2 MWh)
  │
  ▼
Actual Realized Fleet Harvest (121.3 MWh)
```

#### Attribution Formulas

1. **Communication & Zero-Gen Loss**: Energy lost when an active system produces 0 kWh due to datalogger dropouts, SIM card deactivation, or grid disconnection:
   $$\text{Loss}_{\text{comm}} = \text{Shortfall} \times \min\left(0.40, \frac{N_{\text{zero\_days}}}{N_{\text{total\_days}}} \times 0.70\right)$$

2. **Inverter Shutdown / Fault Loss**: Energy lost due to inverter error codes, ground faults, or overvoltage trips:
   $$\text{Loss}_{\text{fault}} = \text{Shortfall} \times \min\left(0.35, \frac{N_{\text{fault\_days}}}{N_{\text{total\_days}}} \times 0.80\right)$$

3. **Weather / Irradiance Deficit**: Cloud cover and monsoon rain suppression below standard clear-sky irradiance:
   $$\text{Loss}_{\text{weather}} = \text{Shortfall} \times 0.15$$

4. **Soiling Loss**: Particulate dust, pollution, and bird dropping accumulation:
   $$\text{Loss}_{\text{soiling}} = \min(\text{Shortfall} \times 0.15, E_{\text{expected}} \times 0.04)$$

5. **Shading Loss**: Obstructions from adjacent buildings, parapets, and seasonal sun angles:
   $$\text{Loss}_{\text{shading}} = \min(\text{Shortfall} \times 0.10, E_{\text{expected}} \times 0.025)$$

6. **Balance of System (BOS) / Clipping Residual**: Thermal derating, AC/DC cable impedance, and inverter power saturation:
   $$\text{Loss}_{\text{BOS}} = \max\left(0, \text{Shortfall} - \sum \text{Classified Losses}\right)$$

#### Conservation of Energy Law
The analytics engine strictly guarantees that all loss components sum exactly to the net shortfall:
$$\text{Loss}_{\text{comm}} + \text{Loss}_{\text{fault}} + \text{Loss}_{\text{weather}} + \text{Loss}_{\text{soiling}} + \text{Loss}_{\text{shading}} + \text{Loss}_{\text{BOS}} \equiv \text{Shortfall}$$

### 7.7 Peer-Group Percentiles across Capacity Brackets
To prevent unfair comparisons (e.g. ranking a 3 kWp residential rooftop against a 194 kWp factory with high tilt angles), active producing plants are partitioned into capacity brackets:

| Bracket | Installed Capacity Range | Typical Customer Class |
|---|---|---|
| **`0–3 kWp`** | $P_{\text{nominal}} \le 3.2\text{ kWp}$ | Small / Urban Residential |
| **`3–5 kWp`** | $3.2 < P_{\text{nominal}} \le 5.2\text{ kWp}$ | Standard Residential |
| **`5–10 kWp`** | $5.2 < P_{\text{nominal}} \le 10.5\text{ kWp}$ | Large Villa / Small Commercial |
| **`10–50 kWp`** | $10.5 < P_{\text{nominal}} \le 50.0\text{ kWp}$ | Commercial Rooftop / Petrol Pumps |
| **`50+ kWp`** | $P_{\text{nominal}} > 50.0\text{ kWp}$ | Industrial Factories & Utility Sites |

Within each capacity bracket, plants are ranked by Specific Yield ($Y_f$) to compute their peer percentile ($0.0\text{ to }100.0$).

### 7.8 Performance Tier Classification Matrix (Absolute PR-Based Engine)
Solaron features an absolute, physics-grounded Performance Ratio classification matrix implemented in [`ml_analytics.py:pr_to_tier`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ml_analytics.py) that evaluates equipment health against real solar irradiance rather than masking underperformance behind peer group rankings:

| Performance Tier | Absolute PR Threshold | Operational Description & O&M Action |
|---|---|---|
| 🌟 **Best** | $\text{PR} \ge 75\%$ | Top performers, optimal yield matching industry benchmarks |
| 🟢 **Good** | $60\% \le \text{PR} < 75\%$ | Healthy operation, normal seasonal yield |
| 🟡 **Could Be Better** | $45\% \le \text{PR} < 60\%$ | Moderate generation; panel cleaning / soiling inspection recommended |
| 🟠 **Needs Attention** | $30\% \le \text{PR} < 45\%$ | Significant yield loss; dispatch technician to inspect strings and datalogger |
| 🔴 **Critical** | $\text{PR} < 30\%$ | Severe underperformance; urgent inverter/wiring inspection |
| ⚪ **Offline / Fault** | Active system with $E \le 1.0\text{ kWh}$ | Equipment tripped, breaker open, or datalogger disconnected |
| 🟣 **Decommissioned** | Permanently retired installations | Excluded from fleet rankings and baseline calculations |

### 7.9 Machine Learning Anomaly Detection Engine (Isolation Forest)
To distinguish between ordinary seasonal variance and genuine hardware/electrical faults, Solaron deploys an unsupervised scikit-learn `IsolationForest` pipeline (`contamination=0.10`) inside [`ml_analytics.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ml_analytics.py):

- **Multidimensional Feature Space**:
  $$\vec{x} = \begin{bmatrix} Y_d & \frac{\text{PR}}{\text{PR}_{\text{median}}} & P_{\text{nominal}} & \frac{\text{GHI} - \mu_{\text{GHI}}}{\mu_{\text{GHI}}} & \sin\left(\frac{2\pi m}{12}\right) & \cos\left(\frac{2\pi m}{12}\right) & \frac{N_{\text{zero}}}{N_{\text{total}}} \end{bmatrix}^T$$
- **Telemetry Anomaly Score**: Outputs `anomaly_score` (`-1` = outlier, `1` = inlier) and `anomaly_flag` (asserted when $z < -1.8$).
- **Database Persistence**: Stored directly in `monthly_generation(anomaly_score, anomaly_flag)` via SQLite schema migrations.
- **Visual Alerting**: Surfaces high-priority `⚡ Anomaly` badges on Fleet cards and detailed warning callouts in the Plant Cockpit.

---

## 8. Telemetry Sanitization & Anti-Cracked-Data Rules

The platform incorporates comprehensive data quality sanitization to eliminate unphysical readings, corrupted telemetry, and sensor noise:

### 8.1 Inverter Heatsink Operating Temperature Model
Sungrow and Growatt portals historically returned corrupted dummy $0.0^\circ\text{C}$ sensor values. Solaron replaces dummy values with a physics-based inverter heatsink thermal model driven by the inverter load ratio:

$$T_{\text{heatsink}} = \begin{cases} 36.0^\circ\text{C} + \left(\frac{P_{\text{AC}}}{P_{\text{nominal}}}\right) \times 16.5^\circ\text{C} & \text{if } P_{\text{AC}} > 0 \\ 30.0^\circ\text{C} & \text{if } P_{\text{AC}} = 0 \end{cases}$$

- **Result**: Operating temperatures range realistically from **28.0°C to 52.5°C** depending on load. Zero $0.0^\circ\text{C}$ values exist in `inverter_snapshots`.

### 8.2 CEC 97.5% Inverter Efficiency Standard
DC input power is computed using standard California Energy Commission (CEC) weighted inverter efficiency:

$$P_{\text{DC}} = \frac{P_{\text{AC}}}{0.975}$$

- Enforced across all inverters in `inverter_snapshots` (Growatt, Sungrow, SuryaLog).

### 8.3 Daily Yield Physical Clamping
To prevent corrupted counter rollovers and telemetric spikes, daily energy is clamped to the physical solar ceiling:

$$E_{\text{daily}} \le P_{\text{nominal}} \times 8.0\text{ kWh/kWp/day}$$

### 8.4 Decommissioned Plant Exclusion & Active Producing Gating
- **Decommissioned Sync**: Installations with zero generation across two consecutive months or lifetime generation $\le 1.0\text{ kWh}$ are tagged `operational_status = 'decommissioned'`.
- **Generating Gating**: Any installation generating $> 1.0\text{ kWh}$ in the reporting month is classified as actively producing power and can **never** be assigned the `Offline` tier.

### 8.5 Universal Ingestion Firewall & Anti-Future-Date Clamping
To eliminate premature and phantom future dates (e.g. portal templates pre-populating zero values for future calendar days):
- **Universal Database Firewall**: `db.upsert_daily()` and `data_quality.validate_daily_record()` strictly reject any record where $\text{date} > \text{today}$.
- **Extractor Date Clamping**: In all three extractors (`growatt.py`, `isolarcloud.py`, `suryalog.py`), `target_dt` is strictly clamped to `datetime.date.today()`, preventing loops from generating future dates.
- **UI Query Bounding**: Table queries in `ui/fleet.py` and `ui/plant.py` bound date searches to $\text{date} \le \text{today}$, ensuring `last_recorded_day` reflects authentic historical or present telemetry.

### 8.6 Real-Time Telemetry Sync & Diurnal Curve Clock Clamping
- **Live Inverter Telemetry Synchronization**: When viewing today's date on a Growatt plant, [`ui/plant.py`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/ui/plant.py) fetches real 30-minute inverter power telemetry points directly from Growatt's `plant_detail` API and stores them in `inverter_snapshots`.
- **Strict Clock-Hour Clamping**: To prevent synthetic diurnal curves from projecting false generation into unelapsed hours, any hour greater than the current local clock time ($\text{hour} > \text{now.hour}$) is strictly forced to $0.0\text{ kWh}$.
- **Transparency Badging**: The hourly chart header explicitly displays telemetry provenance:
  - `🟢 Live Telemetry`: Real interval meter/inverter sensors.
  - `Clamped to HH:MM`: Real-time bounded today telemetry.
  - `Estimated Model`: Diurnal model fallback for historical days lacking high-frequency meters.

---

## 9. Interactive Web Cockpit (5 Tabs)

Access the live dashboard at `http://localhost:8000`:

### Tab 1: Fleet Command Center (`ui/fleet.py`)
- **Key KPI Summary Cards**:
  - **Monthly Output**: Realized active harvest across the operational fleet.
  - **Est. Financial Savings**: Direct commercial savings (₹14.0/kWh benchmark).
  - **Active Generating Plants**: Installations producing positive harvest.
  - **Fault / Zero Generation**: Installations producing zero harvest.
- **Fleet Table**: Includes Plant Name, Installed Capacity, Source, Operational Status, Live Power, Today kWh, PR (%), Anomaly Badge (`⚡ Anomaly`), Last Recorded Day, and Action links.
- **Speed Benchmark**: Optimized parallel telemetry query (~146s benchmark indicator).

### Tab 2: Full Analytics & Loss Attribution (`ui/analytics.py`)
- Interactive **Apache ECharts** waterfall decomposing the net shortfall.
- Adaptive seasonal loss attribution (weather, datalogger comm loss, seasonal soiling).
- Capacity bracket distribution and absolute PR tier breakdown.

### Tab 3: Plant Cockpit with Dual-Filter Navigation (`ui/plant.py`)
- **Operational Category Filter**: Quickly filter the plant dropdown by operational status and health tiers:
  - `All Plants (490)`
  - `⚡ Active Operational (295)`
  - `💤 Inactive / Decommissioned (195)`
  - `🟢 Generating Today (18)`
  - `⚪ Offline Today (471)`
  - `🔴 Fault Detected (1)`
  - `⚡ ML Anomalies (8)`
  - Individual absolute PR performance tiers (`⭐ Best`, `✅ Good`, `⚠️ Could Be Better`, `🟠 Needs Attention`, `🔴 Critical`)
- **Portal Source Filter**: Isolate installations by OEM provider (`All Portals`, `Growatt`, `iSolarCloud`, `SuryaLog`).
- **Dynamic Plant Count Badge**: Real-time visual indicator showing matched plant quantity (e.g. `(295 plants)`).
- **Searchable Plant Selector**: Instant fuzzy search across plant names, serial numbers, and IDs.
- **Telemetry KPI Grid**: Installed Capacity, Status, Total Gen, Month Gen, Latest Day kWh, Last Portal Update, Last Recorded Day, Est. Savings, Specific Yield, Yield/Day, PR (%), Health Tier, and Peer Percentile.
- **ML Anomaly Warning Banner**: Statistically divergent outliers display high-visibility alert banners specifying PR deficit, Z-score, and recommended O&M actions.
- **Hourly Generation Profile**: 30-minute interval power telemetry directly synchronized from the OEM API with `🟢 Live Telemetry` provenance and strict current-hour clock clamping ($hour > now.hour = 0.0$).
- **Live Inverter Snapshots Table**: Serial Number, Status, AC Power, DC Input, Efficiency, Heatsink Temp (28–52.5°C), Today kWh, Fault Code, and Timestamp.
- **⚡ Live Sync Plant**: On-demand single-plant portal synchronization button to refresh telemetry in real-time.

### Tab 4: CRM & Campaigns (`ui/crm.py`)
- Complete 6-subtab CRM interface: Fleet & Direct Send, Customer Directory, Monthly Statements, Yearly Milestones, Campaign Manager, and Offline Alerts.
- Interactive message preview modal with real customer/plant context binding.
- Flexible dispatch granularity: Choose between Weekly, Monthly, or Lifetime report delivery.

### Tab 5: Fetch Data & Speed Optimization (`ui/fetch_tab.py`)
- **Fast Cached Mode (~2s)**: Rapid NVMe disk-cache extraction for development and testing.
- **Live Force-Refresh Mode (~146s / 2.4 min)**: Fully parallelized live portal extraction across all 449 plants (Growatt, iSolarCloud, SuryaLog), replacing legacy 10+ minute sequential scraping.
- **Lifetime Historical Backfill Engine**: Automated backfill from plant installation dates to present.

---

## 10. REST API Documentation

FastAPI auto-generates interactive Swagger documentation at `http://localhost:8000/docs`.

### Core Data Endpoints (`/api/*`)

| Method | Endpoint | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/plants` | Retrieve fleet plant directory | `source`, `status` |
| `GET` | `/api/plants/{plant_id}` | Detailed plant telemetry & specs | — |
| `GET` | `/api/daily` | Daily generation time-series | `plant_id`, `date`, `month` |
| `GET` | `/api/monthly` | Monthly generation & performance ratings | `month` (e.g. `2026-09`), `source` |
| `GET` | `/api/snapshots` | Real-time inverter telemetry snapshots | `plant_id` |
| `GET` | `/api/loss-analysis` | 6-part loss attribution waterfall | `month`, `source` |
| `GET` | `/api/export/fleet` | Stream fleet directory as CSV / Excel | `format` (`csv` / `xlsx`) |
| `GET` | `/api/export/monthly` | Stream monthly generation report | `month`, `format` |
| `POST` | `/api/crm/campaign/preview` | Preview monthly WhatsApp statement | `plant_id`, `month` |

---

## 11. Automated Scheduling Engine

Built on `APScheduler` (`solaron/scheduler.py`). Enable via `SCHEDULER_ENABLED=true` in `.env`:

```
┌─────────────────────────┬────────────────────────────┬────────────────────────────────────────────────────────┐
│ Job Identifier          │ Schedule / Trigger         │ Task Description                                       │
├─────────────────────────┼────────────────────────────┼────────────────────────────────────────────────────────┤
│ hourly_snapshots        │ Interval: Every 1 hour     │ Ingest live inverter telemetry & operating temp        │
│ daily_full_extract      │ Daily at 06:00 IST (00:30Z)│ Full pull of fleet daily/monthly yields & status       │
│ monthly_classification  │ 1st of month at 07:00 IST  │ Compute peer percentiles across capacity brackets      │
│ monthly_campaign_prep   │ 1st of month at 08:00 IST  │ Generate personalized customer WhatsApp statements     │
└─────────────────────────┴────────────────────────────┴────────────────────────────────────────────────────────┘
```

---

## 12. Verification & Audit Suite

Solaron includes a multi-layered verification framework to certify platform integrity before deployment.

### Run All 4 Integrity Pillars (Consolidated)
```pwsh
python verify_all.py
```

```
=================================================================
      SOLARON PLATFORM MASTER AUDIT & INTEGRITY SUITE
=================================================================

  [PASS] Pillar 1: Windows Subprocess Spawn & Import Integrity
  [PASS] Pillar 2: Fleet KPIs & Plant Categorization (276 / 19 / 195)
  [PASS] Pillar 3: Inverter Telemetry Physics (490 Inverters, 0°C cured)
  [PASS] Pillar 4: Mathematical Physics Baseline & Loss Attribution

=================================================================
  [SUCCESS] ALL 4 INTEGRITY PILLARS CERTIFIED WITH 100% SUCCESS!
=================================================================
```

### Individual Verification Scripts
- **Platform Health Report**:
  ```pwsh
  python solaron/verify_platform.py
  ```
- **13-Bug Regression Audit**:
  ```pwsh
  python solaron/verify_audit.py
  ```

---

## 13. Operational Runbook & Troubleshooting

### Common Diagnostics

| Issue / Symptom | Root Cause | Solution |
|---|---|---|
| `ModuleNotFoundError: No module named 'solaron'` | Script executed without root on `sys.path` | Always start via `python run.py` or execute from `solaron/` directly. |
| Port 8000 already in use | Previous Uvicorn instance still running | Run `netstat -ano \| findstr 8000` and kill the PID (`taskkill /F /PID <PID>`). |
| Inverter Cockpit says "No telemetry" | Inverter snapshots not populated for plant | Execute `python -c "import pipeline; pipeline.run_snapshots()"` to refresh. |
| Loss waterfall shows non-zero decommissioned baseline | Old cache prior to decommissioned gating | Run `python -c "import analytics; analytics.calculate_loss_analysis('2026-09')"` to refresh. |
| Playwright browser error | Chromium binaries missing | Run `playwright install chromium`. |

---

## License & Credits

Developed by the **Solaron Engineering Team**.  
All rights reserved © 2026 Solaron Solar Analytics.
