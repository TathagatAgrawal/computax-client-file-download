"""Tests for indexing the CompuTax folder and resolving files per client-year."""

from pathlib import Path

from computax_client_file_download.scanner import (
    build_index,
    check_root,
    natural_key,
    resolve_year,
    sorted_clients,
)


def test_index_merges_ids_case_insensitively(computax: Path) -> None:
    """``7d`` and ``7D`` are one client, shown with the more common spelling."""
    index = build_index(computax)
    assert index["7D"].id == "7D"
    assert sorted(index["7D"].folders) == [2020, 2022, 2023]


def test_index_ignores_non_year_folders_and_files(computax: Path) -> None:
    """Only four-digit year folders are scanned."""
    index = build_index(computax)
    assert set(index) == {"1", "7D", "42", "264B", "99", "EMPTY"}


def test_natural_sort_orders_numbers_numerically() -> None:
    """IDs sort as 1, 2, 10, 103A, 103B, NEHA4."""
    ids = ["103B", "10", "NEHA4", "2", "103A", "1"]
    assert sorted(ids, key=natural_key) == ["1", "2", "10", "103A", "103B", "NEHA4"]


def test_sorted_clients_uses_natural_order(computax: Path) -> None:
    """Clients come back in natural ID order."""
    assert [c.id for c in sorted_clients(build_index(computax))] == [
        "1",
        "7D",
        "42",
        "99",
        "264B",
        "EMPTY",
    ]


def test_resolve_skips_compare_and_partial_files(computax: Path) -> None:
    """ComputationCompare and ``.pdf_`` files are never matched."""
    found = resolve_year("1", 2024, computax / "2024/1")
    assert [p.name for p in found.itrv] == ["ITRV_1.pdf"]
    assert [p.name for p in found.computation] == ["Computation_1_2024_1.pdf"]
    assert found.warnings == []


def test_resolve_handles_case_revised_and_numbering(computax: Path) -> None:
    """Revised ITRV comes after the original; computations sort by number."""
    found = resolve_year("7d", 2022, computax / "2022/7D")
    assert [p.name for p in found.itrv] == ["ITRV_7D.pdf", "ITRV_7D_Revised.pdf"]
    assert [p.name for p in found.computation] == [
        "Computation_7D_2022_1.pdf",
        "Computation_7D_2022_2.pdf",
        "Computation_7D_2022_10.pdf",
    ]


def test_resolve_refuses_other_clients_files(computax: Path) -> None:
    """A misfiled folder yields warnings, not another client's files."""
    found = resolve_year("264B", 2021, computax / "2021/264B")
    assert found.itrv == [] and found.computation == []
    assert len(found.warnings) == 2
    assert all("(274)" in w for w in found.warnings)


def test_resolve_missing_folder_is_empty(tmp_path: Path) -> None:
    """An unreadable folder resolves to nothing instead of raising."""
    found = resolve_year("1", 2024, tmp_path / "nope")
    assert found.itrv == [] and found.computation == [] and found.warnings == []


def test_check_root_accepts_computax(computax: Path) -> None:
    """A proper CompuTax folder validates and reports its contents."""
    check = check_root(computax)
    assert check.ok
    assert check.years == [2012, 2020, 2021, 2022, 2023, 2024]
    assert check.client_count == 6


def test_check_root_explains_year_folder(computax: Path) -> None:
    """Picking a year folder by mistake gets a helpful message."""
    check = check_root(computax / "2024")
    assert not check.ok and "single year folder" in check.message


def test_check_root_suggests_child_computax(computax: Path) -> None:
    """Picking the parent of CompuTax points the user at the right folder."""
    check = check_root(computax.parent)
    assert not check.ok and str(computax) in check.message


def test_check_root_missing(tmp_path: Path) -> None:
    """A path that doesn't exist is rejected."""
    assert not check_root(tmp_path / "missing").ok
