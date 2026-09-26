from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
import pandas as pd
import crm
import db

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
