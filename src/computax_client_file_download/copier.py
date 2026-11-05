"""Copy a client's ITRV and Computation PDFs into ``<dest>/<ID>/<year>/``."""

import shutil
from pathlib import Path

from .scanner import Client, resolve_year


def _same_file(src: Path, dst: Path) -> bool:
    """Return True if ``dst`` already holds an identical copy of ``src``."""
    try:
        a, b = src.stat(), dst.stat()
    except OSError:
        return False
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def _copy_one(src: Path, target_dir: Path) -> dict:
    """Copy one file and return ``{name, status[, error]}`` describing the outcome."""
    dst = target_dir / src.name
    if _same_file(src, dst):
        return {"name": src.name, "status": "skipped"}
    existed = dst.exists()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except OSError as exc:
        return {"name": src.name, "status": "error", "error": exc.strerror or str(exc)}
    return {"name": src.name, "status": "replaced" if existed else "copied"}


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
                    entry[kind].append(_copy_one(src, dest_root / str(year)))
                else:
                    entry["warnings"].append(f"{src.name} points outside the CompuTax folder; not copied.")
        report.append(entry)
    counts = {"copied": 0, "replaced": 0, "skipped": 0, "error": 0}
    for entry in report:
        for item in entry["itrv"] + entry["computation"]:
            counts[item["status"]] += 1
    return {"dest_root": str(dest_root), "years": report, "totals": counts}
