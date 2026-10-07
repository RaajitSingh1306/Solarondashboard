"""
Solaron Gupshup Inbound Webhook Route.

Receives customer messages and status events from Gupshup WhatsApp API.
Logs all events to gupshup_inbound_log and triggers escalation state transitions
for customer replies (e.g. YES to book technician, NO to postpone).
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple
from fastapi import APIRouter, Request, Response, status

try:
    from pipeline import db
    from engines import escalation_state_machine
except ImportError:
    import db
    import escalation_state_machine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Gupshup Webhook"])


def extract_inbound_message(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extracts (phone, text, message_type, event_type) across various Gupshup payload formats.
    """
    event_type = payload.get("type", "unknown")
    inner = payload.get("payload", {})

    if event_type == "message":
        # Standard WhatsApp inbound message
        phone = inner.get("source") or inner.get("sender", {}).get("phone")
        m_type = inner.get("type", "text")
        text = ""

        if m_type == "text":
            p_text = inner.get("payload", {})
            if isinstance(p_text, dict):
                text = p_text.get("text", "")
            else:
                text = str(p_text)
        elif m_type in ("button", "quick_reply"):
            p_btn = inner.get("payload", {})
            if isinstance(p_btn, dict):
                text = p_btn.get("text") or p_btn.get("postbackText") or p_btn.get("title") or ""
            else:
                text = str(p_btn)
        elif m_type == "interactive":
            p_inter = inner.get("payload", {})
            if isinstance(p_inter, dict):
                btn_rep = p_inter.get("button_reply", {})
                list_rep = p_inter.get("list_reply", {})
                text = btn_rep.get("title") or btn_rep.get("id") or list_rep.get("title") or ""
        else:
            text = str(inner.get("text") or inner.get("payload") or "")

        return phone, text, m_type, event_type

    elif event_type == "message-event":
        # Delivery, read, or failed status update
        phone = inner.get("destination") or inner.get("phone")
        status_val = inner.get("type", "status_event")
        return phone, status_val, "status_event", event_type

    # Fallback for simple flat formats
    phone = payload.get("phone") or payload.get("source") or payload.get("from")
    text = payload.get("text") or payload.get("message")
    m_type = payload.get("type", "text")
    return phone, text, m_type, event_type


@router.get("/webhooks/gupshup")
def gupshup_webhook_challenge(request: Request):
    """
    Gupshup verification challenge endpoint.
    Some webhook providers ping GET /webhooks/gupshup with a challenge token.
    """
    challenge = request.query_params.get("challenge") or request.query_params.get("hub.challenge")
    if challenge:
        return Response(content=challenge, media_type="text/plain")
    return {"status": "active", "service": "Solaron Gupshup Webhook"}


@router.post("/webhooks/gupshup")
async def gupshup_webhook_handler(request: Request):
    """
    Receives incoming WhatsApp events from Gupshup.
    Logs raw payload to SQLite and triggers escalation state transitions.
    """
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception as e:
        logger.error("Failed to parse Gupshup webhook JSON: %s", e)
        return {"status": "error", "message": "invalid_json"}

    phone, text, m_type, event_type = extract_inbound_message(payload)
    phone_clean = phone or "unknown"
    raw_str = json.dumps(payload)

    # 1. Log inbound payload
    inbound_id = None
    try:
        with db.crm_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO gupshup_inbound_log (
                    phone, message_text, message_type, gupshup_event, raw_payload, processed, created_at
                ) VALUES (?, ?, ?, ?, ?, 0, datetime('now'));
            """, [phone_clean, text or "", m_type, event_type, raw_str])
            inbound_id = cur.lastrowid
    except Exception as e:
        logger.error("Failed to log Gupshup inbound message: %s", e)

    # 2. Advance state machine if this is an inbound message with content
    transition_result = None
    if event_type == "message" and phone and text:
        try:
            transition_result = escalation_state_machine.handle_customer_reply(
                phone_or_plant=phone,
                reply_text=text
            )
            logger.info("Processed WhatsApp reply from %s: %s -> %s", phone, text, transition_result)

            if inbound_id:
                with db.crm_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("UPDATE gupshup_inbound_log SET processed = 1 WHERE id = ?", [inbound_id])
        except Exception as e:
            logger.error("Error processing escalation customer reply for %s: %s", phone, e)

    return {
        "status": "ok",
        "inbound_id": inbound_id,
        "event_type": event_type,
        "processed": transition_result is not None,
        "result": transition_result
    }
