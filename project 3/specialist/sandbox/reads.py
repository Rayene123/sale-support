
"""Read-only support tools backed by the sandbox store."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from specialist.sandbox.store import SandboxStore, StoreError
from specialist.sandbox.schemas import (
    GetTicketInput,
    FindCustomerInput,
    GetOrderInput,
    TicketOutput,
    CustomerOutput,
    OrderOutput,
)

logger = logging.getLogger(__name__)


def _get_store(store: SandboxStore | None) -> SandboxStore:
    """Use an injected store for tests or connect to the sandbox."""

    return store if store is not None else SandboxStore.from_env()


def _error_result(
    code: str,
    message: str,
    retryable: bool = False,
) -> dict[str, Any]:
    """Return a consistent, model-safe tool error."""

    return {
        "success": False,
        "error": code,
        "message": message,
        "retryable": retryable,
    }


def _handle_error(error: Exception) -> dict[str, Any]:
    """Convert internal exceptions into short actionable errors."""

    if isinstance(error, StoreError):
        return _error_result(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
        )

    if isinstance(error, ValidationError):
        return _error_result(
            code="invalid_tool_input",
            message="The supplied tool arguments are invalid.",
        )

    logger.exception("Unexpected read-tool failure")

    return _error_result(
        code="sandbox_database_failed",
        message="The sandbox read operation failed.",
        retryable=True,
    )


def get_ticket(
    ticket_id: str,
    *,
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Retrieve a ticket and clearly identify its message as untrusted."""

    try:
        request = GetTicketInput(ticket_id=ticket_id)
        result = _get_store(store).get_ticket(request.ticket_id)

        ticket = TicketOutput.model_validate(result)

        return {
            "success": True,
            "data": ticket.model_dump(mode="json"),
        }

    except (StoreError, ValidationError) as error:
        return _handle_error(error)
    except Exception as error:
        return _handle_error(error)


def find_customer(
    *,
    customer_id: str | None = None,
    email: str | None = None,
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Find one customer by exactly one identifier."""

    try:
        request = FindCustomerInput(
            customer_id=customer_id,
            email=email,
        )

        result = _get_store(store).find_customer(
            customer_id=request.customer_id,
            email=request.email,
        )

        safe_result = {
    key: result.get(key)
    for key in (
        "customer_id",
        "display_name",
        "contact_channel",
        "account_status",
        "relevant_notes",
    )
}

        customer = CustomerOutput.model_validate(safe_result)

        return {
            "success": True,
            "data": customer.model_dump(mode="json"),
        }

    except (StoreError, ValidationError) as error:
        return _handle_error(error)
    except Exception as error:
        return _handle_error(error)


def get_order(
    order_id: str,
    *,
    store: SandboxStore | None = None,
) -> dict[str, Any]:
    """Retrieve order details and shipment information."""

    try:
        request = GetOrderInput(order_id=order_id)
        result = _get_store(store).get_order(request.order_id)

        order = OrderOutput.model_validate(result)

        return {
            "success": True,
            "data": order.model_dump(mode="json"),
        }

    except (StoreError, ValidationError) as error:
        return _handle_error(error)
    except Exception as error:
        return _handle_error(error)
