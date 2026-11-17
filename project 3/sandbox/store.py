
"""Database access layer for the Sale Support sandbox.

Supports:
- Supabase-backed reads.
- In-memory reads for offline tests.
- Deterministic transient read and write failure simulation.

Write transactions and idempotency will be implemented through
dedicated PostgreSQL RPC functions in the next stage.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FAULTS_FILE = PROJECT_ROOT / "sandbox" / "data" / "faults.json"
ENV_FILE = PROJECT_ROOT.parent / ".env"


class StoreError(Exception):
    """Base class for safe, application-level store errors."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


class RecordNotFound(StoreError):
    """Raised when a requested record does not exist."""

    def __init__(self, record_type: str, record_id: str):
        super().__init__(
            code=f"{record_type}_not_found",
            message=f"{record_type.capitalize()} '{record_id}' was not found.",
            retryable=False,
        )


class DatabaseFailure(StoreError):
    """Raised when a database operation fails."""

    def __init__(self, message: str = "The sandbox database operation failed."):
        super().__init__(
            code="sandbox_database_failed",
            message=message,
            retryable=True,
        )


class OperationConflict(StoreError):
    """Raised when an operation ID is reused with different content."""

    def __init__(self):
        super().__init__(
            code="operation_conflict",
            message="This operation ID was already used with different content.",
            retryable=False,
        )


class SandboxStore:
    """Accesses sandbox records using Supabase or local in-memory data."""

    def __init__(
        self,
        supabase_client: Client | None = None,
        local_data: dict[str, list[dict[str, Any]]] | None = None,
        faults_file: Path | str | None = None,
    ):
        self.client = supabase_client
        self.local_data = {
            table: [dict(row) for row in rows]
            for table, rows in (local_data or {}).items()
        }

        self.mode = "supabase" if self.client is not None else "memory"

        self.faults_file = Path(faults_file) if faults_file else FAULTS_FILE
        self.faults = self._load_faults()

        # Track which one-shot failures have already been triggered.
        self._triggered_failures: set[str] = set()

    @classmethod
    def from_env(cls) -> "SandboxStore":
        """Create a store connected to the configured Supabase sandbox."""

        load_dotenv(ENV_FILE)

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            raise DatabaseFailure(
                "Supabase configuration is missing. Check the project .env file."
            )

        # Refuse to connect if the project is not explicitly identified
        # as a sandbox. The URL is checked against an explicit allowlist.
        allowed_url = os.getenv("SUPABASE_SANDBOX_URL")

        if not allowed_url or url.rstrip("/") != allowed_url.rstrip("/"):
            raise DatabaseFailure(
                "Supabase URL is not approved as the dedicated sandbox URL."
            )

        try:
            client = create_client(url, key)
            return cls(supabase_client=client)
        except Exception:
            logger.exception("Could not initialize Supabase client")
            raise DatabaseFailure() from None

    @classmethod
    def in_memory(
        cls,
        data: dict[str, list[dict[str, Any]]],
        faults_file: Path | str | None = None,
    ) -> "SandboxStore":
        """Create an offline store for deterministic tests."""

        return cls(
            supabase_client=None,
            local_data=data,
            faults_file=faults_file,
        )

    def _load_faults(self) -> dict[str, Any]:
        """Load deterministic failure fixtures."""

        if not self.faults_file.exists():
            return {"read_failures": [], "write_failures": []}

        try:
            with self.faults_file.open("r", encoding="utf-8") as file:
                result = json.load(file)

            return {
                "read_failures": result.get("read_failures", []),
                "write_failures": result.get("write_failures", []),
            }
        except (OSError, json.JSONDecodeError):
            logger.exception("Could not load failure fixtures")
            raise DatabaseFailure("The failure fixture file could not be loaded.") from None

    def _trigger_read_failure(self, action: str, record_id: str) -> None:
        """Trigger a configured one-time read failure."""

        for failure in self.faults["read_failures"]:
            fixture_id = failure.get("fixture_id")

            if (
                failure.get("action") == action
                and failure.get("ticket_id") == record_id
                and failure.get("mode") == "fail_once"
                and fixture_id not in self._triggered_failures
            ):
                self._triggered_failures.add(fixture_id)
                raise DatabaseFailure(
                    "A simulated temporary database read failure occurred."
                )

    def before_write(self, operation_id: str) -> None:
        """Simulate a failure before a write is persisted."""

        for failure in self.faults["write_failures"]:
            fixture_id = failure.get("fixture_id")

            if (
                failure.get("operation_id") == operation_id
                and failure.get("mode") == "before_persistence"
                and fixture_id not in self._triggered_failures
            ):
                self._triggered_failures.add(fixture_id)
                raise DatabaseFailure(
                    "A simulated failure occurred before persistence."
                )

    def after_write(self, operation_id: str) -> None:
        """Simulate a lost response after a write has been persisted."""

        for failure in self.faults["write_failures"]:
            fixture_id = failure.get("fixture_id")

            if (
                failure.get("operation_id") == operation_id
                and failure.get("mode") == "after_persistence"
                and fixture_id not in self._triggered_failures
            ):
                self._triggered_failures.add(fixture_id)
                raise DatabaseFailure(
                    "The write was persisted, but its response was lost."
                )

    def _get_one(
        self,
        table: str,
        id_column: str,
        record_id: str,
        record_type: str,
    ) -> dict[str, Any]:
        """Retrieve one record from the selected storage backend."""

        if not isinstance(record_id, str) or not record_id.strip():
            raise StoreError(
                "invalid_record_id",
                "A valid record ID is required.",
            )

        if self.client is not None:
            try:
                response = (
                    self.client.table(table)
                    .select("*")
                    .eq(id_column, record_id)
                    .limit(1)
                    .execute()
                )

                rows = response.data or []

            except Exception:
                logger.exception(
                    "Supabase read failed: table=%s id=%s",
                    table,
                    record_id,
                )
                raise DatabaseFailure() from None

        else:
            rows = [
                row
                for row in self.local_data.get(table, [])
                if row.get(id_column) == record_id
            ]

        if not rows:
            raise RecordNotFound(record_type, record_id)

        return dict(rows[0])

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        """Retrieve a ticket, treating its body as untrusted customer data."""

        self._trigger_read_failure("get_ticket", ticket_id)

        record = self._get_one(
            table="tickets",
            id_column="ticket_id",
            record_id=ticket_id,
            record_type="ticket",
        )

        return {
            "ticket_id": record.get("ticket_id"),
            "customer_id": record.get("customer_id"),
            "order_id": record.get("order_id"),
            "untrusted_customer_message": record.get("body"),
            "labels": record.get("labels", []),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
        }

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        """Retrieve only the approved customer fields."""

        record = self._get_one(
            table="clients",
            id_column="customer_id",
            record_id=customer_id,
            record_type="customer",
        )

        return {
            "customer_id": record.get("customer_id"),
            "email": record.get("email"),
            "display_name": record.get("display_name"),
            "contact_channel": record.get("contact_channel"),
            "account_status": record.get("account_status"),
            "relevant_notes": record.get("relevant_notes", ""),
        }

    def find_customer(
        self,
        customer_id: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        """Find a customer using exactly one ID or email."""

        if (customer_id is None) == (email is None):
            raise StoreError(
                "invalid_customer_lookup",
                "Provide exactly one customer ID or email.",
            )

        value = customer_id if customer_id is not None else email

        if not isinstance(value, str) or not value.strip() or len(value) > 254:
            raise StoreError(
                "invalid_customer_lookup",
                "The customer lookup value is invalid.",
            )

        if customer_id is not None:
            return self.get_customer(customer_id)

        if self.client is not None:
            try:
                response = (
                    self.client.table("clients")
                    .select("*")
                    .ilike("email", email.strip())
                    .limit(2)
                    .execute()
                )
                rows = response.data or []
            except Exception:
                logger.exception("Supabase customer email lookup failed")
                raise DatabaseFailure() from None
        else:
            normalized_email = email.strip().casefold()
            rows = [
                row for row in self.local_data.get("clients", [])
                if str(row.get("email", "")).casefold() == normalized_email
            ]

        if not rows:
            raise RecordNotFound("customer", email)

        if len(rows) != 1:
            raise StoreError(
                "ambiguous_customer_lookup",
                "The email matched more than one customer record.",
            )

        record = rows[0]

        return {
            "customer_id": record.get("customer_id"),
            "email": record.get("email"),
            "display_name": record.get("display_name"),
            "contact_channel": record.get("contact_channel"),
            "account_status": record.get("account_status"),
            "relevant_notes": record.get("relevant_notes", ""),
        }

    def get_order(self, order_id: str) -> dict[str, Any]:
        """Retrieve an order without exposing unnecessary customer data."""

        record = self._get_one(
            table="orders",
            id_column="order_id",
            record_id=order_id,
            record_type="order",
        )

        return {
            "order_id": record.get("order_id"),
            "customer_id": record.get("customer_id"),
            "order_status": record.get("order_status"),
            "item_summary": record.get("item_summary"),
            "total_amount": record.get("total_amount"),
            "currency": record.get("currency"),
            "shipment_status": record.get("shipment_status"),
            "ordered_at": record.get("ordered_at"),
            "shipped_at": record.get("shipped_at"),
            "delivered_at": record.get("delivered_at"),
        }
