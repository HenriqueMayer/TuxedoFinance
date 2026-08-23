#!/usr/bin/env python3
"""Validate the public Tuxedo Finance version contract."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def fail(message: str) -> None:
    print(f"Version check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_toml(path: Path) -> dict:
    with path.open("rb") as source:
        return tomllib.load(source)


def main() -> None:
    project = read_toml(ROOT / "pyproject.toml")["project"]
    version = project["version"]

    if not SEMVER.fullmatch(version):
        fail(f"pyproject.toml version {version!r} is not valid Semantic Versioning")

    lock_packages = read_toml(ROOT / "uv.lock").get("package", [])
    locked_project = [
        package for package in lock_packages if package.get("name") == project["name"]
    ]
    if len(locked_project) != 1:
        fail("uv.lock must contain exactly one tuxedo-finance project entry")
    if locked_project[0].get("version") != version:
        fail(
            "uv.lock project version does not match pyproject.toml; "
            "run `uv lock`"
        )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if f'alt="Version {version}"' not in readme:
        fail("README version badge does not match pyproject.toml")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release_heading = re.compile(
        rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
        re.MULTILINE,
    )
    if not release_heading.search(changelog):
        fail(f"CHANGELOG.md has no dated [{version}] release section")

    ref_type = os.environ.get("GITHUB_REF_TYPE")
    ref_name = os.environ.get("GITHUB_REF_NAME")
    if ref_type == "tag" and ref_name != f"v{version}":
        fail(f"tag {ref_name!r} must be v{version}")

    print(f"Tuxedo Finance version {version} is consistent.")


if __name__ == "__main__":
    main()
