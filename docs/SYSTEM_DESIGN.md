# Solaron — System Design

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│                                                                 │
│  Growatt ShineServer     iSolarCloud          SuryaLog Cloud   │
│  growattServer lib       Playwright XHR       Playwright CSV    │
│  445 plants              28 plants            12 plants         │
└──────────┬───────────────────┬──────────────────┬──────────────┘
           │                   │                  │
           └───────────────────┼──────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    extractors/      │
                    │  base.py contract   │
                    │  fetch → normalize  │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │    pipeline.py      │
                    │  normalize → upsert │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼──────────────────┐
           ▼                   ▼                  ▼
  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐
  │    plants      │  │daily_generation│  │monthly_generation  │
  │   485 rows     │  │  ~43k rows     │  │   ~5.8k rows       │
  └────────────────┘  └────────────────┘  └────────────────────┘
                                          ┌────────────────────┐
                                          │inverter_snapshots  │
                                          │  hourly rolling    │
                                          └────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    analytics.py     │
                    │  classifier+metrics │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼──────────────────┐
           ▼                   ▼                  ▼
     routes/data.py      routes/export.py    routes/crm.py
           │                   │                  │
           └───────────────────┼──────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  FastAPI  port 8000 │
                    │  NiceGUI mounted    │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
          /api/*           / (NiceGUI)        /docs
          JSON REST        4-tab dashboard    Swagger
```

---

## Data Flow

### Daily cron (06:00 IST — full extract)

```
scheduler.py → pipeline.run_full_extract()
    │
    ├── GrowattExtractor.fetch_fleet()      → upsert plants
    ├── GrowattExtractor.fetch_daily()      → upsert daily_generation
    ├── GrowattExtractor.fetch_monthly()    → upsert monthly_generation
    │
    ├── ISolarCloudExtractor.fetch_fleet()  → upsert plants
    ├── ISolarCloudExtractor.fetch_daily()  → upsert daily_generation
    ├── ISolarCloudExtractor.fetch_monthly()→ upsert monthly_generation
    │
    ├── SuryaLogExtractor.fetch_fleet()     → upsert plants
    ├── SuryaLogExtractor.fetch_daily()     → upsert daily_generation  (with native PR)
    └── SuryaLogExtractor.fetch_monthly()   → upsert monthly_generation (with native PR)
```

### Hourly cron (live status)

```
scheduler.py → pipeline.run_snapshots()
    │
    ├── GrowattExtractor.fetch_snapshots()     → upsert inverter_snapshots
    ├── ISolarCloudExtractor.fetch_snapshots() → upsert inverter_snapshots
    └── SuryaLogExtractor.fetch_snapshots()    → upsert inverter_snapshots
```

### Monthly cron (1st of month, 07:00 IST)

```
scheduler.py → analytics.classify_all(month)
    → reads monthly_generation for all 485 plants
    → ranks by specific_yield within capacity bracket + source
    → updates tier column
    → triggers CRM monthly campaign preparation
```

### Dashboard request flow

```
Browser → NiceGUI page load
    → ui/ tab component calls fetch('/api/...')
    → routes/data.py queries DB
    → returns JSON → NiceGUI renders table/chart
    → Export button → window.location = /api/export/...
    → routes/export.py → pandas → StreamingResponse (CSV or XLSX)
```

---

## Database Schema

Two SQLite files. Swap both to PostgreSQL via `DATABASE_URL` env var for production.

### solar_analytics.db

```
plants
  plant_id TEXT PK          "growatt_12345" | "isc_Name" | "syr_Name"
  source TEXT               growatt | isolarcloud | suryalog
  plant_name TEXT
  capacity_kwp REAL
  latitude REAL
  longitude REAL
  city TEXT
  install_date TEXT
  inverter_model TEXT
  panel_model TEXT
  updated_at TEXT

daily_generation
  plant_id TEXT FK
  date TEXT                 'YYYY-MM-DD'
  kwh REAL                  today's generation
  revenue_inr REAL
  specific_yield REAL       kwh / capacity_kwp (native for SuryaLog)
  live_power_kw REAL
  status TEXT               active | offline | fault
  PK (plant_id, date)

monthly_generation
  plant_id TEXT FK
  month TEXT                'YYYY-MM'
  kwh REAL
  revenue_inr REAL
  specific_yield REAL
  pr_pct REAL               native for SuryaLog; NASA POWER calc for others
  PK (plant_id, month)

inverter_snapshots
  plant_id TEXT FK
  inverter_sn TEXT
  snapshot_ts TEXT          ISO datetime
  ac_power_w REAL
  dc_power_w REAL
  temperature_c REAL
  e_today_kwh REAL
  fault_code TEXT
  status TEXT
  PK (plant_id, inverter_sn, snapshot_ts)
```

### crm_data.db

```
customers
  id INTEGER PK AUTOINCREMENT
  plant_id TEXT UNIQUE      FK to solar_analytics.plants
  customer_name TEXT
  phone TEXT
  email TEXT
  preferred_lang TEXT       english | hindi | marathi
  opt_in_status TEXT        active | pending | do_not_send

campaign_log
  id INTEGER PK AUTOINCREMENT
  campaign_name TEXT
  month TEXT
  status TEXT               PENDING | SENT | FAILED
  total_messages INTEGER
  sent_count INTEGER
  failed_count INTEGER

message_queue
  id INTEGER PK AUTOINCREMENT
  campaign_id INTEGER FK
  customer_id INTEGER FK
  phone TEXT
  message_text TEXT
  language TEXT
  status TEXT               PENDING | SENT | FAILED | SKIPPED

alert_send_log
  id INTEGER PK AUTOINCREMENT
  plant_id TEXT
  alert_type TEXT           offline | fault
  sent_at TEXT
  cooldown_hours INTEGER    24 for offline, 6 for fault
```

---

## Field Mapping — Platform → Schema

| Schema field     | Growatt                     | iSolarCloud               | SuryaLog                     |
|------------------|-----------------------------|---------------------------|------------------------------|
| `kwh` (daily)    | `todayEnergy`               | `yieldToday_kWh`          | `generationToday_kWh`        |
| `kwh` (monthly)  | `monthEnergy`               | energyAnalysis (month)    | `generationMonth_kWh`        |
| `live_power_kw`  | `currentPower / 1000`       | `currentPower_kW`         | `currentPower_kW`            |
| `status`         | `deviceStatus` (0/1/3 int)  | Normal/Abnormal/Offline   | Normal/Fault/Offline         |
| `capacity_kwp`   | `nominal_Power / 1000`      | `installedCapacity_kWp`   | `installedCapacity_kWp`      |
| `revenue_inr`    | `formulaMoney × eToday`     | `netRevenue`              | `revenueToday`               |
| `specific_yield` | calculated                  | calculated                | **native** `specificYield`   |
| `pr_pct`         | NASA POWER calculation      | NASA POWER calculation    | **native** `performanceRatio_pct` |
| `ac_power_w`     | `pac` (W)                   | `totalActivePower_kW×1000`| `acPower_kW×1000`            |
| `temperature_c`  | `temperature`               | —                         | `inverterTemp_C`             |
| `fault_code`     | `faultCode` (int)           | Abnormal status           | `alarmType` (string)         |

Status normalisation: all platform codes → `active | offline | fault | unknown`

---

## Performance Tier Classification

Two-layer system in `analytics.py`:

**Layer 1 — Operational filter**
Plants with status `offline` or `fault` skip percentile ranking → assigned `Offline` / `Fault` tier directly.

**Layer 2 — Peer-group percentile**
Active plants ranked by `specific_yield` within their source group (Growatt plants vs Growatt plants, etc.). Capacity bracket applied as secondary grouping where data is sufficient.

| Tier             | Percentile band |
|------------------|----------------|
| Best             | P80 – P100     |
| Good             | P55 – P80      |
| Could Be Better  | P30 – P55      |
| Needs Attention  | P15 – P30      |
| Critical         | P0  – P15      |

---

## Scheduling Cadence

| Job                         | Schedule            | Function                          |
|-----------------------------|---------------------|-----------------------------------|
| Hourly live status          | Every 60 min        | `pipeline.run_snapshots()`        |
| Daily full extract          | 06:00 IST           | `pipeline.run_full_extract()`     |
| Monthly classification      | 1st of month 07:00  | `analytics.classify_all(month)`   |
| Monthly CRM campaign prep   | 1st of month 08:00  | `crm.prepare_monthly_campaign()`  |

Scheduler runs inside the FastAPI process via APScheduler (BackgroundScheduler).
`SCHEDULER_ENABLED=true` env var gates it — disable for local dev if needed.

---

## Extractor Strategy

| Platform    | Method                     | Auth           | Speed       | Notes                               |
|-------------|----------------------------|----------------|-------------|-------------------------------------|
| Growatt     | `growattServer` lib (REST) | username/pw    | ~25 s total | No browser. Most reliable.          |
| iSolarCloud | Playwright XHR intercept   | username/pw    | ~90 s total | 28 plants. Register Basic API later.|
| SuryaLog    | Playwright CSV trigger     | username/pw    | ~60 s total | Clicks Export button, parses download. Falls back to DOM scrape. |

All three extractors implement `BaseExtractor`. `pipeline.py` calls them uniformly.
