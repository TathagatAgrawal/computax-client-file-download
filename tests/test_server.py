"""End-to-end tests of the HTTP API on a real local server (folder dialog stubbed)."""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from computax_client_file_download.server import AppServer, AppState


class StubDialog:
    """Stands in for the native folder dialog."""

    is_open = False

    def __init__(self, answer: str | None) -> None:
        """Remember the path the 'user' will pick."""
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def pick(self, title: str, initial: str = "") -> str | None:
        """Record the call and return the canned answer."""
        self.calls.append((title, initial))
        return self.answer

    def cancel(self) -> None:
        """Nothing to cancel."""


class Client:
    """Tiny HTTP client for the test server."""

    def __init__(self, server: AppServer) -> None:
        """Bind to a running server."""
        self.server = server

    def call(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        token: str | None = None,
        host: str | None = None,
    ):
        """Send a request and return ``(status, json)``."""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}{path}", data=data, method=method
        )
        req.add_header("X-Session-Token", self.server.token if token is None else token)
        req.add_header("Content-Type", "application/json")
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req) as res:
                raw = res.read()
                return res.status, (
                    json.loads(raw)
                    if res.headers.get_content_type() == "application/json"
                    else raw
                )
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())


@pytest.fixture
def make_app(tmp_path: Path):
    """Start a server for the given root; stop it after the test."""
    servers = []

    def start(
        root: Path | None, dialog_answer: str | None = None
    ) -> tuple[Client, AppState, StubDialog]:
        """Create state, start serving in a thread and return helpers."""
        dialog = StubDialog(dialog_answer)
        state = AppState(root, tmp_path / "settings" / "settings.json", dialog=dialog)
        server = AppServer(state)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return Client(server), state, dialog

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_rejects_missing_token_and_foreign_host(make_app, computax: Path) -> None:
    """API calls need the token, and the Host must be this server."""
    client, _, _ = make_app(computax)
    assert client.call("GET", "/api/settings", token="wrong")[0] == 401
    assert client.call("GET", "/api/settings", host="evil.example:80")[0] == 403
    assert client.call("GET", "/api/settings")[0] == 200


def test_serves_static_but_not_traversal(make_app, computax: Path) -> None:
    """The page and its assets are served; paths outside static are not."""
    client, _, _ = make_app(computax)
    status, body = client.call("GET", "/")
    assert status == 200 and b"ITR Fetch" in body
    assert client.call("GET", "/static/app.js")[0] == 200
    assert client.call("GET", "/static/../server.py")[0] == 404
    assert client.call("GET", "/static/%2e%2e%2fserver.py")[0] == 404


def test_setup_flow_saves_root(make_app, computax: Path, tmp_path: Path) -> None:
    """Without a root the clients call fails; setting one saves and indexes it."""
    client, state, _ = make_app(None)
    status, settings = client.call("GET", "/api/settings")
    assert status == 200 and settings["root_valid"] is False
    assert client.call("GET", "/api/clients")[0] == 409
    status, check = client.call(
        "POST", "/api/validate-root", {"root": str(computax / "2024")}
    )
    assert status == 200 and not check["ok"]
    assert (
        client.call("PUT", "/api/settings", {"root": str(computax / "2024")})[0] == 400
    )
    status, settings = client.call("PUT", "/api/settings", {"root": str(computax)})
    assert status == 200 and settings["root_valid"]
    saved = json.loads((tmp_path / "settings/settings.json").read_text())
    assert saved == {"computax_root": str(computax)}


def test_invalid_saved_root_is_offered_as_hint(make_app, tmp_path: Path) -> None:
    """A saved path that no longer works pre-fills the setup screen."""
    client, _, _ = make_app(tmp_path / "gone")
    settings = client.call("GET", "/api/settings")[1]
    assert settings["root_valid"] is False and settings["root_hint"] == str(
        tmp_path / "gone"
    )


def test_clients_include_names(make_app, computax: Path) -> None:
    """Once names load, the client list carries names and aliases."""
    client, state, _ = make_app(computax)
    assert state.names_done.wait(5)
    status, data = client.call("GET", "/api/clients")
    assert status == 200 and data["names_ready"]
    by_id = {c["id"]: c for c in data["clients"]}
    assert by_id["1"]["name"] == "ASHA SHARMA" and by_id["1"]["aliases"] == [
        "ASHA VERMA"
    ]
    assert by_id["7D"]["years"] == [2020, 2022, 2023]
    assert by_id["264B"]["name"] is None


def test_client_detail(make_app, computax: Path) -> None:
    """Per-year availability lists the wanted files and warnings."""
    client, _, _ = make_app(computax)
    status, detail = client.call("GET", "/api/clients/264b")
    assert status == 200
    assert (
        detail["years"]["2021"]["itrv"] == []
        and len(detail["years"]["2021"]["warnings"]) == 2
    )
    assert detail["years"]["2022"]["itrv"] == ["ITRV_264B.pdf"]
    assert client.call("GET", "/api/clients/NOPE")[0] == 404


def test_copy_and_open_rules(make_app, computax: Path, tmp_path: Path) -> None:
    """Copy validates input, writes files and only lets copied folders be opened."""
    client, state, _ = make_app(computax)
    assert state.names_done.wait(5)
    dest = tmp_path / "out"
    dest.mkdir()
    assert (
        client.call("POST", "/api/copy", {"id": "1", "years": [], "dest": str(dest)})[0]
        == 400
    )
    assert (
        client.call(
            "POST",
            "/api/copy",
            {"id": "1", "years": [2024], "dest": str(tmp_path / "nope")},
        )[0]
        == 400
    )
    assert (
        client.call(
            "POST", "/api/copy", {"id": "1", "years": [2024], "dest": "relative/path"}
        )[0]
        == 400
    )
    status, report = client.call(
        "POST", "/api/copy", {"id": "1", "years": [2024, 2021], "dest": str(dest)}
    )
    assert status == 200 and report["totals"]["copied"] == 4
    assert report["dest_root"] == str(dest / "ASHA SHARMA")
    assert (dest / "ASHA SHARMA/ITRV_1_2021.pdf").exists()
    assert client.call("POST", "/api/open", {"path": str(tmp_path)})[0] == 400


def test_pick_folder_uses_fixed_titles(make_app, computax: Path) -> None:
    """The dialog gets a fixed title and returns the chosen path."""
    client, _, dialog = make_app(computax, dialog_answer="/Users/me/Downloads")
    status, data = client.call(
        "POST", "/api/pick-folder", {"purpose": "root", "initial": "/x"}
    )
    assert status == 200 and data == {"path": "/Users/me/Downloads"}
    assert dialog.calls == [("Select your CompuTax folder", "/x")]


def test_rescan_picks_up_new_folders(make_app, computax: Path) -> None:
    """Folders copied in after startup appear after a rescan."""
    client, _, _ = make_app(computax)
    (computax / "2025" / "NEW1").mkdir(parents=True)
    ids = [c["id"] for c in client.call("POST", "/api/rescan")[1]["clients"]]
    assert "NEW1" in ids


def test_event_stream_needs_token_and_tracks_open_pages(
    make_app, computax: Path
) -> None:
    """The presence stream rejects bad tokens and counts open pages."""
    import http.client
    import time

    client, _, _ = make_app(computax)
    server = client.server
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/api/events?t=wrong")
    assert conn.getresponse().status == 401
    conn.close()

    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", f"/api/events?t={server.token}")
    res = conn.getresponse()
    assert res.status == 200 and res.getheader("Content-Type") == "text/event-stream"
    assert res.fp.readline().startswith(b"retry:")
    assert server.presence.count == 1
    res.close()
    conn.close()
    for _ in range(50):
        if server.presence.count == 0:
            break
        time.sleep(0.05)
    assert server.presence.count == 0 and server.presence.ever_connected


def test_ping(make_app, computax: Path) -> None:
    """Ping answers with the token, so a second launch can find this instance."""
    client, _, _ = make_app(computax)
    assert client.call("GET", "/api/ping") == (200, {"ok": True})


def test_copy_is_refused_until_names_are_loaded(
    make_app, computax: Path, tmp_path: Path
) -> None:
    """Copying waits for names so the folder is named consistently."""
    client, state, _ = make_app(computax)
    assert state.names_done.wait(5)
    ready = state.names_done
    state.names_done = threading.Event()
    body = {"id": "1", "years": [2024], "dest": str(tmp_path)}
    status, data = client.call("POST", "/api/copy", body)
    assert status == 409 and "loading" in data["error"]
    state.names_done = ready
    assert client.call("POST", "/api/copy", body)[0] == 200
