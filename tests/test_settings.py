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


def test_instance_record_round_trip_and_ownership(tmp_path: Path) -> None:
    """Only the run that wrote the instance record can clear it."""
    from computax_client_file_download.settings import (
        clear_instance,
        read_instance,
        write_instance,
    )

    f = tmp_path / "instance.json"
    write_instance(f, "http://127.0.0.1:1234/?t=abc", "abc")
    assert read_instance(f) == {"url": "http://127.0.0.1:1234/?t=abc", "token": "abc"}
    clear_instance(f, "someone-else")
    assert f.exists()
    clear_instance(f, "abc")
    assert not f.exists()
