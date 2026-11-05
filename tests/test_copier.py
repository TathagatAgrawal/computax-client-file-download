"""Tests for copying files into ``<dest>/<ID>/`` and reporting outcomes."""

import os
from pathlib import Path

from computax_client_file_download.copier import copy_client_files, target_name
from computax_client_file_download.scanner import build_index


def test_copies_flat_into_id_folder_with_year_suffix(computax: Path, tmp_path: Path) -> None:
    """All years land in one client folder; the year is added only where missing."""
    dest = tmp_path / "out"
    dest.mkdir()
    client = build_index(computax)["7D"]
    report = copy_client_files(computax, client, [2022, 2020], dest)
    assert report["dest_root"] == str(dest / "7D")
    assert sorted(p.name for p in (dest / "7D").iterdir()) == [
        "Computation_7D_2020_1.pdf",
        "Computation_7D_2022_1.pdf",
        "Computation_7D_2022_10.pdf",
        "Computation_7D_2022_2.pdf",
        "ITRV_7D_2020.pdf",
        "ITRV_7D_2022.pdf",
        "ITRV_7D_Revised_2022.pdf",
    ]
    assert report["totals"] == {"copied": 7, "exists": 0, "blocked": 0, "error": 0}
    assert [y["year"] for y in report["years"]] == [2020, 2022]
    assert report["years"][0]["itrv"][0] == {"name": "ITRV_7D_2020.pdf", "source": "ITRV_7D.pdf", "status": "copied"}


def test_target_name_rules() -> None:
    """The year is appended unless already present outside the client ID."""
    assert target_name("ITRV_1.pdf", "1", 2024) == "ITRV_1_2024.pdf"
    assert target_name("ITRV_1_Revised.pdf", "1", 2024) == "ITRV_1_Revised_2024.pdf"
    assert target_name("Computation_1_2024_2.pdf", "1", 2024) == "Computation_1_2024_2.pdf"
    assert target_name("ITRV_2024.pdf", "2024", 2024) == "ITRV_2024_2024.pdf"
    assert target_name("Computation_2024_2024_1.pdf", "2024", 2024) == "Computation_2024_2024_1.pdf"
    assert target_name("itrv_7d.pdf", "7D", 2020) == "itrv_7d_2020.pdf"


def test_existing_files_are_never_overwritten(computax: Path, tmp_path: Path) -> None:
    """Re-running writes only missing files and leaves existing ones untouched."""
    client = build_index(computax)["1"]
    copy_client_files(computax, client, [2024], tmp_path)
    edited = tmp_path / "1/ITRV_1_2024.pdf"
    edited.write_bytes(b"user's own edit")
    (tmp_path / "1/Computation_1_2024_1.pdf").unlink()
    report = copy_client_files(computax, client, [2024], tmp_path)
    statuses = {i["name"]: i["status"] for i in report["years"][0]["itrv"] + report["years"][0]["computation"]}
    assert statuses == {"ITRV_1_2024.pdf": "exists", "Computation_1_2024_1.pdf": "copied"}
    assert edited.read_bytes() == b"user's own edit"
    assert report["totals"] == {"copied": 1, "exists": 1, "blocked": 0, "error": 0}


def test_missing_year_and_empty_year_are_reported(computax: Path, tmp_path: Path) -> None:
    """A year without a folder warns; a year with no PDFs has empty lists."""
    client = build_index(computax)["7D"]
    report = copy_client_files(computax, client, [2023, 2025], tmp_path)
    y2023, y2025 = report["years"]
    assert y2023["itrv"] == [] and y2023["computation"] == []
    assert "No 2025 folder" in y2025["warnings"][0]
    assert not (tmp_path / "7D").exists()


def test_folder_in_the_way_is_a_warning(computax: Path, tmp_path: Path) -> None:
    """A folder with a file's name blocks only that file, with a warning; the rest copy."""
    client = build_index(computax)["1"]
    (tmp_path / "1/ITRV_1_2020.pdf").mkdir(parents=True)
    report = copy_client_files(computax, client, [2020, 2021], tmp_path)
    assert report["totals"] == {"copied": 3, "exists": 0, "blocked": 1, "error": 0}
    assert any("ITRV_1_2020.pdf was not saved" in w for w in report["years"][0]["warnings"])
    assert (tmp_path / "1/ITRV_1_2020.pdf").is_dir()


def test_write_errors_do_not_abort_batch(computax: Path, tmp_path: Path) -> None:
    """A real write failure is an error for that year, and other years still copy."""
    client = build_index(computax)["1"]
    blocker = tmp_path / "1"
    blocker.write_text("a file where the client folder should be")
    report = copy_client_files(computax, client, [2020], tmp_path)
    assert report["totals"]["error"] == 2
    assert report["years"][0]["itrv"][0]["error"]


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
    assert not (tmp_path / "out/1/ITRV_1_Revised_2024.pdf").exists()
