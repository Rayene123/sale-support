"""Trusted server bridge between Specialist decisions and Person 2's sandbox tools."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from specialist.sandbox.dispatcher import make_sandbox_approval_lookup, make_tool_executor
from specialist.sandbox.approvals import record_approval
from specialist.sandbox.store import SandboxStore


class SandboxWriter:
    def __init__(self, store: SandboxStore):
        if store.client is None:
            raise ValueError("Specialist writes require the dedicated Supabase sandbox")
        self.store = store
        self.lookup = make_sandbox_approval_lookup(store)
        self.execute = make_tool_executor(approval_lookup=self.lookup, store=store)

    def receipt(self, action, run_id):
        kind, operation, payload = action["action"], action["operation_id"], action["payload"]
        return self.store.client.rpc("read_specialist_receipt", {
            "p_action_type": kind, "p_operation_id": operation,
            "p_run_id": run_id, "p_payload": payload,
        }).execute().data

    def apply(self, action, run_id, approval):
        kind, operation, payload = action["action"], action["operation_id"], action["payload"]
        if not self.lookup(kind, operation, run_id, payload):
            identity = str(uuid5(NAMESPACE_URL, f"specialist:{run_id}:{operation}"))
            record_approval(store=self.store, action=kind, operation_id=operation, run_id=run_id,
                            approval_id=identity, approved_by=approval["reviewer_id"],
                            payload=payload, expires_at=datetime.fromtimestamp(approval["expires_at"], timezone.utc))
        return self.execute(kind, {**payload, "operation_id": operation, "approved_by": run_id})
