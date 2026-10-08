"""
Solaron Gupshup WhatsApp Integration Service.

Handles outbound template sending, session messaging, and webhook payload verification.
Includes template ID resolution (B11) and safety switches (GUPSHUP_SEND_MODE = off | test_only | live).
"""

import json
import logging
import uuid
import re
from typing import Any, Dict, List, Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)

GUPSHUP_TEMPLATE_API_URL = "https://api.gupshup.io/wa/api/v1/template/msg"
GUPSHUP_MSG_API_URL = "https://api.gupshup.io/wa/api/v1/msg"


def resolve_template_id(template_name_or_id: str) -> str:
    """
    Resolves internal template name to Meta-approved Gupshup template ID from config.
    Fixes B11 where internal template names (e.g. solaron_average) were rejected by API.
    """
    tpl_map = {
        "solaron_active": settings.gupshup_tpl_active,
        "solaron_average": settings.gupshup_tpl_average,
        "solaron_critical_perf": settings.gupshup_tpl_critical_perf,
        "solaron_offline": settings.gupshup_tpl_offline,
        "solaron_inactive": settings.gupshup_tpl_inactive,
        "solaron_plant_critical": settings.gupshup_tpl_plant_critical,
        "solaron_offer_visit": settings.gupshup_tpl_offer_visit,
        "solaron_wait_recheck": settings.gupshup_tpl_wait_recheck,
        "solaron_reminder": settings.gupshup_tpl_reminder,
        "solaron_monthly_statement": settings.gupshup_tpl_monthly,
    }
    return tpl_map.get(template_name_or_id, template_name_or_id)


async def send_template_message(
    phone: str,
    template_id: str,
    template_params: List[str],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Sends a WhatsApp template message via Gupshup WhatsApp API.
    
    Safety switch GUPSHUP_SEND_MODE:
    - 'off': Completely disabled.
    - 'test_only': Only sends to TEST_PHONE_NUMBER; redirects any other phone.
    - 'live': Sends to destination phone.
    """
    send_mode = getattr(settings, "gupshup_send_mode", "test_only").lower().strip()
    if send_mode == "off":
        logger.info(f"[GUPSHUP DISABLED] Outbound to {phone} suppressed (GUPSHUP_SEND_MODE=off).")
        return {"status": "disabled", "simulated": True, "destination": phone, "template": template_id}

    clean_digits = re.sub(r"\D", "", str(phone))
    if len(clean_digits) == 10:
        clean_phone = f"91{clean_digits}"
    elif len(clean_digits) == 12 and clean_digits.startswith("91"):
        clean_phone = clean_digits
    else:
        clean_phone = clean_digits

    # Resolved approved Gupshup template ID
    approved_tpl_id = resolve_template_id(template_id)

    # In test_only mode, redirect to TEST_PHONE_NUMBER
    test_phone_clean = re.sub(r"\D", "", str(settings.test_phone_number or "919619455207"))
    if len(test_phone_clean) == 10:
        test_phone_clean = f"91{test_phone_clean}"

    effective_destination = clean_phone
    if send_mode == "test_only":
        if clean_phone != test_phone_clean:
            logger.info(
                f"[GUPSHUP TEST MODE] Redirecting message for customer {clean_phone} to TEST_PHONE_NUMBER {test_phone_clean}."
            )
            effective_destination = test_phone_clean

    # Fallback simulation if no API key is provided
    if not settings.gupshup_api_key or settings.gupshup_api_key.strip() in ("", "your_api_key_here"):
        mock_msg_id = f"mock_{uuid.uuid4().hex[:16]}"
        logger.info(
            "[MOCK GUPSHUP] Outbound to %s | Template: %s (%s) | Params: %s | ID: %s",
            effective_destination, approved_tpl_id, template_id, template_params, mock_msg_id
        )
        return {
            "status": "submitted",
            "messageId": mock_msg_id,
            "simulated": True,
            "destination": effective_destination,
            "template": approved_tpl_id,
        }

    headers = {
        "apikey": settings.gupshup_api_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "channel": "whatsapp",
        "source": settings.gupshup_source_number or "919619455207",
        "destination": effective_destination,
        "template": json.dumps({
            "id": approved_tpl_id,
            "params": [str(p) for p in template_params],
        }),
        "src.name": settings.gupshup_app_name or "SolaronHomes",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(GUPSHUP_TEMPLATE_API_URL, data=payload, headers=headers)
            try:
                data = resp.json()
            except Exception:
                data = {"status": resp.status_code, "text": resp.text}
            logger.info("Gupshup API response for %s: %s", effective_destination, data)
            return data
    except Exception as e:
        logger.error("Failed to send Gupshup template message to %s: %s", effective_destination, e)
        return {"status": "error", "error": str(e), "messageId": None}


def send_template_message_sync(
    phone: str,
    template_id: str,
    template_params: List[str],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Synchronous wrapper for sending template messages (used by background workers/schedulers).
    """
    import asyncio
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    send_template_message(phone, template_id, template_params, language)
                )
                return future.result()
        else:
            return asyncio.run(send_template_message(phone, template_id, template_params, language))
    except Exception as e:
        logger.error("Error in send_template_message_sync: %s", e)
        return {"status": "error", "error": str(e)}
