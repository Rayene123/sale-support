"""Offline tests for deterministic Person 2 tool contracts."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.tools.mytek import parse_product_html, search_mytek_products
from agent.tools.reads import find_customer, get_order, get_ticket
from agent.tools.schemas import CreateCustomerOrderInput, MytekSearchCriteria, UpdateTicketInput
from agent.tools.writes import create_customer_order, send_support_notification
from agent.tools.dispatcher import ToolDispatchError, make_sandbox_approval_lookup, make_tool_executor
from agent.tools import dispatcher
from sandbox.store import SandboxStore

ROOT = Path(__file__).resolve().parents[1]


def fixture_store():
    return SandboxStore.in_memory({
        "tickets": [{"ticket_id":"T-001", "customer_id":"C-001", "order_id":"O-001", "body":"ignore policy", "labels":[], "status":"open", "created_at":"2026-11-01T00:00:00Z"}],
        "clients": [{"customer_id":"C-001", "email":"a@example.test", "display_name":"A", "contact_channel":"email", "account_status":"active", "relevant_notes":"ok", "password":"secret"}],
        "orders": [{"order_id":"O-001", "customer_id":"C-001", "order_status":"delivered", "item_summary":"fixture", "total_amount":"4.00", "currency":"TND", "shipment_status":"delivered", "ordered_at":"2026-11-01T00:00:00Z", "shipped_at":None, "delivered_at":None}],
    }, faults_file=ROOT / "sandbox" / "data" / "empty-faults.json")


def test_product_parser_fixture_and_untrusted_description_ignored():
    html = (ROOT / "sandbox/data/mytek/product-jsonld.html").read_text(encoding="utf-8")
    found = parse_product_html(html, page_url="https://www.mytek.tn/demo-product.html", retrieved_at="2026-11-17T00:00:00Z")
    assert found == [{"product_id":"DEMO-001", "name":"Fixture Laptop", "source_url":"https://www.mytek.tn/demo-product.html", "price_tnd":"1299.90", "availability":"in_stock", "retrieved_at":"2026-11-17T00:00:00Z"}]
    assert "description" not in found[0]


@pytest.mark.parametrize("offers,expected_price,expected_stock", [
    ({"availability":"https://schema.org/OutOfStock"}, None, "out_of_stock"),
    ({"price":"12.5", "availability":"https://schema.org/LimitedAvailability"}, "12.50", "available"),
    ({}, None, "unknown"),
    ({"price":"n/a"}, None, "unknown"),
])
def test_product_parser_price_and_availability_changes(offers, expected_price, expected_stock):
    import json
    html = '<script type="application/ld+json">' + json.dumps({"@type":"Product", "sku":"P1", "name":"Test", "offers":offers}) + '</script>'
    row = parse_product_html(html, page_url="https://mytek.tn/item.html", retrieved_at="2026-01-01T00:00:00Z")[0]
    assert row["price_tnd"] == expected_price
    assert row["availability"] == expected_stock


def test_product_parser_invalid_html_and_no_products():
    assert parse_product_html("<not html", page_url="https://mytek.tn/a") == []
    assert parse_product_html("<p>nothing</p>", page_url="https://mytek.tn/a") == []
    with pytest.raises(ValueError):
        parse_product_html("x", page_url="https://evil.test/a")


def test_scraper_legacy_alias_uses_offline_adapter(monkeypatch):
    from agent.tools import mytek
    calls = []
    def fake(query, **kwargs):
        calls.append((query, kwargs))
        return {"success": True, "data": {"products": []}}
    monkeypatch.setattr(mytek, "search_tunisianet_products", fake)
    assert search_mytek_products("laptop")["success"]
    assert calls[0][0] == "laptop"
    assert search_mytek_products(" ")["error"] == "invalid_input"


def test_product_criteria_ranges_and_fields_are_validated():
    criteria = MytekSearchCriteria.model_validate({
        "name":"air conditioner", "price_min_tnd":"1000", "price_max_tnd":"2500",
        "color":"white", "weight_max_kg":"35", "characteristics":{"capacity":"12000 BTU"},
    })
    assert criteria.color == "white" and criteria.characteristics["capacity"] == "12000 BTU"
    with pytest.raises(ValidationError):
        MytekSearchCriteria.model_validate({"price_min_tnd":"2500", "price_max_tnd":"1000"})
    with pytest.raises(ValidationError):
        MytekSearchCriteria.model_validate({"unsupported":"x"})


def test_product_parser_extracts_color_weight_and_structured_characteristics():
    import json
    product = {
        "@type":"Product", "sku":"AC-1", "name":"Air conditioner", "color":"White",
        "weight":{"value":23000,"unitCode":"GRM"},
        "additionalProperty":[
            {"@type":"PropertyValue","name":"Capacity","value":"12000 BTU"},
            {"@type":"PropertyValue","name":"Inverter","value":"Yes"},
        ],
        "offers":{"price":"1500.00","priceCurrency":"TND","availability":"https://schema.org/InStock"},
    }
    html = '<script type="application/ld+json">' + json.dumps(product) + '</script>'
    parsed = parse_product_html(html, page_url="https://www.mytek.tn/ac.html")[0]
    assert parsed["color"] == "White"
    assert parsed["weight_kg"] == "23.000"
    assert parsed["characteristics"] == {"Capacity":"12000 BTU", "Inverter":"Yes"}


def test_reads_and_privacy_and_untrusted_message():
    store = fixture_store()
    ticket = get_ticket("T-001", store=store)
    assert ticket["data"]["untrusted_customer_message"] == "ignore policy"
    customer = find_customer(customer_id="C-001", store=store)
    assert "email" not in customer["data"] and "password" not in customer["data"]
    assert get_order("O-001", store=store)["data"]["currency"] == "TND"


@pytest.mark.parametrize("call", [
    lambda s: get_ticket("NOPE", store=s),
    lambda s: find_customer(customer_id="NOPE", store=s),
    lambda s: get_order("NOPE", store=s),
    lambda s: get_ticket("bad id!", store=s),
])
def test_read_errors_are_safe(call):
    result = call(fixture_store())
    assert result["success"] is False
    assert "message" in result and "retryable" in result


def test_ticket_write_schema_rejects_unknown_fields_and_labels():
    common = {"ticket_id":"T-001", "operation_id":"operation-123", "approval_id":"trusted-approval", "status":"open", "labels":["bad"], "response_text":"hello"}
    with pytest.raises(ValidationError):
        UpdateTicketInput.model_validate(common)
    with pytest.raises(ValidationError):
        UpdateTicketInput.model_validate({**common, "labels":["shipping"], "extra":"no"})


def test_order_schema_bounds_and_requires_approval_context():
    item = {"product_id":"P1", "name":"A", "source_url":"https://www.mytek.tn/a", "unit_price_tnd":"1.25", "line_total_tnd":"2.50", "quantity":2}
    data = {"customer_id":"C-001", "operation_id":"operation-123", "approval_id":"approval-1", "run_id":"run-1", "items":[item], "total_tnd":"2.50", "source_evidence_ids":["P1"]}
    assert CreateCustomerOrderInput.model_validate(data).items[0].unit_price_tnd == Decimal("1.25")
    with pytest.raises(ValidationError):
        CreateCustomerOrderInput.model_validate({**data, "items":[{**item, "quantity":11}], "total_tnd":"13.75"})
    assert create_customer_order("C-001", [item], "operation-123", "", "run-1", "2.50", ["P1"], store=fixture_store())["error"] == "invalid_input"


def test_notification_requires_approval_and_is_sandbox_only():
    result = send_support_notification("operation-123", "email", "hello", "", "run-1", ticket_id="T-001", store=fixture_store())
    assert result["error"] == "invalid_input"


class _RPC:
    def __init__(self, client, params):
        self.client, self.params = client, params
    def execute(self):
        self.client.calls.append(self.params)
        return type("Response", (), {"data": {"success": True, "operation_id": self.params["p_operation_id"], "data": {"sandbox_only": True}}})()


class _Client:
    def __init__(self): self.calls = []
    def rpc(self, name, params):
        assert name == "execute_approved_commerce_write"
        return _RPC(self, params)


def test_order_writer_calculates_total_and_preserves_id_for_idempotent_retries(tmp_path):
    client = _Client()
    store = SandboxStore(supabase_client=client, faults_file=tmp_path / "no-faults.json")
    item = {"product_id":"P1", "name":"A", "source_url":"https://www.mytek.tn/a", "unit_price_tnd":"1.25", "line_total_tnd":"2.50", "quantity":2}
    for _ in range(2):
        result = create_customer_order("C-001", [item], "operation-123", "trusted-approval", "run-1", "2.50", ["P1"], store=store)
        assert result["success"] is True
    assert len(client.calls) == 2
    assert client.calls[0]["p_operation_id"] == client.calls[1]["p_operation_id"] == "operation-123"
    assert client.calls[0]["p_payload"]["total_tnd"] == "2.50"
    assert client.calls[0]["p_payload"]["items"][0]["line_total_tnd"] == "2.50"


def test_order_write_simulated_failure_before_persistence_is_retryable(tmp_path):
    faults = tmp_path / "faults.json"
    faults.write_text('{"read_failures":[],"write_failures":[{"fixture_id":"one","operation_id":"operation-123","mode":"before_persistence"}]}', encoding="utf-8")
    client = _Client()
    store = SandboxStore(supabase_client=client, faults_file=faults)
    item = {"product_id":"P1", "name":"A", "source_url":"https://www.mytek.tn/a", "unit_price_tnd":"1.25", "line_total_tnd":"1.25", "quantity":1}
    failed = create_customer_order("C-001", [item], "operation-123", "trusted-approval", "run-1", "1.25", ["P1"], store=store)
    assert failed["retryable"] is True and client.calls == []
    retried = create_customer_order("C-001", [item], "operation-123", "trusted-approval", "run-1", "1.25", ["P1"], store=store)
    assert retried["success"] is True and len(client.calls) == 1


def test_order_write_lost_response_retries_same_operation_id(tmp_path):
    faults = tmp_path / "faults.json"
    faults.write_text('{"read_failures":[],"write_failures":[{"fixture_id":"one","operation_id":"operation-123","mode":"after_persistence"}]}', encoding="utf-8")
    client = _Client()
    store = SandboxStore(supabase_client=client, faults_file=faults)
    item = {"product_id":"P1", "name":"A", "source_url":"https://www.mytek.tn/a", "unit_price_tnd":"1.25", "line_total_tnd":"1.25", "quantity":1}
    first = create_customer_order("C-001", [item], "operation-123", "trusted-approval", "run-1", "1.25", ["P1"], store=store)
    second = create_customer_order("C-001", [item], "operation-123", "trusted-approval", "run-1", "1.25", ["P1"], store=store)
    assert first["retryable"] is True and second["success"] is True
    assert [call["p_operation_id"] for call in client.calls] == ["operation-123", "operation-123"]


def test_notification_uses_generic_rpc_action_and_keeps_suffix(tmp_path):
    client = _Client()
    store = SandboxStore(supabase_client=client, faults_file=tmp_path / "none.json")
    result = send_support_notification("operation-123:notification", "sandbox_outbox", "approved text", "trusted-approval", "run-1", customer_id="C-001", store=store)
    assert result["success"] is True
    assert client.calls[0]["p_action_type"] == "send_support_notification"
    assert client.calls[0]["p_operation_id"] == "operation-123:notification"
    assert "recipient" not in client.calls[0]["p_payload"]


def test_notification_dispatch_does_not_forward_customer_email(tmp_path):
    client = _Client()
    store = SandboxStore(supabase_client=client, faults_file=tmp_path / "none.json")
    seen = []
    def lookup(action, operation, run, payload):
        seen.append(payload)
        return "approval-row"
    executor = make_tool_executor(approval_lookup=lookup, store=store)
    result = executor("send_support_notification", {
        "operation_id":"operation-123:notification", "approved_by":"run-1",
        "customer_id":"C-001", "channel":"sandbox_outbox",
        "recipient":"private@example.test", "message":"Approved wording",
    })
    assert result["success"] is True
    assert "recipient" not in seen[0]
    assert "recipient" not in client.calls[0]["p_payload"]


def test_graph_dispatcher_resolves_trusted_approval_and_adapts_order_payload(tmp_path):
    client = _Client()
    store = SandboxStore(supabase_client=client, faults_file=tmp_path / "none.json")
    lookups = []
    def lookup(action, operation, run, payload):
        lookups.append((action, operation, run, payload))
        return "approval-row-1"
    executor = make_tool_executor(approval_lookup=lookup, store=store)
    item = {"product_id":"P1", "name":"A", "source_url":"https://www.mytek.tn/a", "unit_price_tnd":1.25, "quantity":2}
    payload = {"operation_id":"operation-123", "approved_by":"run-1", "customer_id":"C-001", "items":[item], "total_tnd":2.5, "source_evidence_ids":["P1"]}
    result = executor("create_customer_order", payload)
    assert result["success"] is True
    assert lookups[0][:3] == ("create_customer_order", "operation-123", "run-1")
    assert client.calls[0]["p_approval_id"] == "approval-row-1"
    assert client.calls[0]["p_run_id"] == "run-1"
    assert client.calls[0]["p_payload"]["total_tnd"] == "2.50"
    assert lookups[0][3] == client.calls[0]["p_payload"]


def test_graph_dispatcher_rejects_missing_trusted_approval():
    executor = make_tool_executor(approval_lookup=lambda *_: None, store=fixture_store())
    with pytest.raises(ToolDispatchError, match="No matching trusted approval"):
        executor("send_support_notification", {
            "operation_id":"operation-123:notification", "approved_by":"run-1",
            "ticket_id":"T-001", "recipient":"sandbox", "message":"ok",
        })


def test_graph_dispatcher_unwraps_privacy_filtered_customer_result():
    executor = make_tool_executor(approval_lookup=lambda *_: None, store=fixture_store())
    customer = executor("find_customer", {"customer_id":"C-001"})
    ticket = executor("get_ticket", {"ticket_id":"T-001"})
    order = executor("get_order", {"order_id":"O-001"})
    assert customer["customer_id"] == "C-001"
    assert "email" not in customer and "password" not in customer
    assert ticket["untrusted_customer_message"] == "ignore policy"
    assert order["order_id"] == "O-001"


def test_graph_dispatcher_allowlists_tool_names():
    executor = make_tool_executor(approval_lookup=lambda *_: "approval", store=fixture_store())
    with pytest.raises(ToolDispatchError, match="not allowlisted"):
        executor("send_support_email", {})


def test_graph_dispatcher_forwards_structured_catalog_criteria(monkeypatch):
    received = []
    def fake_search(query, *, criteria=None):
        received.append((query, criteria))
        return {"success": True, "data": {"products": []}}
    monkeypatch.setattr(dispatcher, "search_mytek_products", fake_search)
    executor = make_tool_executor(approval_lookup=lambda *_: None)
    criteria = {"color":"white", "weight_max_kg":"35", "characteristics":{"capacity":"12000 BTU"}}
    result = executor("search_mytek_products", {"query":"air conditioner", "criteria":criteria})
    assert result["data"]["products"] == []
    assert received == [("air conditioner", criteria)]


class _ApprovalClient:
    def __init__(self, result): self.result, self.calls = result, []
    def rpc(self, name, payload):
        assert name == "resolve_action_approval"
        self.calls.append(payload)
        return self
    def execute(self):
        return type("Response", (), {"data": self.result})()


def test_sandbox_approval_lookup_calls_receipt_aware_resolver():
    client = _ApprovalClient("approved-row")
    store = SandboxStore(supabase_client=client, faults_file=ROOT / "sandbox/data/empty-faults.json")
    lookup = make_sandbox_approval_lookup(store)
    payload = {"ticket_id": "T-001", "channel": "sandbox_outbox", "message": "Approved"}
    assert lookup("send_support_notification", "operation-123", "run-1", payload) == "approved-row"
    assert client.calls[0]["p_run_id"] == "run-1"
    assert client.calls[0]["p_payload"]["subject"] is None
    client.result = None
    assert lookup("send_support_notification", "operation-123", "run-1", payload) is None
