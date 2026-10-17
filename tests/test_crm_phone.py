"""
Tests for CRM Customer Phone Requirements:
1. “Phone” column is mandatory.
2. Phone number should have country code as prefix and no ‘+’ symbol.
"""
import io
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from app import app
from services import crm
from pipeline import db

client = TestClient(app)


def test_normalize_phone_various_formats():
    """Verify phone normalizer strips '+' and adds country code prefix."""
    # 10-digit number without country code gets '91' prefix
    assert crm.normalize_phone("9876543210") == "919876543210"

    # Number with leading zero gets replaced with '91'
    assert crm.normalize_phone("09876543210") == "919876543210"

    # Number with '+' symbol gets '+' stripped
    assert crm.normalize_phone("+919876543210") == "919876543210"

    # Number with '+', spaces, and dashes gets cleaned
    assert crm.normalize_phone("+91 98765-43210") == "919876543210"

    # Number with float artifact (.0) gets cleaned
    assert crm.normalize_phone("919876543210.0") == "919876543210"

    # Standard 12-digit Indian number preserved
    assert crm.normalize_phone("919876543210") == "919876543210"

    # Invalid / empty / None returns None
    assert crm.normalize_phone("") is None
    assert crm.normalize_phone("   ") is None
    assert crm.normalize_phone(None) is None
    assert crm.normalize_phone("nan") is None
    assert crm.normalize_phone("null") is None
    assert crm.normalize_phone("12345") is None  # Too short


def test_upsert_customer_mandatory_phone():
    """Verify upsert_customer enforces mandatory phone with country code prefix and no '+'."""
    # Fails when phone is empty
    with pytest.raises(ValueError, match="“Phone” is mandatory"):
        crm.upsert_customer(plant_id="test_plant_nophone", name="Test User", phone="")

    with pytest.raises(ValueError, match="“Phone” is mandatory"):
        crm.upsert_customer(plant_id="test_plant_nophone", name="Test User", phone="   ")

    with pytest.raises(ValueError, match="“Phone” is mandatory"):
        crm.upsert_customer(plant_id="test_plant_nophone", name="Test User", phone="123")

    # Succeeds with valid phone and normalizes '+91' to '91'
    pid = "test_plant_valid_phone_99"
    crm.upsert_customer(plant_id=pid, name="Phone Test Customer", phone="+919812345678")
    
    # Query database and verify
    df = db.query_df("SELECT phone FROM customers WHERE plant_id = ?", [pid], db="crm")
    assert not df.empty
    saved_phone = df.iloc[0]["phone"]
    assert saved_phone == "919812345678"
    assert "+" not in saved_phone
    assert saved_phone.startswith("91")

    # Clean up test row
    db.execute("DELETE FROM customers WHERE plant_id = ?", [pid], db="crm")


def test_customer_import_missing_phone_column():
    """Verify CSV import rejects file when 'Phone' column is missing."""
    csv_without_phone = "plant_id,customer_name,email\nplant_101,Test Customer,test@example.com\n"
    file = ("customers_no_phone.csv", io.BytesIO(csv_without_phone.encode("utf-8")), "text/csv")

    res = client.post("/api/crm/customers/import", files={"file": file})
    assert res.status_code == 400
    assert "“Phone” column is mandatory" in res.json()["detail"]


def test_customer_import_with_phone_normalization():
    """Verify CSV import accepts file with Phone column, strips '+' and prefixes country code."""
    csv_data = """plant_id,customer_name,Phone,preferred_lang,opt_in_status
test_import_p1,Import Customer 1,+919876500001,english,active
test_import_p2,Import Customer 2,9876500002,hindi,active
test_import_p3,Import Customer 3,+91 98765-00003,marathi,opt-out
"""
    file = ("customers_with_phone.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")
    res = client.post("/api/crm/customers/import", files={"file": file})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["imported"] == 3

    # Verify rows in database
    for pid, expected_phone in [
        ("test_import_p1", "919876500001"),
        ("test_import_p2", "919876500002"),
        ("test_import_p3", "919876500003"),
    ]:
        df = db.query_df("SELECT phone FROM customers WHERE plant_id = ?", [pid], db="crm")
        assert not df.empty
        phone = df.iloc[0]["phone"]
        assert phone == expected_phone
        assert "+" not in phone
        assert phone.startswith("91")

        # Cleanup
        db.execute("DELETE FROM customers WHERE plant_id = ?", [pid], db="crm")


def test_customer_api_create_mandatory_phone():
    """Verify POST /api/crm/customers requires phone and normalizes country code prefix."""
    # 1. Missing phone
    payload_no_phone = {
        "plant_id": "test_api_p1",
        "customer_name": "API Test",
        "phone": ""
    }
    res = client.post("/api/crm/customers", json=payload_no_phone)
    assert res.status_code == 400
    assert "“Phone” column is mandatory" in res.json()["detail"]

    # 2. Invalid phone
    payload_bad_phone = {
        "plant_id": "test_api_p1",
        "customer_name": "API Test",
        "phone": "invalid_phone"
    }
    res = client.post("/api/crm/customers", json=payload_bad_phone)
    assert res.status_code == 400
    assert "Phone number should have country code as prefix and no ‘+’ symbol" in res.json()["detail"]

    # 3. Valid phone with '+' symbol
    payload_valid = {
        "plant_id": "test_api_p1",
        "customer_name": "API Test",
        "phone": "+919899911122"
    }
    res = client.post("/api/crm/customers", json=payload_valid)
    assert res.status_code == 200
    assert res.json()["phone"] == "919899911122"
    assert "+" not in res.json()["phone"]

    # Cleanup
    db.execute("DELETE FROM customers WHERE plant_id = 'test_api_p1'", db="crm")


def test_export_customer_phone_formatting():
    """Verify /api/export/customers produces phone numbers without '+' and with country code prefix."""
    pid = "test_export_cust_phone"
    crm.upsert_customer(plant_id=pid, name="Export Phone Customer", phone="+919822334455")

    res = client.get("/api/export/customers?fmt=csv")
    assert res.status_code == 200
    df = pd.read_csv(io.StringIO(res.text), dtype=str)
    assert "phone" in df.columns

    target_rows = df[df["plant_id"] == pid]
    assert not target_rows.empty
    exported_phone = str(target_rows.iloc[0]["phone"])
    assert exported_phone == "919822334455"
    assert "+" not in exported_phone
    assert exported_phone.startswith("91")

    # Cleanup
    db.execute("DELETE FROM customers WHERE plant_id = ?", [pid], db="crm")
