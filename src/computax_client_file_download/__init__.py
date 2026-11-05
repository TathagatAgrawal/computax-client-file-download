"""CompuTax client file downloader: a local web app for copying ITR-V and Computation PDFs."""

import argparse
import webbrowser
from pathlib import Path

from .dialogs import run_tk_picker
from .server import AppServer, AppState, start_watchdog
from .settings import default_settings_file, load_root


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        prog="computax-client-file-download",
        description="Copy a client's ITRV and Computation PDFs out of the CompuTax folder.",
    )
    parser.add_argument("--root", help="CompuTax folder to use for this run (overrides the saved one)")
    parser.add_argument("--port", type=int, default=0, help="port to listen on (default: any free port)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    parser.add_argument("--pick-folder", nargs=2, metavar=("TITLE", "INITIAL"), help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Start the local server and open the app in the default browser."""
    args = _parse_args(argv)
    if args.pick_folder:
        run_tk_picker(*args.pick_folder)
        return
    settings_file = default_settings_file()
    root = args.root or load_root(settings_file)
    state = AppState(Path(root).expanduser() if root else None, settings_file)
    server = AppServer(state, args.port)
    print("CompuTax file downloader is running.")
    print(f"Open this address if the browser didn't open: {server.url}")
    print("Close this window (or press Ctrl+C) to quit.", flush=True)
    start_watchdog(server)
    if not args.no_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("Stopped.")
