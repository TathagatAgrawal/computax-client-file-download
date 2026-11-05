"""Tests for saving and loading the CompuTax path."""

from pathlib import Path

from computax_client_file_download.settings import load_root, save_root


def test_round_trip(tmp_path: Path) -> None:
    """A saved path loads back unchanged."""
    f = tmp_path / "cfg" / "settings.json"
    save_root(f, "/data/CompuTax")
    assert load_root(f) == "/data/CompuTax"


def test_missing_or_corrupt_file(tmp_path: Path) -> None:
    """Missing, corrupt or wrongly shaped files give None."""
    f = tmp_path / "settings.json"
    assert load_root(f) is None
    f.write_text("{oops")
    assert load_root(f) is None
    f.write_text("[1, 2]")
    assert load_root(f) is None
