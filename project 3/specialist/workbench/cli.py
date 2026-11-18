"""Launch the Specialist workbench with the selected catalog and sandbox."""

from argparse import ArgumentParser
from contextlib import ExitStack
import os
from pathlib import Path
from secrets import token_urlsafe

from specialist.catalog.fixtures import DemoCatalog
from specialist.config import load_settings
from specialist.contracts.validation import validate_identifier
from specialist.observability import Observability, langsmith_exporter
from specialist.sandbox.local_rpc import LocalSandbox
from specialist.sandbox.store import SandboxStore
from specialist.sandbox.writer import SandboxWriter
from specialist.workflow.coordinator import Specialist
from specialist.workflow.store import CaseStore

from .http import Workbench


def reset_local(cases, client):
    """Clear case history only after the database confirms its reset."""
    result = client.rpc("reset_sale_support_sandbox").execute().data
    if (not isinstance(result, dict) or result.get("success") is not True
            or result.get("operation_history_cleared") is not True):
        raise RuntimeError("Local database did not confirm the reset. Case history was preserved.")
    cases.clear()


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=8767, type=int)
    parser.add_argument("--catalog", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--sandbox", choices=("local", "supabase"), default="local")
    parser.add_argument("--planner", choices=("local", "rules"), default="local")
    parser.add_argument("--data-dir", type=Path, default=Path(".specialist"))
    parser.add_argument("--reset-local", action="store_true", help="Clear cases and restore local SQL fixtures, then exit")
    args = parser.parse_args()
    if args.reset_local and args.sandbox != "local":
        parser.error("--reset-local requires the local sandbox.")
    load_settings()
    customer = validate_identifier(os.getenv("SPECIALIST_CUSTOMER_ID", "C-001"))
    reviewer = validate_identifier(os.getenv("SPECIALIST_REVIEWER_ID", "R-001"))
    passwords = {role: os.getenv(f"SPECIALIST_{role.upper()}_PASSWORD") or token_urlsafe(12)
                 for role in ("customer", "admin")}
    if customer == reviewer or passwords["customer"] == passwords["admin"]:
        parser.error("Use distinct customer and reviewer identities and passcodes.")
    directory = args.data_dir / f"{args.catalog}-{args.sandbox}-{args.planner}"
    store = CaseStore(directory / "cases.db")
    fixture = args.catalog == "fixture"
    with ExitStack() as stack:
        if args.sandbox == "local":
            client = stack.enter_context(LocalSandbox(directory / "sandbox"))
            if args.reset_local:
                reset_local(store, client)
                print("Local cases cleared and sandbox fixtures restored.")
                return
            sandbox = SandboxStore(supabase_client=client)
        else:
            sandbox = SandboxStore.from_env()
        researcher = DemoCatalog().researcher() if fixture else None
        factory = Specialist.with_local_model if args.planner == "local" else Specialist
        service = factory(store, researcher, writer=SandboxWriter(sandbox))
        try:
            exporter = langsmith_exporter()
        except Exception:
            exporter = None
        observer = Observability(directory / "metrics.jsonl", exporter=exporter)
        with Workbench(args.port, service, observer, customer=customer, reviewer=reviewer, passwords=passwords,
                       fixture=fixture, sandbox=f"{args.sandbox.title()} sandbox only") as server:
            print(f"Customer http://127.0.0.1:{server.server_port}/customer/", flush=True)
            print(f"Reviewer http://127.0.0.1:{server.server_port}/admin/", flush=True)
            for role, password in passwords.items():
                if not os.getenv(f"SPECIALIST_{role.upper()}_PASSWORD"):
                    print(f"{role.title()} passcode {password}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
