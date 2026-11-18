"""Anonymous browsing sessions and customer-owned shopping cases."""

from hmac import compare_digest
from pathlib import Path
import re

from specialist.workflow.case_state import CaseConflict
from specialist.workflow.proposals import proposal_matches

from .shop_view import render_shop


CASE_ROUTE = re.compile(r"/shop/([a-f0-9-]{36})/?")
ASSETS = {"site.css": "text/css; charset=utf-8", "site.js": "text/javascript; charset=utf-8"}
CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; "
    "img-src https://www.tunisianet.com.tn https://tunisianet.com.tn; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)


def serve_shop(handler, method, path):
    filename = path.removeprefix("/shop/assets/")
    if method == "GET" and path.startswith("/shop/assets/") and filename in ASSETS:
        file = Path(__file__).with_name("shop_assets") / filename
        return handler.send_document(file.read_bytes(), content_type=ASSETS[filename])

    match = CASE_ROUTE.fullmatch(path)
    if path != "/shop/" and match is None:
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
        data = render_shop(csrf, fixture=fixture, case=case, error=error).encode("utf-8")
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
        observe = handler.server.observer.run
        action = fields.get("action")
        if case_id:
            case = service.store.get(case_id, owner)
        if action == "start" and case_id is None:
            case = observe("start", lambda: service.start(owner, fields.get("request", "")))
        elif action == "revise" and case_id:
            case = observe("revise", lambda: service.revise(
                case_id, owner, fields.get("request", ""), expected_revision=int(fields.get("revision", ""))))
        elif action == "research" and case_id:
            case = observe("research", lambda: service.research(case_id, owner))
        elif action == "select" and case_id:
            with service.store.update(case_id, owner) as current:
                if not proposal_matches(current, int(fields.get("revision", "")), fields.get("proposal_hash")):
                    raise CaseConflict("This recommendation has changed. Review the latest setup.")
                current["selected_proposal"] = current["proposal"]["hash"]
        else:
            return handler.send_error(403)
        return handler.redirect(f'/shop/{case["case_id"]}')
    except LookupError:
        return page(error="This search is unavailable in this browser. Start a new search.", status=404)
    except CaseConflict:
        return page(case, error="This search has changed. Refresh to see the latest result.", status=409)
    except ValueError:
        return page(case, error="Enter a request between 1 and 1,200 characters.", status=400)
    except Exception:
        return page(case, error="The search couldn’t finish. Please try again.", status=500)
