"""Tests for copying files into ``<dest>/<ID>/<year>/`` and reporting outcomes."""

import os
from pathlib import Path

from computax_client_file_download.copier import copy_client_files
from computax_client_file_download.scanner import build_index


def test_copies_into_id_and_year_folders(computax: Path, tmp_path: Path) -> None:
    """Files land under the client ID and year with original names."""
    dest = tmp_path / "out"
    dest.mkdir()
    client = build_index(computax)["7D"]
    report = copy_client_files(computax, client, [2022, 2020], dest)
    assert report["dest_root"] == str(dest / "7D")
    assert sorted(p.name for p in (dest / "7D/2022").iterdir()) == [
        "Computation_7D_2022_1.pdf",
        "Computation_7D_2022_10.pdf",
        "Computation_7D_2022_2.pdf",
        "ITRV_7D.pdf",
        "ITRV_7D_Revised.pdf",
    ]
    assert (dest / "7D/2020/ITRV_7D.pdf").exists()
    assert report["totals"] == {"copied": 7, "replaced": 0, "skipped": 0, "error": 0}
    assert [y["year"] for y in report["years"]] == [2020, 2022]


def test_second_copy_skips_identical_and_replaces_changed(computax: Path, tmp_path: Path) -> None:
    """Re-running skips identical files and overwrites changed ones."""
    client = build_index(computax)["1"]
    copy_client_files(computax, client, [2024], tmp_path)
    changed = tmp_path / "1/2024/ITRV_1.pdf"
    changed.write_bytes(b"different")
    report = copy_client_files(computax, client, [2024], tmp_path)
    statuses = {i["name"]: i["status"] for i in report["years"][0]["itrv"] + report["years"][0]["computation"]}
    assert statuses == {"ITRV_1.pdf": "replaced", "Computation_1_2024_1.pdf": "skipped"}
    assert changed.read_bytes() == (computax / "2024/1/ITRV_1.pdf").read_bytes()


def test_missing_year_and_empty_year_are_reported(computax: Path, tmp_path: Path) -> None:
    """A year without a folder warns; a year with no PDFs has empty lists."""
    client = build_index(computax)["7D"]
    report = copy_client_files(computax, client, [2023, 2025], tmp_path)
    y2023, y2025 = report["years"]
    assert y2023["itrv"] == [] and y2023["computation"] == []
    assert "No 2025 folder" in y2025["warnings"][0]
    assert not (tmp_path / "7D").exists()


def test_errors_do_not_abort_batch(computax: Path, tmp_path: Path) -> None:
    """A file that can't be written is reported and the rest still copy."""
    client = build_index(computax)["1"]
    blocker = tmp_path / "1/2020"
    blocker.parent.mkdir(parents=True)
    blocker.write_text("a file where a folder should be")
    report = copy_client_files(computax, client, [2020, 2021], tmp_path)
    assert report["totals"]["error"] == 2
    assert report["totals"]["copied"] == 2


def test_symlink_outside_root_is_refused(computax: Path, tmp_path: Path) -> None:
    """A link pointing outside CompuTax is not followed."""
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"secret")
    link = computax / "2024/1/ITRV_1_Revised.pdf"
    try:
        os.symlink(outside, link)
    except OSError:
        return  # symlinks need extra rights on Windows
    client = build_index(computax)["1"]
    report = copy_client_files(computax, client, [2024], tmp_path / "out")
    assert any("outside the CompuTax folder" in w for w in report["years"][0]["warnings"])
    assert not (tmp_path / "out/1/2024/ITRV_1_Revised.pdf").exists()
