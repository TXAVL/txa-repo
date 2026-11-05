"""Follow a package's own GitHub Releases (``txacli sync``).

``txacli sync`` knows two upstreams: WinGet and the Antigravity download page. Software that lives only in the
maintainer's own GitHub repositories (T-Drop, TXAWinSetup...) is on neither, so it was never updated by the bot.

A package is followed here when the installer links of its newest release in this repository are
``https://github.com/<owner>/<repo>/releases/download/<tag>/<asset>`` and ``<owner>`` is in ``GITHUB_OWNERS``.
Nothing has to be configured: the previous release is the configuration. The newest published release of that
repository is read, the asset that matches each previous asset name (the old version turned into a wildcard) is
downloaded, hashed, and the previous cards are cloned with the new version, link, SHA-256 and size. Everything else
(engine, switches, scope, texts, tags) is kept as it was.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Only releases of these owners are followed automatically. Third-party installers come from WinGet, where a
# reviewed manifest vouches for them; an arbitrary GitHub project is never trusted just because it is linked.
GITHUB_OWNERS = {"TXAVL"}

_ASSET_URL = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/releases/download/([^/\s]+)/([^/\s?#]+)$")
_URL_LINE = re.compile(r"^(?P<indent>\s*)url:\s*(?P<url>https://\S+)\s*$", re.M)
_MAX_BYTES = 4 * 1024 * 1024 * 1024


@dataclass
class Outcome:
    status: str  # "updated" | "up_to_date" | "skipped" | "failed"
    new_version: str = ""
    detail: str = ""


def release_repo(release_dir: Path) -> str | None:
    """'owner/repo' when every installer link of the release is a GitHub release asset of one trusted repo."""
    build = release_dir / "build.txa.yaml"
    if not build.is_file():
        return None
    repos: set[str] = set()
    urls = [m.group("url") for m in _URL_LINE.finditer(build.read_text("utf-8"))]
    if not urls:
        return None
    for url in urls:
        m = _ASSET_URL.match(url)
        if not m or m.group(1) not in GITHUB_OWNERS:
            return None
        repos.add(f"{m.group(1)}/{m.group(2)}")
    return repos.pop() if len(repos) == 1 else None


def asset_pattern(name: str, old_version: str) -> re.Pattern[str]:
    """The file name of the previous asset with its version number turned into a wildcard."""
    escaped = re.escape(name)
    old = re.escape(old_version)
    if old in escaped:
        escaped = escaped.replace(old, r"\d+(?:\.\d+){1,3}")
    return re.compile(f"^{escaped}$")


def pick_latest(releases: list[dict]) -> dict | None:
    """The highest version among published (not draft, not pre-release) releases.

    GitHub's ``/releases/latest`` orders by the *commit date* of the tag, so a release whose tag points at an older
    commit (a re-tagged or back-dated one) is never reported as latest. The version in the tag is what counts.
    """
    from txa.core import semver
    from txa.create.winget import normalize_version

    best: tuple | None = None
    for rel in releases:
        tag = str(rel.get("tag_name", ""))
        if rel.get("draft") or rel.get("prerelease") or not re.search(r"\d+\.\d+", tag):
            continue
        version = normalize_version(tag)
        if not semver.is_valid(version):
            continue
        key = semver.parse(version)
        if best is None or key > best[0]:
            best = (key, rel)
    return best[1] if best else None


def latest_release(repo: str, session=None) -> dict | None:
    """The newest published release of ``repo`` by version, or None."""
    from txa.core import net

    s = session or net.session()
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = s.get(f"https://api.github.com/repos/{repo}/releases", params={"per_page": 50}, headers=headers, timeout=30)
    if response.status_code != 200:
        return None
    return pick_latest(response.json())


def _download_hash(url: str) -> tuple[str, int]:
    from txa.core import net

    work = Path(tempfile.mkdtemp(prefix="gh-sync-", dir=_temp_root()))
    try:
        dl = net.download(net.session(), url, work, _MAX_BYTES)
        return dl.sha256.upper(), dl.bytes
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _temp_root() -> Path:
    from txa.core import config

    return config.temp_root()


def sync_release(
    app_dir: Path,
    release_dir: Path,
    repo: str,
    *,
    dry_run: bool = False,
    keep_old: bool = False,
    fetch: Callable[[str], dict | None] = latest_release,
    fingerprint: Callable[[str], tuple[str, int]] = _download_hash,
) -> Outcome:
    """Check one package against the newest release of ``repo`` and add the new release folder when there is one."""
    from txa.core import retention, semver
    from txa.create.winget import normalize_version

    current = release_dir.name
    release = fetch(repo)
    if not release:
        return Outcome("skipped", detail=f"no published release found in {repo}")
    tag = str(release.get("tag_name", ""))
    if not re.search(r"\d+\.\d+", tag):
        # normalize_version() turns "nightly" into 1.0.0: a tag without a dotted number is never a version
        return Outcome("skipped", detail=f"release tag {tag!r} is not a version")
    new_version = normalize_version(tag)
    if not semver.is_valid(new_version):
        return Outcome("failed", detail=f"release tag {tag!r} is not a version")
    if semver.parse(new_version) <= semver.parse(current):
        return Outcome("up_to_date", new_version)
    new_dir = app_dir / new_version
    if new_dir.exists():
        return Outcome("up_to_date", new_version, "already in the repository")

    assets = {a["name"]: a for a in release.get("assets", [])}
    build = (release_dir / "build.txa.yaml").read_text("utf-8")
    replacements: dict[str, str] = {}
    for m in _URL_LINE.finditer(build):
        old_url = m.group("url")
        parsed = _ASSET_URL.match(old_url)
        pattern = asset_pattern(parsed.group(4), current)
        hits = [name for name in assets if pattern.match(name)]
        if len(hits) != 1:
            why = "no asset matches" if not hits else f"{len(hits)} assets match"
            return Outcome("skipped", new_version, f"{why} {parsed.group(4)!r} in {release.get('tag_name')} - left for a maintainer")
        replacements[old_url] = assets[hits[0]]["browser_download_url"]
    if dry_run:
        return Outcome("updated", new_version, f"{len(replacements)} installer(s) found")

    fingerprints = {old: fingerprint(new) for old, new in replacements.items()}
    try:
        new_dir.mkdir(parents=True)
        for card in sorted(release_dir.iterdir()):
            if not card.is_file():
                continue
            text = card.read_text("utf-8")
            text = re.sub(rf"@{re.escape(current)}\b", f"@{new_version}", text)           # ref: Id@x.y.z and comments
            text = re.sub(rf"(?m)^(  version:\s*){re.escape(current)}\s*$", rf"\g<1>{new_version}", text)  # core card
            if card.name == "build.txa.yaml":
                text = _rewrite_targets(text, replacements, fingerprints)
            (new_dir / card.name).write_text(text, "utf-8", newline="\n")
    except Exception:
        shutil.rmtree(new_dir, ignore_errors=True)  # never leave a half-written release behind
        raise
    if not keep_old:
        retention.prune_package(app_dir)
    return Outcome("updated", new_version)


def _rewrite_targets(text: str, replacements: dict[str, str], fingerprints: dict[str, tuple[str, int]]) -> str:
    """Per target block: new url, then the sha256 and size lines that follow it."""
    out: list[str] = []
    pending: tuple[str, int] | None = None
    for line in text.split("\n"):
        m = re.match(r"^(\s*)url:\s*(\S+)\s*$", line)
        if m and m.group(2) in replacements:
            out.append(f"{m.group(1)}url: {replacements[m.group(2)]}")
            pending = fingerprints[m.group(2)]
            continue
        if pending:
            sha = re.match(r"^(\s*)sha256:\s*\S+\s*$", line)
            size = re.match(r"^(\s*)size:\s*\d+\s*$", line)
            if sha:
                out.append(f"{sha.group(1)}sha256: {pending[0]}")
                continue
            if size:
                out.append(f"{size.group(1)}size: {pending[1]}")
                pending = None
                continue
        out.append(line)
    return "\n".join(out)
