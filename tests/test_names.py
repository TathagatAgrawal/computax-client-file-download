"""Tests for reading client names out of FiledJson files."""

from pathlib import Path

from computax_client_file_download.names import client_names, find_assessee_name, format_name, load_names
from computax_client_file_download.scanner import build_index


def test_latest_name_wins_and_older_becomes_alias(computax: Path) -> None:
    """The newest year's highest-numbered FiledJson gives the name."""
    index = build_index(computax)
    assert client_names(index["1"]) == ("ASHA SHARMA", ["ASHA VERMA"])


def test_firm_name_with_bom_and_extra_spaces(computax: Path) -> None:
    """ITR-5 org names are read, BOMs tolerated and spaces collapsed."""
    index = build_index(computax)
    assert client_names(index["42"]) == ("SHARMA TRADERS", [])


def test_misfiled_folder_does_not_take_other_clients_name(computax: Path) -> None:
    """264B's folder holds 274's FiledJson, which must be ignored."""
    index = build_index(computax)
    assert client_names(index["264B"]) == (None, [])


def test_malformed_json_is_skipped(computax: Path) -> None:
    """Broken JSON just means no name."""
    index = build_index(computax)
    assert client_names(index["99"]) == (None, [])


def test_load_names_covers_all_clients(computax: Path) -> None:
    """load_names returns an entry for every client, keyed by upper-cased ID."""
    index = build_index(computax)
    names = load_names(list(index.values()))
    assert set(names) == set(index)


def test_find_assessee_name_in_lists() -> None:
    """The search also descends into lists."""
    data = {"a": [{"b": 1}, {"AssesseeName": {"FirstName": "X"}}]}
    assert find_assessee_name(data) == {"FirstName": "X"}


def test_format_name_empty() -> None:
    """All-empty parts give None."""
    assert format_name({"FirstName": "", "SurNameOrOrgName": None}) is None
