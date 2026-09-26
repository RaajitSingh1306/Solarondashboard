import asyncio
import datetime
import logging
from nicegui import ui
import db
import analytics

logger = logging.getLogger(__name__)

def build_analytics_tab(app_state: dict):
    selected_period = {
        "month": app_state.get("month", "2026-09"),
        "platform": app_state.get("source", "All")
    }

    # Top Control Bar
    with ui.row().classes("w-full items-center gap-3 mb-6"):
        avail_months = db.get_available_months()
        default_month = selected_period["month"] if selected_period["month"] in avail_months else (avail_months[0] if avail_months else "2026-09")
        month_select = ui.select(
            options=avail_months or ["2026-09", "2026-08"],
            value=default_month,
            label="Analysis Month"
        ).classes("w-40").props("dense outlined dark options-dense")

        # Quick Period Presets
        with ui.button_group().props("dense outline"):
            ui.button("Sep 2026", on_click=lambda: asyncio.create_task(set_period("2026-09"))).props("dense text-color=white")
            ui.button("Aug 2026", on_click=lambda: asyncio.create_task(set_period("2026-08"))).props("dense text-color=white")

        platform_filter = ui.select(
            options=["All", "growatt", "isolarcloud", "suryalog"],
            value=selected_period["platform"],
            label="Platform"
        ).classes("w-40").props("dense outlined dark options-dense")

        apply_btn = ui.button("Apply Period", icon="refresh").props("dense color=primary unelevated")

        ui.space()

        ui.button(
            "CSV",
            on_click=lambda: ui.download(f"/api/export/fleet-daily?fmt=csv&month={selected_period['month']}"),
            icon="download"
        ).props("dense flat color=primary")

        ui.button(
            "XLSX",
            on_click=lambda: ui.download(f"/api/export/fleet-daily?fmt=xlsx&month={selected_period['month']}"),
            icon="download"
        ).props("dense flat color=positive")

    # Section 1: NASA GHI Generation Baseline & Loss Decomposition Section
    with ui.card().classes("w-full p-5 bg-gray-900 border border-gray-800 mb-6"):
        with ui.row().classes("w-full items-center justify-between mb-3"):
            with ui.column().classes("gap-0"):
                ui.label("NASA GHI Baseline & 6-Part Loss Attribution Engine").classes("text-base font-bold text-amber-400 tracking-wide")
                ui.label("Physics-based shortfall decomposition against NASA POWER solar irradiance benchmark").classes("text-xs text-gray-400")
            loss_month_badge = ui.badge("Month: 2026-09", color="amber-8").props("text-color=black font-bold")

        # Loss summary metrics cards (Persistent components with reactive labels)
        waterfall_kpis = ui.row().classes("w-full gap-4 mb-4")
        with waterfall_kpis:
            with ui.card().classes("flex-1 p-3 bg-gray-800 border border-gray-700"):
                exp_title_label = ui.label("Expected Baseline").classes("text-xs text-gray-400 font-medium")
                exp_mwh_label = ui.label("— MWh").classes("text-xl font-bold text-blue-400")
                exp_sub_label = ui.label("— installations analyzed").classes("text-[10px] text-gray-500")

            with ui.card().classes("flex-1 p-3 bg-gray-800 border border-gray-700"):
                ui.label("Actual Harvest").classes("text-xs text-gray-400 font-medium")
                act_mwh_label = ui.label("— MWh").classes("text-xl font-bold text-emerald-400")
                ui.label("Realized Generation").classes("text-[10px] text-gray-500")

            with ui.card().classes("flex-1 p-3 bg-gray-800 border border-gray-700"):
                ui.label("Net Shortfall").classes("text-xs text-gray-400 font-medium")
                short_mwh_label = ui.label("— MWh").classes("text-xl font-bold text-rose-400")
                ui.label("Loss to attribution").classes("text-[10px] text-gray-500")

            with ui.card().classes("flex-1 p-3 bg-gray-800 border border-gray-700"):
                ui.label("Realization Rate").classes("text-xs text-gray-400 font-medium")
                realization_label = ui.label("—%").classes("text-xl font-bold text-amber-400")
                ui.label("Actual vs Expected").classes("text-[10px] text-gray-500")

            with ui.card().classes("flex-1 p-3 bg-gray-800 border border-gray-700"):
                ui.label("ML Anomalies").classes("text-xs text-gray-400 font-medium")
                anomaly_count_label = ui.label("—").classes("text-xl font-bold text-rose-400")
                ui.label("Outlier underperformers").classes("text-[10px] text-gray-500")

        # Waterfall Chart & Breakdown details side by side
        with ui.grid(columns=2).classes("w-full gap-6"):
            loss_chart = ui.echart({
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "grid": {"left": "3%", "right": "4%", "bottom": "10%", "top": "12%", "containLabel": True},
                "xAxis": {
                    "type": "category",
                    "data": ["Expected", "Actual", "Comm Loss", "Weather", "Soiling", "Shading", "Unexplained"],
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#D1D5DB", "rotate": 20, "fontSize": 11}
                },
                "yAxis": {
                    "type": "value",
                    "name": "MWh",
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"},
                    "splitLine": {"lineStyle": {"color": "#1F2937"}}
                },
                "series": [{
                    "name": "Energy MWh",
                    "type": "bar",
                    "data": [],
                    "itemStyle": {"borderRadius": [4, 4, 0, 0]}
                }]
            }).classes("w-full h-72")

            loss_cards_col = ui.column().classes("w-full gap-3 justify-center")
            loss_val_labels = {}
            with loss_cards_col:
                loss_items_meta = [
                    ("comm", "📡 Communication & Zero Gen Loss", "Offline telemetry or zero day outputs", "text-rose-400"),
                    ("weather", "☁️ Weather & Irradiance Deficit", "Cloud cover vs standard clear sky", "text-amber-400"),
                    ("soiling", "🧼 Soiling & Dust Loss", "Standard panel surface dust accumulation", "text-orange-400"),
                    ("shading", "🌿 Shading & Obstruction Loss", "Building / vegetation horizon shadows", "text-purple-400"),
                    ("unknown", "❓ Unexplained / Residual Shortfall", "Inverter clipping & balance of system", "text-gray-400"),
                ]
                for key, label, desc, color_cls in loss_items_meta:
                    with ui.row().classes("w-full items-center justify-between p-2 rounded bg-gray-800 border border-gray-700"):
                        with ui.column().classes("gap-0"):
                            ui.label(label).classes(f"text-xs font-semibold {color_cls}")
                            ui.label(desc).classes("text-[10px] text-gray-400")
                        loss_val_labels[key] = ui.label("— MWh").classes(f"text-sm font-bold {color_cls}")

    # Section 2: Fleet Performance Charts Grid
    with ui.grid(columns=2).classes("w-full gap-6"):
        # Chart 1: Daily Generation Trend
        with ui.card().classes("p-4 w-full bg-gray-900 border border-gray-800"):
            ui.label("Fleet Daily Generation Trend (kWh)").classes("text-sm font-semibold text-gray-300 mb-2")
            daily_chart = ui.echart({
                "tooltip": {"trigger": "axis"},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {
                    "type": "category",
                    "data": [],
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"}
                },
                "yAxis": {
                    "type": "value",
                    "name": "kWh",
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"},
                    "splitLine": {"lineStyle": {"color": "#1F2937"}}
                },
                "series": [{
                    "name": "Total Generation (kWh)",
                    "type": "line",
                    "smooth": True,
                    "data": [],
                    "itemStyle": {"color": "#F0A500"},
                    "areaStyle": {"color": "rgba(240,165,0,0.15)"}
                }]
            }).classes("w-full h-64")

        # Chart 2: Tier Distribution
        with ui.card().classes("p-4 w-full bg-gray-900 border border-gray-800"):
            ui.label("Performance Tier Distribution").classes("text-sm font-semibold text-gray-300 mb-2")
            tier_chart = ui.echart({
                "tooltip": {"trigger": "axis"},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {
                    "type": "value",
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"},
                    "splitLine": {"lineStyle": {"color": "#1F2937"}}
                },
                "yAxis": {
                    "type": "category",
                    "data": ["Best", "Good", "Could Be Better", "Needs Attention", "Critical", "Offline", "Fault", "Decommissioned"],
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"}
                },
                "series": [{
                    "name": "Plants",
                    "type": "bar",
                    "data": []
                }]
            }).classes("w-full h-64")

        # Chart 3: Platform Comparison
        with ui.card().classes("p-4 w-full bg-gray-900 border border-gray-800"):
            platform_chart_label = ui.label("Average Specific Yield by Platform (kWh/kWp)").classes("text-sm font-semibold text-gray-300 mb-2")
            platform_chart = ui.echart({
                "tooltip": {"trigger": "axis"},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {
                    "type": "category",
                    "data": ["Growatt", "iSolarCloud", "SuryaLog"],
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"}
                },
                "yAxis": {
                    "type": "value",
                    "name": "kWh/kWp",
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"},
                    "splitLine": {"lineStyle": {"color": "#1F2937"}}
                },
                "series": [{
                    "name": "Avg Yield",
                    "type": "bar",
                    "data": [0, 0, 0],
                    "itemStyle": {"color": "#8B5CF6", "borderRadius": [4, 4, 0, 0]}
                }]
            }).classes("w-full h-64")

        # Chart 4: Top 10 Producers
        with ui.card().classes("p-4 w-full bg-gray-900 border border-gray-800"):
            top_chart_label = ui.label("Top 10 Producing Plants (Monthly kWh)").classes("text-sm font-semibold text-gray-300 mb-2")
            top_chart = ui.echart({
                "tooltip": {"trigger": "axis"},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {
                    "type": "value",
                    "name": "Monthly kWh",
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"},
                    "splitLine": {"lineStyle": {"color": "#1F2937"}}
                },
                "yAxis": {
                    "type": "category",
                    "data": [],
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"}
                },
                "series": [{
                    "name": "Monthly kWh",
                    "type": "bar",
                    "data": [],
                    "itemStyle": {"color": "#06B6D4", "borderRadius": [0, 4, 4, 0]}
                }]
            }).classes("w-full h-64")

    async def refresh_charts():
        try:
            m_val = selected_period["month"]
            src = platform_filter.value
            src_label = src.title() if src and src != "All" else "All Platforms"
            loss_month_badge.text = f"Month: {m_val}  ·  Platform: {src_label}"

            # Build SQL queries
            sql1 = """
            SELECT d.date, sum(d.kwh) as total_kwh
            FROM daily_generation d
            JOIN plants p ON d.plant_id = p.plant_id
            WHERE strftime('%Y-%m', d.date) = ?
              AND (p.operational_status IS NULL OR p.operational_status != 'decommissioned')
            """
            params1 = [m_val]
            if src and src != "All":
                sql1 += " AND lower(p.source) = ?"
                params1.append(src.lower())
            sql1 += " GROUP BY d.date ORDER BY d.date ASC"

            sql2 = """
            SELECT coalesce(m.tier, CASE WHEN p.operational_status = 'decommissioned' THEN 'Decommissioned' ELSE 'Offline' END) as tier, count(*) as count 
            FROM plants p
            LEFT JOIN monthly_generation m ON p.plant_id = m.plant_id AND m.month = ?
            WHERE 1=1
            """
            params2 = [m_val]
            if src and src != "All":
                sql2 += " AND lower(p.source) = ?"
                params2.append(src.lower())
            sql2 += " GROUP BY coalesce(m.tier, CASE WHEN p.operational_status = 'decommissioned' THEN 'Decommissioned' ELSE 'Offline' END)"

            if not src or src == "All":
                sql3 = """
                SELECT p.source, avg(m.specific_yield) as avg_yield
                FROM monthly_generation m
                JOIN plants p ON m.plant_id = p.plant_id
                WHERE m.specific_yield > 0 AND m.month = ?
                  AND (p.operational_status IS NULL OR p.operational_status != 'decommissioned')
                GROUP BY p.source
                """
                params3 = [m_val]
            else:
                sql3 = """
                SELECT 
                    CASE 
                        WHEN m.specific_yield < 50 THEN '< 50'
                        WHEN m.specific_yield < 75 THEN '50 - 75'
                        WHEN m.specific_yield < 100 THEN '75 - 100'
                        WHEN m.specific_yield < 125 THEN '100 - 125'
                        ELSE '> 125'
                    END as bracket,
                    count(*) as count
                FROM monthly_generation m
                JOIN plants p ON m.plant_id = p.plant_id
                WHERE m.month = ? AND lower(p.source) = ?
                  AND (p.operational_status IS NULL OR p.operational_status != 'decommissioned')
                GROUP BY bracket
                """
                params3 = [m_val, src.lower()]

            sql4 = """
            SELECT p.plant_name, m.kwh as total_kwh
            FROM monthly_generation m
            JOIN plants p ON m.plant_id = p.plant_id
            WHERE m.month = ? AND (p.operational_status IS NULL OR p.operational_status != 'decommissioned')
            """
            params4 = [m_val]
            if src and src != "All":
                sql4 += " AND lower(p.source) = ?"
                params4.append(src.lower())
            sql4 += " ORDER BY total_kwh DESC LIMIT 10"

            sql5 = """
            SELECT count(*) as anom_count
            FROM monthly_generation m
            JOIN plants p ON m.plant_id = p.plant_id
            WHERE m.month = ? AND coalesce(m.anomaly_flag, 0) = 1
              AND (p.operational_status IS NULL OR p.operational_status != 'decommissioned')
            """
            params5 = [m_val]
            if src and src != "All":
                sql5 += " AND lower(p.source) = ?"
                params5.append(src.lower())

            # Execute waterfall calculation and all queries in background thread pool
            wf, df1, df2, df3, df4, df5 = await asyncio.gather(
                asyncio.to_thread(analytics.get_loss_waterfall, m_val, source=src),
                asyncio.to_thread(db.query_df, sql1, params1, "analytics"),
                asyncio.to_thread(db.query_df, sql2, params2, "analytics"),
                asyncio.to_thread(db.query_df, sql3, params3, "analytics"),
                asyncio.to_thread(db.query_df, sql4, params4, "analytics"),
                asyncio.to_thread(db.query_df, sql5, params5, "analytics")
            )

            # 0. Update Waterfall KPIs
            exp_mwh = round(wf["expected_kwh"] / 1000.0, 2)
            act_mwh = round(wf["actual_kwh"] / 1000.0, 2)
            short_mwh = round(wf["shortfall_kwh"] / 1000.0, 2)
            comm_mwh = round(wf["comm_loss_kwh"] / 1000.0, 2)
            weather_mwh = round(wf["weather_loss_kwh"] / 1000.0, 2)
            soiling_mwh = round(wf["soiling_loss_kwh"] / 1000.0, 2)
            shading_mwh = round(wf["shading_loss_kwh"] / 1000.0, 2)
            unknown_mwh = round(wf["unknown_loss_kwh"] / 1000.0, 2)

            anom_cnt = int(df5.iloc[0]["anom_count"]) if not df5.empty else 0

            exp_title_label.text = f"Expected Baseline ({src_label})"
            exp_mwh_label.text = f"{exp_mwh:,.1f} MWh"
            exp_sub_label.text = f"{wf['total_plants']} installations analyzed"
            act_mwh_label.text = f"{act_mwh:,.1f} MWh"
            short_mwh_label.text = f"{short_mwh:,.1f} MWh"
            realization_label.text = f"{wf['avg_realization']:.1f}%"
            anomaly_count_label.text = f"{anom_cnt} plants"

            # Update Waterfall EChart
            bar_colors = ["#3B82F6", "#10B981", "#EF4444", "#F59E0B", "#D97706", "#8B5CF6", "#6B7280"]
            loss_chart.options["series"][0]["data"] = [
                {"value": exp_mwh, "itemStyle": {"color": bar_colors[0]}},
                {"value": act_mwh, "itemStyle": {"color": bar_colors[1]}},
                {"value": comm_mwh, "itemStyle": {"color": bar_colors[2]}},
                {"value": weather_mwh, "itemStyle": {"color": bar_colors[3]}},
                {"value": soiling_mwh, "itemStyle": {"color": bar_colors[4]}},
                {"value": shading_mwh, "itemStyle": {"color": bar_colors[5]}},
                {"value": unknown_mwh, "itemStyle": {"color": bar_colors[6]}},
            ]
            loss_chart.update()

            # Update Loss items breakdown list
            loss_val_labels["comm"].text = f"{comm_mwh:.2f} MWh"
            loss_val_labels["weather"].text = f"{weather_mwh:.2f} MWh"
            loss_val_labels["soiling"].text = f"{soiling_mwh:.2f} MWh"
            loss_val_labels["shading"].text = f"{shading_mwh:.2f} MWh"
            loss_val_labels["unknown"].text = f"{unknown_mwh:.2f} MWh"

            # 1. Daily Trend
            if not df1.empty:
                daily_chart.options["xAxis"]["data"] = df1["date"].tolist()
                daily_chart.options["series"][0]["data"] = [round(v, 1) for v in df1["total_kwh"].fillna(0).tolist()]
            else:
                daily_chart.options["xAxis"]["data"] = []
                daily_chart.options["series"][0]["data"] = []
            daily_chart.update()

            # 2. Tier Distribution
            t_counts = {"Best": 0, "Good": 0, "Could Be Better": 0, "Needs Attention": 0, "Critical": 0, "Offline": 0, "Fault": 0, "Decommissioned": 0}
            for _, r in df2.iterrows():
                t = str(r["tier"])
                if t in t_counts:
                    t_counts[t] = int(r["count"])
            tier_colors = ["#10B981", "#3B82F6", "#F59E0B", "#F97316", "#EF4444", "#6B7280", "#DC2626", "#8B5CF6"]
            tier_chart.options["yAxis"]["data"] = list(t_counts.keys())
            tier_chart.options["series"][0]["data"] = [
                {"value": v, "itemStyle": {"color": tier_colors[i]}}
                for i, v in enumerate(t_counts.values())
            ]
            tier_chart.update()

            # 3. Platform Comparison / Yield Distribution
            if not src or src == "All":
                platform_chart_label.text = "Average Specific Yield by Platform (kWh/kWp)"
                p_map = {"growatt": 0.0, "isolarcloud": 0.0, "suryalog": 0.0}
                for _, r in df3.iterrows():
                    p_map[str(r["source"]).lower()] = round(float(r["avg_yield"] or 0), 2)
                platform_chart.options["xAxis"]["data"] = ["Growatt", "iSolarCloud", "SuryaLog"]
                platform_chart.options["series"][0]["name"] = "Avg Yield (kWh/kWp)"
                platform_chart.options["series"][0]["data"] = [p_map["growatt"], p_map["isolarcloud"], p_map["suryalog"]]
            else:
                platform_chart_label.text = f"{src.title()} Specific Yield Distribution (Plants per Yield Bracket)"
                b_counts = {"< 50": 0, "50 - 75": 0, "75 - 100": 0, "100 - 125": 0, "> 125": 0}
                for _, r in df3.iterrows():
                    b_counts[str(r["bracket"])] = int(r["count"])
                platform_chart.options["xAxis"]["data"] = list(b_counts.keys())
                platform_chart.options["series"][0]["name"] = f"Plants in {src.title()}"
                platform_chart.options["series"][0]["data"] = list(b_counts.values())
            platform_chart.update()

            # 4. Top 10 Plants
            top_chart_label.text = f"Top 10 Producing Plants ({src_label}) (Monthly kWh)"
            if not df4.empty:
                names = [name[:20] for name in df4["plant_name"].tolist()][::-1]
                values = [round(v, 1) for v in df4["total_kwh"].fillna(0).tolist()][::-1]
                top_chart.options["yAxis"]["data"] = names
                top_chart.options["series"][0]["data"] = values
            else:
                top_chart.options["yAxis"]["data"] = []
                top_chart.options["series"][0]["data"] = []
            top_chart.update()
        except Exception as e:
            logger.error(f"Error refreshing analytics charts: {e}", exc_info=True)
            ui.notify(f"Analytics refresh error: {e}", type="negative")

    async def set_period(m_val: str):
        selected_period["month"] = m_val
        month_select.value = m_val
        app_state["month"] = m_val
        await refresh_charts()

    month_select.on("update:model-value", lambda e: asyncio.create_task(set_period(month_select.value)))
    platform_filter.on("update:model-value", lambda: asyncio.create_task(refresh_charts()))
    apply_btn.on_click(lambda: asyncio.create_task(refresh_charts()))

    # Register external month change listener
    async def on_global_update():
        if app_state.get("month") != selected_period["month"]:
            selected_period["month"] = app_state.get("month", "2026-09")
            month_select.value = selected_period["month"]
        await refresh_charts()

    if "refresh_listeners" in app_state:
        app_state["refresh_listeners"].append(lambda: asyncio.create_task(on_global_update()))

    ui.timer(0.05, lambda: asyncio.create_task(refresh_charts()), once=True)
