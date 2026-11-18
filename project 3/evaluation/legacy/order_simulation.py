"""Replay-safe simulated tool adapter for the original ordering regression cases."""
from copy import deepcopy
from typing import Any

from specialist.catalog.tunisianet import search_tunisianet_products
from specialist.support import fixtures


_DEMO_RECEIPTS: dict[str, dict[str, Any]] = {}


def _customer_executor(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "find_customer":
        customer = fixtures.find_customer(payload.get("customer_id", ""))
        return {"customer_id": customer["customer_id"], "name": customer["name"]}
    if name == "search_tunisianet_products":
        return search_tunisianet_products(payload.get("query", ""), criteria=payload.get("criteria"))
    if name in {"create_customer_order", "send_support_notification"}:
        # This adapter is a process-local simulation, never the Supabase approval service.
        operation_id = payload.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id or not payload.get("approved_by"):
            raise ValueError("Missing demo operation/run reference")
        record = {"action": name, "payload": deepcopy(payload)}
        if operation_id in _DEMO_RECEIPTS:
            previous = _DEMO_RECEIPTS[operation_id]
            if previous["record"] != record:
                raise ValueError("Demo operation ID conflicts with a different payload")
            return deepcopy(previous["result"])
        result = {"success": True, "simulated": True, "operation_id": operation_id,
                  "status": "pending" if name == "create_customer_order" else "queued"}
        _DEMO_RECEIPTS[operation_id] = {"record": record, "result": result}
        return deepcopy(result)
    raise RuntimeError("Unknown demo tool")
