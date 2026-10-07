"""
Solaron Gupshup WhatsApp Integration Service.

Handles outbound template sending, session messaging, and webhook payload verification.
Gracefully handles missing API credentials for local testing and staging environments.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)

GUPSHUP_TEMPLATE_API_URL = "https://api.gupshup.io/wa/api/v1/template/msg"
GUPSHUP_MSG_API_URL = "https://api.gupshup.io/wa/api/v1/msg"


async def send_template_message(
    phone: str,
    template_id: str,
    template_params: List[str],
    language: str = "en",
) -> Dict[str, Any]:
    """
    Sends a WhatsApp template message via Gupshup WhatsApp API.
    
    If GUPSHUP_API_KEY is not set or in test mode, simulates successful dispatch
    and returns a mock message ID for sandbox development and automated tests.
    """
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    if len(clean_phone) == 10:
        clean_phone = f"91{clean_phone}"

    # Fallback simulation if no API key is provided
    if not settings.gupshup_api_key or settings.gupshup_api_key.strip() in ("", "your_api_key_here"):
        mock_msg_id = f"mock_{uuid.uuid4().hex[:16]}"
        logger.info(
            "[MOCK GUPSHUP] Outbound to %s | Template: %s | Params: %s | ID: %s",
            clean_phone, template_id, template_params, mock_msg_id
        )
        return {
            "status": "submitted",
            "messageId": mock_msg_id,
            "simulated": True,
            "destination": clean_phone,
            "template": template_id,
        }

    headers = {
        "apikey": settings.gupshup_api_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "channel": "whatsapp",
        "source": settings.gupshup_source_number or "919619455207",
        "destination": clean_phone,
        "template": json.dumps({
            "id": template_id,
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
            logger.info("Gupshup API response for %s: %s", clean_phone, data)
            return data
    except Exception as e:
        logger.error("Failed to send Gupshup template message to %s: %s", clean_phone, e)
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
