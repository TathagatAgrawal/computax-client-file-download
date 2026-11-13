"""ITR Fetch: a local web app that copies ITR-V and Computation PDFs out of CompuTax."""

import argparse
import json
import sys
import traceback
import urllib.request
import webbrowser
from pathlib import Path

from .dialogs import run_tk_picker
from .server import AppServer, AppState, start_auto_exit
from .settings import (
    clear_instance,
    config_dir,
    default_settings_file,
    instance_file,
    load_root,
    read_instance,
    write_instance,
)

APP_NAME = "ITR Fetch"
__version__ = "0.1.3"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        prog="itr-fetch",
        description=(
            f"{APP_NAME}: copy a client's ITRV and Computation PDFs "
            "out of the CompuTax folder."
        ),
    )
    parser.add_argument(
        "--root", help="CompuTax folder to use for this run (overrides the saved one)"
    )
    parser.add_argument(
        "--port", type=int, default=0, help="port to listen on (default: any free port)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help=(
            "don't open the browser, and keep running when no page is open "
            "(for development)"
        ),
    )
    parser.add_argument(
        "--pick-folder",
        nargs=3,
        metavar=("TITLE", "INITIAL", "ANSWER_FILE"),
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def _running_instance_url() -> str | None:
    """Return the URL of an already running instance, or None if there isn't one."""
    record = read_instance(instance_file())
    if not record:
        return None
    base = record["url"].split("/?", 1)[0]
    req = urllib.request.Request(
        f"{base}/api/ping", headers={"X-Session-Token": record["token"]}
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as res:
            if json.loads(res.read()).get("ok"):
                return record["url"]
    except (OSError, ValueError):
        pass
    return None


def _log_crash() -> None:
    """Write the current exception to error.log (a windowless app has no console)."""
    try:
        log = config_dir() / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        pass


def _run(args: argparse.Namespace) -> None:
    """Start the server (or reuse a running one) and open the app in the browser."""
    if not args.no_browser and (url := _running_instance_url()):
        webbrowser.open(url)
        return
    settings_file = default_settings_file()
    root = args.root or load_root(settings_file)
    state = AppState(Path(root).expanduser() if root else None, settings_file)
    try:
        server = AppServer(state, args.port)
    except OSError as exc:
        raise SystemExit(
            f"{APP_NAME} could not listen on port {args.port}: "
            f"{exc.strerror or exc}. Another program (or another copy of "
            "this app) may be using it; pick a different --port, or omit it "
            "to use any free port."
        ) from exc
    record = instance_file()
    write_instance(record, server.url, server.token)
    print(f"{APP_NAME} is running at {server.url}", flush=True)
    if args.no_browser:
        print("Press Ctrl+C to stop.", flush=True)
    else:
        start_auto_exit(server)
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        clear_instance(record, server.token)


def main(argv: list[str] | None = None) -> None:
    """Entry point: run the folder-dialog helper or the app itself."""
    args = _parse_args(argv)
    if args.pick_folder:
        run_tk_picker(*args.pick_folder)
        return
    try:
        _run(args)
    except Exception:
        _log_crash()
        if sys.stderr:
            traceback.print_exc()
        sys.exit(1)
