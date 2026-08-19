"""
PayPal Webhook Router

Handles incoming webhook events from PayPal.

Security:
  - Webhook ID verification via PayPal's REST API (POST /v1/notifications/verify-webhook-signature).
  - Required headers extracted: PAYPAL-AUTH-ALGO, PAYPAL-CERT-URL,
    PAYPAL-TRANSMISSION-ID, PAYPAL-TRANSMISSION-SIG, PAYPAL-TRANSMISSION-TIME.
  - Idempotency: PAYPAL-TRANSMISSION-ID is used as the event's unique identifier
    to detect and reject duplicate deliveries before processing.

Note:
  Full PayPal SDK verification is stubbed for local testing without live
  credentials. The idempotency layer (Redis) is wired in Day 5.
"""

import json
from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import settings

router = APIRouter(prefix="/webhooks/paypal", tags=["PayPal Webhooks"])


# ─── Signature Verification ───────────────────────────────────────────────────


async def verify_paypal_webhook(
    *,
    auth_algo: str,
    cert_url: str,
    transmission_id: str,
    transmission_sig: str,
    transmission_time: str,
    webhook_id: str,
    raw_body: bytes,
) -> None:
    """
    Verify a PayPal webhook notification against PayPal's verification API.

    Calls ``POST /v1/notifications/verify-webhook-signature`` with the
    webhook headers and raw payload. PayPal responds with
    ``{"verification_status": "SUCCESS"}`` for valid webhooks.

    Args:
        auth_algo:        Value of ``PAYPAL-AUTH-ALGO`` header.
        cert_url:         Value of ``PAYPAL-CERT-URL`` header.
        transmission_id:  Value of ``PAYPAL-TRANSMISSION-ID`` header (event ID).
        transmission_sig: Value of ``PAYPAL-TRANSMISSION-SIG`` header.
        transmission_time: Value of ``PAYPAL-TRANSMISSION-TIME`` header.
        webhook_id:       The PayPal webhook ID from the developer dashboard.
        raw_body:         Raw request body bytes.

    Raises:
        HTTPException 400: If PayPal reports the webhook is invalid.
        HTTPException 502: If the PayPal verification service is unreachable.
    """
    # ── Obtain OAuth2 access token ────────────────────────────────────────────
    base_url = (
        "https://api-m.sandbox.paypal.com"
        if settings.PAYPAL_MODE == "sandbox"
        else "https://api-m.paypal.com"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Get access token
        token_response = await client.post(
            f"{base_url}/v1/oauth2/token",
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
        )
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to obtain PayPal access token for webhook verification.",
            )
        access_token: str = token_response.json().get("access_token", "")

        # Verify webhook signature
        verify_response = await client.post(
            f"{base_url}/v1/notifications/verify-webhook-signature",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "auth_algo": auth_algo,
                "cert_url": cert_url,
                "transmission_id": transmission_id,
                "transmission_sig": transmission_sig,
                "transmission_time": transmission_time,
                "webhook_id": webhook_id,
                "webhook_event": json.loads(raw_body),
            },
        )

    if verify_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="PayPal webhook verification service unavailable.",
        )

    result = verify_response.json()
    if result.get("verification_status") != "SUCCESS":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"PayPal webhook signature verification failed: "
                f"status={result.get('verification_status')}"
            ),
        )


# ─── Idempotency Check (in-memory stub — Redis wired in Day 5) ────────────────

_processed_event_ids: set[str] = set()  # Replaced by Redis on Day 5


def is_duplicate_event(event_id: str) -> bool:
    """
    Check whether this event has already been processed.

    In Day 5 this will be replaced by an atomic Redis SET NX EX operation.
    For now, an in-memory set provides the same logical guarantee within
    a single process.

    Args:
        event_id: The unique identifier for the incoming event.

    Returns:
        True if the event was already seen; False otherwise.
    """
    if event_id in _processed_event_ids:
        return True
    _processed_event_ids.add(event_id)
    return False


# ─── Webhook Endpoint ─────────────────────────────────────────────────────────


@router.post(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Receive PayPal Webhook Events",
    response_description="Webhook acknowledged",
)
async def receive_paypal_webhook(
    request: Request,
    paypal_auth_algo: Annotated[
        str | None, Header(alias="paypal-auth-algo")
    ] = None,
    paypal_cert_url: Annotated[
        str | None, Header(alias="paypal-cert-url")
    ] = None,
    paypal_transmission_id: Annotated[
        str | None, Header(alias="paypal-transmission-id")
    ] = None,
    paypal_transmission_sig: Annotated[
        str | None, Header(alias="paypal-transmission-sig")
    ] = None,
    paypal_transmission_time: Annotated[
        str | None, Header(alias="paypal-transmission-time")
    ] = None,
) -> dict:
    """
    PayPal webhook receiver endpoint.

    Processing pipeline:
      1. Read raw body bytes.
      2. Validate all required PayPal signature headers are present.
      3. Check idempotency: reject duplicate TRANSMISSION-ID events.
      4. Verify webhook signature via PayPal's verification API.
      5. Dispatch to event-specific handler (persistence added Day 5).

    Returns:
        JSON acknowledgement.
    """
    # ── 1. Read raw body ──────────────────────────────────────────────────────
    raw_body: bytes = await request.body()

    # ── 2. Validate required headers ─────────────────────────────────────────
    required_headers = {
        "PAYPAL-AUTH-ALGO": paypal_auth_algo,
        "PAYPAL-CERT-URL": paypal_cert_url,
        "PAYPAL-TRANSMISSION-ID": paypal_transmission_id,
        "PAYPAL-TRANSMISSION-SIG": paypal_transmission_sig,
        "PAYPAL-TRANSMISSION-TIME": paypal_transmission_time,
    }
    missing = [k for k, v in required_headers.items() if not v]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required PayPal webhook headers: {', '.join(missing)}",
        )

    # ── 3. Idempotency check ──────────────────────────────────────────────────
    event_id: str = paypal_transmission_id  # type: ignore[assignment]
    if is_duplicate_event(event_id):
        # Return 200 — PayPal will retry non-2xx responses
        return {
            "received": True,
            "event_id": event_id,
            "status": "duplicate_ignored",
        }

    # ── 4. Verify signature ───────────────────────────────────────────────────
    # NOTE: Skipped when PAYPAL_CLIENT_ID/SECRET are not configured (local dev)
    if settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET:
        await verify_paypal_webhook(
            auth_algo=paypal_auth_algo,  # type: ignore[arg-type]
            cert_url=paypal_cert_url,  # type: ignore[arg-type]
            transmission_id=event_id,
            transmission_sig=paypal_transmission_sig,  # type: ignore[arg-type]
            transmission_time=paypal_transmission_time,  # type: ignore[arg-type]
            webhook_id=settings.PAYPAL_WEBHOOK_ID,
            raw_body=raw_body,
        )

    # ── 5. Parse + Dispatch ───────────────────────────────────────────────────
    try:
        event_data: dict = json.loads(raw_body)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse PayPal webhook payload as JSON.",
        )

    event_type: str = event_data.get("event_type", "unknown")

    # TODO(Day5): persist WebhookEvent to database
    # TODO(Day5): route to payment-specific handler

    return {
        "received": True,
        "event_id": event_id,
        "event_type": event_type,
    }
