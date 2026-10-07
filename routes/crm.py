from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
import pandas as pd
try:
    from services import crm, s3_archive
    from pipeline import db
    from engines import escalation_categorizer, escalation_state_machine
except ImportError:
    import crm
    import s3_archive
    import db
    import escalation_categorizer
    import escalation_state_machine

router = APIRouter(prefix="/crm")

class CustomerCreate(BaseModel):
    plant_id: str
    customer_name: str
    phone: str
    email: Optional[str] = ""
    preferred_lang: Optional[str] = "english"
    opt_in_status: Optional[str] = "active"

class CampaignPrepareRequest(BaseModel):
    month: Optional[str] = None

class AlertPrepareRequest(BaseModel):
    hours: Optional[int] = 4

@router.get("/customers")
def list_customers(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None)
):
    customers = crm.get_customers(limit=limit, offset=offset, search=search)
    total_df = db.query_df("SELECT count(*) as count FROM customers", db="crm")
    total = int(total_df.iloc[0]["count"]) if not total_df.empty else 0
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "customers": customers,
    }

@router.post("/customers")
def create_or_update_customer(payload: CustomerCreate):
    rowcount = crm.upsert_customer(
        plant_id=payload.plant_id,
        name=payload.customer_name,
        phone=payload.phone,
        email=payload.email or "",
        lang=payload.preferred_lang or "english",
        opt_in=payload.opt_in_status or "active"
    )
    return {"status": "success", "modified_rows": rowcount}

@router.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    profile = crm.get_customer_profile(customer_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Customer not found")
    return profile

@router.post("/customers/import")
async def import_customers(file: UploadFile = File(...)):
    contents = await file.read()
    try:
        df = pd.read_csv(pd.io.common.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {e}")

    imported = 0
    for _, row in df.iterrows():
        pid = row.get("plant_id")
        name = row.get("customer_name")
        phone = row.get("phone")
        if pd.notna(pid) and pd.notna(phone):
            crm.upsert_customer(
                plant_id=str(pid),
                name=str(name) if pd.notna(name) else "Solar Customer",
                phone=str(phone),
                email=str(row.get("email", "")) if pd.notna(row.get("email")) else "",
                lang=str(row.get("preferred_lang", "english")).lower(),
                opt_in=str(row.get("opt_in_status", "active")).lower(),
            )
            imported += 1

    return {"status": "success", "imported": imported}

@router.get("/campaigns")
def list_campaigns():
    df = db.query_df("SELECT * FROM campaign_log ORDER BY id DESC", db="crm")
    return {
        "campaigns": df.to_dict(orient="records") if not df.empty else []
    }

@router.post("/campaigns/prepare")
def prepare_campaign(payload: CampaignPrepareRequest):
    res = crm.prepare_monthly_campaign(payload.month)
    return {"status": "success", "result": res}

@router.get("/offline")
def offline_plants(hours: int = Query(4, ge=1)):
    plants = crm.get_offline_plants(hours_threshold=hours)
    return {"count": len(plants), "plants": plants}

@router.post("/offline/prepare-alerts")
def prepare_offline_alerts(payload: AlertPrepareRequest):
    res = crm.prepare_offline_alerts(hours=payload.hours or 4)
    return {"status": "success", "result": res}

@router.get("/statements")
def get_statement(
    plant_id: str = Query(..., description="Target plant ID"),
    month: Optional[str] = Query(None, description="Month YYYY-MM")
):
    cust_df = db.query_df("SELECT * FROM customers WHERE plant_id = ?", [plant_id], db="crm")
    customer = cust_df.iloc[0].to_dict() if not cust_df.empty else {}

    sql = "SELECT * FROM monthly_generation WHERE plant_id = ?"
    params = [plant_id]
    if month:
        sql += " AND month = ?"
        params.append(month)
    sql += " ORDER BY month DESC"
    gen_df = db.query_df(sql, params, db="analytics")

    return {
        "customer": customer,
        "records": gen_df.to_dict(orient="records") if not gen_df.empty else []
    }


# ── Escalation Engine REST Endpoints ─────────────────────────────────

class EscalationOverrideRequest(BaseModel):
    level: str  # e.g. 'RESOLVED', 'TEAM_ESCALATION', 'L2'
    notes: Optional[str] = ""

class VisitScheduleRequest(BaseModel):
    plant_id: str
    visit_type: Optional[str] = "standard"
    scheduled_date: str
    charges_inr: Optional[float] = 500.0
    notes: Optional[str] = ""


@router.get("/escalations")
def list_escalations(
    category: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    sql = """
    SELECT e.*, c.customer_name, c.phone, c.preferred_lang
    FROM escalation_state e
    LEFT JOIN customers c ON e.plant_id = c.plant_id
    WHERE 1=1
    """
    params = []
    if category:
        sql += " AND e.category = ?"
        params.append(category.upper())
    if level:
        sql += " AND e.current_level = ?"
        params.append(level.upper())
    sql += " ORDER BY e.updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    df = db.query_df(sql, params, db="crm")
    total_df = db.query_df("SELECT count(*) as count FROM escalation_state", db="crm")
    total = int(total_df.iloc[0]["count"]) if not total_df.empty else 0

    return {
        "total": total,
        "count": len(df),
        "escalations": df.to_dict(orient="records") if not df.empty else []
    }


@router.get("/escalations/{plant_id}")
def get_plant_escalation_details(plant_id: str):
    state = escalation_state_machine.get_active_escalation(plant_id)
    if not state:
        raise HTTPException(status_code=404, detail="No escalation state found for plant")

    sql_logs = """
    SELECT * FROM escalation_log
    WHERE plant_id = ?
    ORDER BY created_at DESC;
    """
    logs_df = db.query_df(sql_logs, [plant_id], db="crm")

    cust = escalation_state_machine.get_customer_for_plant(plant_id)
    return {
        "plant_id": plant_id,
        "state": state,
        "customer": cust or {},
        "history": logs_df.to_dict(orient="records") if not logs_df.empty else []
    }


@router.post("/escalations/categorize")
def run_categorization(target_date: Optional[str] = None):
    res = escalation_state_machine.run_daily_categorization(target_date)
    return {"status": "success", "result": res}


@router.post("/escalations/advance")
def run_state_machine_advancement():
    res = escalation_state_machine.advance_all_state_machines()
    return {"status": "success", "advanced_count": len(res), "results": res}


@router.post("/escalations/{plant_id}/override")
def override_escalation_state(plant_id: str, payload: EscalationOverrideRequest):
    state = escalation_state_machine.get_active_escalation(plant_id)
    if not state:
        raise HTTPException(status_code=404, detail="Plant escalation state not found")

    old_level = state["current_level"]
    new_level = payload.level.strip().upper()

    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE escalation_state
            SET current_level = ?, notes = notes || ' | ' || ?, updated_at = datetime('now')
            WHERE plant_id = ?;
        """, [new_level, payload.notes or "Manual operator override", plant_id])

    escalation_state_machine.log_escalation_transition(
        plant_id=plant_id,
        customer_id=state.get("customer_id"),
        category=state["category"],
        from_level=old_level,
        to_level=new_level,
        trigger_reason="manual_operator_override",
        metadata_json=payload.notes
    )

    return {"status": "success", "plant_id": plant_id, "from": old_level, "to": new_level}


@router.get("/visits")
def list_technician_visits(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200)
):
    sql = """
    SELECT v.*, c.customer_name, c.phone
    FROM technician_visits v
    LEFT JOIN customers c ON v.plant_id = c.plant_id
    WHERE 1=1
    """
    params = []
    if status_filter:
        sql += " AND v.status = ?"
        params.append(status_filter.upper())
    sql += " ORDER BY v.created_at DESC LIMIT ?;"
    params.append(limit)

    df = db.query_df(sql, params, db="crm")
    return {
        "visits": df.to_dict(orient="records") if not df.empty else []
    }


@router.post("/visits")
def schedule_technician_visit(payload: VisitScheduleRequest):
    cust = escalation_state_machine.get_customer_for_plant(payload.plant_id)
    cust_id = cust["id"] if cust else None

    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO technician_visits (
                plant_id, customer_id, visit_type, scheduled_date,
                status, charges_inr, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'SCHEDULED', ?, ?, datetime('now'), datetime('now'));
        """, [
            payload.plant_id,
            cust_id,
            payload.visit_type or "standard",
            payload.scheduled_date,
            payload.charges_inr or 500.0,
            payload.notes or "Direct API booking"
        ])
        v_id = cur.lastrowid

    return {"status": "success", "visit_id": v_id, "plant_id": payload.plant_id}


@router.post("/archive/nightly")
def trigger_nightly_s3_archive(target_date: Optional[str] = None):
    res = s3_archive.run_nightly_archive(target_date)
    return {"status": "success", "archive": res}

