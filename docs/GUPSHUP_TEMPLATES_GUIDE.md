# Solaron Gupshup WhatsApp Template Registration Guide

> Complete, copy-paste ready reference for registering Meta-compliant WhatsApp Business Templates via the Gupshup WhatsApp Dashboard / Meta Business Manager.
> Configured strictly for **English (`en`)** and **Hindi (`hi`)** (Marathi removed per Solaron operational guidelines).
> All templates are driven directly by **real-time server telemetry collected from Growatt, iSolarCloud, and SuryaLog inverter servers** and stored in `solar_analytics.db` and `crm_data.db`.

---

## ⚙️ Meta Business Manager Settings Summary

| Attribute | Recommended Value | Rationale |
|---|---|---|
| **Category** | `UTILITY` | Rapid Meta approval (<2 mins), lowest per-message pricing, highest delivery rate. |
| **Header** | `None` (plain text) | Maximizes cross-device readability across low-end and high-end smartphones. |
| **Footer** | `Solaron Homes Pvt Ltd` | Official registered enterprise identity. |
| **Button Type** | `Quick Reply` (where specified) | Fast 1-tap customer actions without requiring typing. |
| **Languages Supported** | **English (`en`)**, **Hindi (`hi`)** | Bilingual messaging for Solaron residential & commercial customers. |
| **Variable Format** | `{{1}}`, `{{2}}`, `{{3}}`... | Required by Meta Business Manager; sequential numerical numbering. |

---

## 📋 Master Template Catalog & Trigger Rules

| # | Template Key | Purpose | Trigger Condition | Target Audience | Variables |
|---|---|---|---|---|---|
| **1** | `solaron_monthly_statement` | Monthly Energy & Savings Report | 1st of every month | All active plants | `{{1}}`..`{{5}}` |
| **2** | `solaron_offline_alert` | Initial Disconnection Notice | Daytime generation = 0 or no data > 4 hrs | Newly offline plants | `{{1}}` |
| **3** | `solaron_monsoon_alert` | Pre-Monsoon Preventive Health Check | Yearly (~mid-May) | Fleet-wide (all plants) | `{{1}}` |
| **F1** | `solaron_offline_f1` | L2 Info: Plant Still Offline | Plant still offline 3 days after Message 2 | Offline plants | `{{1}}` |
| **F2** | `solaron_offline_f2` | L3 Action: Check Hardware & Clean Panels | Plant still offline after F1 (Step 2) | Offline plants | `{{1}}` |
| **F3** | `solaron_offline_f3` | L4 Proposal: Offer Technician Visit & Cleaning | Plant still offline after F2 (Step 3) | Offline plants | `{{1}}`, `{{2}}` |
| **F4** | `solaron_offline_f4` | L5 Confirmation: Visit Booked (Reply YES) | Customer replies YES to F3 | Opted-in customers | `{{1}}`..`{{5}}` |
| **F5** | `solaron_offline_f5` | L5 Standby: Recheck in 3 Days (Reply NO) | Customer replies NO to F3 | Deferred customers | `{{1}}` |
| **F6** | `solaron_offline_f6` | L6 Final Escalation: Still Offline + Team Call | Still offline after 3-day recheck | Escalated plants | `{{1}}`, `{{2}}` |

> ⚠️ **State Machine Rule**: Message 2 is the initial offline alert, and F1 to F6 follow it strictly in sequence. The automation engine **must never skip ahead** to F2 or F3 without dispatching F1 first.

---

# 1. MONTHLY STATEMENT (Trigger: 1st of Every Month, Per Plant)

* **Template Name**: `solaron_monthly_statement`
* **Category**: `UTILITY`
* **Footer**: `Solaron Homes Pvt Ltd`
* **Buttons (Quick Reply)**: `CLEANING KIT` | `SUPPORT`
* **Parameter Mapping**:
  * `{{1}}` = `{energy}` (Total units generated in kWh, e.g. `540`)
  * `{{2}}` = `{month_name}` (Month name, e.g. `September` / `सितंबर`)
  * `{{3}}` = `{year}` (Year, e.g. `2026`)
  * `{{4}}` = `{savings}` (Estimated bill savings, strictly computed as `energy * 14`, e.g. `7560`)
  * `{{5}}` = `{phone}` (Support contact number, e.g. `9619455207`)

---

### English (`en`)
```text
Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
Your solar plant generated {{1}} units in {{2}} {{3}}.
You have saved approximately ₹{{4}}.

Kindly ensure regular cleaning of your plant to maximize your savings.
For cleaning equipment like telescopic poles or any other query, contact us at {{5}}

Thank You,
Team Solaron
```
* **Sample Values**: `{{1}}` 540 | `{{2}}` September | `{{3}}` 2026 | `{{4}}` 7560 | `{{5}}` 9619455207

---

### Hindi (`hi`)
```text
सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,

प्रिय महोदय/मैम,
आपके सोलर प्लांट ने {{2}} {{3}} में {{1}} यूनिट बिजली बनाई।
आपने लगभग ₹{{4}} की बचत की है।

कृपया अधिकतम बचत के लिए प्लांट की नियमित सफाई करें।
सफाई उपकरण (टेलीस्कोपिक पोल) या किसी भी प्रश्न के लिए संपर्क करें: {{5}}

धन्यवाद,
टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 540 | `{{2}}` सितंबर | `{{3}}` 2026 | `{{4}}` 7560 | `{{5}}` 9619455207

---

### Bilingual Combined (English + Hindi Official Production Version)
```text
Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
Your solar plant generated {{1}} units in {{2}} {{3}}.
You have saved approximately ₹{{4}}.

Kindly ensure regular cleaning of your plant to maximize your savings.
For cleaning equipment like telescopic poles or any other query, contact us at {{5}}

Thank You,
Team Solaron

सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,

प्रिय महोदय/मैम,
आपके सोलर प्लांट ने {{2}} {{3}} में {{1}} यूनिट बिजली बनाई।
आपने लगभग ₹{{4}} की बचत की है।

कृपया अधिकतम बचत के लिए प्लांट की नियमित सफाई करें।
सफाई उपकरण (टेलीस्कोपिक पोल) या किसी भी प्रश्न के लिए संपर्क करें: {{5}}

धन्यवाद,
टीम सोलरॉन
```

---

# 2. OFFLINE ALERT (Trigger: No Data / Zero Daytime Generation > 4 Hrs)

* **Template Name**: `solaron_offline_alert`
* **Category**: `UTILITY`
* **Footer**: `Solaron Homes Pvt Ltd`
* **Buttons (Quick Reply)**: `REQUEST VISIT` | `RESOLVED`
* **Parameter Mapping**:
  * `{{1}}` = `{phone}` (Support team number, e.g. `9619455207`)

---

### English (`en`)
```text
Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
Your solar plant is offline. Please check once physically: either the plant is not working, the data logger has failed, or the wifi connection is unavailable.
If you want, we will send a representative to check your plant and troubleshoot. We will check all parameters and share a visit report. A cleaning cycle can also be done at additional cost.

For any queries, contact our team at {{1}}

Team Solaron
```
* **Sample Values**: `{{1}}` 9619455207

---

### Hindi (`hi`)
```text
सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,

प्रिय महोदय/मैम,
आपका सोलर प्लांट ऑफ़लाइन है। कृपया एक बार भौतिक रूप से जाँच लें: या तो प्लांट काम नहीं कर रहा, डेटा लॉगर खराब है, या वाईफ़ाई उपलब्ध नहीं है।
यदि आप चाहें तो हम अपने प्रतिनिधि को जाँच और समस्या निवारण के लिए भेजेंगे। हम सभी पैरामीटर जाँचकर रिपोर्ट साझा करेंगे। अतिरिक्त शुल्क पर सफाई भी की जा सकती है।

किसी भी प्रश्न के लिए हमारी टीम को कॉल करें: {{1}}

टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 9619455207

---

### Bilingual Combined (English + Hindi Official Production Version)
```text
Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
Your solar plant is offline. Please check once physically: either the plant is not working, the data logger has failed, or the wifi connection is unavailable.
If you want, we will send a representative to check your plant and troubleshoot. We will check all parameters and share a visit report. A cleaning cycle can also be done at additional cost.

For any queries, contact our team at {{1}}

Team Solaron

सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,

प्रिय महोदय/मैम,
आपका सोलर प्लांट ऑफ़लाइन है। कृपया एक बार भौतिक रूप से जाँच लें: या तो प्लांट काम नहीं कर रहा, डेटा लॉगर खराब है, या वाईफ़ाई उपलब्ध नहीं है।
यदि आप चाहें तो हम अपने प्रतिनिधि को जाँच और समस्या निवारण के लिए भेजेंगे। हम सभी पैरामीटर जाँचकर रिपोर्ट साझा करेंगे। अतिरिक्त शुल्क पर सफाई भी की जा सकती है।

किसी भी प्रश्न के लिए हमारी टीम को कॉल करें: {{1}}

टीम सोलरॉन
```

---

# 3. MONSOON ALERT (Trigger: Yearly, ~Mid-May, All Plants)

* **Template Name**: `solaron_monsoon_alert`
* **Category**: `UTILITY`
* **Footer**: `Solaron Homes Pvt Ltd`
* **Buttons (Quick Reply)**: `SCHEDULE CHECK` | `SUPPORT`
* **Parameter Mapping**:
  * `{{1}}` = `{phone}` (Support team number, e.g. `9619455207`)

---

### English (`en`)
```text
Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
The monsoon season is going to start soon and wind speeds will go up. We strongly recommend a pre-monsoon check-up of your solar plant.
We will check overall plant working and tighten any loose nuts and bolts. Please contact us at {{1}} for a single visit or an annual service contract (AMC).

Thank You,
Team Solaron
```
* **Sample Values**: `{{1}}` 9619455207

---

### Hindi (`hi`)
```text
सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से,

प्रिय महोदय/मैम,
मानसून जल्द शुरू होने वाला है और हवा की गति बढ़ेगी। हम आपके सोलर प्लांट की प्री-मानसून जांच करवाने की दृढ़ता से सलाह देते हैं।
हम प्लांट के कामकाज की जांच करेंगे और ढीले नट-बोल्ट कसेंगे। एक विजिट या वार्षिक सेवा अनुबंध (AMC) के लिए संपर्क करें: {{1}}

धन्यवाद,
टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 9619455207

---

### Bilingual Combined (English + Hindi Official Production Version)
```text
Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
The monsoon season is going to start soon and wind speeds will go up. We strongly recommend a pre-monsoon check-up of your solar plant.
We will check overall plant working and tighten any loose nuts and bolts. Please contact us at {{1}} for a single visit or an annual service contract (AMC).

Thank You,
Team Solaron

सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से,

प्रिय महोदय/मैम,
मानसून जल्द शुरू होने वाला है और हवा की गति बढ़ेगी। हम आपके सोलर प्लांट की प्री-मानसून जांच करवाने की दृढ़ता से सलाह देते हैं।
हम प्लांट के कामकाज की जांच करेंगे और ढीले नट-बोल्ट कसेंगे। एक विजिट या वार्षिक सेवा अनुबंध (AMC) के लिए संपर्क करें: {{1}}

धन्यवाद,
टीम सोलरॉन
```

---

# 4. OFFLINE FOLLOW-UP TREE (6 Levels, Only for Plants Still Offline)

```
[Day 0]  Message 2 (Initial Offline Alert)
   │
   ▼ (Plant still offline after 3 days)
[Day 3]  L2 (STEP 1): F1 (Info — Still Offline for {days} days)
   │
   ▼ (Plant still offline)
[Day 5]  L3 (STEP 2): F2 (Action — Check Hardware + Clean Panels)
   │
   ▼ (Plant still offline)
[Day 7]  L4 (STEP 3): F3 (Offer — Technician Visit ₹{charges} + Cleaning)
   │
   ├── Customer Replies YES ──► L5: F4 (Visit Booked with Date & Technician Info)
   └── Customer Replies NO  ──► L5: F5 (Understood, Wait 3 Days)
                                    │
                                    ▼ (After 3 days)
                                L6: Re-Check
                                    ├── Back Online ──► Close Ticket
                                    └── Still Offline ──► F6 (Final Reminder) + Dedicated Team Call
```

---

## F1 (L2, STEP 1: Info — Still Offline)

* **Template Name**: `solaron_offline_f1`
* **Trigger**: Plant still offline 3 days after Message 2
* **Category**: `UTILITY`
* **Parameter Mapping**:
  * `{{1}}` = `{days}` (Consecutive offline days, e.g. `3`)

### English (`en`)
```text
Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
Your solar plant has been offline for {{1}} days and no generation data is being received. You may be losing savings every day.

Team Solaron
```
* **Sample Values**: `{{1}}` 3

### Hindi (`hi`)
```text
सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,

प्रिय महोदय/मैम,
आपका सोलर प्लांट {{1}} दिनों से ऑफ़लाइन है और कोई डेटा प्राप्त नहीं हो रहा। इससे आपकी बचत का नुकसान हो रहा है।

टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 3

### Bilingual Combined (English + Hindi)
```text
Greetings From Solaron Homes Pvt Ltd,

Dear Sir/Madam,
Your solar plant has been offline for {{1}} days and no generation data is being received. You may be losing savings every day.

Team Solaron

सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,

प्रिय महोदय/मैम,
आपका सोलर प्लांट {{1}} दिनों से ऑफ़लाइन है और कोई डेटा प्राप्त नहीं हो रहा। इससे आपकी बचत का नुकसान हो रहा है।

टीम सोलरॉन
```

---

## F2 (L3, STEP 2: Ask to Check Hardware + Clean Panels)

* **Template Name**: `solaron_offline_f2`
* **Trigger**: Still offline after F1
* **Category**: `UTILITY`
* **Buttons (Quick Reply)**: `DONE` | `NEED HELP`
* **Parameter Mapping**:
  * `{{1}}` = `{phone}` (Support contact, e.g. `9619455207`)

### English (`en`)
```text
Dear Sir/Madam,
Please check: inverter display/green light, wifi router, MCB switch.
Also clean your panels (dust, bird droppings) and remove any shade. Dirty panels reduce generation.
If it is still offline after this, contact us at {{1}}

Team Solaron
```
* **Sample Values**: `{{1}}` 9619455207

### Hindi (`hi`)
```text
प्रिय महोदय/मैम,
कृपया जाँचें: इन्वर्टर डिस्प्ले/हरी लाइट, वाईफ़ाई राउटर, MCB स्विच।
साथ ही पैनलों की सफाई करें (धूल, पक्षियों की बीट) और छाया हटाएं। गंदे पैनल उत्पादन घटाते हैं।
इसके बाद भी ऑफ़लाइन रहे तो संपर्क करें: {{1}}

टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 9619455207

### Bilingual Combined (English + Hindi)
```text
Dear Sir/Madam,
Please check: inverter display/green light, wifi router, MCB switch.
Also clean your panels (dust, bird droppings) and remove any shade. Dirty panels reduce generation.
If it is still offline after this, contact us at {{1}}

Team Solaron

प्रिय महोदय/मैम,
कृपया जाँचें: इन्वर्टर डिस्प्ले/हरी लाइट, वाईफ़ाई राउटर, MCB स्विच।
साथ ही पैनलों की सफाई करें (धूल, पक्षियों की बीट) और छाया हटाएं। गंदे पैनल उत्पादन घटाते हैं।
इसके बाद भी ऑफ़लाइन रहे तो संपर्क करें: {{1}}

टीम सोलरॉन
```

---

## F3 (L4, STEP 3: Offer Technician Visit & Cleaning)

* **Template Name**: `solaron_offline_f3`
* **Trigger**: Still offline after F2
* **Category**: `UTILITY`
* **Buttons (Quick Reply)**: `YES` | `NO`
* **Parameter Mapping**:
  * `{{1}}` = `{charges}` (Visit service charges, e.g. `500`)
  * `{{2}}` = `{phone}` (Contact helpline, e.g. `9619455207`)

### English (`en`)
```text
Dear Sir/Madam,
We can send a technician to inspect and restore your plant. Visit charges: ₹{{1}}. A cleaning cycle can be added at extra cost.
Reply YES to book or NO to wait. Contact: {{2}}

Team Solaron
```
* **Sample Values**: `{{1}}` 500 | `{{2}}` 9619455207

### Hindi (`hi`)
```text
प्रिय महोदय/मैम,
हम आपके प्लांट की जाँच और मरम्मत के लिए तकनीशियन भेज सकते हैं। विजिट शुल्क: ₹{{1}}। अतिरिक्त शुल्क पर सफाई भी जोड़ी जा सकती है।
बुक करने के लिए YES, प्रतीक्षा के लिए NO लिखें। संपर्क: {{2}}

टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 500 | `{{2}}` 9619455207

### Bilingual Combined (English + Hindi)
```text
Dear Sir/Madam,
We can send a technician to inspect and restore your plant. Visit charges: ₹{{1}}. A cleaning cycle can be added at extra cost.
Reply YES to book or NO to wait. Contact: {{2}}

Team Solaron

प्रिय महोदय/मैम,
हम आपके प्लांट की जाँच और मरम्मत के लिए तकनीशियन भेज सकते हैं। विजिट शुल्क: ₹{{1}}। अतिरिक्त शुल्क पर सफाई भी जोड़ी जा सकती है।
बुक करने के लिए YES, प्रतीक्षा के लिए NO लिखें। संपर्क: {{2}}

टीम सोलरॉन
```

---

## F4 (L5-YES: Technician Visit Booked)

* **Template Name**: `solaron_offline_f4`
* **Trigger**: Customer replied YES to F3
* **Category**: `UTILITY`
* **Buttons (Quick Reply)**: `CALL TECHNICIAN` | `SUPPORT`
* **Parameter Mapping**:
  * `{{1}}` = `{visit_date}` (Scheduled date, e.g. `12 Oct 2026` / `12 अक्टूबर 2026`)
  * `{{2}}` = `{time_slot}` (Time slot, e.g. `10:00 AM - 01:00 PM` / `सुबह 10:00 से दोपहर 01:00`)
  * `{{3}}` = `{charges}` (Service charges in ₹, e.g. `500`)
  * `{{4}}` = `{tech_name}` (Certified technician name, e.g. `Sunil Patil`)
  * `{{5}}` = `{tech_phone}` (Technician phone number, e.g. `9822012345`)

### English (`en`)
```text
Thank you. Your technician visit is booked for {{1}}, {{2}}.
Charges: ₹{{3}} (payable after service).
Technician: {{4}}, {{5}}

Team Solaron
```
* **Sample Values**: `{{1}}` 12 Oct 2026 | `{{2}}` 10:00 AM - 01:00 PM | `{{3}}` 500 | `{{4}}` Sunil Patil | `{{5}}` 9822012345

### Hindi (`hi`)
```text
धन्यवाद। आपकी तकनीशियन विजिट {{1}}, {{2}} को बुक हो गई है।
शुल्क: ₹{{3}} (सेवा के बाद देय)।
तकनीशियन: {{4}}, {{5}}

टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 12 अक्टूबर 2026 | `{{2}}` सुबह 10:00 से दोपहर 01:00 | `{{3}}` 500 | `{{4}}` सुनील पाटिल | `{{5}}` 9822012345

### Bilingual Combined (English + Hindi)
```text
Thank you. Your technician visit is booked for {{1}}, {{2}}.
Charges: ₹{{3}} (payable after service).
Technician: {{4}}, {{5}}

Team Solaron

धन्यवाद। आपकी तकनीशियन विजिट {{1}}, {{2}} को बुक हो गई है।
शुल्क: ₹{{3}} (सेवा के बाद देय)।
तकनीशियन: {{4}}, {{5}}

टीम सोलरॉन
```

---

## F5 (L5-NO: Wait 3 Days & Re-evaluate)

* **Template Name**: `solaron_offline_f5`
* **Trigger**: Customer replied NO to F3
* **Category**: `UTILITY`
* **Buttons (Quick Reply)**: `BOOK NOW` | `SUPPORT`
* **Parameter Mapping**:
  * `{{1}}` = `{phone}` (Support contact number, e.g. `9619455207`)

### English (`en`)
```text
Understood. We will check your plant status again in 3 days. To book a visit earlier, reply YES or call {{1}}

Team Solaron
```
* **Sample Values**: `{{1}}` 9619455207

### Hindi (`hi`)
```text
ठीक है। हम 3 दिन बाद आपके प्लांट की स्थिति दोबारा जाँचेंगे। जल्दी विजिट के लिए YES लिखें या कॉल करें: {{1}}

टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 9619455207

### Bilingual Combined (English + Hindi)
```text
Understood. We will check your plant status again in 3 days. To book a visit earlier, reply YES or call {{1}}

Team Solaron

ठीक है। हम 3 दिन बाद आपके प्लांट की स्थिति दोबारा जाँचेंगे। जल्दी विजिट के लिए YES लिखें या कॉल करें: {{1}}

टीम सोलरॉन
```

---

## F6 (L6, Final Escalation: Still Offline + Team Call Scheduled)

* **Template Name**: `solaron_offline_f6`
* **Trigger**: Plant still offline after 3-day recheck; triggers automated ticket for phone call
* **Category**: `UTILITY`
* **Buttons (Quick Reply)**: `CALL NOW` | `BOOK VISIT`
* **Parameter Mapping**:
  * `{{1}}` = `{charges}` (Visit charge, e.g. `500`)
  * `{{2}}` = `{phone}` (Helpline contact, e.g. `9619455207`)

### English (`en`)
```text
Dear Sir/Madam,
Reminder: your solar plant is still offline. Please check and clean your plant, or book a technician visit (₹{{1}}).
Our team will call you shortly. Contact: {{2}}

Team Solaron
```
* **Sample Values**: `{{1}}` 500 | `{{2}}` 9619455207

### Hindi (`hi`)
```text
प्रिय महोदय/मैम,
स्मरण: आपका सोलर प्लांट अभी भी ऑफ़लाइन है। कृपया प्लांट की जाँच व सफाई करें या तकनीशियन विजिट (₹{{1}}) बुक करें।
हमारी टीम जल्द आपको कॉल करेगी। संपर्क: {{2}}

टीम सोलरॉन
```
* **Sample Values**: `{{1}}` 500 | `{{2}}` 9619455207

### Bilingual Combined (English + Hindi)
```text
Dear Sir/Madam,
Reminder: your solar plant is still offline. Please check and clean your plant, or book a technician visit (₹{{1}}).
Our team will call you shortly. Contact: {{2}}

Team Solaron

प्रिय महोदय/मैम,
स्मरण: आपका सोलर प्लांट अभी भी ऑफ़लाइन है। कृपया प्लांट की जाँच व सफाई करें या तकनीशियन विजिट (₹{{1}}) बुक करें।
हमारी टीम जल्द आपको कॉल करेगी। संपर्क: {{2}}

टीम सोलरॉन
```

---

# SECTION 5: Backend Implementation & Gupshup Payload Reference

### 1. Sequential Gupshup Payload Schema
All templates are registered with Meta's sequential variables `{{1}}`, `{{2}}`, `{{3}}`. When sending through the Gupshup API (`services/gupshup.py`), the request payload provides these values in the `params` array:

```json
{
  "channel": "whatsapp",
  "source": "919619455207",
  "destination": "919876543210",
  "src.name": "SolaronHomes",
  "template": {
    "id": "APPROVED_TEMPLATE_UUID",
    "params": [
      "540",
      "September",
      "2026",
      "7560",
      "9619455207"
    ]
  }
}
```

### 2. Operational Rules
* **Sequential Escalation**: F1 through F6 MUST be dispatched sequentially. If an offline customer has not received F1, the engine will never send F2 or F3.
* **Dynamic Support Phone**: Phone numbers are dynamically populated via `{phone}` (`config.settings.support_phone`, defaulting to `9619455207`).
* **Savings Formula**: Monthly savings are strictly calculated as:
  $$\text{Savings (₹)} = \text{round}(\text{energy (kWh)} \times 14.0)$$
* **Gupshup Mode Safety**: During testing, `GUPSHUP_SEND_MODE=test_only` ensures all messages route safely to the verified test number.
