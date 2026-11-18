
"""Pydantic input and output contracts for support tools."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
import re
from typing import Any

from pydantic import (
    Field,
    field_validator,
    model_validator,
)


from specialist.contracts.validation import StrictSchema, validate_identifier

class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    CANCELLED = "cancelled"
    REFUND_REQUESTED = "refund_requested"


class EscalationTeam(str, Enum):
    BILLING = "billing"
    SHIPPING = "shipping"
    TECHNICAL = "technical"
    GENERAL = "general"


class EscalationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


ALLOWED_LABELS = {
    "technical",
    "shipping",
    "delayed",
    "cancellation",
    "refund",
    "delivered",
    "processing",
    "security_review",
    "prompt_injection",
    "missing_customer",
    "missing_order",
    "order_status",
    "billing",
    "account",
    "general",
}


def validate_operation_id(value: str) -> str:
    """Validate a bounded, stable idempotency identifier."""

    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}(?::(?:notification|ticket))?", value):
        raise ValueError("Invalid operation ID format.")

    return value


# ============================================================
# READ TOOL INPUTS
# ============================================================

class GetTicketInput(StrictSchema):
    ticket_id: str = Field(min_length=1, max_length=64)

    @field_validator("ticket_id")
    @classmethod
    def check_ticket_id(cls, value: str) -> str:
        return validate_identifier(value)


class FindCustomerInput(StrictSchema):
    customer_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=254)

    @model_validator(mode="after")
    def check_exactly_one_lookup(self):
        if (self.customer_id is None) == (self.email is None):
            raise ValueError(
                "Provide exactly one customer_id or email."
            )

        if self.customer_id is not None:
            validate_identifier(self.customer_id)

        if self.email is not None:
            if not re.fullmatch(
                r"[^@\s]+@[^@\s]+\.[^@\s]+",
                self.email,
            ):
                raise ValueError("Invalid email format.")

        return self


class GetOrderInput(StrictSchema):
    order_id: str = Field(min_length=1, max_length=64)

    @field_validator("order_id")
    @classmethod
    def check_order_id(cls, value: str) -> str:
        return validate_identifier(value)


class ProductSnapshot(StrictSchema):
    product_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2048)
    price_tnd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

    @field_validator("source_url")
    @classmethod
    def check_mytek_url(cls, value: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"tunisianet.com.tn", "www.tunisianet.com.tn", "mytek.tn", "www.mytek.tn"}:
            raise ValueError("Product source must be an HTTPS approved retailer URL.")
        return value


class OrderItemInput(StrictSchema):
    product_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    quantity: int = Field(ge=1, le=10)
    unit_price_tnd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    line_total_tnd: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    source_url: str = Field(min_length=1, max_length=2048)

    @field_validator("source_url")
    @classmethod
    def check_item_url(cls, value: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"tunisianet.com.tn", "www.tunisianet.com.tn", "mytek.tn", "www.mytek.tn"}:
            raise ValueError("Product source must be an HTTPS approved retailer URL.")
        return value

    @model_validator(mode="after")
    def check_line_total(self):
        expected = (self.unit_price_tnd * self.quantity).quantize(Decimal("0.01"))
        if self.line_total_tnd is not None and expected != self.line_total_tnd:
            raise ValueError("Line total does not match the approved unit price and quantity.")
        return self


class CreateCustomerOrderInput(StrictSchema):
    customer_id: str = Field(min_length=1, max_length=64)
    operation_id: str = Field(min_length=8, max_length=100)
    approval_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    items: list[OrderItemInput] = Field(min_length=1, max_length=20)
    total_tnd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    source_evidence_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("customer_id")
    @classmethod
    def check_customer_id(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("operation_id")
    @classmethod
    def check_order_operation_id(cls, value: str) -> str:
        return validate_operation_id(value)

    @model_validator(mode="after")
    def check_proposal_totals_and_evidence(self):
        calculated = sum(
            (item.unit_price_tnd * item.quantity for item in self.items),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        if calculated != self.total_tnd:
            raise ValueError("Order total does not match the approved product snapshots.")
        product_ids = {item.product_id for item in self.items}
        if len(product_ids) != len(self.items) or product_ids != set(self.source_evidence_ids):
            raise ValueError("Product items and source evidence IDs must match one to one.")
        if len(self.source_evidence_ids) != len(set(self.source_evidence_ids)):
            raise ValueError("Duplicate product evidence IDs are not allowed.")
        return self


# ============================================================
# WRITE TOOL INPUTS
# ============================================================

class ApprovedWriteInput(StrictSchema):
    """Shared fields required for an approved write operation."""

    ticket_id: str = Field(min_length=1, max_length=64)
    operation_id: str = Field(min_length=8, max_length=100)
    approval_id: str = Field(min_length=1, max_length=128)

    @field_validator("ticket_id")
    @classmethod
    def check_ticket_id(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("operation_id")
    @classmethod
    def check_operation_id(cls, value: str) -> str:
        return validate_operation_id(value)


class UpdateTicketInput(ApprovedWriteInput):
    status: TicketStatus
    labels: list[str] = Field(min_length=1, max_length=10)
    response_text: str = Field(min_length=1, max_length=2000)

    @field_validator("labels")
    @classmethod
    def check_labels(cls, labels: list[str]) -> list[str]:
        if len(labels) != len(set(labels)):
            raise ValueError("Duplicate labels are not allowed.")

        invalid = set(labels) - ALLOWED_LABELS

        if invalid:
            raise ValueError(
                f"Unsupported labels: {', '.join(sorted(invalid))}"
            )

        return labels


class SendSupportNotificationInput(StrictSchema):
    """Sandbox-only notification; callers cannot select a delivery provider."""

    ticket_id: str | None = Field(default=None, max_length=64)
    customer_id: str | None = Field(default=None, max_length=64)
    operation_id: str = Field(min_length=8, max_length=100)
    approval_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    channel: str = Field(pattern="^(email|phone|chat|sandbox_outbox)$")
    subject: str | None = Field(default=None, max_length=200)
    message: str = Field(min_length=1, max_length=5000)

    @field_validator("operation_id")
    @classmethod
    def check_notification_operation_id(cls, value: str) -> str:
        return validate_operation_id(value)

    @model_validator(mode="after")
    def check_context(self):
        if (self.ticket_id is None) == (self.customer_id is None):
            raise ValueError("Provide exactly one ticket_id or customer_id.")
        if self.ticket_id is not None:
            validate_identifier(self.ticket_id)
        if self.customer_id is not None:
            validate_identifier(self.customer_id)
        return self


class CreateRefundRequestInput(ApprovedWriteInput):
    order_id: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("order_id")
    @classmethod
    def check_order_id(cls, value: str) -> str:
        return validate_identifier(value)


class CreateEscalationTaskInput(ApprovedWriteInput):
    team: EscalationTeam
    priority: EscalationPriority
    reason: str = Field(min_length=5, max_length=1000)
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def check_due_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_at must include a timezone.")

        return value


# ============================================================
# TOOL OUTPUTS
# ============================================================

class ToolSuccess(StrictSchema):
    success: bool = True
    operation_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ToolError(StrictSchema):
    success: bool = False
    error: str
    message: str
    retryable: bool = False


class TicketOutput(StrictSchema):
    ticket_id: str
    customer_id: str | None
    order_id: str | None
    untrusted_customer_message: str
    labels: list[str]
    status: str
    created_at: str


class CustomerOutput(StrictSchema):
    customer_id: str
    display_name: str
    contact_channel: str
    account_status: str
    relevant_notes: str | None = None


class OrderOutput(StrictSchema):
    order_id: str
    customer_id: str
    order_status: str
    item_summary: str
    total_amount: Decimal
    currency: str
    shipment_status: str
    ordered_at: str
    shipped_at: str | None
    delivered_at: str | None
