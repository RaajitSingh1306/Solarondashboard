import asyncio
import datetime
import time
from typing import Any, Callable, Dict, List, Optional
from nicegui import ui
try:
    from pipeline import db, pipeline
except ImportError:
    import db
    import pipeline

def build_fetch_tab(
    app_state: Dict[str, Any],
    switch_tab: Optional[Callable[[str], None]] = None,
    open_upload_modal: Optional[Callable[[], None]] = None
):
    """
    Dedicated Data Fetch & Extraction Workbench tab.
    Allows selecting Month/Year, Platform source, individual site,
    toggling between Cache vs Force Refresh, executing the extraction,
    and reviewing the initial post-pull analysis and preview data.
    """

    client = ui.context.client

    # Fetch initial plant list for site picker
    plants_raw = db.get_plants()
    plant_options = {"All": "🌐 All Sites (Fleet-wide)"}
    for p in plants_raw:
        pid = p["plant_id"]
        pname = p.get("plant_name") or pid
        src = p.get("source", "").title()
        plant_options[pid] = f"[{src}] {pname} ({p.get('capacity_kwp', 0):.1f} kWp)"

    available_months = db.get_available_months()
    if not available_months:
        available_months = ["2026-09", "2026-08"]

    cache_meta = db.get_cache_metadata()

    # State for the fetch workbench
    workbench_state = {
        "selected_month": app_state.get("month", "2026-09"),
        "selected_platform": app_state.get("source", "All"),
        "selected_site": "All",
        "cache_mode": "cache",  # 'cache' or 'force'
        "is_fetching": False,
        "last_result": None,
    }

    # Container references
    container = ui.column().classes("w-full gap-6")

    with container:
        # 1. Header Banner
        with ui.row().classes("w-full items-center justify-between pb-2 border-b border-gray-800"):
            with ui.column().classes("gap-0.5"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("cloud_download").classes("text-amber-400 text-2xl")
                    ui.label("Data Extraction & Ingestion Engine").classes("text-xl font-bold text-white")
                ui.label(
                    "Fetch real-time or cached telemetry from inverter portals (Growatt, iSolarCloud, SuryaLog), "
                    "apply NASA POWER GHI benchmarks, and inspect post-pull health."
                ).classes("text-xs text-gray-400")

            with ui.row().classes("items-center gap-3"):
                if open_upload_modal:
                    ui.button(
                        "Upload Monthly Excel",
                        icon="upload_file",
                        on_click=open_upload_modal
                    ).props("dense outline color=positive")

        # 2. Control Form Card
        with ui.card().classes("w-full p-5 bg-gray-900 border border-gray-800 rounded-xl shadow-lg"):
            ui.label("Extraction Configuration").classes("text-sm font-semibold text-gray-300 mb-2")

            with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                # Month Selector
                with ui.column().classes("gap-1 min-w-[170px]"):
                    ui.label("Target Month").classes("text-xs font-medium text-gray-400")
                    month_select = ui.select(
                        options=available_months,
                        value=workbench_state["selected_month"],
                    ).props("dense outlined dark options-dense").classes("w-full")

                # Platform Selector
                with ui.column().classes("gap-1 min-w-[170px]"):
                    ui.label("Telemetry Portal").classes("text-xs font-medium text-gray-400")
                    platform_select = ui.select(
                        options=["All", "growatt", "isolarcloud", "suryalog"],
                        value=workbench_state["selected_platform"],
                    ).props("dense outlined dark options-dense").classes("w-full")

                # Specific Site Picker
                with ui.column().classes("gap-1 flex-1 min-w-[260px]"):
                    ui.label("Site Filter (Optional)").classes("text-xs font-medium text-gray-400")
                    site_select = ui.select(
                        options=plant_options,
                        value=workbench_state["selected_site"],
                    ).props("dense outlined dark options-dense filterable use-input").classes("w-full")

                # Cache Strategy
                with ui.column().classes("gap-1 min-w-[240px]"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Cache Strategy").classes("text-xs font-medium text-gray-400")
                        cache_badge = ui.badge(f"Cached: {cache_meta['latest_daily_date']}", color="amber-9").classes("text-[10px] text-white px-1.5 py-0.5 font-mono")
                    cache_toggle = ui.toggle(
                        options={
                            "cache": "⚡ From Cache",
                            "force": "🔄 Force Refresh"
                        },
                        value=workbench_state["cache_mode"]
                    ).props("dense color=amber-7 text-color=white spread").classes("w-full bg-gray-800 rounded-lg p-0.5 border border-gray-700")

            with ui.row().classes("w-full items-center justify-between mt-4 pt-3 border-t border-gray-800 flex-wrap gap-3"):
                with ui.column().classes("gap-1.5"):
                    with ui.row().classes("items-center gap-2 text-xs py-1 px-2.5 rounded bg-gray-800/90 border border-gray-700/60 flex-wrap"):
                        ui.icon("inventory_2", color="amber-4", size="xs")
                        cache_meta_label = ui.label(
                            f"Latest Cached Date: {cache_meta['latest_daily_date']} ({cache_meta['plants_on_latest_day']} plants) · Month: {cache_meta['latest_month']} · Synced: {cache_meta['last_sync_timestamp']}"
                        ).classes("text-xs text-amber-200 font-mono")

                    with ui.row().classes("items-center gap-2 text-xs text-gray-400"):
                        ui.icon("info").classes("text-amber-400 text-sm")
                        strategy_desc = ui.label(
                            f"⚡ Cache Mode: Pulls from existing local offline data and cached JSON telemetry (up to {cache_meta['latest_daily_date']})."
                        ).classes("text-xs text-gray-400")

                    with ui.row().classes("items-center gap-2 text-xs"):
                        ui.icon("schedule").classes("text-cyan-400 text-sm")
                        est_duration_label = ui.label(
                            "Expected Fetch Time: ~1 - 3 seconds (instant local telemetry & offline cache)"
                        ).classes("text-xs font-semibold text-cyan-300 font-mono")

                def compute_est_seconds(is_force: bool, platform: Optional[str], site: Optional[str]) -> float:
                    if not is_force:
                        return 3.0
                    if site and site != "All":
                        return 12.0
                    p = (platform or "all").lower()
                    if p == "growatt":
                        return 65.0
                    elif p == "isolarcloud":
                        return 25.0
                    elif p == "suryalog":
                        return 20.0
                    else:
                        # Full fleet across all 3 portals (490 plants, daily/monthly ingestion, NASA GHI loss attribution)
                        return 146.0

                def format_duration(seconds: float) -> str:
                    secs = int(round(seconds))
                    if secs < 60:
                        return f"{secs}s"
                    mins = secs // 60
                    rem_s = secs % 60
                    if rem_s == 0:
                        return f"{mins}m"
                    return f"{mins}m {rem_s:02d}s"

                def update_strategy_desc():
                    is_force = (cache_toggle.value == "force")
                    p_val = platform_select.value
                    s_val = site_select.value
                    est_sec = compute_est_seconds(is_force, p_val, s_val)
                    est_str = format_duration(est_sec)

                    if not is_force:
                        strategy_desc.set_text(
                            f"⚡ Cache Mode: Pulls from existing local offline data and cached JSON telemetry (up to {cache_meta['latest_daily_date']})."
                        )
                        est_duration_label.set_text(
                            f"Expected Fetch Time: ~{est_str} (instant local database & offline JSON cache)"
                        )
                        est_duration_label.classes(replace="text-cyan-300", remove="text-amber-300")
                    else:
                        strategy_desc.set_text(
                            "🔄 Force Refresh: Connects to portal gateways, extracts live daily/monthly records, recalculates NASA GHI loss attribution & health tiers, and OVERWRITES old records."
                        )
                        if s_val and s_val != "All":
                            est_duration_label.set_text(
                                f"Expected Fetch Time: ~{est_str} (targeted single site refresh & overwrite)"
                            )
                        elif p_val == "All" or not p_val:
                            est_duration_label.set_text(
                                f"Expected Fetch Time: ~{est_str} (~1m 45s for 467 plants across Growatt, iSolarCloud & SuryaLog)"
                            )
                        elif p_val.lower() == "growatt":
                            est_duration_label.set_text(
                                f"Expected Fetch Time: ~{est_str} (~1m 05s for Growatt portal - 449 plants)"
                            )
                        else:
                            est_duration_label.set_text(
                                f"Expected Fetch Time: ~{est_str} for {p_val.title()} portal telemetry"
                            )
                        est_duration_label.classes(replace="text-amber-300", remove="text-cyan-300")

                def refresh_cache_meta_ui():
                    nonlocal cache_meta
                    cache_meta = db.get_cache_metadata()
                    cache_badge.set_text(f"Cached: {cache_meta['latest_daily_date']}")
                    cache_meta_label.set_text(
                        f"Latest Cached Date: {cache_meta['latest_daily_date']} ({cache_meta['plants_on_latest_day']} plants) · Month: {cache_meta['latest_month']} · Synced: {cache_meta['last_sync_timestamp']}"
                    )
                    update_strategy_desc()

                cache_toggle.on("update:model-value", lambda e: update_strategy_desc())

                fetch_btn = ui.button(
                    "⚡ Live Fetch All Portals (Growatt, iSolarCloud, SuryaLog)",
                    icon="bolt"
                ).props("color=amber-6 text-color=black font-bold unelevated px-6").tooltip("Extract and ingest telemetry directly from ALL portals (Growatt, iSolarCloud, SuryaLog)")

                def update_fetch_btn_label():
                    p_val = platform_select.value
                    if p_val == "All" or not p_val:
                        fetch_btn.set_text("⚡ Live Fetch All Portals (Growatt, iSolarCloud, SuryaLog)")
                        fetch_btn.tooltip("Extract and ingest telemetry directly from ALL portals (Growatt, iSolarCloud, SuryaLog)")
                    else:
                        fetch_btn.set_text(f"⚡ Live Fetch ({p_val.title()} Portal)")
                        fetch_btn.tooltip(f"Extract and ingest telemetry directly from {p_val.title()} portal")
                    update_strategy_desc()

                platform_select.on("update:model-value", lambda e: update_fetch_btn_label())
                site_select.on("update:model-value", lambda e: update_strategy_desc())

        # 2B. Lifetime Historical Backfill Engine Card
        with ui.card().classes("w-full p-5 bg-gradient-to-br from-gray-900 via-indigo-950/20 to-gray-900 border border-indigo-800/40 rounded-xl shadow-lg"):
            with ui.row().classes("w-full items-center justify-between pb-3 border-b border-gray-800 flex-wrap gap-2"):
                with ui.row().classes("items-center gap-2.5"):
                    ui.icon("history_toggle_off").classes("text-indigo-400 text-2xl")
                    with ui.column().classes("gap-0"):
                        ui.label("Historical Lifetime Backfill Engine").classes("text-base font-bold text-white")
                        ui.label("Backfill historical monthly & daily generation from plant commissioning date (2017–2026) to present.").classes("text-xs text-gray-400")
                
                with ui.row().classes("items-center gap-2"):
                    ui.badge("490 Plants Synced", color="indigo-8").classes("text-xs font-semibold px-2.5 py-1 rounded")
                    ui.badge("Commissioning Range: 2017 - 2026", color="emerald-9").classes("text-xs font-semibold px-2.5 py-1 rounded")

            with ui.row().classes("w-full items-center gap-4 mt-3 flex-wrap"):
                start_backfill_select = ui.select(
                    options=["From Commissioning (Earliest 2017)", "2023-01", "2024-01", "2025-01", "2026-01"],
                    value="2023-01",
                    label="Backfill Start Month"
                ).props("dense outlined dark options-dense").classes("w-64")

                end_backfill_select = ui.select(
                    options=["2026-09", "2026-08", "2026-07", "2026-06"],
                    value="2026-09",
                    label="Backfill End Month"
                ).props("dense outlined dark options-dense").classes("w-44")

                daily_checkbox = ui.checkbox("Include representative daily telemetry", value=True).classes("text-xs text-gray-300")
                overwrite_checkbox = ui.checkbox("Overwrite existing records", value=True).classes("text-xs text-indigo-300 font-semibold").tooltip("Re-extracts and overwrites all existing monthly and daily records for selected range")

                backfill_btn = ui.button("🚀 Run Lifetime Backfill", icon="rocket_launch").props("color=indigo-7 text-color=white font-bold unelevated px-5")

            backfill_status_row = ui.row().classes("w-full items-center gap-3 mt-3 hidden p-3 bg-indigo-950/40 border border-indigo-800/30 rounded-lg")
            with backfill_status_row:
                bf_spinner = ui.spinner(size="sm", color="indigo")
                bf_status_label = ui.label("Backfilling historical generation...").classes("text-xs text-indigo-200 font-mono")
                bf_progress_bar = ui.linear_progress(value=0.0).props("color=indigo-4 track-color=grey-9 rounded").classes("flex-1 h-2")

            async def on_backfill_execute():
                backfill_btn.disable()
                backfill_status_row.classes(remove="hidden")
                
                raw_start = start_backfill_select.value
                start_m = None if "Commissioning" in str(raw_start) else str(raw_start)
                end_m = str(end_backfill_select.value or "2026-09")
                inc_daily = bool(daily_checkbox.value)
                do_overwrite = bool(overwrite_checkbox.value)

                def on_bf_progress(msg: str, pct: float):
                    if not getattr(client, '_deleted', False):
                        with client:
                            bf_status_label.set_text(msg)
                            bf_progress_bar.set_value(pct)

                try:
                    res = await asyncio.to_thread(
                        pipeline.run_historical_backfill,
                        start_year_month=start_m,
                        end_year_month=end_m,
                        include_daily=inc_daily,
                        force_refresh=do_overwrite,
                        progress_cb=on_bf_progress
                    )
                    refresh_cache_meta_ui()
                    if not getattr(client, '_deleted', False):
                        with client:
                            ui.notify(
                                f"Lifetime backfill complete! Processed {res['months_processed']} months ({res['monthly_records']} monthly records) in {res['duration_sec']}s",
                                type="positive",
                                timeout=6000
                            )
                            bf_status_label.set_text(f"Complete: {res['months_processed']} months ({res['monthly_records']} records) backfilled.")
                            bf_progress_bar.set_value(1.0)
                            for listener in app_state.get("refresh_listeners", []):
                                try:
                                    listener()
                                except Exception:
                                    pass
                except Exception as e:
                    if not getattr(client, '_deleted', False):
                        with client:
                            ui.notify(f"Backfill error: {e}", type="negative")
                            bf_status_label.set_text(f"Error: {e}")
                finally:
                    if not getattr(client, '_deleted', False):
                        with client:
                            backfill_btn.enable()

            backfill_btn.on("click", on_backfill_execute)

        # 3. Loading Indicator & Real-Time Fetch Timer Card
        loading_card = ui.card().classes(
            "w-full p-5 bg-gradient-to-r from-gray-900 via-gray-950 to-gray-900 "
            "border border-amber-500/50 rounded-xl shadow-2xl backdrop-blur-md hidden"
        )
        with loading_card:
            with ui.row().classes("w-full items-center justify-between pb-3 border-b border-gray-800 flex-wrap gap-2"):
                with ui.row().classes("items-center gap-3"):
                    ui.spinner(size="lg", color="amber")
                    with ui.column().classes("gap-0"):
                        ui.label("Ingesting Fleet Telemetry & Running Analytics").classes("text-base font-bold text-white")
                        fetch_subtitle = ui.label("Querying portal APIs, calculating NASA GHI loss attribution & health tiers...").classes("text-xs text-gray-400")

                # Live Running Timer Pill
                with ui.row().classes("items-center gap-2.5 px-3.5 py-2 bg-amber-500/10 border border-amber-500/40 rounded-lg"):
                    ui.icon("hourglass_top").classes("text-amber-400 text-base")
                    with ui.column().classes("gap-0 items-end"):
                        with ui.row().classes("items-baseline gap-1"):
                            elapsed_timer_label = ui.label("00:00.0").classes("text-base font-black font-mono text-amber-300")
                            est_timer_label = ui.label("/ est. ~3s").classes("text-xs font-mono text-gray-400")
                        time_remaining_label = ui.label("Estimating time remaining...").classes("text-[10px] font-mono text-amber-400/80")

            # Progress Bar & Phase Status
            with ui.column().classes("w-full gap-2 mt-3"):
                with ui.row().classes("w-full items-center justify-between text-xs"):
                    current_phase_label = ui.label("Phase 1/4: Initializing pipeline & connecting to portal gateways...").classes("text-amber-300 font-medium")
                    progress_pct_label = ui.label("5%").classes("text-gray-400 font-mono text-xs")

                fetch_progress_bar = ui.linear_progress(value=0.05, show_value=False).props("color=amber-6 track-color=grey-9 stripe rounded").classes("w-full h-2.5")

                with ui.row().classes("w-full items-center justify-between text-[11px] text-gray-500 mt-1"):
                    ui.label("Portals: Growatt (Residential) • iSolarCloud (Commercial) • SuryaLog (Industrial)").classes("text-gray-500")
                    ui.label("Real-time NASA POWER GHI Solar Insolation Benchmark Engine").classes("text-gray-500")

        # 4. Results & Post-Pull Initial Analysis Section
        results_container = ui.column().classes("w-full gap-5")

        def render_initial_analysis(data: Dict[str, Any]):
            results_container.clear()
            with results_container:
                # Summary Banner
                mode_badge = "⚡ Cached Extraction" if "Cache" in data.get("mode", "") else "🔄 Live Force Refresh"
                mode_color = "emerald" if "Cache" in data.get("mode", "") else "amber"

                with ui.row().classes(f"w-full items-center justify-between p-3.5 bg-gray-900 border border-{mode_color}-500/30 rounded-xl shadow flex-wrap gap-2"):
                    with ui.row().classes("items-center gap-2.5"):
                        ui.icon("check_circle").classes(f"text-{mode_color}-400 text-xl")
                        with ui.column().classes("gap-0"):
                            ui.label(f"Data Successfully Extracted for {data.get('month')}").classes("text-sm font-bold text-white")
                            ui.label(
                                f"Strategy: {mode_badge} • Completed in {data.get('elapsed_seconds', 0):.2f}s • "
                                f"{data.get('plants', 0)} Plants Processed • {data.get('loss_calculated', 0)} Loss Records Analyzed"
                            ).classes("text-xs text-gray-400")

                    with ui.row().classes("items-center gap-2"):
                        ui.chip(
                            f"⏱️ {data.get('elapsed_seconds', 0):.2f}s Fetch Time",
                            color="amber-9" if "Force" in mode_badge else "emerald-9",
                            text_color="white"
                        ).props("dense")
                        if switch_tab:
                            ui.button(
                                "Go to Full Fleet Analytics →",
                                icon="analytics",
                                on_click=lambda: switch_tab("Full Analytics")
                            ).props("dense color=primary unelevated")

                # 4 KPI Cards
                with ui.row().classes("w-full gap-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"):
                    # KPI 1: Plants
                    with ui.card().classes("p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                        with ui.row().classes("items-center justify-between w-full mb-1"):
                            ui.label("Plants Processed").classes("text-xs font-semibold text-gray-400")
                            ui.icon("solar_power").classes("text-amber-400 text-base")
                        ui.label(str(data.get("plants", 0))).classes("text-2xl font-black text-white")
                        ui.label(f"{data.get('daily_records', 0)} daily telemetry records").classes("text-[11px] text-gray-500 mt-1")

                    # KPI 2: Energy
                    with ui.card().classes("p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                        with ui.row().classes("items-center justify-between w-full mb-1"):
                            ui.label("Month Generation").classes("text-xs font-semibold text-gray-400")
                            ui.icon("bolt").classes("text-emerald-400 text-base")
                        ui.label(f"{data.get('total_mwh', 0):.1f} MWh").classes("text-2xl font-black text-emerald-400")
                        ui.label(f"{data.get('total_kwh', 0):,.0f} kWh recorded").classes("text-[11px] text-gray-500 mt-1")

                    # KPI 3: Savings
                    with ui.card().classes("p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                        with ui.row().classes("items-center justify-between w-full mb-1"):
                            ui.label("Estimated Value").classes("text-xs font-semibold text-gray-400")
                            ui.icon("payments").classes("text-blue-400 text-base")
                        rev_inr = data.get("total_revenue_inr", 0)
                        val_str = f"₹{rev_inr / 100000.0:.2f} L" if rev_inr >= 100000 else f"₹{rev_inr:,.0f}"
                        ui.label(val_str).classes("text-2xl font-black text-blue-400")
                        ui.label(f"Avg specific yield: {data.get('avg_specific_yield', 0):.1f} kWh/kWp").classes("text-[11px] text-gray-500 mt-1")

                    # KPI 4: Execution Speed
                    with ui.card().classes("p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                        with ui.row().classes("items-center justify-between w-full mb-1"):
                            ui.label("Fetch Duration").classes("text-xs font-semibold text-gray-400")
                            ui.icon("speed").classes("text-purple-400 text-base")
                        el_sec = float(data.get("elapsed_seconds", 0))
                        ui.label(f"{el_sec:.2f}s").classes("text-2xl font-black text-purple-400")
                        speed_sub = "⚡ Instant Cache Hit" if el_sec < 4.0 else f"🔄 Live Sync ({mode_badge})"
                        ui.label(speed_sub).classes("text-[11px] text-purple-300 mt-1")

                # Health Breakdown Section
                health = data.get("health") or {}
                norm_c = health.get("normal", 0)
                under_c = health.get("underperforming", 0)
                off_c = health.get("offline", 0)
                tot_c = max(1, norm_c + under_c + off_c)

                norm_pct = round((norm_c / tot_c) * 100, 1)
                under_pct = round((under_c / tot_c) * 100, 1)
                off_pct = round((off_c / tot_c) * 100, 1)

                with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                    with ui.row().classes("w-full items-center justify-between mb-2"):
                        ui.label("Fleet Health Distribution (Post-Extraction)").classes("text-xs font-semibold text-gray-300")
                        ui.label(f"{tot_c} total plants evaluated").classes("text-xs text-gray-500")

                    # Visual Multi-segment bar
                    with ui.row().classes("w-full h-3 rounded-full overflow-hidden bg-gray-800 flex gap-0.5"):
                        if norm_pct > 0:
                            ui.element("div").classes("h-full bg-emerald-500").style(f"width: {norm_pct}%;")
                        if under_pct > 0:
                            ui.element("div").classes("h-full bg-amber-500").style(f"width: {under_pct}%;")
                        if off_pct > 0:
                            ui.element("div").classes("h-full bg-rose-500").style(f"width: {off_pct}%;")

                    with ui.row().classes("w-full items-center justify-between mt-3 flex-wrap gap-2 text-xs"):
                        with ui.row().classes("items-center gap-1.5"):
                            ui.element("div").classes("w-2.5 h-2.5 rounded-full bg-emerald-500")
                            ui.label(f"Optimal / Good: {norm_c} plants ({norm_pct}%)").classes("text-gray-300")

                        with ui.row().classes("items-center gap-1.5"):
                            ui.element("div").classes("w-2.5 h-2.5 rounded-full bg-amber-500")
                            ui.label(f"Underperforming: {under_c} plants ({under_pct}%)").classes("text-gray-300")

                        with ui.row().classes("items-center gap-1.5"):
                            ui.element("div").classes("w-2.5 h-2.5 rounded-full bg-rose-500")
                            ui.label(f"Zero Gen / Offline: {off_c} plants ({off_pct}%)").classes("text-gray-300")

                # Preview Table of Extracted Telemetry
                preview_list = data.get("preview_plants") or []
                if preview_list:
                    with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                        with ui.row().classes("w-full items-center justify-between mb-3"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("table_chart").classes("text-amber-400 text-lg")
                                ui.label(f"Telemetry Preview (Top {len(preview_list)} Plants)").classes("text-sm font-bold text-white")
                            ui.label("Sorted by Month Generation").classes("text-xs text-gray-500")

                        columns = [
                            {"name": "plant_name", "label": "Plant Name", "field": "plant_name", "align": "left", "sortable": True},
                            {"name": "source", "label": "Portal", "field": "source", "align": "center", "sortable": True},
                            {"name": "capacity_kwp", "label": "Capacity", "field": "capacity_kwp", "align": "right", "sortable": True},
                            {"name": "month_kwh", "label": f"{data.get('month')} Energy", "field": "month_kwh", "align": "right", "sortable": True},
                            {"name": "specific_yield", "label": "Specific Yield", "field": "specific_yield", "align": "right", "sortable": True},
                            {"name": "tier", "label": "Health Tier", "field": "tier", "align": "center", "sortable": True},
                            {"name": "revenue_inr", "label": "Savings", "field": "revenue_inr", "align": "right", "sortable": True},
                            {"name": "action", "label": "Action", "field": "action", "align": "center"},
                        ]

                        rows = []
                        for p in preview_list:
                            cap = p.get("capacity_kwp") or 0.0
                            kwh = p.get("month_kwh") or 0.0
                            sy = p.get("specific_yield") or 0.0
                            rev = p.get("revenue_inr") or 0.0
                            rows.append({
                                "plant_id": p.get("plant_id"),
                                "plant_name": p.get("plant_name") or p.get("plant_id"),
                                "source": (p.get("source") or "").title(),
                                "capacity_kwp": f"{cap:.1f} kWp",
                                "month_kwh": f"{kwh:,.0f} kWh",
                                "specific_yield": f"{sy:.1f} kWh/kWp",
                                "tier": p.get("tier") or "Good",
                                "revenue_inr": f"₹{rev:,.0f}",
                            })

                        preview_table = ui.table(
                            columns=columns,
                            rows=rows,
                            row_key="plant_id",
                            pagination={"rowsPerPage": 10}
                        ).props("dense dark flat bordered").classes("w-full")

                        preview_table.add_slot("body-cell-source", """
                            <q-td :props="props">
                                <q-chip dense :color="props.row.source === 'Growatt' ? 'teal-9' : (props.row.source === 'Isolarcloud' ? 'blue-9' : 'orange-9')" text-color="white" size="xs">
                                    {{ props.row.source }}
                                </q-chip>
                            </q-td>
                        """)

                        preview_table.add_slot("body-cell-tier", """
                            <q-td :props="props">
                                <q-chip dense :color="props.row.tier === 'Best' ? 'green-9' : (props.row.tier === 'Good' ? 'teal-9' : (props.row.tier === 'Could Be Better' ? 'amber-9' : 'red-9'))" text-color="white" size="xs">
                                    {{ props.row.tier }}
                                </q-chip>
                            </q-td>
                        """)

                        def handle_cockpit_click(args):
                            pid = args.get("plant_id")
                            if pid and switch_tab:
                                app_state["selected_plant"] = pid
                                for listener in app_state.get("refresh_listeners", []):
                                    try:
                                        listener()
                                    except Exception:
                                        pass
                                switch_tab("Plant Cockpit")

                        preview_table.add_slot("body-cell-action", """
                            <q-td :props="props">
                                <q-btn flat dense round size="sm" icon="visibility" color="amber-4" @click="() => $parent.$emit('open_plant', props.row)">
                                    <q-tooltip class="bg-gray-800 text-white">Inspect in Cockpit</q-tooltip>
                                </q-btn>
                            </q-td>
                        """)
                        preview_table.on("open_plant", lambda e: handle_cockpit_click(e.args))

                # Footer Action Call to Action
                with ui.row().classes("w-full items-center justify-between p-4 bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 border border-gray-800 rounded-xl mt-2"):
                    with ui.column().classes("gap-0.5"):
                        ui.label("Telemetry Ingestion Ready for Deep Dive").classes("text-sm font-bold text-white")
                        ui.label("Review NASA POWER GHI loss waterfalls, degraded plants, and platform comparisons in Full Analytics.").classes("text-xs text-gray-400")

                    if switch_tab:
                        ui.button(
                            "Open Full Analytics & Loss Attribution →",
                            icon="insights",
                            on_click=lambda: switch_tab("Full Analytics")
                        ).props("color=amber-6 text-color=black font-bold unelevated")

        # Initial Load: Automatically render cached data for the selected month asynchronously
        async def load_cached_initial_state():
            m = workbench_state["selected_month"]
            src = workbench_state["selected_platform"]
            srcs = [src] if src != "All" else None
            p_id = workbench_state["selected_site"] if workbench_state["selected_site"] != "All" else None

            # Run in background thread so tab renders instantly without blocking NiceGUI
            res = await asyncio.to_thread(
                pipeline.run_full_extract,
                month_str=m,
                sources=srcs,
                force_refresh=False,
                target_plant_id=p_id
            )
            if not getattr(client, '_deleted', False):
                with client:
                    render_initial_analysis(res)

        # Trigger initial render asynchronously via timer
        ui.timer(0.05, lambda: asyncio.create_task(load_cached_initial_state()), once=True)

        # Handle Fetch Button Click
        async def on_fetch_execute():
            target_month = month_select.value
            target_src = platform_select.value
            target_site = site_select.value
            is_force = (cache_toggle.value == "force")

            srcs = [target_src] if target_src != "All" else None
            p_id = target_site if target_site != "All" else None
            est_seconds = compute_est_seconds(is_force, target_src, target_site)
            est_formatted = format_duration(est_seconds)

            backend_state: Dict[str, Any] = {
                "msg": "Phase 1/4: Initializing pipeline & connecting to portal gateways...",
                "pct": 0.06
            }

            def on_backend_progress(msg: str, pct: float):
                backend_state["msg"] = msg
                backend_state["pct"] = pct

            if not getattr(client, '_deleted', False):
                with client:
                    fetch_btn.disable()
                    loading_card.classes(remove="hidden")
                    elapsed_timer_label.set_text("00:00.0")
                    est_timer_label.set_text(f"/ est. ~{est_formatted}")
                    time_remaining_label.set_text(f"~{est_formatted} remaining")
                    fetch_progress_bar.set_value(0.06)
                    progress_pct_label.set_text("6%")
                    current_phase_label.set_text("Phase 1/4: Connecting to portals & extracting plant metadata...")
                    ui.notify(
                        f"⚡ Telemetry extraction started (Expected fetch time: ~{est_formatted})...",
                        type="info",
                        timeout=3500
                    )

            start_time = time.time()
            stop_timer = asyncio.Event()

            async def run_live_timer():
                while not stop_timer.is_set():
                    elapsed = time.time() - start_time
                    mins = int(elapsed // 60)
                    secs = elapsed % 60
                    time_display = f"{mins:02d}:{secs:04.1f}"

                    rem = est_seconds - elapsed
                    if rem > 0:
                        rem_text = f"~{format_duration(rem)} remaining"
                    else:
                        over_s = int(elapsed - est_seconds)
                        rem_text = f"Finalizing calculations... (+{over_s}s)"

                    # Progress percentage: blend backend callback progress with elapsed time
                    time_ratio = elapsed / est_seconds
                    cb_pct = backend_state.get("pct", 0.06)
                    if elapsed <= est_seconds:
                        ratio = max(cb_pct, min(0.95, time_ratio * 0.92))
                    else:
                        # Smooth asymptotic creep towards 98.5% so it never freezes
                        ratio = min(0.985, 0.95 + 0.035 * (1.0 - 1.0 / (1.0 + (elapsed - est_seconds) / 25.0)))
                    pct_display = f"{int(ratio * 100)}%"

                    phase_text = backend_state.get("msg") or "Phase 1/4: Extracting telemetry..."

                    if not getattr(client, '_deleted', False):
                        with client:
                            elapsed_timer_label.set_text(time_display)
                            time_remaining_label.set_text(rem_text)
                            fetch_progress_bar.set_value(ratio)
                            progress_pct_label.set_text(pct_display)
                            current_phase_label.set_text(phase_text)

                    await asyncio.sleep(0.15)

            timer_task = asyncio.create_task(run_live_timer())

            try:
                res = await asyncio.to_thread(
                    pipeline.run_full_extract,
                    month_str=target_month,
                    sources=srcs,
                    force_refresh=is_force,
                    target_plant_id=p_id,
                    progress_cb=on_backend_progress
                )

                stop_timer.set()
                try:
                    timer_task.cancel()
                except Exception:
                    pass

                total_elapsed = round(time.time() - start_time, 2)
                res["elapsed_seconds"] = total_elapsed
                res["est_seconds"] = est_seconds

                # Sync app_state
                app_state["month"] = target_month
                if target_src != "All":
                    app_state["source"] = target_src
                refresh_cache_meta_ui()
                for listener in app_state.get("refresh_listeners", []):
                    try:
                        listener()
                    except Exception:
                        pass

                if not getattr(client, '_deleted', False):
                    with client:
                        fetch_progress_bar.set_value(1.0)
                        progress_pct_label.set_text("100%")
                        current_phase_label.set_text(f"Phase 4/4: Complete in {total_elapsed:.1f}s")
                        time_remaining_label.set_text("Extraction complete")
                        ui.notify(
                            f"Extraction complete in {total_elapsed:.2f}s! Processed {res['plants']} plants.",
                            type="positive",
                            timeout=4000
                        )
                        render_initial_analysis(res)
            except Exception as exc:
                stop_timer.set()
                try:
                    timer_task.cancel()
                except Exception:
                    pass
                if not getattr(client, '_deleted', False):
                    with client:
                        ui.notify(f"Extraction failed: {exc}", type="negative")
            finally:
                stop_timer.set()
                try:
                    timer_task.cancel()
                except Exception:
                    pass
                if not getattr(client, '_deleted', False):
                    with client:
                        loading_card.classes(add="hidden")
                        fetch_btn.enable()

        fetch_btn.on("click", on_fetch_execute)

        # React to month changes from app_state if updated externally
        def on_app_state_external_update():
            if app_state.get("month") != workbench_state["selected_month"]:
                workbench_state["selected_month"] = app_state["month"]
                month_select.value = app_state["month"]
                asyncio.create_task(load_cached_initial_state())

        app_state.setdefault("refresh_listeners", []).append(on_app_state_external_update)
