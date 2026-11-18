"""One representation for both approval records and executed payloads."""
from decimal import Decimal
from .schemas import CreateCustomerOrderInput, SendSupportNotificationInput, UpdateTicketInput


def canonical_action_payload(action: str, payload: dict) -> dict:
    schemas = {"create_customer_order": CreateCustomerOrderInput,
               "send_support_notification": SendSupportNotificationInput,
               "update_ticket_database": UpdateTicketInput}
    if action not in schemas:
        raise ValueError("Unsupported approved action")
    values = dict(payload)
    values.update(operation_id="canonical-validation", approval_id="canonical-validation")
    if action != "update_ticket_database":
        values["run_id"] = "canonical-validation"
    if action == "send_support_notification":
        values.setdefault("ticket_id", None)
        values.setdefault("customer_id", None)
        values.setdefault("subject", None)
        values["channel"] = values.get("channel") or "sandbox_outbox"
    model = schemas[action].model_validate(values)
    result = model.model_dump(mode="json")
    for field in ("operation_id", "approval_id", "run_id"):
        result.pop(field, None)
    if action == "create_customer_order":
        for item in result["items"]:
            price = Decimal(item["unit_price_tnd"])
            item["unit_price_tnd"] = format(price, ".2f")
            item["line_total_tnd"] = format(price * item["quantity"], ".2f")
        result["total_tnd"] = format(model.total_tnd, ".2f")
    return result
