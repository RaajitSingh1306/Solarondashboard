import asyncio
import datetime
import db
import ui.crm as crm_ui
import crm

def test_granularity():
    print("=== 1. Testing _fetch_fleet_send_data directly across all 4 modes ===")
    
    # Test monthly
    monthly_rows = crm_ui._fetch_fleet_send_data("2026-09", mode="monthly")
    assert len(monthly_rows) == 490, f"Expected 490 rows, got {len(monthly_rows)}"
    m_kwh = [r["kwh"] for r in monthly_rows if r["kwh"] > 0]
    print(f"Monthly: {len(monthly_rows)} plants, active: {len(m_kwh)}, avg kWh: {sum(m_kwh)/len(m_kwh):.1f}")

    # Test daily (today)
    daily_rows = crm_ui._fetch_fleet_send_data("2026-09", mode="daily", date_val="2026-09-29")
    assert len(daily_rows) == 490, f"Expected 490 rows, got {len(daily_rows)}"
    d_kwh = [r["kwh"] for r in daily_rows if r["kwh"] > 0]
    print(f"Daily (2026-09-29): {len(daily_rows)} plants, active: {len(d_kwh)}, avg kWh: {sum(d_kwh)/len(d_kwh):.1f}")

    # Test daily (yesterday)
    yest_date = (datetime.date.fromisoformat("2026-09-29") - datetime.timedelta(days=1)).isoformat()
    yest_rows = crm_ui._fetch_fleet_send_data("2026-09", mode="daily", date_val=yest_date)
    assert len(yest_rows) == 490
    y_kwh = [r["kwh"] for r in yest_rows if r["kwh"] > 0]
    print(f"Daily ({yest_date}): {len(yest_rows)} plants, active: {len(y_kwh)}, avg kWh: {sum(y_kwh)/len(y_kwh):.1f}")

    # Test weekly
    week_rows = crm_ui._fetch_fleet_send_data("2026-09", mode="weekly", date_range=("2026-09-23", "2026-09-29"))
    assert len(week_rows) == 490
    w_kwh = [r["kwh"] for r in week_rows if r["kwh"] > 0]
    print(f"Weekly (7 days): {len(week_rows)} plants, active: {len(w_kwh)}, avg kWh: {sum(w_kwh)/len(w_kwh):.1f}")

    # Test yearly
    yearly_rows = crm_ui._fetch_fleet_send_data("2026-09", mode="yearly", year_val="2026")
    assert len(yearly_rows) == 490
    yr_kwh = [r["kwh"] for r in yearly_rows if r["kwh"] > 0]
    print(f"Yearly (2026): {len(yearly_rows)} plants, active: {len(yr_kwh)}, avg kWh: {sum(yr_kwh)/len(yr_kwh):.1f}")

    print("\n=== 2. Validating Scale Hierarchy for Same Plant ===")
    p0 = monthly_rows[0]["plant_id"]
    m_p0 = next(r for r in monthly_rows if r["plant_id"] == p0)
    d_p0 = next(r for r in daily_rows if r["plant_id"] == p0)
    w_p0 = next(r for r in week_rows if r["plant_id"] == p0)
    yr_p0 = next(r for r in yearly_rows if r["plant_id"] == p0)
    
    print(f"Plant {p0}:")
    print(f"  Daily:   {d_p0['kwh']} kWh (Rs.{d_p0['revenue_inr']})")
    print(f"  Weekly:  {w_p0['kwh']} kWh (Rs.{w_p0['revenue_inr']})")
    print(f"  Monthly: {m_p0['kwh']} kWh (Rs.{m_p0['revenue_inr']})")
    print(f"  Yearly:  {yr_p0['kwh']} kWh (Rs.{yr_p0['revenue_inr']})")
    
    assert d_p0["kwh"] < w_p0["kwh"] < m_p0["kwh"] < yr_p0["kwh"], "Scale hierarchy violated!"
    print("Scale hierarchy validated successfully!")

    print("\n=== 3. WhatsApp Formatting Validation ===")
    # Daily statement format
    d_txt = crm.format_daily_whatsapp_statement(
        name="Test Customer", plant_id=p0, plant_name="Test Plant",
        kwh=d_p0["kwh"], revenue=d_p0["revenue_inr"], date_str="29 Sep 2026", lang="english"
    )
    assert str(d_p0["kwh"]) in d_txt, f"Daily kWh {d_p0['kwh']} missing from statement"
    print("Daily statement WhatsApp format OK!")

    # Weekly statement format
    w_txt = crm.format_weekly_whatsapp_statement(
        name="Test Customer", plant_id=p0, plant_name="Test Plant",
        kwh=w_p0["kwh"], revenue=w_p0["revenue_inr"], lang="english"
    )
    assert str(w_p0["kwh"]) in w_txt, f"Weekly kWh {w_p0['kwh']} missing from statement"
    print("Weekly statement WhatsApp format OK!")

    # Yearly statement format
    y_txt = crm.format_yearly_whatsapp_statement(
        name="Test Customer", plant_id=p0, plant_name="Test Plant",
        kwh=yr_p0["kwh"], revenue=yr_p0["revenue_inr"], year="2026", lang="english"
    )
    y_formatted = f"{yr_p0['kwh']:,.1f}" if (yr_p0['kwh'] % 1 != 0) else f"{round(yr_p0['kwh']):,}"
    assert y_formatted in y_txt, f"Yearly kWh {y_formatted} missing from statement"
    print("Yearly statement WhatsApp format OK!")

    print("\n=== ALL GRANULARITY CHECKS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_granularity()
