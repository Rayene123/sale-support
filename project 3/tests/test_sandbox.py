"""Offline sandbox safety and fixture checks."""
import json
import re
from pathlib import Path

import pytest

from specialist.sandbox.store import SandboxStore, DatabaseFailure
from specialist.sandbox import reset

ROOT = Path(__file__).resolve().parents[1]


def test_seed_fixture_counts_and_required_scenarios():
    seed = (ROOT / "specialist/sandbox/seed.sql").read_text(encoding="utf-8")
    customers = seed.split("-- CUSTOMERS", 1)[1].split("-- ORDERS", 1)[0]
    orders = seed.split("-- ORDERS", 1)[1].split("-- TICKETS", 1)[0]
    tickets = seed.split("-- SUPPORT TICKETS", 1)[1]
    assert customers.count("'C-") == 10
    assert len(re.findall(r"^\s*'O-", orders, re.MULTILINE)) == 10
    assert len(re.findall(r"^\s*'T-", tickets, re.MULTILINE)) == 12
    for ticket in ("T-001", "T-002", "T-003", "T-004", "T-010", "T-011", "T-012"):
        assert f"'{ticket}'" in seed


def test_failure_fixtures_are_bounded_and_deterministic(tmp_path):
    faults = json.loads((ROOT / "specialist/sandbox/data/faults.json").read_text(encoding="utf-8"))
    store = SandboxStore.in_memory({}, faults_file=ROOT / "specialist/sandbox/data/faults.json")
    with pytest.raises(DatabaseFailure):
        store._trigger_read_failure("get_ticket", "T-001")
    store._trigger_read_failure("get_ticket", "T-001")
    with pytest.raises(DatabaseFailure):
        store.before_write("OP-FAIL-BEFORE-001")
    store.before_write("OP-FAIL-BEFORE-001")
    assert {entry["mode"] for entry in faults["write_failures"]} == {"before_persistence", "after_persistence"}


def test_schema_has_only_sandbox_side_effect_storage():
    schema = (ROOT / "specialist/sandbox/schema.sql").read_text(encoding="utf-8").lower()
    assert "email_outbox" in schema
    assert "approval_records" in schema
    assert "create table" in schema
    assert "smtp" not in schema and "payment_gateway" not in schema


def test_database_configuration_requires_explicit_sandbox_allowlist(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "test-only-not-a-secret")
    monkeypatch.delenv("SUPABASE_SANDBOX_URL", raising=False)
    with pytest.raises(DatabaseFailure, match="approved as the dedicated sandbox"):
        SandboxStore.from_env()


def test_ordinary_sandbox_operations_do_not_use_network():
    store = SandboxStore.in_memory({"tickets": []}, faults_file=ROOT / "specialist/sandbox/data/empty-faults.json")
    assert store.mode == "memory"
    assert store.client is None


def test_commerce_migration_is_additive_and_service_role_only():
    migration = (ROOT / "specialist/sandbox/migrations/002_approved_commerce_writes.sql").read_text(encoding="utf-8")
    assert "create or replace function public.execute_approved_commerce_write" in migration
    assert "create or replace function public.record_commerce_approval" in migration
    assert "create or replace function public.execute_support_write" not in migration
    assert "grant execute on function public.execute_approved_commerce_write" in migration
    assert "approved_payload = p_payload" in migration
    assert "round(v_unit_price * v_quantity, 2)" in migration
    assert "pg_advisory_xact_lock" in migration
    assert "notification_outbox" in migration
    assert "checkout" not in migration.lower() and "payment" not in migration.lower()


class _ResetRPC:
    def __init__(self, client, function):
        self.client, self.function = client, function
    def execute(self):
        self.client.calls.append(self.function)
        if self.function == "reset_sale_support_sandbox":
            data = {"success": True, "customers": 10, "orders": 10, "tickets": 12, "operation_history_cleared": True}
        else:
            data = {"success": True, "notifications_cleared": 1, "sandbox_orders_cleared": 1, "operation_history_cleared": 1, "approvals_cleared": 1}
        return type("Response", (), {"data": data})()


class _ResetClient:
    def __init__(self): self.calls = []
    def rpc(self, function): return _ResetRPC(self, function)


def test_reset_uses_one_atomic_rpc(monkeypatch, tmp_path, capsys):
    client = _ResetClient()
    monkeypatch.setattr(reset, "load_settings", lambda: None)
    monkeypatch.setenv("SUPABASE_URL", "https://sandbox.invalid")
    monkeypatch.setenv("SUPABASE_SANDBOX_URL", "https://sandbox.invalid")
    monkeypatch.setattr(reset.SandboxStore, "from_env", lambda: SandboxStore(supabase_client=client, faults_file=tmp_path / "no-faults.json"))
    reset.reset_supabase()
    assert client.calls == ["reset_sale_support_sandbox"]
    assert "Sandbox reset completed successfully" in capsys.readouterr().out


def test_reset_refuses_before_fixture_reset_if_migration_rpc_is_missing(monkeypatch, tmp_path):
    class MissingMigrationClient(_ResetClient):
        def rpc(self, function):
            if function == "reset_sale_support_sandbox":
                raise RuntimeError("function is missing")
            return super().rpc(function)
    client = MissingMigrationClient()
    monkeypatch.setattr(reset, "load_settings", lambda: None)
    monkeypatch.setenv("SUPABASE_URL", "https://sandbox.invalid")
    monkeypatch.setenv("SUPABASE_SANDBOX_URL", "https://sandbox.invalid")
    monkeypatch.setattr(reset.SandboxStore, "from_env", lambda: SandboxStore(supabase_client=client, faults_file=tmp_path / "no-faults.json"))
    with pytest.raises(RuntimeError, match="Sandbox reset failed"):
        reset.reset_supabase()
    assert client.calls == []
