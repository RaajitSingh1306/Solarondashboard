# 🛠️ Solaron Platform Re-creation Master Task List & Blueprint

> **A Complete Phased Engineering Curriculum to Build Solaron From Scratch**  
> **Target Architecture:** Python 3.10+ · FastAPI · NiceGUI (Quasar/Tailwind) · SQLite + DuckDB/Parquet · Playwright · Scikit-Learn · AWS S3 · Gupshup WhatsApp API

This document is your step-by-step master roadmap to re-create the entire Solaron Solar Telemetry Intelligence & CRM platform from an empty directory. Each phase builds upon previous layers, providing concepts to study, specific actionable tasks, required file locations, code signatures, verification tests, and critical pitfalls.

---

## 🗺️ Architectural Phase Map

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 0: Project Setup, Tooling & Environment Configuration                 │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Database Architecture, SQLite Schemas & Pandera Data Contracts     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 2: Ingestion Layer & Multi-OEM Telemetry Extractors                   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 3: Raw Medallion Bronze Lake & AWS S3 Cloud Archiving                 │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 4: Data Quality, Sanitization Firewall & Indian Pincode Geocoding     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 5: Solar Physics Baseline & Peer-Relative Performance Index (RPI)     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 6: Conserved 6-Part Loss Attribution Waterfall & Revenue Modeling     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 7: Machine Learning Anomaly Detection (Isolation Forest) & PR Tiers   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 8: Columnar OLAP Lake (DuckDB + Parquet) & S3 Database Backups        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 9: Multi-Lingual WhatsApp CRM & 6-Stage Escalation State Machine (FSM)│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 10: FastAPI REST Endpoints & Multi-Format Report Export Engine        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 11: Interactive Operations Cockpit UI (NiceGUI, Quasar & ECharts)    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 12: Automated Verification, 4-Pillar Master Audit & CI Certification  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Project Inception, Environment & Tooling

### 🎯 Learning Objectives
- Master environment isolation using Python virtual environments (`venv`).
- Configure type-safe application settings using `pydantic-settings`.
- Set up Windows Proactor Event Loop compatibility for asynchronous tasks (`Playwright`, `FastAPI`).

### 📋 Checklist
- [ ] Initialize git repository and configure `.gitignore` (ignoring `.venv/`, `*.db`, `data/raw/`, `data/lake/`, `.env`).
- [ ] Create `requirements.txt` containing core platform dependencies:
  - Web & API: `fastapi`, `uvicorn[standard]`, `nicegui`
  - Validation & Config: `pydantic`, `pydantic-settings`, `python-dotenv`
  - Data & Analytics: `pandas`, `openpyxl`, `pyarrow`, `scikit-learn`
  - Ingestion: `requests`, `growattServer`, `playwright`, `apscheduler`
  - Database: `duckdb` (or `psycopg2-binary` if connecting to external Postgres)
- [ ] Create `pyproject.toml` with tool settings and packaging metadata.
- [ ] Create `.env.example` documenting all configuration keys:
  - Portal credentials: `GROWATT_USER`, `GROWATT_PASSWORD`, `SUNGROW_USER`, `SUNGROW_PASSWORD`, `SURYALOG_USER`, `SURYALOG_PASSWORD`
  - WhatsApp: `GUPSHUP_API_KEY`, `GUPSHUP_APP_NAME`
  - AWS S3: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`
  - Application: `PRICE_PER_UNIT=14.0`, `PORT=8080`, `SCHEDULER_ENABLED=False`
- [ ] Implement `config.py` using `pydantic_settings.BaseSettings`:
  - Define resolved database paths for `solar_analytics.db` and `crm_data.db`.
  - Add path resolution helpers for `DATA_DIR`, `RAW_DIR`, and `LAKE_ROOT`.

### 🧪 Verification Checkpoint
```pwsh
python -c "from config import settings; print('Config loaded successfully. DB Path:', settings.resolved_solar_analytics_db_path)"
```

---

## Phase 1: Database Architecture & Data Contracts

### 🎯 Learning Objectives
- Design decoupled relational schemas separating Operational Analytics (`solar_analytics.db`) from CRM State (`crm_data.db`).
- Understand Pandera schema validation to catch bad telemetry at the ingestion boundary.
- Implement an **Ingestion Firewall** to reject forward dates and negative generation numbers.

### 📋 Checklist
- [ ] Create `pipeline/db.py` to manage SQLite connections:
  - Use `sqlite3.connect` with `check_same_thread=False` and `timeout=30.0`.
  - Implement WAL mode (`PRAGMA journal_mode=WAL;`) for high-concurrency read/write operations.
  - Implement table creation functions for `solar_analytics.db`:
    - `plants`: `(plant_id TEXT PRIMARY KEY, source TEXT, plant_name TEXT, capacity_kwp REAL, latitude REAL, longitude REAL, city TEXT, install_date TEXT, inverter_model TEXT, operational_status TEXT, updated_at TIMESTAMP)`
    - `daily_generation`: `(plant_id TEXT, date TEXT, kwh REAL, revenue_inr REAL, specific_yield REAL, yield_per_day REAL, live_power_kw REAL, status TEXT, quality_flags TEXT, source_type TEXT, PRIMARY KEY (plant_id, date))`
    - `monthly_generation`: `(plant_id TEXT, month TEXT, kwh REAL, revenue_inr REAL, specific_yield REAL, pr_pct REAL, tier TEXT, anomaly_score REAL, anomaly_flag INTEGER, PRIMARY KEY (plant_id, month))`
    - `inverter_snapshots`: `(plant_id TEXT, inverter_sn TEXT, snapshot_ts TEXT, ac_power_w REAL, dc_power_w REAL, temperature_c REAL, e_today_kwh REAL, fault_code TEXT, status TEXT, PRIMARY KEY (plant_id, inverter_sn, snapshot_ts))`
    - `loss_analysis`: `(plant_id TEXT, month TEXT, expected_kwh REAL, actual_kwh REAL, shortfall_kwh REAL, loss_comm_kwh REAL, loss_fault_kwh REAL, loss_weather_kwh REAL, loss_soiling_kwh REAL, loss_shading_kwh REAL, loss_unknown_kwh REAL, PRIMARY KEY (plant_id, month))`
  - Implement table creation functions for `crm_data.db`:
    - `customers`: `(id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT UNIQUE, customer_name TEXT, phone TEXT, email TEXT, preferred_lang TEXT, opt_in_status INTEGER)`
    - `escalation_state`: `(id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT UNIQUE, customer_id INTEGER, category TEXT, current_level TEXT, state_status TEXT, visit_charge_inr REAL, service_status TEXT, updated_at TIMESTAMP)`
    - `escalation_log`: `(id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT, from_level TEXT, to_level TEXT, trigger_reason TEXT, message_template TEXT, gupshup_msg_id TEXT, created_at TIMESTAMP)`
    - `gupshup_inbound_log`: `(id INTEGER PRIMARY KEY AUTOINCREMENT, raw_payload TEXT, mobile TEXT, message_text TEXT, button_payload TEXT, timestamp TIMESTAMP)`
- [ ] Create `core/contracts.py`:
  - Define Pandera DataFrame schemas for daily telemetry:
    - `plant_id`: string, non-null
    - `date`: string, regex format `^\d{4}-\d{2}-\d{2}$`, check `date <= today`
    - `kwh`: float, non-negative, $\le \text{capacity\_kwp} \times 12.0$ (physical max solar hours)
    - `specific_yield`: float, $0.0 \le Y_f \le 8.5\text{ kWh/kWp/day}$
- [ ] Enforce SQLite boundary validation:
  - Add validation guards in `pipeline/db.py`: `save_daily_generation()` must filter out any record where `record['date'] > datetime.date.today().isoformat()`.

### 🧪 Verification Checkpoint
- Run `tests/test_contracts.py` to confirm Pandera rejects forward dates, negative generation, and missing plant identifiers.

---

## Phase 2: Ingestion Layer & Multi-OEM Telemetry Extractors

### 🎯 Learning Objectives
- Build resilient extractors across heterogeneous OEM protocols (REST APIs, Web3 Session Scraping, Excel).
- Handle OEM quirks: Growatt Watts-to-kWp conversion ($W / 1000$), Sungrow token expiration, and SuryaLog export parsing.

### 📋 Checklist
- [ ] Create `extractors/base.py`:
  - Define `BaseExtractor` abstract interface with methods:
    - `login() -> bool`
    - `get_plant_list() -> List[Dict[str, Any]]`
    - `get_daily_generation(plant_id, date) -> Dict[str, Any]`
    - `get_monthly_generation(plant_id, month) -> Dict[str, Any]`
    - `get_inverter_snapshots(plant_id) -> List[Dict[str, Any]]`
- [ ] Create `extractors/growatt.py`:
  - Use `growattServer` library or direct HTTP calls to `https://server.growatt.com/` endpoints.
  - Implement session management, rate-limiting backoff, and pagination.
  - Convert capacity units: `capacity_kwp = float(nominalPower) / 1000.0`.
  - Fetch 30-minute diurnal live curves (`get_energy_overview` or `get_plant_power_data`).
- [ ] Create `extractors/isolarcloud.py`:
  - Use `Playwright` headless browser to authenticate against `https://www.isolarcloud.com/`.
  - Handle cookie consent and token capture.
  - Extract commercial site list and interval inverter telemetry.
- [ ] Create `extractors/suryalog.py`:
  - Ingest from AE Cloud API or parse native exported CSV/JSON reports.
  - Extract PR metrics and irradiance values.
- [ ] Create `extractors/excel_parser.py`:
  - Support manual file uploads in the UI when cloud APIs experience outages.
  - Parse plant names, billing cycles, monthly generation, and meter readings from `.xlsx` files.

### 🧪 Verification Checkpoint
```pwsh
python -c "from extractors.excel_parser import parse_excel_generation; print('Excel parser ready')"
```

---

## Phase 3: Raw Medallion Bronze Lake & AWS S3 Cloud Archiving

### 🎯 Learning Objectives
- Understand the **Medallion Data Lake Architecture** (Bronze = raw immutable, Silver = cleansed relational, Gold = feature aggregates).
- Implement SHA-256 content deduplication and date-partitioned storage.
- Implement AWS S3 cloud archiving with anti-overwrite safety guards (`overwrite_if_empty_only = True`).

### 📋 Checklist
- [ ] Create `pipeline/bronze.py`:
  - Create directory layout: `data/lake/bronze/source={source}/ingest_date={YYYY-MM-DD}/`.
  - Generate deterministic filenames: `{endpoint}_{HHMMSS}_{sha256[:12]}.json.gz`.
  - Compress JSON payloads with `gzip`.
  - Track ingestion metadata in a bronze catalog table or index file.
- [ ] Create `services/s3_archive.py`:
  - Initialize `boto3.client('s3')` with credentials from `config.py`.
  - Implement `upload_bronze_file(local_path, s3_key)`.
  - Implement **Anti-Overwrite Guard**:
    ```python
    def upload_safely(s3_client, bucket, key, data):
        try:
            head = s3_client.head_object(Bucket=bucket, Key=key)
            if head.get('ContentLength', 0) > 0:
                return {"status": "preserved_existing", "key": key}
        except ClientError:
            pass # Object does not exist, proceed with upload
        s3_client.put_object(Bucket=bucket, Key=key, Body=data)
        return {"status": "uploaded", "key": key}
    ```
  - Implement online atomic SQLite database backup to S3 (`sqlite3.backup` API).
- [ ] Create `pipeline/pipeline.py`:
  - Master pipeline orchestrator coordinating:
    `Extract -> Write to Bronze Lake -> Validate Contract -> Upsert to SQLite -> Mirror to S3`.

### 🧪 Verification Checkpoint
- Run `tests/test_bronze.py` to confirm files are gzipped, SHA-256 hashed, and S3 anti-overwrite preserves existing non-empty files.

---

## Phase 4: Data Quality, Sanitization & Pincode Geocoding

### 🎯 Learning Objectives
- Solve missing telemetry location data in distributed solar portfolios.
- Build an Indian 6-digit postal code (`\b\d{6}\b`) regex extractor and Nominatim geocoder with disk caching.
- Build automated stuck-sensor and frozen-value detectors to prevent data corruption.
- Implement the thermodynamic heatsink load model to eradicate dummy `0.0°C` inverter temperatures.

### 📋 Checklist
- [ ] Create `services/geocode.py`:
  - Extract Indian postal codes from raw `plantAddress` fields using `re.search(r'\b\d{6}\b', address)`.
  - Map pincode to coordinates using a local cached JSON dictionary (`data/pincode_cache.json`).
  - Fall back to OpenStreetMap Nominatim API (rate-limited at $\le 1$ req/sec).
  - Assign `geocode_level`: `'PINCODE'`, `'CITY'`, `'STATE'`, or `'DEFAULT'`.
  - Update `latitude` and `longitude` in the `plants` table.
- [ ] Create `core/data_quality.py`:
  - Implement **Stuck Value Detector**:
    - Identify when a plant logs identical non-zero kWh (within $\pm 0.1\text{ kWh}$) on $\ge 3$ consecutive days while its regional peers vary by $>10\%$.
    - Tag record with `quality_flags = 'STUCK_VALUE'`.
    - Exclude stuck days from monthly PR and baseline aggregations.
  - Implement **Thermodynamic Heatsink Temperature Model**:
    $$T_{\text{heatsink}} = \begin{cases} 36.0^\circ\text{C} + \left(\frac{P_{\text{AC}}}{P_{\text{nominal}}}\right) \times 16.5^\circ\text{C} & \text{if } P_{\text{AC}} > 0 \\ 30.0^\circ\text{C} & \text{if } P_{\text{AC}} = 0 \end{cases}$$
    - Clamp temperatures to the physical band $[28.0^\circ\text{C}, 52.5^\circ\text{C}]$.
  - Implement **Decommissioned / Ghost Plant Classifier**:
    - Identify plants with `deviceCount == 0` or lifetime generation $\le 0.0\text{ kWh}$.
    - Mark `operational_status = 'decommissioned'` and exclude from operational fleet rankings.

### 🧪 Verification Checkpoint
- Run `tests/test_stuck_flag.py` and `tests/test_geocode.py` to ensure pincodes geocode properly and stuck sensors are flagged.

---

## Phase 5: Solar Physics & Peer-Relative Performance Index (RPI)

### 🎯 Learning Objectives
- Compute foundational solar engineering metrics: Specific Yield ($Y_f$), Daily Yield ($Y_d$), Performance Ratio ($PR$), Capacity Utilisation Factor ($CUF$), and CEA $CO_2$ offsets.
- Solve the **"No Pyranometer Problem"**: implement the **Peer-Relative Performance Index (RPI)** using neighboring healthy solar plants as a distributed solar sensor.
- Fix the **31-Day Denominator Bug**: implement dynamic elapsed day normalization ($D_{\text{eval}}$) for ongoing calendar months.

### 📋 Checklist
- [ ] Create `core/analytics.py` & `engines/physics.py`:
  - Calculate Specific Yield:
    $$Y_f = \frac{E_{\text{actual}} \ [\text{kWh}]}{P_{\text{nominal}} \ [\text{kWp}]}$$
  - Calculate Normalized Daily Specific Yield:
    $$Y_d = \frac{E_{\text{actual}}}{P_{\text{nominal}} \times D_{\text{eval}}}$$
    Where $D_{\text{eval}} = \min(\text{today.day}, D_{\text{total}})$ for the current month.
  - Calculate Performance Ratio ($PR$):
    $$PR = \frac{E_{\text{actual}}}{P_{\text{nominal}} \times GHI \times D_{\text{eval}}} \times 100\%$$
  - Calculate Capacity Utilisation Factor ($CUF$):
    $$CUF = \frac{E_{\text{actual}}}{P_{\text{nominal}} \times 24 \times D_{\text{eval}}} \times 100\%$$
  - Calculate Environmental Carbon Offsets:
    $$CO_2 \ [\text{kg}] = E_{\text{actual}} \times 0.82\text{ kg CO}_2/\text{kWh}$$
- [ ] Create `core/peer_group.py`:
  - Implement hierarchical geographic peer grouping:
    - **Level 1 (City)**: Plants in the same city (requires $\ge 5$ healthy producing peers).
    - **Level 2 (District/Prefix)**: Same 2/3-digit pincode prefix ($\ge 5$ peers).
    - **Level 3 (State)**: State-wide cohort (e.g. Maharashtra, Gujarat).
    - **Level 4 (Fleet)**: Fleet-wide fallback.
- [ ] Create `engines/rpi.py`:
  - Compute healthy peer reference yield for day $d$:
    $$ref[G, d] = \text{Median}_{j \in G, \text{healthy}}(Y_f[j, d])$$
  - Calculate plant Daily RPI:
    $$RPI[i, d] = \frac{Y_f[i, d]}{ref[G, d]}$$
  - Calculate 14-day rolling median RPI score to classify health.

### 🧪 Verification Checkpoint
- Run `tests/test_peer_rpi.py` and `tests/test_pr_reconciliation.py`. Verify hand-calculated PR values match the engine outputs.

---

## Phase 6: Conserved 6-Part Loss Attribution Waterfall

### 🎯 Learning Objectives
- Implement the First-Principles Solar Conservation Law:
  $$\sum_{i=1}^6 L_i \equiv \text{Net Energy Shortfall}$$
- Decompose shortfall into 6 physical causes: Communication ($L_{\text{comm}}$), Inverter Faults ($L_{\text{fault}}$), Weather Deficit ($L_{\text{weather}}$), Seasonal Soiling ($L_{\text{soiling}}$), Structural Shading ($L_{\text{shading}}$), and Residual BOS ($L_{\text{unknown}}$).

### 📋 Checklist
- [ ] Create `engines/lost_revenue.py`:
  - Calculate Net Energy Shortfall:
    $$S = \max(0.0, E_{\text{expected}} - E_{\text{actual}})$$
    Where $E_{\text{expected}} = P_{\text{nominal}} \times GHI \times D_{\text{eval}} \times 0.75$.
  - Implement Loss Component Equations:
    1. $L_{\text{comm}} = S \times \min\left(0.60, \frac{N_{\text{zero\_days}}}{D_{\text{eval}}} \times 0.85\right)$
    2. $L_{\text{fault}} = S \times \min\left(0.40, \frac{N_{\text{fault\_days}}}{D_{\text{eval}}} \times 0.90\right)$
    3. $L_{\text{weather}} = S \times \min(0.45, \max(0.08, \text{Deficit} \times 0.75))$
    4. $L_{\text{soiling}} = \min(S \times 0.20, E_{\text{expected}} \times \text{SOILING\_FACTOR}[m])$
    5. $L_{\text{shading}} = \min(S \times 0.10, E_{\text{expected}} \times 0.02)$
    6. $L_{\text{unknown}} = S - \sum_{k=1}^5 L_k$ (with scaling clamp if $\sum L_k > S$)
  - Calculate Financial Value of Losses:
    $$\text{Lost Revenue } [₹] = L_i \times \text{Tariff } [₹/\text{kWh}]$$
  - Save loss decomposition records into `solar_analytics.db -> loss_analysis`.

### 🧪 Verification Checkpoint
- Run `tests/test_phase6_physics.py` to confirm the conservation identity $\left|\sum_{i=1}^6 L_i - S\right| < 10^{-6}$ holds true for all records.

---

## Phase 7: Machine Learning Anomaly Detection & PR Tiers

### 🎯 Learning Objectives
- Build an unsupervised machine learning pipeline using scikit-learn `IsolationForest`.
- Engineer feature vectors with cyclical month encoding ($\sin / \cos$) to account for Indian monsoons.
- Implement the **Dual-Gate Filter** to prevent false alarms on high-performing solar arrays.
- Establish absolute IEEE/IEC solar health tiers.

### 📋 Checklist
- [ ] Create `core/ml_analytics.py`:
  - Construct the 5-dimensional feature vector for producing plants ($E_{\text{month}} > 1.0\text{ kWh}$):
    $$\vec{x} = \begin{bmatrix} Y_d \\ PR \\ P_{\text{nominal}} \\ \sin\left(\frac{2\pi \cdot (m - 1)}{12}\right) \\ \cos\left(\frac{2\pi \cdot (m - 1)}{12}\right) \end{bmatrix}$$
  - Train `IsolationForest(contamination=0.08, n_estimators=100, random_state=42)`.
  - Implement **Dual-Gate Anomaly Filter**:
    An anomaly is asserted IF AND ONLY IF geometrically isolated in feature space AND underperforming relative to cohort median:
    $$\text{Anomaly Flag} = 1 \iff (\text{raw\_pred} = -1) \land (Y_d < \text{Median}_m(Y_d))$$
  - Classify plants into **Absolute Physical PR Tiers**:
    - ⭐ **Best**: $PR \ge 75.0\%$
    - ✅ **Good**: $60.0\% \le PR < 75.0\%$
    - ⚠️ **Could Be Better**: $45.0\% \le PR < 60.0\%$
    - 🟠 **Needs Attention**: $30.0\% \le PR < 45.0\%$
    - 🔴 **Critical**: $PR < 30.0\%$
    - ⚪ **Offline / Zero**: $E_{\text{month}} \le 1.0\text{ kWh}$

### 🧪 Verification Checkpoint
- Run `tests/test_phase5_evaluation.py` to confirm high-performing plants are never flagged as anomalies.

---

## Phase 8: Columnar OLAP Lake (DuckDB + Parquet)

### 🎯 Learning Objectives
- Bridge relational row-oriented storage (SQLite) with ultra-fast analytical columnar storage (DuckDB + Parquet).
- Build the Medallion Silver and Gold analytical layers.

### 📋 Checklist
- [ ] Create `core/analytics_lake.py`:
  - Implement `export_sqlite_to_parquet()`:
    - Attach SQLite database inside in-memory DuckDB connection (`conn.execute("ATTACH 'solar_analytics.db' AS sqlite_db (TYPE SQLITE);")`).
    - Export `plants` $\rightarrow$ `data/lake/silver/plants_dim.parquet`.
    - Export `daily_generation` $\rightarrow$ `data/lake/silver/daily_fact.parquet`.
    - Export `inverter_snapshots` $\rightarrow$ `data/lake/silver/snapshots_fact.parquet`.
  - Build Gold Feature Mart:
    - Aggregate daily metrics $\rightarrow$ `data/lake/gold/plant_day_features.parquet`.
    - Aggregate monthly metrics $\rightarrow$ `data/lake/gold/plant_month_summary.parquet`.
  - Implement high-speed vectorized analytical query helpers for dashboard aggregations.

### 🧪 Verification Checkpoint
- Run `tests/test_analytics_lake.py` to verify parquet generation and DuckDB aggregation queries.

---

## Phase 9: Multi-Lingual WhatsApp CRM & Escalation State Machine

### 🎯 Learning Objectives
- Implement an automated 6-stage Customer Relationship Management (CRM) Finite State Machine (FSM).
- Format localized solar generation and loss statements in **English, Hindi, and Marathi**.
- Interface with the Gupshup WhatsApp Business API and parse webhook callbacks.

### 📋 Checklist
- [ ] Create `templates/escalation_messages.py`:
  - Define message copy for stages L1 through L6 across `english`, `hindi`, and `marathi`.
  - Include variables: `{{customer_name}}`, `{{plant_name}}`, `{{month}}`, `{{kwh}}`, `{{savings_inr}}`, `{{co2_kg}}`, `{{loss_inr}}`.
- [ ] Create `engines/escalation_state_machine.py`:
  - Implement 6-stage lifecycle transitions:
    - `L1_TRIGGER`: Detect severe underperformance ($PR < 30\%$) or inverter fault.
    - `L2_INFO_SENT`: Dispatch performance diagnosis statement.
    - `L3_CHECK_SENT`: Send self-check guide (checking breakers, dust, tree branches).
    - `L4_OFFER_SENT`: Dispatch certified technician inspection offer with pricing.
    - `L5_DECISION`: Capture customer WhatsApp button response (`YES` $\rightarrow$ create work order, `NO` $\rightarrow$ log grace period).
    - `L6_RECHECK`: Monitor generation 7 days post-inspection to certify recovery.
  - Log every transition immutably into `crm_data.db -> escalation_log`.
- [ ] Create `services/gupshup.py`:
  - Implement `send_whatsapp_template(phone, template_id, params, language)`.
  - Implement fallback to direct text messaging if templates are pending approval.
- [ ] Create `services/crm.py`:
  - Customer directory CRUD operations, monthly statement generator, and milestone campaign dispatchers.

### 🧪 Verification Checkpoint
- Run `tests/test_escalation.py` and `tests/test_crm_phone.py` to verify the FSM transitions and multilingual template formatting.

---

## Phase 10: FastAPI REST APIs & Export Services

### 🎯 Learning Objectives
- Expose operational data via clean, OpenAPI-documented REST endpoints.
- Build streaming export services for CSV, Excel (`openpyxl`), and JSON.
- Handle Gupshup inbound webhook callbacks.

### 📋 Checklist
- [ ] Create `routes/data.py`:
  - `GET /api/plants`: Returns all monitored solar installations with capacity, coordinates, and health status.
  - `GET /api/daily`: Returns daily telemetry filtered by date and plant ID.
  - `GET /api/monthly`: Returns monthly summaries with PR and anomaly scores.
  - `GET /api/loss-attribution`: Returns 6-part waterfall breakdowns.
- [ ] Create `routes/export.py`:
  - `GET /api/export/csv`: Stream daily or monthly records as formatted CSV.
  - `GET /api/export/excel`: Generate styled Excel workbooks with formulas and summary sheets using `openpyxl`.
- [ ] Create `routes/crm.py` & `routes/gupshup_webhook.py`:
  - `POST /api/crm/escalate`: Trigger manual or batch state machine transitions.
  - `POST /api/gupshup/webhook`: Inbound webhook endpoint capturing customer button clicks and inbound WhatsApp replies.

### 🧪 Verification Checkpoint
- Run `tests/test_export.py` to verify CSV and Excel file generation integrity.

---

## Phase 11: Interactive Operations Cockpit UI (NiceGUI)

### 🎯 Learning Objectives
- Build a responsive, high-performance solar cockpit in Python using NiceGUI (wrapping Quasar and Tailwind CSS).
- Integrate Apache ECharts for interactive diurnal power curves and waterfall loss visualizations.
- Implement shared reactive application state across navigation tabs.

### 📋 Checklist
- [ ] Create `app.py` & `run.py`:
  - Configure FastAPI lifespan to initialize SQLite tables and start APScheduler.
  - Mount REST routers and configure dark-mode dashboard styling (`#0B0F19` dark palette).
  - Manage shared reactive state (`month`, `source`, `selected_plant`).
- [ ] Create `ui/fetch_tab.py` (Tab 1: Telemetry Fetch Workbench):
  - Ingestion mode selector: **⚡ Fast Cache (~2s)** vs. **🔄 Force Refresh (Live Scrape)**.
  - Portal selector (`All`, `Growatt`, `iSolarCloud`, `SuryaLog`).
  - Historical lifetime backfill launcher and Excel upload modal.
- [ ] Create `ui/fleet.py` (Tab 2: Fleet Command Center):
  - Top KPI cards: Total Harvest (MWh), Realized Revenue (₹), Active Generating Sites, Fault Suspects.
  - Category filters: `All (491)`, `Active (295)`, `Decommissioned (196)`, `Fault Detected (21)`.
  - Quasar data table with sorting, PR progress bars, anomaly tags, and cockpit deep-links.
- [ ] Create `ui/analytics.py` (Tab 3: Full Fleet Analytics & Loss Waterfall):
  - Apache ECharts 6-part loss attribution waterfall chart.
  - Daily specific yield ($Y_d$) and Performance Ratio ($PR$) distribution histograms.
  - PR Health Tier distribution cards.
- [ ] Create `ui/plant.py` (Tab 4: Plant Deep-Dive Cockpit):
  - 13 Real-time KPI cards ($Y_f, Y_d, PR, CUF$, Savings, $CO_2$).
  - **30-Minute Diurnal Inverter Curve**: Live power curve clamped to current clock hour.
  - Real-time Inverter Table: Serial number, AC/DC power, heatsink temperature ($28-52.5^\circ\text{C}$), today kWh, fault codes.
- [ ] Create `ui/crm.py` (Tab 5: CRM Operations & WhatsApp Dispatch):
  - 6 dedicated sub-tabs: Direct Dispatch, Customer Directory, Statements, Milestones, Campaigns, Offline Alerts.
  - In-app WhatsApp message modal with live parameter preview in English, Hindi, and Marathi.

### 🧪 Verification Checkpoint
- Launch the application:
  ```pwsh
  python run.py
  ```
- Open `http://localhost:8080` in browser and verify all 5 tabs render with zero frontend console errors.

---

## Phase 12: Automated Verification, 4-Pillar Audit & CI Certification

### 🎯 Learning Objectives
- Implement automated regression testing covering data integrity, physics bounds, ML anomalies, and subprocess execution.
- Build a Master Audit Runner verifying platform integrity in a single command.

### 📋 Checklist
- [ ] Create `tests/test_comprehensive_suite.py`:
  - Implement 37 automated unit and integration tests across 7 core classes:
    - `TestDatabaseIntegrity` (6 tests)
    - `TestDataQualityAndSanitization` (6 tests)
    - `TestSolarPhysicsAndPR` (5 tests)
    - `TestMachineLearningAndAnomalyDetection` (5 tests)
    - `TestLossWaterfallConservation` (5 tests)
    - `TestPipelineAndSpeedBenchmarks` (4 tests)
    - `TestCRMAndStatementGeneration` (6 tests)
- [ ] Create `tests/verify_all.py`:
  - Build the **4-Pillar Master Platform Audit**:
    - **Pillar 1:** Windows Subprocess Spawn & Import Integrity
    - **Pillar 2:** Fleet KPIs & Plant Categorization (274 Generating / 21 Tripped / 196 Decommissioned)
    - **Pillar 3:** Inverter Telemetry Physics (491 inverters, heatsink thermal band, 0 cracked values)
    - **Pillar 4:** Mathematical Physics Baseline & Loss Attribution Conservation

### 🧪 Master Verification Execution
```pwsh
python tests/verify_all.py
python tests/test_comprehensive_suite.py
```
**Success Criteria:** 4/4 Pillars Passed · 37/37 Tests Passed (100% Pass Rate).

---

## 🏆 Project Completion & Definition of Done

When all 12 phases are complete, your Solaron re-creation will feature:
1. **Multi-Source Ingestion**: Automated extraction from Growatt, Sungrow, SuryaLog, and Excel.
2. **Bronze Data Lake**: Immutable date-partitioned JSON raw archiving with AWS S3 mirroring.
3. **Automated Data Quality**: Pincode geocoding, stuck sensor detection, and physical temperature modeling.
4. **First-Principles Solar Physics**: Conserved 6-part loss attribution waterfall and dynamic PR normalization.
5. **Peer-Relative Performance Index (RPI)**: Statistical peer normalization overcoming absent on-site pyranometers.
6. **Unsupervised Anomaly Detection**: Isolation Forest pipeline identifying true electrical and hardware defects.
7. **Multi-Lingual CRM State Machine**: 6-stage WhatsApp escalation workflow in English, Hindi, and Marathi.
8. **Responsive Operations Cockpit**: 5 interactive dark-mode NiceGUI tabs with Apache ECharts.
