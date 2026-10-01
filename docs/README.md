# 📚 Solaron Platform Technical Documentation Hub

Welcome to the Solaron Platform technical documentation repository. This directory contains detailed architectural specifications, solar physics formulations, component walkthroughs, and operational runbooks.

---

## Documentation Index

| Document | File Link | Target Audience & Purpose |
|:---|:---|:---|
| **Exhaustive Tab Guide** | [`TAB_INFO.md`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/TAB_INFO.md) | **Operators & Frontend Engineers.** Detailed breakdown of every tab, sub-tab, 13 Cockpit KPIs, filter dropdowns, live curves, and WhatsApp campaign modals. |
| **Master Platform Specification** | [`DATA_DOCUMENT.md`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/DATA_DOCUMENT.md) | **Solar Engineers & Data Scientists.** Empirical baselines, mathematical solar physics ($Y_f, Y_d, PR$), Isolation Forest ML pipeline, 6-part loss attribution waterfall, and resolved engineering issues. |
| **System Design Architecture** | [`SYSTEM_DESIGN.md`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/SYSTEM_DESIGN.md) | **System Architects.** Multi-portal ingestion topologies (Growatt REST, Sungrow Web3, SuryaLog AE), pipeline stages, and concurrent scheduling. |
| **Backend Architecture** | [`BACKEND.md`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/BACKEND.md) | **Backend Engineers.** FastAPI REST API endpoints, SQLite schema migrations, data sanitization firewalls, and pipeline orchestrators. |
| **Frontend Architecture** | [`FRONTEND.md`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/FRONTEND.md) | **Frontend Engineers.** NiceGUI component hierarchy, client-side reactive state management, Tailwind styling, and Apache ECharts integration. |
| **Security & Compliance** | [`SECURITY.md`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/docs/SECURITY.md) | **DevOps & SecOps.** Credential isolation, encrypted environment storage, network firewalls, and rate-limiting protocols. |

---

## Key Platform Specifications at a Glance

- **Aggregated Fleet Scope**: 491 Solar Installations (451 Growatt, 28 Sungrow iSolarCloud, 12 SuryaLog Cloud).
- **Active Operational Fleet**: 295 Installations (2.29 MWp) actively monitored.
- **Decommissioned / Inactive**: 196 Installations (122.4 kWp) dynamically detected from OEM server attributes & SQLite.
- **Data Quality & Telemetry Refresh**: Force-refresh queries live OEM portals, overwrites raw disk caches (`data/raw/`), updates SQLite, and powers subsequent cache-mode runs with fresh data.
- **Loss Attribution**: 6-part conservation-law-compliant waterfall ($\sum_{i=1}^6 L_i \equiv \text{Net Shortfall}$).
- **Inverter Telemetry**: 89,227 snapshots, heatsink thermal model (28.0°C–52.5°C), 0 cracked records.

---

## 🧪 Automated Testing & Verification Suite

All platform audits and test suites are consolidated under the [`tests/`](file:///c:/Users/raaji/Downloads/Solaron/Solarondashboard/tests) directory:

| Test Script | Execution Command | Scope & Verification Coverage |
|:---|:---|:---|
| **Master Platform Audit** | `python tests/verify_all.py` | 4 Core Pillars: Windows subprocesses, fleet KPIs (274/21/196), inverter physics (0°C cure), and thermodynamic loss conservation. |
| **Comprehensive Test Suite** | `python tests/test_comprehensive_suite.py` | 37 automated test cases spanning data ingestion, schemas, physics bounds, ML anomalies, CRM messaging, and REST API contracts. |
| **Granularity & Cadence Test** | `python tests/test_granularity_verification.py` | Verifies multi-temporal scale hierarchy (Daily $\le$ Weekly $\le$ Monthly $\le$ Yearly) and WhatsApp formatting across 3 languages. |

