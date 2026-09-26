import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Ensure solaron directory and workspace root are on Python path and subprocess PYTHONPATH
solaron_dir = Path(__file__).resolve().parent
root_dir = solaron_dir.parent
sys.path.insert(0, str(solaron_dir))
sys.path.insert(0, str(root_dir))

cur_pp = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = f"{root_dir}{os.pathsep}{solaron_dir}{os.pathsep}{cur_pp}"

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from nicegui import ui, events

from config import settings
import db
import pipeline
from extractors import excel_parser
import scheduler
from routes import data_router, export_router, crm_router
from ui import build_fleet_tab, build_analytics_tab, build_plant_tab, build_crm_tab, build_fetch_tab

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db.init_db()
    if settings.scheduler_enabled:
        scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(
    title="Solaron Solar Analytics & CRM Platform",
    description="Unified solar telemetry, loss attribution, performance rating, and customer messaging platform.",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST API routers
app.include_router(data_router, prefix="/api", tags=["Data"])
app.include_router(export_router, prefix="/api", tags=["Exports"])
app.include_router(crm_router, prefix="/api", tags=["CRM"])

@ui.page("/")
def dashboard():
    client = ui.context.client
    ui.dark_mode().enable()

    # Shared Reactive Application State
    avail_months = db.get_available_months()
    init_month = "2026-09" if "2026-09" in avail_months else (avail_months[0] if avail_months else "2026-09")
    app_state = {
        "month": init_month,
        "source": "All",
        "selected_plant": None,
        "refresh_listeners": []
    }

    def broadcast_update():
        for listener in app_state["refresh_listeners"]:
            try:
                listener()
            except Exception:
                pass

    # Custom styling
    ui.add_head_html("""
    <style>
      .q-table__card { background: #111827 !important; border: 1px solid #374151; }
      .q-chip { font-size: 11px; }
      body { background-color: #0B0F19; font-family: 'Inter', sans-serif; }
      .q-table tbody tr { cursor: pointer; transition: background 0.15s ease; }
      .q-table tbody tr:hover { background: rgba(255, 255, 255, 0.05) !important; }
    </style>
    """)

    # Upload Excel Modal
    upload_dialog = ui.dialog()
    with upload_dialog, ui.card().classes("w-[500px] max-w-full p-6 bg-gray-900 border border-gray-700 text-white rounded-2xl shadow-2xl"):
        with ui.row().classes("w-full items-center justify-between mb-4"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("upload_file").classes("text-emerald-400 text-2xl")
                ui.label("Upload SolarOn Monthly Report").classes("text-base font-bold text-white")
            ui.button(icon="close", on_click=upload_dialog.close).props("flat round dense size=sm color=white")

        ui.label("Upload an exported SolarOn .xlsx or .xls report file. Plant generation and financial savings will be automatically extracted and merged.").classes("text-xs text-gray-400 mb-4")

        async def handle_excel_upload(e: events.UploadEventArguments):
            temp_path = Path(__file__).resolve().parent / "data" / "raw" / e.name
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "wb") as f:
                f.write(e.content.read())

            if not getattr(client, '_deleted', False):
                with client:
                    upload_dialog.close()
                    ui.notify("Parsing and ingesting monthly Excel report...", type="info", timeout=3000)
            try:
                res = await asyncio.to_thread(excel_parser.parse_and_ingest_excel, str(temp_path))
                if not getattr(client, '_deleted', False):
                    with client:
                        ui.notify(f"Ingested {res['plants_ingested']} plant records for {res['month_label']}!", type="positive")
                        app_state["month"] = res["month"]
                        if res["month"] not in header_month_select.options:
                            header_month_select.options = db.get_available_months()
                        header_month_select.value = res["month"]
                        broadcast_update()
            except Exception as exc:
                if not getattr(client, '_deleted', False):
                    with client:
                        ui.notify(f"Failed to ingest Excel file: {exc}", type="negative")

        ui.upload(
            label="Choose .xlsx / .xls file",
            on_upload=handle_excel_upload,
            auto_upload=True
        ).props("dark accept=.xlsx,.xls").classes("w-full mb-4")

        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=upload_dialog.close).props("flat color=white")

    # Command Center Header
    with ui.header().classes("bg-gray-900 text-white px-6 py-2 border-b border-gray-800 items-center"):
        with ui.row().classes("items-center gap-3"):
            ui.label("☀️ Solaron").classes("text-xl font-extrabold tracking-wide text-amber-400")
            ui.label("Solar Operations & Intelligence").classes("text-xs text-gray-400 self-center hidden sm:inline")

        ui.space()

        # Month Selector & Stepper
        with ui.row().classes("items-center gap-1 bg-gray-800 rounded-lg px-2 py-0.5 border border-gray-700"):
            def step_month(direction: int):
                cur_opts = header_month_select.options
                if not cur_opts:
                    return
                try:
                    idx = cur_opts.index(header_month_select.value)
                    new_idx = max(0, min(len(cur_opts) - 1, idx + direction))
                    header_month_select.value = cur_opts[new_idx]
                except Exception:
                    pass

            ui.button(icon="chevron_left", on_click=lambda: step_month(1)).props("flat dense round size=xs color=white")
            header_month_select = ui.select(
                options=avail_months,
                value=app_state["month"],
            ).props("dense borderless dark options-dense").classes("w-28 text-center text-sm font-bold")
            ui.button(icon="chevron_right", on_click=lambda: step_month(-1)).props("flat dense round size=xs color=white")

        def on_header_month_change(e):
            app_state["month"] = header_month_select.value
            broadcast_update()
        header_month_select.on("update:model-value", on_header_month_change)

        # Platform Filter in Header
        header_source_select = ui.select(
            options=["All", "growatt", "isolarcloud", "suryalog"],
            value=app_state["source"],
            label="Platform"
        ).props("dense outlined dark options-dense").classes("w-32")

        def on_header_source_change(e):
            app_state["source"] = header_source_select.value
            broadcast_update()
        header_source_select.on("update:model-value", on_header_source_change)

        # Tabs navigation
        def trigger_fetch_tab():
            if "switch_tab_fn" in app_state:
                app_state["switch_tab_fn"]("Fetch Data")

        ui.button("Fetch Data", on_click=trigger_fetch_tab, icon="cloud_download").props("dense color=primary unelevated")
        ui.button("Upload Excel", on_click=upload_dialog.open, icon="upload_file").props("dense color=positive outline")

    # Tabs navigation
    with ui.tabs().classes("w-full bg-gray-900 text-gray-300 border-b border-gray-800") as tabs:
        t_fetch = ui.tab("Fetch Data", icon="cloud_download")
        t_fleet = ui.tab("Fleet", icon="solar_power")
        t_analytics = ui.tab("Full Analytics", icon="analytics")
        t_plant = ui.tab("Plant Cockpit", icon="eco")
        t_crm = ui.tab("CRM & Campaigns", icon="contacts")

    def switch_tab(tab_target: str):
        target_map = {
            "Fetch Data": t_fetch,
            "Fleet": t_fleet,
            "Full Analytics": t_analytics,
            "Analytics": t_analytics,
            "Plant Cockpit": t_plant,
            "CRM & Campaigns": t_crm,
        }
        if tab_target in target_map:
            tgt = target_map[tab_target]
            tabs.set_value(tgt)
            if tab_target in ("Plant Cockpit", "Plant", "plant"):
                broadcast_update()

    app_state["switch_tab_fn"] = switch_tab

    # Tab Panels: Mount all tabs upfront so switching is instantaneous and panels are never empty
    with ui.tab_panels(tabs, value=t_fetch).classes("w-full p-6 bg-[#0B0F19]"):
        with ui.tab_panel(t_fetch):
            build_fetch_tab(app_state, switch_tab=switch_tab, open_upload_modal=upload_dialog.open)
        with ui.tab_panel(t_fleet):
            build_fleet_tab(app_state)
        with ui.tab_panel(t_analytics):
            build_analytics_tab(app_state)
        with ui.tab_panel(t_plant):
            build_plant_tab(app_state)
        with ui.tab_panel(t_crm):
            build_crm_tab(app_state)

# Mount NiceGUI on FastAPI
ui.run_with(app)

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  SOLARON SOLAR ANALYTICS & CRM PLATFORM")
    print(f"  Open in browser: http://localhost:{settings.app_port} or http://127.0.0.1:{settings.app_port}")
    print("=" * 60 + "\n")
    app_target = "solaron.app:app" if (Path.cwd() / "solaron").exists() else "app:app"
    uvicorn.run(
        app_target,
        host="127.0.0.1",
        port=settings.app_port,
        reload=True,
        reload_dirs=[str(solaron_dir)],
        reload_excludes=["*.db*", "data/*", "scratch/*", "*.log", "*.pyc", "__pycache__/*", ".git/*"]
    )

