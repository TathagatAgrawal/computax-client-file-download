"""Read client names from the ``FiledJson_<id>_<n>.json`` ITR files.

The name lives in an ``AssesseeName`` object whose location depends on the ITR
form (ITR-1 to ITR-6), so the JSON is searched rather than addressed by path.
"""

import json
import re
from pathlib import Path

from .scanner import Client

FILEDJSON_RE = re.compile(r"FiledJson_(.+)_(\d+)\.json", re.IGNORECASE)
NAME_PARTS = ("FirstName", "MiddleName", "SurNameOrOrgName")


def find_assessee_name(data: object) -> dict | None:
    """Return the first ``AssesseeName`` object found anywhere in ``data``."""
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            found = node.get("AssesseeName")
            if isinstance(found, dict):
                return found
            stack.extend(reversed(list(node.values())))
        elif isinstance(node, list):
            stack.extend(reversed(node))
    return None


def format_name(assessee: dict) -> str | None:
    """Join the name parts into one string, or None if all parts are empty."""
    parts = [str(assessee.get(k) or "").strip() for k in NAME_PARTS]
    name = " ".join(" ".join(p for p in parts if p).split())
    return name or None


def read_name(path: Path) -> str | None:
    """Return the assessee name from one FiledJson file, or None if unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    assessee = find_assessee_name(data)
    return format_name(assessee) if assessee else None


def _filed_jsons(client_id: str, folder: Path) -> list[Path]:
    """Return this client's FiledJson files in ``folder``, highest number first."""
    try:
        names = [p.name for p in folder.iterdir()]
    except OSError:
        return []
    matches = []
    for name in names:
        m = FILEDJSON_RE.fullmatch(name)
        if m and m.group(1).upper() == client_id.upper():
            matches.append((int(m.group(2)), folder / name))
    return [p for _, p in sorted(matches, reverse=True)]


def client_names(client: Client) -> tuple[str | None, list[str]]:
    """Return the client's latest name and any distinct older names.

    Each year contributes the name from its highest-numbered FiledJson that can
    be read. Older names become search aliases.
    """
    names: list[str] = []
    for year in sorted(client.folders, reverse=True):
        for path in _filed_jsons(client.id, client.folders[year]):
            name = read_name(path)
            if name:
                if name.upper() not in (n.upper() for n in names):
                    names.append(name)
                break
    return (names[0], names[1:]) if names else (None, [])


def load_names(clients: list[Client]) -> dict[str, tuple[str | None, list[str]]]:
    """Return ``{ID_UPPER: (name, aliases)}`` for every client given."""
    return {c.id.upper(): client_names(c) for c in clients}
