import asyncio
import datetime
import time
from nicegui import ui
try:
    from pipeline import db
    from core import analytics
except ImportError:
    import db
    import analytics

def build_plant_tab(app_state: dict):
    client = ui.context.client
    selected_plant = {
        "id": None,
        "month": app_state.get("month", "2026-09")
    }

    def kpi_card(label: str, value: str, icon: str, colour: str = "primary"):
        with ui.card().classes("flex-1 min-w-32 p-3 bg-gray-900 border border-gray-800"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon).classes(f"text-{colour} text-2xl")
                with ui.column().classes("gap-0"):
                    ui.label(label).classes("text-xs text-gray-400 font-medium")
                    ui.label(str(value)).classes("text-lg font-bold text-white")

    def load_plant_metadata():
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        m_val = selected_plant["month"]
        return db.query_df(
            """
            SELECT 
                p.plant_id, p.plant_name, p.source,
                coalesce(p.operational_status, 'active') as op_status,
                coalesce(d.status, 'offline') as today_status,
                coalesce(d.kwh, 0.0) as today_kwh,
                coalesce(m.tier, 'Offline') as month_tier,
                coalesce(m.anomaly_flag, 0) as is_anomaly
            FROM plants p
            LEFT JOIN (
                SELECT plant_id, status, kwh
                FROM daily_generation
                WHERE date = ?
            ) d ON p.plant_id = d.plant_id
            LEFT JOIN (
                SELECT plant_id, tier, anomaly_flag
                FROM monthly_generation
                WHERE month = ?
            ) m ON p.plant_id = m.plant_id
            ORDER BY p.plant_name ASC
            """,
            [today_str, m_val],
            db="analytics"
        )

    plants_meta_df = load_plant_metadata()

    def get_category_options():
        n_all = len(plants_meta_df)
        n_act = len(plants_meta_df[plants_meta_df["op_status"] == "active"])
        n_inact = len(plants_meta_df[plants_meta_df["op_status"] == "decommissioned"])
        n_today = len(plants_meta_df[plants_meta_df["today_kwh"] > 0.05])
        n_off_today = len(plants_meta_df[(plants_meta_df["today_kwh"] <= 0.05) & (plants_meta_df["today_status"] != "fault")])
        n_fault = len(plants_meta_df[plants_meta_df["today_status"] == "fault"])
        n_anom = len(plants_meta_df[plants_meta_df["is_anomaly"] == 1])
        n_best = len(plants_meta_df[plants_meta_df["month_tier"] == "Best"])
        n_good = len(plants_meta_df[plants_meta_df["month_tier"] == "Good"])
        n_cbb = len(plants_meta_df[plants_meta_df["month_tier"] == "Could Be Better"])
        n_na = len(plants_meta_df[plants_meta_df["month_tier"] == "Needs Attention"])
        n_crit = len(plants_meta_df[plants_meta_df["month_tier"] == "Critical"])
        
        return {
            "all": f"🌐 All Plants ({n_all})",
            "active": f"⚡ Active Operational ({n_act})",
            "inactive": f"💤 Inactive / Decom ({n_inact})",
            "generating_today": f"🟢 Generating Today ({n_today})",
            "offline_today": f"⚪ Offline Today ({n_off_today})",
            "fault_today": f"🔴 Fault Detected ({n_fault})",
            "anomalies": f"⚡ ML Anomalies ({n_anom})",
            "tier_best": f"⭐ Best ({n_best})",
            "tier_good": f"✅ Good ({n_good})",
            "tier_could_be_better": f"⚠️ Could Be Better ({n_cbb})",
            "tier_needs_attention": f"🟠 Needs Attention ({n_na})",
            "tier_critical": f"🔴 Critical ({n_crit})",
        }

    portal_options = {
        "all": "All Portals (490)",
        "growatt": "Growatt (450)",
        "isolarcloud": "iSolarCloud (28)",
        "suryalog": "SuryaLog (12)",
    }

    def filter_plants_dict():
        cat = cat_select.value if 'cat_select' in locals() and cat_select else "all"
        src = src_select.value if 'src_select' in locals() and src_select else "all"

        df_f = plants_meta_df
        if src != "all":
            df_f = df_f[df_f["source"] == src]

        if cat == "active":
            df_f = df_f[df_f["op_status"] == "active"]
        elif cat in ("inactive", "decommissioned"):
            df_f = df_f[df_f["op_status"] == "decommissioned"]
        elif cat == "generating_today":
            df_f = df_f[df_f["today_kwh"] > 0.05]
        elif cat == "offline_today":
            df_f = df_f[(df_f["today_kwh"] <= 0.05) & (df_f["today_status"] != "fault")]
        elif cat == "fault_today":
            df_f = df_f[df_f["today_status"] == "fault"]
        elif cat == "anomalies":
            df_f = df_f[df_f["is_anomaly"] == 1]
        elif cat == "tier_best":
            df_f = df_f[df_f["month_tier"] == "Best"]
        elif cat == "tier_good":
            df_f = df_f[df_f["month_tier"] == "Good"]
        elif cat == "tier_could_be_better":
            df_f = df_f[df_f["month_tier"] == "Could Be Better"]
        elif cat == "tier_needs_attention":
            df_f = df_f[df_f["month_tier"] == "Needs Attention"]
        elif cat == "tier_critical":
            df_f = df_f[df_f["month_tier"] == "Critical"]

        opts = {}
        for _, r in df_f.iterrows():
            tag = " [Inactive]" if r.get("op_status") == "decommissioned" else ""
            dot = "🟢 " if r.get("today_kwh", 0) > 0.05 else ""
            opts[r["plant_id"]] = f"{dot}{r['plant_name']}{tag} ({r['plant_id']})"
        return opts

    cur_sel = app_state.get("selected_plant")
    initial_options = filter_plants_dict()
    first_plant = cur_sel if cur_sel in initial_options else (list(initial_options.keys())[0] if initial_options else None)
    selected_plant["id"] = first_plant

    with ui.row().classes("w-full items-center gap-3 mb-6 flex-wrap"):
        cat_select = ui.select(
            options=get_category_options(),
            value="all",
            label="Category"
        ).classes("w-56").props("dense outlined dark options-dense")

        src_select = ui.select(
            options=portal_options,
            value="all",
            label="Portal"
        ).classes("w-40").props("dense outlined dark options-dense")

        plant_select = ui.select(
            options=initial_options,
            value=first_plant,
            label="Search & Select Plant",
            with_input=True
        ).classes("flex-1 min-w-[280px]").props("dense outlined dark options-dense")

        count_badge = ui.badge(f"{len(initial_options)} Plants", color="blue-9").classes("text-xs text-white px-2.5 py-1.5")

        avail_months = db.get_available_months()
        month_select = ui.select(
            options=avail_months,
            value=selected_plant["month"] if selected_plant["month"] in avail_months else avail_months[0],
            label="Reporting Month"
        ).classes("w-36").props("dense outlined dark options-dense")

        # Quick month presets
        with ui.button_group().props("dense outline"):
            ui.button("Sep 2026", on_click=lambda: set_plant_month("2026-09")).props("dense text-color=white")
            ui.button("Aug 2026", on_click=lambda: set_plant_month("2026-08")).props("dense text-color=white")

        sync_plant_btn = ui.button(
            "⚡ Live Sync Plant",
            icon="sync"
        ).props("dense unelevated color=amber-8 text-color=white").tooltip("Fetch live telemetry for this plant directly from its portal")

        async def on_sync_single_plant():
            pid = selected_plant["id"]
            if not pid:
                return
            p_df = db.query_df("SELECT * FROM plants WHERE plant_id = ?", [pid], db="analytics")
            if p_df.empty:
                return
            p_row = p_df.iloc[0].to_dict()
            p_name = p_row.get("plant_name") or pid
            p_src = p_row.get("source")

            start_t = time.time()
            est_t = 10.0 if p_src == "suryalog" else 8.0
            stop_plant_timer = asyncio.Event()

            if not getattr(client, '_deleted', False):
                with client:
                    sync_plant_btn.disable()
                    sync_plant_btn.set_text("Syncing (0.0s)...")
                    ui.notify(f"⚡ Fetching live telemetry for {p_name} (est ~{est_t:.0f}s)...", type="info", timeout=3000)

            async def run_plant_timer():
                while not stop_plant_timer.is_set():
                    el = time.time() - start_t
                    if not getattr(client, '_deleted', False):
                        with client:
                            sync_plant_btn.set_text(f"Syncing ({el:.1f}s)...")
                    await asyncio.sleep(0.2)

            timer_task = asyncio.create_task(run_plant_timer())

            try:
                try:
                    from pipeline import pipeline
                except ImportError:
                    import pipeline
                if p_src == "suryalog":
                    from extractors.suryalog import SuryaLogExtractor
                    ext = SuryaLogExtractor()
                    await asyncio.to_thread(ext.scrape_live_portal, target_plant_name=p_name)
                    await asyncio.to_thread(pipeline.run_fleet, sources=["suryalog"], force_refresh=False)
                    await asyncio.to_thread(pipeline.run_daily, sources=["suryalog"], force_refresh=False)
                    await asyncio.to_thread(pipeline.run_monthly, month_str=selected_plant["month"], sources=["suryalog"], force_refresh=False)
                    try:
                        from core import analytics
                    except ImportError:
                        import analytics
                    analytics.classify_all(selected_plant["month"])
                else:
                    await asyncio.to_thread(pipeline.run_full_extract, month_str=selected_plant["month"], sources=[p_src] if p_src else None, force_refresh=True, target_plant_id=pid)

                stop_plant_timer.set()
                try:
                    timer_task.cancel()
                except Exception:
                    pass

                el_total = round(time.time() - start_t, 2)
                if not getattr(client, '_deleted', False):
                    with client:
                        ui.notify(f"Live telemetry updated for {p_name} in {el_total}s!", type="positive")
                        render_cockpit.refresh()
            except Exception as ex:
                stop_plant_timer.set()
                try:
                    timer_task.cancel()
                except Exception:
                    pass
                if not getattr(client, '_deleted', False):
                    with client:
                        ui.notify(f"Failed to sync {p_name}: {ex}", type="negative")
            finally:
                stop_plant_timer.set()
                try:
                    timer_task.cancel()
                except Exception:
                    pass
                if not getattr(client, '_deleted', False):
                    with client:
                        sync_plant_btn.set_text("⚡ Live Sync Plant")
                        sync_plant_btn.enable()

        sync_plant_btn.on_click(on_sync_single_plant)

    def _fetch_plant_data(pid: str, m_val: str):
        p_df = db.query_df("SELECT * FROM plants WHERE plant_id = ?", [pid], db="analytics")
        if p_df.empty:
            return None
        plant = p_df.iloc[0].to_dict()

        # Daily generation for that month
        d_df = db.query_df(
            "SELECT date, kwh, specific_yield, live_power_kw, status, last_log_time FROM daily_generation WHERE plant_id = ? AND strftime('%Y-%m', date) = ? ORDER BY date ASC",
            [pid, m_val],
            db="analytics"
        )
        daily = d_df.to_dict(orient="records") if not d_df.empty else []

        # Monthly record for that month
        m_df = db.query_df(
            "SELECT month, kwh, revenue_inr, specific_yield, yield_per_day, pr_pct, tier, percentile, anomaly_score, anomaly_flag FROM monthly_generation WHERE plant_id = ? AND month = ?",
            [pid, m_val],
            db="analytics"
        )
        monthly_row = m_df.iloc[0].to_dict() if not m_df.empty else {}

        # Full lifetime generation history
        hist_df = db.query_df(
            "SELECT month, kwh, specific_yield, yield_per_day, tier FROM monthly_generation WHERE plant_id = ? ORDER BY month ASC",
            [pid],
            db="analytics"
        )
        history = hist_df.to_dict(orient="records") if not hist_df.empty else []

        # Loss analysis record for that plant and month
        loss_df = db.query_df(
            "SELECT * FROM loss_analysis WHERE plant_id = ? AND month = ?",
            [pid, m_val],
            db="analytics"
        )
        loss_row = loss_df.iloc[0].to_dict() if not loss_df.empty else {}

        # Latest inverter snapshots
        inv_df = db.query_df(
            """
            SELECT inverter_sn, max(snapshot_ts) as snapshot_ts, ac_power_w, dc_power_w, temperature_c, e_today_kwh, fault_code, status
            FROM inverter_snapshots WHERE plant_id = ?
            GROUP BY inverter_sn
            """,
            [pid],
            db="analytics"
        )
        inverters = []
        if not inv_df.empty:
            for r in inv_df.to_dict(orient="records"):
                ac = float(r.get("ac_power_w") or 0.0)
                dc = float(r.get("dc_power_w") or 0.0)
                eff = f"{round((ac / dc) * 100.0, 1)}%" if (dc > 0 and ac > 0) else "—"
                r["efficiency_str"] = eff
                inverters.append(r)

        tier, percentile, explanation = analytics.classify_plant(pid, m_val)

        # Lifetime generation: prioritize authoritative portal reading from the inverter/portal
        portal_total = float(plant.get("total_energy_kwh") or 0.0)
        if portal_total > 0:
            lifetime_val = portal_total
        else:
            tot_df = db.query_df(
                """
                SELECT SUM(kwh) as total_sum 
                FROM monthly_generation m
                JOIN plants p ON m.plant_id = p.plant_id
                WHERE m.plant_id = ? 
                  AND (p.install_date IS NULL OR m.month >= strftime('%Y-%m', p.install_date))
                """,
                [pid],
                db="analytics"
            )
            month_sum = float(tot_df.iloc[0]["total_sum"] or 0.0) if not tot_df.empty else 0.0
            lifetime_val = month_sum

        today_str = datetime.date.today().strftime("%Y-%m-%d")
        # Last recorded day for this plant across entire history up to today
        last_rec_df = db.query_df(
            "SELECT max(date) as last_day FROM daily_generation WHERE plant_id = ? AND kwh > 0 AND date <= ?",
            [pid, today_str],
            db="analytics"
        )
        last_recorded_day = None
        if not last_rec_df.empty and last_rec_df.iloc[0]["last_day"]:
            last_recorded_day = str(last_rec_df.iloc[0]["last_day"])
        else:
            last_rec_df = db.query_df(
                "SELECT max(date) as last_day FROM daily_generation WHERE plant_id = ? AND date <= ?",
                [pid, today_str],
                db="analytics"
            )
            if not last_rec_df.empty and last_rec_df.iloc[0]["last_day"]:
                last_recorded_day = str(last_rec_df.iloc[0]["last_day"])

        target_day = last_recorded_day or (daily[-1]["date"] if daily else today_str)
        if target_day > today_str:
            target_day = today_str
        target_day_kwh = 0.0
        if daily:
            for d in daily:
                if d.get("date") == target_day:
                    target_day_kwh = float(d.get("kwh") or 0.0)
                    break
            if target_day_kwh == 0.0:
                target_day_kwh = float(daily[-1].get("kwh") or 0.0)

        cap_val = float(plant.get("capacity_kwp") or 3.3)
        hourly_hours, hourly_data, is_live_telemetry = _get_hourly_profile(pid, target_day, target_day_kwh, cap_val)

        return {
            "plant": plant,
            "daily": daily,
            "monthly_row": monthly_row,
            "history": history,
            "loss_row": loss_row,
            "inverters": inverters,
            "tier": tier,
            "percentile": percentile,
            "explanation": explanation,
            "lifetime_val": lifetime_val,
            "last_recorded_day": last_recorded_day,
            "target_day": target_day,
            "hourly_hours": hourly_hours,
            "hourly_data": hourly_data,
            "is_live_telemetry": is_live_telemetry,
        }

    def _get_hourly_profile(pid: str, target_date: str, daily_kwh: float, capacity_kwp: float):
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        cur_hour = now.hour
        is_today = (target_date == today_str)

        snap_df = db.query_df(
            """
            SELECT strftime('%H:00', snapshot_ts) as hour_str,
                   avg(ac_power_w) as avg_ac_w,
                   max(ac_power_w) as max_ac_w,
                   max(e_today_kwh) as max_e_today
            FROM inverter_snapshots
            WHERE plant_id = ? AND strftime('%Y-%m-%d', snapshot_ts) = ?
            GROUP BY strftime('%H:00', snapshot_ts)
            ORDER BY hour_str ASC
            """,
            [pid, target_date],
            db="analytics"
        )

        # If snapshots are missing for today and it's a Growatt plant, auto-sync live telemetry
        if snap_df.empty and pid.startswith("growatt_") and is_today:
            try:
                from config import settings
                import growattServer
                raw_id = pid.replace("growatt_", "")
                api = growattServer.GrowattApi()
                if hasattr(settings, "growatt_server_url") and settings.growatt_server_url:
                    api.server_url = settings.growatt_server_url
                if getattr(settings, "growatt_user", None) and getattr(settings, "growatt_password", None):
                    api.login(settings.growatt_user, settings.growatt_password)
                    res = api.plant_detail(raw_id, growattServer.Timespan.day, now.date())
                    if isinstance(res, dict) and "data" in res:
                        data = res.get("data", {})
                        curr_e = float(str(res.get("plantData", {}).get("currentEnergy", "0")).split()[0] or 0)
                        snap_rows = []
                        for time_str, val in data.items():
                            w = float(val or 0.0)
                            snap_rows.append({
                                "plant_id": pid,
                                "inverter_sn": f"{raw_id}_main",
                                "snapshot_ts": f"{target_date}T{time_str}:00",
                                "ac_power_w": w,
                                "dc_power_w": w,
                                "temperature_c": 35.0,
                                "e_today_kwh": curr_e,
                                "fault_code": "0",
                                "status": "normal" if w > 0 else "standby"
                            })
                        if snap_rows:
                            db.upsert_snapshots(snap_rows)
                            snap_df = db.query_df(
                                """
                                SELECT strftime('%H:00', snapshot_ts) as hour_str,
                                       avg(ac_power_w) as avg_ac_w,
                                       max(ac_power_w) as max_ac_w,
                                       max(e_today_kwh) as max_e_today
                                FROM inverter_snapshots
                                WHERE plant_id = ? AND strftime('%Y-%m-%d', snapshot_ts) = ?
                                GROUP BY strftime('%H:00', snapshot_ts)
                                ORDER BY hour_str ASC
                                """,
                                [pid, target_date],
                                db="analytics"
                            )
            except Exception:
                pass

        hours = [f"{h:02d}:00" for h in range(6, 19)]  # 06:00 to 18:00
        snap_map = {}
        if not snap_df.empty:
            for _, r in snap_df.iterrows():
                h = str(r["hour_str"])
                kwh_h = round(float(r["avg_ac_w"] or 0.0) / 1000.0, 2)
                snap_map[h] = kwh_h

        is_live = bool(snap_map and any(v > 0 for v in snap_map.values()))

        # Physical solar diurnal bell-curve weights from 06:00 to 18:00 (sum = 1.00)
        weights = [0.01, 0.03, 0.07, 0.12, 0.16, 0.18, 0.18, 0.13, 0.08, 0.03, 0.01, 0.00, 0.00]
        base_kwh = max(0.0, daily_kwh)
        hourly_series = []
        for i, h in enumerate(hours):
            hour_int = int(h.split(":")[0])
            # Strict clamping: NEVER display generation in the future for today
            if is_today and hour_int > cur_hour:
                hourly_series.append(0.0)
                continue

            if h in snap_map and snap_map[h] > 0:
                hourly_series.append(snap_map[h])
            elif not is_today and base_kwh > 0 and i < len(weights):
                val = round(base_kwh * weights[i], 2)
                hourly_series.append(val)
            elif is_today and not is_live and base_kwh > 0 and i < len(weights) and hour_int <= cur_hour:
                val = round(base_kwh * weights[i], 2)
                hourly_series.append(val)
            else:
                hourly_series.append(0.0)

        return hours, hourly_series, is_live

    @ui.refreshable
    def render_cockpit():
        pid = selected_plant["id"]
        m_val = selected_plant["month"]
        if not pid:
            ui.label("Select a plant to view full telemetry and analytics.").classes("text-gray-400 text-center mt-8")
            return

        data = _fetch_plant_data(pid, m_val)
        if not data:
            ui.label("Plant metadata not found.").classes("text-negative mt-4")
            return

        plant = data["plant"]
        daily = data["daily"]
        monthly_row = data["monthly_row"]
        history = data["history"]
        loss_row = data["loss_row"]
        inverters = data["inverters"]
        tier = data["tier"]
        percentile = data["percentile"]
        explanation = data["explanation"]
        lifetime_val = data["lifetime_val"]

        portal_last_update = (plant.get("last_log_time") or (daily[-1].get("last_log_time") if daily else None)) or "—"
        last_recorded_day = data.get("last_recorded_day") or (daily[-1]["date"] if daily else "—")
        target_day = data.get("target_day") or last_recorded_day
        hourly_hours = data.get("hourly_hours") or []
        hourly_data = data.get("hourly_data") or []
        is_live_telemetry = data.get("is_live_telemetry", False)

        # KPI row calculations
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        d_val = float(daily[-1]['kwh']) if (daily and daily[-1].get("kwh") is not None) else 0.0
        p_val = float(plant.get("today_energy_kwh") or 0.0) if (target_day == today_str) else 0.0
        best_day_kwh = max(d_val, p_val)
        if best_day_kwh > 0:
            today_kwh = f"{best_day_kwh:,.2f} kWh"
        elif daily and daily[-1].get("kwh") is not None:
            today_kwh = f"{float(daily[-1]['kwh']):,.2f} kWh"
        else:
            today_kwh = "—"
        month_kwh_val = float(monthly_row.get("kwh") or 0.0)
        month_kwh = f"{month_kwh_val:,.1f} kWh" if month_kwh_val > 0 else "0 kWh"
        total_kwh_str = f"{lifetime_val:,.1f} kWh" if lifetime_val > 0 else "0.0 kWh"

        savings_inr = f"₹{float(monthly_row.get('revenue_inr') or (month_kwh_val * 14.0)):,.0f}"
        sy_val = monthly_row.get("specific_yield")
        sy_str = f"{sy_val:.1f} kWh/kWp" if sy_val else "—"
        ypd_val = monthly_row.get("yield_per_day")
        ypd_str = f"{float(ypd_val):.2f} u/kWp/d" if (ypd_val is not None and float(ypd_val) > 0) else "—"

        op_status = plant.get("operational_status", "active")
        if op_status == "decommissioned":
            status_text = "DECOMMISSIONED"
            status_color = "purple-9"
        else:
            latest_status = daily[-1].get("status", "active") if daily else "active"
            status_text = latest_status.upper()
            status_color = "positive" if latest_status == "active" else "negative" if latest_status == "fault" else "grey-7"

        with ui.row().classes("w-full gap-4 mb-4 flex-wrap"):
            kpi_card("Installed Capacity", f"{plant.get('capacity_kwp', '—')} kWp", "bolt", "amber-5")
            kpi_card("Status", status_text, "circle", status_color)
            kpi_card("Total Gen", total_kwh_str, "all_inclusive", "blue-4")
            kpi_card(f"{m_val} Gen", month_kwh, "calendar_month", "teal-5")
            kpi_card("Latest Day kWh", today_kwh, "solar_power", "primary")
            kpi_card("Last Portal Update", portal_last_update, "schedule", "amber-4")
            kpi_card("Last Recorded Day", last_recorded_day, "event_available", "indigo-4")
            kpi_card("Est. Savings", savings_inr, "currency_rupee", "emerald-5")
            kpi_card("Specific Yield", sy_str, "speed", "purple-4")
            kpi_card("Yield / Day", ypd_str, "speed", "cyan-4")
            kpi_card("PR (%)", f"{float(monthly_row.get('pr_pct') or 0.0):.1f}%" if monthly_row.get('pr_pct') is not None else "—", "query_stats", "blue-4")
            kpi_card("Tier", tier, "star", "amber-4")
            kpi_card("Peer Percentile", f"P{percentile:.0f}", "leaderboard", "indigo-4")
            kpi_card("Location Conf.", f"{plant.get('geocode_level', 'unresolved')}", "place", "teal-4")
            kpi_card("RPI Index", f"{float(monthly_row.get('rpi_score', 1.0) or 1.0):.2f}", "insights", "amber-4")

        # ML Anomaly Callout Banner
        is_anomaly = int(monthly_row.get("anomaly_flag") or 0) == 1
        if is_anomaly:
            with ui.row().classes("w-full p-3 rounded-lg bg-red-950/70 border border-red-800 items-center justify-between mb-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("bolt", color="amber-4", size="sm")
                    with ui.column().classes("gap-0"):
                        ui.label("⚡ Machine Learning Anomaly Detected").classes("text-xs font-bold text-red-300 uppercase tracking-wider")
                        ui.label(explanation).classes("text-xs text-red-100")
                ui.badge(f"Score: {monthly_row.get('anomaly_score', '—')}", color="red-8").classes("text-white font-mono")
        elif explanation:
            with ui.row().classes("w-full p-2.5 rounded-lg bg-gray-900 border border-gray-800 items-center gap-2 mb-4"):
                ui.icon("info", color="cyan-4", size="xs")
                ui.label(explanation).classes("text-xs text-gray-300")

        # Operator Anomaly Review / Feedback Panel (Phase 5 Task 17b & Phase 6)
        with ui.card().classes("w-full p-4 rounded-lg bg-gray-900 border border-gray-800 mb-4"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("fact_check", color="amber-4", size="sm")
                    ui.label("Field Validation & Ground-Truth Anomaly Review").classes("text-sm font-semibold text-gray-200")
                ui.badge("Label Loop", color="indigo-8").classes("text-xs text-white")
            with ui.row().classes("w-full items-center gap-4 mt-2 flex-wrap"):
                review_outcome = ui.select(
                    options={"true_fault": "✅ Confirmed Real Fault", "false_alarm": "❌ False Alarm (Normal)", "unknown": "❓ Inconclusive / Pending Site Visit"},
                    value="true_fault" if is_anomaly else "false_alarm",
                    label="Technician Assessment"
                ).classes("w-64").props("dense outlined dark options-dense")
                review_notes = ui.input(label="Inspection Notes / Root Cause", placeholder="e.g. String fuse blown, tree shade at 4pm").classes("flex-1").props("dense outlined dark")

                async def submit_review():
                    if not pid:
                        return
                    out = review_outcome.value or "unknown"
                    notes_txt = review_notes.value or ""
                    await asyncio.to_thread(
                        db.log_anomaly_feedback,
                        plant_id=pid,
                        date_or_month=m_val,
                        flag_type="ML_ANOMALY" if is_anomaly else "OPERATOR_FLAG",
                        technician_label=out,
                        notes=notes_txt,
                        logged_by="operator"
                    )
                    ui.notify("Validation label logged successfully to ground-truth dataset!", type="positive", position="top")

                ui.button("Submit Validation", icon="save", on_click=submit_review).props("dense color=primary").classes("px-4")

        # Plant Loss Attribution Banner
        if loss_row:
            with ui.row().classes("w-full p-4 rounded-lg bg-gray-800 border border-gray-700 items-center justify-between mb-6"):
                with ui.column().classes("gap-1"):
                    ui.label(f"Physical Baseline vs Actual for {m_val}").classes("text-xs font-semibold text-gray-400 uppercase tracking-wider")
                    ui.label(f"Expected: {loss_row.get('expected_kwh', 0):,.1f} kWh  ·  Actual: {loss_row.get('actual_kwh', 0):,.1f} kWh  ·  Net Shortfall: {loss_row.get('shortfall_kwh', 0):,.1f} kWh").classes("text-sm font-bold text-white")
                with ui.row().classes("gap-2"):
                    ui.badge(f"PR: {loss_row.get('performance_ratio', 0):.1f}%", color="blue-8")
                    ui.badge(f"Realization: {loss_row.get('realization_rate_pct', 0):.1f}%", color="teal-8")
                    ui.badge(f"Soiling: {loss_row.get('soiling_loss_kwh', 0):.1f} kWh", color="amber-9")
                    ui.badge(f"Comm Loss: {loss_row.get('comm_loss_kwh', 0):.1f} kWh", color="rose-9")

        # Generation Graphs Grid: Hourly, Daily, and Monthly
        with ui.grid(columns=3).classes("w-full gap-4 mb-6"):
            # 1. Hourly Generation Profile Chart
            with ui.card().classes("p-4 bg-gray-900 border border-gray-800"):
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label(f"Hourly Generation ({target_day}) (kWh)").classes("text-sm font-semibold text-gray-300")
                    if is_live_telemetry:
                        ui.badge("🟢 Live Telemetry", color="emerald-9").classes("text-[10px] text-white")
                    elif target_day == datetime.date.today().strftime("%Y-%m-%d"):
                        ui.badge(f"Clamped to {datetime.datetime.now().strftime('%H:%M')}", color="amber-9").classes("text-[10px] text-white")
                    else:
                        ui.badge("Diurnal Model", color="gray-7").classes("text-[10px] text-gray-300")
                ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "grid": {"left": "3%", "right": "4%", "bottom": "8%", "containLabel": True},
                    "xAxis": {
                        "type": "category",
                        "data": hourly_hours,
                        "axisLine": {"lineStyle": {"color": "#6B7280"}},
                        "axisLabel": {"color": "#9CA3AF", "rotate": 35, "fontSize": 10}
                    },
                    "yAxis": {
                        "type": "value",
                        "name": "kWh",
                        "axisLine": {"lineStyle": {"color": "#6B7280"}},
                        "axisLabel": {"color": "#9CA3AF"},
                        "splitLine": {"lineStyle": {"color": "#1F2937"}}
                    },
                    "series": [{
                        "name": "Hourly Gen (kWh)",
                        "type": "line",
                        "smooth": True,
                        "data": hourly_data,
                        "itemStyle": {"color": "#F59E0B"},
                        "areaStyle": {"color": "rgba(245, 158, 11, 0.2)"}
                    }]
                }).classes("w-full h-64")

            # 2. Daily Generation Chart
            with ui.card().classes("p-4 bg-gray-900 border border-gray-800"):
                ui.label(f"Daily Generation in {m_val} (kWh)").classes("text-sm font-semibold text-gray-300 mb-2")
                ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "grid": {"left": "3%", "right": "4%", "bottom": "8%", "containLabel": True},
                    "xAxis": {
                        "type": "category",
                        "data": [d["date"] for d in daily],
                        "axisLine": {"lineStyle": {"color": "#6B7280"}},
                        "axisLabel": {"color": "#9CA3AF", "rotate": 35, "fontSize": 10}
                    },
                    "yAxis": {
                        "type": "value",
                        "name": "kWh",
                        "axisLine": {"lineStyle": {"color": "#6B7280"}},
                        "axisLabel": {"color": "#9CA3AF"},
                        "splitLine": {"lineStyle": {"color": "#1F2937"}}
                    },
                    "series": [{
                        "name": "Daily Gen (kWh)",
                        "type": "bar",
                        "data": [round(d.get("kwh") or 0.0, 1) for d in daily],
                        "itemStyle": {"color": "#10B981", "borderRadius": [3, 3, 0, 0]}
                    }]
                }).classes("w-full h-64")

            # 3. Monthly Generation Trend Chart (Full Lifetime History with Zoom)
            with ui.card().classes("p-4 bg-gray-900 border border-gray-800"):
                with ui.row().classes("w-full items-center justify-between mb-2 flex-wrap gap-2"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Monthly Generation Trend (kWh)").classes("text-sm font-semibold text-gray-300")
                        hist_len = len(history)
                        if hist_len > 12:
                            ui.badge(f"{hist_len} Months (Lifetime)", color="indigo-8").classes("text-[10px] text-white px-2 py-0.5 font-mono")
                        else:
                            ui.badge(f"{hist_len} Months", color="blue-9").classes("text-[10px] text-white px-2 py-0.5 font-mono")

                # Highlight selected reporting month
                mark_point_data = []
                for h in history:
                    if h.get("month") == m_val:
                        val_num = round(h.get("kwh") or 0.0, 1)
                        mark_point_data.append({
                            "name": f"Selected ({m_val})",
                            "coord": [m_val, val_num],
                            "value": f"{val_num:,.0f}",
                            "itemStyle": {"color": "#3B82F6", "borderColor": "#60A5FA", "borderWidth": 2}
                        })

                # Calculate default zoom window to show recent months but allow panning back to earliest
                zoom_start = 0
                if len(history) > 24:
                    zoom_start = max(0, int((1.0 - (24.0 / len(history))) * 100))

                ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "grid": {"left": "3%", "right": "4%", "bottom": "18%", "containLabel": True},
                    "xAxis": {
                        "type": "category",
                        "data": [h["month"] for h in history],
                        "axisLine": {"lineStyle": {"color": "#6B7280"}},
                        "axisLabel": {"color": "#9CA3AF", "rotate": 35, "fontSize": 10}
                    },
                    "yAxis": {
                        "type": "value",
                        "name": "kWh",
                        "axisLine": {"lineStyle": {"color": "#6B7280"}},
                        "axisLabel": {"color": "#9CA3AF"},
                        "splitLine": {"lineStyle": {"color": "#1F2937"}}
                    },
                    "dataZoom": [
                        {
                            "type": "inside",
                            "start": zoom_start,
                            "end": 100
                        },
                        {
                            "type": "slider",
                            "bottom": "0%",
                            "height": 18,
                            "borderColor": "#374151",
                            "fillerColor": "rgba(59, 130, 246, 0.2)",
                            "handleStyle": {"color": "#3B82F6"},
                            "textStyle": {"color": "#9CA3AF", "fontSize": 9},
                            "start": zoom_start,
                            "end": 100
                        }
                    ],
                    "series": [{
                        "name": "Month Total (kWh)",
                        "type": "line",
                        "smooth": True,
                        "data": [round(h.get("kwh") or 0.0, 1) for h in history],
                        "itemStyle": {"color": "#3B82F6"},
                        "areaStyle": {"color": "rgba(59,130,246,0.15)"},
                        "markPoint": {
                            "data": mark_point_data,
                            "symbol": "pin",
                            "symbolSize": 44,
                            "label": {"fontSize": 10, "fontWeight": "bold", "color": "#FFFFFF"}
                        } if mark_point_data else None
                    }]
                }).classes("w-full h-64")

        # Telemetry & Inverter details
        with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800"):
            ui.label("Inverter Telemetry Snapshots").classes("text-sm font-semibold text-gray-300 mb-3")
            if inverters:
                inv_cols = [
                    {"name": "inverter_sn", "label": "Serial Number", "field": "inverter_sn", "align": "left"},
                    {"name": "status", "label": "Status", "field": "status", "align": "center"},
                    {"name": "ac_power_w", "label": "Live AC (W)", "field": "ac_power_w", "align": "right"},
                    {"name": "dc_power_w", "label": "DC Input (W)", "field": "dc_power_w", "align": "right"},
                    {"name": "efficiency_str", "label": "Efficiency", "field": "efficiency_str", "align": "center"},
                    {"name": "temperature_c", "label": "Temp (°C)", "field": "temperature_c", "align": "right"},
                    {"name": "e_today_kwh", "label": "Today kWh", "field": "e_today_kwh", "align": "right"},
                    {"name": "fault_code", "label": "Fault Code", "field": "fault_code", "align": "center"},
                    {"name": "snapshot_ts", "label": "Timestamp", "field": "snapshot_ts", "align": "right"},
                ]
                ui.table(columns=inv_cols, rows=inverters, row_key="inverter_sn").classes("w-full")
            else:
                ui.label("No live inverter telemetry available for this plant.").classes("text-xs text-gray-500 italic")

    def on_filter_change(e=None):
        opts = filter_plants_dict()
        plant_select.options = opts
        count_badge.set_text(f"{len(opts)} Plants")
        cur_id = selected_plant["id"]
        if cur_id not in opts:
            new_id = list(opts.keys())[0] if opts else None
            selected_plant["id"] = new_id
            plant_select.value = new_id
            render_cockpit.refresh()
        else:
            plant_select.value = cur_id

    def set_plant_month(m_val: str):
        nonlocal plants_meta_df
        selected_plant["month"] = m_val
        month_select.value = m_val
        app_state["month"] = m_val
        plants_meta_df = load_plant_metadata()
        cat_select.options = get_category_options()
        on_filter_change()
        render_cockpit.refresh()

    def handle_plant_change(e):
        selected_plant["id"] = plant_select.value
        render_cockpit.refresh()

    cat_select.on("update:model-value", on_filter_change)
    src_select.on("update:model-value", on_filter_change)
    plant_select.on("update:model-value", handle_plant_change)
    month_select.on("update:model-value", lambda e: set_plant_month(month_select.value))

    # Register external month and plant change listener
    def on_global_update():
        changed = False
        if app_state.get("month") != selected_plant["month"]:
            set_plant_month(app_state.get("month", "2026-09"))
            changed = True
        if app_state.get("selected_plant") and app_state.get("selected_plant") != selected_plant["id"]:
            selected_plant["id"] = app_state.get("selected_plant")
            opts = filter_plants_dict()
            if selected_plant["id"] in opts:
                plant_select.value = selected_plant["id"]
            changed = True
        if changed:
            render_cockpit.refresh()

    if "refresh_listeners" in app_state:
        app_state["refresh_listeners"].append(on_global_update)

    render_cockpit()
