"""Open the operating system's native folder dialog and file manager.

Browsers never reveal real folder paths, so the local server opens the dialog
itself. macOS uses ``osascript`` (built in). Windows re-launches this program
with ``--pick-folder`` so Tk runs in its own process, away from the server's
threads; the child writes its answer to a temporary file because a windowless
app has no usable stdout. Linux is only for development and uses ``zenity`` when available.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

MAC_SCRIPT = [
    "on run argv",
    "set promptText to item 1 of argv",
    "set startPath to item 2 of argv",
    "activate",
    'if startPath is "" then',
    "set chosen to choose folder with prompt promptText",
    "else",
    "set chosen to choose folder with prompt promptText default location (POSIX file startPath)",
    "end if",
    "return POSIX path of chosen",
    "end run",
]


class DialogBusy(Exception):
    """Raised when a folder dialog is already open."""


class DialogUnavailable(Exception):
    """Raised when this platform has no way to show a native folder dialog."""


def _self_command() -> list[str]:
    """Return the command that re-launches this program."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "computax_client_file_download"]


def _command(title: str, initial: str, answer_file: str) -> list[str]:
    """Build the command that shows a folder dialog on this platform."""
    if sys.platform == "darwin":
        script = [arg for line in MAC_SCRIPT for arg in ("-e", line)]
        return ["osascript", *script, title, initial]
    if sys.platform == "win32":
        return [*_self_command(), "--pick-folder", title, initial, answer_file]
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--directory", f"--title={title}"]
        return cmd + ([f"--filename={initial}/"] if initial else [])
    raise DialogUnavailable("No folder dialog is available on this system. Type the path instead.")


def _parse(returncode: int, out: str, err: str, answer: str) -> str | None:
    """Turn the dialog process's output into a chosen path, or None if cancelled."""
    out = out.strip()
    if sys.platform == "win32":
        try:
            path = json.loads(answer).get("path") if answer else None
        except ValueError:
            path = None
        return os.path.normpath(path) if path else None
    if returncode != 0:
        if returncode < 0 or "-128" in err or sys.platform != "darwin":
            return None
        raise RuntimeError(err.strip() or "The folder dialog failed.")
    if not out:
        return None
    return out.rstrip("/") or "/"


class FolderDialog:
    """Shows one native folder dialog at a time and allows cancelling it."""

    def __init__(self) -> None:
        """Create an idle dialog controller."""
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    @property
    def is_open(self) -> bool:
        """Return True while a dialog is being shown."""
        return self._lock.locked()

    def pick(self, title: str, initial: str = "") -> str | None:
        """Show the dialog and block until the user picks a folder or cancels."""
        if not self._lock.acquire(blocking=False):
            raise DialogBusy("A folder dialog is already open.")
        try:
            if initial and not Path(initial).is_dir():
                initial = ""
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            with tempfile.TemporaryDirectory() as tmp:
                answer_file = Path(tmp) / "answer.json"
                self._proc = subprocess.Popen(
                    _command(title, initial, str(answer_file)),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=flags,
                )
                out, err = self._proc.communicate()
                answer = answer_file.read_text(encoding="utf-8") if answer_file.exists() else ""
            return _parse(self._proc.returncode, out, err, answer)
        finally:
            self._proc = None
            self._lock.release()

    def cancel(self) -> None:
        """Close the open dialog, if any, as though the user cancelled it."""
        proc = self._proc
        if proc and proc.poll() is None:
            proc.kill()


def run_tk_picker(title: str, initial: str, answer_file: str) -> None:
    """Show a Tk folder dialog and write ``{"path": ...}`` to ``answer_file`` (Windows child process)."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    path = filedialog.askdirectory(parent=root, title=title, initialdir=initial or None, mustexist=True)
    root.destroy()
    Path(answer_file).write_text(json.dumps({"path": path or None}), encoding="utf-8")


def default_destination() -> str:
    """Return the user's Downloads folder, or their home folder if it is missing."""
    downloads = Path.home() / "Downloads"
    return str(downloads if downloads.is_dir() else Path.home())


def open_in_file_manager(path: str) -> None:
    """Open ``path`` in Finder, Explorer or the Linux file manager."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
