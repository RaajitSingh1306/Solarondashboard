"""
Comprehensive Unit & Integration Test Suite for Solaron Escalation Engine.

Tests:
1. Baseline calculation & 6-category classification (ALL_FINE, AVERAGE, CRITICAL_PERF, OFFLINE, INACTIVE, PLANT_CRITICAL)
2. Multi-lingual message template rendering (11 templates x 3 languages)
3. 6-level state machine progression (L1 -> L2 -> L3 -> L4 -> L5 YES/NO -> L6 -> repeat -> team escalation)
4. Cooldown and severity upgrading rules
5. Gupshup outbound client and inbound webhook handling
6. S3 bronze archival snapshotting
7. CRM API REST endpoints
"""

import datetime
import json
import pytest
from fastapi.testclient import TestClient

from app import app
from config import settings
from pipeline import db
from templates import escalation_messages
from engines import escalation_categorizer, escalation_state_machine
from services import gupshup, s3_archive

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure database schemas are initialized and test records cleaned up."""
    db.init_db()
    with db.analytics_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM daily_generation WHERE plant_id LIKE 'TEST-%';")
        cur.execute("DELETE FROM plants WHERE plant_id LIKE 'TEST-%';")
        cur.execute("DELETE FROM inverter_snapshots WHERE plant_id LIKE 'TEST-%';")
    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM escalation_log WHERE plant_id LIKE 'TEST-%';")
        cur.execute("DELETE FROM escalation_state WHERE plant_id LIKE 'TEST-%';")
        cur.execute("DELETE FROM technician_visits WHERE plant_id LIKE 'TEST-%';")
        cur.execute("DELETE FROM customers WHERE plant_id LIKE 'TEST-%';")
        cur.execute("DELETE FROM gupshup_inbound_log WHERE phone IN ('919876543210', '919112233445', '919988776655');")


def test_message_templates_all_languages():
    """Verify all 11 escalation templates format correctly in English, Hindi, and Marathi."""
    tpl_keys = [
        "solaron_active", "solaron_average", "solaron_critical_perf",
        "solaron_offline", "solaron_inactive", "solaron_plant_critical",
        "solaron_check_plant", "solaron_offer_visit", "solaron_visit_scheduled",
        "solaron_wait_recheck", "solaron_reminder"
    ]
    sample_params = {
        "name": "Rajesh Sharma",
        "plant_id": "TEST-PLANT-01",
        "energy": 350.0,
        "expected": 450.0,
        "ratio": 78,
        "month": "September 2026",
        "savings": 4900,
        "hours_offline": 6,
        "days_inactive": 10,
        "fault_code": "ERR_GRID_VOLT",
        "checklist": "• Check MCB\n• Clean panels",
        "visit_type": "standard",
        "charges": 500,
        "date": "10 Oct 2026",
        "recheck_date": "15 Oct 2026",
        "status": "AVERAGE",
    }

    for tpl in tpl_keys:
        for lang in ("english", "hindi", "marathi"):
            msg = escalation_messages.compose_escalation_message(tpl, sample_params, lang)
            assert len(msg) > 20, f"Template {tpl} in {lang} rendered too short: {msg}"
            assert "Rajesh Sharma" in msg or "Solaron" in msg, f"Missing name/brand in {tpl} ({lang})"

    # Check category checklists
    for cat in ("ALL_FINE", "AVERAGE", "CRITICAL_PERF", "OFFLINE", "INACTIVE", "PLANT_CRITICAL"):
        for lang in ("english", "hindi", "marathi"):
            chk = escalation_messages.get_checklist(cat, lang)
            assert len(chk) > 10, f"Checklist for {cat} in {lang} empty"


def test_baseline_calculation():
    """Verify 30-day rolling median baseline and fallback to capacity."""
    test_pid = "TEST-BASELINE-PLANT"
    db.upsert_plant({
        "plant_id": test_pid,
        "source": "growatt",
        "plant_name": "Test Baseline Plant",
        "capacity_kwp": 5.0,
        "capacity_effective": 5.0,
    })

    # Case 1: Insufficient history (< 14 days) -> capacity fallback (5.0 * 4.0 = 20.0)
    baseline, src = escalation_categorizer.get_plant_baseline(test_pid)
    assert src == "capacity_fallback"
    assert baseline == pytest.approx(20.0, rel=0.01)

    # Case 2: Ingest 20 days of daily data -> 30-day median
    daily_rows = []
    base_date = datetime.date(2026, 9, 1)
    for i in range(20):
        d_str = (base_date + datetime.timedelta(days=i)).isoformat()
        daily_rows.append({
            "plant_id": test_pid,
            "date": d_str,
            "kwh": 18.0 if i % 2 == 0 else 22.0,  # median should be 20.0
            "status": "active"
        })
    db.upsert_daily(daily_rows)

    baseline_2, src_2 = escalation_categorizer.get_plant_baseline(test_pid, before_date="2026-09-25")
    assert src_2 == "30_day_median"
    assert baseline_2 == pytest.approx(20.0, rel=0.05)


def test_categorizer_classifications():
    """Verify all 6 categories are correctly identified under various conditions."""
    cat_pid = "TEST-CAT-PLANT"
    db.upsert_plant({
        "plant_id": cat_pid,
        "source": "growatt",
        "plant_name": "Test Categorization Plant",
        "capacity_kwp": 5.0,
        "capacity_effective": 5.0,  # baseline = 20.0 kWh
    })

    target_date = "2026-10-01"

    # 1. ALL_FINE: actual 19.0 kWh (19/20 = 95% >= 90%)
    db.upsert_daily([{"plant_id": cat_pid, "date": target_date, "kwh": 19.0, "status": "active"}])
    res = escalation_categorizer.categorize_plant(cat_pid, target_date)
    assert res["category"] == "ALL_FINE"
    assert res["ratio"] >= 0.90

    # 2. AVERAGE: actual 16.0 kWh (16/20 = 80%, between 70% and 90%)
    db.upsert_daily([{"plant_id": cat_pid, "date": target_date, "kwh": 16.0, "status": "active"}])
    res = escalation_categorizer.categorize_plant(cat_pid, target_date)
    assert res["category"] == "AVERAGE"
    assert 0.70 <= res["ratio"] < 0.90

    # 3. CRITICAL_PERF: actual 10.0 kWh (10/20 = 50% < 70%)
    db.upsert_daily([{"plant_id": cat_pid, "date": target_date, "kwh": 10.0, "status": "active"}])
    res = escalation_categorizer.categorize_plant(cat_pid, target_date)
    assert res["category"] == "CRITICAL_PERF"
    assert res["ratio"] < 0.70

    # 4. OFFLINE: logged as status 'offline' or no telemetry
    db.upsert_daily([{"plant_id": cat_pid, "date": target_date, "kwh": 0.0, "status": "offline"}])
    res = escalation_categorizer.categorize_plant(cat_pid, target_date)
    assert res["category"] == "OFFLINE"

    # 5. INACTIVE: zero generation for >= 7 days
    zero_rows = []
    base_d = datetime.date(2026, 9, 20)
    for i in range(8):
        zero_rows.append({
            "plant_id": cat_pid,
            "date": (base_d + datetime.timedelta(days=i)).isoformat(),
            "kwh": 0.0,
            "status": "active"
        })
    db.upsert_daily(zero_rows)
    res = escalation_categorizer.categorize_plant(cat_pid, "2026-09-27")
    assert res["category"] == "INACTIVE"
    assert res["consecutive_zero_days"] >= 7

    # 6. PLANT_CRITICAL: Inverter snapshot error code present
    db.upsert_snapshots([{
        "plant_id": cat_pid,
        "inverter_sn": "INV-12345",
        "snapshot_ts": "2026-10-02 11:00:00",
        "fault_code": "101",
        "status": "fault",
        "ac_power_w": 0.0,
        "dc_power_w": 0.0,
        "temperature_c": 45.0,
        "e_today_kwh": 0.0
    }])
    res = escalation_categorizer.categorize_plant(cat_pid, "2026-10-02")
    assert res["category"] == "PLANT_CRITICAL"
    assert res["fault_code"] == "101"


def test_state_machine_happy_path_all_fine():
    """Verify ALL_FINE happy path: L1 -> L2 -> L3 -> RESOLVED without technician visit offer."""
    plant_id = "TEST-HAPPY-01"
    db.upsert_plant({"plant_id": plant_id, "source": "growatt", "plant_name": "Happy Plant", "capacity_kwp": 4.0})

    # Trigger ALL_FINE
    cat_meta = {
        "plant_id": plant_id,
        "category": "ALL_FINE",
        "actual_kwh": 18.0,
        "baseline_kwh": 16.0,
        "ratio": 1.12
    }
    t_start = datetime.datetime(2026, 10, 1, 8, 0, 0)
    res_trig = escalation_state_machine.trigger_escalation(plant_id, cat_meta, as_of=t_start)
    assert res_trig["status"] in ("created", "upgraded")

    st = escalation_state_machine.get_active_escalation(plant_id)
    assert st["current_level"] == "L1"

    # Advance L1 -> L2 (Info message sent)
    res_l2 = escalation_state_machine.advance_plant_escalation(plant_id, as_of=t_start)
    assert res_l2["to"] == "L2"

    # Advance L2 -> L3 (+1 day)
    t_day2 = t_start + datetime.timedelta(days=1, hours=1)
    res_l3 = escalation_state_machine.advance_plant_escalation(plant_id, as_of=t_day2)
    assert res_l3["to"] == "L3"

    # Advance L3 -> RESOLVED (+1 day) (Happy path skips visit offering)
    t_day3 = t_day2 + datetime.timedelta(days=1, hours=1)
    res_res = escalation_state_machine.advance_plant_escalation(plant_id, as_of=t_day3)
    assert res_res["to"] == "RESOLVED"

    final_st = escalation_state_machine.get_active_escalation(plant_id)
    assert final_st["current_level"] == "RESOLVED"


def test_state_machine_customer_yes_visit_booking():
    """Verify customer YES reply books technician visit and transitions to VISIT_SCHEDULED."""
    plant_id = "TEST-VISIT-01"
    cust_phone = "919876543210"
    db.upsert_plant({"plant_id": plant_id, "source": "growatt", "plant_name": "Underperforming Plant", "capacity_kwp": 5.0})

    # Link customer
    with db.crm_conn() as conn:
        conn.cursor().execute("""
            INSERT INTO customers (plant_id, customer_name, phone, preferred_lang, opt_in_status)
            VALUES (?, 'Anil Kumar', ?, 'english', 'active')
            ON CONFLICT(plant_id) DO UPDATE SET phone = excluded.phone;
        """, [plant_id, cust_phone])

    # Trigger AVERAGE
    cat_meta = {"plant_id": plant_id, "category": "AVERAGE", "actual_kwh": 15.0, "baseline_kwh": 20.0, "ratio": 0.75}
    t0 = datetime.datetime(2026, 10, 1, 9, 0, 0)
    escalation_state_machine.trigger_escalation(plant_id, cat_meta, as_of=t0)

    # Advance to L4 (offer sent)
    escalation_state_machine.advance_plant_escalation(plant_id, as_of=t0)  # to L2
    escalation_state_machine.advance_plant_escalation(plant_id, as_of=t0 + datetime.timedelta(days=1, hours=1))  # to L3
    escalation_state_machine.advance_plant_escalation(plant_id, as_of=t0 + datetime.timedelta(days=2, hours=1))  # to L4

    st_l4 = escalation_state_machine.get_active_escalation(plant_id)
    assert st_l4["current_level"] == "L4"

    # Customer replies YES via WhatsApp
    reply_res = escalation_state_machine.handle_customer_reply(cust_phone, "YES please schedule visit", as_of=t0 + datetime.timedelta(days=2, hours=3))
    assert reply_res["status"] == "visit_scheduled"
    assert reply_res["charges"] == 500.0

    st_final = escalation_state_machine.get_active_escalation(plant_id)
    assert st_final["current_level"] == "VISIT_SCHEDULED"

    # Verify technician_visits table has row
    v_df = db.query_df("SELECT * FROM technician_visits WHERE plant_id = ?", [plant_id], db="crm")
    assert not v_df.empty
    assert v_df.iloc[0]["status"] == "SCHEDULED"
    assert float(v_df.iloc[0]["charges_inr"]) == 500.0


def test_state_machine_customer_no_and_recheck_loop():
    """Verify customer NO -> L6_RECHECK -> repeat reminder -> TEAM_ESCALATION."""
    plant_id = "TEST-REPEAT-01"
    cust_phone = "919112233445"
    db.upsert_plant({"plant_id": plant_id, "source": "growatt", "plant_name": "Repeated Plant", "capacity_kwp": 5.0})

    with db.crm_conn() as conn:
        conn.cursor().execute("""
            INSERT INTO customers (plant_id, customer_name, phone, preferred_lang, opt_in_status)
            VALUES (?, 'Sunil Patil', ?, 'english', 'active')
            ON CONFLICT(plant_id) DO UPDATE SET phone = excluded.phone;
        """, [plant_id, cust_phone])

    cat_meta = {"plant_id": plant_id, "category": "CRITICAL_PERF", "actual_kwh": 8.0, "baseline_kwh": 20.0, "ratio": 0.40}
    t0 = datetime.datetime(2026, 10, 1, 9, 0, 0)
    escalation_state_machine.trigger_escalation(plant_id, cat_meta, as_of=t0)

    # Advance to L4
    escalation_state_machine.advance_plant_escalation(plant_id, as_of=t0)
    escalation_state_machine.advance_plant_escalation(plant_id, as_of=t0 + datetime.timedelta(days=1, hours=1))
    escalation_state_machine.advance_plant_escalation(plant_id, as_of=t0 + datetime.timedelta(days=2, hours=1))

    # Customer replies NO
    rep = escalation_state_machine.handle_customer_reply(cust_phone, "NO, will check myself", as_of=t0 + datetime.timedelta(days=2, hours=2))
    assert rep["status"] == "recheck_scheduled"

    st = escalation_state_machine.get_active_escalation(plant_id)
    assert st["current_level"] == "L6_RECHECK"

    # Recheck 1: Plant still bad -> repeats L2, reminder_count becomes 1
    t_recheck1 = t0 + datetime.timedelta(days=5, hours=2)
    adv1 = escalation_state_machine.advance_plant_escalation(plant_id, as_of=t_recheck1)
    assert adv1["status"] == "repeated"
    assert adv1["reminder_count"] == 1

    # Simulate fast-forwarding to exceed max_reminders
    with db.crm_conn() as conn:
        conn.cursor().execute("UPDATE escalation_state SET current_level = 'L6_RECHECK', reminder_count = 2, next_action_at = NULL WHERE plant_id = ?", [plant_id])

    # Recheck 2: reminder_count >= max_reminders -> TEAM_ESCALATION
    adv2 = escalation_state_machine.advance_plant_escalation(plant_id, as_of=t_recheck1 + datetime.timedelta(days=3))
    assert adv2["status"] == "team_escalated"
    assert adv2["to"] == "TEAM_ESCALATION"


def test_severity_upgrade_and_cooldown():
    """Verify higher severity upgrades an active state, while same/lower respects cooldown."""
    plant_id = "TEST-SEVERITY-01"
    db.upsert_plant({"plant_id": plant_id, "source": "growatt", "plant_name": "Severity Plant", "capacity_kwp": 5.0})

    t0 = datetime.datetime(2026, 10, 1, 9, 0, 0)
    # Start with AVERAGE
    res1 = escalation_state_machine.trigger_escalation(plant_id, {"category": "AVERAGE"}, as_of=t0)
    assert res1["status"] == "created"

    # Advance to L2
    escalation_state_machine.advance_plant_escalation(plant_id, as_of=t0)

    # Re-trigger with AVERAGE -> cooldown active (no reset)
    res2 = escalation_state_machine.trigger_escalation(plant_id, {"category": "AVERAGE"}, as_of=t0 + datetime.timedelta(hours=5))
    assert res2["status"] == "cooldown_active"

    # Re-trigger with PLANT_CRITICAL (higher severity) -> upgraded and reset to L1
    res3 = escalation_state_machine.trigger_escalation(plant_id, {"category": "PLANT_CRITICAL"}, as_of=t0 + datetime.timedelta(hours=6))
    assert res3["status"] == "upgraded"
    assert res3["category"] == "PLANT_CRITICAL"

    st = escalation_state_machine.get_active_escalation(plant_id)
    assert st["category"] == "PLANT_CRITICAL"
    assert st["current_level"] == "L1"


def test_gupshup_inbound_webhook():
    """Test POST /api/webhooks/gupshup parses inbound customer payload and logs entry."""
    test_phone = "919988776655"
    test_pid = "TEST-HOOK-PLANT"
    db.upsert_plant({"plant_id": test_pid, "source": "growatt", "plant_name": "Webhook Plant", "capacity_kwp": 3.0})

    with db.crm_conn() as conn:
        conn.cursor().execute("""
            INSERT INTO customers (plant_id, customer_name, phone, preferred_lang, opt_in_status)
            VALUES (?, 'Vijay Mane', ?, 'marathi', 'active')
            ON CONFLICT(plant_id) DO UPDATE SET phone = excluded.phone;
        """, [test_pid, test_phone])

    # Put plant in L4 state
    escalation_state_machine.trigger_escalation(test_pid, {"category": "AVERAGE"})
    with db.crm_conn() as conn:
        conn.cursor().execute("UPDATE escalation_state SET current_level = 'L4' WHERE plant_id = ?", [test_pid])

    webhook_payload = {
        "app": "SolaronHomes",
        "timestamp": 1696500000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "MSG_TEST_123456",
            "source": test_phone,
            "type": "text",
            "payload": {
                "text": "YES"
            },
            "sender": {
                "phone": test_phone,
                "name": "Vijay Mane"
            }
        }
    }

    resp = client.post("/api/webhooks/gupshup", json=webhook_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["processed"] is True

    # Check webhook was logged
    inbound_df = db.query_df("SELECT * FROM gupshup_inbound_log WHERE phone = ?", [test_phone], db="crm")
    assert not inbound_df.empty
    assert inbound_df.iloc[0]["processed"] == 1

    # Check plant advanced to VISIT_SCHEDULED
    st = escalation_state_machine.get_active_escalation(test_pid)
    assert st["current_level"] == "VISIT_SCHEDULED"


def test_s3_bronze_archival():
    """Test nightly bronze archiving of state, logs, inbound payloads, and daily gen."""
    archive_res = s3_archive.run_nightly_archive("2026-10-06")
    assert archive_res["target_date"] == "2026-10-06"
    assert "escalation_state" in archive_res
    assert "escalation_log" in archive_res
    assert "daily_generation" in archive_res
    assert archive_res["escalation_state"]["status"] in ("uploaded", "local_mirror", "local_fallback")


def test_crm_escalation_api_endpoints():
    """Verify REST API endpoints for viewing and overriding escalations."""
    test_pid = "TEST-API-PLANT"
    db.upsert_plant({"plant_id": test_pid, "source": "growatt", "plant_name": "API Plant", "capacity_kwp": 4.0})
    escalation_state_machine.trigger_escalation(test_pid, {"category": "AVERAGE"})

    # GET /api/crm/escalations
    resp = client.get("/api/crm/escalations")
    assert resp.status_code == 200
    data = resp.json()
    assert "escalations" in data
    assert any(e["plant_id"] == test_pid for e in data["escalations"])

    # GET /api/crm/escalations/{plant_id}
    resp_detail = client.get(f"/api/crm/escalations/{test_pid}")
    assert resp_detail.status_code == 200
    det = resp_detail.json()
    assert det["state"]["plant_id"] == test_pid
    assert len(det["history"]) >= 1

    # POST /api/crm/escalations/{plant_id}/override
    resp_over = client.post(f"/api/crm/escalations/{test_pid}/override", json={
        "level": "RESOLVED",
        "notes": "Testing override endpoint"
    })
    assert resp_over.status_code == 200
    assert resp_over.json()["to"] == "RESOLVED"

    # POST /api/crm/visits
    resp_vis = client.post("/api/crm/visits", json={
        "plant_id": test_pid,
        "visit_type": "priority",
        "scheduled_date": "12 Oct 2026",
        "charges_inr": 1000.0,
        "notes": "Booked from test"
    })
    assert resp_vis.status_code == 200
    assert resp_vis.json()["status"] == "success"
