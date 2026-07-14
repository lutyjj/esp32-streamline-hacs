"""Prepare and validate the integration version in manifest.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

STABLE_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
DEFAULT_MANIFEST = Path("custom_components/streamline/manifest.json")


def parse_version(value: str) -> tuple[int, int, int]:
    """Parse a stable semantic version."""
    match = STABLE_VERSION.fullmatch(value)
    if match is None:
        raise ValueError("version must be a stable X.Y.Z value")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def read_manifest(path: Path) -> dict[str, Any]:
    """Read one Home Assistant manifest object."""
    value: object = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def prepare_version(path: Path, version: str) -> bool:
    """Set a non-decreasing stable version and report whether the file changed."""
    requested = parse_version(version)
    manifest = read_manifest(path)
    current_value = manifest.get("version")
    if not isinstance(current_value, str):
        raise ValueError(f"{path} has no string version")
    current = parse_version(current_value)
    if requested < current:
        raise ValueError(f"version {version} is older than manifest version {current_value}")
    if requested == current:
        return False
    manifest["version"] = version
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return True


def check_version(path: Path, version: str) -> None:
    """Require the manifest to carry the requested stable version."""
    parse_version(version)
    current = read_manifest(path).get("version")
    if current != version:
        raise ValueError(f"version {version} does not match {path} ({current})")


def main() -> int:
    """Run one release-version operation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("prepare", "check"))
    parser.add_argument("version")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        if args.operation == "prepare":
            prepare_version(args.manifest, args.version)
        else:
            check_version(args.manifest, args.version)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
