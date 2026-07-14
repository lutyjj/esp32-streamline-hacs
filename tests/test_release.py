"""Release version preparation tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tools.release import check_version, prepare_version

if TYPE_CHECKING:
    from pathlib import Path


def manifest(tmp_path: Path, version: str = "0.1.0") -> Path:
    """Write a representative ordered integration manifest."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"domain": "streamline", "version": version}, indent=2) + "\n")
    return path


def test_prepare_updates_only_the_manifest_version(tmp_path: Path) -> None:
    path = manifest(tmp_path)

    assert prepare_version(path, "0.2.0") is True

    assert json.loads(path.read_text()) == {"domain": "streamline", "version": "0.2.0"}


def test_prepare_same_version_preserves_exact_bytes(tmp_path: Path) -> None:
    path = manifest(tmp_path)
    before = path.read_bytes()

    assert prepare_version(path, "0.1.0") is False

    assert path.read_bytes() == before


@pytest.mark.parametrize("version", ["v0.2.0", "0.2", "0.2.0-rc.1", "01.2.0"])
def test_release_version_must_be_stable_semver(tmp_path: Path, version: str) -> None:
    with pytest.raises(ValueError, match=r"stable X\.Y\.Z"):
        prepare_version(manifest(tmp_path), version)


def test_prepare_rejects_a_downgrade(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="older"):
        prepare_version(manifest(tmp_path, "1.0.0"), "0.9.0")


def test_check_requires_the_exact_manifest_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not match"):
        check_version(manifest(tmp_path), "0.2.0")
