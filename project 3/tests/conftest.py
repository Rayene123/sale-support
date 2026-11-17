"""Keep the ordinary test suite offline and independent of developer secrets."""
import os

# graph.py loads dotenv at import time. Disable that before test collection so
# a developer's OPENAI_API_KEY can never cause ordinary graph tests to call an
# external model service.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.pop("OPENAI_API_KEY", None)


import socket
import pytest


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Default tests must use fixtures, never a live model, database or scraper."""
    def blocked(*args, **kwargs):
        raise AssertionError("Network disabled in offline tests; use a fixture adapter")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
