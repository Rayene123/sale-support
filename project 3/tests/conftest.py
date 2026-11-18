"""Keep the ordinary test suite offline and independent of developer secrets."""
import os

# graph.py loads dotenv at import time. Disable that before test collection so
# ordinary graph tests do not use the developer's local model.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["SPECIALIST_LEGACY_LLM"] = "false"


import socket
import pytest


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Default tests must use fixtures, never a live model, database or scraper."""
    def blocked(*args, **kwargs):
        raise AssertionError("Network disabled in offline tests; use a fixture adapter")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
