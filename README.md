# Payment Webhook Processor

A production-grade payment webhook processing service built with **FastAPI**, **PostgreSQL**, **Redis**, and **Docker**. Handles Stripe and PayPal webhooks with idempotency, audit logging, dead-letter queuing, and an admin dashboard.

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL + SQLAlchemy (async) |
| Cache / Idempotency | Redis |
| Payment Providers | Stripe, PayPal |
| Containerisation | Docker + Docker Compose |
| Testing | Pytest + Locust |
| CI/CD | GitHub Actions |

## Project Structure

```
payment-webhook-processor/
├── app/
│   ├── main.py          # FastAPI application entry point
│   ├── config.py        # Pydantic-settings configuration
│   ├── models/          # SQLAlchemy ORM models
│   ├── routers/         # Webhook route handlers
│   ├── services/        # Business logic (idempotency, audit, retry)
│   ├── schemas/         # Pydantic request/response schemas
│   └── templates/       # Jinja2 admin dashboard templates
├── tests/
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Charleskojomark/payment-webhook-processor.git
cd payment-webhook-processor

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and configure environment variables
cp .env.example .env
# Edit .env with your Stripe/PayPal keys, DB URL, Redis URL

# 5. Run the development server
uvicorn app.main:app --reload
```

## Health Check

```
GET /health
→ {"status": "healthy", "service": "payment-webhook-processor", "version": "1.0.0"}
```

---

> **Status**: 🚧 Active Development — Week 4 of 6
