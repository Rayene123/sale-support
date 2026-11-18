"""Cooperative cancellation for a shopping request."""

from contextlib import contextmanager
from contextvars import ContextVar


_active = ContextVar("shop_cancellation", default=None)


class ShoppingCancelled(RuntimeError):
    pass


@contextmanager
def cancellable(event):
    token = _active.set(event)
    try:
        yield
    finally:
        _active.reset(token)


def check_cancelled():
    event = _active.get()
    if event is not None and event.is_set():
        raise ShoppingCancelled
