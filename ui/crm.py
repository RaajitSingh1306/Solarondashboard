import asyncio
import datetime
import urllib.parse
from typing import Any, Dict, List, Optional
from nicegui import ui
try:
    from pipeline import db
    from services import crm
except ImportError:
    import db
    import crm

def fetch_fleet_send_data(
    m: str = "2026-09",
    mode: str = "monthly",
    date_val: Optional[str] = None,
    date_range: Optional[tuple] = None,
    year_val: Optional[str] = None,
) -> List[Dict[str, Any]]:
    cust_df = db.query_df("SELECT id, plant_id, customer_name, phone, preferred_lang, opt_in_status FROM customers", db="crm")
    if cust_df.empty:
        return []
    plants_df = db.query_df("SELECT plant_id, plant_name, source, capacity_kwp FROM plants", db="analytics")

    if mode == "daily":
        target_date = date_val or datetime.date.today().isoformat()
        gen_df = db.query_df(
            "SELECT plant_id, kwh, revenue_inr, status, specific_yield FROM daily_generation WHERE date = ?",
            [target_date], db="analytics"
        )
        if not gen_df.empty:
            def get_daily_tier(r):
                kwh = float(r.get("kwh") or 0.0)
                st = str(r.get("status") or "").lower()
                if st == "offline" or kwh <= 0:
                    return "Offline"
                if st == "fault":
                    return "Fault"
                sy = float(r.get("specific_yield") or 0.0)
                if sy >= 4.0:
                    return "Best"
                elif sy >= 3.0:
                    return "Good"
                elif sy >= 2.0:
                    return "Could Be Better"
                return "Critical"
            gen_df["tier"] = gen_df.apply(get_daily_tier, axis=1)

    elif mode == "weekly":
        if date_range and date_range[0] and date_range[1]:
            start_d, end_d = date_range[0], date_range[1]
        else:
            today = datetime.date.today()
            start_week = today - datetime.timedelta(days=today.weekday())
            start_d, end_d = start_week.isoformat(), today.isoformat()

        gen_df = db.query_df(
            """
            SELECT plant_id, ROUND(SUM(kwh), 1) as kwh, ROUND(SUM(revenue_inr), 1) as revenue_inr,
                   ROUND(AVG(specific_yield), 2) as specific_yield,
                   CASE WHEN SUM(kwh) > 0 THEN 'active' ELSE 'offline' END as status
            FROM daily_generation
            WHERE date BETWEEN ? AND ?
            GROUP BY plant_id
            """,
            [start_d, end_d], db="analytics"
        )
        if not gen_df.empty:
            def get_weekly_tier(r):
                kwh = float(r.get("kwh") or 0.0)
                st = str(r.get("status") or "").lower()
                if st == "offline" or kwh <= 0:
                    return "Offline"
                sy = float(r.get("specific_yield") or 0.0)
                if sy >= 4.0:
                    return "Best"
                elif sy >= 3.0:
                    return "Good"
                elif sy >= 2.0:
                    return "Could Be Better"
                return "Critical"
            gen_df["tier"] = gen_df.apply(get_weekly_tier, axis=1)

    elif mode == "yearly":
        target_year = year_val or "2026"
        gen_df = db.query_df(
            """
            SELECT plant_id, ROUND(SUM(kwh), 1) as kwh, ROUND(SUM(revenue_inr), 1) as revenue_inr,
                   ROUND(AVG(specific_yield), 2) as specific_yield,
                   CASE WHEN SUM(kwh) > 0 THEN 'active' ELSE 'offline' END as status
            FROM monthly_generation
            WHERE month LIKE ?
            GROUP BY plant_id
            """,
            [f"{target_year}%"], db="analytics"
        )
        if not gen_df.empty:
            def get_yearly_tier(r):
                kwh = float(r.get("kwh") or 0.0)
                st = str(r.get("status") or "").lower()
                if st == "offline" or kwh <= 0:
                    return "Offline"
                sy = float(r.get("specific_yield") or 0.0)
                if sy >= 80.0:
                    return "Best"
                elif sy >= 60.0:
                    return "Good"
                elif sy >= 40.0:
                    return "Could Be Better"
                return "Critical"
            gen_df["tier"] = gen_df.apply(get_yearly_tier, axis=1)

    else:
        # monthly
        gen_df = db.query_df(
            "SELECT plant_id, kwh, revenue_inr, tier, specific_yield FROM monthly_generation WHERE month = ?",
            [m], db="analytics"
        )

    merged = cust_df.merge(plants_df, on="plant_id", how="left")
    if not gen_df.empty:
        merged = merged.merge(gen_df, on="plant_id", how="left")
    else:
        merged["kwh"] = 0.0
        merged["revenue_inr"] = 0.0
        merged["tier"] = "Offline"
        merged["specific_yield"] = 0.0

    merged["kwh"] = merged["kwh"].fillna(0.0).round(1)
    merged["revenue_inr"] = merged["revenue_inr"].fillna(merged["kwh"] * 14.0).round(0)
    if "tier" not in merged.columns:
        merged["tier"] = "Good"
    else:
        merged["tier"] = merged["tier"].fillna("Good")
    merged["granularity"] = mode
    merged["selected"] = False
    return merged.to_dict(orient="records")

_fetch_fleet_send_data = fetch_fleet_send_data


def build_crm_tab(app_state: dict):
    today = datetime.date.today()
    cur_m = today.strftime("%Y-%m")
    selected_month = {"val": app_state.get("month", cur_m)}
    selected_view = {"mode": "monthly"}  # 'daily', 'weekly', 'monthly', 'yearly'
    selected_date = {"val": datetime.date.today().isoformat()}
    selected_date_range = {"start": "", "end": ""}
    selected_year = {"val": "2026"}

    # WhatsApp Statement & Message Preview Dialog
    preview_modal = ui.dialog().classes("items-center justify-center")
    modal_content = {
        "cust": None,
        "view": "monthly",
        "lang": "english",
        "date_str": datetime.date.today().strftime("%d %b %Y"),
        "year": "2026",
    }

    with preview_modal, ui.card().classes("w-[660px] max-w-full p-6 bg-gray-900 border border-gray-700 text-white shadow-2xl rounded-2xl"):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("chat").classes("text-emerald-400 text-2xl")
                ui.label("WhatsApp Statement & Message Preview").classes("text-base font-bold text-white")
            ui.button(icon="close", on_click=preview_modal.close).props("flat round dense size=sm color=white")

        ui.label("Select report granularity/type and language to preview message formatted for Solaron customers:").classes("text-xs text-gray-400 mb-2")

        # Granularity switcher tabs (programmatic string values)
        preview_granularity_tabs = ui.tabs().classes("w-full bg-gray-800 text-gray-300 rounded-lg mb-2")
        with preview_granularity_tabs:
            ui.tab("monthly", label="Monthly Statement", icon="calendar_month")
            ui.tab("daily", label="Daily Report", icon="today")
            ui.tab("weekly", label="Weekly", icon="date_range")
            ui.tab("yearly", label="Yearly Recap", icon="emoji_events")
            ui.tab("offline", label="Offline Alert", icon="notifications_active")
            ui.tab("monsoon", label="Monsoon Advisory", icon="cloudy_snowing")

        # Language tabs (programmatic string values)
        lang_tabs = ui.tabs().classes("w-full bg-gray-800/80 text-gray-300 rounded-lg mb-3")
        with lang_tabs:
            ui.tab("english", label="English")
            ui.tab("hindi", label="हिंदी (Hindi)")
            ui.tab("marathi", label="मराठी (Marathi)")

        # WhatsApp Bubble Card (WhatsApp Emerald Green Styled, with message_label strictly nested INSIDE)
        with ui.card().classes("w-full p-4 bg-[#075E54] text-white rounded-xl shadow-inner whitespace-pre-line font-sans text-xs leading-relaxed border border-emerald-600/40 min-h-[160px]"):
            message_label = ui.label("Loading preview...").classes("text-emerald-50 select-all font-mono leading-relaxed")

        with ui.row().classes("w-full justify-between items-center mt-4 gap-2 flex-wrap"):
            with ui.row().classes("items-center gap-2"):
                wa_link_btn = ui.button("Open WhatsApp Web", icon="open_in_new").props("dense unelevated color=emerald-7 text-color=white")
                copy_btn = ui.button("Copy Message", icon="content_copy").props("dense outline color=emerald-4")

            ui.button("Close", on_click=preview_modal.close).props("dense flat color=white")

    # Solaron Test WhatsApp Dialog
    test_modal = ui.dialog().classes("items-center justify-center")
    test_state = {
        "phone": getattr(crm.settings, "test_phone_number", "") or "919999999999",
        "template": "monthly",
        "lang": "english",
    }
    with test_modal, ui.card().classes("w-[620px] max-w-full p-6 bg-gray-900 border border-gray-700 text-white rounded-2xl shadow-2xl"):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("send_to_mobile").classes("text-emerald-400 text-2xl")
                ui.label("Send Test WhatsApp Message").classes("text-base font-bold text-white")
            ui.button(icon="close", on_click=test_modal.close).props("flat round dense size=sm color=white")

        ui.label("Dispatch a live test using Solaron official templates directly to your personal or team number:").classes("text-xs text-gray-400 mb-3")

        with ui.row().classes("w-full gap-3 mb-2 flex-wrap"):
            test_phone_input = ui.input("Target Phone (with country code e.g. 919999999999)", value=test_state["phone"]).classes("flex-1 min-w-[220px]").props("dense outlined dark")
            test_tmpl_select = ui.select(
                options={
                    "monthly": "Active Monthly Statement",
                    "offline": "Offline Outage Alert",
                    "monsoon": "Pre-Monsoon Advisory",
                    "daily": "Daily Report",
                    "weekly": "Weekly Summary",
                    "yearly": "Yearly Milestone",
                },
                value="monthly",
                label="Template Type"
            ).classes("w-52").props("dense outlined dark options-dense")
            test_lang_select = ui.select(
                options={"english": "English", "hindi": "हिंदी (Hindi)", "marathi": "मराठी (Marathi)"},
                value="english",
                label="Language"
            ).classes("w-36").props("dense outlined dark options-dense")

        with ui.card().classes("w-full p-4 bg-[#075E54] text-white rounded-xl shadow-inner whitespace-pre-line font-sans text-xs leading-relaxed border border-emerald-600/40 min-h-[150px]"):
            test_preview_label = ui.label("").classes("text-emerald-50 select-all font-mono leading-relaxed")

        with ui.row().classes("w-full justify-between items-center mt-4 gap-2 flex-wrap"):
            with ui.row().classes("items-center gap-2"):
                test_send_btn = ui.button("Open WhatsApp Web", icon="open_in_new").props("dense unelevated color=emerald-7 text-color=white")
                test_copy_btn = ui.button("Copy Message", icon="content_copy").props("dense outline color=emerald-4")
            ui.button("Close", on_click=test_modal.close).props("dense flat color=white")

    def render_test_preview():
        tmpl = test_tmpl_select.value or "monthly"
        lang = test_lang_select.value or "english"
        s_phone = getattr(crm.settings, "support_phone", "") or "+91 00000 00000"
        if tmpl == "offline":
            txt = crm.format_offline_whatsapp_message(
                name="Solar Customer", plant_id="SAMPLE-PLANT", plant_name="Sample Solar Plant",
                support_phone=s_phone, lang=lang
            )
        elif tmpl == "monsoon":
            txt = crm.format_monsoon_whatsapp_message(support_phone=s_phone, lang=lang)
        elif tmpl == "daily":
            txt = crm.format_daily_whatsapp_statement(
                name="Solar Customer", plant_id="SAMPLE-PLANT", plant_name="Sample Solar Plant",
                kwh=16.8, revenue=235.0, date_str=datetime.date.today().strftime("%d %b %Y"), lang=lang
            )
        elif tmpl == "weekly":
            txt = crm.format_weekly_whatsapp_statement(
                name="Solar Customer", plant_id="SAMPLE-PLANT", plant_name="Sample Solar Plant",
                kwh=115.0, revenue=1610.0, lang=lang
            )
        elif tmpl == "yearly":
            txt = crm.format_yearly_whatsapp_statement(
                name="Solar Customer", plant_id="SAMPLE-PLANT", plant_name="Sample Solar Plant",
                kwh=5400.0, revenue=75600.0, year="2026", lang=lang
            )
        else:
            txt = crm.format_rich_whatsapp_statement(
                name="Solar Customer", plant_id="SAMPLE-PLANT", plant_name="Sample Solar Plant",
                kwh=485.5, revenue=6797.0, tier="Good", lang=lang, month=selected_month["val"]
            )
        test_preview_label.text = txt

    test_tmpl_select.on("update:model-value", lambda e: render_test_preview())
    test_lang_select.on("update:model-value", lambda e: render_test_preview())

    def open_test_send_wa():
        ph = (test_phone_input.value or "").strip().replace("+", "").replace("-", "").replace(" ", "")
        if not ph:
            ui.notify("Please enter a valid phone number.", type="warning")
            return
        txt = test_preview_label.text or ""
        enc = urllib.parse.quote(txt)
        url = f"https://web.whatsapp.com/send?phone={ph}&text={enc}"
        ui.run_javascript(f"window.open({repr(url)}, '_blank');")
        ui.notify(f"Launching WhatsApp Web for {ph}...", type="positive")

    test_send_btn.on("click", open_test_send_wa)

    def copy_test_text():
        txt = test_preview_label.text or ""
        js_code = f"""
        (function() {{
            const text = {repr(txt)};
            if (navigator.clipboard && window.isSecureContext) {{
                navigator.clipboard.writeText(text).catch(err => {{
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                }});
            }} else {{
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            }}
        }})();
        """
        ui.run_javascript(js_code)
        ui.notify("Test message copied to clipboard!", type="positive")

    test_copy_btn.on("click", copy_test_text)

    def open_test_modal():
        render_test_preview()
        test_modal.open()

    def get_preview_rendered_text() -> str:
        c = modal_content["cust"]
        if not c:
            return "No customer selected."
        lang = str(modal_content.get("lang") or "english").lower()
        mode = str(modal_content.get("view") or "monthly").lower()
        name = c.get("customer_name") or "Solar Customer"
        pid = c.get("plant_id") or ""
        pname = c.get("plant_name") or pid or "Solar Plant"
        kwh = float(c.get("kwh") or c.get("annual_kwh") or 0.0)
        rev = float(c.get("revenue_inr") or c.get("annual_savings") or (kwh * 14.0))
        phone = str(c.get("phone") or "")

        if mode == "daily":
            if c.get("granularity") == "daily":
                d_kwh = float(c.get("kwh") or 0.0)
                d_rev = float(c.get("revenue_inr") or (d_kwh * 14.0))
            else:
                d_kwh = float(c.get("today_kwh") or c.get("kwh_daily") or (round(kwh / 30.0, 1) if kwh > 0 else 12.5))
                d_rev = d_kwh * 14.0
            return crm.format_daily_whatsapp_statement(
                name=name, plant_id=pid, plant_name=pname,
                kwh=d_kwh, revenue=d_rev,
                date_str=modal_content.get("date_str", ""), lang=lang
            )
        elif mode == "weekly":
            if c.get("granularity") == "weekly":
                w_kwh = float(c.get("kwh") or 0.0)
                w_rev = float(c.get("revenue_inr") or (w_kwh * 14.0))
            else:
                w_kwh = float(c.get("week_kwh") or (round(kwh / 4.33, 1) if kwh > 0 else 85.0))
                w_rev = w_kwh * 14.0
            return crm.format_weekly_whatsapp_statement(
                name=name, plant_id=pid, plant_name=pname,
                kwh=w_kwh, revenue=w_rev, lang=lang
            )
        elif mode == "yearly":
            if c.get("granularity") == "yearly":
                y_kwh = float(c.get("kwh") or 0.0)
                y_rev = float(c.get("revenue_inr") or (y_kwh * 14.0))
            else:
                y_kwh = float(c.get("annual_kwh") or (kwh * 12.0 if kwh > 0 else 4200.0))
                y_rev = y_kwh * 14.0
            return crm.format_yearly_whatsapp_statement(
                name=name, plant_id=pid, plant_name=pname,
                kwh=y_kwh, revenue=y_rev,
                year=modal_content.get("year", "2026"), lang=lang
            )
        elif mode == "offline":
            return crm.format_offline_whatsapp_message(
                name=name, plant_id=pid, plant_name=pname,
                support_phone=phone or getattr(crm.settings, "support_phone", "") or "+91 00000 00000",
                lang=lang
            )
        elif mode == "monsoon":
            return crm.format_monsoon_whatsapp_message(
                support_phone=phone or getattr(crm.settings, "support_phone", "") or "+91 00000 00000",
                lang=lang
            )
        else:
            # Default monthly rich statement
            tier = c.get("tier") or "Good"
            m = selected_month["val"]
            m_kwh = float(c.get("kwh") or 0.0) if c.get("granularity") == "monthly" else kwh
            m_rev = float(c.get("revenue_inr") or (m_kwh * 14.0)) if c.get("granularity") == "monthly" else rev
            return crm.format_rich_whatsapp_statement(
                name=name, plant_id=pid, plant_name=pname,
                kwh=m_kwh, revenue=m_rev, tier=tier,
                lang=lang, month=m
            )

    def refresh_preview_dialog():
        text = get_preview_rendered_text()
        message_label.text = text
        c = modal_content["cust"] or {}
        raw_phone = str(c.get("phone") or "").strip().replace("+", "").replace("-", "").replace(" ", "")
        if raw_phone:
            wa_link_btn.enable()
            wa_link_btn.props("color=emerald-7 text-color=white")
        else:
            wa_link_btn.props("color=grey-7 text-color=grey-3")

    def open_wa_web():
        c = modal_content["cust"] or {}
        raw_phone = str(c.get("phone") or "").strip().replace("+", "").replace("-", "").replace(" ", "")
        txt = message_label.text or get_preview_rendered_text()
        if not raw_phone:
            ui.notify("No customer phone number available. Please edit customer or test with admin phone.", type="warning")
            return
        encoded = urllib.parse.quote(txt)
        url = f"https://web.whatsapp.com/send?phone={raw_phone}&text={encoded}"
        ui.run_javascript(f"window.open({repr(url)}, '_blank');")
        ui.notify(f"Opening WhatsApp Web for {c.get('customer_name') or raw_phone}...", type="positive")

    wa_link_btn.on("click", open_wa_web)

    def do_copy():
        txt = message_label.text or get_preview_rendered_text()
        js_code = f"""
        (function() {{
            const text = {repr(txt)};
            if (navigator.clipboard && window.isSecureContext) {{
                navigator.clipboard.writeText(text).catch(err => {{
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                }});
            }} else {{
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            }}
        }})();
        """
        ui.run_javascript(js_code)
        ui.notify("WhatsApp message copied to clipboard!", type="positive")

    copy_btn.on("click", do_copy)

    def on_preview_granularity_change(e=None):
        val = str(preview_granularity_tabs.value or (e.args if hasattr(e, "args") else "") or "monthly").lower()
        modal_content["view"] = val
        refresh_preview_dialog()

    def on_preview_lang_change(e=None):
        val = str(lang_tabs.value or (e.args if hasattr(e, "args") else "") or "english").lower()
        modal_content["lang"] = val
        refresh_preview_dialog()

    preview_granularity_tabs.on("update:model-value", on_preview_granularity_change)
    lang_tabs.on("update:model-value", on_preview_lang_change)

    def open_preview(cust_row: dict, default_view: str = "monthly"):
        modal_content["cust"] = cust_row
        modal_content["view"] = default_view.lower()
        pref_lang = str(cust_row.get("preferred_lang") or "english").lower()
        if pref_lang not in ("english", "hindi", "marathi"):
            pref_lang = "english"
        modal_content["lang"] = pref_lang

        try:
            d_obj = datetime.date.fromisoformat(str(selected_date.get("val", "")))
            modal_content["date_str"] = d_obj.strftime("%d %b %Y")
        except Exception:
            modal_content["date_str"] = datetime.date.today().strftime("%d %b %Y")
        modal_content["year"] = selected_year.get("val", "2026")

        # Set tab active states
        preview_granularity_tabs.value = modal_content["view"]
        lang_tabs.value = modal_content["lang"]

        refresh_preview_dialog()
        preview_modal.open()

    # Customer Edit / Add Modal
    customer_dialog = ui.dialog().classes("items-center justify-center")
    cust_dialog_mode = {"mode": "add", "id": None}
    with customer_dialog, ui.card().classes("w-[500px] max-w-full p-6 bg-gray-900 border border-gray-700 text-white rounded-xl shadow-2xl"):
        cust_dialog_title = ui.label("Add New Customer Contact").classes("text-base font-bold text-white mb-2")
        d_name = ui.input("Customer Name").classes("w-full").props("dense outlined dark")
        d_plant = ui.input("Plant ID / Serial").classes("w-full").props("dense outlined dark")
        d_phone = ui.input("Phone Number (with Country Code e.g. 919820012345)").classes("w-full").props("dense outlined dark")
        d_email = ui.input("Email (Optional)").classes("w-full").props("dense outlined dark")
        d_lang = ui.select(options=["english", "hindi", "marathi"], value="english", label="Preferred Language").classes("w-full").props("dense outlined dark")
        d_opt = ui.select(options=["active", "opt-out"], value="active", label="WhatsApp Opt-In Status").classes("w-full").props("dense outlined dark")

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=customer_dialog.close).props("dense flat color=white")
            save_cust_btn = ui.button("Save Customer", icon="save").props("dense unelevated color=primary")

    # Main Tab Container
    with ui.column().classes("w-full gap-5"):
        # Top Navigation Bar with the 6 Sub-Tabs
        with ui.tabs().classes("w-full bg-gray-900 border-b border-gray-800 text-gray-300 rounded-t-xl") as sub_tabs:
            st_telemetry = ui.tab("Fleet & Direct Send", icon="bolt")
            st_directory = ui.tab("Customer Directory", icon="people")
            st_monthly = ui.tab("Monthly Statements", icon="receipt_long")
            st_yearly = ui.tab("Yearly Milestones", icon="emoji_events")
            st_campaigns = ui.tab("Campaign Manager", icon="rocket_launch")
            st_alerts = ui.tab("Offline Alerts", icon="notifications_active")

        with ui.tab_panels(sub_tabs, value=st_telemetry).classes("w-full p-0 bg-transparent"):
            # ─────────────────────────────────────────────────────────────
            # SUB-TAB 1: Fleet & Direct WhatsApp Send
            # ─────────────────────────────────────────────────────────────
            with ui.tab_panel(st_telemetry).classes("p-0 w-full gap-5 flex flex-col"):
                # View Granularity & Presets Bar
                with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3 pb-3 border-b border-gray-800"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label("Report Granularity:").classes("text-xs font-bold text-gray-400 uppercase tracking-wider")
                            with ui.button_group().props("dense outline"):
                                bg_d = ui.button("📅 Daily", on_click=lambda: asyncio.create_task(set_view_granularity("daily"))).props("dense text-color=white")
                                bg_w = ui.button("📊 Weekly", on_click=lambda: asyncio.create_task(set_view_granularity("weekly"))).props("dense text-color=white")
                                bg_m = ui.button("🗓️ Monthly", on_click=lambda: asyncio.create_task(set_view_granularity("monthly"))).props("dense color=primary text-color=white")
                                bg_y = ui.button("🏆 Yearly", on_click=lambda: asyncio.create_task(set_view_granularity("yearly"))).props("dense text-color=white")

                        with ui.row().classes("items-center gap-2"):
                            ui.label("⚡ Quick Presets:").classes("text-xs font-semibold text-gray-400")
                            with ui.button_group().props("dense outline"):
                                ui.button("Today", on_click=lambda: asyncio.create_task(apply_preset("today"))).props("dense text-color=white")
                                ui.button("Yesterday", on_click=lambda: asyncio.create_task(apply_preset("yesterday"))).props("dense text-color=white")
                                ui.button("This Week", on_click=lambda: asyncio.create_task(apply_preset("this_week"))).props("dense text-color=white")
                                ui.button("This Month", on_click=lambda: asyncio.create_task(apply_preset("this_month"))).props("dense text-color=white")
                                ui.button("Last Month", on_click=lambda: asyncio.create_task(apply_preset("last_month"))).props("dense text-color=white")
                                ui.button("2026", on_click=lambda: asyncio.create_task(apply_preset("2026"))).props("dense text-color=white")

                    # Filters and Bulk Action Toolbar
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3 pt-2"):
                        with ui.row().classes("items-center gap-3 flex-wrap"):
                            search_input = ui.input(placeholder="🔍 Search customer or plant...").classes("w-56").props("dense outlined dark")
                            source_filter = ui.select(options=["All", "growatt", "isolarcloud", "suryalog"], value="All", label="Platform").classes("w-36").props("dense outlined dark")
                            status_filter = ui.select(
                                options=["All", "Active Only", "Not Working / Fault", "Offline Only", "Underperforming (< -15%)", "Phone Verified"],
                                value="All", label="Plant Status"
                            ).classes("w-44").props("dense outlined dark")

                        with ui.row().classes("items-center gap-2 flex-wrap"):
                            send_mode_select = ui.select(
                                options=["👤 Manual (WhatsApp Web)", "🤖 Auto Simulated Send"],
                                value="👤 Manual (WhatsApp Web)",
                                label="Send Mode"
                            ).classes("w-48").props("dense outlined dark")

                            bulk_send_btn = ui.button("✉ Send Selected (0)", icon="send").props("dense unelevated color=primary")
                            ui.button("📱 Test Send", icon="send_to_mobile", on_click=lambda: open_test_modal()).props("dense outline color=emerald")

                    # Helper selection buttons
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-2 pt-2 border-t border-gray-800/60"):
                        with ui.row().classes("items-center gap-2 flex-wrap"):
                            ui.label("Select Helpers:").classes("text-xs text-gray-500 font-semibold")
                            ui.button("📱 Phone + Active", on_click=lambda: select_helper("active_phone")).props("dense outline size=sm color=positive")
                            ui.button("⚠️ Phone + Not Working", on_click=lambda: select_helper("fault_phone")).props("dense outline size=sm color=warning")
                            ui.button("🔴 Phone + Offline", on_click=lambda: select_helper("offline_phone")).props("dense outline size=sm color=negative")
                            ui.button("📉 Phone + Deviated", on_click=lambda: select_helper("deviated_phone")).props("dense outline size=sm color=amber")
                            ui.button("⚡ All Active", on_click=lambda: select_helper("all_active")).props("dense outline size=sm color=teal")
                            ui.button("⚠️ All Offline", on_click=lambda: select_helper("all_offline")).props("dense outline size=sm color=deep-orange")
                            ui.button("Select All", on_click=lambda: select_helper("all")).props("dense flat size=sm color=white")
                            ui.button("Clear", on_click=lambda: select_helper("none")).props("dense flat size=sm color=gray-4")

                        ui.button("📥 Export Table CSV", on_click=lambda: ui.download("/api/export/fleet-status?fmt=csv"), icon="download").props("dense outline size=sm color=cyan")

                # Direct Telemetry & Send Table
                telemetry_cols = [
                    {"name": "select", "label": "Select", "field": "select", "align": "center"},
                    {"name": "customer_name", "label": "Customer", "field": "customer_name", "sortable": True, "align": "left"},
                    {"name": "plant_name", "label": "Plant Name", "field": "plant_name", "sortable": True, "align": "left"},
                    {"name": "phone", "label": "Phone Number", "field": "phone", "align": "left"},
                    {"name": "source", "label": "Portal", "field": "source", "sortable": True, "align": "center"},
                    {"name": "kwh", "label": "Generation (kWh)", "field": "kwh", "sortable": True, "align": "right"},
                    {"name": "revenue_inr", "label": "Est. Savings (₹)", "field": "revenue_inr", "sortable": True, "align": "right"},
                    {"name": "tier", "label": "Tier / Status", "field": "tier", "sortable": True, "align": "center"},
                    {"name": "actions", "label": "WhatsApp Statement", "field": "actions", "align": "center"},
                ]
                telemetry_table = ui.table(columns=telemetry_cols, rows=[], row_key="id", pagination=15).classes("w-full bg-gray-900 border border-gray-800 rounded-xl")
                telemetry_table.add_slot("body-cell-tier", """
                    <q-td :props="props">
                        <q-chip :color="props.value === 'Best' ? 'amber-8' : props.value === 'Good' ? 'teal-7' : props.value === 'Could Be Better' ? 'blue-grey-7' : props.value === 'Critical' ? 'deep-orange-9' : 'grey-8'" text-color="white" size="sm" dense>
                            {{ props.value || '—' }}
                        </q-chip>
                    </q-td>
                """)
                telemetry_table.add_slot("body-cell-source", """
                    <q-td :props="props">
                        <q-badge :color="props.value === 'growatt' ? 'teal-9' : props.value === 'isolarcloud' ? 'blue-9' : 'purple-9'">
                            {{ props.value }}
                        </q-badge>
                    </q-td>
                """)
                telemetry_table.add_slot("body-cell-select", """
                    <q-td :props="props">
                        <q-checkbox :model-value="props.row.selected" dense @update:model-value="(val) => $parent.$emit('row-select', {id: props.row.id || props.row.plant_id, val: val})" />
                    </q-td>
                """)
                telemetry_table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <div class="row items-center justify-center q-gutter-xs">
                            <q-btn dense flat color="positive" icon="chat" label="Preview" size="sm" @click="() => $parent.$emit('preview', props.row)" />
                            <q-btn v-if="props.row.phone" dense round flat color="emerald" icon="open_in_new" size="xs" @click="() => $parent.$emit('direct-wa', props.row)" />
                        </div>
                    </q-td>
                """)

            # ─────────────────────────────────────────────────────────────
            # SUB-TAB 2: Customer Directory
            # ─────────────────────────────────────────────────────────────
            with ui.tab_panel(st_directory).classes("p-0 w-full gap-5 flex flex-col"):
                # Data Health Audit Card
                with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                    with ui.row().classes("w-full items-center justify-between pb-3 border-b border-gray-800 flex-wrap gap-2"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("health_and_safety").classes("text-cyan-400 text-xl")
                            ui.label("Customer Directory Data Health Audit").classes("text-base font-bold text-white")
                        ui.badge("Live Telemetry Sync Active", color="cyan-9").classes("text-xs font-semibold px-2.5 py-1 rounded")

                    with ui.row().classes("w-full gap-4 mt-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5"):
                        with ui.card().classes("p-3 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Total Customers").classes("text-xs text-gray-400")
                            audit_total_label = ui.label("—").classes("text-xl font-bold text-white")
                        with ui.card().classes("p-3 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Verified Phones").classes("text-xs text-gray-400")
                            audit_phone_label = ui.label("—").classes("text-xl font-bold text-emerald-400")
                        with ui.card().classes("p-3 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Missing Phone").classes("text-xs text-gray-400")
                            audit_nophone_label = ui.label("0").classes("text-xl font-bold text-amber-400")
                        with ui.card().classes("p-3 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Active Opt-In").classes("text-xs text-gray-400")
                            audit_optin_label = ui.label("—").classes("text-xl font-bold text-cyan-400")
                        with ui.card().classes("p-3 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Opted Out").classes("text-xs text-gray-400")
                            audit_optout_label = ui.label("—").classes("text-xl font-bold text-gray-400")

                    # Directory Toolbar
                    with ui.row().classes("w-full items-center justify-between mt-4 flex-wrap gap-3"):
                        with ui.row().classes("items-center gap-3 flex-wrap"):
                            dir_search = ui.input(placeholder="🔍 Search name, phone, plant...").classes("w-64").props("dense outlined dark")
                            dir_opt_filter = ui.select(options=["All", "active", "opt-out"], value="All", label="Opt-in").classes("w-32").props("dense outlined dark")

                        with ui.row().classes("items-center gap-2"):
                            ui.button("Add Customer", icon="person_add", on_click=lambda: open_customer_dialog("add")).props("dense unelevated color=primary")
                            ui.button("Export Directory CSV", icon="download", on_click=lambda: ui.download("/api/export/customers?fmt=csv")).props("dense outline color=cyan")

                # Directory Table
                dir_cols = [
                    {"name": "customer_name", "label": "Customer Name", "field": "customer_name", "sortable": True, "align": "left"},
                    {"name": "plant_id", "label": "Plant ID / Serial", "field": "plant_id", "sortable": True, "align": "left"},
                    {"name": "plant_name", "label": "Assigned Plant", "field": "plant_name", "sortable": True, "align": "left"},
                    {"name": "phone", "label": "Phone Number", "field": "phone", "align": "left"},
                    {"name": "preferred_lang", "label": "Language", "field": "preferred_lang", "align": "center"},
                    {"name": "opt_in_status", "label": "Opt-In", "field": "opt_in_status", "sortable": True, "align": "center"},
                    {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
                ]
                dir_table = ui.table(columns=dir_cols, rows=[], row_key="id", pagination=15).classes("w-full bg-gray-900 border border-gray-800 rounded-xl")
                dir_table.add_slot("body-cell-opt_in_status", """
                    <q-td :props="props">
                        <q-badge :color="props.value === 'active' ? 'positive' : 'grey-7'">
                            {{ props.value }}
                        </q-badge>
                    </q-td>
                """)
                dir_table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <div class="row items-center justify-center q-gutter-xs">
                            <q-btn dense flat color="primary" icon="edit" size="sm" @click="() => $parent.$emit('edit-cust', props.row)" />
                            <q-btn dense flat color="negative" icon="delete" size="sm" @click="() => $parent.$emit('del-cust', props.row)" />
                        </div>
                    </q-td>
                """)

            # ─────────────────────────────────────────────────────────────
            # SUB-TAB 3: Monthly Statements
            # ─────────────────────────────────────────────────────────────
            with ui.tab_panel(st_monthly).classes("p-0 w-full gap-5 flex flex-col"):
                with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3 pb-3 border-b border-gray-800"):
                        with ui.row().classes("items-center gap-3"):
                            ui.icon("receipt_long").classes("text-emerald-400 text-2xl")
                            with ui.column().classes("gap-0"):
                                ui.label("Monthly WhatsApp Statements & Billing Summaries").classes("text-base font-bold text-white")
                                ui.label("Detailed generation, solar yield, CO2 offset, and monetary savings per customer.").classes("text-xs text-gray-400")

                        with ui.row().classes("items-center gap-3"):
                            avail_m = db.get_available_months()
                            stmt_month_select = ui.select(
                                options=avail_m,
                                value=selected_month["val"] if selected_month["val"] in avail_m else (avail_m[0] if avail_m else cur_m),
                                label="Statement Month"
                            ).classes("w-40").props("dense outlined dark options-dense")

                            ui.button("⚡ Prepare Monthly Campaign", icon="campaign", on_click=lambda: run_prepare_monthly()).props("dense unelevated color=primary")
                            ui.button("📥 Export CSV", icon="download", on_click=lambda: ui.download("/api/export/campaign?fmt=csv")).props("dense outline color=cyan")

                    # 4 KPI Summary Cards
                    with ui.row().classes("w-full gap-4 mt-3 grid grid-cols-2 lg:grid-cols-4"):
                        with ui.card().classes("p-3.5 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Total Monthly Generation").classes("text-xs text-gray-400")
                            stmt_gen_kpi = ui.label("— kWh").classes("text-xl font-bold text-white")
                            ui.label("Fleet solar energy produced").classes("text-[10px] text-gray-500")

                        with ui.card().classes("p-3.5 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Total Customer Savings").classes("text-xs text-gray-400")
                            stmt_sav_kpi = ui.label("₹—").classes("text-xl font-bold text-emerald-400")
                            ui.label("Calculated at ₹14.0/kWh").classes("text-[10px] text-gray-500")

                        with ui.card().classes("p-3.5 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Customers Ready").classes("text-xs text-gray-400")
                            stmt_ready_kpi = ui.label("—").classes("text-xl font-bold text-cyan-400")
                            ui.label("Verified phone & active opt-in").classes("text-[10px] text-gray-500")

                        with ui.card().classes("p-3.5 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Reports Pending").classes("text-xs text-gray-400")
                            stmt_pending_kpi = ui.label("—").classes("text-xl font-bold text-amber-400")
                            ui.label("Ready for dispatch queue").classes("text-[10px] text-gray-500")

                # Monthly Statements Table
                stmt_cols = [
                    {"name": "customer_name", "label": "Customer Name", "field": "customer_name", "sortable": True, "align": "left"},
                    {"name": "plant_name", "label": "Plant Name", "field": "plant_name", "sortable": True, "align": "left"},
                    {"name": "phone", "label": "Phone Number", "field": "phone", "align": "left"},
                    {"name": "kwh", "label": "Generation (kWh)", "field": "kwh", "sortable": True, "align": "right"},
                    {"name": "revenue_inr", "label": "Est. Savings (₹)", "field": "revenue_inr", "sortable": True, "align": "right"},
                    {"name": "co2_kg", "label": "CO₂ Saved (kg)", "field": "co2_kg", "sortable": True, "align": "right"},
                    {"name": "specific_yield", "label": "Yield (kWh/kWp)", "field": "specific_yield", "sortable": True, "align": "right"},
                    {"name": "tier", "label": "Tier", "field": "tier", "sortable": True, "align": "center"},
                    {"name": "actions", "label": "Statement", "field": "actions", "align": "center"},
                ]
                stmt_table = ui.table(columns=stmt_cols, rows=[], row_key="id", pagination=15).classes("w-full bg-gray-900 border border-gray-800 rounded-xl")
                stmt_table.add_slot("body-cell-tier", """
                    <q-td :props="props">
                        <q-chip :color="props.value === 'Best' ? 'amber-8' : props.value === 'Good' ? 'teal-7' : props.value === 'Could Be Better' ? 'blue-grey-7' : props.value === 'Critical' ? 'deep-orange-9' : 'grey-8'" text-color="white" size="sm" dense>
                            {{ props.value || '—' }}
                        </q-chip>
                    </q-td>
                """)
                stmt_table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <q-btn dense flat color="positive" icon="chat" label="Preview" size="sm" @click="() => $parent.$emit('preview-stmt', props.row)" />
                    </q-td>
                """)

            # ─────────────────────────────────────────────────────────────
            # SUB-TAB 4: Yearly Milestones
            # ─────────────────────────────────────────────────────────────
            with ui.tab_panel(st_yearly).classes("p-0 w-full gap-5 flex flex-col"):
                with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3 pb-3 border-b border-gray-800"):
                        with ui.row().classes("items-center gap-3"):
                            ui.icon("emoji_events").classes("text-amber-400 text-2xl")
                            with ui.column().classes("gap-0"):
                                ui.label("Annual Solar Milestones & Customer Recap").classes("text-base font-bold text-white")
                                ui.label("Celebrate cumulative yearly generation, customer financial returns, and clean energy milestones.").classes("text-xs text-gray-400")

                        with ui.row().classes("items-center gap-3"):
                            year_select = ui.select(options=["2026", "2025", "2024", "2023"], value="2026", label="Select Year").classes("w-32").props("dense outlined dark")
                            ui.button("🏆 Prepare Yearly Recap Messages", icon="campaign", on_click=lambda: run_prepare_yearly()).props("dense unelevated color=primary")
                            ui.button("📥 Export Yearly CSV", icon="download", on_click=lambda: ui.download("/api/export/fleet-status?fmt=csv")).props("dense outline color=cyan")

                    # 4 Yearly KPI Cards
                    with ui.row().classes("w-full gap-4 mt-3 grid grid-cols-2 lg:grid-cols-4"):
                        with ui.card().classes("p-3.5 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Annual Fleet Generation").classes("text-xs text-gray-400")
                            yearly_gen_kpi = ui.label("— kWh").classes("text-xl font-bold text-white")
                            ui.label("Recorded generation").classes("text-[10px] text-gray-500")

                        with ui.card().classes("p-3.5 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Total Annual Savings").classes("text-xs text-gray-400")
                            yearly_sav_kpi = ui.label("₹—").classes("text-xl font-bold text-emerald-400")
                            ui.label("Calculated at ₹14.0/kWh").classes("text-[10px] text-gray-500")

                        with ui.card().classes("p-3.5 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Homes Powered Equivalent").classes("text-xs text-gray-400")
                            yearly_homes_kpi = ui.label("— days").classes("text-xl font-bold text-cyan-400")
                            ui.label("@ 30 kWh / household / day").classes("text-[10px] text-gray-500")

                        with ui.card().classes("p-3.5 bg-gray-950 border border-gray-800 rounded-lg"):
                            ui.label("Milestone Customers").classes("text-xs text-gray-400")
                            yearly_cust_kpi = ui.label("—").classes("text-xl font-bold text-amber-400")
                            ui.label("Plants with annual records").classes("text-[10px] text-gray-500")

                # Yearly Milestones Table
                yearly_cols = [
                    {"name": "customer_name", "label": "Customer Name", "field": "customer_name", "sortable": True, "align": "left"},
                    {"name": "plant_name", "label": "Plant Name", "field": "plant_name", "sortable": True, "align": "left"},
                    {"name": "phone", "label": "Phone Number", "field": "phone", "align": "left"},
                    {"name": "annual_kwh", "label": "Annual kWh", "field": "annual_kwh", "sortable": True, "align": "right"},
                    {"name": "annual_savings", "label": "Annual Savings (₹)", "field": "annual_savings", "sortable": True, "align": "right"},
                    {"name": "days_powered", "label": "Days Powered", "field": "days_powered", "sortable": True, "align": "right"},
                    {"name": "actions", "label": "Milestone Message", "field": "actions", "align": "center"},
                ]
                yearly_table = ui.table(columns=yearly_cols, rows=[], row_key="id", pagination=15).classes("w-full bg-gray-900 border border-gray-800 rounded-xl")
                yearly_table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <q-btn dense flat color="amber" icon="emoji_events" label="Recap" size="sm" @click="() => $parent.$emit('preview-yearly', props.row)" />
                    </q-td>
                """)

            # ─────────────────────────────────────────────────────────────
            # SUB-TAB 5: Campaign Manager
            # ─────────────────────────────────────────────────────────────
            with ui.tab_panel(st_campaigns).classes("p-0 w-full gap-5 flex flex-col"):
                with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3 pb-3 border-b border-gray-800"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label("Campaign:").classes("text-xs font-bold text-gray-400 uppercase")
                            campaign_select = ui.select(options={}, value=None, label="Select Campaign").classes("w-80").props("dense outlined dark options-dense")

                        with ui.row().classes("items-center gap-2 flex-wrap"):
                            ui.button("📥 Export Campaign CSV", icon="download", on_click=lambda: ui.download("/api/export/campaign?fmt=csv")).props("dense outline color=cyan")
                            dry_run_btn = ui.button("🧪 Run Dry-Run Simulation", icon="science").props("dense unelevated color=indigo-7")
                            ui.button("⚡ Quick Weekly Campaign", icon="date_range", on_click=lambda: run_prepare_weekly()).props("dense outline color=emerald")
                            ui.button("🌧️ Pre-Monsoon Campaign", icon="cloudy_snowing", on_click=lambda: run_prepare_monsoon()).props("dense outline color=teal")

                    # Campaign Summary & Progress Track
                    with ui.column().classes("w-full gap-2 mt-3 p-4 bg-gray-950 border border-gray-800 rounded-lg"):
                        with ui.row().classes("w-full items-center justify-between"):
                            camp_title_label = ui.label("No Campaign Selected").classes("text-sm font-bold text-white")
                            ui.badge("IDLE", color="gray-7").classes("text-xs font-semibold px-2 py-0.5 rounded")

                        # Progress Bar
                        camp_prog_bar = ui.linear_progress(value=0.0).props("color=emerald-5 track-color=grey-9 rounded").classes("w-full h-2.5")

                        # Breakdown metrics
                        with ui.row().classes("w-full gap-5 text-xs text-gray-400 pt-1 flex-wrap"):
                            camp_total_metric = ui.label("Total: 0").classes("text-white font-semibold")
                            camp_sent_metric = ui.label("Sent: 0").classes("text-emerald-400 font-semibold")
                            camp_failed_metric = ui.label("Failed: 0").classes("text-red-400 font-semibold")
                            camp_pending_metric = ui.label("Pending: 0").classes("text-cyan-400 font-semibold")

                # Campaign Messages Queue Table
                msg_cols = [
                    {"name": "id", "label": "#", "field": "id", "align": "center"},
                    {"name": "customer_name", "label": "Customer", "field": "customer_name", "sortable": True, "align": "left"},
                    {"name": "plant_id", "label": "Plant", "field": "plant_id", "sortable": True, "align": "left"},
                    {"name": "phone", "label": "Phone Number", "field": "phone", "align": "left"},
                    {"name": "message_text", "label": "Message Preview", "field": "message_text", "align": "left"},
                    {"name": "status", "label": "Status", "field": "status", "sortable": True, "align": "center"},
                ]
                msg_table = ui.table(columns=msg_cols, rows=[], row_key="id", pagination=15).classes("w-full bg-gray-900 border border-gray-800 rounded-xl")
                msg_table.add_slot("body-cell-status", """
                    <q-td :props="props">
                        <q-badge :color="props.value === 'SENT' ? 'positive' : props.value === 'FAILED' ? 'negative' : 'warning'">
                            {{ props.value }}
                        </q-badge>
                    </q-td>
                """)
                msg_table.add_slot("body-cell-message_text", """
                    <q-td :props="props">
                        <div class="ellipsis" style="max-width: 320px;" :title="props.value">
                            {{ props.value }}
                        </div>
                    </q-td>
                """)

            # ─────────────────────────────────────────────────────────────
            # SUB-TAB 6: Offline Alerts
            # ─────────────────────────────────────────────────────────────
            with ui.tab_panel(st_alerts).classes("p-0 w-full gap-5 flex flex-col"):
                with ui.card().classes("w-full p-4 bg-gray-900 border border-gray-800 rounded-xl"):
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3 pb-3 border-b border-gray-800"):
                        with ui.row().classes("items-center gap-3"):
                            ui.icon("notifications_active").classes("text-red-400 text-2xl")
                            with ui.column().classes("gap-0"):
                                ui.label("Automated Inverter Outage & Fault Alerts").classes("text-base font-bold text-white")
                                ui.label("Identify offline systems and inverter faults with smart 24h deduplication cooldown.").classes("text-xs text-gray-400")

                        with ui.row().classes("items-center gap-3"):
                            alert_threshold_select = ui.select(
                                options={"12": "Offline > 12 Hours", "24": "Offline > 24 Hours", "48": "Offline > 48 Hours"},
                                value="24", label="Offline Threshold"
                            ).classes("w-44").props("dense outlined dark options-dense")

                            ui.button("🚨 Queue Offline Alerts", icon="send", on_click=lambda: run_offline_alerting()).props("dense unelevated color=negative")
                            ui.button("🔄 Refresh", icon="refresh", on_click=lambda: load_offline_alerts()).props("dense outline color=white")

                    with ui.row().classes("w-full items-center justify-between mt-2"):
                        offline_found_label = ui.label("Scanning telemetry for offline plants...").classes("text-xs font-semibold text-amber-400 font-mono")
                        ui.button("📥 Export Outage CSV", icon="download", on_click=lambda: ui.download("/api/export/fleet-status?fmt=csv")).props("dense outline size=sm color=red")

                # Offline Plants Table
                offline_cols = [
                    {"name": "plant_name", "label": "Plant Name", "field": "plant_name", "sortable": True, "align": "left"},
                    {"name": "source", "label": "Portal", "field": "source", "sortable": True, "align": "center"},
                    {"name": "customer_name", "label": "Customer Contact", "field": "customer_name", "sortable": True, "align": "left"},
                    {"name": "phone", "label": "Phone Number", "field": "phone", "align": "left"},
                    {"name": "status", "label": "Device Status", "field": "status", "sortable": True, "align": "center"},
                    {"name": "last_log_time", "label": "Last Telemetry", "field": "last_log_time", "align": "center"},
                    {"name": "actions", "label": "Alert", "field": "actions", "align": "center"},
                ]
                offline_table = ui.table(columns=offline_cols, rows=[], row_key="plant_id", pagination=15).classes("w-full bg-gray-900 border border-gray-800 rounded-xl")
                offline_table.add_slot("body-cell-status", """
                    <q-td :props="props">
                        <q-badge color="negative">
                            {{ props.value }}
                        </q-badge>
                    </q-td>
                """)
                offline_table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <q-btn dense flat color="negative" icon="notifications" label="Preview Alert" size="sm" @click="() => $parent.$emit('preview-alert', props.row)" />
                    </q-td>
                """)

                # Multilingual Draft Offline Alert Box
                with ui.card().classes("w-full p-4 bg-gray-950 border border-red-900/40 rounded-xl"):
                    ui.label("💬 Solaron Draft Outage Alert Preview:").classes("text-xs font-bold text-red-400 uppercase tracking-wider mb-1")
                    ui.label(
                        "Greetings From Solaron Homes Pvt Ltd,\n\n"
                        "Dear Sir/Madam,\n"
                        "Your solar plant is currently detected offline. Please check your AC/DC isolator switches or WiFi data logger.\n"
                        "If any queries, please connect with our team at +91 98200 12345.\n\n"
                        "Team Solaron\n"
                        "सोलरॉन होम्स प्राइवेट लिमिटेड"
                    ).classes("text-xs text-gray-300 font-mono whitespace-pre-line leading-relaxed")

    # ─────────────────────────────────────────────────────────────
    # REACTIVE DATA LOADING & EVENT HANDLERS
    # ─────────────────────────────────────────────────────────────

    cached_telemetry_rows: List[Dict[str, Any]] = []

    async def set_view_granularity(mode: str):
        selected_view["mode"] = mode
        bg_d.props(f"dense {'color=primary' if mode=='daily' else 'outline'} text-color=white")
        bg_w.props(f"dense {'color=primary' if mode=='weekly' else 'outline'} text-color=white")
        bg_m.props(f"dense {'color=primary' if mode=='monthly' else 'outline'} text-color=white")
        bg_y.props(f"dense {'color=primary' if mode=='yearly' else 'outline'} text-color=white")

        col_labels = {
            "daily": "Daily Gen (kWh)",
            "weekly": "Weekly Gen (kWh)",
            "monthly": "Monthly Gen (kWh)",
            "yearly": "Yearly Gen (kWh)",
        }
        for c in telemetry_cols:
            if c["name"] == "kwh":
                c["label"] = col_labels.get(mode, "Generation (kWh)")
        telemetry_table.columns = list(telemetry_cols)

        nonlocal cached_telemetry_rows
        d_val = selected_date.get("val") or datetime.date.today().isoformat()
        d_rng = (selected_date_range.get("start"), selected_date_range.get("end")) if selected_date_range.get("start") else None
        y_val = selected_year.get("val", "2026")
        m_val = selected_month.get("val", cur_m)

        cached_telemetry_rows = await asyncio.to_thread(
            _fetch_fleet_send_data, m_val, mode, d_val, d_rng, y_val
        )
        filter_and_render_telemetry()

    async def apply_preset(p: str):
        today = datetime.date.today()
        if p == "today":
            selected_date["val"] = today.isoformat()
            await set_view_granularity("daily")
        elif p == "yesterday":
            selected_date["val"] = (today - datetime.timedelta(days=1)).isoformat()
            await set_view_granularity("daily")
        elif p == "this_week":
            start_week = today - datetime.timedelta(days=today.weekday())
            selected_date_range["start"] = start_week.isoformat()
            selected_date_range["end"] = today.isoformat()
            await set_view_granularity("weekly")
        elif p == "this_month":
            selected_month["val"] = today.strftime("%Y-%m")
            await set_view_granularity("monthly")
        elif p == "last_month":
            first = today.replace(day=1)
            last_m = first - datetime.timedelta(days=1)
            selected_month["val"] = last_m.strftime("%Y-%m")
            await set_view_granularity("monthly")
        elif p == "2026":
            selected_year["val"] = "2026"
            await set_view_granularity("yearly")

    _fetch_fleet_send_data = fetch_fleet_send_data

    selected_pids = set()

    def filter_and_render_telemetry():
        q = (search_input.value or "").strip().lower()
        src = source_filter.value
        st = status_filter.value
        
        filtered = []
        for r in cached_telemetry_rows:
            pid = str(r.get("id") or r.get("plant_id"))
            r["selected"] = pid in selected_pids
            if q:
                cname = str(r.get("customer_name", "")).lower()
                pname = str(r.get("plant_name", "")).lower()
                if q not in cname and q not in pname and q not in pid.lower():
                    continue
            if src != "All" and str(r.get("source", "")).lower() != src.lower():
                continue
            if st == "Active Only" and (r.get("kwh", 0) <= 0 or r.get("tier") in ("Offline", "Fault")):
                continue
            if st == "Offline Only" and r.get("tier") != "Offline":
                continue
            if st == "Not Working / Fault" and r.get("tier") != "Fault":
                continue
            if st == "Underperforming (< -15%)" and r.get("tier") not in ("Could Be Better", "Critical", "Needs Attention"):
                continue
            if st == "Phone Verified" and not r.get("phone"):
                continue
            filtered.append(r)

        telemetry_table.rows = filtered
        update_selected_count_badge()

    def update_selected_count_badge():
        sel_count = len(selected_pids)
        bulk_send_btn.text = f"✉ Send Selected ({sel_count})"

    def on_row_select(e):
        data = e.args
        if isinstance(data, dict):
            pid = str(data.get("id"))
            is_sel = bool(data.get("val"))
            if is_sel:
                selected_pids.add(pid)
            else:
                selected_pids.discard(pid)
            for r in telemetry_table.rows:
                if str(r.get("id") or r.get("plant_id")) == pid:
                    r["selected"] = is_sel
                    break
        update_selected_count_badge()

    telemetry_table.on("row-select", on_row_select)

    def select_helper(action: str):
        selected_pids.clear()
        for r in telemetry_table.rows:
            pid = str(r.get("id") or r.get("plant_id"))
            raw_phone = str(r.get("phone") or "").strip()
            phone_ok = bool(raw_phone and raw_phone not in ("None", "—", "nan"))
            tier = str(r.get("tier") or "")
            kwh = float(r.get("kwh") or 0.0)
            
            sel = False
            if action == "all":
                sel = True
            elif action == "none":
                sel = False
            elif action == "active_phone":
                sel = phone_ok and kwh > 0 and tier not in ("Offline", "Fault")
            elif action == "fault_phone":
                sel = phone_ok and tier == "Fault"
            elif action == "offline_phone":
                sel = phone_ok and (tier == "Offline" or kwh == 0)
            elif action == "deviated_phone":
                sel = phone_ok and tier in ("Could Be Better", "Critical", "Needs Attention")
            elif action == "all_active":
                sel = kwh > 0 and tier not in ("Offline", "Fault")
            elif action == "all_offline":
                sel = tier == "Offline" or kwh == 0

            r["selected"] = sel
            if sel:
                selected_pids.add(pid)
        telemetry_table.rows = list(telemetry_table.rows)
        update_selected_count_badge()

    search_input.on("update:model-value", lambda e: filter_and_render_telemetry())
    source_filter.on("update:model-value", lambda e: filter_and_render_telemetry())
    status_filter.on("update:model-value", lambda e: filter_and_render_telemetry())

    # Bulk Send Handler
    def on_bulk_send():
        selected = [r for r in telemetry_table.rows if str(r.get("id") or r.get("plant_id")) in selected_pids]
        if not selected:
            ui.notify("Please select at least one customer using the checkboxes or helpers.", type="warning")
            return
        
        mode = send_mode_select.value
        if "Manual" in mode:
            # Find first selected customer with a verified phone
            valid_with_phone = [r for r in selected if str(r.get("phone") or "").strip() not in ("", "None", "—", "nan")]
            if not valid_with_phone:
                ui.notify(f"None of the {len(selected)} selected customer(s) have a phone number.", type="warning")
                return
            first = valid_with_phone[0]
            phone = str(first.get("phone") or "").strip().replace("+", "").replace("-", "").replace(" ", "")
            cur_mode = selected_view.get("mode", "monthly")
            k_val = float(first.get("kwh") or 0.0)
            r_val = float(first.get("revenue_inr") or (k_val * 14.0))
            p_lang = str(first.get("preferred_lang", "english")).lower()
            if cur_mode == "daily":
                d_str = selected_date.get("val", datetime.date.today().strftime("%d %b %Y"))
                txt = crm.format_daily_whatsapp_statement(
                    name=first.get("customer_name", "Customer"),
                    plant_id=first.get("plant_id", ""),
                    plant_name=first.get("plant_name", ""),
                    kwh=k_val, revenue=r_val, date_str=d_str, lang=p_lang
                )
            elif cur_mode == "weekly":
                txt = crm.format_weekly_whatsapp_statement(
                    name=first.get("customer_name", "Customer"),
                    plant_id=first.get("plant_id", ""),
                    plant_name=first.get("plant_name", ""),
                    kwh=k_val, revenue=r_val, lang=p_lang
                )
            elif cur_mode == "yearly":
                txt = crm.format_yearly_whatsapp_statement(
                    name=first.get("customer_name", "Customer"),
                    plant_id=first.get("plant_id", ""),
                    plant_name=first.get("plant_name", ""),
                    kwh=k_val, revenue=r_val, year=selected_year.get("val", "2026"), lang=p_lang
                )
            else:
                txt = crm.format_rich_whatsapp_statement(
                    name=first.get("customer_name", "Customer"),
                    plant_id=first.get("plant_id", ""),
                    plant_name=first.get("plant_name", ""),
                    kwh=k_val, revenue=r_val,
                    tier=first.get("tier", "Good"),
                    lang=p_lang, month=selected_month["val"]
                )
            enc = urllib.parse.quote(txt)
            ui.run_javascript(f"window.open('https://web.whatsapp.com/send?phone={phone}&text={enc}', '_blank');")
            ui.notify(f"Opening WhatsApp Web for {first.get('customer_name')} ({len(selected)} selected)", type="positive")
        else:
            ui.notify(f"Dispatched simulation for {len(selected)} customer statements!", type="positive")
            for r in selected:
                r["selected"] = False
            selected_pids.clear()
            telemetry_table.rows = list(telemetry_table.rows)
            update_selected_count_badge()

    bulk_send_btn.on("click", on_bulk_send)

    telemetry_table.on("preview", lambda e: open_preview(e.args, selected_view["mode"]))
    telemetry_table.on("direct-wa", lambda e: open_preview(e.args, selected_view["mode"]))
    stmt_table.on("preview-stmt", lambda e: open_preview(e.args, "monthly"))
    yearly_table.on("preview-yearly", lambda e: open_preview(e.args, "yearly"))

    # Load Customer Directory & Audit
    async def load_directory_data():
        audit = await asyncio.to_thread(crm.get_customers_audit)
        audit_total_label.text = str(audit["total"])
        audit_phone_label.text = str(audit["with_phone"])
        audit_nophone_label.text = str(audit["missing_phone"])
        audit_optin_label.text = str(audit["opted_in"])
        audit_optout_label.text = str(audit["opted_out"])

        q = (dir_search.value or "").strip()
        rows = await asyncio.to_thread(crm.get_customers, 200, 0, q if q else None)
        plants_df = await asyncio.to_thread(db.query_df, "SELECT plant_id, plant_name FROM plants", db="analytics")
        p_map = dict(zip(plants_df["plant_id"], plants_df["plant_name"])) if not plants_df.empty else {}
        for r in rows:
            r["plant_name"] = p_map.get(str(r.get("plant_id")), r.get("plant_id", ""))
        dir_table.rows = rows

    dir_search.on("update:model-value", lambda e: asyncio.create_task(load_directory_data()))
    dir_opt_filter.on("update:model-value", lambda e: asyncio.create_task(load_directory_data()))

    def open_customer_dialog(mode: str, cust_row: Optional[dict] = None):
        cust_dialog_mode["mode"] = mode
        if mode == "edit" and cust_row:
            cust_dialog_mode["id"] = cust_row.get("id")
            cust_dialog_title.text = f"Edit Customer: {cust_row.get('customer_name')}"
            d_name.value = cust_row.get("customer_name", "")
            d_plant.value = cust_row.get("plant_id", "")
            d_phone.value = cust_row.get("phone", "")
            d_email.value = cust_row.get("email", "")
            d_lang.value = cust_row.get("preferred_lang", "english")
            d_opt.value = cust_row.get("opt_in_status", "active")
        else:
            cust_dialog_mode["id"] = None
            cust_dialog_title.text = "Add New Customer Contact"
            d_name.value = ""
            d_plant.value = ""
            d_phone.value = ""
            d_email.value = ""
            d_lang.value = "english"
            d_opt.value = "active"
        customer_dialog.open()

    async def save_customer():
        name = d_name.value.strip()
        pid = d_plant.value.strip()
        phone = d_phone.value.strip()
        if not name or not pid:
            ui.notify("Customer name and Plant ID are required.", type="warning")
            return
        await asyncio.to_thread(
            crm.upsert_customer,
            plant_id=pid, name=name, phone=phone,
            email=d_email.value.strip(),
            lang=d_lang.value, opt_in=d_opt.value
        )
        customer_dialog.close()
        ui.notify("Customer saved successfully!", type="positive")
        await load_directory_data()

    save_cust_btn.on("click", lambda: asyncio.create_task(save_customer()))
    dir_table.on("edit-cust", lambda e: open_customer_dialog("edit", e.args))
    
    async def delete_cust(row: dict):
        cid = row.get("id")
        if cid:
            await asyncio.to_thread(crm.delete_customer, cid)
            ui.notify("Customer deleted.", type="info")
            await load_directory_data()
    dir_table.on("del-cust", lambda e: asyncio.create_task(delete_cust(e.args)))

    # Load Monthly Statements
    async def load_monthly_statements():
        m = stmt_month_select.value or selected_month["val"]
        rows = await asyncio.to_thread(_fetch_fleet_send_data, m)
        for r in rows:
            r["co2_kg"] = round(r["kwh"] * 0.82, 1)
        stmt_table.rows = rows
        
        tot_kwh = sum(r["kwh"] for r in rows)
        tot_sav = sum(r["revenue_inr"] for r in rows)
        ready = sum(1 for r in rows if r.get("phone") and r.get("opt_in_status") == "active")
        
        stmt_gen_kpi.text = f"{tot_kwh:,.0f} kWh"
        stmt_sav_kpi.text = f"₹{tot_sav:,.0f}"
        stmt_ready_kpi.text = str(ready)
        stmt_pending_kpi.text = str(len(rows))

    stmt_month_select.on("update:model-value", lambda e: asyncio.create_task(load_monthly_statements()))

    # Load Yearly Milestones
    async def load_yearly_milestones():
        yr = year_select.value or "2026"
        rows = await asyncio.to_thread(crm.get_yearly_milestones, yr)
        yearly_table.rows = rows
        
        tot_kwh = sum(r["annual_kwh"] for r in rows)
        tot_sav = sum(r["annual_savings"] for r in rows)
        tot_days = sum(r["days_powered"] for r in rows)
        
        yearly_gen_kpi.text = f"{tot_kwh:,.0f} kWh"
        yearly_sav_kpi.text = f"₹{tot_sav:,.0f}"
        yearly_homes_kpi.text = f"{tot_days:,.0f} days"
        yearly_cust_kpi.text = str(len(rows))

    year_select.on("update:model-value", lambda e: asyncio.create_task(load_yearly_milestones()))

    # Load Campaigns
    async def load_campaigns():
        camps = await asyncio.to_thread(crm.get_all_campaigns)
        if not camps:
            campaign_select.options = {}
            return
        options = {c["id"]: f"#{c['id']} {c['campaign_name']} ({c['status']})" for c in camps}
        campaign_select.options = options
        if not campaign_select.value or campaign_select.value not in options:
            campaign_select.value = camps[0]["id"]
        await on_campaign_changed()

    async def on_campaign_changed():
        cid = campaign_select.value
        if not cid:
            return
        msgs = await asyncio.to_thread(crm.get_campaign_messages, int(cid))
        msg_table.rows = msgs
        
        total = len(msgs)
        sent = sum(1 for m in msgs if m.get("status") == "SENT")
        failed = sum(1 for m in msgs if m.get("status") == "FAILED")
        pending = sum(1 for m in msgs if m.get("status") == "PENDING")
        
        camp_title_label.text = f"Campaign #{cid}"
        camp_total_metric.text = f"Total: {total}"
        camp_sent_metric.text = f"Sent: {sent}"
        camp_failed_metric.text = f"Failed: {failed}"
        camp_pending_metric.text = f"Pending: {pending}"
        
        ratio = (sent / total) if total > 0 else 0.0
        camp_prog_bar.value = ratio

    campaign_select.on("update:model-value", lambda e: asyncio.create_task(on_campaign_changed()))

    # Run Prepare Actions
    async def run_prepare_monthly():
        m = stmt_month_select.value or selected_month["val"]
        res = await asyncio.to_thread(crm.prepare_monthly_campaign, m)
        ui.notify(f"Prepared Monthly Campaign #{res['campaign_id']}: {res['queued']} statements queued!", type="positive")
        sub_tabs.value = st_campaigns
        await load_campaigns()

    async def run_prepare_weekly():
        res = await asyncio.to_thread(crm.prepare_weekly_campaign)
        ui.notify(f"Prepared Weekly Campaign #{res['campaign_id']}: {res['queued']} statements queued!", type="positive")
        sub_tabs.value = st_campaigns
        await load_campaigns()

    async def run_prepare_yearly():
        yr = year_select.value or "2026"
        res = await asyncio.to_thread(crm.prepare_yearly_campaign, yr)
        ui.notify(f"Prepared Yearly Milestone Campaign #{res['campaign_id']}: {res['queued']} recap messages queued!", type="positive")
        sub_tabs.value = st_campaigns
        await load_campaigns()

    async def run_prepare_monsoon():
        res = await asyncio.to_thread(crm.prepare_monsoon_campaign)
        ui.notify(f"Prepared Pre-Monsoon Advisory Campaign #{res['campaign_id']}: {res['queued']} advisories queued!", type="positive")
        sub_tabs.value = st_campaigns
        await load_campaigns()

    # Dry-Run Simulation
    async def do_dry_run():
        cid = campaign_select.value
        if not cid:
            ui.notify("No campaign selected.", type="warning")
            return
        ui.notify(f"Running console dry-run for Campaign #{cid}...", type="info")
        await asyncio.sleep(0.5)
        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE message_queue SET status = 'SENT' WHERE campaign_id = ?", (cid,))
            cur.execute("UPDATE campaign_log SET status = 'COMPLETED', sent_count = total_messages WHERE id = ?", (cid,))
        ui.notify(f"Dry-run simulation completed for Campaign #{cid}!", type="positive")
        await on_campaign_changed()

    dry_run_btn.on("click", lambda: asyncio.create_task(do_dry_run()))

    # Load Offline Alerts
    async def load_offline_alerts():
        h = int(alert_threshold_select.value or 24)
        plants = await asyncio.to_thread(crm.get_offline_plants, h)
        cust_df = await asyncio.to_thread(db.query_df, "SELECT plant_id, customer_name, phone FROM customers", db="crm")
        c_map = {str(r["plant_id"]): r for _, r in cust_df.iterrows()} if not cust_df.empty else {}
        for p in plants:
            c = c_map.get(str(p["plant_id"]), {})
            p["customer_name"] = c.get("customer_name", "—")
            p["phone"] = c.get("phone", "—")
        offline_table.rows = plants
        offline_found_label.text = f"Found {len(plants)} plants in offline or fault condition."

    alert_threshold_select.on("update:model-value", lambda e: asyncio.create_task(load_offline_alerts()))

    async def run_offline_alerting():
        h = int(alert_threshold_select.value or 24)
        res = await asyncio.to_thread(crm.prepare_offline_alerts, h)
        ui.notify(f"Queued {res['alerts_queued']} offline alert messages (checked {res['offline_found']} plants)", type="info")
        await load_offline_alerts()

    offline_table.on("preview-alert", lambda e: open_preview(e.args, "offline"))

    # Initial Master Table Load
    async def load_all_crm_data():
        nonlocal cached_telemetry_rows
        m = selected_month["val"]
        cached_telemetry_rows = await asyncio.to_thread(_fetch_fleet_send_data, m, selected_view["mode"])
        filter_and_render_telemetry()
        await load_directory_data()
        await load_monthly_statements()
        await load_yearly_milestones()
        await load_campaigns()
        await load_offline_alerts()

    # External refresh listener
    async def on_external_update():
        if app_state.get("month") != selected_month["val"]:
            selected_month["val"] = app_state.get("month", cur_m)
            await load_all_crm_data()

    if "refresh_listeners" in app_state:
        app_state["refresh_listeners"].append(lambda: asyncio.create_task(on_external_update()))

    ui.timer(0.05, lambda: asyncio.create_task(load_all_crm_data()), once=True)
