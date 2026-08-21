"""
SQLAlchemy Database Models
"""
import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base


class EventStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    DLQ = "dlq"


class WebhookEvent(Base):
    """
    Stores incoming webhook events for idempotency and processing.
    """
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # 'stripe', 'paypal'
    event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, native_enum=False), default=EventStatus.PENDING, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transactions: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction", back_populates="webhook_event", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="webhook_event", cascade="all, delete-orphan"
    )


class PaymentTransaction(Base):
    """
    Represents a payment transaction extracted from a webhook.
    """
    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    webhook_event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Stored in cents
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    webhook_event: Mapped["WebhookEvent"] = relationship("WebhookEvent", back_populates="transactions")


class AuditLog(Base):
    """
    Tracks the lifecycle and processing attempts of a webhook event.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    webhook_event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False)  # 'received', 'processing', 'success', 'failed'
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    webhook_event: Mapped["WebhookEvent"] = relationship("WebhookEvent", back_populates="audit_logs")
