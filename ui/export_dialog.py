"""Export dialog component with column selection and period filtering."""
import datetime
import json
from pathlib import Path
from typing import Dict, Optional, Set
from nicegui import ui

try:
    from pipeline import db
    from core import platforms
    from routes.export import MONTHLY_COLUMNS, DAILY_COLUMNS, WEEKLY_COLUMNS, YEARLY_COLUMNS
except ImportError:
    import db
    import platforms  # type: ignore
    from routes.export import MONTHLY_COLUMNS, DAILY_COLUMNS, WEEKLY_COLUMNS, YEARLY_COLUMNS

PREFS_FILE = Path(__file__).resolve().parent.parent / "data" / "export_preferences.json"

MONTHLY_PRESETS = {
    "⚡ Generation Report": [
        "plant_id", "plant_name", "source", "capacity_kwp", "month",
        "kwh", "specific_yield", "yield_per_day", "revenue_inr"
    ],
    "📊 Performance Audit": [
        "plant_id", "plant_name", "source", "capacity_kwp", "month",
        "kwh", "pr_pct", "tier", "percentile", "anomaly_score", "anomaly_flag"
    ],
    "🔬 Loss Analysis": [
        "plant_id", "plant_name", "month", "kwh",
        "expected_kwh", "ghi_kwh_m2_day", "shortfall_kwh", "comm_loss_kwh",
        "shutdown_loss_kwh", "weather_loss_kwh", "soiling_loss_kwh",
        "shading_loss_kwh", "unknown_loss_kwh", "realization_rate_pct"
    ],
    "📋 Full Profile": [
        "plant_id", "plant_name", "source", "capacity_kwp", "operational_status",
        "city", "install_date", "inverter_model", "panel_model", "month", "kwh"
    ],
}

DAILY_PRESETS = {
    "⚡ Generation Report": [
        "plant_id", "plant_name", "source", "capacity_kwp", "date",
        "kwh", "specific_yield", "yield_per_day", "revenue_inr"
    ],
    "📡 Live & Telemetry": [
        "plant_id", "plant_name", "source", "capacity_kwp", "date",
        "kwh", "live_power_kw", "status", "quality_flags", "last_log_time"
    ],
    "📋 Full Profile": [
        "plant_id", "plant_name", "source", "capacity_kwp", "city",
        "date", "kwh", "live_power_kw", "status", "revenue_inr"
    ],
}

WEEKLY_PRESETS = {
    "⚡ Weekly Generation": [
        "period", "period_start", "period_end", "plant_id", "plant_name", "source",
        "capacity_kwp", "kwh", "specific_yield", "yield_per_day", "revenue_inr"
    ],
    "📊 IEC 61724-1 Audit": [
        "period", "plant_id", "plant_name", "source", "capacity_kwp", "kwh",
        "reference_yield_h", "pr_pct", "cuf_pct", "availability_pct", "producing_days"
    ],
    "📋 Comprehensive": [
        "period", "plant_id", "plant_name", "source", "city", "capacity_kwp",
        "kwh", "specific_yield", "pr_pct", "cuf_pct", "expected_kwh", "realization_pct",
        "days_reported", "producing_days", "availability_pct", "revenue_inr", "co2_kg"
    ],
}

YEARLY_PRESETS = {
    "🏆 Annual Performance": [
        "period", "plant_id", "plant_name", "source", "capacity_kwp", "kwh",
        "specific_yield", "pr_pct", "cuf_pct", "availability_pct", "revenue_inr", "co2_kg"
    ],
    "📋 Complete Annual Ledger": [
        "period", "plant_id", "plant_name", "source", "city", "capacity_kwp",
        "kwh", "specific_yield", "yield_per_day", "cuf_pct", "pr_pct",
        "expected_kwh", "realization_pct", "days_reported", "producing_days",
        "availability_pct", "revenue_inr", "co2_kg"
    ],
}

def _load_persisted_cols() -> Dict[str, Set[str]]:
    defaults = {
        "monthly": {k for k, meta in MONTHLY_COLUMNS.items() if meta["default"]},
        "daily": {k for k, meta in DAILY_COLUMNS.items() if meta["default"]},
        "weekly": {k for k, meta in WEEKLY_COLUMNS.items() if meta.get("default")},
        "yearly": {k for k, meta in YEARLY_COLUMNS.items() if meta.get("default")},
    }
    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for ds, reg in [("monthly", MONTHLY_COLUMNS), ("daily", DAILY_COLUMNS), ("weekly", WEEKLY_COLUMNS), ("yearly", YEARLY_COLUMNS)]:
                        if ds in data and isinstance(data[ds], list):
                            val = {k for k in data[ds] if k in reg}
                            if val:
                                defaults[ds] = val
        except Exception:
            pass
    return defaults

def _save_persisted_cols(prefs: Dict[str, Set[str]]):
    try:
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump({k: sorted(list(v)) for k, v in prefs.items()}, f, indent=2)
    except Exception:
        pass

def _sync_browser_storage(dataset: str, selected_keys: Set[str]):
    try:
        keys_list = sorted(list(selected_keys))
        ui.run_javascript(f"try {{ localStorage.setItem('solaron_export_cols_{dataset}', JSON.stringify({json.dumps(keys_list)})); }} catch(e){{}}")
    except Exception:
        pass

# Persistent column selection across modal opens within session and across restarts
_user_selected_cols = _load_persisted_cols()

def show_export_dialog(
    month: Optional[str] = None,
    platform: str = "All",
    include_decom: bool = True,
    default_dataset: str = "monthly",
):
    """Open interactive modal dialog for customized CSV / XLSX data export."""
    avail_months = db.get_available_months()
    cur_m = datetime.date.today().strftime("%Y-%m")
    if not month:
        month = cur_m if cur_m in avail_months else (avail_months[0] if avail_months else cur_m)

    state = {
        "dataset": default_dataset,  # 'monthly' or 'daily'
        "period_mode": "single",    # 'single', 'range', 'all'
        "month": month,
        "start_month": avail_months[-1] if avail_months else cur_m,
        "end_month": month,
        "platform": platform or "All",
        "include_decom": include_decom,
        "selected_keys": set(_user_selected_cols.get(default_dataset, set())),
    }

    with ui.dialog().classes("items-center justify-center") as dialog, \
         ui.card().classes("w-[780px] max-w-[96vw] max-h-[90vh] overflow-y-auto p-6 bg-gray-900 border border-gray-700 text-white rounded-2xl shadow-2xl"):

        # Header
        with ui.row().classes("w-full items-center justify-between mb-4 border-b border-gray-800 pb-3"):
            with ui.row().classes("items-center gap-3"):
                with ui.element("div").classes("p-2 rounded-xl bg-cyan-950/80 border border-cyan-800/60 text-cyan-400"):
                    ui.icon("file_download", size="md")
                with ui.column().classes("gap-0.5"):
                    ui.label("Export Fleet Telemetry & Performance").classes("text-lg font-bold text-white tracking-wide")
                    ui.label("Download customized CSV or Excel reports with column selection and date filtering").classes("text-xs text-gray-400")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense size=sm color=white")

        # 1. Dataset & Period Configuration Section
        with ui.card().classes("w-full p-4 bg-gray-800/80 border border-gray-700/80 rounded-xl mb-4 gap-3"):
            ui.label("1. Scope & Timeframe").classes("text-xs font-semibold text-cyan-400 uppercase tracking-wider")

            with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                # Granularity Selector
                dataset_radio = ui.radio(
                    {
                        "monthly": "Monthly Yield (Aggregated)",
                        "daily": "Daily Telemetry (Granular)",
                        "weekly": "Weekly IEC Performance",
                        "yearly": "Yearly Performance & CUF",
                    },
                    value=state["dataset"],
                ).props("dense inline color=cyan dark")

                platform_select = ui.select(
                    options=platforms.options(include_all=True),
                    value=state["platform"],
                    label="Platform",
                ).classes("w-40").props("dense outlined dark options-dense")

                decom_checkbox = ui.checkbox("Include Decommissioned", value=state["include_decom"]).props("dense dark").classes("text-xs text-gray-300")

            with ui.row().classes("w-full items-center gap-3 mt-1 flex-wrap"):
                period_mode_select = ui.select(
                    options={"single": "Single Month", "range": "Month Range", "all": "All Time Available"},
                    value=state["period_mode"],
                    label="Time Range",
                ).classes("w-44").props("dense outlined dark options-dense")

                single_month_container = ui.row().classes("items-center gap-2")
                range_month_container = ui.row().classes("items-center gap-2")
                range_month_container.visible = False

                with single_month_container:
                    single_month_select = ui.select(
                        options=avail_months,
                        value=state["month"],
                        label="Reporting Month",
                    ).classes("w-40").props("dense outlined dark options-dense")

                with range_month_container:
                    start_month_select = ui.select(
                        options=avail_months,
                        value=state["start_month"],
                        label="From Month",
                    ).classes("w-36").props("dense outlined dark options-dense")
                    ui.label("→").classes("text-gray-400")
                    end_month_select = ui.select(
                        options=avail_months,
                        value=state["end_month"],
                        label="To Month",
                    ).classes("w-36").props("dense outlined dark options-dense")

        # Period mode switch handler
        def update_period_visibility():
            mode = period_mode_select.value
            single_month_container.visible = (mode == "single")
            range_month_container.visible = (mode == "range")

        period_mode_select.on_value_change(update_period_visibility)

        # 2. Column Selection Section
        columns_container = ui.column().classes("w-full gap-3 mb-4")

        # Top bar of column section: counter + select all / reset buttons
        count_label = ui.label("").classes("text-xs font-semibold text-amber-400")

        def get_active_registry():
            ds = dataset_radio.value
            if ds == "daily":
                return DAILY_COLUMNS
            elif ds == "weekly":
                return WEEKLY_COLUMNS
            elif ds == "yearly":
                return YEARLY_COLUMNS
            return MONTHLY_COLUMNS

        def refresh_column_ui():
            columns_container.clear()
            registry = get_active_registry()
            cur_keys = state["selected_keys"]

            # Filter out keys not in active registry
            valid_keys = {k for k in cur_keys if k in registry}
            if not valid_keys:
                valid_keys = {k for k, meta in registry.items() if meta["default"]}
            state["selected_keys"] = valid_keys
            _user_selected_cols[dataset_radio.value] = set(valid_keys)
            _save_persisted_cols(_user_selected_cols)

            total_cols = len(registry)
            count_label.text = f"{len(valid_keys)} of {total_cols} columns selected"

            # Group columns by meta["group"]
            groups = {}
            for k, meta in registry.items():
                groups.setdefault(meta["group"], []).append((k, meta))

            with columns_container:
                with ui.card().classes("w-full p-4 bg-gray-800/80 border border-gray-700/80 rounded-xl gap-3"):
                    with ui.row().classes("w-full items-center justify-between border-b border-gray-700/60 pb-2 flex-wrap gap-2"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label("2. Select Export Columns").classes("text-xs font-semibold text-cyan-400 uppercase tracking-wider")
                            count_badge = ui.badge(f"{len(valid_keys)} / {total_cols}", color="cyan-9").props("text-color=cyan-2")

                        with ui.row().classes("items-center gap-2"):
                            def select_all():
                                state["selected_keys"] = set(registry.keys())
                                _user_selected_cols[dataset_radio.value] = set(state["selected_keys"])
                                _save_persisted_cols(_user_selected_cols)
                                _sync_browser_storage(dataset_radio.value, state["selected_keys"])
                                refresh_column_ui()

                            def deselect_all():
                                state["selected_keys"] = set()
                                _user_selected_cols[dataset_radio.value] = set()
                                _save_persisted_cols(_user_selected_cols)
                                _sync_browser_storage(dataset_radio.value, set())
                                refresh_column_ui()

                            def reset_defaults():
                                state["selected_keys"] = {k for k, meta in registry.items() if meta["default"]}
                                _user_selected_cols[dataset_radio.value] = set(state["selected_keys"])
                                _save_persisted_cols(_user_selected_cols)
                                _sync_browser_storage(dataset_radio.value, state["selected_keys"])
                                refresh_column_ui()

                            ui.button("Select All", on_click=select_all).props("dense flat size=xs color=cyan")
                            ui.button("Deselect All", on_click=deselect_all).props("dense flat size=xs color=gray")
                            ui.button("Reset Defaults", on_click=reset_defaults).props("dense flat size=xs color=amber")

                    # Preset Quick-Select Toolbar
                    with ui.row().classes("w-full items-center gap-2 pt-1 pb-2 border-b border-gray-700/50 flex-wrap"):
                        ui.label("Presets:").classes("text-xs font-semibold text-gray-400")
                        ds = dataset_radio.value
                        if ds == "daily":
                            active_presets = DAILY_PRESETS
                        elif ds == "weekly":
                            active_presets = WEEKLY_PRESETS
                        elif ds == "yearly":
                            active_presets = YEARLY_PRESETS
                        else:
                            active_presets = MONTHLY_PRESETS
                        for preset_name, preset_cols in active_presets.items():
                            def make_preset_handler(p_cols=preset_cols):
                                def apply_preset():
                                    state["selected_keys"] = set(p_cols)
                                    _user_selected_cols[dataset_radio.value] = set(state["selected_keys"])
                                    _save_persisted_cols(_user_selected_cols)
                                    _sync_browser_storage(dataset_radio.value, state["selected_keys"])
                                    refresh_column_ui()
                                return apply_preset

                            ui.button(
                                preset_name,
                                on_click=make_preset_handler(preset_cols),
                            ).props("dense outline size=xs color=cyan-3").tooltip(f"Columns: {', '.join(preset_cols[:5])}...")

                    # Render each group
                    for group_name, col_list in groups.items():
                        with ui.card().classes("w-full p-3 bg-gray-900/60 border border-gray-700/50 rounded-lg gap-2"):
                            group_keys = [k for k, _ in col_list]
                            all_in_group = all(k in state["selected_keys"] for k in group_keys)

                            def toggle_group(g_keys=group_keys, current_all=all_in_group):
                                if current_all:
                                    state["selected_keys"] -= set(g_keys)
                                else:
                                    state["selected_keys"] |= set(g_keys)
                                _user_selected_cols[dataset_radio.value] = set(state["selected_keys"])
                                _save_persisted_cols(_user_selected_cols)
                                _sync_browser_storage(dataset_radio.value, state["selected_keys"])
                                refresh_column_ui()

                            with ui.row().classes("w-full items-center justify-between mb-1"):
                                ui.label(group_name).classes("text-xs font-bold text-gray-200")
                                ui.button(
                                    "Toggle Group" if not all_in_group else "Uncheck Group",
                                    on_click=toggle_group,
                                ).props("dense flat size=xs color=gray")

                            # Grid of checkboxes
                            with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-3 gap-y-1"):
                                for key, meta in col_list:
                                    is_checked = key in state["selected_keys"]

                                    def make_handler(col_key=key):
                                        def on_change(e):
                                            if e.value:
                                                state["selected_keys"].add(col_key)
                                            else:
                                                state["selected_keys"].discard(col_key)
                                            _user_selected_cols[dataset_radio.value] = set(state["selected_keys"])
                                            _save_persisted_cols(_user_selected_cols)
                                            _sync_browser_storage(dataset_radio.value, state["selected_keys"])
                                            active_reg = get_active_registry()
                                            count_label.text = f"{len(state['selected_keys'])} of {len(active_reg)} columns selected"
                                            count_badge.text = f"{len(state['selected_keys'])} / {len(active_reg)}"
                                        return on_change

                                    cb = ui.checkbox(meta["label"], value=is_checked).props("dense dark size=sm").classes("text-xs text-gray-300")
                                    cb.on_value_change(make_handler(key))

        def on_dataset_change(e):
            state["dataset"] = e.value
            state["selected_keys"] = set(_user_selected_cols.get(e.value, set()))
            refresh_column_ui()

        dataset_radio.on_value_change(on_dataset_change)
        refresh_column_ui()

        # 3. Footer Actions (Download CSV / XLSX)
        with ui.row().classes("w-full items-center justify-between pt-3 border-t border-gray-800 mt-2 flex-wrap gap-3"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("info", size="xs").classes("text-gray-400")
                ui.label("Exports stream directly from the analytics engine.").classes("text-xs text-gray-400")

            with ui.row().classes("items-center gap-3"):
                ui.button("Cancel", on_click=dialog.close).props("flat color=gray dense")

                def trigger_export(fmt: str):
                    selected_cols = list(state["selected_keys"])
                    if not selected_cols:
                        ui.notify("Please select at least one column to export.", type="warning")
                        return

                    # Preserve the canonical order defined in the column registry
                    registry = get_active_registry()
                    ordered_cols = [k for k in registry.keys() if k in state["selected_keys"]]
                    cols_param = ",".join(ordered_cols)

                    dataset = dataset_radio.value  # 'monthly', 'daily', 'weekly', 'yearly'
                    base_url = f"/api/export/fleet-{dataset}?fmt={fmt}&cols={cols_param}"

                    # Time params
                    mode = period_mode_select.value
                    if mode == "single":
                        if dataset == "monthly":
                            base_url += f"&month={single_month_select.value}"
                        elif dataset == "yearly":
                            yr = str(single_month_select.value)[:4]
                            base_url += f"&start={yr}&end={yr}"
                        elif dataset == "weekly":
                            m_val = single_month_select.value
                            base_url += f"&start={m_val}-01&end={m_val}-31"
                        else:
                            base_url += f"&month={single_month_select.value}"
                    elif mode == "range":
                        if dataset == "monthly":
                            base_url += f"&start_month={start_month_select.value}&end_month={end_month_select.value}"
                        elif dataset == "yearly":
                            s_yr = str(start_month_select.value)[:4]
                            e_yr = str(end_month_select.value)[:4]
                            base_url += f"&start={s_yr}&end={e_yr}"
                        else:
                            base_url += f"&start={start_month_select.value}-01&end={end_month_select.value}-31"
                    # If 'all', omit month filter so all historical data is exported

                    # Platform filter
                    if platform_select.value and platform_select.value != "All":
                        base_url += f"&source={platform_select.value}"

                    # Decommissioned
                    base_url += f"&include_decom={str(decom_checkbox.value).lower()}"

                    _save_persisted_cols(_user_selected_cols)
                    _sync_browser_storage(dataset, state["selected_keys"])

                    ui.download(base_url)
                    ui.notify(
                        f"Downloading {dataset.capitalize()} {fmt.upper()} ({len(ordered_cols)} columns)...",
                        type="positive",
                        icon="cloud_download",
                    )
                    dialog.close()

                ui.button(
                    "📥 Download CSV",
                    on_click=lambda: trigger_export("csv"),
                ).props("unelevated color=cyan-7 text-color=white font-bold px-4 dense")

                ui.button(
                    "📊 Download Excel (XLSX)",
                    on_click=lambda: trigger_export("xlsx"),
                ).props("unelevated color=emerald-7 text-color=white font-bold px-4 dense")

    dialog.open()
