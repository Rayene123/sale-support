"""Graph adapter for the public Person 2 tool contracts.

The approval resolver is supplied by trusted application code. It looks up an
already-created approval record; it must never create approval from this call.
The database independently checks the record against the exact write payload.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.tools.mytek import search_mytek_products, search_tunisianet_products
from agent.tools.reads import find_customer, get_order, get_ticket
from agent.tools.writes import (
    create_customer_order,
    send_support_notification,
    update_ticket_database,
)
from sandbox.store import SandboxStore


ApprovalLookup = Callable[[str, str, str, dict[str, Any]], str | None]


class ToolDispatchError(RuntimeError):
    """Safe failure raised when a tool returns an unsuccessful result."""


def make_sandbox_approval_lookup(
    store: SandboxStore,
) -> ApprovalLookup:
    """Resolve one pre-existing approval row without creating approvals.

    The client must be the sandbox's trusted service-role client. Exact payload
    equality, expiration, and action authorization are checked again in SQL.
    """
    if store.client is None:
        raise ValueError("Approval lookup requires the connected sandbox store.")

    def lookup(action: str, operation_id: str, run_id: str, _payload: dict[str, Any]) -> str | None:
        try:
            response = (
                store.client.table("approval_records")
                .select("approval_id")
                .eq("action_type", action)
                .eq("operation_id", operation_id)
                .eq("run_id", run_id)
                .eq("status", "approved")
                .limit(2)
                .execute()
            )
            records = response.data or []
            if len(records) != 1:
                return None
            approval_id = records[0].get("approval_id")
            return approval_id if isinstance(approval_id, str) and approval_id else None
        except Exception:
            # Do not turn lookup failure into approval or expose database detail.
            return None

    return lookup


def make_tool_executor(
    *,
    approval_lookup: ApprovalLookup,
    store: SandboxStore | None = None,
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Build the `(tool_name, payload)` adapter used by Person 1's graph.

    `approval_lookup(action, operation_id, run_id, payload)` must return only
    the ID of an approval already persisted by the trusted human approval
    service. The SQL function checks its action, run, expiry, and full payload.
    """
    if not callable(approval_lookup):
        raise TypeError("A trusted approval lookup is required.")

    def execute(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ToolDispatchError("Tool payload must be an object.")
        if tool_name == "search_tunisianet_products":
            result = search_tunisianet_products(
                payload.get("query", ""), criteria=payload.get("criteria"),
            )
        elif tool_name == "search_mytek_products":
            result = search_mytek_products(payload.get("query", ""), criteria=payload.get("criteria"))
        elif tool_name == "find_customer":
            result = find_customer(
                customer_id=payload.get("customer_id"),
                email=payload.get("email"),
                store=store,
            )
        elif tool_name == "get_ticket":
            result = get_ticket(payload.get("ticket_id", ""), store=store)
        elif tool_name == "get_order":
            result = get_order(payload.get("order_id", ""), store=store)
        elif tool_name in {
            "create_customer_order",
            "send_support_notification",
            "update_ticket_database",
        }:
            operation_id = payload.get("operation_id")
            run_id = payload.get("approved_by")
            if not isinstance(operation_id, str) or not isinstance(run_id, str):
                raise ToolDispatchError("Write is missing its operation or run reference.")
            # Never consume an approval ID from graph/model input. Resolve an
            # existing trusted row, then let SQL bind it to the exact payload.
            if tool_name == "create_customer_order":
                approval_payload = {key: payload.get(key) for key in (
                    "customer_id", "items", "total_tnd", "source_evidence_ids")
                }
            elif tool_name == "send_support_notification":
                approval_payload = {key: payload.get(key) for key in (
                    "ticket_id", "customer_id", "channel", "subject", "message")
                }
            else:
                approval_payload = {key: payload.get(key) for key in (
                    "ticket_id", "status", "labels", "response_text")
                }
            approval_id = approval_lookup(tool_name, operation_id, run_id, approval_payload)
            if not isinstance(approval_id, str) or not approval_id.strip():
                raise ToolDispatchError("No matching trusted approval record exists.")
            if tool_name == "create_customer_order":
                result = create_customer_order(
                    customer_id=payload.get("customer_id", ""),
                    items=payload.get("items", []),
                    operation_id=operation_id,
                    approval_id=approval_id,
                    run_id=run_id,
                    total_tnd=payload.get("total_tnd"),
                    source_evidence_ids=payload.get("source_evidence_ids", []),
                    store=store,
                )
            elif tool_name == "send_support_notification":
                result = send_support_notification(
                    operation_id=operation_id,
                    channel=payload.get("channel") or "sandbox_outbox",
                    subject=payload.get("subject"),
                    message=payload.get("message", ""),
                    approval_id=approval_id,
                    run_id=run_id,
                    ticket_id=payload.get("ticket_id"),
                    customer_id=payload.get("customer_id"),
                    store=store,
                )
            else:
                result = update_ticket_database(
                    ticket_id=payload.get("ticket_id", ""),
                    operation_id=operation_id,
                    status=payload.get("status", ""),
                    labels=payload.get("labels", []),
                    response_text=payload.get("response_text", ""),
                    approval_id=approval_id,
                    store=store,
                )
        else:
            raise ToolDispatchError("Tool name is not allowlisted.")

        if tool_name in {"find_customer", "get_ticket", "get_order"}:
            if not isinstance(result, dict) or result.get("success") is not True:
                code = result.get("error", "tool_failed") if isinstance(result, dict) else "tool_failed"
                raise ToolDispatchError(str(code))
            return result.get("data", {})
        if not isinstance(result, dict) or result.get("success") is not True:
            code = result.get("error", "tool_failed") if isinstance(result, dict) else "tool_failed"
            raise ToolDispatchError(str(code))
        return result

    return execute
