"""Loopback workbench for customer requests and separate sandbox review."""
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from secrets import token_bytes, token_urlsafe
from time import time
from urllib.parse import parse_qs, urlsplit


from specialist.workflow.case_state import CaseConflict

from .shop import serve_shop
from .support import render_support, review_ticket
from .views import case_list, e, login, page, render_case


ROUTE = re.compile(r"/(customer|admin)(?:/([0-9a-f-]{36}|login|logout|support))?/?")
COOKIE_AGE = 8 * 60 * 60


class Workbench(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, port, service, observer, *, customer, reviewer, passwords, fixture, sandbox, shop_service=None):
        self.service, self.observer = service, observer
        self.customer, self.reviewer, self.passwords = customer, reviewer, passwords
        self.fixture, self.sandbox = fixture, sandbox
        self.shop_service = shop_service
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
            return self.redirect("/shop/" if server.shop_service is not None else "/customer/")
        if path == "/shop" and method == "GET" and server.shop_service is not None:
            return self.redirect("/shop/")
        if path.startswith("/shop/") and server.shop_service is not None:
            return serve_shop(self, method, path)
        match = ROUTE.fullmatch(path)
        if not match:
            return self.send_error(404)
        role, target = match.groups()
        if target == "support" and role != "admin":
            return self.send_error(404)
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
                    _, cookie = self.issue_session(role)
                    return self.redirect(f"/{role}/", cookie=cookie)
                if not csrf or not compare_digest(fields.get("csrf", "").encode(), csrf.encode()):
                    return self.send_error(403)
                if target == "logout":
                    return self.redirect(f"/{role}/", cookie=self.cookie(role, "", 0))
                if target == "support":
                    return self.render(role, render_support(csrf, review_ticket(fields)), csrf=csrf)
                return self.process_action(role, target, fields)
            if target in {"login", "logout"}:
                return self.redirect(f"/{role}/")
            if csrf is None:
                return self.render(role, login(role))
            if target == "support":
                return self.render(role, render_support(csrf), csrf=csrf)
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

    def issue_session(self, role):
        csrf = token_urlsafe(24)
        data = f"{int(time()) + COOKIE_AGE}.{csrf}"
        return csrf, self.cookie(role, data + "." + self.server.sign(role, data))

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
        self.send_document(data, status=status)

    def send_document(self, data, *, status=200, cookie=None, content_type="text/html; charset=utf-8", csp=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", csp or
                         "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)
