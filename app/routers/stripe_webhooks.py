"""
Stripe Webhook Router

Handles incoming webhook events from Stripe.

Security:
  - Raw request body is read before any parsing (required for HMAC validation).
  - HMAC-SHA256 signature is verified using Stripe's `Stripe-Signature` header
    and the configured webhook signing secret.
  - Timestamps are validated to reject replayed requests older than 5 minutes.
  - Constant-time comparison (hmac.compare_digest) prevents timing attacks.
"""

import hashlib
import hmac
import time
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import settings

router = APIRouter(prefix="/webhooks/stripe", tags=["Stripe Webhooks"])

# Replay attack tolerance: reject payloads older than 5 minutes
_TIMESTAMP_TOLERANCE_SECONDS: int = 300


# ─── Signature Verification ───────────────────────────────────────────────────


def verify_stripe_signature(
    payload: bytes,
    sig_header: str,
    secret: str,
    tolerance: int = _TIMESTAMP_TOLERANCE_SECONDS,
) -> None:
    """
    Verify a Stripe webhook signature.

    Stripe constructs the signature by:
      1. Concatenating the Unix timestamp + "." + raw payload.
      2. Computing HMAC-SHA256 of that string with the webhook signing secret.
      3. Encoding the result as a hex digest.

    The `Stripe-Signature` header format:
      ``t=<timestamp>,v1=<hex_signature>[,v1=<additional_sig>...]``

    Args:
        payload:   Raw request body bytes (must NOT be decoded/re-encoded).
        sig_header: The full value of the ``Stripe-Signature`` HTTP header.
        secret:    The webhook endpoint's signing secret (``whsec_...``).
        tolerance: Maximum allowed age of the event in seconds (default 5 min).

    Raises:
        HTTPException 400: If the header is malformed, the signature does not
                           match, or the timestamp exceeds the tolerance window.
    """
    # ── Parse header elements ─────────────────────────────────────────────────
    elements: dict[str, list[str]] = {}
    for part in sig_header.split(","):
        if "=" not in part:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Stripe-Signature header format.",
            )
        key, _, value = part.partition("=")
        elements.setdefault(key.strip(), []).append(value.strip())

    timestamp_parts = elements.get("t")
    v1_signatures = elements.get("v1")

    if not timestamp_parts or not v1_signatures:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe-Signature header missing timestamp or v1 signature.",
        )

    # ── Validate timestamp (replay attack prevention) ─────────────────────────
    try:
        event_timestamp = int(timestamp_parts[0])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe-Signature timestamp is not a valid integer.",
        )

    current_time = int(time.time())
    if tolerance and abs(current_time - event_timestamp) > tolerance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Stripe webhook timestamp is too old "
                f"(age={current_time - event_timestamp}s, tolerance={tolerance}s). "
                "Possible replay attack."
            ),
        )

    # ── Compute expected HMAC-SHA256 signature ────────────────────────────────
    signed_payload = f"{event_timestamp}.".encode() + payload
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    # ── Constant-time comparison (prevents timing attacks) ────────────────────
    if not any(
        hmac.compare_digest(expected_sig, received_sig)
        for received_sig in v1_signatures
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe webhook signature verification failed.",
        )


# ─── Webhook Endpoint ─────────────────────────────────────────────────────────


@router.post(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Receive Stripe Webhook Events",
    response_description="Webhook acknowledged",
)
async def receive_stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="stripe-signature")] = None,
) -> dict:
    """
    Stripe webhook receiver endpoint.

    Stripe sends a POST request to this endpoint whenever a subscribed event
    occurs (e.g. ``payment_intent.succeeded``, ``charge.refunded``).

    Processing pipeline:
      1. Read raw body bytes (required for HMAC verification).
      2. Verify HMAC-SHA256 signature from ``Stripe-Signature`` header.
      3. Parse event payload.
      4. Dispatch to event-specific handler (idempotency + audit added Day 5).

    Returns:
        JSON acknowledgement (Stripe considers any 2xx a success).
    """
    # ── 1. Read raw body ──────────────────────────────────────────────────────
    raw_body: bytes = await request.body()

    # ── 2. Require Stripe-Signature header ───────────────────────────────────
    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header.",
        )

    # ── 3. Verify signature ───────────────────────────────────────────────────
    verify_stripe_signature(
        payload=raw_body,
        sig_header=stripe_signature,
        secret=settings.STRIPE_WEBHOOK_SECRET,
    )

    # ── 4. Parse JSON payload ─────────────────────────────────────────────────
    try:
        import json
        event_data: dict = json.loads(raw_body)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse webhook payload as JSON.",
        )

    event_type: str = event_data.get("type", "unknown")
    event_id: str = event_data.get("id", "unknown")

    # ── 5. Dispatch (placeholder — idempotency & persistence added Day 5) ─────
    # TODO(Day5): idempotency check via Redis before processing
    # TODO(Day5): persist WebhookEvent to database
    # TODO(Day5): route to payment-specific handler

    return {
        "received": True,
        "event_id": event_id,
        "event_type": event_type,
    }
