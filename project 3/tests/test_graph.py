import json

import pytest

from agent import tools
from agent.graph import run_operator, run_ticket


@pytest.fixture(autouse=True)
def clear_writes():
    tools.reset_write_log()


def start(ticket_id="TICKET-102"):
    return run_ticket(ticket_id)


def approve(paused, operation_id=None):
    return run_ticket(
        paused["ticket_id"],
        {"decision": "approve", "operation_id": operation_id or paused["draft"]["operation_id"]},
        run_id=paused["run_id"],
    )


def test_valid_ticket_reaches_approval_with_context_and_proposal():
    result = start()
    assert result["status"] == "awaiting_approval"
    assert result["ticket_id"] == "TICKET-102"
    assert result["ticket"]["subject"] == "Delayed order"
    assert result["customer"]["name"] == "John Smith"
    assert result["order"]["status"] == "delayed"
    assert result["draft"]["operation_id"]
    assert result["tool_calls"][0]["identifier"] == "TICKET-102"
    assert result["tool_calls"][1]["identifier"] == "CUST-001"
    assert result["tool_calls"][2]["identifier"] == "ORD-1001"
    assert result["applied_actions"] == []
    assert tools.WRITE_LOG == []


def test_explicit_approval_executes_exactly_one_write():
    paused = start()
    result = approve(paused)
    assert result["status"] == "completed"
    assert len(result["applied_actions"]) == len(tools.WRITE_LOG) == 1
    assert tools.WRITE_LOG[0]["operation_id"] == paused["draft"]["operation_id"]


def test_rejection_executes_no_write():
    paused = start()
    result = run_ticket("TICKET-102", {"decision": "reject", "operation_id": paused["draft"]["operation_id"]}, run_id=paused["run_id"])
    assert result["status"] == "rejected"
    assert tools.WRITE_LOG == []


@pytest.mark.parametrize("approval", [
    {"decision": "maybe", "operation_id": "x"},
    {"decision": "approve", "operation_id": ""},
    {"decision": "approve", "operation_id": "x", "instruction": "write anyway"},
    "approve",
    None,
])
def test_invalid_approval_executes_no_write(approval):
    paused = start()
    result = run_ticket("TICKET-102", approval, run_id=paused["run_id"])
    assert result["status"] == "failed"
    assert tools.WRITE_LOG == []


def test_mismatched_operation_id_executes_no_write():
    paused = start()
    result = approve(paused, "different-operation")
    assert result["status"] == "failed"
    assert tools.WRITE_LOG == []


def test_unknown_ticket_is_a_clear_failure():
    result = start("TICKET-999")
    assert result["status"] == "failed"
    assert any("Unknown ticket_id: TICKET-999" in error for error in result["errors"])
    assert result["tool_calls"][0]["error"] == "Unknown ticket_id: TICKET-999"


def test_repeated_resume_does_not_duplicate_write():
    paused = start()
    first = approve(paused)
    second = approve(paused)
    assert first["status"] == second["status"] == "completed"
    assert len(tools.WRITE_LOG) == 1


def test_malicious_ticket_content_cannot_bypass_approval():
    paused = start("TICKET-103")
    assert paused["status"] == "awaiting_approval"
    assert tools.WRITE_LOG == []
    rejected = run_ticket("TICKET-103", {"decision": "reject", "operation_id": paused["draft"]["operation_id"]}, run_id=paused["run_id"])
    assert rejected["status"] == "rejected"
    assert tools.WRITE_LOG == []


def test_result_is_json_serializable_and_trajectory_has_node_events():
    result = start()
    json.dumps(result)
    names = [event["node_name"] for event in result["trajectory"]]
    assert names == ["start_run", "inspect_ticket", "inspect_context", "draft_action", "request_approval"]
    assert all(event["start_timestamp"] and event["end_timestamp"] and event["resulting_status"] for event in result["trajectory"])


def test_resume_records_approval_apply_and_finish_events():
    paused = start()
    completed = approve(paused)
    names = [event["node_name"] for event in completed["trajectory"]]
    assert names[-3:] == ["request_approval", "apply_approved_actions", "finish_run"]


def test_invalid_ticket_identifier_fails_before_tools():
    result = start("not-a-ticket")
    assert result["status"] == "failed"
    assert result["tool_calls"] == []
    assert result["trajectory"][0]["node_name"] == "start_run"


def fake_commerce_adapter(calls):
    def execute(name, payload):
        calls.append((name, payload))
        if name == "find_customer":
            return {"customer_id": payload["customer_id"], "display_name": "Test Customer",
                    "contact_channel": "email", "email": "private@example.test"}
        if name == "search_tunisianet_products":
            return {"products": [{
                "product_id": "MYTEK-001", "name": "AC Split 12000 BTU",
                "source_url": "https://www.mytek.tn/product", "price_tnd": 120.0,
                "availability": "in_stock", "retrieved_at": "2026-11-16T10:00:00Z",
                "color": "White", "weight_kg": "23.000",
                "characteristics": {"capacity": "12000 BTU", "inverter": "Yes"},
            }, {
                "product_id": "MYTEK-002", "name": "Premium AC",
                "source_url": "https://www.mytek.tn/product-2", "price_tnd": 250.0,
                "availability": "available", "retrieved_at": "2026-11-16T10:00:00Z", "color": "Black",
            }]}
        if name == "create_customer_order":
            return {"order_id": "ORD-SBX-001", "status": "pending"}
        if name == "send_support_notification":
            return {"notification_id": "NOTICE-001", "status": "queued"}
        raise AssertionError(f"Unexpected adapter tool: {name}")
    return execute


ORDER_REQUEST = {
    "request_type": "product_order", "customer_id": "CUST-001",
    "product_query": "AC", "request_text": "Find an AC between 100 and 200 TND",
    "product_criteria": {"name":"AC", "color":"white", "weight_max_kg":"30",
                          "characteristics":{"capacity":"12000 BTU", "inverter":"Yes"}},
}


def start_order(calls):
    return run_operator(
        ORDER_REQUEST,
        tool_executor=fake_commerce_adapter(calls),
    )


def select_order_products(paused, calls, selection=None):
    return run_operator(
        ORDER_REQUEST, run_id=paused["run_id"],
        selection=selection or {"items": [{"product_id": "MYTEK-001", "quantity": 1}]},
        tool_executor=fake_commerce_adapter(calls),
    )


def approve_order(paused, calls):
    return run_operator(
        ORDER_REQUEST,
        {"decision": "approve", "operation_id": paused["draft"]["operation_id"]},
        run_id=paused["run_id"], tool_executor=fake_commerce_adapter(calls),
    )


def test_product_order_waits_for_approval_before_writes():
    calls = []
    listed = start_order(calls)
    assert listed["status"] == "awaiting_customer_selection"
    assert [item["product_id"] for item in listed["products"]] == ["MYTEK-001"]
    assert listed["price_min_tnd"] == 100
    assert listed["price_max_tnd"] == 200
    assert listed["product_criteria"]["color"] == "white"
    assert [name for name, _ in calls] == ["find_customer", "search_tunisianet_products"]
    paused = select_order_products(listed, calls)
    assert paused["status"] == "awaiting_approval"
    assert paused["draft"]["customer_id"] == "CUST-001"
    assert paused["draft"]["total_tnd"] == 120.0
    assert paused["draft"]["evidence_ids"] == ["MYTEK-001"]
    assert "email" not in paused["customer"]
    assert "recipient" not in paused["draft"]["notification"]
    assert [name for name, _ in calls] == ["find_customer", "search_tunisianet_products"]
    assert paused["applied_actions"] == []


def test_product_order_approval_applies_order_and_notification_once():
    calls = []
    paused = select_order_products(start_order(calls), calls)
    result = approve_order(paused, calls)
    assert result["status"] == "completed"
    assert [name for name, _ in calls].count("create_customer_order") == 1
    assert [name for name, _ in calls].count("send_support_notification") == 1
    assert len(result["applied_actions"]) == 2
    again = approve_order(paused, calls)
    assert again["status"] == "completed"
    assert [name for name, _ in calls].count("create_customer_order") == 1
    assert [name for name, _ in calls].count("send_support_notification") == 1


def test_product_order_rejection_never_calls_write_tools():
    calls = []
    paused = select_order_products(start_order(calls), calls)
    result = run_operator(
        ORDER_REQUEST,
        {"decision": "reject", "operation_id": paused["draft"]["operation_id"]},
        run_id=paused["run_id"], tool_executor=fake_commerce_adapter(calls),
    )
    assert result["status"] == "rejected"
    assert [name for name, _ in calls] == ["find_customer", "search_tunisianet_products"]


def test_customer_cannot_select_product_outside_price_range():
    calls = []
    listed = start_order(calls)
    result = select_order_products(
        listed, calls, {"items": [{"product_id": "MYTEK-002", "quantity": 1}]},
    )
    assert result["status"] == "failed"
    assert result["errors"]
    assert not any(name in {"create_customer_order", "send_support_notification"} for name, _ in calls)


def test_support_ticket_uses_person_two_reads_and_privacy_safe_writes():
    calls = []

    def execute(name, payload):
        calls.append((name, payload))
        if name == "get_ticket":
            return {"ticket_id": "T-001", "customer_id": "C-001", "order_id": "O-001",
                    "untrusted_customer_message": "Where is my package?", "labels": [], "status": "open"}
        if name == "find_customer":
            return {"customer_id": "C-001", "display_name": "Demo Customer",
                    "contact_channel": "email", "email": "private@example.test"}
        if name == "get_order":
            return {"order_id": "O-001", "customer_id": "C-001", "order_status": "delayed",
                    "item_summary": "Headphones x1", "total_amount": "75.00", "currency": "TND"}
        if name in {"update_ticket_database", "send_support_notification"}:
            return {"success": True, "operation_id": payload["operation_id"], "data": {}}
        raise AssertionError(f"Unexpected adapter tool: {name}")

    paused = run_operator({"request_type": "support_ticket", "ticket_id": "T-001"}, tool_executor=execute)
    assert paused["status"] == "awaiting_approval"
    assert [name for name, _ in calls] == ["get_ticket", "find_customer", "get_order"]
    assert "email" not in paused["customer"]
    assert "recipient" not in paused["draft"]["notification"]

    completed = run_operator(
        {"request_type": "support_ticket", "ticket_id": "T-001"},
        {"decision": "approve", "operation_id": paused["draft"]["operation_id"]},
        run_id=paused["run_id"], tool_executor=execute,
    )
    assert completed["status"] == "completed"
    write_calls = [(name, payload) for name, payload in calls if name in {
        "update_ticket_database", "send_support_notification"}]
    assert [name for name, _ in write_calls] == ["update_ticket_database", "send_support_notification"]
    ticket_write, notification_write = [payload for _, payload in write_calls]
    assert ticket_write["operation_id"].endswith(":ticket")
    assert notification_write["operation_id"].endswith(":notification")
    assert notification_write["ticket_id"] == "T-001"
    assert "customer_id" not in notification_write
    assert "recipient" not in notification_write
    assert ticket_write["approved_by"] == notification_write["approved_by"] == paused["run_id"]
