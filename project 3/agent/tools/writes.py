
"""Approved, idempotent write tools for the support sandbox."""

import logging
from decimal import Decimal
from typing import Any, Callable

from pydantic import ValidationError

from sandbox.store import SandboxStore, StoreError, DatabaseFailure

from agent.tools.schemas import (
    UpdateTicketInput,
    SendSupportNotificationInput,
    CreateCustomerOrderInput,
    CreateRefundRequestInput,
    CreateEscalationTaskInput,
)

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Shared helpers
# -------------------------------------------------------------------

def _get_store(store: SandboxStore | None) -> SandboxStore:
    """Use an injected store or initialize the approved sandbox."""

    return store if store is not None else SandboxStore.from_env()


def _error_result(
    code: str,
    message: str,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "success": False,
        "error": code,
        "message": message,
        "retryable": retryable,
    }


def _handle_error(exc: Exception) -> dict[str, Any]:
    """Convert internal exceptions into safe tool error results."""

    if isinstance(exc, ValidationError):
        return _error_result(
            "invalid_input",
            "The supplied input is invalid. Check the required fields and allowed values.",
        )

    if isinstance(exc, StoreError):
        return _error_result(
            exc.code,
            exc.message,
            exc.retryable,
        )

    if isinstance(exc, DatabaseFailure):
        return _error_result(
            "sandbox_database_failed",
            str(exc),
            retryable=True,
        )

    # PostgreSQL exceptions raised by the RPC function.
    # Only expose recognized, short error codes.
    error_text = str(exc)

    known_errors = {
        "operation_conflict": (
            "operation_conflict",
            "This operation ID was already used with different content.",
            False,
        ),
        "ticket_not_found": (
            "ticket_not_found",
            "The specified ticket does not exist.",
            False,
        ),
        "customer_not_found": (
            "customer_not_found",
            "The ticket's customer could not be found.",
            False,
        ),
        "order_not_found": (
            "order_not_found",
            "The specified order does not exist.",
            False,
        ),
        "refund_order_ownership_mismatch": (
            "refund_order_ownership_mismatch",
            "The order does not belong to the ticket's customer.",
            False,
        ),
        "refund_amount_exceeds_order": (
            "refund_amount_exceeds_order",
            "The requested refund exceeds the order total.",
            False,
        ),
        "invalid_update_field": (
    "invalid_update_field",
    "The update contains fields that are not allowed.",
    False,
),
        "invalid_escalation_team": (
            "invalid_escalation_team",
            "The selected escalation team is not allowed.",
            False,
        ),
        "invalid_escalation_priority": (
            "invalid_escalation_priority",
            "The selected escalation priority is not allowed.",
            False,
        ),
        "approval_invalid_or_expired": (
            "approval_invalid_or_expired",
            "The approval is missing, expired, revoked, or already consumed.",
            False,
        ),
        "approval_payload_mismatch": (
            "approval_invalid_or_expired",
            "The approval does not match this action, run, or exact payload.",
            False,
        ),
        "invalid_order_payload": ("invalid_input", "The approved order payload is invalid.", False),
        "invalid_order_item": ("invalid_input", "An approved order item is invalid.", False),
        "duplicate_product_id": ("invalid_input", "An order cannot include the same product more than once.", False),
        "order_total_mismatch": ("invalid_input", "The order total does not match the approved item prices.", False),
        "order_evidence_mismatch": ("invalid_input", "The order product IDs do not match the approved source evidence.", False),
        "invalid_notification_payload": ("invalid_input", "The approved notification payload is invalid.", False),
        "invalid_action_type": ("invalid_input", "The requested sandbox action is not allowed.", False),
        "invalid_operation_id": ("invalid_input", "The operation ID is invalid.", False),
        "invalid_write_payload": ("invalid_input", "The approved write payload is invalid.", False),
        "invalid_approval_record": ("invalid_approval", "The trusted approval record is invalid.", False),
        "service_role_required": ("sandbox_permission_denied", "The sandbox write requires the trusted service role.", False),
    }

    for marker, result in known_errors.items():
        if marker in error_text:
            return _error_result(*result)

    logger.exception("Unexpected support write failure")

    return _error_result(
        "sandbox_database_failed",
        "The sandbox write failed. Retry using the same operation ID if the outcome is uncertain.",
        retryable=True,
    )


def _execute_write(
    action_type: str,
    input_schema: type,
    values: dict[str, Any],
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Validate, execute, and safely return one approved write."""

    try:
        # 1. Validate arguments before accessing the database.
        validated = input_schema.model_validate(values)

        payload = validated.model_dump(mode="json")
        operation_id = validated.operation_id

# operation_id is passed separately to the SQL RPC function.
        payload.pop("operation_id", None)

        # 2. Get the configured sandbox.
        active_store = _get_store(store)

        if active_store.client is None:
            return _error_result(
                "sandbox_database_failed",
                "Write operations require the configured Supabase sandbox.",
                retryable=False,
            )

        # 3. Simulate a failure before persistence, if configured.
        active_store.before_write(operation_id)

        # 4. Call the transactional PostgreSQL function.
        response = active_store.client.rpc(
            "execute_support_write",
            {
                "p_action_type": action_type,
                "p_operation_id": operation_id,
                "p_payload": payload,
            },
        ).execute()

        result = response.data

        if not isinstance(result, dict):
            raise DatabaseFailure(
                "The sandbox returned an unexpected write response."
            )

        if result.get("success") is not True:
            raise DatabaseFailure(
                "The sandbox did not confirm the write."
            )

        # 5. Simulate a lost response after persistence, if configured.
        # The database has already committed. Retrying the same
        # operation ID will return the stored idempotent result.
        active_store.after_write(operation_id)

        return result

    except Exception as exc:
        return _handle_error(exc)


def _execute_commerce_write(
    action_type: str,
    operation_id: str,
    approval_id: str,
    run_id: str,
    payload: dict[str, Any],
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Run a commerce/notification write through its separate SQL boundary."""
    try:
        active_store = _get_store(store)
        if active_store.client is None:
            return _error_result("sandbox_database_failed", "Write operations require the configured Supabase sandbox.")
        active_store.before_write(operation_id)
        response = active_store.client.rpc("execute_approved_commerce_write", {
            "p_action_type": action_type,
            "p_operation_id": operation_id,
            "p_approval_id": approval_id,
            "p_run_id": run_id,
            "p_payload": payload,
        }).execute()
        result = response.data
        if not isinstance(result, dict) or result.get("success") is not True:
            raise DatabaseFailure("The sandbox did not confirm the approved write.")
        active_store.after_write(operation_id)
        return result
    except Exception as exc:
        return _handle_error(exc)


# -------------------------------------------------------------------
# Tool 1: Update ticket
# -------------------------------------------------------------------

def update_ticket_database(
    ticket_id: str,
    operation_id: str,
    status: str,
    labels: list[str],
    response_text: str,
    approval_id: str,
    *,
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Update an allowlisted set of ticket fields after approval."""

    return _execute_write(
        action_type="update_ticket_database",
        input_schema=UpdateTicketInput,
        values={
            "ticket_id": ticket_id,
            "operation_id": operation_id,
            "status": status,
            "labels": labels,
            "response_text": response_text,
            "approval_id": approval_id,
        },
        store=store,
    )


# -------------------------------------------------------------------
# Tool 2: Queue sandbox notification
# -------------------------------------------------------------------

def send_support_notification(
    operation_id: str,
    channel: str,
    message: str,
    approval_id: str,
    run_id: str,
    *,
    ticket_id: str | None = None,
    customer_id: str | None = None,
    subject: str | None = None,
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Queue a generic notification in the sandbox. Nothing is delivered."""

    try:
        validated = SendSupportNotificationInput.model_validate({
            "ticket_id": ticket_id,
            "customer_id": customer_id,
            "operation_id": operation_id,
            "channel": channel,
            "subject": subject,
            "message": message,
            "approval_id": approval_id,
            "run_id": run_id,
        })
        payload = validated.model_dump(mode="json", exclude_unset=True)
        for trusted_field in ("operation_id", "approval_id", "run_id"):
            payload.pop(trusted_field, None)
        return _execute_commerce_write("send_support_notification", validated.operation_id,
            validated.approval_id, validated.run_id, payload, store)
    except Exception as exc:
        return _handle_error(exc)


def create_customer_order(
    customer_id: str,
    items: list[dict[str, Any]],
    operation_id: str,
    approval_id: str,
    run_id: str,
    total_tnd: Any,
    source_evidence_ids: list[str],
    *,
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Create an internal sandbox order record; never contacts a retailer."""

    try:
        validated = CreateCustomerOrderInput.model_validate({
            "customer_id": customer_id, "items": items,
            "operation_id": operation_id, "approval_id": approval_id,
            "run_id": run_id, "total_tnd": total_tnd,
            "source_evidence_ids": source_evidence_ids,
        })
        payload = validated.model_dump(mode="json", exclude_unset=True)
        calculated_total = sum(
            (item.unit_price_tnd * item.quantity for item in validated.items),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        payload["total_tnd"] = str(calculated_total)
        for trusted_field in ("operation_id", "approval_id", "run_id"):
            payload.pop(trusted_field, None)
        return _execute_commerce_write("create_customer_order", validated.operation_id,
            validated.approval_id, validated.run_id, payload, store)
    except Exception as exc:
        return _handle_error(exc)


# -------------------------------------------------------------------
# Tool 3: Create refund request
# -------------------------------------------------------------------

def create_refund_request(
    ticket_id: str,
    order_id: str,
    operation_id: str,
    amount: Any,
    reason: str,
    approval_id: str,
    *,
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Create a pending refund request after approval.

    This does not transfer money.
    """

    return _execute_write(
        action_type="create_refund_request",
        input_schema=CreateRefundRequestInput,
        values={
            "ticket_id": ticket_id,
            "order_id": order_id,
            "operation_id": operation_id,
            "amount": amount,
            "reason": reason,
            "approval_id": approval_id,
        },
        store=store,
    )


# -------------------------------------------------------------------
# Tool 4: Create escalation task
# -------------------------------------------------------------------

def create_escalation_task(
    ticket_id: str,
    operation_id: str,
    team: str,
    priority: str,
    reason: str,
    due_at: str,
    approval_id: str,
    *,
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Create a pending escalation task after approval."""

    return _execute_write(
        action_type="create_escalation_task",
        input_schema=CreateEscalationTaskInput,
        values={
            "ticket_id": ticket_id,
            "operation_id": operation_id,
            "team": team,
            "priority": priority,
            "reason": reason,
            "due_at": due_at,
            "approval_id": approval_id,
        },
        store=store,
    )
