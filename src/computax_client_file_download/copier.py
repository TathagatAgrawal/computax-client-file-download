"""Copy a client's ITRV and Computation PDFs into ``<dest>/<ID>/``.

All years go into the one client folder, so the year is appended to any filename
that doesn't already contain it: ``ITRV_1.pdf`` from 2024 becomes
``ITRV_1_2024.pdf``, while ``Computation_1_2024_1.pdf`` keeps its name.

Existing files in the destination are never overwritten; only missing files are
written.
"""

import re
import shutil
from pathlib import Path

from .scanner import Client, resolve_year


def target_name(src_name: str, client_id: str, year: int) -> str:
    """Return the saved filename: ``src_name`` with ``_<year>`` added unless already present.

    The client ID part of the name is ignored when looking for the year, so a
    client whose ID looks like a year still gets the suffix.
    """
    stem, dot, ext = src_name.rpartition(".")
    if not dot:
        stem, ext = src_name, ""
    rest = re.sub(rf"_{re.escape(client_id)}(?=_|$)", "", stem, count=1, flags=re.IGNORECASE)
    if re.search(rf"(^|_){year}(_|$)", rest):
        return src_name
    return f"{stem}_{year}{dot}{ext}"


def _copy_one(src: Path, target_dir: Path, client_id: str, year: int) -> dict:
    """Copy one file unless something already has its name.

    Returns ``{name, source, status[, error]}``. Status is ``copied``, ``exists``
    (a file is already there and was left alone), ``blocked`` (a folder has the
    file's name) or ``error``.
    """
    name = target_name(src.name, client_id, year)
    dst = target_dir / name
    result = {"name": name, "source": src.name}
    if dst.is_dir():
        return {**result, "status": "blocked"}
    if dst.exists():
        return {**result, "status": "exists"}
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {**result, "status": "error", "error": exc.strerror or str(exc)}
    try:
        with src.open("rb") as fsrc, dst.open("xb") as fdst:
            shutil.copyfileobj(fsrc, fdst)
        shutil.copystat(src, dst)
    except FileExistsError:
        return {**result, "status": "exists"}
    except OSError as exc:
        return {**result, "status": "error", "error": exc.strerror or str(exc)}
    return {**result, "status": "copied"}


def _inside(path: Path, root: Path) -> bool:
    """Return True if ``path`` resolves to a location under ``root``."""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def copy_client_files(root: Path, client: Client, years: list[int], dest: Path) -> dict:
    """Copy the selected years' files and return a per-year report.

    Errors on one file are recorded and the rest of the batch continues.
    """
    dest_root = dest / client.id
    report = []
    for year in sorted(set(years)):
        entry = {"year": year, "itrv": [], "computation": [], "warnings": []}
        folder = client.folders.get(year)
        if folder is None:
            entry["warnings"].append(f"No {year} folder for this client.")
            report.append(entry)
            continue
        found = resolve_year(client.id, year, folder)
        entry["warnings"] = found.warnings
        for kind, paths in (("itrv", found.itrv), ("computation", found.computation)):
            for src in paths:
                if _inside(src, root):
                    item = _copy_one(src, dest_root, client.id, year)
                    entry[kind].append(item)
                    if item["status"] == "blocked":
                        entry["warnings"].append(
                            f"{item['name']} was not saved because a folder with that name is already in {dest_root}."
                        )
                else:
                    entry["warnings"].append(f"{src.name} points outside the CompuTax folder; not copied.")
        report.append(entry)
    counts = {"copied": 0, "exists": 0, "blocked": 0, "error": 0}
    for entry in report:
        for item in entry["itrv"] + entry["computation"]:
            counts[item["status"]] += 1
    return {"dest_root": str(dest_root), "years": report, "totals": counts}
