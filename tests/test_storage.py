"""Tests for the resilient output writers."""

import os

import pandas as pd
import pytest

from src import storage


def frame() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})


def test_write_csv_creates_the_file_without_an_index(tmp_path):
    target = storage.write_csv(frame(), tmp_path / "out.csv")
    assert target.read_text(encoding="utf-8").splitlines()[0] == "a,b"
    assert pd.read_csv(target).equals(frame())


def test_write_csv_creates_missing_folders(tmp_path):
    target = storage.write_csv(frame(), tmp_path / "deep" / "folder" / "out.csv")
    assert target.is_file()


def test_write_csv_replaces_an_existing_file(tmp_path):
    target = tmp_path / "out.csv"
    target.write_text("old content", encoding="utf-8")
    storage.write_csv(frame(), target)
    assert "old content" not in target.read_text(encoding="utf-8")


def test_write_csv_leaves_no_temporary_file(tmp_path):
    storage.write_csv(frame(), tmp_path / "out.csv")
    assert [p.name for p in tmp_path.iterdir()] == ["out.csv"]


def test_write_csv_retries_until_the_lock_clears(tmp_path, monkeypatch):
    attempts = {"count": 0}
    real_replace = os.replace

    def flaky_replace(source, destination):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise OSError(22, "Invalid argument")
        return real_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", flaky_replace)
    target = storage.write_csv(frame(), tmp_path / "out.csv", delay=0)

    assert attempts["count"] == 3
    assert pd.read_csv(target).equals(frame())
    assert [p.name for p in tmp_path.iterdir()] == ["out.csv"]


def test_write_csv_raises_a_clear_error_when_the_lock_never_clears(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage.os,
        "replace",
        lambda source, destination: (_ for _ in ()).throw(OSError(22, "Invalid argument")),
    )

    with pytest.raises(OSError, match="Could not write"):
        storage.write_csv(frame(), tmp_path / "out.csv", retries=2, delay=0)

    assert list(tmp_path.iterdir()) == []


def test_write_text_round_trip(tmp_path):
    target = storage.write_text('{"a": 1}', tmp_path / "out.json")
    assert target.read_text(encoding="utf-8") == '{"a": 1}'


def test_write_text_replaces_an_existing_file(tmp_path):
    target = tmp_path / "out.json"
    target.write_text("old", encoding="utf-8")
    storage.write_text("new", target)
    assert target.read_text(encoding="utf-8") == "new"
