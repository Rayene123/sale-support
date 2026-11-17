"""Persist a human decision from a trusted server, never from the model itself."""
from datetime import datetime

from agent.tools.payloads import canonical_action_payload
from sandbox.store import SandboxStore


def record_approval(*, store: SandboxStore, action: str, operation_id: str,
                    run_id: str, approval_id: str, approved_by: str,
                    payload: dict, expires_at: datetime) -> dict:
    """The caller must authenticate the human and authorize this run first.

    Pass the server-held proposal and authenticated identity, not browser/model
    assertions. This helper only validates/persists; it is not an auth endpoint.
    """
    if store.client is None:
        raise ValueError("Approval persistence requires the connected sandbox.")
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("Approval expiry must include a timezone.")
    result = store.client.rpc("record_commerce_approval", {
        "p_action_type": action, "p_operation_id": operation_id,
        "p_run_id": run_id, "p_approval_id": approval_id,
        "p_approved_by": approved_by,
        "p_payload": canonical_action_payload(action, payload),
        "p_expires_at": expires_at.isoformat(),
    }).execute().data
    if not isinstance(result, dict) or result.get("success") is not True or result.get("approval_id") != approval_id:
        raise RuntimeError("Database did not confirm the approval.")
    return result
