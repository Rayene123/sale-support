"""Hybrid workflow regressions using a provider stub and sourced product fixtures."""
import json

import pytest
import requests

from specialist.workflow.coordinator import CaseConflict, Specialist
from specialist.workflow.planner import ModelUnavailable, OllamaPlanner
from specialist.catalog.research import Researcher
from specialist.contracts.setup import SetupPlan
from specialist.workflow.planning import ground_plan, read_plan_findings
from specialist.workflow.store import CaseStore
from specialist.catalog.fixtures import Catalog, product


PROMPT = "Find a desktop, two keyboards, and a mouse under 1,500 TND."


def line(id, kind, query, *, quantity=1, owned=False, exact_model=None, specs=None):
    return {"id": id, "kind": kind, "quantity": quantity, "owned": owned,
            "exact_model": exact_model, "queries": [query], "specs": specs or []}


def expected_plan():
    return {"budget_tnd": "1500", "items": [
        line("pc", "desktop", "pc de bureau"),
        line("keys", "keyboard", "clavier usb", quantity=2),
        line("pointer", "mouse", "souris usb"),
    ], "links": [{"source": "pc", "target": "keys", "kind": "usb"},
                 {"source": "pc", "target": "pointer", "kind": "usb"}]}


def test_standard_link_omits_inferred_defaults_but_keeps_requested_display_mode():
    model = SetupPlan.model_validate({
        "budget_tnd": 4000,
        "items": [line("pc", "laptop", "pc portable", specs=[
            {"field": "RAM", "value": "16 GB", "comparison": "at_least"},
            {"field": "storage", "value": "512 GB", "comparison": "at_least"},
        ]), line("screen", "monitor", "ecran pc")],
        "links": [{"source": "pc", "target": "screen", "kind": "video", "transport": "hdmi",
                   "resolution": "2560x1440", "refresh_hz": 120}],
    })
    text = "Find a laptop with 16 Go of RAM and a 1440p monitor under 4000 TND."
    grounded = ground_plan(model, text, None)
    assert [spec.field for spec in grounded.items[0].specs] == ["RAM"]
    assert grounded.links[0].resolution == "2560x1440"
    assert grounded.links[0].transport is grounded.links[0].refresh_hz is None
    assert read_plan_findings(grounded, text) == []
    assert any("resolution" in note for note in read_plan_findings(grounded, text.replace("1440p", "4K")))


class StubModel:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def __enter__(self):
        self.trust_env = None
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, *, json, timeout, allow_redirects):
        assert url == "http://127.0.0.1:11434/api/chat"
        assert self.trust_env is False and allow_redirects is False
        assert json["format"] == SetupPlan.model_json_schema() and json["stream"] is False
        self.prompts.append(json["messages"])
        if isinstance(self.response, Exception):
            raise self.response
        return self

    status_code = 200

    def json(self):
        return {"done_reason": "stop", "message": {"content": json.dumps(self.response)}}


class Sources:
    def __init__(self):
        self.items = {
            "pc": [product("PC1", "Desktop A", "1200", {"Ports": "3x USB-A"})],
            "keys": [product("K1", "USB Keyboard", "40", {"Ports": "1x USB-A", "Stock quantity": "4"})],
            "pointer": [product("M1", "Mouse A", "35", {"Ports": "1x USB-A"})],
        }
        self.queries = {"pc de bureau": "pc", "clavier usb": "keys", "souris usb": "pointer"}
        self.calls = []

    def search(self, query, *, max_results):
        self.calls.append(query)
        return {"success": True, "data": {"products": self.items.get(self.queries.get(query), [])[:max_results]}}

    def inspect(self, product_id, url):
        self.calls.append(product_id)
        for items in self.items.values():
            for item in items:
                if item["product_id"] == product_id and item["source_url"] == url:
                    return {"success": True, "data": item}
        return {"success": False}

    def researcher(self):
        return Researcher(self.search, self.inspect)


@pytest.fixture
def runner(tmp_path, monkeypatch):
    def build(response, sources=None, **kwargs):
        source = sources or Sources()
        model = StubModel(response)
        monkeypatch.setattr("specialist.workflow.planner.requests.Session", lambda: model)
        service = Specialist.with_local_model(CaseStore(tmp_path / "case.db"), source.researcher(), **kwargs)
        return service, source, model
    return build


def test_three_types_and_four_units_are_verified_and_priced(runner):
    service, source, model = runner(expected_plan())
    case = service.start("C-001", PROMPT)
    assert len(model.prompts) == 1 and case["status"] == "awaiting_approval"
    assert source.calls == ["pc de bureau", "PC1", "clavier usb", "K1", "souris usb", "M1"]
    payload = case["proposal"]["actions"][0]["payload"]
    assert [item["quantity"] for item in payload["items"]] == [1, 2, 1]
    assert payload["total_tnd"] == "1315.00"
    assert len([f for f in case["findings"] if "->" in f["code"] and f["verdict"] == "pass"]) == 2
    assert case["approval"] is None


def test_shared_port_is_not_counted_twice(runner):
    source = Sources()
    source.items["pc"][0]["characteristics"]["Ports"] = "2x USB-A"
    service, _, _ = runner(expected_plan(), source)
    case = service.start("C-001", PROMPT)
    assert case["status"] == "verification_blocked" and case["proposal"] is None
    assert any(f["code"] == "port_capacity" for f in case["findings"])


def test_adaptive_second_query_can_find_host_with_enough_ports(runner):
    source = Sources()
    source.items["pc"][0]["characteristics"]["Ports"] = "2x USB-A"
    source.queries["desktop with multiple USB ports"] = "pc2"
    source.items["pc2"] = [product("PC2", "Desktop B", "1250", {"Ports": "4x USB-A"})]
    plan = expected_plan()
    plan["items"][0]["queries"].append("desktop with multiple USB ports")
    service, _, _ = runner(plan, source)
    case = service.start("C-001", PROMPT)
    assert case["status"] == "awaiting_approval"
    assert case["proposal"]["evidence"]["pc"]["product_id"] == "PC2"
    assert any(event["action"] == "broaden_research" for event in case["trajectory"])


def test_quantity_stock_is_not_assumed(runner):
    source = Sources()
    del source.items["keys"][0]["characteristics"]["Stock quantity"]
    service, _, _ = runner(expected_plan(), source)
    case = service.start("C-001", PROMPT)
    assert any(f["code"] == "keys_stock" and f["verdict"] == "unknown" for f in case["findings"])
    assert not case["proposal"]


def test_owned_exact_model_is_evidence_but_excluded_from_purchase(runner):
    plan = expected_plan()
    plan["items"][0].update(owned=True, exact_model="Desktop A")
    service, _, _ = runner(plan)
    case = service.start("C-001", "I already own Desktop A. " + PROMPT)
    payload = case["proposal"]["actions"][0]["payload"]
    assert len(case["proposal"]["evidence"]) == 3
    assert [i["product_id"] for i in payload["items"]] == ["K1", "M1"]
    assert payload["total_tnd"] == "115.00"


@pytest.mark.parametrize("drift", ["drop", "quantity", "budget", "owned_model", "unlinked"])
def test_invalid_or_incomplete_model_plans_pause_before_any_search(runner, drift):
    plan = expected_plan()
    if drift == "drop":
        plan["items"].pop()
        plan["links"].pop()
    elif drift == "quantity":
        plan["items"][1]["quantity"] = 1
    elif drift == "budget":
        plan["budget_tnd"] = "1600"
    elif drift == "owned_model":
        plan["items"][0]["owned"] = True
    else:
        plan["links"].pop()
    service, source, _ = runner(plan)
    case = service.start("C-001", PROMPT)
    assert case["status"] == "awaiting_clarification" and not source.calls and not case["proposal"]


def test_unsupported_relationship_remains_unknown(runner):
    plan = expected_plan()
    plan["links"][1]["kind"] = "power_delivery"
    service, _, _ = runner(plan)
    case = service.start("C-001", PROMPT)
    assert case["status"] == "verification_blocked"
    assert any("Could not establish power_delivery" in f["reason"] for f in case["findings"])
    assert case["proposal"] is None


@pytest.mark.parametrize(("length", "declared", "check", "pairing"), [
    ("300 mm", "GPU-300", "pass", "pass"),
    ("330 mm", "GPU-300", "fail", "pass"),
    ("300 mm", "not compatible with GPU-300", "pass", "unknown"),
    ("29 A", "GPU-300", "unknown", "pass"),
    (None, "GPU-300", "unknown", "pass"),
])
def test_model_selects_new_fields_but_evidence_determines_result(runner, length, declared, check, pairing):
    plan = {
        "budget_tnd": "2000",
        "items": [line("case", "boitier_pc", "boîtier pc"), line("card", "carte_graphique", "carte graphique")],
        "links": [{"source": "case", "target": "card", "kind": "clearance", "checks": [
            {"source_field": "maximum GPU length", "target_field": "GPU length", "comparison": "at_least"},
        ]}],
    }
    sources = Sources()
    gpu_specs = {"MPN": "GPU-300"}
    if length is not None:
        gpu_specs["GPU length"] = length
    sources.items.update(
        case=[product("CASE-100", "Boîtier-PC", "130", {
            "Maximum GPU length": "32 cm", "Compatible models": declared,
        })],
        card=[product("GPU-300", "Carte graphique", "800", gpu_specs)],
    )
    sources.queries.update({"boîtier pc": "case", "carte graphique": "card"})
    service, _, _ = runner(plan, sources)
    case = service.start("C-001", "Find a PC case and a GPU under 2000 TND that fit together.")
    findings = {finding["code"]: finding for finding in case["findings"]}
    clearance = findings["case->card:clearance:check:1"]
    assert clearance["verdict"] == check
    assert len(clearance["evidence"]) == (1 if length is None else 2)
    assert findings["case->card:clearance"]["verdict"] == pairing
    assert bool(case["proposal"]) == (check == pairing == "pass")


@pytest.mark.parametrize("url", ["https://api.openai.com", "http://localhost:11434/api"])
def test_ollama_endpoint_accepts_only_a_local_base_url(url):
    with pytest.raises(ValueError, match="local Ollama service"):
        OllamaPlanner(url)


def test_model_failure_does_not_drop_items_into_the_old_parser(runner):
    service, source, _ = runner(ValueError("credential or provider error detail"))
    case = service.start("C-001", PROMPT)
    assert case["status"] == "planner_unavailable" and not source.calls
    assert "credential or provider error detail" not in str(case)


def test_revision_reuses_evidence_and_invalidates_old_proposal(runner):
    service, source, model = runner(expected_plan())
    case = service.start("C-001", PROMPT)
    model.response = {**expected_plan(), "budget_tnd": "1450"}
    source.calls.clear()
    updated = service.revise(case["case_id"], "C-001", "New total budget of 1,450 TND", expected_revision=1)
    assert not source.calls and updated["status"] == "awaiting_approval"
    assert updated["proposal"]["hash"] != case["proposal"]["hash"]
    assert len(model.prompts) == 2 and "previous_requirements" in model.prompts[-1][-1]["content"]
    with pytest.raises(CaseConflict):
        service.decide(case["case_id"], "C-001", reviewer_id="admin-1", revision=1,
                       proposal_hash=case["proposal"]["hash"], decision="approve")


def test_hybrid_price_recheck_preserves_quantities_and_requires_fresh_approval(runner):
    service, source, _ = runner(expected_plan(), writer=object())
    case = service.start("C-001", PROMPT)
    service.decide(case["case_id"], "C-001", reviewer_id="admin-1", revision=1,
                   proposal_hash=case["proposal"]["hash"], decision="approve")
    source.items["keys"][0]["price_tnd"] = "45"
    revised = service.execute_next(case["case_id"], "C-001")
    assert revised["status"] == "reapproval_required" and not revised["receipts"]
    assert revised["proposal"]["actions"][0]["payload"]["total_tnd"] == "1325.00"


def test_budget_only_revision_cannot_remove_quantity_or_connection(runner):
    service, source, model = runner(expected_plan())
    case = service.start("C-001", PROMPT)
    changed = expected_plan()
    changed["budget_tnd"] = "1450"
    changed["items"][1]["quantity"] = 1
    model.response = changed
    source.calls.clear()
    updated = service.revise(case["case_id"], "C-001", "Make that 1,450 TND", expected_revision=1)
    assert updated["status"] == "awaiting_clarification" and not source.calls
    assert updated["setup"]["items"][1]["quantity"] == 2
    assert updated["proposal"] is None


def test_discarded_refresh_rate_blocks_silently_weaker_plan(runner):
    service, source, _ = runner(expected_plan())
    case = service.start("C-001", PROMPT + " I need 120 Hz on the monitor.")
    assert case["status"] == "awaiting_clarification" and not source.calls
    assert any("refresh rate" in question for question in case["questions"])


def test_hybrid_order_and_notification_recover_after_service_restart(runner):
    class DurableWriter:
        def __init__(self):
            self.saved = {}
            self.calls = []
            self.fail_notification = True

        def receipt(self, action, run_id):
            return self.saved.get(action["operation_id"])

        def apply(self, action, run_id, approval):
            self.calls.append(action["action"])
            key = action["operation_id"]
            receipt = self.saved.setdefault(key, {"success": True, "operation_id": key})
            if action["action"] == "send_support_notification" and self.fail_notification:
                self.fail_notification = False
                raise RuntimeError("Lost notification response after commit")
            return receipt

    writer = DurableWriter()
    service, source, _ = runner(expected_plan(), writer=writer)
    case = service.start("C-001", PROMPT)
    key = case["case_id"]
    service.decide(key, "C-001", reviewer_id="admin-1", revision=1,
                   proposal_hash=case["proposal"]["hash"], decision="approve")
    assert service.execute_next(key, "C-001")["status"] == "partially_completed"
    assert service.execute_next(key, "C-001")["status"] == "partially_completed"
    restored = Specialist(CaseStore(service.store.path), source.researcher(), writer=writer)
    result = restored.execute_next(key, "C-001")
    assert result["status"] == "completed" and len(result["receipts"]) == 2
    assert writer.calls == ["create_customer_order", "send_support_notification"]


def test_usb_c_connector_shape_does_not_prove_data_support(runner):
    source = Sources()
    source.items["pc"][0]["characteristics"]["Ports"] = "3x USB-C"
    source.items["keys"][0]["characteristics"]["Ports"] = "1x USB-C data"
    source.items["pointer"][0]["characteristics"]["Ports"] = "1x USB-C data"
    service, _, _ = runner(expected_plan(), source)
    case = service.start("C-001", PROMPT)
    assert case["status"] == "verification_blocked"
    assert any("No shared connection" in f["reason"] for f in case["findings"])


def test_live_catalog_retries_a_narrow_model_query_on_the_bounded_category(runner):
    class NarrowSearch(Catalog):
        def general(self, query, *, max_results):
            if "moniteur" in query:
                return self.search("first monitor", max_results=max_results)
            self.lookups.append(("search", query))
            return {"success": True, "data": {"products": []}}

        def researcher(self):
            return Researcher(self.search, self.inspect, self.general)

    plan = {"budget_tnd": 2900, "items": [
        line("pc", "laptop", "portable 8 Go en promotion"),
        line("screen", "monitor", "moniteur Full HD noir"),
    ], "links": [{"source": "pc", "target": "screen", "kind": "video"}]}
    catalog = NarrowSearch()
    catalog.queries["first monitor"] = ["M0"]  # VGA cannot connect to the available laptop.
    service, source, _ = runner(plan, catalog)
    case = service.start("C-001", "Find a laptop and a compatible monitor under 2900 TND.")
    assert case["status"] == "awaiting_approval"
    assert ("search", "pc portable") in source.lookups
    assert ("search", "écran pc") in source.lookups
