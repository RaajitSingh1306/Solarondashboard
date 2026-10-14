"""
Solaron Analytics & Intelligence Cockpit.

Comprehensive analytics suite combining:
1. IEC 61724-1 Capacity-Weighted Performance Scorecard (PR, CUF, Availability)
2. NASA POWER GHI Physics Baseline & 6-Part Loss Attribution Engine
3. Damped-Trend Holt / ETS(A,Ad,N) Machine Learning Forecasting with P10/P50/P90 Prediction Intervals
4. Moving-Block Bootstrap Simulation Month-End Energy & Revenue Projections
5. Plant Health Diagnostics with Relative Performance Index (RPI) OLS Drift & CUSUM Change Detection
6. Cross-Platform Benchmarking across all 5 monitored portals (Growatt, iSolarCloud, SuryaLog, Fronius, InjectSolar)
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Dict, List, Optional
from nicegui import ui

try:
    from pipeline import db
    from core import analytics
    from core import platforms
    from core import fleet_intelligence
    from ui.export_dialog import show_export_dialog
except ImportError:
    import db  # type: ignore
    import analytics  # type: ignore
    import platforms  # type: ignore
    import fleet_intelligence  # type: ignore
    try:
        from export_dialog import show_export_dialog  # type: ignore
    except ImportError:
        from ui.export_dialog import show_export_dialog  # type: ignore

logger = logging.getLogger(__name__)


def build_analytics_tab(app_state: dict):
    client = ui.context.client
    today = datetime.date.today()
    cur_m = today.strftime("%Y-%m")
    cur_lbl = today.strftime("%b %Y")
    first_of_cur = today.replace(day=1)
    prev_date = first_of_cur - datetime.timedelta(days=1)
    prev_m = prev_date.strftime("%Y-%m")
    prev_lbl = prev_date.strftime("%b %Y")

    selected_period = {
        "month": app_state.get("month", cur_m),
        "platform": app_state.get("source", "All")
    }

    # =========================================================================
    # Top Control Bar: Month, Platform Filter, Quick Presets, Export & Recompute
    # =========================================================================
    with ui.row().classes("w-full items-center gap-3 mb-6 flex-wrap"):
        avail_months = db.get_available_months()
        default_month = selected_period["month"] if selected_period["month"] in avail_months else (avail_months[0] if avail_months else cur_m)
        month_select = ui.select(
            options=avail_months or [cur_m, prev_m],
            value=default_month,
            label="Analysis Month"
        ).classes("w-40").props("dense outlined dark options-dense")

        # Quick Period Presets
        with ui.button_group().props("dense outline"):
            ui.button(cur_lbl, on_click=lambda: asyncio.create_task(set_period(cur_m))).props("dense text-color=white")
            ui.button(prev_lbl, on_click=lambda: asyncio.create_task(set_period(prev_m))).props("dense text-color=white")

        platform_filter = ui.select(
            options=platforms.options(include_all=True),
            value=selected_period["platform"],
            label="Platform"
        ).classes("w-44").props("dense outlined dark options-dense")

        apply_btn = ui.button("Refresh Analytics", icon="refresh").props("dense color=primary unelevated")

        ui.space()

        with ui.button_group().props("dense outline"):
            ui.button(
                "Export Data",
                icon="file_download",
                on_click=lambda: show_export_dialog(
                    month=selected_period["month"],
                    platform=platform_filter.value,
                    default_dataset="monthly"
                ),
            ).props("dense unelevated color=indigo-7 text-color=white font-medium").tooltip("Export Daily, Weekly, Monthly or Yearly data with column selection as CSV or Excel")

            ui.button(
                "Quick CSV",
                icon="download",
                on_click=lambda: ui.download(
                    f"/api/export/fleet-monthly?fmt=csv&month={selected_period['month']}"
                    + (f"&source={platform_filter.value}" if platform_filter.value != "All" else "")
                ),
            ).props("dense flat text-color=cyan-3").tooltip("Download monthly CSV (11 default columns)")

    # =========================================================================
    # Section 0: Executive Performance Scorecard (IEC 61724-1 Standard Metrics)
    # =========================================================================
    with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 mb-6"):
        with ui.row().classes("w-full items-center justify-between pb-3 border-b border-gray-800"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("speed").classes("text-cyan-400 text-xl")
                with ui.column().classes("gap-0"):
                    ui.label("IEC 61724-1 Fleet Intelligence & Performance Scorecard").classes("text-sm font-bold text-white tracking-wide")
                    scorecard_sub_label = ui.label("Capacity-weighted telemetry metrics across all active solar installations").classes("text-[11px] text-gray-400")
            period_badge = ui.badge(f"Period: {selected_period['month']}", color="cyan-9").props("text-color=cyan-2 font-mono text-xs")

        kpi_row = ui.row().classes("w-full gap-3 mt-3 flex-wrap")
        with kpi_row:
            # 1. Capacity-Weighted PR
            with ui.card().classes("flex-1 min-w-[155px] p-3 bg-gray-800/90 border border-gray-700/80 rounded-xl"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Capacity PR").classes("text-xs text-gray-400 font-medium")
                    ui.icon("info", size="xs").classes("text-gray-500").tooltip("IEC weighted: ΣE / Σ(P0·Yr) — capacity-normalized against local NASA GHI benchmark")
                pr_val_label = ui.label("—%").classes("text-2xl font-black text-amber-400 mt-0.5")
                pr_sub_label = ui.label("vs 75% IEC benchmark").classes("text-[10px] text-gray-400")

            # 2. CUF & Availability
            with ui.card().classes("flex-1 min-w-[155px] p-3 bg-gray-800/90 border border-gray-700/80 rounded-xl"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("CUF / Availability").classes("text-xs text-gray-400 font-medium")
                    ui.icon("info", size="xs").classes("text-gray-500").tooltip("CUF: E / (P0 · 24h · days). Availability: producing plant-days / reported plant-days")
                cuf_val_label = ui.label("—%").classes("text-2xl font-black text-emerald-400 mt-0.5")
                avail_sub_label = ui.label("—% availability").classes("text-[10px] text-gray-400")

            # 3. Realized Energy Output
            with ui.card().classes("flex-1 min-w-[155px] p-3 bg-gray-800/90 border border-gray-700/80 rounded-xl"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Measured Harvest").classes("text-xs text-gray-400 font-medium")
                    ui.icon("info", size="xs").classes("text-gray-500").tooltip("Total measured energy from inverter smart meters")
                harvest_mwh_label = ui.label("— MWh").classes("text-2xl font-black text-blue-400 mt-0.5")
                harvest_sub_label = ui.label("— plants active").classes("text-[10px] text-gray-400")

            # 4. Financial & Carbon Offset
            with ui.card().classes("flex-1 min-w-[155px] p-3 bg-gray-800/90 border border-gray-700/80 rounded-xl"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Commercial Savings").classes("text-xs text-gray-400 font-medium")
                    ui.icon("info", size="xs").classes("text-gray-500").tooltip("Tariff savings (₹14.0/unit default) & avoided emissions (CEA v20 baseline: 0.82 kg/kWh)")
                savings_inr_label = ui.label("₹—").classes("text-2xl font-black text-emerald-400 mt-0.5")
                co2_sub_label = ui.label("— tons CO₂ offset").classes("text-[10px] text-gray-400")

            # 5. Specific Yield vs Reference
            with ui.card().classes("flex-1 min-w-[155px] p-3 bg-gray-800/90 border border-gray-700/80 rounded-xl"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Specific Yield Yf").classes("text-xs text-gray-400 font-medium")
                    ui.icon("info", size="xs").classes("text-gray-500").tooltip("Specific yield Yf (kWh/kWp) vs peak sun-hours reference yield Yr")
                sy_val_label = ui.label("—").classes("text-2xl font-black text-indigo-300 mt-0.5")
                sy_sub_label = ui.label("kWh/kWp").classes("text-[10px] text-gray-400")

            # 6. ML Outliers & Degradation
            with ui.card().classes("flex-1 min-w-[155px] p-3 bg-gray-800/90 border border-gray-700/80 rounded-xl"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Health Diagnostics").classes("text-xs text-gray-400 font-medium")
                    ui.icon("info", size="xs").classes("text-gray-500").tooltip("Seasonal ML anomaly outliers (z > 2.5) & statistically significant RPI degradation drift")
                anom_count_label = ui.label("—").classes("text-2xl font-black text-rose-400 mt-0.5")
                drift_sub_label = ui.label("— drifting plants").classes("text-[10px] text-gray-400")

    # =========================================================================
    # Section 1: NASA POWER Physics Baseline & 6-Part Loss Attribution Engine
    # =========================================================================
    with ui.card().classes("w-full p-5 bg-gray-900 border border-gray-800 mb-6"):
        with ui.row().classes("w-full items-center justify-between mb-3"):
            with ui.column().classes("gap-0"):
                ui.label("NASA GHI Baseline & 6-Part Loss Attribution Engine").classes("text-base font-bold text-amber-400 tracking-wide")
                ui.label("Thermodynamic shortfall decomposition against NASA POWER satellite irradiance standard").classes("text-xs text-gray-400")
            loss_month_badge = ui.badge(f"Month: {selected_period['month']}", color="amber-8").props("text-color=black font-bold")

        with ui.grid(columns=2).classes("w-full gap-6"):
            loss_chart = ui.echart({
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "grid": {"left": "3%", "right": "4%", "bottom": "12%", "top": "10%", "containLabel": True},
                "xAxis": {
                    "type": "category",
                    "data": ["Expected", "Actual", "Comm Loss", "Weather", "Soiling", "Shading", "Residual"],
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

            loss_cards_col = ui.column().classes("w-full gap-2.5 justify-center")
            loss_val_labels = {}
            with loss_cards_col:
                loss_items_meta = [
                    ("comm", "📡 Telemetry & Shutdown [Measured]", "Logger downtime & inverter communication gaps", "text-rose-400"),
                    ("weather", "☁️ Weather Deficit [Est. Range ±15%]", "Satellite GHI deficit vs regional clear-sky standard", "text-amber-400"),
                    ("soiling", "🧼 Soiling & Dust [Est. Range ±30%]", "Seasonal particulate accumulation & wash interval", "text-orange-400"),
                    ("shading", "🌿 Shading & Obstruction [Est. Range ±35%]", "Horizon geometry and roof obstacle shadows", "text-purple-400"),
                    ("unknown", "⚖️ Unattributed Residual [BOS / Variance]", "Wiring resistance, inverter clipping & mismatch", "text-gray-400"),
                ]
                for key, label_t, desc, color_cls in loss_items_meta:
                    with ui.row().classes("w-full items-center justify-between p-2 rounded-lg bg-gray-800/80 border border-gray-700/60"):
                        with ui.column().classes("gap-0"):
                            ui.label(label_t).classes(f"text-xs font-semibold {color_cls}")
                            ui.label(desc).classes("text-[10px] text-gray-400")
                        loss_val_labels[key] = ui.label("— MWh").classes(f"text-sm font-bold {color_cls}")

    # =========================================================================
    # Section 2: Machine Learning & Time-Series Forecasting (Damped Holt ETS)
    # =========================================================================
    with ui.card().classes("w-full p-5 bg-gray-900 border border-gray-800 mb-6"):
        with ui.row().classes("w-full items-center justify-between pb-3 border-b border-gray-800 flex-wrap gap-2"):
            with ui.row().classes("items-center gap-2.5"):
                ui.icon("insights").classes("text-cyan-400 text-2xl")
                with ui.column().classes("gap-0"):
                    ui.label("Fleet Forecasting Engine — Damped-Trend Holt / ETS(A,Ad,N)").classes("text-base font-bold text-white")
                    ui.label("Auto-tuned vectorised ETS with analytic h-step prediction intervals (P10 / P50 / P90)").classes("text-xs text-gray-400")
            forecast_status_pill = ui.badge("Model Status: Ready", color="cyan-9").classes("text-xs text-cyan-2 font-mono px-2.5 py-1")

        with ui.grid(columns=3).classes("w-full gap-4 my-3"):
            # Model metrics
            with ui.card().classes("p-3 bg-gray-800/70 border border-gray-700 rounded-lg"):
                ui.label("Model Calibration").classes("text-[11px] font-semibold text-gray-400 uppercase tracking-wide")
                model_params_label = ui.label("α: — | β: — | φ: —").classes("text-xs font-mono font-bold text-cyan-300 mt-1")
                model_sample_label = ui.label("Trained on — clean days").classes("text-[10px] text-gray-500")

            with ui.card().classes("p-3 bg-gray-800/70 border border-gray-700 rounded-lg"):
                ui.label("Rolling-Origin Backtest").classes("text-[11px] font-semibold text-gray-400 uppercase tracking-wide")
                backtest_metrics_label = ui.label("MAE: — | MAPE: —%").classes("text-xs font-mono font-bold text-emerald-400 mt-1")
                skill_score_label = ui.label("Skill vs 7d Mean: —").classes("text-[10px] text-gray-500")

            with ui.card().classes("p-3 bg-gray-800/70 border border-gray-700 rounded-lg"):
                ui.label("Next 7-Day Forecast").classes("text-[11px] font-semibold text-gray-400 uppercase tracking-wide")
                next_7d_kwh_label = ui.label("— MWh").classes("text-xs font-mono font-bold text-amber-400 mt-1")
                typical_cap_label = ui.label("For active fleet").classes("text-[10px] text-gray-500")

        # 14-Day Forecast Chart with P10-P90 Cone
        forecast_chart = ui.echart({
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Historical Specific Yield", "Fitted / P50 Forecast", "P10 Floor", "P90 Ceiling"], "textStyle": {"color": "#9CA3AF"}},
            "grid": {"left": "3%", "right": "4%", "bottom": "8%", "top": "14%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": [],
                "axisLine": {"lineStyle": {"color": "#6B7280"}},
                "axisLabel": {"color": "#9CA3AF", "rotate": 25, "fontSize": 10}
            },
            "yAxis": {
                "type": "value",
                "name": "Specific Yield (kWh/kWp)",
                "axisLine": {"lineStyle": {"color": "#6B7280"}},
                "axisLabel": {"color": "#9CA3AF"},
                "splitLine": {"lineStyle": {"color": "#1F2937"}}
            },
            "series": [
                {
                    "name": "Historical Specific Yield",
                    "type": "line",
                    "data": [],
                    "itemStyle": {"color": "#94A3B8"},
                    "lineStyle": {"color": "#94A3B8", "width": 1.5},
                    "symbol": "circle",
                    "symbolSize": 4,
                },
                {
                    "name": "Fitted / P50 Forecast",
                    "type": "line",
                    "data": [],
                    "itemStyle": {"color": "#22D3EE"},
                    "lineStyle": {"color": "#22D3EE", "width": 2.5},
                    "smooth": True,
                },
                {
                    "name": "P10 Floor",
                    "type": "line",
                    "data": [],
                    "lineStyle": {"color": "#F59E0B", "type": "dashed", "width": 1.2},
                    "symbol": "none",
                },
                {
                    "name": "P90 Ceiling",
                    "type": "line",
                    "data": [],
                    "lineStyle": {"color": "#3B82F6", "type": "dashed", "width": 1.2},
                    "symbol": "none",
                },
            ]
        }).classes("w-full h-80")

    # =========================================================================
    # Section 3: Month-End Generation & Revenue Projections (Bootstrap Simulation)
    # =========================================================================
    with ui.card().classes("w-full p-5 bg-gray-900 border border-gray-800 mb-6"):
        with ui.row().classes("w-full items-center justify-between pb-3 border-b border-gray-800 flex-wrap gap-2"):
            with ui.row().classes("items-center gap-2.5"):
                ui.icon("analytics").classes("text-emerald-400 text-2xl")
                with ui.column().classes("gap-0"):
                    ui.label("Month-End Energy Projection — Moving-Block Bootstrap").classes("text-base font-bold text-white")
                    ui.label("4,000 empirical block resamples (block size = 3) simulating weather variance through month end").classes("text-xs text-gray-400")
            proj_status_badge = ui.badge("Projection: Running", color="emerald-9").classes("text-xs text-emerald-2 font-mono px-2.5 py-1")

        with ui.grid(columns=4).classes("w-full gap-4 my-3"):
            with ui.card().classes("p-3 bg-gray-800/70 border border-gray-700 rounded-lg"):
                ui.label("P10 Floor (90% Conf.)").classes("text-[11px] font-semibold text-amber-400 uppercase tracking-wide")
                proj_p10_label = ui.label("— MWh").classes("text-lg font-mono font-bold text-amber-300 mt-0.5")
                ui.label("Conservative output floor").classes("text-[10px] text-gray-500")

            with ui.card().classes("p-3 bg-gray-800/70 border border-gray-700 rounded-lg"):
                ui.label("P50 Expected Total").classes("text-[11px] font-semibold text-emerald-400 uppercase tracking-wide")
                proj_p50_label = ui.label("— MWh").classes("text-lg font-mono font-bold text-emerald-300 mt-0.5")
                proj_p50_inr_label = ui.label("Est. ₹—").classes("text-[10px] text-gray-400")

            with ui.card().classes("p-3 bg-gray-800/70 border border-gray-700 rounded-lg"):
                ui.label("P90 Ceiling (10% High)").classes("text-[11px] font-semibold text-blue-400 uppercase tracking-wide")
                proj_p90_label = ui.label("— MWh").classes("text-lg font-mono font-bold text-blue-300 mt-0.5")
                ui.label("Optimistic solar output").classes("text-[10px] text-gray-500")

            with ui.card().classes("p-3 bg-gray-800/70 border border-gray-700 rounded-lg"):
                ui.label("Target Benchmark Match").classes("text-[11px] font-semibold text-indigo-400 uppercase tracking-wide")
                proj_prob_label = ui.label("—%").classes("text-lg font-mono font-bold text-indigo-300 mt-0.5")
                proj_days_label = ui.label("— elapsed / — left").classes("text-[10px] text-gray-500")

        # Cumulative projection chart
        proj_chart = ui.echart({
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Actual MWh to Date", "Projected P50 Path", "P10 Lower Envelope", "P90 Upper Envelope"], "textStyle": {"color": "#9CA3AF"}},
            "grid": {"left": "3%", "right": "4%", "bottom": "8%", "top": "14%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": [],
                "axisLine": {"lineStyle": {"color": "#6B7280"}},
                "axisLabel": {"color": "#9CA3AF", "rotate": 25, "fontSize": 10}
            },
            "yAxis": {
                "type": "value",
                "name": "Cumulative Energy (MWh)",
                "axisLine": {"lineStyle": {"color": "#6B7280"}},
                "axisLabel": {"color": "#9CA3AF"},
                "splitLine": {"lineStyle": {"color": "#1F2937"}}
            },
            "series": [
                {
                    "name": "Actual MWh to Date",
                    "type": "line",
                    "data": [],
                    "itemStyle": {"color": "#10B981"},
                    "lineStyle": {"color": "#10B981", "width": 2.5},
                    "symbol": "circle",
                },
                {
                    "name": "Projected P50 Path",
                    "type": "line",
                    "data": [],
                    "itemStyle": {"color": "#06B6D4"},
                    "lineStyle": {"color": "#06B6D4", "width": 2, "type": "dashed"},
                    "symbol": "none",
                },
                {
                    "name": "P10 Lower Envelope",
                    "type": "line",
                    "data": [],
                    "lineStyle": {"color": "#F59E0B", "width": 1, "type": "dotted"},
                    "symbol": "none",
                },
                {
                    "name": "P90 Upper Envelope",
                    "type": "line",
                    "data": [],
                    "lineStyle": {"color": "#60A5FA", "width": 1, "type": "dotted"},
                    "symbol": "none",
                },
            ]
        }).classes("w-full h-72")

    # =========================================================================
    # Section 4: Cross-Platform Benchmarking Grid & Yield Distribution
    # =========================================================================
    with ui.grid(columns=2).classes("w-full gap-6 mb-6"):
        # 1. Platform PR (%) & Yield Comparison
        with ui.card().classes("p-4 w-full bg-gray-900 border border-gray-800"):
            platform_chart_label = ui.label("Capacity-Weighted PR (%) by Platform").classes("text-sm font-semibold text-gray-300 mb-2")
            platform_chart = ui.echart({
                "tooltip": {"trigger": "axis"},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {
                    "type": "category",
                    "data": [platforms.label(k) for k in platforms.platform_keys()],
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"}
                },
                "yAxis": {
                    "type": "value",
                    "name": "PR (%)",
                    "axisLine": {"lineStyle": {"color": "#6B7280"}},
                    "axisLabel": {"color": "#9CA3AF"},
                    "splitLine": {"lineStyle": {"color": "#1F2937"}}
                },
                "series": [{
                    "name": "Capacity PR (%)",
                    "type": "bar",
                    "data": [0] * len(platforms.platform_keys()),
                    "itemStyle": {"borderRadius": [4, 4, 0, 0]}
                }]
            }).classes("w-full h-64")

        # 2. Daily Generation Trend
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

        # 3. Performance Tier Distribution
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

        # 4. Top 10 Producers
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

    # =========================================================================
    # Reactive Async Refresh Logic
    # =========================================================================
    _refreshing = False

    async def refresh_charts():
        nonlocal _refreshing
        if getattr(client, '_deleted', False) or _refreshing:
            return
        _refreshing = True

        m_val = selected_period["month"]
        src = platform_filter.value
        src_label = platforms.label(src)
        src_clean = src.lower() if (src and src != "All") else None

        if getattr(client, '_deleted', False):
            _refreshing = False
            return

        loss_month_badge.text = f"Month: {m_val}  ·  Platform: {src_label}"
        period_badge.text = f"Period: {m_val} ({src_label})"

        try:
            # 1. Fetch Fleet Intelligence KPIs & Machine Learning Calculations
            kpis, forecast_res, proj_res, health_res, wf = await asyncio.gather(
                asyncio.to_thread(fleet_intelligence.fleet_kpis, month=m_val, source=src_clean),
                asyncio.to_thread(fleet_intelligence.forecast_fleet, horizon=14, source=src_clean),
                asyncio.to_thread(fleet_intelligence.project_month_end, month=m_val, source=src_clean),
                asyncio.to_thread(fleet_intelligence.plant_health_matrix, source=src_clean),
                asyncio.to_thread(analytics.get_loss_waterfall, m_val, source=src)
            )

            if getattr(client, '_deleted', False):
                return

            # 2. Update Top Executive KPI Scorecard
            pr_val = float(kpis.get("pr_weighted_pct", 0.0))
            pr_val_label.text = f"{pr_val:.1f}%"
            pr_val_label.classes(
                replace="text-amber-400" if pr_val >= 65 else ("text-emerald-400" if pr_val >= 50 else "text-rose-400")
            )

            cuf_val = float(kpis.get("cuf_pct", 0.0))
            avail_val = float(kpis.get("availability_pct", 0.0))
            cuf_val_label.text = f"{cuf_val:.1f}%"
            avail_sub_label.text = f"{avail_val:.1f}% availability"

            mwh_val = float(kpis.get("kwh", 0.0)) / 1000.0
            harvest_mwh_label.text = f"{mwh_val:,.1f} MWh"
            harvest_sub_label.text = f"{kpis.get('plants_generating', 0)} of {kpis.get('plants_active', 0)} producing"

            rev_inr = float(kpis.get("revenue_inr", 0.0))
            co2_t = float(kpis.get("co2_t", 0.0))
            savings_inr_label.text = f"₹{rev_inr:,.0f}"
            co2_sub_label.text = f"{co2_t:,.1f} tons CO₂ offset"

            sy_val = float(kpis.get("specific_yield", 0.0))
            sy_val_label.text = f"{sy_val:.1f}"
            sy_sub_label.text = f"kWh/kWp (median {kpis.get('median_ypd', 0.0):.1f}/d)"

            anom_cnt = int(kpis.get("anomalies", 0))
            drifting_cnt = int(health_res.get("n_drifting", 0))
            anom_count_label.text = f"{anom_cnt}"
            drift_sub_label.text = f"{drifting_cnt} plants drifting"

            # 3. Update Waterfall EChart & Loss Breakdown Cards
            exp_mwh = round(wf["expected_kwh"] / 1000.0, 2)
            act_mwh = round(wf["actual_kwh"] / 1000.0, 2)
            short_mwh = round(wf["shortfall_kwh"] / 1000.0, 2)
            comm_mwh = round(wf["comm_loss_kwh"] / 1000.0, 2)
            weather_mwh = round(wf["weather_loss_kwh"] / 1000.0, 2)
            soiling_mwh = round(wf["soiling_loss_kwh"] / 1000.0, 2)
            shading_mwh = round(wf["shading_loss_kwh"] / 1000.0, 2)
            unknown_mwh = round(wf["unknown_loss_kwh"] / 1000.0, 2)

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

            loss_val_labels["comm"].text = f"{comm_mwh:.2f} MWh"
            loss_val_labels["weather"].text = f"{weather_mwh:.2f} MWh"
            loss_val_labels["soiling"].text = f"{soiling_mwh:.2f} MWh"
            loss_val_labels["shading"].text = f"{shading_mwh:.2f} MWh"
            loss_val_labels["unknown"].text = f"{unknown_mwh:.2f} MWh"

            # 4. Update Holt ETS Forecasting Chart & Metrics
            if forecast_res.get("status") == "ok":
                forecast_status_pill.text = "Model: Damped Holt ETS (Calibrated)"
                forecast_status_pill.props("color=emerald-9 text-color=emerald-2")

                f_params = forecast_res.get("params", {})
                alpha_v = float(f_params.get("alpha", 0.0) or 0.0)
                beta_v = float(f_params.get("beta_star", f_params.get("beta", 0.0)) or 0.0)
                phi_v = float(f_params.get("phi", 1.0) or 1.0)
                model_params_label.text = f"α: {alpha_v:.2f} | β: {beta_v:.3f} | φ: {phi_v:.2f}"
                model_sample_label.text = f"Trained on {forecast_res.get('train_days', 0)} clean days"

                bt = forecast_res.get("backtest", {})
                mae_v = float(bt.get("mae_model", 0.0) or 0.0)
                mape_v = float(bt.get("mape_model_pct", 0.0) or 0.0)
                skill_v = float(bt.get("skill_vs_mean7", 0.0) or 0.0)
                backtest_metrics_label.text = f"MAE: {mae_v:.2f} | MAPE: {mape_v:.1f}%"
                skill_score_label.text = f"Skill vs 7d Mean: {skill_v:+.1%}"

                next_7d_mwh = round(float(forecast_res.get("next_7d_kwh", 0.0)) / 1000.0, 1)
                next_7d_kwh_label.text = f"{next_7d_mwh:,.1f} MWh"
                typical_cap_label.text = f"~{forecast_res.get('typical_capacity_kwp', 0.0):,.0f} kWp capacity"

                h_dates = list(forecast_res.get("history_dates", []))
                f_dates = list(forecast_res.get("forecast_dates", []))
                all_fc_dates = h_dates + f_dates

                h_sy = [round(float(v), 2) for v in forecast_res.get("history_sy", [])]
                fit_sy = [round(float(v), 2) for v in forecast_res.get("fitted_sy", [])]
                fc_sy = [round(float(v), 2) for v in forecast_res.get("forecast_sy", [])]
                fc_lo = [round(float(v), 2) for v in forecast_res.get("forecast_lo_sy", [])]
                fc_hi = [round(float(v), 2) for v in forecast_res.get("forecast_hi_sy", [])]

                forecast_chart.options["xAxis"]["data"] = all_fc_dates
                forecast_chart.options["series"][0]["data"] = h_sy + [None] * len(f_dates)
                forecast_chart.options["series"][1]["data"] = fit_sy + fc_sy
                forecast_chart.options["series"][2]["data"] = [None] * len(h_dates) + fc_lo
                forecast_chart.options["series"][3]["data"] = [None] * len(h_dates) + fc_hi
                forecast_chart.update()

            # 5. Update Month-End Bootstrap Projection Chart & Metrics
            if proj_res.get("status") == "ok":
                proj_status_badge.text = f"Resampled: {proj_res.get('sample_days', 0)} Clean Days"
                p10_mwh = round(float(proj_res.get("p10_kwh", 0.0)) / 1000.0, 1)
                p50_mwh = round(float(proj_res.get("p50_kwh", 0.0)) / 1000.0, 1)
                p90_mwh = round(float(proj_res.get("p90_kwh", 0.0)) / 1000.0, 1)
                p50_inr = round(p50_mwh * 1000.0 * 14.0)

                proj_p10_label.text = f"{p10_mwh:,.1f} MWh"
                proj_p50_label.text = f"{p50_mwh:,.1f} MWh"
                proj_p50_inr_label.text = f"Est. ₹{p50_inr:,.0f}"
                proj_p90_label.text = f"{p90_mwh:,.1f} MWh"
                prob_exp = proj_res.get("prob_meet_expected")
                proj_prob_label.text = f"{prob_exp:.0%}" if prob_exp is not None else "—%"
                proj_days_label.text = f"{proj_res.get('elapsed_days', 0)} elapsed / {proj_res.get('remaining_days', 0)} left"

                cum_dates = list(proj_res.get("cum_dates", []))
                p_dates = list(proj_res.get("proj_dates", []))
                all_p_dates = cum_dates + p_dates

                cum_act = [round(float(v) / 1000.0, 2) for v in proj_res.get("cum_actual_kwh", [])]
                p50_path = [round(float(v) / 1000.0, 2) for v in proj_res.get("proj_p50", [])]
                p10_path = [round(float(v) / 1000.0, 2) for v in proj_res.get("proj_p10", [])]
                p90_path = [round(float(v) / 1000.0, 2) for v in proj_res.get("proj_p90", [])]

                proj_chart.options["xAxis"]["data"] = all_p_dates
                proj_chart.options["series"][0]["data"] = cum_act + [None] * len(p_dates)
                proj_chart.options["series"][1]["data"] = [None] * (len(cum_dates) - 1) + [cum_act[-1]] + p50_path if cum_act else p50_path
                proj_chart.options["series"][2]["data"] = [None] * (len(cum_dates) - 1) + [cum_act[-1]] + p10_path if cum_act else p10_path
                proj_chart.options["series"][3]["data"] = [None] * (len(cum_dates) - 1) + [cum_act[-1]] + p90_path if cum_act else p90_path
                proj_chart.update()

            # 6. Cross-Platform Benchmarking Chart
            bench_platforms = kpis.get("platforms", [])
            p_keys = platforms.platform_keys()
            p_labels = [platforms.label(k) for k in p_keys]
            p_map = {p["key"]: p for p in bench_platforms}

            platform_chart.options["xAxis"]["data"] = p_labels
            platform_chart.options["series"][0]["data"] = [
                {
                    "value": round(float(p_map.get(k, {}).get("pr_weighted_pct", 0.0)), 1),
                    "itemStyle": {"color": platforms.color(k)}
                }
                for k in p_keys
            ]
            platform_chart.update()

            # 7. Daily Generation Trend & Tier Breakdown SQL queries
            sql_daily = """
            SELECT d.date, sum(d.kwh) as total_kwh
            FROM daily_generation d
            JOIN plants p ON d.plant_id = p.plant_id
            WHERE strftime('%Y-%m', d.date) = ?
              AND (p.operational_status IS NULL OR p.operational_status != 'decommissioned')
            """
            p_params = [m_val]
            if src_clean:
                sql_daily += " AND lower(p.source) = ?"
                p_params.append(src_clean)
            sql_daily += " GROUP BY d.date ORDER BY d.date ASC"

            sql_tier = """
            SELECT coalesce(m.tier, CASE WHEN p.operational_status = 'decommissioned' THEN 'Decommissioned' ELSE 'Offline' END) as tier, count(*) as count 
            FROM plants p
            LEFT JOIN monthly_generation m ON p.plant_id = m.plant_id AND m.month = ?
            WHERE 1=1
            """
            t_params = [m_val]
            if src_clean:
                sql_tier += " AND lower(p.source) = ?"
                t_params.append(src_clean)
            sql_tier += " GROUP BY coalesce(m.tier, CASE WHEN p.operational_status = 'decommissioned' THEN 'Decommissioned' ELSE 'Offline' END)"

            sql_top = """
            SELECT p.plant_name, m.kwh as total_kwh
            FROM monthly_generation m
            JOIN plants p ON m.plant_id = p.plant_id
            WHERE m.month = ? AND (p.operational_status IS NULL OR p.operational_status != 'decommissioned')
            """
            top_params = [m_val]
            if src_clean:
                sql_top += " AND lower(p.source) = ?"
                top_params.append(src_clean)
            sql_top += " ORDER BY total_kwh DESC LIMIT 10"

            df_daily, df_tier, df_top = await asyncio.gather(
                asyncio.to_thread(db.query_df, sql_daily, p_params, "analytics"),
                asyncio.to_thread(db.query_df, sql_tier, t_params, "analytics"),
                asyncio.to_thread(db.query_df, sql_top, top_params, "analytics")
            )

            if getattr(client, '_deleted', False):
                return

            # Daily trend update
            if not df_daily.empty:
                daily_chart.options["xAxis"]["data"] = df_daily["date"].tolist()
                daily_chart.options["series"][0]["data"] = [round(v, 1) for v in df_daily["total_kwh"].fillna(0).tolist()]
            else:
                daily_chart.options["xAxis"]["data"] = []
                daily_chart.options["series"][0]["data"] = []
            daily_chart.update()

            # Tier distribution update
            t_counts = {"Best": 0, "Good": 0, "Could Be Better": 0, "Needs Attention": 0, "Critical": 0, "Offline": 0, "Fault": 0, "Decommissioned": 0}
            for _, r in df_tier.iterrows():
                t_k = str(r["tier"])
                if t_k in t_counts:
                    t_counts[t_k] = int(r["count"])
            tier_colors = ["#10B981", "#3B82F6", "#F59E0B", "#F97316", "#EF4444", "#6B7280", "#DC2626", "#8B5CF6"]
            tier_chart.options["yAxis"]["data"] = list(t_counts.keys())
            tier_chart.options["series"][0]["data"] = [
                {"value": v, "itemStyle": {"color": tier_colors[i]}}
                for i, v in enumerate(t_counts.values())
            ]
            tier_chart.update()

            # Top 10 plants
            top_chart_label.text = f"Top 10 Producing Plants ({src_label}) (Monthly kWh)"
            if not df_top.empty:
                names = [name[:20] for name in df_top["plant_name"].tolist()][::-1]
                values = [round(v, 1) for v in df_top["total_kwh"].fillna(0).tolist()][::-1]
                top_chart.options["yAxis"]["data"] = names
                top_chart.options["series"][0]["data"] = values
            else:
                top_chart.options["yAxis"]["data"] = []
                top_chart.options["series"][0]["data"] = []
            top_chart.update()

        except Exception as e:
            logger.error(f"Error refreshing analytics cockpit: {e}", exc_info=True)
            if not getattr(client, '_deleted', False):
                try:
                    with client:
                        ui.notify(f"Analytics refresh error: {e}", type="negative")
                except Exception:
                    pass
        finally:
            _refreshing = False

    async def set_period(m_val: str):
        selected_period["month"] = m_val
        month_select.value = m_val
        app_state["month"] = m_val
        await refresh_charts()

    month_select.on("update:model-value", lambda e: asyncio.create_task(set_period(month_select.value)))
    platform_filter.on("update:model-value", lambda: asyncio.create_task(refresh_charts()))
    apply_btn.on_click(lambda: asyncio.create_task(refresh_charts()))

    # External month change listener from header bar
    async def on_global_update():
        if getattr(client, '_deleted', False):
            return
        if app_state.get("month") != selected_period["month"]:
            selected_period["month"] = app_state.get("month", cur_m)
            month_select.value = selected_period["month"]
        if app_state.get("source") != selected_period["platform"]:
            selected_period["platform"] = app_state.get("source", "All")
            platform_filter.value = selected_period["platform"]
        await refresh_charts()

    if "refresh_listeners" in app_state:
        app_state["refresh_listeners"].append(lambda: asyncio.create_task(on_global_update()))

    ui.timer(0.05, lambda: asyncio.create_task(refresh_charts()), once=True)
