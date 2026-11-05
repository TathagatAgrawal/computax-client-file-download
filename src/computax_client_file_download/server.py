"""Local HTTP server: serves the UI and a small JSON API on 127.0.0.1 only.

Every ``/api/`` request must carry the per-launch session token, and the Host
header must name this server, so other web pages open in the browser cannot
drive the app (including via DNS rebinding).

Each open page keeps a server-sent-events connection to ``/api/events``. When
the last one closes (tab or browser closed), the app quits after a short grace
period that lets a page reload reconnect.
"""

import hmac
import json
import secrets
import select
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .copier import copy_client_files
from .dialogs import DialogBusy, DialogUnavailable, FolderDialog, default_destination, open_in_file_manager
from .names import load_names
from .scanner import Client, build_index, check_root, resolve_year, sorted_clients
from .settings import save_root

STATIC_DIR = Path(__file__).parent / "static"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}
DIALOG_TITLES = {
    "dest": "Choose where to save the files",
    "root": "Select your CompuTax folder",
}
MAX_BODY = 1_000_000
KEEPALIVE_SECONDS = 15


class ApiError(Exception):
    """An error returned to the browser as ``{"error": message}`` with a status code."""

    def __init__(self, status: int, message: str) -> None:
        """Store the HTTP status and the user-facing message."""
        super().__init__(message)
        self.status = status
        self.message = message


class AppState:
    """Everything the server knows: the CompuTax folder, the client index and UI liveness."""

    def __init__(self, root: Path | None, settings_file: Path, dialog: FolderDialog | None = None) -> None:
        """Create the state and index ``root`` if it is a valid CompuTax folder."""
        self.lock = threading.RLock()
        self.settings_file = settings_file
        self.dialog = dialog or FolderDialog()
        self.root: Path | None = None
        self.index: dict[str, Client] = {}
        self.names_done = threading.Event()
        self.copied_dirs: set[str] = set()
        self._generation = 0
        self.root_hint = str(root) if root is not None else None
        if root is not None and check_root(root).ok:
            self.set_root(root, save=False)

    def set_root(self, root: Path, save: bool) -> None:
        """Switch to ``root``, rebuild the index and start loading names in the background."""
        index = build_index(root)
        with self.lock:
            self._generation += 1
            generation = self._generation
            self.root = root
            self.index = index
            self.names_done = threading.Event()
            done = self.names_done
        if save:
            save_root(self.settings_file, str(root))
        clients = list(index.values())
        threading.Thread(target=self._load_names, args=(generation, clients, done), daemon=True).start()

    def _load_names(self, generation: int, clients: list[Client], done: threading.Event) -> None:
        """Read client names and attach them, unless a newer scan has started meanwhile."""
        try:
            names = load_names(clients)
            with self.lock:
                if generation != self._generation:
                    return
                for key, (name, aliases) in names.items():
                    client = self.index.get(key)
                    if client:
                        client.name, client.aliases = name, aliases
        finally:
            done.set()

    def rescan(self) -> None:
        """Rebuild the index from the current CompuTax folder."""
        if self.root is not None:
            self.set_root(self.root, save=False)

    def client(self, client_id: str) -> Client:
        """Return the client with this ID (any case) or raise a 404."""
        with self.lock:
            client = self.index.get(client_id.upper())
        if client is None:
            raise ApiError(404, f"Unknown client ID: {client_id}")
        return client

    def clients_payload(self) -> dict:
        """Return the client list as sent to the browser."""
        with self.lock:
            if self.root is None:
                raise ApiError(409, "The CompuTax folder has not been set.")
            return {
                "names_ready": self.names_done.is_set(),
                "clients": [c.to_json() for c in sorted_clients(self.index)],
            }


class AppServer(ThreadingHTTPServer):
    """HTTP server that carries the app state and session token."""

    daemon_threads = True

    def __init__(self, state: AppState, port: int = 0, token: str | None = None) -> None:
        """Bind to 127.0.0.1 on ``port`` (0 picks a free port)."""
        super().__init__(("127.0.0.1", port), Handler)
        self.state = state
        self.token = token or secrets.token_urlsafe(24)
        self.presence = Presence()

    @property
    def port(self) -> int:
        """Return the port the server is listening on."""
        return self.server_address[1]

    @property
    def url(self) -> str:
        """Return the URL that opens the app with its session token."""
        return f"http://127.0.0.1:{self.port}/?t={self.token}"


class Handler(BaseHTTPRequestHandler):
    """Routes requests to static files or API handlers."""

    server: AppServer

    def log_message(self, format: str, *args) -> None:
        """Stay quiet: request logs would only clutter the console window."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        self._dispatch("GET")

    def do_POST(self) -> None:
        """Handle POST requests."""
        self._dispatch("POST")

    def do_PUT(self) -> None:
        """Handle PUT requests."""
        self._dispatch("PUT")

    def _dispatch(self, method: str) -> None:
        """Check the Host header, then serve a static file or an API route."""
        if not self._host_ok():
            self._send_json(403, {"error": "Forbidden host."})
            return
        url = urlsplit(self.path)
        path = url.path
        try:
            if method == "GET" and path == "/api/events":
                self._check_token(parse_qs(url.query).get("t", [""])[0])
                self._events()
            elif method == "GET" and path in ("/", "/index.html"):
                self._send_static("index.html")
            elif method == "GET" and path.startswith("/static/"):
                self._send_static(path.removeprefix("/static/"))
            elif path.startswith("/api/"):
                self._check_token()
                self._send_json(200, self._api(method, path))
            else:
                raise ApiError(404, "Not found.")
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.message})

    def _host_ok(self) -> bool:
        """Return True if the Host header names this server."""
        port = self.server.port
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _check_token(self, given: str | None = None) -> None:
        """Reject API requests without the session token (header, or ``given`` for event streams)."""
        if given is None:
            given = self.headers.get("X-Session-Token", "")
        if not hmac.compare_digest(given.encode(), self.server.token.encode()):
            raise ApiError(401, "This page is from an earlier run of the app. Open the app again.")

    def _events(self) -> None:
        """Hold a server-sent-events stream open for as long as the page is open."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        presence = self.server.presence
        presence.opened()
        try:
            self.wfile.write(b"retry: 1000\ndata: hello\n\n")
            self.wfile.flush()
            sock = self.connection
            while True:
                readable, _, _ = select.select([sock], [], [], KEEPALIVE_SECONDS)
                if readable and not sock.recv(1024):
                    break  # the browser closed the connection
                if not readable:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except OSError:
            pass
        finally:
            presence.closed()
            self.close_connection = True

    def _body(self) -> dict:
        """Parse the JSON request body."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(413, "Request too large.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise ApiError(400, "Request body is not valid JSON.") from None
        if not isinstance(data, dict):
            raise ApiError(400, "Request body must be a JSON object.")
        return data

    def _send_json(self, status: int, payload: dict) -> None:
        """Write a JSON response."""
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, name: str) -> None:
        """Serve a file from the static folder; names with path separators are refused."""
        path = STATIC_DIR / name
        if "/" in name or "\\" in name or name.startswith(".") or not path.is_file():
            raise ApiError(404, "Not found.")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _api(self, method: str, path: str) -> dict:
        """Run the API route for ``method`` and ``path`` and return its JSON payload."""
        state = self.server.state
        route = (method, path)
        if route == ("GET", "/api/settings"):
            return self._settings_payload()
        if route == ("POST", "/api/validate-root"):
            return self._root_check(self._body())
        if route == ("PUT", "/api/settings"):
            check = self._root_check(self._body())
            if not check["ok"]:
                raise ApiError(400, check["message"])
            state.set_root(Path(check["root"]), save=True)
            return self._settings_payload()
        if route == ("GET", "/api/clients"):
            return state.clients_payload()
        if route == ("POST", "/api/rescan"):
            state.rescan()
            return state.clients_payload()
        if method == "GET" and path.startswith("/api/clients/"):
            return self._client_detail(unquote(path.removeprefix("/api/clients/")))
        if route == ("POST", "/api/pick-folder"):
            return self._pick_folder(self._body())
        if route == ("POST", "/api/pick-folder/cancel"):
            state.dialog.cancel()
            return {"ok": True}
        if route == ("POST", "/api/copy"):
            return self._copy(self._body())
        if route == ("POST", "/api/open"):
            return self._open(self._body())
        if route == ("GET", "/api/ping"):
            return {"ok": True}
        if route == ("POST", "/api/quit"):
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {"ok": True}
        raise ApiError(404, "Unknown API route.")

    def _settings_payload(self) -> dict:
        """Return the current CompuTax folder and the default destination."""
        root = self.server.state.root
        return {
            "root": str(root) if root else None,
            "root_valid": root is not None,
            "root_hint": str(root) if root else self.server.state.root_hint,
            "default_dest": default_destination(),
        }

    def _root_check(self, body: dict) -> dict:
        """Validate the ``root`` path given in ``body``."""
        raw = body.get("root")
        if not isinstance(raw, str) or not raw.strip():
            return {"ok": False, "message": "Enter or choose a folder.", "root": None}
        root = Path(raw.strip()).expanduser()
        check = check_root(root)
        return {
            "ok": check.ok,
            "message": check.message,
            "root": str(root),
            "years": check.years,
            "client_count": check.client_count,
        }

    def _client_detail(self, client_id: str) -> dict:
        """Return, for each year, which wanted files exist for this client."""
        client = self.server.state.client(client_id)
        years = {}
        for year, folder in sorted(client.folders.items()):
            found = resolve_year(client.id, year, folder)
            years[str(year)] = {
                "itrv": [p.name for p in found.itrv],
                "computation": [p.name for p in found.computation],
                "warnings": found.warnings,
            }
        return {"id": client.id, "name": client.name, "years": years}

    def _pick_folder(self, body: dict) -> dict:
        """Show the native folder dialog and return the chosen path (or null)."""
        state = self.server.state
        title = DIALOG_TITLES.get(body.get("purpose"), DIALOG_TITLES["dest"])
        initial = body.get("initial") if isinstance(body.get("initial"), str) else ""
        try:
            path = state.dialog.pick(title, initial)
        except DialogBusy as exc:
            raise ApiError(409, str(exc)) from None
        except DialogUnavailable as exc:
            raise ApiError(501, str(exc)) from None
        except RuntimeError as exc:
            raise ApiError(500, str(exc)) from None
        return {"path": path}

    def _copy(self, body: dict) -> dict:
        """Copy the requested client's files and return the per-year report."""
        state = self.server.state
        client_id, years, dest = body.get("id"), body.get("years"), body.get("dest")
        if not isinstance(client_id, str):
            raise ApiError(400, "Choose a client.")
        if not isinstance(years, list) or not years or not all(isinstance(y, int) for y in years):
            raise ApiError(400, "Choose at least one year.")
        if not isinstance(dest, str) or not dest.strip():
            raise ApiError(400, "Choose where to save the files.")
        dest_path = Path(dest.strip()).expanduser()
        if not dest_path.is_absolute() or not dest_path.is_dir():
            raise ApiError(400, f"The destination folder does not exist: {dest}")
        client = state.client(client_id)
        if state.root is None:
            raise ApiError(409, "The CompuTax folder has not been set.")
        report = copy_client_files(state.root, client, years, dest_path)
        with state.lock:
            state.copied_dirs.add(report["dest_root"])
        report["id"], report["name"] = client.id, client.name
        return report

    def _open(self, body: dict) -> dict:
        """Open a folder that this session copied files into."""
        path = body.get("path")
        if path not in self.server.state.copied_dirs or not Path(path).is_dir():
            raise ApiError(400, "That folder can't be opened.")
        open_in_file_manager(path)
        return {"ok": True}


class Presence:
    """Counts open pages (event streams) and when the count last reached zero."""

    def __init__(self) -> None:
        """Start with no pages connected."""
        self._lock = threading.Lock()
        self.count = 0
        self.ever_connected = False
        self.started = time.monotonic()
        self.empty_since = self.started

    def opened(self) -> None:
        """Record a page connecting."""
        with self._lock:
            self.count += 1
            self.ever_connected = True

    def closed(self) -> None:
        """Record a page disconnecting."""
        with self._lock:
            self.count -= 1
            if self.count == 0:
                self.empty_since = time.monotonic()

    def should_exit(self, grace: float, startup: float) -> bool:
        """Return True if no page is open and the grace (or startup) period has passed."""
        with self._lock:
            if self.count:
                return False
            limit = grace if self.ever_connected else startup
            return time.monotonic() - self.empty_since > limit


def start_auto_exit(server: AppServer, grace: float = 4.0, startup: float = 90.0) -> threading.Thread:
    """Stop the server once no page has been open for ``grace`` seconds.

    If no page ever connects (for example, the browser failed to open), the
    server stops after ``startup`` seconds. It never stops while a folder dialog
    is open.
    """

    def watch() -> None:
        """Poll the open-page count and shut the server down when it stays at zero."""
        while True:
            time.sleep(0.5)
            if not server.state.dialog.is_open and server.presence.should_exit(grace, startup):
                server.shutdown()
                return

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return thread
