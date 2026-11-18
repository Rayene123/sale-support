"""Expose the secondary fixture-based ticket review in the existing workbench."""

from threading import Lock
from uuid import UUID

from specialist.contracts.validation import validate_identifier

from .views import e, form, rows


SUPPORT_PATH = "/admin/support/"
_review_lock = Lock()


def review_ticket(fields):
    # Load LangGraph only for ticket review. Serialize its process-local runs.
    from specialist.support.graph import run_ticket

    ticket_id = validate_identifier(fields.get("ticket_id", "").strip())
    action = fields.get("action")
    with _review_lock:
        if action == "start":
            return run_ticket(ticket_id)
        if action in {"approve", "reject"}:
            run_id = str(UUID(fields.get("run_id", "")))
            operation_id = str(UUID(fields.get("operation_id", "")))
            return run_ticket(ticket_id, {"decision": action, "operation_id": operation_id}, run_id=run_id)
    raise ValueError("Unknown support action")


def render_support(csrf, result=None):
    content = ('<p><a href="/admin/">Review queue</a></p><h2>Support tickets</h2>'
               '<p>Fictional tickets and simulated updates for this session.</p>')
    content += form(SUPPORT_PATH, csrf, '<label>Ticket ID <input name="ticket_id" required maxlength="64" '
                    'placeholder="TICKET-102"></label><button>Review ticket</button>', action="start")
    if result is None:
        return content
    status = result["status"]
    content += f'<h3>{e(result["ticket_id"])} · {e(status.replace("_", " ").capitalize())}</h3>'
    if result.get("errors"):
        content += rows(map(e, result["errors"]))
    draft = result.get("draft")
    if draft:
        content += (f'<p>Proposed status · {e(draft["proposed_status"])}</p>'
                    f'<p>Labels · {e(", ".join(draft["proposed_labels"]))}</p>'
                    f'<p>{e(draft["response"])}</p>')
        if status == "awaiting_approval":
            content += form(SUPPORT_PATH, csrf, '<div class="buttons">'
                            '<button name="action" value="approve">Approve simulated update</button>'
                            '<button name="action" value="reject">Reject</button></div>',
                            ticket_id=result["ticket_id"], run_id=result["run_id"],
                            operation_id=draft["operation_id"])
    return content
