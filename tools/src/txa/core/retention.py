"""How many versions of a package the repository keeps: the newest ``KEEP``; adding one drops the oldest."""
from __future__ import annotations

import shutil
from pathlib import Path

from txa.core import semver

KEEP = 10


def stale_versions(versions: list[str], keep: int = KEEP, protect: str | None = None) -> list[str]:
    """Versions beyond the newest ``keep`` (oldest first). ``protect`` (a version being added) is never returned."""
    valid = sorted((v for v in set(versions) if semver.is_valid(v)), key=semver.parse, reverse=True)
    return [v for v in reversed(valid[keep:]) if v != protect]


def prune_package(package_dir: Path, keep: int = KEEP) -> list[str]:
    """Delete the oldest release folders of one package; returns the versions removed."""
    versions = [d.name for d in package_dir.iterdir() if d.is_dir() and semver.is_valid(d.name)] if package_dir.is_dir() else []
    removed = stale_versions(versions, keep)
    for version in removed:
        shutil.rmtree(package_dir / version, ignore_errors=True)
    return removed


def prune_repo(root: Path, keep: int = KEEP, dry_run: bool = False) -> dict[str, list[str]]:
    """Apply the rule to every package under ``<root>/manifests``."""
    report: dict[str, list[str]] = {}
    for package_dir in sorted((root / "manifests").glob("*/*/*")):
        if not package_dir.is_dir():
            continue
        versions = [d.name for d in package_dir.iterdir() if d.is_dir() and semver.is_valid(d.name)]
        stale = stale_versions(versions, keep)
        if stale:
            report[f"{package_dir.parent.name}.{package_dir.name}"] = stale
            if not dry_run:
                for version in stale:
                    shutil.rmtree(package_dir / version, ignore_errors=True)
    return report
