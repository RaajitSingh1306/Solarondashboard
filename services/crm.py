import datetime
import logging
import re
from typing import Any, Dict, List, Optional
import pandas as pd
from config import settings
try:
    from pipeline import db
except ImportError:
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

# --- Solaron Official Message Templates ---
MONTH_NAMES = {
    "english": {
        "01": "January", "02": "February", "03": "March", "04": "April",
        "05": "May", "06": "June", "07": "July", "08": "August",
        "09": "September", "10": "October", "11": "November", "12": "December",
    },
    "hindi": {
        "01": "जनवरी", "02": "फरवरी", "03": "मार्च", "04": "अप्रैल",
        "05": "मई", "06": "जून", "07": "जुलाई", "08": "अगस्त",
        "09": "सितंबर", "10": "अक्टूबर", "11": "नवंबर", "12": "दिसंबर",
    },
    "marathi": {
        "01": "जानेवारी", "02": "फेब्रुवारी", "03": "मार्च", "04": "एप्रिल",
        "05": "मे", "06": "जून", "07": "जुलै", "08": "ऑगस्ट",
        "09": "सप्टेंबर", "10": "ऑक्टोबर", "11": "नोव्हेंबर", "12": "डिसेंबर",
    }
}

MSG_ACTIVE_EN = (
    "Greetings From Solaron Homes Pvt Ltd,\n\n"
    "Dear Sir/Madam,\n"
    "Your solar plant generated {energy} units in the previous month {month_name} {year}!\n"
    "You have saved approximately ₹{savings} (calculated at ₹14/unit).\n\n"
    "Kindly ensure regular cleaning of your plant maximizes your savings.\n"
    "If you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us at 9619455207.\n\n"
    "Thank You,\n"
    "Team Solaron"
)

MSG_ACTIVE_HI = (
    "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,\n\n"
    "प्रिय महोदय/मैम,\n"
    "आपके सोलर प्लांट ने पिछले महीने {month_name} {year} में {energy} यूनिट बिजली बनाई!\n"
    "आपने लगभग ₹{savings} की बचत की है (₹14/यूनिट की दर से)।\n\n"
    "कृपया ध्यान दें कि प्लांट की नियमित सफाई से आपकी बचत अधिकतम होती है।\n"
    "यदि आप टेलीस्कोपिक पोल जैसे सफाई उपकरण खरीदना चाहते हैं, या कोई अन्य प्रश्न है, तो कृपया हमसे ९६१९४५५२०७ पर संपर्क करें।\n\n"
    "धन्यवाद,\n"
    "टीम सोलरॉन"
)

MSG_ACTIVE_MR = MSG_ACTIVE_EN

MSG_OFFLINE_EN = (
    "Greetings From Solaron Homes Pvt Ltd ,\n\n"
    "Dear sir /Mam,\n"
    "your solar plant is offline. please check once physically - either your plant is not working or your data logger has got spoilt or the wifi connection is not available any longer. If you want we will arrange our representative to check your plant and carry out the troubleshooting for your plant .\n"
    "We will check all parameter of your solar plant and share visit report with you. We can also carry out a cleaning cycle at additional cost if you want.\n\n"
    "If any queries , please connect with our team at {support_phone}\n\n"
    "Team solaron"
)

MSG_OFFLINE_HI = (
    "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं\n\n"
    "प्रिय महोदय/मैम,\n"
    "आपका सोलर प्लांट ऑफ़लाइन है। कृपया एक बार भौतिक रूप से जाँच लें - या तो आपका प्लांट काम नहीं कर रहा है या आपका डेटा लॉगर खराब हो गया है या वाईफ़ाई कनेक्शन अब उपलब्ध नहीं है। यदि आप चाहें तो हम आपके प्लांट की जाँच करने और आपके प्लांट के लिए समस्या निवारण करने के लिए अपने प्रतिनिधि की व्यवस्था करेंगे।\n"
    "हम आपके सोलर प्लांट के सभी पैरामीटर की जाँच करेंगे और आपको एक रिपोर्ट साझा करेंगे। यदि आप चाहें तो हम अतिरिक्त लागत पर सफाई चक्र भी चला सकते हैं।\n\n"
    "यदि कोई प्रश्न हैं, तो कृपया हमारी टीम को कॉल कीजिए {support_phone}\n\n"
    "टीम सोलरॉन"
)

MSG_OFFLINE_DEFAULT = (
    "Greetings From Solaron Homes Pvt Ltd ,\n\n"
    "Dear sir /Mam,\n"
    "your solar plant is offline. please check once physically - either your plant is not working or your data logger has got spoilt or the wifi connection is not available any longer. If you want we will arrange our representative to check your plant and carry out the troubleshooting for your plant .\n"
    "We will check all parameter of your solar plant and share visit report with you. We can also carry out a cleaning cycle at additional cost if you want.\n\n"
    "If any queries , please connect with our team at {support_phone}\n\n"
    "Team solaron,\n\n"
    "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं\n\n"
    "प्रिय महोदय/मैम,\n"
    "आपका सोलर प्लांट ऑफ़लाइन है। कृपया एक बार भौतिक रूप से जाँच लें - या तो आपका प्लांट काम नहीं कर रहा है या आपका डेटा लॉगर खराब हो गया है या वाईफ़ाई कनेक्शन अब उपलब्ध नहीं है। यदि आप चाहें तो हम आपके प्लांट की जाँच करने और आपके प्लांट के लिए समस्या निवारण करने के लिए अपने प्रतिनिधि की व्यवस्था करेंगे।\n"
    "हम आपके सोलर प्लांट के सभी पैरामीटर की जाँच करेंगे और आपको एक रिपोर्ट साझा करेंगे। यदि आप चाहें तो हम अतिरिक्त लागत पर सफाई चक्र भी चला सकते हैं।\n\n"
    "यदि कोई प्रश्न हैं, तो कृपया हमारी टीम को कॉल कीजिए {support_phone}\n\n"
    "टीम सोलरॉन"
)

MSG_OFFLINE_MR = MSG_OFFLINE_EN

MSG_MONSOON_EN = (
    "from Solaron Homes Pvt Ltd ,\n\n"
    "Dear Sir/Madam,\n"
    "The monsoon season is going to start soon and this will result in wind speed going up. We strongly recommend that you’ll carry out the pre monsoon check up for your solar plants. As part of the pre monsoon check up we shall check the overall plant working and also tighten any loose nuts and bolts. Please contact us for a single visit or for the annual service contracts.\n\n"
    "Thank You\n"
    "Team Solaron"
)

MSG_MONSOON_HI = (
    "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से,\n\n"
    "प्रिय महोदय/मैम,\n"
    "मानसून का मौसम जल्द ही शुरू होने वाला है और इसके कारण हवा की गति बढ़ जाएगी। हम दृढ़ता से अनुशंसा करते हैं कि आप अपने सोलर प्लांट की प्री-मानसून जांच अवश्य करवाएं। प्री-मानसून जांच के हिस्से के रूप में हम प्लांट के समग्र कामकाज की जांच करेंगे और किसी भी ढीले नट-बोल्ट को कसेंगे। कृपया एक विजिट या वार्षिक सेवा अनुबंध (AMC) के लिए हमसे संपर्क करें।\n\n"
    "धन्यवाद,\n"
    "टीम सोलरॉन"
)

MSG_MONSOON_MR = MSG_MONSOON_EN

MSG_DAILY_EN = (
    "Greetings From Solaron Homes Pvt Ltd,\n\n"
    "Dear Sir/Madam,\n"
    "Your solar plant generated {energy} units today ({date}).\n"
    "You have saved approximately ₹{savings}.\n"
    "Kindly ensure regular cleaning of your plant maximizes your savings.\n"
    "If you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us.\n\n"
    "Thank You,\n"
    "Team Solaron"
)

MSG_DAILY_HI = (
    "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,\n\n"
    "प्रिय महोदय/मैम,\n"
    "आपके सोलर प्लांट ने आज ({date}) {energy} यूनिट बिजली बनाई।\n"
    "आपने लगभग ₹{savings} की बचत की है।\n"
    "कृपया ध्यान दें कि प्लांट की नियमित सफाई से आपकी बचत अधिकतम होती है।\n"
    "यदि आप टेलीस्कोपिक पोल जैसे सफाई उपकरण खरीदना चाहते हैं, या कोई अन्य प्रश्न है, तो कृपया हमसे संपर्क करें।\n\n"
    "धन्यवाद,\n"
    "टीम सोलरॉन"
)

MSG_DAILY_MR = (
    "सोलरॉन होम्स प्रायव्हेट लिमिटेड कडून सस्नेह नमस्कार,\n\n"
    "प्रिय महोदय/मॅडम,\n"
    "आपल्या सोलर प्लांटने आज ({date}) {energy} युनिट्स वीज निर्मिती केली.\n"
    "आपली अंदाजे बचत ₹{savings} झाली आहे.\n"
    "कृपया लक्षात ठेवा की प्लांटची नियमित स्वच्छता आपल्या बचतीत वाढ करते.\n"
    "आपण टेलिस्कोपिक पोलसारखी स्वच्छता उपकरणे खरेदी करू इच्छित असल्यास, किंवा इतर कोणतीही शंका असल्यास, कृपया आमच्याशी संपर्क साधा.\n\n"
    "धन्यवाद,\n"
    "टीम सोलरॉन"
)

MSG_WEEKLY_EN = (
    "Greetings From Solaron Homes Pvt Ltd,\n\n"
    "Dear Sir/Madam,\n"
    "Your solar plant generated approximately {energy} units this week.\n"
    "You have saved approximately ₹{savings}.\n"
    "Kindly ensure regular cleaning of your plant maximizes your savings.\n"
    "If you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us.\n\n"
    "Thank You,\n"
    "Team Solaron"
)

MSG_WEEKLY_HI = (
    "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,\n\n"
    "प्रिय महोदय/मैम,\n"
    "आपके सोलर प्लांट ने इस सप्ताह लगभग {energy} यूनिट बिजली बनाई।\n"
    "आपने लगभग ₹{savings} की बचत की है।\n"
    "कृपया ध्यान दें कि प्लांट की नियमित सफाई से आपकी बचत अधिकतम होती है।\n"
    "यदि आप टेलीस्कोपिक पोल जैसे सफाई उपकरण खरीदना चाहते हैं, या कोई अन्य प्रश्न है, तो कृपया हमसे संपर्क करें।\n\n"
    "धन्यवाद,\n"
    "टीम सोलरॉन"
)

MSG_WEEKLY_MR = (
    "सोलरॉन होम्स प्रायव्हेट लिमिटेड कडून सस्नेह नमस्कार,\n\n"
    "प्रिय महोदय/मॅडम,\n"
    "आपल्या सोलर प्लांटने या आठवड्यात अंदाजे {energy} युनिट्स वीज निर्माण केली.\n"
    "आपली अंदाजे बचत ₹{savings} झाली आहे.\n"
    "कृपया लक्षात ठेवा की प्लांटची नियमित स्वच्छता आपल्या बचतीत वाढ करते.\n"
    "आपण टेलिस्कोपिक पोलसारखी स्वच्छता उपकरणे खरेदी करू इच्छित असल्यास, किंवा इतर कोणतीही शंका असल्यास, कृपया आमच्याशी संपर्क साधा.\n\n"
    "धन्यवाद,\n"
    "टीम सोलरॉन"
)

MSG_YEARLY_EN = (
    "Greetings From Solaron Homes Pvt Ltd,\n\n"
    "Dear Sir/Madam,\n"
    "Your solar plant generated {energy} units in the year {year}.\n"
    "You have saved approximately ₹{savings}.\n"
    "Thank you for choosing Solaron as your solar partner!\n"
    "For annual maintenance contracts, panel cleaning, or queries, please reach out to us.\n\n"
    "Thank You,\n"
    "Team Solaron"
)

MSG_YEARLY_HI = (
    "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,\n\n"
    "प्रिय महोदय/मैम,\n"
    "आपके सोलर प्लांट ने वर्ष {year} में कुल {energy} यूनिट बिजली बनाई।\n"
    "आपने लगभग ₹{savings} की बचत की है।\n"
    "सोलरॉन को अपना सोलर पार्टनर चुनने के लिए धन्यवाद!\n"
    "वार्षिक रखरखाव (AMC), पैनल सफाई या अन्य सेवा के लिए हमसे संपर्क करें।\n\n"
    "धन्यवाद,\n"
    "टीम सोलरॉन"
)

MSG_YEARLY_MR = (
    "सोलरॉन होम्स प्रायव्हेट लिमिटेड कडून सस्नेह नमस्कार,\n\n"
    "प्रिय महोदय/मॅडम,\n"
    "आपल्या सोलर प्लांटने वर्ष {year} मध्ये एकूण {energy} युनिट्स वीज निर्मिती केली.\n"
    "आपली अंदाजे बचत ₹{savings} झाली आहे.\n"
    "सोलरॉन सोबत भागीदारी केल्याबद्दल धन्यवाद!\n"
    "वार्षिक देखभाल (AMC), पॅनेल स्वच्छता किंवा चौकशीसाठी आमच्याशी संपर्क साधा.\n\n"
    "धन्यवाद,\n"
    "टीम सोलरॉन"
)

def _resolve_lang(lang: str) -> str:
    l = (lang or "english").lower().strip()
    if "mr" in l or "marathi" in l:
        return "marathi"
    elif "hi" in l or "hindi" in l:
        return "hindi"
    return "english"

def format_rich_whatsapp_statement(
    name: str,
    plant_id: str,
    plant_name: str,
    kwh: float,
    revenue: float,
    tier: str = "Good",
    lang: str = "english",
    month: str = "2026-09"
) -> str:
    resolved_lang = _resolve_lang(lang)
    energy_str = f"{kwh:,.1f}" if (kwh % 1 != 0) else f"{round(kwh):,}"
    savings_str = f"{round(revenue):,}" if revenue else f"{round(kwh * 14.0):,}"

    parts = month.split("-") if month and "-" in month else ["2026", "09"]
    yr = parts[0]
    m_num = parts[1] if len(parts) > 1 else "09"
    m_name_en = MONTH_NAMES["english"].get(m_num, "September")

    if resolved_lang == "marathi":
        m_name = MONTH_NAMES["marathi"].get(m_num, m_name_en)
        return MSG_ACTIVE_MR.format(
            energy=energy_str,
            month_name=m_name,
            year=yr,
            savings=savings_str
        )
    elif resolved_lang == "hindi":
        m_name = MONTH_NAMES["hindi"].get(m_num, m_name_en)
        return MSG_ACTIVE_HI.format(
            energy=energy_str,
            month_name=m_name,
            year=yr,
            savings=savings_str
        )
    else:
        return MSG_ACTIVE_EN.format(
            energy=energy_str,
            month_name=m_name_en,
            year=yr,
            savings=savings_str
        )

def format_offline_whatsapp_message(
    name: str = "",
    plant_id: str = "",
    plant_name: str = "",
    support_phone: str = "",
    lang: str = "english"
) -> str:
    resolved_lang = _resolve_lang(lang)
    phone = support_phone or getattr(settings, "support_phone", "") or "+91 00000 00000"
    if "bilingual" in (lang or "").lower():
        return MSG_OFFLINE_DEFAULT.format(support_phone=phone)
    if resolved_lang == "marathi":
        return MSG_OFFLINE_MR.format(support_phone=phone)
    elif resolved_lang == "hindi":
        return MSG_OFFLINE_HI.format(support_phone=phone)
    else:
        return MSG_OFFLINE_EN.format(support_phone=phone)


def build_gupshup_monthly_statement_params(
    customer_name: str,
    plant_name: str,
    capacity_kwp: float,
    month: str,
    kwh: float,
    revenue_inr: float,
    yield_per_day: Optional[float] = None,
    tier: str = "Good",
    lang: str = "english",
) -> List[str]:
    """
    Builds the exact sequential parameters list [{{1}}, {{2}}, ... {{8}}]
    for Meta Gupshup template 'solaron_monthly_statement'.
    """
    resolved_lang = _resolve_lang(lang)
    cap = f"{capacity_kwp:.1f} kWp" if capacity_kwp else "5.0 kWp"

    parts = month.split("-") if month and "-" in month else ["2026", "09"]
    yr = parts[0]
    m_num = parts[1] if len(parts) > 1 else "09"
    m_name = MONTH_NAMES.get(resolved_lang, MONTH_NAMES["english"]).get(m_num, "September")
    period_str = f"{m_name} {yr}"

    energy_str = f"{kwh:,.1f}" if (kwh % 1 != 0) else f"{round(kwh):,}"
    savings_str = f"{round(revenue_inr or (kwh * 14.0)):,}"

    if yield_per_day is not None and yield_per_day > 0:
        ypd = f"{yield_per_day:.2f}"
    else:
        denom = (capacity_kwp or 5.0) * 30.0
        ypd = f"{(kwh / denom):.2f}" if denom > 0 else "3.6"

    if resolved_lang == "marathi":
        yield_str = f"{ypd} युनिट/kWp/दिवस"
        status_str = f"{tier} (योग्य कार्यक्षमता)"
    elif resolved_lang == "hindi":
        yield_str = f"{ypd} यूनिट/kWp/दिन"
        status_str = f"{tier} (सक्रिय स्थिति)"
    else:
        yield_str = f"{ypd} units/kWp/day"
        status_str = f"{tier} (Optimal Performance)"

    return [
        str(customer_name or "Solar Customer"),
        str(plant_name or "Solar Rooftop"),
        cap,
        period_str,
        energy_str,
        savings_str,
        yield_str,
        status_str,
    ]


def build_gupshup_offline_alert_params(
    customer_name: str,
    plant_name: str,
    inverter_model: str,
    last_log_time: str,
    hours_offline: int = 4,
    support_phone: str = "",
    lang: str = "english",
) -> List[str]:
    """
    Builds the exact sequential parameters list [{{1}}, {{2}}, ... {{6}}]
    for Meta Gupshup template 'solaron_offline_alert'.
    """
    resolved_lang = _resolve_lang(lang)
    phone = support_phone or getattr(settings, "support_phone", "") or "+91 96194 55207"

    if resolved_lang == "marathi":
        dur_str = f"{hours_offline} तास"
    elif resolved_lang == "hindi":
        dur_str = f"{hours_offline} घंटे"
    else:
        dur_str = f"{hours_offline} hours"

    return [
        str(customer_name or "Solar Customer"),
        str(plant_name or "Solar Rooftop"),
        str(inverter_model or "Solar Inverter"),
        str(last_log_time or "Recently"),
        dur_str,
        phone,
    ]

def format_monsoon_whatsapp_message(
    support_phone: str = "",
    lang: str = "english"
) -> str:
    resolved_lang = _resolve_lang(lang)
    if resolved_lang == "marathi":
        return MSG_MONSOON_MR
    elif resolved_lang == "hindi":
        return MSG_MONSOON_HI
    return MSG_MONSOON_EN

def format_daily_whatsapp_statement(
    name: str,
    plant_id: str,
    plant_name: str,
    kwh: float,
    revenue: float = 0.0,
    date_str: str = "",
    lang: str = "english"
) -> str:
    resolved_lang = _resolve_lang(lang)
    date_display = date_str or datetime.date.today().strftime("%d %b %Y")
    energy_str = f"{kwh:,.1f}" if (kwh % 1 != 0) else f"{round(kwh):,}"
    savings_str = f"{round(revenue or (kwh * 14.0)):,}"

    if resolved_lang == "marathi":
        return MSG_DAILY_MR.format(energy=energy_str, date=date_display, savings=savings_str)
    elif resolved_lang == "hindi":
        return MSG_DAILY_HI.format(energy=energy_str, date=date_display, savings=savings_str)
    else:
        return MSG_DAILY_EN.format(energy=energy_str, date=date_display, savings=savings_str)

def format_weekly_whatsapp_statement(
    name: str,
    plant_id: str,
    plant_name: str,
    kwh: float,
    revenue: float = 0.0,
    lang: str = "english"
) -> str:
    resolved_lang = _resolve_lang(lang)
    energy_str = f"{kwh:,.1f}" if (kwh % 1 != 0) else f"{round(kwh):,}"
    savings_str = f"{round(revenue or (kwh * 14.0)):,}"

    if resolved_lang == "marathi":
        return MSG_WEEKLY_MR.format(energy=energy_str, savings=savings_str)
    elif resolved_lang == "hindi":
        return MSG_WEEKLY_HI.format(energy=energy_str, savings=savings_str)
    else:
        return MSG_WEEKLY_EN.format(energy=energy_str, savings=savings_str)

def format_yearly_whatsapp_statement(
    name: str,
    plant_id: str,
    plant_name: str,
    kwh: float,
    revenue: float = 0.0,
    year: str = "2026",
    lang: str = "english"
) -> str:
    resolved_lang = _resolve_lang(lang)
    energy_str = f"{kwh:,.1f}" if (kwh % 1 != 0) else f"{round(kwh):,}"
    savings_str = f"{round(revenue or (kwh * 14.0)):,}"

    if resolved_lang == "marathi":
        return MSG_YEARLY_MR.format(energy=energy_str, year=year, savings=savings_str)
    elif resolved_lang == "hindi":
        return MSG_YEARLY_HI.format(energy=energy_str, year=year, savings=savings_str)
    else:
        return MSG_YEARLY_EN.format(energy=energy_str, year=year, savings=savings_str)

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

def normalize_phone(phone: Any) -> Optional[str]:
    """
    Normalizes phone string:
    - Strips '.0' float artifact (e.g. '917020188095.0' -> '917020188095')
    - Strips '+' symbol and all non-digits
    - Prepends country code (default '91' for India) if missing
    - Guarantees return value has country code as prefix and NO '+' symbol
    """
    if phone is None:
        return None
    if isinstance(phone, float) and (np.isnan(phone) or np.isneginf(phone) or np.isposinf(phone)):
        return None
    s = str(phone).strip()
    if s.lower() in ("nan", "none", "null", "", "—", "-", "undefined"):
        return None
    if s.endswith(".0"):
        s = s[:-2]
    # Remove '+' symbol explicitly and any other non-digit characters
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None

    # If 10 digits starting with 6-9 (Indian standard mobile) -> prepend '91'
    if len(digits) == 10 and digits[0] in "6789":
        return f"91{digits}"
    # If 10 digits generally -> prepend '91'
    elif len(digits) == 10:
        return f"91{digits}"
    # If 11 digits starting with 0 -> replace '0' with '91'
    elif len(digits) == 11 and digits.startswith("0"):
        return f"91{digits[1:]}"
    # If 12 digits starting with 91 -> valid Indian number with country code, no '+'
    elif len(digits) == 12 and digits.startswith("91"):
        return digits
    # International number already containing country code (>10 digits, max 15 digits)
    elif 10 <= len(digits) <= 15:
        return digits
    return None

def upsert_customer(plant_id: str, name: str, phone: str, email: str = "", lang: str = "english", opt_in: str = "active") -> int:
    clean_phone = normalize_phone(phone)
    if not clean_phone:
        raise ValueError("“Phone” is mandatory and must have country code prefix with no '+' symbol.")
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
    return db.execute(sql, (plant_id, name, clean_phone, email, lang.lower(), opt_in.lower()), db="crm")

def find_phone_column(columns: List[str]) -> Optional[str]:
    """Finds the phone column from list of column names, ensuring case-insensitivity and common headers."""
    for col in columns:
        c_norm = str(col).strip().lower().replace(" ", "_").replace("-", "_")
        if c_norm in ("phone", "phone_number", "phonenumber", "mobile", "mobile_number", "mobilenumber", "contact", "contact_number", "phone_no") or c_norm.startswith("phone"):
            return col
    return None

def import_customers_from_df(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Imports customers from DataFrame with mandatory Phone column validation and normalization.
    Requirements:
    1. “Phone” column is mandatory.
    2. Phone number should have country code as prefix and no ‘+’ symbol.
    """
    phone_col = find_phone_column(list(df.columns))
    if not phone_col:
        raise ValueError("“Phone” column is mandatory.")

    plant_col = None
    for col in df.columns:
        c_norm = str(col).strip().lower().replace(" ", "_").replace("-", "_")
        if c_norm in ("plant_id", "plantid", "plant", "serial", "plant_serial") or "plant" in c_norm:
            plant_col = col
            break

    name_col = None
    for col in df.columns:
        c_norm = str(col).strip().lower().replace(" ", "_").replace("-", "_")
        if c_norm in ("customer_name", "customer", "name", "client_name", "owner"):
            name_col = col
            break

    email_col = next((c for c in df.columns if "email" in str(c).lower()), None)
    lang_col = next((c for c in df.columns if "lang" in str(c).lower()), None)
    opt_col = next((c for c in df.columns if "opt" in str(c).lower()), None)

    imported = 0
    skipped = 0
    errors: List[str] = []

    for idx, row in df.iterrows():
        raw_phone = row.get(phone_col)
        if pd.isna(raw_phone) or not str(raw_phone).strip() or str(raw_phone).strip().lower() in ("nan", "none", "null", "—"):
            skipped += 1
            errors.append(f"Row {idx+1}: Missing mandatory phone number.")
            continue

        clean_phone = normalize_phone(raw_phone)
        if not clean_phone:
            skipped += 1
            errors.append(f"Row {idx+1}: Invalid phone '{raw_phone}'. Phone number should have country code as prefix and no '+' symbol.")
            continue

        pid = row.get(plant_col) if plant_col else row.get("plant_id")
        if pd.isna(pid) or not str(pid).strip():
            pid = f"plant_{clean_phone}"

        name = row.get(name_col) if name_col else row.get("customer_name")
        c_name = str(name).strip() if (pd.notna(name) and str(name).strip()) else "Solar Customer"
        email = str(row.get(email_col, "")).strip() if (email_col and pd.notna(row.get(email_col))) else ""
        lang = str(row.get(lang_col, "english")).lower().strip() if (lang_col and pd.notna(row.get(lang_col))) else "english"
        opt_in = str(row.get(opt_col, "active")).lower().strip() if (opt_col and pd.notna(row.get(opt_col))) else "active"

        upsert_customer(
            plant_id=str(pid),
            name=c_name,
            phone=clean_phone,
            email=email,
            lang=lang,
            opt_in=opt_in,
        )
        imported += 1

    return {
        "status": "success",
        "imported": imported,
        "total_rows": len(df),
        "skipped": skipped,
        "errors": errors[:10] if errors else [],
    }

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

    plants_meta = db.query_df("SELECT plant_id, plant_name FROM plants", db="analytics")
    pname_map = dict(zip(plants_meta["plant_id"], plants_meta["plant_name"])) if not plants_meta.empty else {}

    for _, row in merged.iterrows():
        lang = str(row["preferred_lang"]).lower()
        pid = str(row["plant_id"])
        msg = format_rich_whatsapp_statement(
            name=str(row.get("customer_name") or "Solar Customer"),
            plant_id=pid,
            plant_name=pname_map.get(pid, pid),
            kwh=float(row.get("kwh") or 0.0),
            revenue=float(row.get("revenue_inr") or 0.0),
            tier=str(row.get("tier") or "Good"),
            lang=lang,
            month=month
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

def prepare_monsoon_campaign() -> Dict[str, Any]:
    with db.crm_conn() as conn:
        cur = conn.cursor()
        now_str = datetime.date.today().strftime("%Y-%m-%d")
        cur.execute(
            "INSERT INTO campaign_log (campaign_name, month, status, total_messages) VALUES (?, ?, 'PENDING', 0)",
            (f"Monsoon Alert - {now_str}", now_str[:7])
        )
        campaign_id = cur.lastrowid

    cust_df = db.query_df("SELECT id, plant_id, customer_name, phone, preferred_lang FROM customers WHERE opt_in_status = 'active' AND phone IS NOT NULL AND trim(phone) != ''", db="crm")
    if cust_df.empty:
        return {"campaign_id": campaign_id, "queued": 0}

    queue_rows = []
    for _, row in cust_df.iterrows():
        lang = str(row.get("preferred_lang", "english")).lower()
        msg = format_monsoon_whatsapp_message(support_phone=settings.support_phone, lang=lang)
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
            msg = format_offline_whatsapp_message(
                name=c["customer_name"],
                plant_id=pid,
                support_phone=getattr(settings, "support_phone", "") or "+91 00000 00000",
                lang=lang
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
