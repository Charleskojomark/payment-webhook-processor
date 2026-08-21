"""
Payment Webhook Processor - FastAPI Application Entry Point

This module initializes the FastAPI application with:
- CORS middleware for cross-origin requests
- Health check endpoint
- Versioned API routers (added incrementally per day)
- Startup/shutdown lifecycle events
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import paypal_webhooks, stripe_webhooks

# ─── Application Factory ──────────────────────────────────────────────────────

app = FastAPI(
    title="Payment Webhook Processor",
    description=(
        "Production-grade webhook processing for Stripe and PayPal. "
        "Features idempotency, audit logging, dead-letter queuing, and "
        "an admin dashboard."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(stripe_webhooks.router)
app.include_router(paypal_webhooks.router)


# ─── Lifecycle Events ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup() -> None:
    """Run on application startup."""
    # Initialize DB (if using create_all instead of alembic for dev)
    # from app.db.database import engine, Base
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    pass


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Run on application shutdown."""
    pass


# ─── Core Endpoints ───────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns the current health status of the service.
    Used by load balancers and monitoring systems.
    """
    return {
        "status": "healthy",
        "service": "payment-webhook-processor",
        "version": "1.0.0",
    }
