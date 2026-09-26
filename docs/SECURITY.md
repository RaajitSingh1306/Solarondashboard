# Solaron — Security

## Credential Handling Rules

1. No credentials in source code — ever. Not even in comments.
2. No credentials in git history. `.env` is in `.gitignore` from day one.
3. All secrets loaded at startup via `config.py` (Pydantic-settings reads from `.env`).
4. If a credential appears in a log line, that is a bug.
5. Production credentials live in Render environment variables, never in files.

---

## .env.example

Commit this file. It documents what variables are required without exposing values.

```
# ── Growatt ───────────────────────────────────────────────────────
GROWATT_USER=
GROWATT_PASSWORD=

# ── iSolarCloud ───────────────────────────────────────────────────
ISOLARCLOUD_USER=
ISOLARCLOUD_PASSWORD=

# ── SuryaLog ──────────────────────────────────────────────────────
SURYALOG_USER=
SURYALOG_PASSWORD=

# ── Database ──────────────────────────────────────────────────────
# Leave blank for local SQLite. Set for Supabase PostgreSQL.
DATABASE_URL=
SOLAR_ANALYTICS_DB_PATH=data/solar_analytics.db
CRM_DB_PATH=data/crm_data.db

# ── Messaging (WhatsApp BSP) ──────────────────────────────────────
AISENSY_API_KEY=
FRESHWORKS_API_KEY=
GUPSHUP_API_KEY=
SUPPORT_PHONE=

# ── App ───────────────────────────────────────────────────────────
SCHEDULER_ENABLED=true
PLAYWRIGHT_HEADLESS=true
APP_PORT=8000
```

---

## config.py Pattern

All variables accessed through one Pydantic-settings class. This gives type validation,
missing-variable errors at startup (not at runtime), and a single import surface.

```python
# config.py — do not read os.environ directly anywhere else in the codebase

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    growatt_user: str
    growatt_password: str
    isolarcloud_user: str
    isolarcloud_password: str
    suryalog_user: str
    suryalog_password: str
    database_url: str = ""
    solar_analytics_db_path: str = "data/solar_analytics.db"
    crm_db_path: str = "data/crm_data.db"
    scheduler_enabled: bool = True
    playwright_headless: bool = True
    app_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

`config.py` is the only file that touches `.env`. Every other module imports `settings`.

---

## Playwright Session Security

Both iSolarCloud and SuryaLog extractors use Playwright with real portal credentials.

**Risks and mitigations:**

| Risk | Mitigation |
|---|---|
| Browser profile stored on disk | Use `browser_type.launch_persistent_context` with a temp dir; clean up after each run |
| Session cookies written to disk | Set `storage_state=None`, do not persist between runs — re-login each extraction |
| Screenshot/video captures leaking credentials | Disable recording: `record_video=None`, `record_har=None` |
| Headless detection by portal → block | Set realistic `user_agent`, `viewport`, and add `time.sleep()` between actions |
| Playwright process crash leaving browser open | Wrap in `async with` context manager; always call `browser.close()` in `finally` |

```python
# Safe pattern for Playwright context
async with async_playwright() as pw:
    browser = await pw.chromium.launch(headless=settings.playwright_headless)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 ...",
        viewport={"width": 1280, "height": 800},
        record_video=None,
        record_har=None,
    )
    try:
        page = await context.new_page()
        # ... extraction logic ...
    finally:
        await context.close()
        await browser.close()
```

---

## API Rate Limiting

All three portals are shared production systems. Hammering them risks account suspension.

| Platform    | Strategy                                              |
|-------------|-------------------------------------------------------|
| Growatt     | 50ms sleep between each plant API call (`time.sleep(0.05)`) |
| iSolarCloud | 1–2s between page navigations; batch plant list in one XHR |
| SuryaLog    | 1s between actions; export trigger is a single request |
| NASA POWER  | 5s sleep between calls; batch by coordinate rounding to reduce calls |

These are hard-coded in each extractor, not configurable. Do not remove the sleeps.

---

## FastAPI Endpoint Security

Current deployment is internal (LAN / Render private service). If exposed publicly:

- Add `fastapi-limiter` (Redis-backed) or `slowapi` for per-IP rate limiting on `/api/*`
- Add `python-jose` JWT auth on all write endpoints (`/api/crm/*`, `/api/scheduler/trigger`)
- CORS: restrict `allow_origins` to your Render frontend domain, not `["*"]`
- Add `X-API-Key` header check for the export endpoints if sharing the URL externally

```python
# Minimal API key check for export endpoints
from fastapi import Header, HTTPException
import secrets

API_KEY = settings.export_api_key  # add to .env

def verify_api_key(x_api_key: str = Header(...)):
    if not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(403, "Invalid API key")
```

---

## WhatsApp / BSP Credentials

AiSensy, Freshworks, and Gupshup API keys are in `.env` only.
They are never logged, never returned in API responses, and never stored in the DB.

WhatsApp message content (customer name, phone, generation data) is also sensitive:
- Phone numbers are stored in `crm_data.db` (local, not committed)
- Phone numbers are never returned in GET `/api/fleet` — only in CRM-specific endpoints
- Campaign CSVs exported for BSP ingestion contain phone numbers — treat as PII, do not email unencrypted

---

## Database Security

**Local SQLite:**
- `data/` directory is in `.gitignore`
- Both `.db` files contain customer PII (phone numbers) and portal credentials are not stored in them, but customer data is
- Do not commit, do not sync to cloud storage unencrypted

**Supabase PostgreSQL (production):**
- Connection string in `DATABASE_URL` env var only
- Use connection pooler (port 6543, pgBouncer) — not direct port 5432
- Enable Row Level Security on the `customers` table in Supabase
- Rotate the DB password after initial setup and store the new one in Render env vars

---

## .gitignore Entries Required

```
.env
data/
*.db
exports/
__pycache__/
.playwright/
playwright/.auth/
*.log
```

Verify with `git status` before every commit. If any `.db` or `.env` file appears as untracked, add it before pushing.

---

## Incident Response

If portal credentials are accidentally committed to GitHub:

1. Rotate the credential immediately on the platform (Growatt / iSolarCloud / SuryaLog portal)
2. Force-push a cleaned history: `git filter-branch` or BFG Repo Cleaner
3. If the repo is public, assume the credential is compromised regardless of how fast you act
4. Revoke any API keys (AiSensy, Freshworks) that were exposed
5. Check `git log --all --full-history -- .env` to confirm the file is gone from all commits
