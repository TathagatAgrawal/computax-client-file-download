"""Tests for deciding when the app should quit because no page is open."""

import time

from computax_client_file_download.server import Presence


def test_waits_for_startup_period_before_first_page() -> None:
    """Before any page connects, only the startup period counts."""
    p = Presence()
    assert not p.should_exit(grace=0, startup=60)
    p.empty_since -= 61
    assert p.should_exit(grace=0, startup=60)


def test_never_exits_while_a_page_is_open() -> None:
    """An open page keeps the app alive indefinitely."""
    p = Presence()
    p.opened()
    p.empty_since -= 1000
    assert not p.should_exit(grace=0, startup=0)


def test_exits_after_grace_once_last_page_closes() -> None:
    """After the last page closes, a short grace period applies for reloads."""
    p = Presence()
    p.opened()
    p.opened()
    p.closed()
    assert not p.should_exit(grace=0, startup=0)
    p.closed()
    assert not p.should_exit(grace=5, startup=600)
    p.empty_since = time.monotonic() - 6
    assert p.should_exit(grace=5, startup=600)
