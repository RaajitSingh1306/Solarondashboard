import asyncio
import datetime
import time
from typing import Any, Dict, List, Optional
from nicegui import ui
try:
    from pipeline import db
except ImportError:
    import db

def build_fleet_tab(app_state: dict):
    client = ui.context.client
    all_rows = []
    selected_month = {"val": app_state.get("month", "2026-09")}

    # Top KPI Summary Cards Container (Persistent components with reactive labels)
    kpi_container = ui.row().classes("w-full gap-4 mb-6")
    with kpi_container:
        with ui.card().classes("flex-1 min-w-44 p-4 bg-gray-900 border border-gray-800"):
            kpi_month_label = ui.label(f"Monthly Output ({selected_month['val']})").classes("text-xs text-gray-400 font-medium")
            tot_mwh_label = ui.label("— MWh").classes("text-2xl font-black text-amber-400 mt-1")
            ui.label("Active fleet energy yield").classes("text-[11px] text-gray-500 mt-1")

        with ui.card().classes("flex-1 min-w-44 p-4 bg-gray-900 border border-gray-800"):
            ui.label("Est. Financial Value").classes("text-xs text-gray-400 font-medium")
            rev_inr_label = ui.label("₹—").classes("text-2xl font-black text-emerald-400 mt-1")
            ui.label("Direct commercial energy savings").classes("text-[11px] text-gray-500 mt-1")

        with ui.card().classes("flex-1 min-w-44 p-4 bg-gray-900 border border-gray-800"):
            ui.label("Active Generating Plants").classes("text-xs text-gray-400 font-medium")
            active_gen_label = ui.label("— / —").classes("text-2xl font-black text-blue-400 mt-1")
            ui.label("Operational with positive yield").classes("text-[11px] text-gray-500 mt-1")

        with ui.card().classes("flex-1 min-w-44 p-4 bg-gray-900 border border-gray-800"):
            ui.label("Fault / Zero Generation").classes("text-xs text-gray-400 font-medium")
            fault_zero_label = ui.label("—").classes("text-2xl font-black text-rose-500 mt-1")
            ui.label("Critical alerts & zero energy output").classes("text-[11px] text-gray-500 mt-1")

        with ui.card().classes("flex-1 min-w-44 p-4 bg-gray-900 border border-gray-800"):
            ui.label("Decommissioned / Inactive").classes("text-xs text-gray-400 font-medium")
            decom_label = ui.label("— / —").classes("text-2xl font-black text-purple-400 mt-1")
            ui.label("Permanently retired (excluded)").classes("text-[11px] text-gray-500 mt-1")

        with ui.card().classes("flex-1 min-w-44 p-4 bg-gray-900 border border-gray-800"):
            ui.label("Active Fleet Capacity").classes("text-xs text-gray-400 font-medium")
            tot_kwp_label = ui.label("— MWp").classes("text-2xl font-black text-cyan-400 mt-1")
            inverters_label = ui.label("— Inverters").classes("text-[11px] text-gray-500 mt-1")

    async def render_kpis():
        m = selected_month["val"]
        sql = """
        SELECT 
            count(p.plant_id) as total_plants,
            count(CASE WHEN coalesce(p.operational_status, 'active') != 'decommissioned' THEN 1 END) as active_fleet_count,
            count(CASE WHEN coalesce(p.operational_status, 'active') = 'decommissioned' THEN 1 END) as decom_count,
            coalesce(sum(CASE WHEN coalesce(p.operational_status, 'active') != 'decommissioned' THEN p.capacity_kwp ELSE 0 END), 0.0) as active_kwp,
            coalesce(sum(CASE WHEN coalesce(p.operational_status, 'active') != 'decommissioned' THEN m.kwh ELSE 0 END), 0.0) as total_m_kwh,
            coalesce(sum(CASE WHEN coalesce(p.operational_status, 'active') != 'decommissioned' THEN m.revenue_inr ELSE 0 END), 0.0) as total_revenue,
            count(CASE WHEN coalesce(p.operational_status, 'active') != 'decommissioned' AND coalesce(m.kwh, 0) > 1.0 THEN 1 END) as active_generating_count,
            count(CASE WHEN coalesce(p.operational_status, 'active') != 'decommissioned' AND (m.kwh IS NULL OR m.kwh <= 1.0) THEN 1 END) as fault_zero_count
        FROM plants p
        LEFT JOIN monthly_generation m ON p.plant_id = m.plant_id AND m.month = ?
        WHERE 1=1
        """
        params = [m]
        src_val = source_filter.value if "source_filter" in locals() and source_filter else app_state.get("source", "All")
        if src_val and src_val.lower() != "all":
            sql += " AND lower(p.source) = ?"
            params.append(src_val.lower())

        df = await asyncio.to_thread(db.query_df, sql, params, "analytics")
        if df.empty:
            return

        r = df.iloc[0]
        tot_mwh = round(float(r["total_m_kwh"] or 0.0) / 1000.0, 2)
        active_kwp = float(r["active_kwp"] or 0.0)
        tot_kwp = round(active_kwp / 1000.0, 2) # in MWp
        rev_inr = round(float(r["total_revenue"] or (tot_mwh * 1000 * 14.0)), 0)
        active_generating = int(r["active_generating_count"] or 0)
        active_fleet_count = int(r["active_fleet_count"] or 0)
        fault_zero = int(r["fault_zero_count"] or 0)
        decom_count = int(r["decom_count"] or 0)
        total_plants = int(r["total_plants"] or 0)

        kpi_month_label.text = f"Monthly Output ({m})"
        tot_mwh_label.text = f"{tot_mwh:,.2f} MWh"
        rev_inr_label.text = f"₹{rev_inr:,.0f}"
        active_gen_label.text = f"{active_generating} / {active_fleet_count}"
        fault_zero_label.text = f"{fault_zero}"
        decom_label.text = f"{decom_count} / {total_plants}"
        tot_kwp_label.text = f"{tot_kwp:.2f} MWp"
        inverters_label.text = f"{active_fleet_count} Inverters ({total_plants} Total Tracked)"

    with ui.row().classes("w-full items-center gap-3 mb-4"):
        # Month selector inside tab
        avail_months = db.get_available_months()
        month_select = ui.select(
            options=avail_months,
            value=selected_month["val"] if selected_month["val"] in avail_months else avail_months[0],
            label="Reporting Month"
        ).classes("w-40").props("dense outlined dark options-dense")

        # Quick Period presets
        with ui.button_group().props("dense outline"):
            ui.button("This Month (Sep)", on_click=lambda: asyncio.create_task(set_month("2026-09"))).props("dense text-color=white")
            ui.button("Prev Month (Aug)", on_click=lambda: asyncio.create_task(set_month("2026-08"))).props("dense text-color=white")

        source_filter = ui.select(
            options=["All", "growatt", "isolarcloud", "suryalog"],
            value=app_state.get("source", "All"),
            label="Platform"
        ).classes("w-36").props("dense outlined dark options-dense")

        status_filter = ui.select(
            options=["All", "active", "offline", "fault", "decommissioned"],
            value="All",
            label="Status"
        ).classes("w-32").props("dense outlined dark options-dense")

        tier_filter = ui.select(
            options=["All", "⚡ Anomaly Outliers", "Best", "Good", "Could Be Better", "Needs Attention", "Critical", "Offline", "Fault", "Decommissioned"],
            value="All",
            label="Tier"
        ).classes("w-44").props("dense outlined dark options-dense")

        search_input = ui.input(label="Search plant", placeholder="Type name...").classes("w-48").props("dense outlined dark debounce=250")

        show_decom_switch = ui.checkbox("Include Decommissioned", value=True).props("dense dark").classes("text-xs text-gray-400")

        ui.space()

        ui.button(
            "CSV",
            on_click=lambda: ui.download(f"/api/export/fleet-daily?fmt=csv&month={selected_month['val']}"),
            icon="download"
        ).props("dense flat color=primary")

        ui.button(
            "XLSX",
            on_click=lambda: ui.download(f"/api/export/fleet-daily?fmt=xlsx&month={selected_month['val']}"),
            icon="download"
        ).props("dense flat color=positive")

        sync_status_label = ui.label("").classes("text-xs text-amber-300/80 self-center ml-2")

        live_sync_btn = ui.button(
            "⚡ Live Fetch All Portals",
            icon="cloud_sync"
        ).props("dense unelevated color=amber-6 text-color=black font-bold px-3").tooltip("Scrape live generation directly from all portals (Growatt, iSolarCloud, SuryaLog) and update fleet")

        refresh_btn = ui.button(
            "Reload View",
            icon="refresh"
        ).props("dense flat color=white").tooltip("Reload local database view without scraping portals")

        auto_sync_toggle = ui.checkbox("Auto-Sync (15 min)", value=False).props("dense dark").classes("text-xs text-amber-400 font-medium")

    columns = [
        {"name": "plant_name", "label": "Plant", "field": "plant_name", "sortable": True, "align": "left"},
        {"name": "source", "label": "Platform", "field": "source", "sortable": True, "align": "center"},
        {"name": "capacity_kwp", "label": "kWp", "field": "capacity_kwp", "sortable": True, "align": "right"},
        {"name": "status", "label": "Status", "field": "status", "sortable": True, "align": "center"},
        {"name": "last_log_time", "label": "Portal Last Log", "field": "last_log_time", "sortable": True, "align": "center"},
        {"name": "last_recorded_day", "label": "Last Rec. Day", "field": "last_recorded_day", "sortable": True, "align": "center"},
        {"name": "live_power_kw", "label": "Live kW", "field": "live_power_kw", "sortable": True, "align": "right"},
        {"name": "kwh", "label": "Today kWh", "field": "kwh", "sortable": True, "align": "right"},
        {"name": "monthly_kwh", "label": "Month kWh", "field": "monthly_kwh", "sortable": True, "align": "right"},
        {"name": "revenue_inr", "label": "Est. Savings (₹)", "field": "revenue_inr", "sortable": True, "align": "right"},
        {"name": "specific_yield", "label": "Yield (kWh/kWp)", "field": "specific_yield", "sortable": True, "align": "right"},
        {"name": "yield_per_day", "label": "Units/kWp/day", "field": "yield_per_day", "sortable": True, "align": "right"},
        {"name": "pr_pct", "label": "PR (%)", "field": "pr_pct", "sortable": True, "align": "right"},
        {"name": "tier", "label": "Tier", "field": "tier", "sortable": True, "align": "center"},
        {"name": "geocode_level", "label": "Location Conf.", "field": "geocode_level", "sortable": True, "align": "center"},
    ]

    fleet_table = ui.table(columns=columns, rows=[], row_key="plant_id", pagination=25).classes("w-full cursor-pointer")

    # Custom chip rendering for status
    fleet_table.add_slot("body-cell-status", """
        <q-td :props="props">
            <q-chip
                :color="props.value === 'active' ? 'positive' : props.value === 'fault' ? 'negative' : props.value === 'decommissioned' ? 'purple-9' : 'grey-7'"
                text-color="white" size="sm" dense>
                {{ props.value }}
            </q-chip>
        </q-td>
    """)

    # Custom badge rendering for last_log_time
    fleet_table.add_slot("body-cell-last_log_time", """
        <q-td :props="props">
            <q-badge color="grey-9" text-color="amber-3" class="font-mono text-[11px] px-2 py-0.5 border border-amber-900/40">
                <q-icon name="schedule" size="xs" class="mr-1 text-amber-400" />
                {{ props.value || '—' }}
            </q-badge>
        </q-td>
    """)

    # Custom badge rendering for last_recorded_day
    fleet_table.add_slot("body-cell-last_recorded_day", """
        <q-td :props="props">
            <q-badge color="grey-9" text-color="indigo-3" class="font-mono text-[11px] px-2 py-0.5 border border-indigo-900/40">
                <q-icon name="event_available" size="xs" class="mr-1 text-indigo-400" />
                {{ props.value || '—' }}
            </q-badge>
        </q-td>
    """)

    # Custom rendering for PR (%)
    fleet_table.add_slot("body-cell-pr_pct", """
        <q-td :props="props">
            <span :class="props.value >= 75 ? 'text-amber-400 font-bold' : props.value >= 60 ? 'text-emerald-400 font-medium' : props.value >= 45 ? 'text-blue-300' : props.value >= 30 ? 'text-orange-400' : 'text-rose-400 font-bold'">
                {{ props.value !== null && props.value !== undefined ? props.value + '%' : '—' }}
            </span>
        </q-td>
    """)

    # Custom chip rendering for tier and ML anomaly badge
    fleet_table.add_slot("body-cell-tier", """
        <q-td :props="props">
            <div class="row items-center no-wrap justify-center gap-1">
                <q-chip
                    :color="props.value === 'Best' ? 'amber-8' : props.value === 'Good' ? 'teal-7' : props.value === 'Could Be Better' ? 'blue-grey-7' : props.value === 'Needs Attention' ? 'orange-9' : props.value === 'Critical' ? 'deep-orange-9' : props.value === 'Decommissioned' ? 'purple-9' : 'grey-8'"
                    text-color="white" size="sm" dense>
                    {{ props.value || '—' }}
                </q-chip>
                <q-badge v-if="props.row.anomaly_flag === 1" color="red-9" text-color="white" class="font-bold text-[10px] px-1.5 py-0.5 cursor-pointer shadow">
                    <q-icon name="bolt" size="xs" class="text-amber-300 mr-0.5" />
                    Anomaly
                    <q-tooltip class="bg-gray-900 text-amber-300 border border-red-500/50 text-xs">
                        ⚡ ML Anomaly Detected: Underperforming outlier relative to seasonal peers (Score: {{ props.row.anomaly_score }})
                    </q-tooltip>
                </q-badge>
            </div>
        </q-td>
    """)

    # Custom chip rendering for platform
    fleet_table.add_slot("body-cell-source", """
        <q-td :props="props">
            <q-badge :color="props.value === 'growatt' ? 'indigo-7' : props.value === 'isolarcloud' ? 'cyan-8' : props.value === 'suryalog' ? 'orange-8' : 'grey-8'">
                {{ props.value }}
            </q-badge>
        </q-td>
    """)

    # Custom rendering for geocode location confidence
    fleet_table.add_slot("body-cell-geocode_level", """
        <q-td :props="props">
            <q-badge
                :color="props.value === 'exact' ? 'positive' : props.value === 'pincode_centroid' ? 'teal-7' : props.value === 'city_centroid' ? 'blue-7' : props.value === 'state_default' ? 'orange-8' : 'grey-8'"
                text-color="white" class="text-[10px] px-1.5 py-0.5 font-medium">
                {{ props.value || 'unresolved' }}
            </q-badge>
        </q-td>
    """)

    async def load_fleet_data():
        nonlocal all_rows
        m = selected_month["val"]
        d_start = f"{m}-01"
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        current_ym = datetime.date.today().strftime("%Y-%m")
        d_end = min(f"{m}-31", today_str) if m == current_ym else f"{m}-31"
        sql = """
        SELECT 
            p.plant_id, p.source, p.plant_name, p.capacity_kwp,
            coalesce(p.geocode_level, 'unresolved') as geocode_level,
            coalesce(p.operational_status, 'active') as operational_status,
            CASE 
                WHEN p.operational_status = 'decommissioned' THEN 'decommissioned'
                WHEN coalesce(m.kwh, 0) <= 0.05 AND coalesce(d.status, inv.status, 'active') = 'fault' THEN 'fault'
                WHEN coalesce(m.kwh, 0) <= 0.05 THEN 'offline'
                ELSE coalesce(d.status, inv.status, 'active')
            END as status,
            CASE WHEN p.operational_status = 'decommissioned' THEN 0.0 ELSE coalesce(d.live_power_kw, round(inv.ac_power_w / 1000.0, 2), 0.0) END as live_power_kw,
            CASE WHEN p.operational_status = 'decommissioned' THEN 0.0 ELSE coalesce(d.kwh, inv.e_today_kwh, 0.0) END as kwh,
            coalesce(m.kwh, 0.0) as monthly_kwh,
            coalesce(m.revenue_inr, round(coalesce(m.kwh, 0.0) * 14.0, 0)) as revenue_inr,
            coalesce(m.specific_yield, 0.0) as specific_yield,
            coalesce(m.yield_per_day, 0.0) as yield_per_day,
            coalesce(m.pr_pct, 0.0) as pr_pct,
            coalesce(m.anomaly_flag, 0) as anomaly_flag,
            coalesce(m.anomaly_score, 0.0) as anomaly_score,
            coalesce(m.tier, CASE WHEN p.operational_status = 'decommissioned' THEN 'Decommissioned' ELSE 'Offline' END) as tier,
            coalesce(d.last_log_time, p.last_log_time, '—') as last_log_time,
            coalesce(d.date, '—') as last_recorded_day
        FROM plants p
        LEFT JOIN (
            SELECT plant_id, status, live_power_kw, kwh, date, last_log_time
            FROM daily_generation
            WHERE date >= ? AND date <= ? AND (kwh > 0.05 OR status = 'fault')
            GROUP BY plant_id HAVING date = max(date)
        ) d ON p.plant_id = d.plant_id
        LEFT JOIN (
            SELECT plant_id, ac_power_w, temperature_c, e_today_kwh, status, snapshot_ts
            FROM inverter_snapshots
            GROUP BY plant_id HAVING snapshot_ts = max(snapshot_ts)
        ) inv ON p.plant_id = inv.plant_id
        LEFT JOIN (
            SELECT plant_id, kwh, revenue_inr, specific_yield, yield_per_day, pr_pct, tier, anomaly_flag, anomaly_score
            FROM monthly_generation
            WHERE month = ?
        ) m ON p.plant_id = m.plant_id
        ORDER BY p.plant_name ASC;
        """
        # Run table query and KPI calculation concurrently in background thread pool
        df, _ = await asyncio.gather(
            asyncio.to_thread(db.query_df, sql, [d_start, d_end, m], "analytics"),
            render_kpis()
        )
        all_rows = df.to_dict(orient="records") if not df.empty else []
        apply_filters()

    def apply_filters():
        rows = all_rows
        s_src = source_filter.value
        s_stat = status_filter.value
        s_tier = tier_filter.value
        s_term = (search_input.value or "").strip().lower()
        include_decom = show_decom_switch.value

        if not include_decom:
            rows = [r for r in rows if str(r.get("operational_status", "")).lower() != "decommissioned" and str(r.get("tier", "")).lower() != "decommissioned"]
        if s_src and s_src != "All":
            rows = [r for r in rows if str(r.get("source", "")).lower() == s_src.lower()]
        if s_stat and s_stat != "All":
            rows = [r for r in rows if str(r.get("status", "")).lower() == s_stat.lower()]
        if s_tier and s_tier != "All":
            if s_tier == "⚡ Anomaly Outliers":
                rows = [r for r in rows if int(r.get("anomaly_flag") or 0) == 1]
            else:
                rows = [r for r in rows if str(r.get("tier", "")) == s_tier]
        if s_term:
            rows = [r for r in rows if s_term in str(r.get("plant_name", "")).lower() or s_term in str(r.get("plant_id", "")).lower()]

        fleet_table.rows = rows

    async def set_month(m_val: str):
        selected_month["val"] = m_val
        month_select.value = m_val
        app_state["month"] = m_val
        await load_fleet_data()

    month_select.on("update:model-value", lambda e: asyncio.create_task(set_month(month_select.value)))

    def update_sync_btn_label():
        src_val = source_filter.value
        if src_val == "All" or not src_val:
            live_sync_btn.set_text("⚡ Live Fetch All Portals")
            live_sync_btn.tooltip("Scrape live generation directly from all portals (Growatt, iSolarCloud, SuryaLog) and update fleet")
        else:
            live_sync_btn.set_text(f"⚡ Live Fetch ({src_val.title()})")
            live_sync_btn.tooltip(f"Scrape live generation directly from {src_val.title()} portal and update fleet")

    source_filter.on("update:model-value", lambda: (update_sync_btn_label(), apply_filters()))
    status_filter.on("update:model-value", lambda: apply_filters())
    tier_filter.on("update:model-value", lambda: apply_filters())
    search_input.on("update:model-value", lambda: apply_filters())
    show_decom_switch.on("update:model-value", lambda: apply_filters())
    refresh_btn.on_click(lambda: asyncio.create_task(load_fleet_data()))

    # Direct row click navigation to Plant Cockpit
    def on_row_click(e):
        args = e.args
        row = None
        if isinstance(args, list) and len(args) > 1 and isinstance(args[1], dict):
            row = args[1]
        elif isinstance(args, dict):
            row = args
        if row and "plant_id" in row:
            app_state["selected_plant"] = row["plant_id"]
            if "switch_tab_fn" in app_state:
                app_state["switch_tab_fn"]("Plant Cockpit")

    fleet_table.on("row-click", on_row_click)

    async def on_live_sync():
        if getattr(client, '_deleted', False):
            return

        src = source_filter.value
        srcs = [src] if src != "All" else None
        target_name = "ALL Portals (Growatt, iSolarCloud, SuryaLog)" if src == "All" else f"{src.title()} Portal"

        p = (src or "all").lower()
        if p == "growatt":
            est_t = 65.0
        elif p == "isolarcloud":
            est_t = 25.0
        elif p == "suryalog":
            est_t = 20.0
        else:
            est_t = 146.0

        secs_int = int(round(est_t))
        est_fmt = f"{secs_int // 60}m {secs_int % 60:02d}s" if secs_int >= 60 else f"{secs_int}s"

        start_t = time.time()
        stop_fleet_timer = asyncio.Event()

        backend_status: Dict[str, Any] = {"msg": "Connecting to portals..."}
        def on_fleet_progress(msg: str, pct: float):
            backend_status["msg"] = msg

        with client:
            live_sync_btn.disable()
            live_sync_btn.props("loading")
            refresh_btn.disable()
            sync_status_label.set_text(f"Syncing: 00:00.0 (est ~{est_fmt})...")
            ui.notify(f"⚡ Live fetching telemetry for {target_name} (Est. fetch time: ~{est_fmt})...", type="info", timeout=3500)

        async def run_fleet_timer():
            while not stop_fleet_timer.is_set():
                el = time.time() - start_t
                mins = int(el // 60)
                secs = el % 60
                time_str = f"{mins:02d}:{secs:04.1f}"
                msg = backend_status.get("msg", "Syncing...")
                if not getattr(client, '_deleted', False):
                    with client:
                        sync_status_label.set_text(f"Syncing ({target_name}): {time_str} / ~{est_fmt} • {msg}")
                await asyncio.sleep(0.2)

        timer_task = asyncio.create_task(run_fleet_timer())

        try:
            try:
                from pipeline import pipeline
            except ImportError:
                import pipeline
            m = selected_month["val"]
            res = await asyncio.to_thread(
                pipeline.run_full_extract,
                month_str=m,
                sources=srcs,
                force_refresh=True,
                progress_cb=on_fleet_progress
            )

            stop_fleet_timer.set()
            try:
                timer_task.cancel()
            except Exception:
                pass

            now_str = datetime.datetime.now().strftime("%H:%M:%S")
            el_total = round(time.time() - start_t, 2)
            if not getattr(client, '_deleted', False):
                with client:
                    sync_status_label.set_text(f"Synced {target_name} in {el_total}s ({now_str})")
                    ui.notify(f"Live Fetch Complete! Updated {res['plants']} plants across {target_name} in {el_total}s (est was ~{est_t:.0f}s).", type="positive")
                    await load_fleet_data()
        except Exception as e:
            stop_fleet_timer.set()
            try:
                timer_task.cancel()
            except Exception:
                pass
            if not getattr(client, '_deleted', False):
                with client:
                    sync_status_label.set_text("Sync Error")
                    ui.notify(f"Live Sync Error: {e}", type="negative")
        finally:
            stop_fleet_timer.set()
            try:
                timer_task.cancel()
            except Exception:
                pass
            if not getattr(client, '_deleted', False):
                with client:
                    live_sync_btn.props(remove="loading")
                    live_sync_btn.enable()
                    refresh_btn.enable()

    live_sync_btn.on_click(on_live_sync)

    # Periodic Auto-Sync Timer (every 15 minutes, only if enabled)
    async def on_auto_sync_timer():
        if getattr(client, '_deleted', False) or not getattr(client, 'has_socket_connection', False):
            return
        if auto_sync_toggle.value:
            await on_live_sync()

    ui.timer(900.0, on_auto_sync_timer)

    # Register external month change listener
    async def on_global_update():
        if app_state.get("month") != selected_month["val"]:
            selected_month["val"] = app_state.get("month", "2026-09")
            month_select.value = selected_month["val"]
        if app_state.get("source") != source_filter.value:
            source_filter.value = app_state.get("source", "All")
        await load_fleet_data()

    if "refresh_listeners" in app_state:
        app_state["refresh_listeners"].append(lambda: asyncio.create_task(on_global_update()))

    # Initial load immediately on connection
    async def initial_load():
        try:
            await client.connected()
        except Exception:
            pass
        await load_fleet_data()

    ui.timer(0.01, lambda: asyncio.create_task(initial_load()), once=True)

