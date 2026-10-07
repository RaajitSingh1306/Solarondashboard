# Solaron — Solar Operations, Telemetry & CRM Platform

> **Version:** 2.3.0 · **Python:** 3.10+ · **Stack:** FastAPI + NiceGUI (Quasar / Tailwind CSS) + SQLite  
> **Integrated Inverter Portals:** Growatt Server API, Sungrow iSolarCloud, SuryaLog Cloud  
> **Fleet Scope:** 491 Monitored Solar Sites (2.29 MWp Active Operational Capacity)

---

## ⚡ Overview

**Solaron** is an enterprise solar operations, telemetry intelligence, and CRM communication platform built for distributed rooftop and commercial solar portfolios across India. It unifies telemetry across heterogeneous OEM portals, provides physics-based performance ratio (PR) and loss attribution models, detects operational anomalies using unsupervised machine learning, and automates multi-lingual customer communications via Gupshup WhatsApp.

---

## 🚀 Key Features

- **Multi-Portal Extraction Engine**: Automated data connectors for Growatt, Sungrow iSolarCloud, and SuryaLog with session caching and robust retry handlers.
- **Solar Physics & Baseline Modeling**: Specific yield ($Y_f$), Daily Yield ($Y_d$), NASA POWER GHI benchmarks, and temperature-corrected Performance Ratio (PR %).
- **Adaptive 6-Part Loss Waterfall**: Mathematically conserved loss attribution categorizing Grid Outages, Inverter Clipping, Soiling, Thermal Degradation, Shading, and Curtailment.
- **Machine Learning Health Scoring**: Isolation Forest anomaly detection identifying underperforming arrays, stuck inverters, and degraded strings.
- **Interactive Operations Cockpit**: NiceGUI-powered web interface featuring Fleet Command, Plant Deep-Dives, Loss Attribution, and Live Generation Curves.
- **Multi-Lingual CRM & WhatsApp Dispatch**: Automated customer notifications and escalation campaigns across English, Hindi, and Marathi.

---

## 📂 Project Organization

```text
Solarondashboard/
├── app.py                     # Main NiceGUI & FastAPI web application
├── run.py                     # Server launcher with Windows multiprocess support
├── config.py                  # Global application settings & environment loader
├── core/                      # Solar physics, baseline, ML anomaly detection & metrics
├── engines/                   # Escalation state machine, loss waterfall & physics engine
├── extractors/                # Portal telemetry extractors (Growatt, Sungrow, SuryaLog)
├── pipeline/                  # Ingestion orchestration, bronze storage & database schemas
├── routes/                    # FastAPI endpoints (data, CRM, export, webhooks)
├── services/                  # CRM operations, geocoding, Gupshup API & scheduler
├── templates/                 # Message templates & multi-lingual WhatsApp copy
├── ui/                        # NiceGUI tabs (Fleet, Plant Cockpit, Analytics, CRM, Fetch)
├── scripts/                   # Administrative and capacity audit utilities
├── tests/                     # Comprehensive test & verification suites
├── data/                      # Local storage (.gitkeep, reference pincodes)
└── docs/                      # In-depth architectural & operational documentation
```

---

## 🛠️ Quick Start

### 1. Prerequisites
- Python 3.10 or higher
- Git

### 2. Environment Setup
```bash
# Clone or navigate into directory
cd Solarondashboard

# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Credentials
Copy the example environment file and fill in API credentials:
```bash
cp .env.example .env
```
Key configuration items:
- `GROWATT_USER`, `GROWATT_PASSWORD`: Growatt portal credentials
- `SUNGROW_USER`, `SUNGROW_PASSWORD`: Sungrow iSolarCloud credentials
- `SURYALOG_USER`, `SURYALOG_PASSWORD`: SuryaLog Cloud credentials
- `GUPSHUP_API_KEY`, `GUPSHUP_APP_NAME`: WhatsApp messaging credentials

### 4. Run the Application
```bash
python run.py
```
The interactive cockpit will be accessible at: **`http://localhost:8080`**

---

## 🧪 Testing & Verification

Run the consolidated platform integrity and regression tests:

```bash
# Run the master audit suite
python tests/verify_all.py

# Run the comprehensive test suite
python tests/test_comprehensive_suite.py

# Run the temporal granularity verification
python tests/test_granularity_verification.py
```

---

## 📚 In-Depth Documentation

Detailed architectural and engineering guides are located in the [`docs/`](docs/) directory:

- [**Tab & Cockpit Specifications** (`docs/TAB_INFO.md`)](docs/TAB_INFO.md) — Exhaustive guide to all 5 cockpit tabs, KPIs, and controls.
- [**Physics & Mathematical Formulations** (`docs/DATA_DOCUMENT.md`)](docs/DATA_DOCUMENT.md) — Equations, PR benchmarks, and loss waterfall conservation.
- [**System Design & Ingestion Topology** (`docs/SYSTEM_DESIGN.md`)](docs/SYSTEM_DESIGN.md) — ETL pipelines, multi-portal sync, and scheduling.
- [**Backend API Reference** (`docs/BACKEND.md`)](docs/BACKEND.md) — REST endpoints, database schema, and validation rules.
- [**Frontend Architecture** (`docs/FRONTEND.md`)](docs/FRONTEND.md) — NiceGUI reactive components and ECharts integration.
- [**Security & Compliance** (`docs/SECURITY.md`)](docs/SECURITY.md) — Secret handling, rate limits, and network isolation.
- [**WhatsApp Template Guide** (`docs/GUPSHUP_TEMPLATES_GUIDE.md`)](docs/GUPSHUP_TEMPLATES_GUIDE.md) — Gupshup template specifications and copy.

---

## 📄 License

Proprietary — All rights reserved © 2026 Solaron Homes Pvt Ltd.
