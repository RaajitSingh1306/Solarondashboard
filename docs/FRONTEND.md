# Solaron — Frontend (NiceGUI)

## Why NiceGUI

NiceGUI is a Python UI framework that runs on top of FastAPI/Starlette.
The entire dashboard is written in Python — no separate HTML, no JavaScript files, no build step.
It mounts onto the existing FastAPI app via `ui.run_with(app)`.

**What this means:**
- All tab logic, chart configs, and table data are Python code in `ui/`
- NiceGUI converts them to Vue.js + Quasar components in the browser
- Chart.js charts are configured as Python dicts passed to `ui.chart()`
- `@ui.refreshable` makes components reactive — rerun the function to re-render
- `ui.timer()` polls API endpoints for live data without page reload

---

## Integration with FastAPI

```python
# app.py (abbreviated)
from fastapi import FastAPI
from nicegui import ui
from ui.fleet     import fleet_page
from ui.analytics import analytics_page
from ui.plant     import plant_page
from ui.crm       import crm_page

app = FastAPI()

# include all route routers
app.include_router(data_router)
app.include_router(export_router)
app.include_router(crm_router)

@ui.page('/')
def dashboard():
    build_dashboard()

ui.run_with(app, port=8000)   # one process, one port
```

NiceGUI serves the UI at `/` and all its websocket/static routes automatically.
FastAPI REST endpoints remain at `/api/*` and `/docs`.

---

## ui/ Directory Structure

```
ui/
├── fleet.py        Tab 1 — all 485 plants table, filters, export
├── analytics.py    Tab 2 — 4 charts, date range, platform filter
├── plant.py        Tab 3 — plant search, KPI cards, sparklines, inverter table
└── crm.py          Tab 4 — customer list, campaign prep, alert export
```

Each file exports a single `build_*_tab()` function called from `app.py`.

---

## app.py — Dashboard Shell

```python
@ui.page('/')
def dashboard():
    ui.dark_mode().enable()   # dark theme

    # Header
    with ui.header().classes('bg-gray-900 text-white px-6 py-3'):
        ui.label('☀️ Solaron').classes('text-xl font-bold')
        ui.space()
        ui.label('485 plants · Growatt · iSolarCloud · SuryaLog').classes('text-sm text-gray-400')

    # Tab navigation
    with ui.tabs().classes('w-full bg-gray-800') as tabs:
        t_fleet     = ui.tab('Fleet',     icon='solar_power')
        t_analytics = ui.tab('Analytics', icon='analytics')
        t_plant     = ui.tab('Plant',     icon='eco')
        t_crm       = ui.tab('CRM',       icon='contacts')

    with ui.tab_panels(tabs, value=t_fleet).classes('w-full p-4'):
        with ui.tab_panel(t_fleet):
            build_fleet_tab()
        with ui.tab_panel(t_analytics):
            build_analytics_tab()
        with ui.tab_panel(t_plant):
            build_plant_tab()
        with ui.tab_panel(t_crm):
            build_crm_tab()
```

---

## Tab 1 — Fleet (ui/fleet.py)

Shows all 485 plants in a sortable, filterable table.

### Components

**Filter + export row**
```python
with ui.row().classes('w-full items-center gap-4 mb-4'):
    source_filter = ui.select(
        options=['All', 'growatt', 'isolarcloud', 'suryalog'],
        value='All', label='Platform'
    ).classes('w-40')
    status_filter = ui.select(
        options=['All', 'active', 'offline', 'fault'],
        value='All', label='Status'
    ).classes('w-40')
    tier_filter = ui.select(
        options=['All', 'Best', 'Good', 'Could Be Better', 'Needs Attention', 'Critical'],
        value='All', label='Tier'
    ).classes('w-48')
    ui.space()
    ui.button('CSV',  on_click=lambda: ui.download('/api/export/fleet-daily?fmt=csv'),  icon='download').props('flat')
    ui.button('XLSX', on_click=lambda: ui.download('/api/export/fleet-daily?fmt=xlsx'), icon='download').props('flat color=green')
```

**Table**
```python
columns = [
    {'name': 'plant_name',   'label': 'Plant',    'field': 'plant_name',   'sortable': True},
    {'name': 'source',       'label': 'Platform', 'field': 'source',       'sortable': True},
    {'name': 'capacity_kwp', 'label': 'kWp',      'field': 'capacity_kwp', 'sortable': True},
    {'name': 'status',       'label': 'Status',   'field': 'status',       'sortable': True},
    {'name': 'live_power_kw','label': 'Live kW',  'field': 'live_power_kw','sortable': True},
    {'name': 'kwh',          'label': 'Today kWh','field': 'kwh',          'sortable': True},
    {'name': 'monthly_kwh',  'label': 'Month kWh','field': 'monthly_kwh',  'sortable': True},
    {'name': 'tier',         'label': 'Tier',     'field': 'tier',         'sortable': True},
]

fleet_table = ui.table(columns=columns, rows=[], row_key='plant_id', pagination=25)
fleet_table.classes('w-full')
```

**Data load + filter reactivity**
```python
all_rows = []

async def load_fleet():
    global all_rows
    resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: requests.get('http://localhost:8000/api/fleet').json()
    )
    all_rows = resp.get('plants', [])
    apply_filters()

def apply_filters():
    rows = all_rows
    if source_filter.value != 'All':
        rows = [r for r in rows if r['source'] == source_filter.value]
    if status_filter.value != 'All':
        rows = [r for r in rows if r['status'] == status_filter.value]
    if tier_filter.value != 'All':
        rows = [r for r in rows if r.get('tier') == tier_filter.value]
    fleet_table.rows = rows

source_filter.on('update:model-value', lambda: apply_filters())
status_filter.on('update:model-value', lambda: apply_filters())
tier_filter.on('update:model-value',   lambda: apply_filters())

ui.timer(0, load_fleet, once=True)       # load on page render
ui.timer(300, load_fleet)                # refresh every 5 minutes
```

**Status badge colours** (via Quasar chip in table slot)

```python
# NiceGUI table slots let you inject custom HTML per column
fleet_table.add_slot('body-cell-status', '''
    <q-td :props="props">
        <q-chip
            :color="props.value === 'active' ? 'green' : props.value === 'fault' ? 'red' : 'grey'"
            text-color="white" size="sm" dense>
            {{ props.value }}
        </q-chip>
    </q-td>
''')
```

---

## Tab 2 — Analytics (ui/analytics.py)

Four Chart.js charts with date range and platform filters.

### Chart pattern (NiceGUI)

`ui.chart(options)` takes a Chart.js configuration dict. Update `.options` and call `.update()` to refresh.

```python
daily_chart = ui.chart({
    'type': 'line',
    'data': {
        'labels': [],
        'datasets': [{
            'label': 'Fleet Daily Generation (kWh)',
            'data': [],
            'borderColor': '#F0A500',
            'backgroundColor': 'rgba(240,165,0,0.1)',
            'fill': True,
            'tension': 0.3,
        }]
    },
    'options': {
        'responsive': True,
        'plugins': {'legend': {'display': False}},
        'scales': {'y': {'title': {'display': True, 'text': 'kWh'}}}
    }
}).classes('w-full h-64')
```

### Four charts

| Chart                        | Type             | X axis         | Y axis          | Dataset(s)                          |
|------------------------------|------------------|----------------|-----------------|-------------------------------------|
| Fleet daily generation       | line             | date (30 days) | kWh             | sum of all plants per day           |
| Tier distribution            | bar (horizontal) | tier label     | plant count     | count per tier, current month       |
| Platform comparison          | bar (grouped)    | platform name  | avg spec. yield | Growatt / iSolarCloud / SuryaLog   |
| Top 10 / Bottom 10           | bar (horizontal) | plant name     | monthly kWh     | top 10 green, bottom 10 red         |

### Filter controls

```python
with ui.row().classes('gap-4 mb-4'):
    date_from = ui.date(value='2026-08-01').classes('w-36')
    ui.label('to').classes('self-center')
    date_to   = ui.date(value='2026-09-21').classes('w-36')
    platform  = ui.select(['All', 'growatt', 'isolarcloud', 'suryalog'],
                          value='All', label='Platform').classes('w-40')
    ui.button('Apply', on_click=refresh_charts, icon='refresh')
    ui.space()
    ui.button('CSV',  on_click=lambda: ui.download(f'/api/export/fleet-daily?fmt=csv&start={date_from.value}&end={date_to.value}'))
    ui.button('XLSX', on_click=lambda: ui.download(f'/api/export/fleet-daily?fmt=xlsx&start={date_from.value}&end={date_to.value}'))
```

---

## Tab 3 — Plant (ui/plant.py)

Per-plant cockpit. All components are inside `@ui.refreshable` so selecting a new plant re-renders everything.

```python
selected_plant = {'id': None}

def build_plant_tab():
    # Plant selector
    plant_options = {}  # populated on load: {plant_name: plant_id}
    plant_select = ui.select(options=plant_options, label='Search plant', with_input=True)
    plant_select.on('update:model-value', lambda e: load_plant(e.value))

    render_cockpit()   # renders placeholder until a plant is selected

@ui.refreshable
def render_cockpit():
    pid = selected_plant['id']
    if not pid:
        ui.label('Select a plant to see its cockpit').classes('text-gray-400 text-center mt-8')
        return

    data = requests.get(f'http://localhost:8000/api/plant/{pid}').json()
    plant = data['plant']
    daily = data['daily']     # list of {date, kwh, ...}
    monthly = data['monthly'] # list of {month, kwh, ...}
    inverters = data['inverters']

    # KPI cards
    with ui.row().classes('gap-4 mb-4'):
        kpi_card('Capacity',      f"{plant.get('capacity_kwp', '—')} kWp",    'bolt')
        kpi_card('Status',        plant.get('status', '—'),                   'circle', colour_for_status(plant.get('status')))
        kpi_card('Today',         f"{daily[-1]['kwh'] if daily else '—'} kWh", 'solar_power')
        kpi_card('This Month',    f"{monthly[-1]['kwh'] if monthly else '—'} kWh", 'calendar_month')
        kpi_card('Tier',          data.get('tier', '—'),                      'star')
        kpi_card('Percentile',    f"P{data.get('percentile', '—')}",          'leaderboard')

    # 30-day sparkline
    ui.chart({
        'type': 'line',
        'data': {
            'labels': [r['date'] for r in daily],
            'datasets': [{'label': 'kWh', 'data': [r['kwh'] for r in daily],
                          'borderColor': '#F0A500', 'fill': False}]
        }
    }).classes('w-full h-48')

    # 12-month bar
    ui.chart({
        'type': 'bar',
        'data': {
            'labels': [r['month'] for r in monthly],
            'datasets': [{'label': 'Monthly kWh', 'data': [r['kwh'] for r in monthly],
                          'backgroundColor': '#3B82F6'}]
        }
    }).classes('w-full h-48')

    # Inverter table
    if inverters:
        inv_cols = [
            {'name': 'inverter_sn', 'label': 'SN',     'field': 'inverter_sn'},
            {'name': 'status',      'label': 'Status',  'field': 'status'},
            {'name': 'e_today_kwh', 'label': 'Today kWh','field': 'e_today_kwh'},
            {'name': 'temperature_c','label': 'Temp °C', 'field': 'temperature_c'},
            {'name': 'fault_code',  'label': 'Fault',   'field': 'fault_code'},
        ]
        ui.table(columns=inv_cols, rows=inverters, row_key='inverter_sn').classes('w-full')

    # Export
    ui.button('Export Plant History CSV',  on_click=lambda: ui.download(f'/api/export/plant-daily?plant_id={pid}&fmt=csv'))
    ui.button('Export Plant History XLSX', on_click=lambda: ui.download(f'/api/export/plant-daily?plant_id={pid}&fmt=xlsx'))
```

**KPI card helper:**
```python
def kpi_card(label, value, icon, colour='blue'):
    with ui.card().classes('flex-1 min-w-32 p-3'):
        with ui.row().classes('items-center gap-2'):
            ui.icon(icon).classes(f'text-{colour}-400 text-2xl')
            with ui.column().classes('gap-0'):
                ui.label(label).classes('text-xs text-gray-400')
                ui.label(str(value)).classes('text-lg font-bold')
```

---

## Tab 4 — CRM (ui/crm.py)

Customer directory, campaign preparation, alert export.

### Customer table
```python
crm_cols = [
    {'name': 'customer_name', 'label': 'Name',     'field': 'customer_name', 'sortable': True},
    {'name': 'phone',         'label': 'Phone',    'field': 'phone'},
    {'name': 'plant_id',      'label': 'Plant',    'field': 'plant_id'},
    {'name': 'preferred_lang','label': 'Language', 'field': 'preferred_lang'},
    {'name': 'opt_in_status', 'label': 'Opt-in',  'field': 'opt_in_status', 'sortable': True},
]
crm_table = ui.table(columns=crm_cols, rows=[], row_key='id', pagination=20).classes('w-full')
```

### Campaign section
```python
with ui.card().classes('w-full mt-4 p-4'):
    ui.label('Monthly Campaign').classes('font-bold text-lg mb-2')
    with ui.row().classes('gap-4 items-end'):
        month_input = ui.input(label='Month (YYYY-MM)', value='2026-09').classes('w-40')
        ui.button('Prepare Campaign', on_click=prepare_campaign, icon='campaign')
        ui.button('Export CSV for BSP', on_click=export_campaign, icon='download')

with ui.card().classes('w-full mt-4 p-4'):
    ui.label('Offline Alerts').classes('font-bold text-lg mb-2')
    with ui.row().classes('gap-4 items-end'):
        threshold = ui.number(label='Offline threshold (hours)', value=4, min=1).classes('w-48')
        ui.button('Get Offline Plants', on_click=load_offline, icon='power_off')
        ui.button('Export Alert CSV',   on_click=export_alerts,  icon='download')
```

---

## Component Conventions

| Pattern | NiceGUI API |
|---|---|
| Dark mode | `ui.dark_mode().enable()` at page load |
| Full-width layout | `.classes('w-full')` on containers |
| Spacing | Tailwind utilities via `.classes()` — `gap-4`, `p-4`, `mt-4`, etc. |
| Reactive data | `@ui.refreshable` decorator + call `fn.refresh()` after data change |
| Polling | `ui.timer(interval_seconds, callback)` |
| File download | `ui.download(url)` — triggers browser download from API endpoint |
| Notifications | `ui.notify('Message', type='positive'|'negative'|'warning')` |
| Loading state | `ui.spinner()` inside an `if loading:` block, toggle the bool |

---

## Theming

NiceGUI uses Quasar Framework under the hood. Dark mode applies globally.
Add custom CSS sparingly:

```python
ui.add_head_html('''
<style>
  .q-table__card { background: #1a1a2e !important; }
  .q-chip { font-size: 11px; }
</style>
''')
```

Avoid inline `style=` attributes. Use Tailwind utility classes via `.classes()`.

---

## No JavaScript Files

All interactivity is Python. If you find yourself writing a `.js` file, that is a sign
to look for the NiceGUI equivalent:

| JS equivalent | NiceGUI |
|---|---|
| `document.getElementById` | assign `ui.*` component to a variable |
| `element.innerText = ...` | `component.text = ...` |
| `fetch(url).then(...)` | `async def` + `requests.get` in executor |
| `setInterval(fn, ms)` | `ui.timer(seconds, fn)` |
| `window.location.href = url` | `ui.download(url)` or `ui.navigate.to(url)` |
| Custom event listener | `component.on('event-name', handler)` |

---

## Running

```bash
python app.py
# → FastAPI + NiceGUI on http://localhost:8000
# → API docs at http://localhost:8000/docs
# → Dashboard at http://localhost:8000/
```

For development with auto-reload:
```bash
uvicorn app:app --reload --port 8000
# Note: ui.run_with() handles reload correctly with uvicorn
```
