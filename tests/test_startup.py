"""Tests for how the app starts when its port is unavailable."""

import socket
from pathlib import Path

import pytest

from computax_client_file_download import main


def test_busy_port_exits_with_a_clear_message(tmp_path: Path) -> None:
    """Asking for a port that is already in use stops with an explanation."""
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        with pytest.raises(SystemExit) as exc:
            main(["--port", str(port), "--no-browser", "--root", str(tmp_path)])
    assert f"could not listen on port {port}" in str(exc.value)
