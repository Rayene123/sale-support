"""Loopback workbench for customer requests and separate sandbox review."""
from argparse import ArgumentParser
from contextlib import ExitStack
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from html import escape
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
from secrets import token_bytes, token_urlsafe
from time import time
from urllib.parse import parse_qs, urlsplit

from dotenv import load_dotenv

from agent.observability import Observability, langsmith_exporter
from agent.specialist.coordinator import CaseConflict, Specialist
from agent.specialist.sandbox_writer import SandboxWriter
from agent.specialist.store import CaseStore
from agent.tools.schemas import validate_identifier
from eval.specialist_demo_catalog import DemoCatalog
from sandbox.local_rpc import LocalSandbox
from sandbox.store import SandboxStore


ROUTE = re.compile(r"/(customer|admin)(?:/([0-9a-f-]{36}|login|logout))?/?")
APPROVABLE = {"awaiting_approval", "reapproval_required"}
EXECUTABLE = {"approved", "partially_completed", "reconciliation_required"}
FOLLOW_UP = {"awaiting_clarification", "awaiting_approval", "verification_blocked",
             "reapproval_required", "planner_unavailable", "source_unavailable"}
COOKIE_AGE = 8 * 60 * 60
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
    content = request_form("/customer/", csrf, "start") if role == "customer" else "<h2>Review queue</h2>"
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
    if role == "customer" and status in FOLLOW_UP:
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


class Workbench(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, port, service, observer, *, customer, reviewer, passwords, fixture, sandbox):
        self.service, self.observer = service, observer
        self.customer, self.reviewer, self.passwords = customer, reviewer, passwords
        self.fixture, self.sandbox = fixture, sandbox
        self.session_key = token_bytes(32)
        super().__init__(("127.0.0.1", port), Handler)

    def sign(self, role, data):
        return hmac_new(self.session_key, f"{role}:{data}".encode(), sha256).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(15)
        super().setup()

    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def dispatch(self, method):
        server = self.server
        host = self.headers.get("Host")
        port = server.server_port
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            return self.send_error(400)
        path = urlsplit(self.path).path
        if path == "/" and method == "GET":
            return self.redirect("/customer/")
        match = ROUTE.fullmatch(path)
        if not match:
            return self.send_error(404)
        role, target = match.groups()
        csrf = self.session(role)
        try:
            if method == "POST":
                origin = self.headers.get("Origin")
                if (origin and origin != f"http://{host}") or self.headers.get("Sec-Fetch-Site") == "cross-site":
                    return self.send_error(403)
                fields = self.fields()
                if target == "login":
                    if not compare_digest(fields.get("password", "").encode(), server.passwords[role].encode()):
                        return self.render(role, login(role), error="Invalid passcode.", status=401)
                    data = f"{int(time()) + COOKIE_AGE}.{token_urlsafe(24)}"
                    return self.redirect(f"/{role}/", cookie=self.cookie(role, data + "." + server.sign(role, data)))
                if not csrf or not compare_digest(fields.get("csrf", "").encode(), csrf.encode()):
                    return self.send_error(403)
                if target == "logout":
                    return self.redirect(f"/{role}/", cookie=self.cookie(role, "", 0))
                return self.process_action(role, target, fields)
            if target in {"login", "logout"}:
                return self.redirect(f"/{role}/")
            if csrf is None:
                return self.render(role, login(role))
            owner = server.customer if role == "customer" else None
            if target is None:
                return self.render(role, case_list(role, server.service.store.recent(owner), csrf), csrf=csrf)
            case = self.load_case(role, target)
            return self.render(role, render_case(case, role, csrf, server.fixture), csrf=csrf)
        except LookupError:
            self.send_error(404)
        except CaseConflict as error:
            self.render(role, f'<p><a href="{e(path)}">Reload case</a></p>', csrf=csrf, error=str(error), status=409)
        except ValueError:
            self.render(role, f'<p><a href="{e(path)}">Return</a></p>', csrf=csrf, error="Check the submitted fields.", status=400)
        except Exception:
            self.render(role, f'<p><a href="{e(path)}">Reload case</a></p>', csrf=csrf,
                        error="The request could not be completed. Check the case before retrying.", status=500)

    def load_case(self, role, case_id):
        store = self.server.service.store
        owner = store.owner_for_review(case_id) if role == "admin" else self.server.customer
        return store.get(case_id, owner)

    def process_action(self, role, case_id, fields):
        service = self.server.service
        observe = self.server.observer.run
        action = fields.get("action")
        request = fields.get("request", "")
        if role == "customer" and case_id is None and action == "start":
            case = observe("start", lambda: service.start(self.server.customer, request))
        elif case_id is not None:
            case = self.load_case(role, case_id)
            owner = case["customer_id"]
            if role == "customer" and action == "revise":
                case = observe("revise", lambda: service.revise(case_id, owner, request,
                                                               expected_revision=int(fields.get("revision", ""))))
            elif role == "customer" and action == "research":
                case = observe("research", lambda: service.research(case_id, owner))
            elif role == "admin" and action in {"approve", "reject", "timeout"}:
                case = observe("decide", lambda: service.decide(
                    case_id, owner, reviewer_id=self.server.reviewer, revision=int(fields.get("revision", "")),
                    proposal_hash=fields.get("proposal_hash", ""), decision=action))
            elif role == "admin" and action == "execute":
                case = observe("execute", lambda: service.execute_next(
                    case_id, owner, expected_revision=int(fields.get("revision", "")),
                    expected_hash=fields.get("proposal_hash", "")))
            else:
                return self.send_error(403)
        else:
            return self.send_error(403)
        self.redirect(f'/{role}/{case["case_id"]}')

    def fields(self):
        if self.headers.get_content_type() != "application/x-www-form-urlencoded":
            raise ValueError("Unexpected content type")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 8192:
            raise ValueError("Unexpected form size")
        values = parse_qs(self.rfile.read(length).decode("utf-8"), max_num_fields=12, keep_blank_values=True)
        if any(len(value) != 1 for value in values.values()):
            raise ValueError("Repeated field")
        return {key: value[0] for key, value in values.items()}

    def session(self, role):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
            value = cookies[f"specialist_{role}"].value
            expires, csrf, signature = value.split(".")
            if int(expires) >= time() and compare_digest(signature, self.server.sign(role, f"{expires}.{csrf}")):
                return csrf
        except (CookieError, KeyError, ValueError, TypeError):
            pass
        return None

    @staticmethod
    def cookie(role, value, age=COOKIE_AGE):
        return f"specialist_{role}={value}; Path=/{role}; Max-Age={age}; HttpOnly; SameSite=Strict"

    def redirect(self, location, *, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def render(self, role, body, *, error="", status=200, csrf=None):
        data = page(role, body, error=error, csrf=csrf,
                    source="Fictional catalog fixtures" if self.server.fixture else "Live Tunisianet catalog",
                    sandbox=self.server.sandbox).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)


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
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    load_dotenv(root.parent / ".env")
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
                store.clear()
                result = client.rpc("reset_sale_support_sandbox").execute().data
                if not isinstance(result, dict) or result.get("operation_history_cleared") is not True:
                    raise RuntimeError("Local database did not confirm the reset.")
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


if __name__ == "__main__":
    main()
