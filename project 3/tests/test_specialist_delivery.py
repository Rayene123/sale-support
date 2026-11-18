"""Persona 4 checks with local HTTP and the same sandbox SQL as the hosted adapter."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import socket
from threading import Thread
from types import SimpleNamespace

import pytest
import requests

from specialist.observability import Observability, capture_event, model_attempt, model_tokens
from specialist.workflow.coordinator import Specialist
from specialist.sandbox.writer import SandboxWriter
from specialist.workflow.store import CaseStore
from specialist.catalog.fixtures import Catalog
from specialist.sandbox.local_rpc import LocalSandbox
from specialist.sandbox.store import SandboxStore
from specialist.support import fixtures as support_fixtures
from specialist.workbench.cli import reset_local
from specialist.workbench.http import Workbench


CONNECT = socket.socket.connect


@pytest.fixture
def loopback(monkeypatch):
    def connect(sock, address):
        if address[0] != "127.0.0.1":
            raise AssertionError("The workbench test only uses loopback")
        return CONNECT(sock, address)
    monkeypatch.setattr(socket.socket, "connect", connect)


@contextmanager
def serve(tmp_path, *, researcher=None, writer=None, shop=False):
    store = CaseStore(tmp_path / "cases.db")
    catalog = (researcher or Catalog()).researcher()
    service = Specialist(store, catalog, writer=writer)
    shop_service = Specialist(CaseStore(tmp_path / "shopping.db"), catalog) if shop else None
    observer = Observability(tmp_path / "metrics.jsonl")
    with Workbench(0, service, observer, customer="C-001", reviewer="R-001",
                   passwords={"customer": "customer-test", "admin": "reviewer-test"},
                   fixture=True, sandbox="Local sandbox only", shop_service=shop_service) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", service
        finally:
            server.shutdown()
            thread.join()


def csrf(text):
    return re.search(r'name="csrf" value="([^"]+)"', text).group(1)


def sign_in(base, role, password):
    session = requests.Session()
    session.trust_env = False
    response = session.post(f"{base}/{role}/login", data={"password": password}, timeout=5)
    assert response.status_code == 200 and "Sign out" in response.text
    return session


def submit(client, url, action, **fields):
    state = client.get(url, timeout=5)
    return client.post(url, data={"csrf": csrf(state.text), "action": action, **fields}, timeout=5)


def test_role_csrf_and_case_ownership_are_checked_on_the_server(tmp_path, loopback):
    with serve(tmp_path) as (base, service), sign_in(base, "customer", "customer-test") as customer:
        foreign = service.start("C-002", "Find a laptop and monitor under 3000 TND")
        assert customer.get(f'{base}/customer/{foreign["case_id"]}', timeout=5).status_code == 404
        assert foreign["case_id"] not in customer.get(f"{base}/customer/", timeout=5).text
        denied = customer.post(f'{base}/admin/{foreign["case_id"]}', data={"action": "approve"}, timeout=5)
        assert denied.status_code == 403
        page = customer.get(f"{base}/customer/", timeout=5)
        assert customer.post(page.url, data={"action": "start"}, timeout=5).status_code == 403
        assert customer.post(page.url, data={"action": "start", "csrf": csrf(page.text)},
                             headers={"Origin": "https://not-local.example"}, timeout=5).status_code == 403
        own = submit(customer, page.url, "start", request="Find a laptop and monitor")
        assert "Awaiting clarification" in own.text and "Run trace" not in own.text
        assert submit(customer, own.url, "approve").status_code == 403
        with sign_in(base, "admin", "reviewer-test") as reviewer:
            assert foreign["case_id"] in reviewer.get(f"{base}/admin/", timeout=5).text


def test_support_ticket_review_uses_the_same_admin_session(tmp_path, loopback):
    support_fixtures.reset_write_log()
    try:
        with serve(tmp_path) as (base, _), sign_in(base, "customer", "customer-test") as customer:
            support = base + "/admin/support/"
            assert "Reviewer sign in" in customer.get(support, timeout=5).text
            assert customer.post(support, data={"action": "start", "ticket_id": "TICKET-102"}, timeout=5).status_code == 403
            with sign_in(base, "admin", "reviewer-test") as reviewer:
                draft = submit(reviewer, support, "start", ticket_id="TICKET-102")
                assert draft.status_code == 200 and "Awaiting approval" in draft.text
                assert support_fixtures.WRITE_LOG == []
                fields = dict(re.findall(r'name="(run_id|operation_id)" value="([^"]+)"', draft.text))
                reply = submit(reviewer, support, "approve", ticket_id="TICKET-102", **fields)
                assert reply.status_code == 200 and "Completed" in reply.text
                assert len(support_fixtures.WRITE_LOG) == 1
    finally:
        support_fixtures.reset_write_log()


def test_storefront_keeps_shopper_choices_separate_from_sandbox_approval(tmp_path, loopback):
    with serve(tmp_path, shop=True) as (base, service), requests.Session() as shopper, requests.Session() as stranger:
        shopper.trust_env = stranger.trust_env = False
        page = shopper.get(base, timeout=5)
        assert page.url.endswith("/shop/") and "Find the gear" in page.text
        assert shopper.post(page.url, data={"action": "start", "request": "Find a laptop"}, timeout=5).status_code == 403
        result = submit(shopper, page.url, "start", request="Find a laptop and monitor under 3000 TND")
        assert result.status_code == 200 and "Your recommendation." in result.text
        assert "2,630 TND" in result.text and "Connection verified" in result.text
        assert stranger.get(result.url, timeout=5).status_code == 404
        assert service.store.recent() == []
        fields = dict(re.findall(r'name="(proposal_hash|revision)" value="([^"]+)"', result.text))
        assert submit(shopper, result.url, "select", **{**fields, "revision": "0"}).status_code == 409
        choice = submit(shopper, result.url, "select", **fields)
        assert choice.status_code == 200 and "Your selected setup." in choice.text
        assert service.store.recent() == []


def test_unconfirmed_local_reset_preserves_existing_cases(tmp_path):
    cases = CaseStore(tmp_path / "cases.db")
    state = {"case_id": "saved-case", "customer_id": "C-001"}
    cases.insert(state)
    client = SimpleNamespace(rpc=lambda _: SimpleNamespace(execute=lambda: SimpleNamespace(data={"success": False})))

    with pytest.raises(RuntimeError, match="Case history was preserved"):
        reset_local(cases, client)
    assert cases.get("saved-case", "C-001") == state


def test_local_sql_approval_recheck_and_receipts_through_the_workbench(tmp_path, loopback):
    dependency = Path(__file__).resolve().parents[1] / "specialist/sandbox/sql/node_modules/@electric-sql/pglite"
    if not shutil.which("node") or not (os.getenv("PGLITE_MODULE") or dependency.exists()):
        pytest.skip("Install the local SQL test dependency with npm ci --prefix specialist/sandbox/sql")
    catalog = Catalog()
    database = tmp_path / "sandbox"

    class LoseFirstNotificationReply(SandboxWriter):
        dropped = False

        def apply(self, action, run_id, approval):
            result = super().apply(action, run_id, approval)
            if action["action"] == "send_support_notification" and result.get("success") and not self.dropped:
                self.dropped = True
                raise RuntimeError("Simulated lost reply after the SQL commit")
            return result

    with LocalSandbox(database) as sql:
        writer = LoseFirstNotificationReply(SandboxStore(supabase_client=sql))
        with serve(tmp_path, researcher=catalog, writer=writer) as (base, service):
            with sign_in(base, "customer", "customer-test") as customer, sign_in(base, "admin", "reviewer-test") as admin:
                customer_case = submit(customer, f"{base}/customer/", "start",
                                       request="Find a laptop and monitor under 3000 TND")
                case_id = customer_case.url.rsplit("/", 1)[-1]
                review = f"{base}/admin/{case_id}"
                case = service.store.get(case_id, "C-001")
                first = {"revision": case["revision"], "proposal_hash": case["proposal"]["hash"]}
                assert "2630.00 TND" in customer_case.text and "Sandbox notification" in admin.get(review, timeout=5).text
                assert submit(admin, review, "approve", **first).status_code == 200
                catalog.rows["L1"]["price_tnd"] = "1850.00"
                changed = submit(admin, review, "execute", **first)
                assert "Reapproval required" in changed.text and "2680.00 TND" in changed.text
                assert submit(admin, review, "approve", **first).status_code == 409
                case = service.store.get(case_id, "C-001")
                second = {"revision": case["revision"], "proposal_hash": case["proposal"]["hash"]}
                assert submit(admin, review, "approve", **second).status_code == 200
                assert submit(admin, review, "execute", **first).status_code == 409
                assert "Partially completed" in submit(admin, review, "execute", **second).text
                assert "Partially completed" in submit(admin, review, "execute", **second).text
                lost_reply = service.store.get(case_id, "C-001")
                assert writer.dropped and len(lost_reply["receipts"]) == 1
                assert writer.receipt(lost_reply["proposal"]["actions"][1], lost_reply["run_id"])["success"]
                assert "Completed" in submit(admin, review, "execute", **second).text
                assert "Completed" in submit(admin, review, "execute", **second).text
                complete = service.store.get(case_id, "C-001")
                assert len(complete["receipts"]) == 2
    with LocalSandbox(database) as sql:
        writer = SandboxWriter(SandboxStore(supabase_client=sql))
        actions = complete["proposal"]["actions"]
        assert all(writer.receipt(action, complete["run_id"])["success"] for action in actions)
        assert sql.rpc("reset_sale_support_sandbox").execute().data["operation_history_cleared"] is True
        assert all(writer.receipt(action, complete["run_id"]) is None for action in actions)


def test_trace_only_exports_allowlisted_fields_and_export_failure_is_isolated(tmp_path):
    records = []

    def exporter(data):
        records.append(data)
        raise RuntimeError("unavailable")

    observer = Observability(tmp_path / "metrics.jsonl", exporter=exporter)
    result = {"case_id": "case", "run_id": "run", "revision": 1, "status": "awaiting_approval",
              "prompt": "private@example.test"}

    def invoke():
        model_attempt()
        model_tokens({"prompt_eval_count": 8, "eval_count": 3, "message": "private@example.test"})
        capture_event({"actor": "researcher", "action": "inspect_listing", "at": "2026-11-17T10:00:00+00:00",
                       "elapsed_ms": 4.1, "remaining_steps": 20, "revision": 1,
                       "detail": {"url": "https://example.test/private"}})
        return result

    assert observer.run("start", invoke) == result
    observer.queue.join()
    stored = json.loads((tmp_path / "metrics.jsonl").read_text())
    assert stored == records[0] and stored["model_calls"] == 1
    assert stored["model_usage"] == [{"input_tokens": 8, "output_tokens": 3}]
    assert "private" not in json.dumps(stored)
