"""Tests for exp/corpus.py: repo-name normalisation and the dev/test split."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from originscan.exp.corpus import (
    make_split,
    normalize_repo,
    read_split,
    split_of,
    write_split,
)


@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("https://github.com/mm2/Little-CMS.git", "mm2/little-cms"),
        ("https://github.com/fluent/fluent-bit/", "fluent/fluent-bit"),
        ("https://github.com/imagemagick/imagemagick", "imagemagick/imagemagick"),
        ("https://gitlab.gnome.org/GNOME/libxml2.git", "gnome/libxml2"),
        ("git://git.code.sf.net/p/matio/matio", "matio/matio"),
        ("https://git.ffmpeg.org/ffmpeg.git", "ffmpeg/ffmpeg"),
        ("  https://github.com/VirusTotal/yara.git  ", "virustotal/yara"),
        ("mm2/little-cms", "mm2/little-cms"),
    ],
)
def test_normalize_repo(addr: str, expected: str) -> None:
    assert normalize_repo(addr) == expected


def test_normalize_repo_is_idempotent() -> None:
    once = normalize_repo("https://github.com/AcademySoftwareFoundation/openexr")
    assert normalize_repo(once) == once


@pytest.mark.parametrize("addr", ["", "https://github.com/", "///"])
def test_normalize_repo_rejects_empty(addr: str) -> None:
    with pytest.raises(ValueError):
        normalize_repo(addr)


def test_split_rejects_unnormalised_name() -> None:
    with pytest.raises(ValueError):
        split_of("https://github.com/mm2/Little-CMS.git")


def test_split_is_stable_across_processes() -> None:
    """The split must not depend on Python's per-process hash seed."""
    repos = ["mm2/little-cms", "ffmpeg/ffmpeg", "gnome/libxml2", "file/file"]
    here = [split_of(r) for r in repos]
    code = (
        "from originscan.exp.corpus import split_of;"
        f"print(','.join(split_of(r) for r in {repos!r}))"
    )
    for seed in ("1", "2"):
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert out.stdout.strip().split(",") == here


def test_split_share_is_near_one_in_five() -> None:
    split = make_split(f"owner/repo{i}" for i in range(2000))
    dev = sum(s == "dev" for s in split.values())
    assert 0.17 < dev / len(split) < 0.23


def test_split_csv_roundtrip(tmp_path) -> None:
    split = make_split(["mm2/little-cms", "ffmpeg/ffmpeg", "gnome/libxml2"])
    path = tmp_path / "split.csv"
    write_split(split, path)
    assert read_split(path) == split
    assert path.read_text(encoding="utf-8").splitlines()[0] == "repo,split"


def test_read_split_rejects_bad_value(tmp_path) -> None:
    path = tmp_path / "split.csv"
    path.write_text("repo,split\nmm2/little-cms,train\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_split(path)
