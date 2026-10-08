"""
Solaron Escalation Message Templates.

Provides multi-lingual message templates (English, Hindi, Marathi) for the
6-category x 6-level escalation engine.
11 Gupshup WhatsApp templates with variable interpolation.
"""

from typing import Any, Dict, List, Optional

# Template Definitions for Gupshup WhatsApp Template Registration
ESCALATION_TEMPLATES: Dict[str, Dict[str, str]] = {
    # 1. solaron_active: Happy-path monthly performance summary
    "solaron_active": {
        "english": (
            "Greetings From Solaron Homes Pvt Ltd,\n\n"
            "Dear {name},\n"
            "Your solar plant ({plant_id}) generated {energy} units in {month}!\n"
            "You have saved approximately ₹{savings}.\n\n"
            "Kindly ensure regular cleaning of your plant to maximize your savings.\n"
            "If you need cleaning equipment like telescopic poles, reply 'CLEAN' or contact us.\n\n"
            "Thank You,\n"
            "Team Solaron"
        ),
        "hindi": (
            "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से शुभकामनाएं,\n\n"
            "प्रिय {name},\n"
            "आपके सोलर प्लांट ({plant_id}) ने {month} में {energy} यूनिट बिजली बनाई!\n"
            "आपने लगभग ₹{savings} की अनुमानित बचत की है।\n\n"
            "कृपया प्लांट की नियमित सफाई बनाए रखें ताकि अधिकतम बचत मिले।\n"
            "यदि आप टेलिस्कोपिक पोल जैसे सफाई उपकरण खरीदना चाहते हैं, तो 'CLEAN' लिखकर भेजें।\n\n"
            "धन्यवाद,\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "सोलरॉन होम्स प्रायव्हेट लिमिटेड कडून सस्नेह नमस्कार,\n\n"
            "प्रिय {name},\n"
            "आपल्या सोलर प्लांटने ({plant_id}) {month} मध्ये {energy} युनिट्स वीज निर्मिती केली!\n"
            "आपली अंदाजे बचत ₹{savings} झाली आहे.\n\n"
            "नियमितपणे पॅनेल्स स्वच्छ ठेवल्यास जास्तीत जास्त वीज निर्मिती होईल.\n"
            "टेलिस्कोपिक पोलसारखी स्वच्छता साधने हवी असल्यास 'CLEAN' लिहून पाठवा.\n\n"
            "धन्यवाद,\n"
            "टीम सोलरॉन"
        ),
    },

    # 2. solaron_average: 70% <= ratio < 90%
    "solaron_average": {
        "english": (
            "Greetings From Solaron Homes Pvt Ltd,\n\n"
            "Dear {name},\n"
            "Your solar plant ({plant_id}) generated {energy} units recently.\n"
            "This is about {ratio}% of its expected baseline ({expected} units).\n"
            "A slight dip in generation has been detected.\n\n"
            "Please check for:\n"
            "• Dust or dirt accumulation on panels\n"
            "• Bird droppings or debris\n"
            "• Tree branches casting shadow\n\n"
            "If you would like a technician to inspect, reply YES to schedule a visit or NO to wait.\n\n"
            "Thank You,\n"
            "Team Solaron"
        ),
        "hindi": (
            "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से नमस्कार,\n\n"
            "प्रिय {name},\n"
            "आपके सोलर प्लांट ({plant_id}) ने हाल ही में {energy} यूनिट बिजली बनाई है।\n"
            "यह अपेक्षित क्षमता ({expected} यूनिट) का लगभग {ratio}% है।\n"
            "उत्पादन में मामूली गिरावट दर्ज की गई है।\n\n"
            "कृपया निम्न की जांच करें:\n"
            "• सोलर पैनलों पर धूल या मिट्टी\n"
            "• पक्षियों की बीट या कचरा\n"
            "• पेड़ों की छाया\n\n"
            "यदि आप तकनीशियन जांच चाहते हैं, तो YES लिखकर भेजें अन्यथा प्रतीक्षा के लिए NO लिखें।\n\n"
            "धन्यवाद,\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "सोलरॉन होम्स प्रायव्हेट लिमिटेड कडून सस्नेह नमस्कार,\n\n"
            "प्रिय {name},\n"
            "आपल्या सोलर प्लांटने ({plant_id}) नुकतीच {energy} युनिट्स वीज निर्माण केली आहे.\n"
            "हे अपेक्षित क्षमतेच्या ({expected} युनिट्स) सुमारे {ratio}% आहे.\n"
            "निर्मितीमध्ये थोडी घट दिसून आली आहे.\n\n"
            "कृपया खालील बाबी तपासा:\n"
            "• पॅनेलवरील धूळ किंवा माती\n"
            "• पक्ष्यांची विष्ठा किंवा कचरा\n"
            "• झाडांची सावली\n\n"
            "तंत्रज्ञांची तपासणी हवी असल्यास YES पाठवा, किंवा प्रतीक्षा करण्यासाठी NO पाठवा.\n\n"
            "धन्यवाद,\n"
            "टीम सोलरॉन"
        ),
    },

    # 3. solaron_critical_perf: ratio < 70%
    "solaron_critical_perf": {
        "english": (
            "⚠️ Attention — Solaron Homes Pvt Ltd\n\n"
            "Dear {name},\n"
            "Your solar plant ({plant_id}) generated {energy} units, which is only {ratio}% of its baseline ({expected} units).\n"
            "Performance is significantly below expected standards.\n\n"
            "Recommended checks:\n"
            "• Inverter display indicator lights\n"
            "• AC/DC MCB switch positions\n"
            "• Heavy panel soiling or severe shading\n\n"
            "We strongly recommend a technician visit. Reply YES to schedule inspection or NO to review later.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "⚠️ महत्वपूर्ण सूचना — सोलरॉन होम्स प्राइवेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपके सोलर प्लांट ({plant_id}) ने {energy} यूनिट बनाई है, जो बेसलाइन ({expected} यूनिट) का केवल {ratio}% है।\n"
            "प्रदर्शन अपेक्षित स्तर से काफी कम है।\n\n"
            "कृपया जांचें:\n"
            "• इन्वर्टर डिस्प्ले की लाइटें\n"
            "• AC/DC स्विच चालू हैं या नहीं\n"
            "• पैनलों पर अत्यधिक गंदगी या भारी छाया\n\n"
            "हम तकनीशियन निरीक्षण की सलाह देते हैं। विजिट तय करने के लिए YES लिखें या बाद में देखने के लिए NO लिखें।\n\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "⚠️ महत्त्वाची सूचना — सोलरॉन होम्स प्रायव्हेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपल्या सोलर प्लांटने ({plant_id}) {energy} युनिट्स निर्माण केले, जे बेसलाइनच्या ({expected} युनिट्स) फक्त {ratio}% आहे.\n"
            "उत्पादन अपेक्षित प्रमाणापेक्षा खूपच कमी आहे.\n\n"
            "कृपया तपासा:\n"
            "• इन्व्हर्टर डिस्प्लेवरील लाइट्स\n"
            "• AC/DC स्विच चालू आहेत का\n"
            "• पॅनेलवर जास्त घाण किंवा तीव्र सावली\n\n"
            "आम्ही तंत्रज्ञांच्या तपासणीची शिफारस करतो. व्हिजिट निश्चित करण्यासाठी YES पाठवा किंवा नंतर पाहण्यासाठी NO पाठवा.\n\n"
            "टीम सोलरॉन"
        ),
    },

    # 4. solaron_offline: Plant offline
    "solaron_offline": {
        "english": (
            "⚠️ Offline Alert — Solaron Homes Pvt Ltd\n\n"
            "Dear {name},\n"
            "Your solar plant ({plant_id}) has been offline for over {hours_offline} hours.\n"
            "No generation data is being recorded.\n\n"
            "Quick troubleshooting:\n"
            "1. Check if the home WiFi / router is working\n"
            "2. Verify inverter green light is ON\n"
            "3. Ensure the main solar MCB switch has not tripped\n\n"
            "Need help restoring connection? Reply YES to schedule a technician visit or NO to check yourself.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "⚠️ ऑफलाइन चेतावनी — सोलरॉन होम्स प्राइवेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपका सोलर प्लांट ({plant_id}) पिछले {hours_offline} घंटों से ऑफलाइन है।\n"
            "सिस्टम से कोई डेटा प्राप्त नहीं हो रहा है।\n\n"
            "त्वरित जांच:\n"
            "1. घर का वाईफाई चालू है या नहीं जांचें\n"
            "2. इन्वर्टर की हरी लाइट जल रही है या नहीं\n"
            "3. सोलर MCB स्विच ट्रिप तो नहीं हुआ\n\n"
            "तकनीशियन विजिट के लिए YES लिखें या स्वयं जांचने के लिए NO लिखें।\n\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "⚠️ ऑफलाइन सूचना — सोलरॉन होम्स प्रायव्हेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपला सोलर प्लांट ({plant_id}) मागील {hours_offline} तासांपासून ऑफलाइन आहे.\n"
            "कोणताही डेटा नोंदवला जात नाही आहे.\n\n"
            "त्वरित उपाय:\n"
            "१. घरातील वायफाय चालू आहे का तपासा\n"
            "२. इन्व्हर्टरचा हिरवा दिवा चालू आहे का\n"
            "३. सोलर MCB स्विच ट्रिप झाला नाही ना\n\n"
            "तंत्रज्ञ मदतीसाठी YES पाठवा किंवा स्वतः तपासण्यासाठी NO पाठवा.\n\n"
            "टीम सोलरॉन"
        ),
    },

    # 5. solaron_inactive: Zero generation / offline >= 7 days
    "solaron_inactive": {
        "english": (
            "🚨 Urgent Notice — Solaron Homes Pvt Ltd\n\n"
            "Dear {name},\n"
            "Your solar plant ({plant_id}) has recorded ZERO generation for {days_inactive} consecutive days.\n"
            "This causes significant financial loss on your electricity bill every day.\n\n"
            "Is the plant turned off due to roof work, or has a grid/breaker issue occurred?\n\n"
            "Reply YES to schedule an urgent technician inspection or NO if this is intentional.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "🚨 आवश्यक सूचना — सोलरॉन होम्स प्राइवेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपके सोलर प्लांट ({plant_id}) ने पिछले {days_inactive} दिनों से शून्य (0) यूनिट बिजली बनाई है।\n"
            "इससे आपके बिजली बिल में रोजाना नुकसान हो रहा है।\n\n"
            "क्या छत पर काम के कारण प्लांट बंद है, या कोई तकनीकी खराबी आई है?\n\n"
            "तत्काल तकनीशियन जांच के लिए YES लिखकर भेजें या यदि यह आपकी जानकारी में है तो NO लिखें।\n\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "🚨 तातडीची सूचना — सोलरॉन होम्स प्रायव्हेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपल्या सोलर प्लांटने ({plant_id}) मागील {days_inactive} दिवसांत शून्य (०) युनिट वीज तयार केली आहे.\n"
            "यामुळे आपले दररोज आर्थिक नुकसान होत आहे.\n\n"
            "काही कामामुळे प्लांट बंद ठेवला आहे की काही तांत्रिक बिघाड झाला आहे?\n\n"
            "तातडीने तंत्रज्ञांची तपासणी हवी असल्यास YES पाठवा किंवा माहिती असल्यास NO पाठवा.\n\n"
            "टीम सोलरॉन"
        ),
    },

    # 6. solaron_plant_critical: Hardware fault code / safety hazard
    "solaron_plant_critical": {
        "english": (
            "⚠️ CRITICAL SAFETY ALERT — Solaron Homes Pvt Ltd\n\n"
            "Dear {name},\n"
            "A critical hardware fault has been reported by your solar plant ({plant_id}).\n"
            "Fault Code: {fault_code}\n\n"
            "⚡ SAFETY PRECAUTIONS:\n"
            "• Do NOT touch the inverter, panels, or cables\n"
            "• Keep the main AC isolator switch turned OFF\n"
            "• Do not allow children near the solar installation\n\n"
            "Our emergency response team is on standby. Reply YES to dispatch a priority technician immediately.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "⚠️ गंभीर सुरक्षा चेतावनी — सोलरॉन होम्स प्राइवेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपके सोलर प्लांट ({plant_id}) में गंभीर हार्डवेयर खराबी का संकेत मिला है।\n"
            "फॉल्ट कोड: {fault_code}\n\n"
            "⚡ सुरक्षा निर्देश:\n"
            "• इन्वर्टर, पैनल या तारों को बिल्कुल न छुएं\n"
            "• मुख्य AC स्विच बंद रखें\n"
            "• बच्चों को सोलर सिस्टम से दूर रखें\n\n"
            "हमारी प्राथमिकता टीम तैयार है। तत्काल तकनीशियन भेजने के लिए YES लिखकर जवाब दें।\n\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "⚠️ गंभीर सुरक्षा इशारा — सोलरॉन होम्स प्रायव्हेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपल्या सोलर प्लांटमध्ये ({plant_id}) गंभीर तांत्रिक बिघाड आढळला आहे.\n"
            "फॉल्ट कोड: {fault_code}\n\n"
            "⚡ सुरक्षा सूचना:\n"
            "• इन्व्हर्टर, पॅनेल किंवा वायरला अजिबात हात लावू नका\n"
            "• मुख्य AC स्विच बंद ठेवा\n"
            "• मुलांना सोलर सिस्टीमपासून लांब ठेवा\n\n"
            "तातडीने प्राधान्य तंत्रज्ञ पाठवण्यासाठी कृपया लगेच YES पाठवा.\n\n"
            "टीम सोलरॉन"
        ),
    },

    # 7. solaron_check_plant: L3 Follow-up checklist
    "solaron_check_plant": {
        "english": (
            "Hello {name},\n\n"
            "Following up regarding your Solaron plant.\n"
            "Here is your recommended self-check list:\n"
            "{checklist}\n\n"
            "Did checking these resolve the issue? If you still need help, reply YES for technician assistance.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "नमस्ते {name},\n\n"
            "आपके सोलर प्लांट के संबंध में अनुवर्ती संदेश।\n"
            "यहाँ आपकी त्वरित जांच सूची है:\n"
            "{checklist}\n\n"
            "क्या समस्या का समाधान हुआ? यदि अभी भी सहायता चाहिए, तो तकनीशियन विजिट के लिए YES लिखें।\n\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "नमस्कार {name},\n\n"
            "आपल्या सोलर प्लांटबाबत पुढील सूचना.\n"
            "खालील तपासणी सूची पहा:\n"
            "{checklist}\n\n"
            "समस्या सुटली का? अद्याप मदत हवी असल्यास तंत्रज्ञ तपासणीसाठी YES पाठवा.\n\n"
            "टीम सोलरॉन"
        ),
    },

    # 8. solaron_offer_visit: L4 Offer visit with pricing
    "solaron_offer_visit": {
        "english": (
            "Dear {name},\n\n"
            "To safeguard your solar energy generation, Solaron offers an on-site {visit_type} technician visit.\n"
            "Estimated service charges: ₹{charges}.\n\n"
            "The technician will perform electrical diagnostics, string testing, inverter health verification, and connection tuning.\n\n"
            "Reply YES to book the visit or NO to postpone.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "प्रिय {name},\n\n"
            "आपकी सोलर बिजली उत्पादन की सुरक्षा के लिए, सोलरॉन {visit_type} तकनीशियन विजिट की पेशकश करता है।\n"
            "अनुमानित सेवा शुल्क: ₹{charges}।\n\n"
            "तकनीशियन वायरिंग, इन्वर्टर स्वास्थ्य और कनेक्शन की संपूर्ण जांच करेगा।\n\n"
            "विजिट बुक करने के लिए YES लिखें या टालने के लिए NO लिखें।\n\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "प्रिय {name},\n\n"
            "आपल्या सोलर वीज निर्मितीच्या सुरक्षिततेसाठी, सोलरॉन ऑन-साइट {visit_type} तंत्रज्ञ व्हिजिट उपलब्ध करत आहे.\n"
            "अंदाजे सेवा शुल्क: ₹{charges}.\n\n"
            "तंत्रज्ञ वायरिंग, इन्व्हर्टर आरोग्य आणि सर्व कनेक्शनची सविस्तर तपासणी करेल.\n\n"
            "व्हिजिट बुक करण्यासाठी YES पाठवा किंवा पुढे ढकलण्यासाठी NO पाठवा.\n\n"
            "टीम सोलरॉन"
        ),
    },

    # 9. solaron_visit_scheduled: L5-YES Visit confirmation
    "solaron_visit_scheduled": {
        "english": (
            "✅ Visit Confirmed — Solaron Homes Pvt Ltd\n\n"
            "Dear {name},\n"
            "Your technician visit has been scheduled for {date}.\n"
            "Visit Type: {visit_type}\n"
            "Service Charges: ₹{charges} (payable post-service)\n\n"
            "Our certified solar technician will contact you prior to arrival.\n"
            "For rescheduling, call our support desk.\n\n"
            "Thank You,\n"
            "Team Solaron"
        ),
        "hindi": (
            "✅ विजिट कन्फर्म — सोलरॉन होम्स प्राइवेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपकी तकनीशियन विजिट {date} के लिए निर्धारित कर दी गई है।\n"
            "विजिट प्रकार: {visit_type}\n"
            "शुल्क: ₹{charges} (सेवा के बाद देय)\n\n"
            "हमारे तकनीशियन आने से पहले आपसे संपर्क करेंगे।\n\n"
            "धन्यवाद,\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "✅ व्हिजिट निश्चित — सोलरॉन होम्स प्रायव्हेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपली तंत्रज्ञ भेट {date} साठी निश्चित करण्यात आली आहे.\n"
            "प्रकार: {visit_type}\n"
            "शुल्क: ₹{charges} (सेवेनंतर देय)\n\n"
            "आमचे तंत्रज्ञ येण्यापूर्वी आपल्याशी संपर्क साधतील.\n\n"
            "धन्यवाद,\n"
            "टीम सोलरॉन"
        ),
    },

    # 10. solaron_wait_recheck: L5-NO Wait & recheck acknowledgment
    "solaron_wait_recheck": {
        "english": (
            "Noted, {name}.\n\n"
            "We will hold off on scheduling a technician at this time.\n"
            "Our telemetry engine will continuously monitor your system and automatically re-evaluate performance on {recheck_date}.\n\n"
            "If your plant generation recovers, we will update you. If you change your mind, feel free to contact us anytime.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "नोट कर लिया गया है, {name}।\n\n"
            "हम अभी तकनीशियन विजिट नहीं भेज रहे हैं।\n"
            "हमारा सिस्टम आपके प्लांट पर नज़र रखेगा और {recheck_date} को दोबारा जांच करेगा।\n\n"
            "यदि उत्पादन सुधरता है तो हम आपको सूचित करेंगे। आप कभी भी संपर्क कर सकते हैं।\n\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "नोंद घेण्यात आली आहे, {name}.\n\n"
            "आम्ही सध्या तंत्रज्ञ पाठवणे पुढे ढकलले आहे.\n"
            "आमची यंत्रणा आपल्या सिस्टीमवर लक्ष ठेवेल आणि {recheck_date} रोजी पुन्हा मूल्यांकन करेल.\n\n"
            "उत्पादन सुधारल्यास आम्ही कळवू. आपण कधीही संपर्क साधू शकता.\n\n"
            "टीम सोलरॉन"
        ),
    },

    # 11. solaron_reminder: L6 Recheck failed repeat reminder
    "solaron_reminder": {
        "english": (
            "Reminder — Solaron Homes Pvt Ltd\n\n"
            "Dear {name},\n"
            "Re-evaluation of your solar plant ({plant_id}) indicates it is still operating in {status} condition.\n"
            "Unresolved underperformance continues to impact your monthly electricity savings.\n\n"
            "Reply YES to schedule a technician visit or reply HELP to speak with our support manager.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "स्मरण पत्र — सोलरॉन होम्स प्राइवेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपके सोलर प्लांट ({plant_id}) की पुनः जांच में पाया गया कि यह अभी भी {status} स्थिति में है।\n"
            "इससे आपकी बिजली बचत प्रभावित हो रही है।\n\n"
            "विजिट तय करने के लिए YES लिखें या सहायता के लिए HELP लिखकर भेजें।\n\n"
            "टीम सोलरॉन"
        ),
        "marathi": (
            "स्मरणपत्र — सोलरॉन होम्स प्रायव्हेट लिमिटेड\n\n"
            "प्रिय {name},\n"
            "आपल्या सोलर प्लांटच्या ({plant_id}) फेरतपासणीत तो अजूनही {status} स्थितीत असल्याचे दिसून आले आहे.\n"
            "यामुळे आपल्या वीज बचतीवर परिणाम होत आहे.\n\n"
            "व्हिजिटसाठी YES पाठवा किंवा मदतीसाठी HELP पाठवा.\n\n"
            "टीम सोलरॉन"
        ),
    },

    # Offline Follow-Up Tree (F1 to F6)
    "solaron_offline_f1": {
        "english": (
            "Greetings From Solaron Homes Pvt Ltd,\n\n"
            "Dear Sir/Madam,\n"
            "Your solar plant has been offline for {days} days and no generation data is being received. You may be losing savings every day.\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं,\n\n"
            "प्रिय महोदय/मैम,\n"
            "आपका सोलर प्लांट {days} दिनों से ऑफ़लाइन है और कोई डेटा प्राप्त नहीं हो रहा। इससे आपकी बचत का नुकसान हो रहा है।\n\n"
            "टीम सोलरॉन"
        ),
    },
    "solaron_offline_f2": {
        "english": (
            "Dear Sir/Madam,\n"
            "Please check: inverter display/green light, wifi router, MCB switch.\n"
            "Also clean your panels (dust, bird droppings) and remove any shade. Dirty panels reduce generation.\n"
            "If it is still offline after this, contact us at {phone}\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "प्रिय महोदय/मैम,\n"
            "कृपया जाँचें: इन्वर्टर डिस्प्ले/हरी लाइट, वाईफ़ाई राउटर, MCB स्विच।\n"
            "साथ ही पैनलों की सफाई करें (धूल, पक्षियों की बीट) और छाया हटाएं। गंदे पैनल उत्पादन घटाते हैं।\n"
            "इसके बाद भी ऑफ़लाइन रहे तो संपर्क करें: {phone}\n\n"
            "टीम सोलरॉन"
        ),
    },
    "solaron_offline_f3": {
        "english": (
            "Dear Sir/Madam,\n"
            "We can send a technician to inspect and restore your plant. Visit charges: ₹{charges}. A cleaning cycle can be added at extra cost.\n"
            "Reply YES to book or NO to wait. Contact: {phone}\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "प्रिय महोदय/मैम,\n"
            "हम आपके प्लांट की जाँच और मरम्मत के लिए तकनीशियन भेज सकते हैं। विजिट शुल्क: ₹{charges}। अतिरिक्त शुल्क पर सफाई भी जोड़ी जा सकती है।\n"
            "बुक करने के लिए YES, प्रतीक्षा के लिए NO लिखें। संपर्क: {phone}\n\n"
            "टीम सोलरॉन"
        ),
    },
    "solaron_offline_f4": {
        "english": (
            "Thank you. Your technician visit is booked for {visit_date}, {time_slot}.\n"
            "Charges: ₹{charges} (payable after service).\n"
            "Technician: {tech_name}, {tech_phone}\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "धन्यवाद। आपकी तकनीशियन विजिट {visit_date}, {time_slot} को बुक हो गई है।\n"
            "शुल्क: ₹{charges} (सेवा के बाद देय)।\n"
            "तकनीशियन: {tech_name}, {tech_phone}\n\n"
            "टीम सोलरॉन"
        ),
    },
    "solaron_offline_f5": {
        "english": (
            "Understood. We will check your plant status again in 3 days. To book a visit earlier, reply YES or call {phone}\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "ठीक है। हम 3 दिन बाद आपके प्लांट की स्थिति दोबारा जाँचेंगे। जल्दी विजिट के लिए YES लिखें या कॉल करें: {phone}\n\n"
            "टीम सोलरॉन"
        ),
    },
    "solaron_offline_f6": {
        "english": (
            "Dear Sir/Madam,\n"
            "Reminder: your solar plant is still offline. Please check and clean your plant, or book a technician visit (₹{charges}).\n"
            "Our team will call you shortly. Contact: {phone}\n\n"
            "Team Solaron"
        ),
        "hindi": (
            "प्रिय महोदय/मैम,\n"
            "स्मरण: आपका सोलर प्लांट अभी भी ऑफ़लाइन है। कृपया प्लांट की जाँच व सफाई करें या तकनीशियन विजिट (₹{charges}) बुक करें।\n"
            "हमारी टीम जल्द आपको कॉल करेगी। संपर्क: {phone}\n\n"
            "टीम सोलरॉन"
        ),
    },
}

# Standard category-specific checklists for L3
CHECKLISTS_BY_CATEGORY: Dict[str, Dict[str, str]] = {
    "ALL_FINE": {
        "english": "• Clean dust accumulation off panels early morning\n• Check for bird droppings or dried leaves\n• Maintain clearance around inverter ventilation",
        "hindi": "• सुबह के समय पैनलों से धूल साफ करें\n• पक्षियों की बीट या सूखे पत्तों की जांच करें\n• इन्वर्टर के आसपास हवा का आवागमन बनाए रखें",
        "marathi": "• सकाळी लवकर पॅनेल्सवरील धूळ स्वच्छ करा\n• पक्ष्यांची विष्ठा किंवा वाळलेली पाने तपासा\n• इन्व्हर्टरजवळ मोकळी हवा राहील याची काळजी घ्या",
    },
    "AVERAGE": {
        "english": "• Wash panels using clean soft water\n• Inspect nearby trees for new branch shading\n• Verify all string breakers in ACDB/DCDB boxes are UP",
        "hindi": "• पैनलों को साफ और हल्के पानी से धोएं\n• पेड़ों की नई शाखाओं की छाया की जांच करें\n• ACDB/DCDB बॉक्स में सभी ब्रेकर चालू हैं या नहीं देखें",
        "marathi": "• पॅनेल्स स्वच्छ पाण्याने धुवून घ्या\n• झाडांच्या फांद्यांची सावली पडत नाही ना ते पहा\n• ACDB/DCDB बॉक्समधील सर्व ब्रेकर्स चालू आहेत का तपासा",
    },
    "CRITICAL_PERF": {
        "english": "• Check inverter screen for error symbols or yellow/red LEDs\n• Inspect solar panels for cracked glass or visible hotspot burns\n• Ensure DC isolator knob is fully turned to ON position",
        "hindi": "• इन्वर्टर स्क्रीन पर एरर कोड या पीली/लाल लाइट देखें\n• सोलर पैनल पर टूटा हुआ कांच या जलने के निशान जांचें\n• DC आइसोलेटर स्विच पूरी तरह ON स्थिति में रखें",
        "marathi": "• इन्व्हर्टर स्क्रीनवर त्रुटी चिन्ह किंवा पिवळे/लाल दिवे तपासा\n• पॅनेलवर काच फुटली आहे का किंवा डाग पडले आहेत का ते पहा\n• DC आयसोलेटर स्विच पूर्णपणे ON असल्याची खात्री करा",
    },
    "OFFLINE": {
        "english": "• Restart your home WiFi router\n• Check if the data logger dongle LED is blinking green\n• Inspect main solar MCB in the main electrical distribution box",
        "hindi": "• घर का वाईफाई राउटर रीस्टार्ट करें\n• जांचें कि डेटा लॉगर की लाइट हरी जल रही है या नहीं\n• मुख्य विद्युत बॉक्स में सोलर MCB स्विच जांचें",
        "marathi": "• घरातील वायफाय राऊटर पुन्हा सुरू करा\n• डेटा लॉगरवरील दिवा हिरवा लागत आहे का ते तपासा\n• मुख्य विद्युत पेटीतील सोलर MCB स्विच तपासा",
    },
    "INACTIVE": {
        "english": "• Confirm whether grid power is available at the premises\n• Check if bidirectional net meter is functioning\n• Confirm if any renovation or roof maintenance caused system shutdown",
        "hindi": "• पुष्टि करें कि परिसर में ग्रिड बिजली उपलब्ध है\n• जांचें कि नेट मीटर ठीक से काम कर रहा है या नहीं\n• क्या छत की मरम्मत के कारण सिस्टम बंद किया गया है",
        "marathi": "• घरात मुख्य वीजपुरवठा सुरू आहे का याची खात्री करा\n• नेट मीटर चालू आहे का ते पहा\n• छतावरील काही कामामुळे सिस्टीम बंद केली आहे का तपासा",
    },
    "PLANT_CRITICAL": {
        "english": "• ⚠️ DO NOT TOUCH any equipment or exposed wiring\n• Ensure the main isolator switch is kept OFF\n• Keep clear of inverter and wait for Solaron certified technician",
        "hindi": "• ⚠️ किसी भी उपकरण या खुले तारों को बिल्कुल न छुएं\n• मुख्य स्विच को OFF स्थिति में रखें\n• इन्वर्टर से दूर रहें और सोलरॉन तकनीशियन की प्रतीक्षा करें",
        "marathi": "• ⚠️ कोणत्याही उपकरणाला किंवा उघड्या वायरला हात लावू नका\n• मुख्य स्विच बंद ठेवा\n• इन्व्हर्टरपासून लांब राहा आणि तंत्रज्ञांची वाट पहा",
    },
}


def normalize_language(lang: Optional[str]) -> str:
    """Normalize language string to english, hindi, or marathi."""
    if not lang:
        return "english"
    l = str(lang).lower().strip()
    if "hi" in l or "hin" in l:
        return "hindi"
    if "mr" in l or "mar" in l:
        return "marathi"
    return "english"


def compose_escalation_message(
    template_id: str,
    params: Dict[str, Any],
    language: Optional[str] = "english"
) -> str:
    """
    Renders an escalation template using supplied parameters in the requested language.
    Falls back to English if the translation is missing.
    """
    lang = normalize_language(language)
    tpl_set = ESCALATION_TEMPLATES.get(template_id, {})
    template_str = tpl_set.get(lang) or tpl_set.get("english", "")
    if not template_str:
        return f"Solaron notification: {params}"

    # Safe substitution with defaults
    safe_params = {k: ("" if v is None else str(v)) for k, v in params.items()}
    try:
        return template_str.format(**safe_params)
    except KeyError:
        # Fallback if some param was missing
        import re
        formatted = template_str
        for k, v in safe_params.items():
            formatted = formatted.replace(f"{{{k}}}", str(v))
        # Clear any remaining unformatted placeholders
        return re.sub(r"\{[a-zA-Z0-9_]+\}", "N/A", formatted)


def get_checklist(category: str, language: Optional[str] = "english") -> str:
    """Get the bulleted self-check list for a category and language."""
    lang = normalize_language(language)
    c_set = CHECKLISTS_BY_CATEGORY.get(category, CHECKLISTS_BY_CATEGORY.get("AVERAGE", {}))
    return c_set.get(lang, c_set.get("english", ""))
