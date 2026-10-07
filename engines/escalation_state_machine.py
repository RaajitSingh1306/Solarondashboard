"""
Solaron Escalation State Machine Engine.

Implements the 6-level escalation state machine across all 6 plant categories:
L1_TRIGGER -> L2_INFO_SENT -> L3_CHECK_SENT -> L4_OFFER_SENT -> L5_YES/NO -> L6_RECHECK -> RESOLVED / TEAM_ESCALATION.
"""

import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

try:
    from pipeline import db
    from engines import escalation_categorizer
    from templates import escalation_messages
    from services import gupshup
except ImportError:
    import db
    import escalation_categorizer
    import escalation_messages
    import gupshup

logger = logging.getLogger(__name__)

SEVERITY_RANKS = {
    "ALL_FINE": 1,
    "AVERAGE": 2,
    "CRITICAL_PERF": 3,
    "OFFLINE": 4,
    "INACTIVE": 5,
    "PLANT_CRITICAL": 6,
}

VISIT_CHARGES_BY_CATEGORY = {
    "AVERAGE": (500.0, "standard"),
    "CRITICAL_PERF": (500.0, "standard"),
    "OFFLINE": (500.0, "standard"),
    "INACTIVE": (750.0, "inspection"),
    "PLANT_CRITICAL": (1000.0, "priority"),
}


def _now_iso(dt: Optional[datetime.datetime] = None) -> str:
    now = dt or datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


def _parse_iso(iso_str: Optional[str]) -> Optional[datetime.datetime]:
    if not iso_str:
        return None
    try:
        return datetime.datetime.fromisoformat(iso_str)
    except Exception:
        try:
            return datetime.datetime.strptime(iso_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def get_active_escalation(plant_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve current escalation state row for a plant."""
    sql = "SELECT * FROM escalation_state WHERE plant_id = ?;"
    df = db.query_df(sql, [plant_id], db="crm")
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def log_escalation_transition(
    plant_id: str,
    customer_id: Optional[int],
    category: str,
    from_level: Optional[str],
    to_level: str,
    trigger_reason: str,
    message_template: Optional[str] = None,
    gupshup_msg_id: Optional[str] = None,
    metadata_json: Optional[str] = None,
) -> int:
    """Writes an immutable entry to escalation_log audit trail."""
    sql = """
    INSERT INTO escalation_log (
        plant_id, customer_id, category, from_level, to_level,
        trigger_reason, message_template, gupshup_msg_id, metadata_json, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'));
    """
    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, [
            plant_id, customer_id, category, from_level, to_level,
            trigger_reason, message_template, gupshup_msg_id, metadata_json
        ])
        return cur.lastrowid or 0


def get_customer_for_plant(plant_id: str) -> Optional[Dict[str, Any]]:
    """Fetch customer details linked to plant_id."""
    df = db.query_df(
        "SELECT id, plant_id, customer_name, phone, preferred_lang FROM customers WHERE plant_id = ?",
        [plant_id],
        db="crm"
    )
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def trigger_escalation(
    plant_id: str,
    categorization: Dict[str, Any],
    as_of: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Evaluates categorizer output against existing state machine.
    Applies cooldown & severity upgrading rules.
    """
    now_dt = as_of or datetime.datetime.now()
    now_str = _now_iso(now_dt)
    new_cat = categorization.get("category", "ALL_FINE")

    cust = get_customer_for_plant(plant_id)
    cust_id = cust["id"] if cust else None

    existing = get_active_escalation(plant_id)

    if existing:
        curr_level = existing.get("current_level")
        curr_cat = existing.get("category")

        # If plant was previously resolved, we can start a new escalation cycle
        if curr_level == "RESOLVED":
            # Start fresh
            pass
        elif curr_level in ("VISIT_SCHEDULED", "TEAM_ESCALATION"):
            # If visit already scheduled or team handling, only upgrade if PLANT_CRITICAL
            if new_cat == "PLANT_CRITICAL" and curr_cat != "PLANT_CRITICAL":
                pass
            else:
                return {"status": "in_progress", "level": curr_level, "plant_id": plant_id}
        else:
            # Active ongoing escalation: compare severity
            existing_rank = SEVERITY_RANKS.get(curr_cat, 1)
            new_rank = SEVERITY_RANKS.get(new_cat, 1)

            if new_rank <= existing_rank:
                # Cooldown: Don't re-trigger or reset state machine if severity has not escalated
                return {"status": "cooldown_active", "level": curr_level, "category": curr_cat, "plant_id": plant_id}

            # Higher severity detected (e.g. AVERAGE -> PLANT_CRITICAL)
            logger.info("Severity upgrade for plant %s: %s -> %s", plant_id, curr_cat, new_cat)
            with db.crm_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE escalation_state
                    SET category = ?, current_level = 'L1', level_entered_at = ?,
                        next_action_at = ?, notes = ?, updated_at = datetime('now')
                    WHERE plant_id = ?;
                """, [new_cat, now_str, now_str, f"Upgraded from {curr_cat}", plant_id])

            log_escalation_transition(
                plant_id=plant_id,
                customer_id=cust_id,
                category=new_cat,
                from_level=curr_level,
                to_level="L1",
                trigger_reason="severity_upgrade",
                metadata_json=json.dumps(categorization)
            )
            return {"status": "upgraded", "level": "L1", "category": new_cat, "plant_id": plant_id}

    # Initialize new escalation state
    # Next action is set to immediately advance from L1 to L2
    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO escalation_state (
                plant_id, customer_id, category, current_level, level_entered_at,
                reminder_count, max_reminders, next_action_at, notes, created_at, updated_at
            ) VALUES (?, ?, ?, 'L1', ?, 0, 2, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(plant_id) DO UPDATE SET
                category = excluded.category,
                current_level = 'L1',
                level_entered_at = excluded.level_entered_at,
                reminder_count = 0,
                next_action_at = excluded.next_action_at,
                notes = excluded.notes,
                updated_at = datetime('now');
        """, [plant_id, cust_id, new_cat, now_str, now_str, f"Triggered {new_cat}"])

    log_escalation_transition(
        plant_id=plant_id,
        customer_id=cust_id,
        category=new_cat,
        from_level=None,
        to_level="L1",
        trigger_reason="categorizer",
        metadata_json=json.dumps(categorization)
    )
    return {"status": "created", "level": "L1", "category": new_cat, "plant_id": plant_id}


def _send_escalation_message(
    cust: Optional[Dict[str, Any]],
    plant_id: str,
    template_id: str,
    params: Dict[str, Any]
) -> Optional[str]:
    """Helper to format and dispatch WhatsApp template message via Gupshup."""
    if not cust or not cust.get("phone"):
        logger.warning("No customer phone linked for plant %s. Message skipped.", plant_id)
        return None

    lang = cust.get("preferred_lang") or "english"
    res = gupshup.send_template_message_sync(
        phone=cust["phone"],
        template_id=template_id,
        template_params=list(params.values()),
        language=lang
    )
    return res.get("messageId")


def advance_plant_escalation(
    plant_id: str,
    as_of: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Advances a single plant through the 6-level escalation state machine based on timers and logic.
    """
    now_dt = as_of or datetime.datetime.now()
    now_str = _now_iso(now_dt)

    state = get_active_escalation(plant_id)
    if not state:
        return {"status": "not_found", "plant_id": plant_id}

    curr_level = state["current_level"]
    category = state["category"]
    cust_id = state.get("customer_id")
    cust = get_customer_for_plant(plant_id)
    cust_name = cust.get("customer_name") if cust else "Valued Customer"

    # Completed or escalated states do not advance automatically
    if curr_level in ("RESOLVED", "TEAM_ESCALATION", "VISIT_SCHEDULED"):
        return {"status": "terminal_state", "level": curr_level, "plant_id": plant_id}

    next_act_str = state.get("next_action_at")
    next_act_dt = _parse_iso(next_act_str)
    if next_act_dt and now_dt < next_act_dt:
        return {"status": "waiting_timer", "level": curr_level, "next_action_at": next_act_str}

    # -------------------------------------------------------------
    # State Advancement Flow
    # -------------------------------------------------------------

    # 1. L1 -> L2: Send Info Message
    if curr_level == "L1":
        template_map = {
            "ALL_FINE": "solaron_active",
            "AVERAGE": "solaron_average",
            "CRITICAL_PERF": "solaron_critical_perf",
            "OFFLINE": "solaron_offline",
            "INACTIVE": "solaron_inactive",
            "PLANT_CRITICAL": "solaron_plant_critical",
        }
        tpl_id = template_map.get(category, "solaron_average")

        # Prepare parameters
        cat_info = escalation_categorizer.categorize_plant(plant_id)
        month_label = now_dt.strftime("%B %Y")
        params = {
            "name": cust_name,
            "plant_id": plant_id,
            "energy": cat_info.get("actual_kwh", 0),
            "expected": cat_info.get("baseline_kwh", 0),
            "ratio": int((cat_info.get("ratio") or 0) * 100),
            "month": month_label,
            "savings": int(cat_info.get("actual_kwh", 0) * 14.0),
            "hours_offline": 4,
            "days_inactive": max(cat_info.get("consecutive_zero_days", 7), 7),
            "fault_code": cat_info.get("fault_code") or "ERR_VOLTAGE",
        }

        msg_id = _send_escalation_message(cust, plant_id, tpl_id, params)

        # Scheduled next step: +1 day
        next_step = now_dt + datetime.timedelta(days=1)
        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE escalation_state
                SET current_level = 'L2', level_entered_at = ?, next_action_at = ?,
                    last_message_id = ?, updated_at = datetime('now')
                WHERE plant_id = ?;
            """, [now_str, _now_iso(next_step), msg_id, plant_id])

        log_escalation_transition(
            plant_id=plant_id,
            customer_id=cust_id,
            category=category,
            from_level="L1",
            to_level="L2",
            trigger_reason="timer_expired",
            message_template=tpl_id,
            gupshup_msg_id=msg_id,
            metadata_json=json.dumps(params)
        )
        return {"status": "advanced", "from": "L1", "to": "L2", "plant_id": plant_id}

    # 2. L2 -> L3: Send Self-Check Message
    elif curr_level == "L2":
        tpl_id = "solaron_check_plant"
        lang = cust.get("preferred_lang") if cust else "english"
        checklist_text = escalation_messages.get_checklist(category, lang)
        params = {
            "name": cust_name,
            "checklist": checklist_text,
        }
        msg_id = _send_escalation_message(cust, plant_id, tpl_id, params)

        next_step = now_dt + datetime.timedelta(days=1)
        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE escalation_state
                SET current_level = 'L3', level_entered_at = ?, next_action_at = ?,
                    last_message_id = ?, updated_at = datetime('now')
                WHERE plant_id = ?;
            """, [now_str, _now_iso(next_step), msg_id, plant_id])

        log_escalation_transition(
            plant_id=plant_id,
            customer_id=cust_id,
            category=category,
            from_level="L2",
            to_level="L3",
            trigger_reason="timer_expired",
            message_template=tpl_id,
            gupshup_msg_id=msg_id,
            metadata_json=json.dumps(params)
        )
        return {"status": "advanced", "from": "L2", "to": "L3", "plant_id": plant_id}

    # 3. L3 -> L4 or RESOLVED (for ALL_FINE):
    elif curr_level == "L3":
        if category == "ALL_FINE":
            # Happy path customers skip technician visit offer
            with db.crm_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE escalation_state
                    SET current_level = 'RESOLVED', level_entered_at = ?, next_action_at = NULL,
                        notes = 'Happy path cycle completed normally', updated_at = datetime('now')
                    WHERE plant_id = ?;
                """, [now_str, plant_id])

            log_escalation_transition(
                plant_id=plant_id,
                customer_id=cust_id,
                category=category,
                from_level="L3",
                to_level="RESOLVED",
                trigger_reason="happy_path_completed"
            )
            return {"status": "resolved", "from": "L3", "to": "RESOLVED", "plant_id": plant_id}

        # Non-ALL_FINE categories offer technician visit
        tpl_id = "solaron_offer_visit"
        charges, v_type = VISIT_CHARGES_BY_CATEGORY.get(category, (500.0, "standard"))
        params = {
            "name": cust_name,
            "visit_type": v_type,
            "charges": int(charges),
        }
        msg_id = _send_escalation_message(cust, plant_id, tpl_id, params)

        # Give customer 24 hours to reply YES/NO
        next_step = now_dt + datetime.timedelta(days=1)
        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE escalation_state
                SET current_level = 'L4', level_entered_at = ?, next_action_at = ?,
                    last_message_id = ?, updated_at = datetime('now')
                WHERE plant_id = ?;
            """, [now_str, _now_iso(next_step), msg_id, plant_id])

        log_escalation_transition(
            plant_id=plant_id,
            customer_id=cust_id,
            category=category,
            from_level="L3",
            to_level="L4",
            trigger_reason="timer_expired",
            message_template=tpl_id,
            gupshup_msg_id=msg_id,
            metadata_json=json.dumps(params)
        )
        return {"status": "advanced", "from": "L3", "to": "L4", "plant_id": plant_id}

    # 4. L4 -> L5_NO -> L6_RECHECK: (Customer did not reply within 24h)
    elif curr_level == "L4":
        tpl_id = "solaron_wait_recheck"
        recheck_dt = now_dt + datetime.timedelta(days=3)
        recheck_str = recheck_dt.strftime("%d %b %Y")
        params = {
            "name": cust_name,
            "recheck_date": recheck_str,
        }
        msg_id = _send_escalation_message(cust, plant_id, tpl_id, params)

        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE escalation_state
                SET current_level = 'L6_RECHECK', level_entered_at = ?, next_action_at = ?,
                    last_message_id = ?, notes = 'Customer no-reply after 24h, entered recheck',
                    updated_at = datetime('now')
                WHERE plant_id = ?;
            """, [now_str, _now_iso(recheck_dt), msg_id, plant_id])

        log_escalation_transition(
            plant_id=plant_id,
            customer_id=cust_id,
            category=category,
            from_level="L4",
            to_level="L6_RECHECK",
            trigger_reason="timer_expired_no_reply",
            message_template=tpl_id,
            gupshup_msg_id=msg_id,
            metadata_json=json.dumps(params)
        )
        return {"status": "advanced", "from": "L4", "to": "L6_RECHECK", "plant_id": plant_id}

    # 5. L6_RECHECK: (3 days elapsed - evaluate improvement)
    elif curr_level in ("L5_NO", "L6_RECHECK"):
        latest_eval = escalation_categorizer.categorize_plant(plant_id)
        latest_cat = latest_eval.get("category")

        # Improved: back to ALL_FINE or significantly better
        if latest_cat == "ALL_FINE" or (SEVERITY_RANKS.get(latest_cat, 1) < SEVERITY_RANKS.get(category, 1)):
            with db.crm_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE escalation_state
                    SET current_level = 'RESOLVED', level_entered_at = ?, next_action_at = NULL,
                        notes = ?, updated_at = datetime('now')
                    WHERE plant_id = ?;
                """, [now_str, f"Plant improved to {latest_cat}", plant_id])

            log_escalation_transition(
                plant_id=plant_id,
                customer_id=cust_id,
                category=category,
                from_level="L6_RECHECK",
                to_level="RESOLVED",
                trigger_reason="recheck_improved",
                metadata_json=json.dumps(latest_eval)
            )
            return {"status": "resolved", "plant_id": plant_id, "new_category": latest_cat}

        # Not improved: check reminder limit
        reminders = state.get("reminder_count", 0) or 0
        max_rem = state.get("max_reminders", 2) or 2

        if reminders < max_rem:
            # Send reminder and repeat L2-L4 cycle
            tpl_id = "solaron_reminder"
            params = {
                "name": cust_name,
                "plant_id": plant_id,
                "status": latest_cat,
            }
            msg_id = _send_escalation_message(cust, plant_id, tpl_id, params)

            next_step = now_dt + datetime.timedelta(days=1)
            with db.crm_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE escalation_state
                    SET current_level = 'L2', level_entered_at = ?, next_action_at = ?,
                        reminder_count = reminder_count + 1, last_message_id = ?,
                        notes = ?, updated_at = datetime('now')
                    WHERE plant_id = ?;
                """, [now_str, _now_iso(next_step), msg_id, f"Repeat cycle {reminders + 1}", plant_id])

            log_escalation_transition(
                plant_id=plant_id,
                customer_id=cust_id,
                category=category,
                from_level="L6_RECHECK",
                to_level="L2",
                trigger_reason="recheck_unimproved_repeat",
                message_template=tpl_id,
                gupshup_msg_id=msg_id,
                metadata_json=json.dumps({"reminder_count": reminders + 1})
            )
            return {"status": "repeated", "from": "L6_RECHECK", "to": "L2", "reminder_count": reminders + 1}
        else:
            # Exceeded max reminders -> escalate to internal operations team
            with db.crm_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE escalation_state
                    SET current_level = 'TEAM_ESCALATION', level_entered_at = ?, next_action_at = NULL,
                        notes = 'Repeated cycles failed to resolve. Flagged for direct operator outbound intervention.',
                        updated_at = datetime('now')
                    WHERE plant_id = ?;
                """, [now_str, plant_id])

            log_escalation_transition(
                plant_id=plant_id,
                customer_id=cust_id,
                category=category,
                from_level="L6_RECHECK",
                to_level="TEAM_ESCALATION",
                trigger_reason="max_reminders_exceeded"
            )
            return {"status": "team_escalated", "from": "L6_RECHECK", "to": "TEAM_ESCALATION", "plant_id": plant_id}

    return {"status": "noop", "level": curr_level, "plant_id": plant_id}


def handle_customer_reply(
    phone_or_plant: str,
    reply_text: str,
    as_of: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Parses incoming customer replies (YES/NO) and moves state machine.
    """
    now_dt = as_of or datetime.datetime.now()
    now_str = _now_iso(now_dt)
    norm_text = str(reply_text).strip().lower()

    # Find customer & plant
    clean_digits = "".join(filter(str.isdigit, phone_or_plant))
    if len(clean_digits) >= 10:
        phone_suffix = clean_digits[-10:]
        sql = "SELECT * FROM customers WHERE phone LIKE ?;"
        cust_df = db.query_df(sql, [f"%{phone_suffix}%"], db="crm")
    else:
        cust_df = db.query_df("SELECT * FROM customers WHERE plant_id = ?", [phone_or_plant], db="crm")

    if cust_df.empty:
        # Fallback check directly in plants table
        p_df = db.query_df("SELECT plant_id FROM plants WHERE plant_id = ?", [phone_or_plant], db="analytics")
        if p_df.empty:
            return {"status": "unmatched_customer", "input": phone_or_plant}
        plant_id = str(p_df.iloc[0]["plant_id"])
        cust = {"plant_id": plant_id, "customer_name": "Customer", "id": None, "preferred_lang": "english"}
    else:
        cust = cust_df.iloc[0].to_dict()
        plant_id = str(cust["plant_id"])

    state = get_active_escalation(plant_id)
    if not state or state["current_level"] in ("RESOLVED", "TEAM_ESCALATION", "VISIT_SCHEDULED"):
        return {"status": "no_active_escalation", "plant_id": plant_id}

    curr_level = state["current_level"]
    category = state["category"]
    cust_id = cust.get("id")
    cust_name = cust.get("customer_name") or "Valued Customer"

    # Identify keyword intent
    import re
    tokens = set(re.findall(r"[a-z0-9]+", norm_text))
    no_keywords = {"no", "n", "nahi", "nako", "wait", "cancel", "later", "2", "false", "stop", "dont", "not", "postpone"}
    yes_keywords = {"yes", "y", "haan", "ha", "ho", "book", "confirm", "1", "true", "ok", "pls", "please", "service"}

    is_no = bool(tokens & no_keywords or any(norm_text.startswith(nk) for nk in ("no", "nahi", "nako", "wait", "cancel")))
    is_yes = (not is_no) and bool(tokens & yes_keywords or norm_text in ("check", "yes", "book", "confirm"))

    if is_yes:
        # Customer accepted technician visit!
        charges, v_type = VISIT_CHARGES_BY_CATEGORY.get(category, (500.0, "standard"))
        scheduled_dt = now_dt + datetime.timedelta(days=1)
        sched_date_str = scheduled_dt.strftime("%d %b %Y")

        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO technician_visits (
                    plant_id, customer_id, escalation_id, visit_type,
                    scheduled_date, status, charges_inr, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'SCHEDULED', ?, 'Customer confirmed via WhatsApp reply', datetime('now'), datetime('now'));
            """, [plant_id, cust_id, state["id"], v_type, sched_date_str, charges])

            cur.execute("""
                UPDATE escalation_state
                SET current_level = 'VISIT_SCHEDULED', level_entered_at = ?, next_action_at = NULL,
                    notes = ?, updated_at = datetime('now')
                WHERE plant_id = ?;
            """, [now_str, f"Visit booked for {sched_date_str} (₹{charges})", plant_id])

        # Send confirmation message
        tpl_id = "solaron_visit_scheduled"
        params = {
            "name": cust_name,
            "date": sched_date_str,
            "visit_type": v_type,
            "charges": int(charges),
        }
        msg_id = _send_escalation_message(cust, plant_id, tpl_id, params)

        log_escalation_transition(
            plant_id=plant_id,
            customer_id=cust_id,
            category=category,
            from_level=curr_level,
            to_level="VISIT_SCHEDULED",
            trigger_reason="customer_reply_YES",
            message_template=tpl_id,
            gupshup_msg_id=msg_id,
            metadata_json=json.dumps({"reply": reply_text, "charges": charges, "date": sched_date_str})
        )
        return {"status": "visit_scheduled", "plant_id": plant_id, "scheduled_date": sched_date_str, "charges": charges}

    elif is_no:
        # Customer declined visit, wants to wait & recheck
        recheck_dt = now_dt + datetime.timedelta(days=3)
        recheck_date_str = recheck_dt.strftime("%d %b %Y")

        tpl_id = "solaron_wait_recheck"
        params = {
            "name": cust_name,
            "recheck_date": recheck_date_str,
        }
        msg_id = _send_escalation_message(cust, plant_id, tpl_id, params)

        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE escalation_state
                SET current_level = 'L6_RECHECK', level_entered_at = ?, next_action_at = ?,
                    last_message_id = ?, notes = 'Customer opted to wait for recheck',
                    updated_at = datetime('now')
                WHERE plant_id = ?;
            """, [now_str, _now_iso(recheck_dt), msg_id, plant_id])

        log_escalation_transition(
            plant_id=plant_id,
            customer_id=cust_id,
            category=category,
            from_level=curr_level,
            to_level="L6_RECHECK",
            trigger_reason="customer_reply_NO",
            message_template=tpl_id,
            gupshup_msg_id=msg_id,
            metadata_json=json.dumps({"reply": reply_text, "recheck_date": recheck_date_str})
        )
        return {"status": "recheck_scheduled", "plant_id": plant_id, "recheck_date": recheck_date_str}

    # Other freeform reply
    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE escalation_state
            SET notes = notes || ' | Inbound: ' || ?, updated_at = datetime('now')
            WHERE plant_id = ?;
        """, [reply_text[:100], plant_id])

    return {"status": "unrecognized_reply", "reply": reply_text, "plant_id": plant_id}


def advance_all_state_machines(as_of: Optional[datetime.datetime] = None) -> List[Dict[str, Any]]:
    """
    Scans all active plants in escalation_state ready for advancement and advances them.
    """
    now_dt = as_of or datetime.datetime.now()
    now_str = _now_iso(now_dt)

    sql = """
    SELECT plant_id, current_level, next_action_at FROM escalation_state
    WHERE current_level NOT IN ('RESOLVED', 'TEAM_ESCALATION', 'VISIT_SCHEDULED')
      AND (next_action_at IS NULL OR next_action_at <= ?);
    """
    df = db.query_df(sql, [now_str], db="crm")
    if df.empty:
        return []

    results = []
    for _, row in df.iterrows():
        pid = str(row["plant_id"])
        try:
            res = advance_plant_escalation(pid, as_of=now_dt)
            results.append(res)
        except Exception as e:
            logger.error("Error advancing escalation for %s: %s", pid, e)
    return results


def run_daily_categorization(target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Orchestrates daily plant categorization across the entire active fleet,
    triggers/updates escalation states, and immediately advances L1 -> L2 where ready.
    """
    if not target_date:
        target_date = datetime.date.today().isoformat()

    logger.info("Executing daily escalation categorization for date=%s", target_date)
    cat_results = escalation_categorizer.categorize_all_plants(target_date)

    triggered_count = 0
    cooldown_count = 0
    upgraded_count = 0
    now_dt = datetime.datetime.now()

    for item in cat_results:
        pid = item["plant_id"]
        res = trigger_escalation(pid, item, as_of=now_dt)
        st = res.get("status")
        if st == "created":
            triggered_count += 1
        elif st == "upgraded":
            upgraded_count += 1
        elif st == "cooldown_active":
            cooldown_count += 1

    # Advance newly triggered L1 states to L2
    adv_results = advance_all_state_machines(as_of=now_dt)

    summary = {
        "date": target_date,
        "total_plants_evaluated": len(cat_results),
        "newly_triggered": triggered_count,
        "severity_upgraded": upgraded_count,
        "cooldown_active": cooldown_count,
        "states_advanced": len(adv_results),
        "timestamp": now_dt.isoformat()
    }
    logger.info("Daily escalation categorization completed: %s", summary)
    return summary

