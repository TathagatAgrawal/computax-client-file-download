"""Index the CompuTax folder and resolve the ITRV/Computation files for a client-year.

The CompuTax layout is ``<root>/<year>/<client_id>/<files>``. Client IDs are
matched case-insensitively because the same client is spelled ``7d`` in one
year and ``7D`` in another.
"""

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

YEAR_RE = re.compile(r"\d{4}")
ANY_ITRV_RE = re.compile(r"ITRV_(.+?)(_Revised)?\.pdf", re.IGNORECASE)
ANY_COMPUTATION_RE = re.compile(r"Computation_(.+)_(\d{4})_(\d+)\.pdf", re.IGNORECASE)


@dataclass
class Client:
    """One client across all years, keyed in the index by its upper-cased ID."""

    id: str
    folders: dict[int, Path] = field(default_factory=dict)
    name: str | None = None
    aliases: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        """Return the client's summary as sent to the browser."""
        return {
            "id": self.id,
            "name": self.name,
            "aliases": self.aliases,
            "years": sorted(self.folders),
        }


@dataclass
class YearFiles:
    """The wanted files found in one client-year folder, plus any warnings."""

    itrv: list[Path] = field(default_factory=list)
    computation: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RootCheck:
    """Result of validating a candidate CompuTax folder."""

    ok: bool
    message: str
    years: list[int] = field(default_factory=list)
    client_count: int = 0


def natural_key(text: str) -> list[tuple]:
    """Sort key that orders embedded numbers numerically (1, 2, 10, 103A)."""
    parts = re.split(r"(\d+)", text)
    return [(0, int(p), "") if p.isdigit() else (1, 0, p.upper()) for p in parts if p]


def _subdirs(path: Path) -> list[os.DirEntry]:
    """List visible subdirectories of ``path``, or nothing if it can't be read."""
    try:
        with os.scandir(path) as it:
            return [e for e in it if not e.name.startswith(".") and e.is_dir()]
    except OSError:
        return []


def year_dirs(root: Path) -> dict[int, Path]:
    """Return the four-digit year folders directly under ``root``."""
    return {
        int(e.name): Path(e.path)
        for e in _subdirs(root)
        if YEAR_RE.fullmatch(e.name)
    }


def build_index(root: Path) -> dict[str, Client]:
    """Scan ``root`` and return clients keyed by upper-cased ID.

    Only folder names are listed, so this is fast even on network drives. The
    displayed ID is the most common spelling, with ties going to the latest year.
    """
    folders: dict[str, dict[int, Path]] = {}
    spellings: dict[str, Counter] = {}
    last_seen: dict[str, dict[str, int]] = {}
    for year, ydir in sorted(year_dirs(root).items()):
        for entry in sorted(_subdirs(ydir), key=lambda e: e.name):
            key = entry.name.upper()
            folders.setdefault(key, {}).setdefault(year, Path(entry.path))
            spellings.setdefault(key, Counter())[entry.name] += 1
            last_seen.setdefault(key, {})[entry.name] = year
    index = {}
    for key, by_year in folders.items():
        display = max(spellings[key], key=lambda s: (spellings[key][s], last_seen[key][s]))
        index[key] = Client(id=display, folders=by_year)
    return index


def sorted_clients(index: dict[str, Client]) -> list[Client]:
    """Return the index's clients in natural ID order."""
    return sorted(index.values(), key=lambda c: natural_key(c.id))


def check_root(root: Path) -> RootCheck:
    """Validate that ``root`` looks like a CompuTax folder and explain if not."""
    if not root.is_dir():
        return RootCheck(False, "This folder does not exist.")
    years = year_dirs(root)
    if not years:
        if YEAR_RE.fullmatch(root.name):
            return RootCheck(False, f"This looks like a single year folder ({root.name}). Pick the folder that contains it.")
        for child in _subdirs(root):
            if child.name.lower() == "computax" and year_dirs(Path(child.path)):
                return RootCheck(False, f"This folder has no year folders, but {child.path} does. Pick that one.")
        return RootCheck(False, "This folder has no year folders (2019, 2020, ...).")
    index = build_index(root)
    if not index:
        return RootCheck(False, "The year folders contain no client folders.")
    found = sorted(years)
    return RootCheck(
        True,
        f"Found {len(found)} year folders ({found[0]}–{found[-1]}) and {len(index)} clients.",
        found,
        len(index),
    )


def _list_files(folder: Path) -> list[str]:
    """Return the names of regular files in ``folder``, or nothing if unreadable."""
    try:
        with os.scandir(folder) as it:
            return [e.name for e in it if e.is_file()]
    except OSError:
        return []


def resolve_year(client_id: str, year: int, folder: Path) -> YearFiles:
    """Find the ITRV and Computation PDFs for ``client_id`` in one year folder.

    The client ID in each filename must match ``client_id`` case-insensitively.
    Files belonging to a different ID are reported as warnings, never returned.
    """
    cid = re.escape(client_id)
    itrv_re = re.compile(rf"ITRV_{cid}(_Revised)?\.pdf", re.IGNORECASE)
    comp_re = re.compile(rf"Computation_{cid}_{year}_(\d+)\.pdf", re.IGNORECASE)
    result = YearFiles()
    foreign = []
    for name in sorted(_list_files(folder)):
        if itrv_re.fullmatch(name):
            result.itrv.append(folder / name)
        elif comp_re.fullmatch(name):
            result.computation.append(folder / name)
        elif m := ANY_ITRV_RE.fullmatch(name):
            if m.group(1).upper() != client_id.upper():
                foreign.append(f"{name} belongs to a different client ID ({m.group(1)}); not copied.")
        elif m := ANY_COMPUTATION_RE.fullmatch(name):
            if m.group(1).upper() != client_id.upper():
                foreign.append(f"{name} belongs to a different client ID ({m.group(1)}); not copied.")
            else:
                foreign.append(f"{name} is for year {m.group(2)}, not {year}; not copied.")
    result.itrv.sort(key=lambda p: ("_revised" in p.name.lower(), p.name))
    result.computation.sort(key=lambda p: int(comp_re.fullmatch(p.name).group(1)))
    result.warnings = foreign
    return result
