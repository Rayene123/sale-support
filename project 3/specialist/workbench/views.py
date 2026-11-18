"""Minimal HTML views for the local workbench."""

from html import escape

from specialist.workflow.case_state import APPROVABLE, EXECUTABLE, FOLLOW_UP, can_revise


STYLE = """
body { font: 16px/1.5 system-ui, sans-serif; max-width: 760px; padding: 24px; margin: auto }
nav, .buttons { display: flex; flex-wrap: wrap; gap: 12px; align-items: center }
nav { justify-content: space-between; border-bottom: 1px solid #aaa; padding-bottom: 10px }
textarea { box-sizing: border-box; width: 100%; min-height: 6rem }
input, textarea, button { font: inherit; padding: 6px }
label, details { display: block; margin-block: 12px }
section { border-top: 1px solid #bbb; margin-top: 20px; padding-top: 8px }
summary { cursor: pointer } li { margin-bottom: 6px } code { overflow-wrap: anywhere }
.notice { padding: 10px; border: 1px solid #888 } .error { color: #9b1717 }
"""


def e(value):
    return escape(str(value), quote=True)


def page(role, content, *, source, sandbox, error="", csrf=None):
    sign_out = ""
    if csrf:
        sign_out = form(f"/{role}/logout", csrf, '<button>Sign out</button>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Specialist · {e(role.title())}</title><style>{STYLE}</style></head>
<body><nav><a href="/customer/">Customer</a><a href="/admin/">Reviewer</a>{sign_out}</nav>
<main><h1>The Specialist</h1><p class="notice">{e(source)} · {e(sandbox)}</p>
{f'<p class="error" role="alert">{e(error)}</p>' if error else ''}
{content}</main></body></html>"""


def form(path, csrf, content, **fields):
    hidden = "".join(f'<input type="hidden" name="{e(key)}" value="{e(value)}">'
                     for key, value in {"csrf": csrf, **fields}.items())
    return f'<form method="post" action="{e(path)}">{hidden}{content}</form>'


def login(role):
    return (f'<h2>{"Reviewer" if role == "admin" else "Customer"} sign in</h2>'
            f'<form method="post" action="/{role}/login">'
            '<label>Local passcode <input type="password" name="password" required '
            'autocomplete="current-password" maxlength="256"></label><button>Sign in</button></form>')


def request_form(path, csrf, action, revision=None):
    label = "What would you like to find?" if action == "start" else "Reply or change your requirements"
    fields = {"action": action}
    if revision is not None:
        fields["revision"] = revision
    return form(path, csrf, f'<label>{label}<textarea name="request" '
                'required maxlength="1200"></textarea></label><button>Send request</button>', **fields)


def rows(values):
    return "<ul>" + "".join(f"<li>{item}</li>" for item in values) + "</ul>"


def case_list(role, cases, csrf):
    content = request_form("/customer/", csrf, "start") if role == "customer" else (
        '<h2>Review queue</h2><p><a href="/admin/support/">Support tickets</a></p>')
    return content + (rows(f'<a href="/{role}/{e(case["case_id"])}">Case {e(case["case_id"][:8])}</a>'
                           f' · {e(case["status"].replace("_", " "))}' for case in cases)
                      if cases else "<p>No cases yet.</p>")


def finding_rows(findings, fixture):
    details = []
    for finding in findings:
        facts = []
        for fact in finding.get("evidence", []):
            link = fact.get("url", "")
            origin = "fixture" if fixture else f'<a href="{e(link)}" rel="noreferrer">Listing</a>'
            facts.append(f'{e(fact.get("field", ""))} = {e(fact.get("value", ""))} · {origin}'
                         f' · {e(fact.get("fetched_at", ""))}')
        text = f'<strong>{e(finding["verdict"].title())}</strong> · {e(finding["reason"])}'
        details.append(text + (rows(facts) if facts else ""))
    return rows(details)


def render_case(case, role, csrf, fixture):
    revision, case_id, status = case["revision"], case["case_id"], case["status"]
    path = f"/{role}/{case_id}"
    body = (f'<p><a href="/{role}/">All cases</a> · Case <code>{e(case_id[:8])}</code>'
            f' · Revision {revision}</p><h2>{e(status.replace("_", " ").capitalize())}</h2>')
    if case.get("questions"):
        body += rows(map(e, case["questions"]))
    if case.get("changes"):
        body += "<h3>Changed since review</h3>" + rows(
            f'{e(c["product_id"])} · {e(c["field"])} · {e(c["before"])} → {e(c["after"])}' for c in case["changes"])
    proposal = case.get("proposal")
    if proposal:
        order, notice = (action["payload"] for action in proposal["actions"])
        body += "<section><h3>Proposed sandbox order</h3>" + rows(
            f'{e(item["quantity"])} × {e(item["name"])} · {e(item["unit_price_tnd"])} TND each'
            for item in order["items"])
        body += f'<p><strong>{e(order["total_tnd"])} TND total</strong></p></section>'
        if role == "admin":
            body += f'<p>Sandbox notification · {e(notice["message"])}</p><p>Proposal <code>{e(proposal["hash"])}</code></p>'
            if status in APPROVABLE:
                body += form(path, csrf, '<div class="buttons"><button name="action" value="approve">Approve</button>'
                             '<button name="action" value="reject">Reject</button>'
                             '<button name="action" value="timeout">Expire</button></div>',
                             revision=revision, proposal_hash=proposal["hash"])
            if status in EXECUTABLE:
                label = "Retry unfinished action" if status != "approved" else "Execute next sandbox action"
                body += form(path, csrf, f'<button>{label}</button>', action="execute",
                             revision=revision, proposal_hash=proposal["hash"])
        body += rows(f'{e(action["action"].replace("_", " "))} · '
                     + ("Receipt confirmed" if action["operation_id"] in case["receipts"] else "Pending")
                     for action in proposal["actions"])
    if case.get("findings"):
        body += "<details open><summary>Verification</summary>" + finding_rows(case["findings"], fixture) + "</details>"
    if case.get("alternatives"):
        body += "<details><summary>Other candidates checked</summary>"
        for alternative in case["alternatives"]:
            names = ", ".join(item["name"] for item in alternative["items"].values())
            body += f'<p>{e(names)}</p>' + finding_rows(alternative["findings"], fixture)
        body += "</details>"
    if role == "customer" and status in FOLLOW_UP and can_revise(case):
        body += request_form(path, csrf, "revise", revision)
    if status == "research_pending" and role == "customer":
        body += form(path, csrf, "<button>Resume research</button>", action="research")
    if role == "admin" and case["trajectory"]:
        body += "<details><summary>Run trace</summary>" + rows(
            f'{e(event["actor"])} · {e(event["action"].replace("_", " "))} · '
            f'{e(event["elapsed_ms"])} ms · revision {e(event["revision"])}'
            for event in case["trajectory"]) + "</details>"
    if role == "customer" and case["trajectory"]:
        labels = {"interpret_setup": "Interpreted the request", "search_catalog": "Searched the catalog",
                  "inspect_listing": "Read an exact listing", "check_candidate": "Checked product evidence",
                  "broaden_research": "Tried another search", "receipt_confirmed": "Confirmed a sandbox receipt"}
        steps = [labels[event["action"]] for event in case["trajectory"] if event["action"] in labels]
        if steps:
            body += "<details><summary>Case activity</summary>" + rows(steps) + "</details>"
    return body
