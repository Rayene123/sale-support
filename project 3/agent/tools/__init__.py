"""Person 2 tool package with compatibility exports for Person 1's tests.

`agent/tools.py` predates this package and is still used by the existing graph
prototype as an offline fixture adapter. Python resolves this package for
`import agent.tools`; load that fixture module explicitly until Person 1
replaces the graph's direct fixture reads with the injected executor.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

_fixture_path = Path(__file__).resolve().parents[1] / "tools.py"
_fixture_name = "agent._legacy_tool_fixtures"
_fixture_spec = spec_from_file_location(_fixture_name, _fixture_path)
if _fixture_spec is None or _fixture_spec.loader is None:
    raise ImportError("Could not load the existing offline graph fixtures.")
_fixtures = module_from_spec(_fixture_spec)
sys.modules.setdefault(_fixture_name, _fixtures)
_fixture_spec.loader.exec_module(_fixtures)

TICKETS = _fixtures.TICKETS
CUSTOMERS = _fixtures.CUSTOMERS
ORDERS = _fixtures.ORDERS
WRITE_LOG = _fixtures.WRITE_LOG
reset_write_log = _fixtures.reset_write_log
get_ticket = _fixtures.get_ticket
find_customer = _fixtures.find_customer
get_order = _fixtures.get_order
update_ticket_database = _fixtures.update_ticket_database

__all__ = [
    "TICKETS", "CUSTOMERS", "ORDERS", "WRITE_LOG", "reset_write_log",
    "get_ticket", "find_customer", "get_order", "update_ticket_database",
]
