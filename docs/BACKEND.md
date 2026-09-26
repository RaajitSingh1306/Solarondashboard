# Solaron — Backend

## app.py — Entry Point

```
FastAPI app
  ├── include_router(data_router)     prefix /api
  ├── include_router(export_router)   prefix /api
  ├── include_router(crm_router)      prefix /api/crm
  ├── startup event → db.init_db()
  ├── startup event → scheduler.start()  (if SCHEDULER_ENABLED)
  └── ui.run_with(app, port=8000)     NiceGUI mounts here
```

One process, one port. NiceGUI handles the browser UI; FastAPI handles the REST API.
Both are served from the same ASGI app via `ui.run_with`.

---

## REST API Reference

### Data endpoints — routes/data.py

| Method | Endpoint                        | Returns                                                        |
|--------|---------------------------------|----------------------------------------------------------------|
| GET    | `/api/fleet`                    | All 485 plants + latest daily row + tier. Filter: `?source=` `?status=` |
| GET    | `/api/plant/{plant_id}`         | Full cockpit: metadata, 30-day daily, 12-month monthly, inverter table, tier |
| GET    | `/api/live`                     | Latest inverter snapshots + fleet active/offline/fault counts  |
| GET    | `/api/ratings/current`          | Tier distribution + rated plant list, current month           |
| GET    | `/api/ratings/monthly/{month}`  | Tier distribution + rated plant list, specific YYYY-MM        |
| GET    | `/api/fleet/status`             | Status counts. `?alerts_only=true` returns only offline/fault  |

### Export endpoints — routes/export.py

| Method | Endpoint                        | Returns                                      |
|--------|---------------------------------|----------------------------------------------|
| GET    | `/api/export/fleet-daily`       | All plants × date range rows. `?fmt=csv\|xlsx` `?start=` `?end=` |
| GET    | `/api/export/fleet-monthly`     | All plants × monthly summary. `?fmt=` `?month=` |
| GET    | `/api/export/fleet-status`      | Current status snapshot (for Freshworks/Gupshup). `?fmt=` |
| GET    | `/api/export/ratings`           | Performance tiers all plants. `?fmt=` `?month=` |
| GET    | `/api/export/plant-daily`       | One plant daily history. `?plant_id=` `?fmt=`   |
| GET    | `/api/export/plant-monthly`     | One plant monthly history. `?plant_id=` `?fmt=` |
| GET    | `/api/export/customers`         | CRM directory. `?fmt=`                          |
| GET    | `/api/export/campaign`          | Campaign messages + phones. `?campaign_id=` `?fmt=` |

All export endpoints:
- Default `fmt=csv` → `text/csv` StreamingResponse
- `fmt=xlsx` → `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Use `pandas + openpyxl` for XLSX; `pandas.to_csv` for CSV
- `Content-Disposition: attachment; filename={resource}.{fmt}`

### CRM endpoints — routes/crm.py

| Method | Endpoint                              | Description                                     |
|--------|---------------------------------------|-------------------------------------------------|
| GET    | `/api/crm/customers`                  | Customer list (pagination, platform filter, search) |
| POST   | `/api/crm/customers`                  | Add or update customer (map plant to phone)     |
| GET    | `/api/crm/customers/{id}`             | Profile + generation history + campaign history |
| POST   | `/api/crm/customers/import`           | Bulk CSV import of customer contacts            |
| GET    | `/api/crm/campaigns`                  | Past campaigns with message counts              |
| POST   | `/api/crm/campaigns/prepare`          | Queue a monthly campaign (all opted-in customers)|
| POST   | `/api/crm/campaigns/{id}/export`      | Export campaign messages as CSV for BSP         |
| GET    | `/api/crm/offline`                    | Plants offline > threshold. `?hours=4`          |
| POST   | `/api/crm/offline/prepare-alerts`     | Queue alert campaign with cooldown filter       |
| GET    | `/api/crm/statements`                 | Generate monthly/yearly statement for customer  |

### Scheduler endpoints

| Method | Endpoint                    | Description                              |
|--------|-----------------------------|------------------------------------------|
| GET    | `/api/scheduler/status`     | Job list + last run time + next run time |
| POST   | `/api/scheduler/trigger`    | Trigger immediate full extract           |

---

## Extractors

All in `extractors/`. All implement `BaseExtractor`.

### BaseExtractor contract

```
login()              → authenticate with platform
fetch_fleet()        → List[plant_dict]      matches plants schema
fetch_daily(date)    → List[daily_dict]      matches daily_generation schema
fetch_monthly(month) → List[monthly_dict]    matches monthly_generation schema
fetch_snapshots()    → List[snapshot_dict]   matches inverter_snapshots schema
```

Static helpers on BaseExtractor:
- `safe_float(val)` — parse numeric field, return None on null/empty/dash
- `normalize_status(raw)` — map platform codes → `active | offline | fault | unknown`
- `plant_id(raw_id)` — prefix: `growatt_12345`, `isc_Name`, `syr_Name`

### GrowattExtractor

Library: `growattServer` (pip). No Playwright.

Key API calls:
```
api.login(user, pw)
api.plant_list()                   → all plants with todayEnergy, currentPower
api.plant_info(plant_id)           → monthEnergy, nominal_Power, lat, lon, city
api.device_list(plant_id)          → inverters per plant
api.inverter_detail(device_sn)     → pac, ppv, eToday, temperature, faultCode
api.plant_detail(plant_id, 2, date)→ monthly energy data
```

Throttle: 50ms sleep between calls. Full fleet pull ~25s.

Status codes: `deviceStatus` — 0=offline, 1=active, 3=fault

### ISolarCloudExtractor

Library: Playwright (headless Chromium).

Flow:
1. Navigate to `https://pro.isolarcloud.com.hk`
2. Fill login form → submit
3. Intercept XHR responses from `/api/plant/getPlantList` and `/api/plant/details`
4. Parse JSON from intercepted requests
5. Navigate to each plant page → intercept monthly energy XHR

Fields from XHR JSON:
- `plantStatus` (Normal/Abnormal/Offline), `installedCapacity_kWp`
- `yieldToday_kWh`, `currentPower_kW`, `netRevenue`
- Monthly: `energyAnalysis` array for selected date range
- Inverter: `deviceName`, `deviceSN`, `deviceStatus`, `dailyGeneration_kWh`, `totalActivePower_kW`

28 plants. Full pull ~90s.

### SuryaLogExtractor

Library: Playwright (headless Chromium).

Flow:
1. Navigate to `https://cloud.suryalog.ae`
2. Login with credentials
3. Navigate to Reports → Generation Report
4. Set date range (today / current month)
5. Click Export CSV button → `page.wait_for_download()`
6. Parse downloaded CSV with pandas
7. Fallback: DOM scrape from plant list page if export fails

Native fields (unique to SuryaLog): `performanceRatio_pct`, `specificYield`, `stringCurrent_1..14`, `soilingLevel_pct`

12 plants. Pull ~60s.

---

## pipeline.py

Single module replacing the old `normalizer.py + db_manager.py + orchestrator.py`.

Functions:
```
run_fleet()                     pull + upsert plant metadata, all 3 platforms
run_daily(date=None)            pull + upsert today's daily rows, all 3 platforms
run_monthly(month=None)         pull + upsert monthly rows, all 3 platforms
run_snapshots()                 pull + upsert live inverter snapshots, all 3 platforms
run_full_extract(month=None)    fleet → daily → monthly → snapshots (full cron job)
seed_from_csv_exports(dir)      one-time seed from existing CSV exports
```

`run_full_extract` is what the daily cron calls.
`seed_from_csv_exports` is run once manually to populate the DB without hitting portals.

### Normalisation rules

1. All kwh values: ensure they are positive floats; set `None` if zero or missing
2. `capacity_kwp`: if API returns watts (>100), divide by 1000
3. `live_power_kw`: if API returns watts (>500 for a single plant), divide by 1000
4. `specific_yield`: always calculated as `kwh / capacity_kwp` unless native (SuryaLog)
5. `status`: always normalised through `BaseExtractor.normalize_status()`
6. `plant_id`: always `{source}_{raw_id}` — guaranteed unique across all 3 platforms
7. `revenue_inr`: set `None` if platform does not provide it (not calculated)

---

## analytics.py

Consolidates `loss_engine.py + performance_classifier.py + metrics.py + nasa_power.py` (4 old files → 1).

### Performance classifier

```
classify_all(month)          classify all active plants for a month → write tier
classify_plant(plant_id, month) → (tier, percentile, explanation)
```

Classification pipeline:
1. Pull all `monthly_generation` rows where `kwh > 0` for the month
2. Filter out `offline` / `fault` plants (from `daily_generation.status`)
3. Group by source (Growatt / iSolarCloud / SuryaLog) as peer group
4. Rank by `specific_yield` within peer group → percentile 0–100
5. Map percentile → tier using bins [0, 15, 30, 55, 80, 100]
6. Return tier label + percentile + human-readable explanation string

### NASA POWER GHI (for Growatt + iSolarCloud PR calculation)

```
get_ghi(lat, lon, month)     → float (kWh/m²/day)
calc_pr(kwh, capacity_kwp, ghi, days_in_month) → float (0–1)
```

API: `https://power.larc.nasa.gov/api/temporal/monthly/point`
Parameters: `lat`, `lon`, `parameters=ALLSKY_SFC_SW_DWN`, `community=RE`

Rounding: coordinates rounded to 0.5° to cache GHI values and reduce API calls.
Rate limit: 5s sleep between NASA calls, results cached in memory for the run.

### Metrics

```
specific_yield(kwh, kwp)     → kwh/kwp
cuf(kwh, kwp, hours)         → capacity utilisation factor
revenue(kwh, tariff_inr)     → estimated revenue
co2_saved(kwh)               → kg CO₂ (India grid factor 0.82 kgCO₂/kWh)
```

---

## scheduler.py

Single APScheduler `BackgroundScheduler`. Replaces both old scheduler files.

```python
scheduler.add_job(pipeline.run_snapshots,     'interval', hours=1)
scheduler.add_job(pipeline.run_full_extract,  'cron', hour=0, minute=30)  # 06:00 IST
scheduler.add_job(analytics.classify_all,     'cron', day=1, hour=1, minute=30)  # 07:00 IST 1st
scheduler.add_job(crm.prepare_monthly_campaign,'cron', day=1, hour=2, minute=30) # 08:00 IST 1st
```

Start: `scheduler.start()` called in FastAPI `startup` event.
Shutdown: `scheduler.shutdown()` called in FastAPI `shutdown` event.

Gate: `if settings.scheduler_enabled: scheduler.start()` — set `SCHEDULER_ENABLED=false` in `.env` for local dev to avoid portal calls on every restart.

---

## db.py

```
analytics_conn()         context manager → sqlite3.Connection to solar_analytics.db
crm_conn()               context manager → sqlite3.Connection to crm_data.db
query_df(sql, params, db)→ pd.DataFrame  (SELECT helper)
execute(sql, params, db) → rowcount      (DML helper)
executemany(sql, rows)   → rowcount      (batch DML)
upsert_plant(row)        → None
upsert_daily(rows)       → int
upsert_monthly(rows)     → int
upsert_snapshots(rows)   → int
init_db()                → create all tables + indexes if not exist
```

All upserts use `INSERT ... ON CONFLICT DO UPDATE SET` (SQLite upsert syntax).
`query_df` returns empty DataFrame (not None) when no rows match — callers should check `.empty`.

PostgreSQL switch: set `DATABASE_URL` env var. `db.py` detects it and uses `psycopg2` instead of `sqlite3`. Query placeholders change from `?` to `%s` — handled in `db.py` transparently.
