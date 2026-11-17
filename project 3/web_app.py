"""Small local web UI for reviewing and approving mock ticket actions.

Run with ``python web_app.py`` and open http://127.0.0.1:8000.
The server binds to loopback and uses the agent's in-process checkpointer.
"""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from agent.graph import run_ticket
from customer_ui import handle_shop


def _e(value: object) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _page(content: str, notice: str = "") -> str:
    notice_style = " error" if "failed" in notice.lower() or "could not" in notice.lower() else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Support Desk | Commerce Ops</title>
  <style>
    :root {{ color-scheme: light; font: 14px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #18221f; background: #f4f6f4; --ink:#18221f; --muted:#77827d; --line:#e6eae7; --green:#176b50; --green-dark:#10523d; --surface:#fff; --canvas:#f4f6f4; }}
    * {{ box-sizing: border-box; }} body {{ margin:0; min-height:100vh; }}
    button,input {{ font:inherit; }}
    .app {{ min-height:100vh; }}
    .sidebar {{ position:fixed; inset:0 auto 0 0; width:236px; background:#fff; border-right:1px solid var(--line); padding:25px 16px; display:flex; flex-direction:column; z-index:2; }}
    .brand {{ display:flex; align-items:center; gap:11px; padding:0 9px 30px; font-size:15px; font-weight:750; letter-spacing:-.3px; }}
    .brand-mark {{ width:34px; height:34px; display:grid; place-items:center; color:#fff; background:var(--green); border-radius:11px; font-size:17px; }}
    .brand small {{ display:block; color:var(--muted); font-size:11px; font-weight:550; letter-spacing:.25px; }}
    .nav-label {{ color:#a0aaa5; font-size:10px; font-weight:750; letter-spacing:1.1px; text-transform:uppercase; padding:9px 12px 8px; }}
    .nav-link {{ display:flex; align-items:center; gap:12px; padding:10px 12px; margin:2px 0; border-radius:9px; color:#66716b; text-decoration:none; font-weight:570; }}
    .nav-link.active {{ color:var(--green-dark); background:#edf5f1; font-weight:700; }} .nav-icon {{ width:19px; text-align:center; font-size:16px; }} .nav-link.disabled {{ opacity:.52; cursor:default; }}
    .nav-count {{ margin-left:auto; color:#829089; font-size:11px; }}
    .sidebar-bottom {{ margin-top:auto; padding:13px 11px 0; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
    .operator {{ display:flex; align-items:center; gap:10px; margin-top:15px; color:var(--ink); font-weight:650; }}
    .avatar {{ width:31px; height:31px; border-radius:50%; display:grid; place-items:center; color:#31584b; background:#e3eee8; font-size:11px; font-weight:750; }}
    .workspace {{ margin-left:236px; min-height:100vh; }}
    .topbar {{ height:68px; display:flex; align-items:center; justify-content:space-between; padding:0 clamp(22px,4vw,56px); background:#fff; border-bottom:1px solid var(--line); }}
    .crumb {{ color:#87918c; font-size:12px; }} .crumb strong {{ color:#46534d; font-weight:650; }}
    .top-actions {{ display:flex; align-items:center; gap:18px; color:#748079; font-size:12px; }}
    .live-dot {{ display:inline-block; width:7px; height:7px; margin-right:7px; border-radius:50%; background:#43a879; box-shadow:0 0 0 3px #e8f5ed; }}
    main {{ width:min(1200px,100%); margin:0 auto; padding:34px clamp(22px,4vw,56px) 54px; }}
    .page-head {{ display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin-bottom:21px; }}
    .eyebrow {{ color:#718078; font-size:10px; letter-spacing:1.3px; font-weight:750; text-transform:uppercase; }}
    h1 {{ margin:5px 0 4px; font-size:27px; line-height:1.2; letter-spacing:-.8px; font-weight:720; }}
    .subhead {{ color:var(--muted); margin:0; }} h2 {{ margin:0; font-size:14px; font-weight:700; letter-spacing:-.1px; }}
    .case-id {{ color:#738078; font-size:12px; font-weight:650; }}
    .notice {{ padding:12px 15px; border:1px solid #d9e9de; border-radius:10px; background:#eff7f1; color:#315b43; margin:0 0 20px; }}
    .notice.error {{ border-color:#f0d6d2; background:#fff3f1; color:#8b4037; }}
    .stepper {{ display:flex; align-items:center; gap:9px; margin:0 0 22px; color:#98a19c; font-size:11px; font-weight:650; }}
    .step {{ display:flex; align-items:center; gap:7px; }} .step-num {{ width:21px; height:21px; display:grid; place-items:center; border:1px solid #dbe2dd; border-radius:50%; font-size:10px; }}
    .step.current {{ color:var(--green-dark); }} .step.current .step-num {{ color:#fff; border-color:var(--green); background:var(--green); }}
    .step.done {{ color:#57806d; }} .step.done .step-num {{ border-color:#d6e9dc; background:#e8f4ec; }} .step-line {{ width:35px; height:1px; background:#dfe5e1; }}
    .review-grid {{ display:grid; grid-template-columns:minmax(0,1.55fr) minmax(260px,.8fr); gap:17px; align-items:start; }}
    .primary-column,.context-column {{ display:grid; gap:17px; }}
    .card {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; box-shadow:0 2px 8px #1e352308; overflow:hidden; }}
    .card-head {{ display:flex; justify-content:space-between; align-items:center; gap:12px; padding:17px 19px; border-bottom:1px solid #edf0ee; }}
    .card-body {{ padding:18px 19px; }} .section-label {{ color:#8a958f; font-size:10px; letter-spacing:.9px; font-weight:750; text-transform:uppercase; }}
    .ticket-title {{ margin:10px 0 7px; font-size:18px; line-height:1.35; font-weight:700; letter-spacing:-.3px; }}
    .ticket-copy {{ margin:0; color:#59665f; line-height:1.65; }}
    .status {{ display:inline-flex; align-items:center; gap:6px; padding:5px 9px; border-radius:99px; background:#f0f2ef; color:#647069; font-size:10px; line-height:1; font-weight:750; letter-spacing:.25px; text-transform:uppercase; white-space:nowrap; }}
    .status::before {{ content:""; width:6px; height:6px; border-radius:50%; background:currentColor; }}
    .status.awaiting_approval {{ color:#986719; background:#fbf3e4; }} .status.completed {{ color:#26734f; background:#e8f4ec; }} .status.rejected,.status.failed {{ color:#9a5146; background:#faeeeb; }}
    .priority {{ display:inline-flex; align-items:center; gap:6px; color:#a16a2a; font-size:11px; font-weight:650; }}
    .split {{ display:flex; justify-content:space-between; gap:12px; }} .field-label {{ color:#87928c; font-size:11px; }} .field-value {{ color:#28342e; font-size:12px; font-weight:650; }}
    .customer-top {{ display:flex; align-items:center; gap:11px; margin-bottom:15px; }}
    .customer-avatar {{ width:38px; height:38px; border-radius:50%; display:grid; place-items:center; color:#4b665a; background:#e8eee9; font-size:12px; font-weight:750; }}
    .customer-name {{ font-weight:700; font-size:13px; }} .customer-email {{ color:#7b8680; font-size:11px; }}
    .mini-row {{ display:flex; justify-content:space-between; gap:12px; padding:9px 0; border-top:1px solid #eef1ef; }}
    .order-head {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }}
    .order-number {{ color:#3e4a44; font-size:12px; font-weight:750; }}
    .order-state {{ padding:4px 8px; border-radius:6px; color:#93661e; background:#fbf3e5; font-size:10px; font-weight:700; text-transform:capitalize; }}
    .product-row {{ display:flex; align-items:center; gap:10px; padding:12px 0; border-top:1px solid #eef1ef; }}
    .product-thumb {{ flex:0 0 38px; width:38px; height:38px; display:grid; place-items:center; border-radius:8px; background:#edf1eb; color:#62806c; font-size:11px; font-weight:750; }}
    .product-name {{ font-size:11px; font-weight:650; }} .product-qty {{ color:#89938d; font-size:10px; }}
    .total-row {{ border-top:1px solid #eef1ef; padding-top:11px; }}
    .proposal-card {{ border-color:#d9e8df; }} .proposal-card .card-head {{ background:#fbfdfb; }}
    .proposal-title {{ display:flex; align-items:center; gap:9px; }} .spark {{ width:27px; height:27px; display:grid; place-items:center; border-radius:8px; color:#327252; background:#e8f3eb; font-size:14px; }}
    .model-tag {{ padding:4px 7px; border:1px solid #e7ece8; border-radius:6px; color:#77837c; font-size:9px; font-weight:650; }}
    .proposal-meta {{ display:flex; flex-wrap:wrap; gap:7px; margin:0 0 15px; }}
    .meta-chip,.evidence-chip {{ display:inline-flex; padding:5px 8px; border-radius:6px; color:#52635a; background:#eff4f0; font-size:10px; font-weight:650; }}
    .response-label {{ margin:0 0 7px; color:#849088; font-size:10px; letter-spacing:.7px; text-transform:uppercase; font-weight:750; }}
    .response {{ margin:0; padding:13px 14px; border-left:3px solid #7eae90; border-radius:0 8px 8px 0; background:#f6f9f6; color:#3d4c43; line-height:1.65; }}
    .evidence {{ display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin-top:14px; }}
    .approval-card {{ grid-column:1/-1; display:flex; align-items:center; justify-content:space-between; gap:22px; padding:18px 20px; border:1px solid #dce7df; border-radius:12px; background:#fff; box-shadow:0 4px 16px #193a2410; }}
    .approval-copy strong {{ display:block; margin-bottom:2px; font-size:13px; }} .approval-copy span {{ color:#7b8780; font-size:11px; }}
    .actions {{ display:flex; gap:9px; flex-wrap:wrap; }} .actions form {{ margin:0; }}
    button {{ min-height:39px; padding:9px 15px; border:1px solid transparent; border-radius:8px; cursor:pointer; font-weight:700; font-size:11px; transition:background .15s,transform .15s; }}
    button:hover {{ transform:translateY(-1px); }} button:focus-visible,input:focus-visible {{ outline:3px solid #9ac7ad; outline-offset:2px; }}
    .approve {{ color:#fff; background:var(--green); }} .approve:hover {{ background:var(--green-dark); }}
    .reject {{ color:#5f6963; border-color:#e2e7e3; background:#fff; }} .reject:hover {{ background:#f6f7f6; }}
    .form-card {{ max-width:640px; }} .search-row {{ display:flex; gap:9px; margin-top:7px; }}
    input {{ width:100%; min-width:0; padding:11px 12px; border:1px solid #dce3de; border-radius:8px; color:var(--ink); background:#fff; }}
    input::placeholder {{ color:#a2aba5; }} .helper {{ margin:8px 0 0; color:#929c96; font-size:11px; }}
    .run-details {{ color:#84655d; font-size:11px; }} .run-details summary {{ cursor:pointer; color:#718078; }}
    .new-review {{ margin-top:21px; }} .new-review .card-body {{ display:flex; align-items:center; justify-content:space-between; gap:16px; }}
    .new-review p {{ margin:3px 0 0; color:#87928c; font-size:11px; }} .new-review button {{ color:#466454; background:#eef4f0; }}
    @media(max-width:900px) {{ .sidebar {{ width:70px; padding:20px 10px; }} .brand {{ justify-content:center; padding:0 0 28px; }} .brand-text,.nav-label,.nav-copy,.nav-count,.sidebar-bottom {{ display:none; }} .nav-link {{ justify-content:center; padding:11px 0; }} .workspace {{ margin-left:70px; }} .review-grid {{ grid-template-columns:minmax(0,1fr); }} .context-column {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media(max-width:600px) {{ .topbar {{ height:56px; padding:0 17px; }} .top-actions .desktop-only {{ display:none; }} main {{ padding:25px 16px 40px; }} .page-head {{ align-items:flex-start; flex-direction:column; gap:8px; }} h1 {{ font-size:23px; }} .context-column {{ grid-template-columns:minmax(0,1fr); }} .approval-card {{ align-items:stretch; flex-direction:column; gap:14px; }} .actions {{ display:grid; grid-template-columns:1fr 1fr; }} .actions form,.actions button {{ width:100%; }} .search-row {{ align-items:stretch; flex-direction:column; }} .search-row button {{ width:100%; }} .step-line {{ width:15px; }} .stepper {{ gap:6px; font-size:9px; }} .step {{ gap:5px; }} .new-review .card-body {{ align-items:flex-start; flex-direction:column; }} }}
  </style>
</head>
<body><div class="app">
  <aside class="sidebar">
    <div class="brand"><span class="brand-mark">S</span><span class="brand-text">Shopline Ops<small>COMMERCE SUPPORT</small></span></div>
    <div class="nav-label">Admin workspace</div>
    <a class="nav-link active" href="/admin"><span class="nav-icon">▤</span><span class="nav-copy">Support tickets</span></a>
    <div class="sidebar-bottom">Ticket review only<div class="operator"><span class="avatar">AD</span><span>Admin reviewer</span></div></div>
  </aside>
  <div class="workspace">
    <header class="topbar"><div class="crumb">Admin workspace&nbsp; / &nbsp;<strong>Support tickets</strong></div><div class="top-actions"><a href="/shop" style="color:#176b50;text-decoration:none;font-weight:650">Open customer shop ↗</a><span class="desktop-only"><i class="live-dot"></i>Local demo</span><span class="avatar">AD</span></div></header>
    <main>
      {f'<div class="notice{notice_style}">{_e(notice)}</div>' if notice else ''}
      {content}
    </main>
  </div>
</div></body></html>"""


def _new_run_form(ticket_id: str = "TICKET-102") -> str:
    return f"""<div class="page-head"><div><div class="eyebrow">Customer care / Review queue</div>
      <h1>Support operations</h1><p class="subhead">Review an order issue and decide on the proposed customer response.</p></div></div>
      <section class="card form-card"><div class="card-head"><div><div class="section-label">Open a case</div><h2 style="margin-top:4px">Find a support ticket</h2></div><span class="case-id">DEMO DATA</span></div>
      <div class="card-body"><form method="post" action="/admin"><input type="hidden" name="action" value="start">
        <label class="section-label" for="ticket_id">Ticket ID</label><div class="search-row">
        <input id="ticket_id" name="ticket_id" value="{_e(ticket_id)}" placeholder="e.g. TICKET-102" required>
        <button class="approve" type="submit">Review ticket&nbsp; →</button></div>
        <p class="helper">Try TICKET-102 for a delayed order or TICKET-103 for a missing package.</p>
      </form></div></section>"""


def _render_result(result: dict, notice: str = "") -> str:
    status = result.get("status", "failed")
    ticket = result.get("ticket")
    subject = ticket.get("subject") if ticket else "Ticket review"
    current_step = "3" if status in {"completed", "rejected", "failed"} else "2"
    stepper = f"""<div class="stepper"><span class="step done"><span class="step-num">✓</span>Review case</span><i class="step-line"></i>
      <span class="step {'current' if status == 'awaiting_approval' else 'done'}"><span class="step-num">{'2' if status == 'awaiting_approval' else '✓'}</span>Decision</span><i class="step-line"></i>
      <span class="step {'current' if status in {'completed','rejected','failed'} else ''}"><span class="step-num">{current_step}</span>Outcome</span></div>"""
    status_text = {"awaiting_approval": "Awaiting approval", "completed": "Approved", "rejected": "Rejected", "failed": "Needs attention"}.get(status, status.replace("_", " ").title())
    body = f"""<div class="page-head"><div><div class="eyebrow">Support inbox&nbsp; / &nbsp;Case review</div>
      <h1>{_e(subject)}</h1><p class="subhead">Ticket <span class="case-id">{_e(result.get('ticket_id'))}</span></p></div>
      <span class="status {_e(status)}">{_e(status_text)}</span></div>{stepper}"""
    if ticket:
        customer = result.get("customer") or {}
        order = result.get("order") or {}
        initials = "".join(part[0] for part in customer.get("name", "?").split()[:2]).upper()
        products = "".join(
            f"<div class='product-row'><span class='product-thumb'>{_e(item.get('item_id', 'IT')[-2:])}</span><span><span class='product-name'>{_e(item.get('name'))}</span><br><span class='product-qty'>Qty {_e(item.get('quantity'))}</span></span></div>"
            for item in order.get("items", [])
        ) or "<p class='helper'>No item details available.</p>"
        body += f"""<div class="review-grid"><div class="primary-column">
          <section class="card"><div class="card-head"><div class="proposal-title"><span class="spark">✉</span><div><div class="section-label">Customer message</div><h2 style="margin-top:3px">Ticket details</h2></div></div><span class="priority">●&nbsp; Order issue</span></div>
            <div class="card-body"><div class="ticket-title">{_e(ticket.get('subject'))}</div><p class="ticket-copy">{_e(ticket.get('description'))}</p></div></section>"""
    else:
        body += "<div class='review-grid'><div class='primary-column'>"
    draft = result.get("draft")
    if draft:
        labels = ", ".join(draft.get("proposed_labels", []))
        evidence = ", ".join(draft.get("evidence_ids", []))
        raw_source = draft.get("draft_source", "Agent draft")
        source_label = "OpenAI draft" if str(raw_source).startswith("OpenAI") else "Offline fallback"
        body += f"""<section class="card proposal-card"><div class="card-head"><div class="proposal-title"><span class="spark">✦</span><div><div class="section-label">Suggested resolution</div><h2 style="margin-top:3px">Proposed action</h2></div></div><span class="model-tag">{_e(source_label)}</span></div>
          <div class="card-body"><div class="proposal-meta"><span class="meta-chip">Status: {_e(draft.get('proposed_status'))}</span>{''.join(f'<span class="meta-chip">{_e(label)}</span>' for label in draft.get('proposed_labels', []))}</div>
          <p class="response-label">Reply to customer</p><p class="response">{_e(draft.get('response'))}</p>
          <div class="evidence"><span class="field-label">Based on</span>{''.join(f'<span class="evidence-chip">{_e(item)}</span>' for item in draft.get('evidence_ids', []))}</div>
          <details class="run-details" style="margin-top:13px"><summary>Operation details</summary><p>Operation ID: {_e(draft.get('operation_id'))}</p></details>
          </div></section>"""
    if ticket:
        body += "</div><aside class='context-column'>"
        body += f"""<section class="card" id="customers"><div class="card-head"><h2>Customer</h2><span class="section-label">PROFILE</span></div><div class="card-body">
          <div class="customer-top"><span class="customer-avatar">{_e(initials or 'C')}</span><span><span class="customer-name">{_e(customer.get('name'))}</span><br><span class="customer-email">{_e(customer.get('email'))}</span></span></div>
          <div class="mini-row"><span class="field-label">Customer ID</span><span class="field-value">{_e(customer.get('customer_id'))}</span></div>
          </div></section>
          <section class="card" id="orders"><div class="card-head"><h2>Order summary</h2><span class="section-label">ORDER</span></div><div class="card-body">
          <div class="order-head"><span class="order-number">{_e(order.get('order_id'))}</span><span class="order-state">{_e(order.get('status'))}</span></div>
          {products}<div class="mini-row total-row"><span class="field-label">Order total</span><span class="field-value">{_e(order.get('total'))} {_e(order.get('currency'))}</span></div>
          </div></section></aside>"""
    if status in {"awaiting_approval", "partially_completed"}:
        common = f"""<input type="hidden" name="run_id" value="{_e(result.get('run_id'))}">
          <input type="hidden" name="ticket_id" value="{_e(result.get('ticket_id'))}">
          <input type="hidden" name="operation_id" value="{_e(draft.get('operation_id') if draft else '')}">"""
        body += f"""<section class="approval-card"><div class="approval-copy"><strong>Ready for your review</strong><span>Nothing is changed until you approve this response.</span></div>
          <div class="actions"><form method="post" action="/admin">{common}<input type="hidden" name="action" value="reject"><button class="reject" type="submit">Reject proposal</button></form>
          <form method="post" action="/admin">{common}<input type="hidden" name="action" value="approve"><button class="approve" type="submit">Approve &amp; apply&nbsp; →</button></form></div></section>"""
    elif status == "completed":
        body += "<section class='approval-card'><div class='approval-copy'><strong>Update applied</strong><span>The approved mock ticket update has been recorded.</span></div><span class='status completed'>Complete</span></section>"
    elif status == "rejected":
        body += "<section class='approval-card'><div class='approval-copy'><strong>Proposal rejected</strong><span>No ticket update was made.</span></div><span class='status rejected'>No changes</span></section>"
    errors = result.get("errors") or []
    if errors:
        body += "<section class='card' style='margin-top:17px'><div class='card-body'><div class='section-label'>Run details</div><p class='run-details'>" + "<br>".join(f"{_e(error)}" for error in errors) + "</p></div></section>"
    body += "</div>" if ticket else "</div></div>"
    if ticket and status in {"completed", "rejected", "failed"}:
        body += "<section class='card new-review'><div class='card-body'><div><h2>Review another ticket?</h2><p>Return to the queue and start a new review.</p></div><a href='/admin'><button type='button'>Back to inbox&nbsp; →</button></a></div></section>"
    elif not ticket:
        body += _new_run_form()
    return _page(body, notice)


class ApprovalHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            self.send_response(303)
            self.send_header("Location", "/admin")
            self.end_headers()
            return
        if self.path == "/shop":
            from customer_ui import _layout, _search_form
            self._send_html(_layout(_search_form()))
            return
        if self.path != "/admin":
            self.send_error(404)
            return
        self._send_html(_page(_new_run_form()))

    def do_POST(self) -> None:
        if self.path not in {"/admin", "/shop"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid content length")
            return
        if length < 0 or length > 8192:
            self.send_error(413, "Form is too large")
            return
        form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"), keep_blank_values=True)
        value = lambda key: form.get(key, [""])[0]
        if self.path == "/shop":
            page, status = handle_shop(form)
            self._send_html(page, status=status)
            return
        try:
            if value("action") == "start":
                result = run_ticket(value("ticket_id").strip())
                notice = (
                    "Ticket context loaded. No action has been applied."
                    if result.get("status") == "awaiting_approval"
                    else "Ticket review could not be completed. See the details below."
                    if result.get("status") == "failed"
                    else "Ticket review started."
                )
            elif value("action") in {"approve", "reject"}:
                decision = "approve" if value("action") == "approve" else "reject"
                result = run_ticket(
                    value("ticket_id"),
                    {"decision": decision, "operation_id": value("operation_id")},
                    run_id=value("run_id"),
                )
                notice = "Approval applied." if decision == "approve" else "Proposal rejected. No write was made."
            else:
                self._send_html(_page(_new_run_form(), "Unknown form action."), status=400)
                return
        except Exception as exc:
            self._send_html(_page(_new_run_form(), f"Could not process the request: {exc}"), status=500)
            return
        self._send_html(_render_result(result, notice))

    def _send_html(self, page: str, status: int = 200) -> None:
        encoded = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:
        # Keep local demo logs quiet; server errors remain visible to the user.
        return


def main() -> None:
    host, port = "127.0.0.1", 8000
    server = HTTPServer((host, port), ApprovalHandler)
    print(f"Shopline demo running at http://{host}:{port} (admin: /admin, customer: /shop; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping approval app...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
