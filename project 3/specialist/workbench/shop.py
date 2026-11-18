"""Anonymous browsing sessions and customer-owned shopping cases."""

from contextlib import contextmanager
from hmac import compare_digest
from pathlib import Path
import re
from threading import Event
from time import monotonic

from specialist.workflow.case_state import CaseConflict
from specialist.workflow.cancellation import ShoppingCancelled, cancellable, check_cancelled
from specialist.workflow.proposals import proposal_matches

from .shop_view import render_shop


CASE_ROUTE = re.compile(r"/shop/([a-f0-9-]{36})/?")
OPERATION = re.compile(r"[a-f0-9-]{36}")
ASSETS = {"site.css": "text/css; charset=utf-8", "site.js": "text/javascript; charset=utf-8"}
CSP = (
    "default-src 'none'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
    "script-src 'self'; connect-src 'self'; "
    "img-src https://www.tunisianet.com.tn https://tunisianet.com.tn; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)


def _prune_counters(server):
    now = monotonic()
    for key, (_, deadline) in tuple(server.shop_requests.items()):
        if deadline is not None and deadline <= now:
            server.shop_requests.pop(key)


@contextmanager
def _shopping_request(server, owner, operation):
    if not operation:
        yield
        return
    if not OPERATION.fullmatch(operation):
        raise ValueError("Invalid search identifier")
    key = (owner, operation)
    with server.shop_request_lock:
        _prune_counters(server)
        previous = server.shop_requests.get(key)
        if (previous and previous[1] is None) or (previous is None and len(server.shop_requests) >= 128):
            raise CaseConflict("This search is already running")
        event = previous[0] if previous else Event()
        server.shop_requests[key] = (event, None)
    try:
        with cancellable(event):
            check_cancelled()
            yield
    finally:
        with server.shop_request_lock:
            server.shop_requests.pop(key, None)


def _stop_request(server, owner, operation):
    if not OPERATION.fullmatch(operation):
        raise ValueError("Invalid search identifier")
    with server.shop_request_lock:
        _prune_counters(server)
        key = (owner, operation)
        registered = server.shop_requests.get(key)
        if registered:
            registered[0].set()
        elif len(server.shop_requests) < 128:
            event = Event()
            event.set()
            server.shop_requests[key] = (event, monotonic() + 60)


def serve_shop(handler, method, path):
    filename = path.removeprefix("/shop/assets/")
    if method == "GET" and path.startswith("/shop/assets/") and filename in ASSETS:
        file = Path(__file__).with_name("shop_assets") / filename
        return handler.send_document(file.read_bytes(), content_type=ASSETS[filename])

    match = CASE_ROUTE.fullmatch(path)
    stopping = method == "POST" and path == "/shop/stop/"
    if path != "/shop/" and match is None and not stopping:
        return handler.send_error(404)
    case_id = match[1] if match else None
    csrf = handler.session("shop")
    cookie = None
    if csrf is None and method == "GET":
        csrf, cookie = handler.issue_session("shop")
    owner = f"shop-{csrf}"
    service = handler.server.shop_service
    fixture = handler.server.fixture

    def page(case=None, *, error="", status=200):
        recent = service.store.recent_chats(owner) if csrf else []
        data = render_shop(csrf, fixture=fixture, case=case, error=error, recent=recent).encode("utf-8")
        return handler.send_document(data, status=status, cookie=cookie, csp=CSP)

    case = None
    try:
        if method == "GET":
            return page(service.store.get(case_id, owner) if case_id else None)
        origin = handler.headers.get("Origin")
        if (origin and origin != f"http://{handler.headers['Host']}") or handler.headers.get("Sec-Fetch-Site") == "cross-site":
            return handler.send_error(403)
        fields = handler.fields()
        if not csrf or not compare_digest(fields.get("csrf", "").encode(), csrf.encode()):
            return handler.send_error(403)
        if stopping:
            _stop_request(handler.server, owner, fields.get("operation", ""))
            handler.send_response(204)
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            return
        observe = handler.server.observer.run
        action = fields.get("action")
        if case_id:
            case = service.store.get(case_id, owner)
        with _shopping_request(handler.server, owner, fields.get("operation")):
            if action == "start" and case_id is None:
                case = observe("start", lambda: service.start(owner, fields.get("request", "")))
            elif action == "revise" and case_id:
                case = observe("revise", lambda: service.revise(
                    case_id, owner, fields.get("request", ""), expected_revision=int(fields.get("revision", ""))))
            elif action == "research" and case_id:
                case = observe("research", lambda: service.research(case_id, owner))
            elif action == "refresh" and case_id:
                case = observe("refresh", lambda: service.refresh_shopping(
                    case_id, owner, revision=int(fields.get("revision", "")), proposal_hash=fields.get("proposal_hash")))
            elif action == "select" and case_id:
                with service.store.update(case_id, owner) as current:
                    if not proposal_matches(current, int(fields.get("revision", "")), fields.get("proposal_hash")):
                        raise CaseConflict("This recommendation has changed. Review the latest setup.")
                    current["selected_proposal"] = current["proposal"]["hash"]
            else:
                return handler.send_error(403)
        return handler.redirect(f'/shop/{case["case_id"]}')
    except ShoppingCancelled:
        try:
            return page(case, error="Search stopped.", status=409)
        except (BrokenPipeError, ConnectionResetError):
            return
    except LookupError:
        return page(error="This search is unavailable in this browser. Start a new search.", status=404)
    except CaseConflict:
        return page(case, error="This search has changed. Refresh to see the latest result.", status=409)
    except ValueError:
        return page(case, error="Enter a request between 1 and 1,200 characters.", status=400)
    except Exception:
        return page(case, error="The search couldn’t finish. Please try again.", status=500)
