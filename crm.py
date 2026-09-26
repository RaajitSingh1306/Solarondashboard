import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
from config import settings
import db

TEMPLATES = {
    "english": {
        "monthly_summary": "Hello {name}, your solar plant ({plant_id}) produced {kwh} kWh this month! Performance Tier: {tier}. Estimated savings: ₹{revenue}.",
        "offline_alert": "Alert: Your solar plant ({plant_id}) has been detected offline for over {hours} hours. Please check your inverter switch or contact support.",
        "fault_alert": "Urgent Alert: Inverter fault code {fault_code} detected on {plant_id}. Our technical team has been notified.",
    },
    "hindi": {
        "monthly_summary": "नमस्ते {name}, आपके सोलर प्लांट ({plant_id}) ने इस महीने {kwh} kWh बिजली बनाई! परफॉरमेंस टियर: {tier}। अनुमानित बचत: ₹{revenue}।",
        "offline_alert": "चेतावनी: आपका सोलर प्लांट ({plant_id}) {hours} घंटे से अधिक समय से ऑफलाइन है। कृपया इन्वर्टर कनेक्शन जांचें।",
        "fault_alert": "तत्काल सूचना: आपके सोलर प्लांट ({plant_id}) में फॉल्ट कोड {fault_code} दर्ज किया गया है। हमारी टीम को सूचित कर दिया गया है।",
    },
    "marathi": {
        "monthly_summary": "नमस्कार {name}, तुमच्या सोलर प्लांटने ({plant_id}) या महिन्यात {kwh} kWh ऊर्जा निर्माण केली! कार्यक्षमता श्रेणी: {tier}। बचत: ₹{revenue}।",
        "offline_alert": "सूचना: आपला सोलर प्लांट ({plant_id}) {hours} तासांपेक्षा जास्त वेळ ऑफलाइन आहे. कृपया इन्व्हर्टर तपासा.",
        "fault_alert": "तातडीची सूचना: आपल्या सोलर प्लांटमध्ये ({plant_id}) त्रुटी कोड {fault_code} आढळला आहे.",
    }
}

MARKETING_CTAS = {
    "english": {
        "Best": "🌟 *Solar Champion!* Your plant is in our top 15% fleet performers. Love your solar savings? Refer a neighbor and get ₹2,500 Amazon voucher upon grid connection!",
        "Good": "🧼 *Seasonal Tip:* Your generation is on track! Washing dust off your panels every 15 days in early mornings will maximize harvest by another 6-8%.",
        "Could Be Better": "🌿 *Efficiency Alert:* Output was slightly lower than clear-sky potential. Check for tree shadows or bird drop soiling. Need assistance? Reply 'SERVICE'.",
        "Needs Attention": "⚠️ *Inspection Suggested:* Your generation is 15-30% below peer average. Dust buildup or grid voltage fluctuations may be capping yield. Reply 'CHECK' for assistance.",
        "Critical": "🚨 *Action Recommended:* Your plant produced below threshold. Our diagnostic team recommends a complimentary health check. Reply 'CALL' to book a technician.",
        "Offline": "⚠️ *System Disconnected:* Zero energy detected. Please ensure AC/DC isolators are ON and your WiFi data logger has green light.",
        "Fault": "🚨 *Inverter Fault:* An automated fault state is detected. Our engineering team is reviewing your telemetry.",
    },
    "hindi": {
        "Best": "🌟 *सोलर चैंपियन!* आपका प्लांट टॉप 15% सबसे अच्छा प्रदर्शन करने वालों में है। अपने दोस्त को रेफर करें और ₹2,500 का रिवॉर्ड पाएं!",
        "Good": "🧼 *सफाई टिप:* आपका सिस्टम अच्छा चल रहा है। हर 15 दिन में सुबह-सुबह पैनल धोने से 6-8% अधिक बिजली बनेगी।",
        "Could Be Better": "🌿 *सलाह:* इस महीने बिजली उत्पादन थोड़ा कम रहा। पैनलों पर धूल या छाया की जांच करें। सहायता के लिए 'SERVICE' लिखकर भेजें।",
        "Needs Attention": "⚠️ *जांच की सलाह:* आपका उत्पादन आसपास के समान प्लांट्स से 15-30% कम है। कृपया पैनलों की सफाई या ग्रिड वोल्टेज जांचें। सहायता के लिए 'CHECK' लिखें।",
        "Critical": "🚨 *ध्यान दें:* प्लांट का उत्पादन औसत से कम है। मुफ्त स्वास्थ्य जांच के लिए 'CALL' लिखकर जवाब दें।",
        "Offline": "⚠️ *सिस्टम ऑफलाइन:* सोलर इनवर्टर चालू है या नहीं जांचें।",
        "Fault": "🚨 *इन्वर्टर समस्या:* तकनीकी सहायता के लिए हमारी टीम तत्पर है।",
    },
    "marathi": {
        "Best": "🌟 *सोलर चॅम्पियन!* तुमचा सोलर प्लांट सर्वोत्तम कामगिरी करणाऱ्या टॉप १५% मध्ये आहे. मित्राला रेफर करा आणि ₹२,५०० मिळवा!",
        "Good": "🧼 *देखभाल टीप:* दर १५ दिवसांनी सकाळी पॅनेल्स धुतल्यास ६-८% जास्त वीज मिळेल.",
        "Could Be Better": "🌿 *सूचना:* या महिन्यात उत्पादन थोडे कमी आहे. पॅनेलवरील धूळ किंवा सावली तपासा. मदतीसाठी 'SERVICE' पाठवा.",
        "Needs Attention": "⚠️ *तपासणीची गरज:* तुमचे उत्पादन सरासरीपेक्षा १५-३०% कमी आहे. कृपया पॅनेल्सची स्वच्छता व व्होल्टेज तपासा. मदतीसाठी 'CHECK' पाठवा.",
        "Critical": "🚨 *तातडीची गरज:* उत्पादन खूप कमी झाले आहे. मोफत तांत्रिक तपासणीसाठी 'CALL' पाठवा.",
        "Offline": "⚠️ *सिस्टम ऑफलाइन:* कृपया इन्व्हर्टर स्विच चालू असल्याची खात्री करा.",
        "Fault": "🚨 *दोष आढळला:* आमचे तंत्रज्ञ लवकरच संपर्क साधतील.",
    }
}

def format_rich_whatsapp_statement(
    name: str,
    plant_id: str,
    plant_name: str,
    kwh: float,
    revenue: float,
    tier: str,
    lang: str = "english",
    month: str = "2026-09"
) -> str:
    lang = lang.lower() if lang else "english"
    if lang not in MARKETING_CTAS:
        lang = "english"

    tier_clean = tier if tier in MARKETING_CTAS[lang] else "Good"
    cta = MARKETING_CTAS[lang].get(tier_clean, MARKETING_CTAS[lang]["Good"])
    co2 = round(kwh * 0.82, 1)
    days_powered = max(1, round(kwh / 10.5))

    if lang == "hindi":
        return f"""☀️ *सोलरऑन मासिक प्रदर्शन विवरण* ☀️
📅 माह: *{month}*
👤 ग्राहक: *{name}*
📍 सोलर प्लांट: *{plant_name}* (`{plant_id}`)

📊 *बिजली उत्पादन व बचत:*
⚡ कुल उत्पादन: *{kwh:,.1f} kWh*
💰 अनुमानित बिजली बचत: *₹{revenue:,.0f}*
🏆 परफॉरमेंस टियर: *{tier}*
🌱 CO₂ बचाव: *{co2} किलोग्राम*
💡 घरेलू उपयोग समतुल्य: *{days_powered} दिन*

{cta}

📞 किसी भी प्रश्न के लिए सोलरऑन केयर से संपर्क करें या इस संदेश का उत्तर दें।"""
    elif lang == "marathi":
        return f"""☀️ *सोलरऑन मासिक कार्यक्षमता अहवाल* ☀️
📅 कालावधी: *{month}*
👤 ग्राहक: *{name}*
📍 प्रकल्प: *{plant_name}* (`{plant_id}`)

📊 *ऊर्जा व बचत तपशील:*
⚡ एकूण निर्मिती: *{kwh:,.1f} kWh*
💰 अंदाजे आर्थिक बचत: *₹{revenue:,.0f}*
🏆 कार्यक्षमता श्रेणी: *{tier}*
🌱 कार्बन उत्सर्जन घट: *{co2} kg*
💡 घरगुती वीज समतुल्य: *{days_powered} दिवस*

{cta}

📞 अधिक माहितीसाठी सोलरऑन ग्राहक सेवेशी संपर्क साधा."""
    else:
        return f"""☀️ *SolarOn Monthly Solar Statement* ☀️
📅 Period: *{month}*
👤 Customer: *{name}*
📍 Plant: *{plant_name}* (`{plant_id}`)

📊 *Energy Harvest & Financial Return:*
⚡ Total Generation: *{kwh:,.1f} kWh*
💰 Estimated Savings: *₹{revenue:,.0f}*
🏆 Performance Tier: *{tier}*
🌱 Carbon Offset: *{co2:,.1f} kg CO₂*
💡 Home Energy Equivalent: *{days_powered} Days Powered*

{cta}

📞 Questions? Contact SolarOn Care at +91 98200 12345 or reply to this message."""

def format_daily_whatsapp_statement(
    name: str,
    plant_id: str,
    plant_name: str,
    kwh: float,
    revenue: float = 0.0,
    date_str: str = "",
    lang: str = "english"
) -> str:
    lang = (lang or "english").lower()
    date_display = date_str or datetime.date.today().strftime("%d %b %Y")
    energy = round(kwh, 1)
    savings = round(revenue or (kwh * 14.0))

    if lang == "hindi":
        return f"""सोलरॉन होम्स की ओर से नमस्कार,

प्रिय महोदय/मैम,
आपके सोलर प्लांट ({plant_name}) ने आज ({date_display}) कुल {energy} यूनिट बिजली बनाई।
आपने लगभग ₹{savings:,.0f} की बचत की है।
प्लांट की नियमित सफाई से अधिकतम बिजली उत्पादन व बचत सुनिश्चित करें।
सफाई उपकरण या किसी भी प्रश्न के लिए हमसे संपर्क करें।

धन्यवाद,
टीम सोलरॉन"""
    elif lang == "marathi":
        return f"""सोलरॉन होम्स कडून सस्नेह नमस्कार,

प्रिय महोदय/मॅडम,
आपल्या सोलर प्लांटने ({plant_name}) आज ({date_display}) {energy} युनिट्स वीज निर्मिती केली.
आपली अंदाजे बचत ₹{savings:,.0f} झाली आहे.
सोलर पॅनेल्सची वेळेवर स्वच्छता जास्तीत जास्त वीज निर्मितीसाठी आवश्यक आहे.
स्वच्छता उपकरणे किंवा इतर माहितीसाठी आमच्याशी संपर्क साधा.

धन्यवाद,
टीम सोलरॉन"""
    else:
        return f"""Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
Your solar plant ({plant_name}) generated {energy} units today ({date_display}).
You have saved approximately ₹{savings:,.0f}.
Kindly ensure regular cleaning of your plant maximizes your savings.
If you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us at +91 98200 12345.

Thank You,
Team Solaron"""

def format_weekly_whatsapp_statement(
    name: str,
    plant_id: str,
    plant_name: str,
    kwh: float,
    revenue: float = 0.0,
    lang: str = "english"
) -> str:
    lang = (lang or "english").lower()
    energy = round(kwh, 1)
    savings = round(revenue or (kwh * 14.0))

    if lang == "hindi":
        return f"""सोलरॉन होम्स की ओर से नमस्कार,

प्रिय महोदय/मैम,
आपके सोलर प्लांट ({plant_name}) ने इस सप्ताह लगभग {energy} यूनिट बिजली बनाई।
आपने लगभग ₹{savings:,.0f} की बचत की है।
प्लांट की नियमित सफाई बनाए रखें जिससे उत्पादन उत्कृष्ट रहे।
किसी भी सहायता के लिए सोलरॉन केयर से संपर्क करें।

धन्यवाद,
टीम सोलरॉन"""
    elif lang == "marathi":
        return f"""सोलरॉन होम्स कडून सस्नेह नमस्कार,

प्रिय महोदय/मॅडम,
आपल्या सोलर प्लांटने ({plant_name}) या आठवड्यात अंदाजे {energy} युनिट्स वीज निर्माण केली.
आपली अंदाजे बचत ₹{savings:,.0f} झाली आहे.
नियमित स्वच्छतेने आपल्या प्लांटची कार्यक्षमता उच्चतम ठेवा.
अधिक माहितीसाठी आमच्याशी संपर्क साधा.

धन्यवाद,
टीम सोलरॉन"""
    else:
        return f"""Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
Your solar plant ({plant_name}) generated approximately {energy} units this week.
You have saved approximately ₹{savings:,.0f}.
Kindly ensure regular cleaning of your plant maximizes your savings.
If you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us at +91 98200 12345.

Thank You,
Team Solaron"""

def format_yearly_whatsapp_statement(
    name: str,
    plant_id: str,
    plant_name: str,
    kwh: float,
    revenue: float = 0.0,
    year: str = "2026",
    lang: str = "english"
) -> str:
    lang = (lang or "english").lower()
    energy = round(kwh, 1)
    savings = round(revenue or (kwh * 14.0))
    days_powered = max(1, round(kwh / 30.0))

    if lang == "hindi":
        return f"""☀️ *सोलरॉन वार्षिक माइलस्टोन विवरण ({year})* ☀️

प्रिय महोदय/मैम ({name}),
आपके सोलर प्लांट ({plant_name}) ने वर्ष {year} में कुल *{energy:,.0f} यूनिट* बिजली बनाई!
आपने लगभग *₹{savings:,.0f}* की आर्थिक बचत की और ~{days_powered} दिनों की घरेलू बिजली बनाई।
सोलरॉन को अपना सोलर पार्टनर चुनने के लिए धन्यवाद!
वार्षिक रखरखाव (AMC), पैनल सफाई या अन्य सेवा के लिए हमसे संपर्क करें।

धन्यवाद,
टीम सोलरॉन केयर"""
    elif lang == "marathi":
        return f"""☀️ *सोलरॉन वार्षिक कामगिरी अहवाल ({year})* ☀️

प्रिय महोदय/मॅडम ({name}),
आपल्या सोलर प्लांटने ({plant_name}) वर्ष {year} मध्ये तब्बल *{energy:,.0f} युनिट्स* वीज निर्मिती केली!
आपली अंदाजे आर्थिक बचत *₹{savings:,.0f}* झाली आहे (~{days_powered} दिवस घरगुती वीज समतुल्य).
सोलरॉन सोबत भागीदारी केल्याबद्दल धन्यवाद!
वार्षिक देखभाल (AMC) किंवा पॅनेल स्वच्छतेसाठी आमच्याशी संपर्क साधा.

धन्यवाद,
टीम सोलरॉन केयर"""
    else:
        return f"""☀️ *Solaron Annual Milestone Summary ({year})* ☀️

Dear Sir/Madam ({name}),
Your solar plant ({plant_name}) generated *{energy:,.0f} units* in the year {year}.
You have saved approximately *₹{savings:,.0f}* (~{days_powered} days of residential energy equivalent)!
Thank you for choosing Solaron as your solar partner!
For annual maintenance contracts (AMC), panel cleaning, or queries, please reach out to us at +91 98200 12345.

Thank You,
Team Solaron"""

def get_customers(limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = "SELECT id, plant_id, customer_name, phone, email, preferred_lang, opt_in_status FROM customers"
    params = []
    if search:
        sql += " WHERE customer_name LIKE ? OR phone LIKE ? OR plant_id LIKE ?"
        s = f"%{search}%"
        params.extend([s, s, s])
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    df = db.query_df(sql, params, db="crm")
    return df.to_dict(orient="records") if not df.empty else []

def get_customers_audit() -> Dict[str, Any]:
    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM customers")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM customers WHERE phone IS NOT NULL AND trim(phone) != ''")
        with_phone = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM customers WHERE opt_in_status = 'active'")
        active = cur.fetchone()[0]
    return {
        "total": total,
        "with_phone": with_phone,
        "missing_phone": total - with_phone,
        "opted_in": active,
        "opted_out": total - active
    }

def delete_customer(cust_id: int) -> int:
    return db.execute("DELETE FROM customers WHERE id = ?", (cust_id,), db="crm")

def get_all_campaigns() -> List[Dict[str, Any]]:
    df = db.query_df("SELECT * FROM campaign_log ORDER BY id DESC", db="crm")
    return df.to_dict(orient="records") if not df.empty else []

def get_campaign_messages(campaign_id: int) -> List[Dict[str, Any]]:
    sql = """
    SELECT q.id, q.campaign_id, q.customer_id, q.phone, q.message_text, q.language, q.status,
           c.customer_name, c.plant_id
    FROM message_queue q
    LEFT JOIN customers c ON q.customer_id = c.id
    WHERE q.campaign_id = ?
    ORDER BY q.id ASC
    """
    df = db.query_df(sql, [campaign_id], db="crm")
    return df.to_dict(orient="records") if not df.empty else []

def get_yearly_milestones(year: str = "2026") -> List[Dict[str, Any]]:
    cust_df = db.query_df("SELECT id, plant_id, customer_name, phone, preferred_lang, opt_in_status FROM customers", db="crm")
    if cust_df.empty:
        return []
    plants_df = db.query_df("SELECT plant_id, plant_name, source, capacity_kwp FROM plants", db="analytics")
    
    sql = """
    SELECT plant_id, SUM(kwh) as annual_kwh, SUM(revenue_inr) as annual_savings,
           AVG(specific_yield) as avg_yield, MAX(kwh) as max_month_kwh
    FROM monthly_generation
    WHERE month LIKE ?
    GROUP BY plant_id
    """
    gen_df = db.query_df(sql, [f"{year}-%"], db="analytics")
    
    merged = cust_df.merge(plants_df, on="plant_id", how="left").merge(gen_df, on="plant_id", how="left")
    merged["annual_kwh"] = merged["annual_kwh"].fillna(0.0).round(1)
    merged["annual_savings"] = merged["annual_savings"].fillna(merged["annual_kwh"] * 14.0).round(0)
    merged["days_powered"] = (merged["annual_kwh"] / 30.0).round(0).astype(int)
    return merged.to_dict(orient="records")

def upsert_customer(plant_id: str, name: str, phone: str, email: str = "", lang: str = "english", opt_in: str = "active") -> int:
    sql = """
    INSERT INTO customers (plant_id, customer_name, phone, email, preferred_lang, opt_in_status)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(plant_id) DO UPDATE SET
        customer_name = excluded.customer_name,
        phone = excluded.phone,
        email = excluded.email,
        preferred_lang = excluded.preferred_lang,
        opt_in_status = excluded.opt_in_status;
    """
    return db.execute(sql, (plant_id, name, phone, email, lang.lower(), opt_in.lower()), db="crm")

def get_customer_profile(cust_id: int) -> Dict[str, Any]:
    df = db.query_df("SELECT * FROM customers WHERE id = ?", [cust_id], db="crm")
    if df.empty:
        return {}
    cust = df.iloc[0].to_dict()
    pid = cust["plant_id"]

    # Pull generation from analytics DB
    gen_df = db.query_df(
        "SELECT month, kwh, specific_yield, tier, revenue_inr FROM monthly_generation WHERE plant_id = ? ORDER BY month DESC LIMIT 12",
        [pid],
        db="analytics"
    )
    # Pull messages from CRM DB
    msg_df = db.query_df(
        "SELECT id, campaign_id, message_text, status FROM message_queue WHERE customer_id = ? ORDER BY id DESC LIMIT 20",
        [cust_id],
        db="crm"
    )
    cust["monthly_history"] = gen_df.to_dict(orient="records") if not gen_df.empty else []
    cust["message_history"] = msg_df.to_dict(orient="records") if not msg_df.empty else []
    return cust

def prepare_monthly_campaign(month: Optional[str] = None) -> Dict[str, Any]:
    if not month:
        month = datetime.date.today().strftime("%Y-%m")

    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO campaign_log (campaign_name, month, status, total_messages) VALUES (?, ?, 'PENDING', 0)",
            (f"Monthly Statement - {month}", month)
        )
        campaign_id = cur.lastrowid

    # Join customers with monthly_generation
    cust_df = db.query_df("SELECT id, plant_id, customer_name, phone, preferred_lang FROM customers WHERE opt_in_status = 'active'", db="crm")
    if cust_df.empty:
        return {"campaign_id": campaign_id, "queued": 0}

    plants_df = db.query_df(
        "SELECT plant_id, kwh, tier, revenue_inr FROM monthly_generation WHERE month = ?",
        [month],
        db="analytics"
    )
    merged = pd.merge(cust_df, plants_df, on="plant_id", how="inner")
    queue_rows = []

    for _, row in merged.iterrows():
        lang = str(row["preferred_lang"]).lower()
        tmpl_group = TEMPLATES.get(lang, TEMPLATES["english"])
        tmpl = tmpl_group["monthly_summary"]
        msg = tmpl.format(
            name=row["customer_name"],
            plant_id=row["plant_id"],
            kwh=row["kwh"] or 0,
            tier=row["tier"] or "Good",
            revenue=row["revenue_inr"] or 0
        )
        queue_rows.append((campaign_id, row["id"], row["phone"], msg, lang, "PENDING"))

    if queue_rows:
        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.executemany(
                "INSERT INTO message_queue (campaign_id, customer_id, phone, message_text, language, status) VALUES (?, ?, ?, ?, ?, ?)",
                queue_rows
            )
            cur.execute("UPDATE campaign_log SET total_messages = ? WHERE id = ?", (len(queue_rows), campaign_id))

    return {"campaign_id": campaign_id, "queued": len(queue_rows)}

def prepare_weekly_campaign() -> Dict[str, Any]:
    with db.crm_conn() as conn:
        cur = conn.cursor()
        now_str = datetime.date.today().strftime("%Y-%m-%d")
        cur.execute(
            "INSERT INTO campaign_log (campaign_name, month, status, total_messages) VALUES (?, ?, 'PENDING', 0)",
            (f"Weekly Statement - {now_str}", now_str[:7])
        )
        campaign_id = cur.lastrowid

    cust_df = db.query_df("SELECT id, plant_id, customer_name, phone, preferred_lang FROM customers WHERE opt_in_status = 'active'", db="crm")
    if cust_df.empty:
        return {"campaign_id": campaign_id, "queued": 0}

    sql = """
    SELECT plant_id, SUM(kwh) as week_kwh, SUM(revenue_inr) as week_savings
    FROM daily_generation
    WHERE date >= date('now', '-7 days')
    GROUP BY plant_id
    """
    gen_df = db.query_df(sql, db="analytics")
    merged = pd.merge(cust_df, gen_df, on="plant_id", how="inner")
    
    if merged.empty or merged["week_kwh"].sum() <= 0:
        curr_m = datetime.date.today().strftime("%Y-%m")
        m_df = db.query_df("SELECT plant_id, kwh, revenue_inr FROM monthly_generation WHERE month = ?", [curr_m], db="analytics")
        merged = pd.merge(cust_df, m_df, on="plant_id", how="inner")
        merged["week_kwh"] = (merged["kwh"] / 4.33).round(1)
        merged["week_savings"] = (merged["revenue_inr"] / 4.33).round(0)

    queue_rows = []
    plants_df = db.query_df("SELECT plant_id, plant_name FROM plants", db="analytics")
    pname_map = dict(zip(plants_df["plant_id"], plants_df["plant_name"])) if not plants_df.empty else {}

    for _, row in merged.iterrows():
        lang = str(row.get("preferred_lang", "english")).lower()
        pid = str(row["plant_id"])
        pname = pname_map.get(pid, pid)
        msg = format_weekly_whatsapp_statement(
            name=row["customer_name"],
            plant_id=pid,
            plant_name=pname,
            kwh=float(row.get("week_kwh") or 0.0),
            revenue=float(row.get("week_savings") or 0.0),
            lang=lang
        )
        queue_rows.append((campaign_id, row["id"], row["phone"], msg, lang, "PENDING"))

    if queue_rows:
        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.executemany(
                "INSERT INTO message_queue (campaign_id, customer_id, phone, message_text, language, status) VALUES (?, ?, ?, ?, ?, ?)",
                queue_rows
            )
            cur.execute("UPDATE campaign_log SET total_messages = ? WHERE id = ?", (len(queue_rows), campaign_id))

    return {"campaign_id": campaign_id, "queued": len(queue_rows)}

def prepare_yearly_campaign(year: str = "2026") -> Dict[str, Any]:
    with db.crm_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO campaign_log (campaign_name, month, status, total_messages) VALUES (?, ?, 'PENDING', 0)",
            (f"Yearly Milestone Recap - {year}", year)
        )
        campaign_id = cur.lastrowid

    milestones = get_yearly_milestones(year)
    queue_rows = []
    for m in milestones:
        if m.get("opt_in_status") != "active" or not m.get("phone"):
            continue
        msg = format_yearly_whatsapp_statement(
            name=m.get("customer_name") or "Solar Customer",
            plant_id=m.get("plant_id", ""),
            plant_name=m.get("plant_name") or m.get("plant_id", ""),
            kwh=float(m.get("annual_kwh") or 0.0),
            revenue=float(m.get("annual_savings") or 0.0),
            year=year,
            lang=str(m.get("preferred_lang", "english")).lower()
        )
        queue_rows.append((campaign_id, m["id"], m["phone"], msg, m.get("preferred_lang", "english"), "PENDING"))

    if queue_rows:
        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.executemany(
                "INSERT INTO message_queue (campaign_id, customer_id, phone, message_text, language, status) VALUES (?, ?, ?, ?, ?, ?)",
                queue_rows
            )
            cur.execute("UPDATE campaign_log SET total_messages = ? WHERE id = ?", (len(queue_rows), campaign_id))

    return {"campaign_id": campaign_id, "queued": len(queue_rows)}

def get_offline_plants(hours_threshold: int = 4) -> List[Dict[str, Any]]:
    sql = """
    SELECT d.plant_id, p.plant_name, p.source, d.status, d.date, d.live_power_kw
    FROM daily_generation d
    JOIN plants p ON d.plant_id = p.plant_id
    WHERE d.status IN ('offline', 'fault')
    GROUP BY d.plant_id HAVING d.date = max(d.date);
    """
    df = db.query_df(sql, db="analytics")
    return df.to_dict(orient="records") if not df.empty else []

def is_alert_on_cooldown(plant_id: str, alert_type: str, cooldown_hours: int = 24) -> bool:
    sql = """
    SELECT sent_at FROM alert_send_log
    WHERE plant_id = ? AND alert_type = ?
    ORDER BY sent_at DESC LIMIT 1;
    """
    df = db.query_df(sql, [plant_id, alert_type], db="crm")
    if df.empty:
        return False
    last_sent_str = df.iloc[0]["sent_at"]
    try:
        last_sent = datetime.datetime.fromisoformat(last_sent_str)
        elapsed = (datetime.datetime.now() - last_sent).total_seconds() / 3600.0
        return elapsed < cooldown_hours
    except Exception:
        return False

def prepare_offline_alerts(hours: int = 4) -> Dict[str, Any]:
    offline_list = get_offline_plants(hours)
    queued = 0
    now_str = datetime.datetime.now().isoformat()

    for item in offline_list:
        pid = item["plant_id"]
        status = item["status"]
        cooldown = 24 if status == "offline" else 6

        if is_alert_on_cooldown(pid, status, cooldown):
            continue

        # Find customer
        cust_df = db.query_df("SELECT id, customer_name, phone, preferred_lang FROM customers WHERE plant_id = ? AND opt_in_status = 'active'", [pid], db="crm")
        if not cust_df.empty:
            c = cust_df.iloc[0]
            lang = str(c["preferred_lang"]).lower()
            tmpl_group = TEMPLATES.get(lang, TEMPLATES["english"])
            msg = tmpl_group["offline_alert"].format(
                plant_id=pid,
                hours=hours
            )
            with db.crm_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO message_queue (campaign_id, customer_id, phone, message_text, language, status) VALUES (NULL, ?, ?, ?, ?, 'PENDING')",
                    (c["id"], c["phone"], msg, lang)
                )
                cur.execute(
                    "INSERT INTO alert_send_log (plant_id, alert_type, sent_at, cooldown_hours) VALUES (?, ?, ?, ?)",
                    (pid, status, now_str, cooldown)
                )
                queued += 1

    return {"offline_found": len(offline_list), "alerts_queued": queued}
