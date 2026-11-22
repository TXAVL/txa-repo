"""Package sources.

A source is anything that serves the txa.v1 REST API::

    <url>/index.json                every package, newest version summary
    <url>/packages/<Id>.json        every version of one package (core, build, about cards)

- the official ``txa`` source (GitHub Pages of txa-repo, with a GitHub contents fallback);
- any custom HTTPS server: a company mirror, an intranet share, another GitHub Pages site -
  generate the files with ``txaci build-api`` from a folder of manifests;
- a local folder that contains ``manifests/`` (read directly, no server needed).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import requests

from txa.core import config, net, semver
from txa.core.github import GitHub, GitHubError
from txa.core.manifest import Bundle, assemble, package_dir, split_id


class NotFound(LookupError):
    pass


class SourceError(ValueError):
    pass


def _local_path(url: str) -> Path | None:
    if url.startswith("file://"):
        return Path(url[7:].lstrip("/") if re.match(r"^file:///[A-Za-z]:", url) else url[7:])
    if re.match(r"^[A-Za-z]:[\\/]", url) or url.startswith(("\\\\", "/", ".")):
        return Path(url)
    return None


def check_url(url: str) -> str:
    """Normalise a source location and refuse insecure ones."""
    local = _local_path(url)
    if local is not None:
        local = local.expanduser().resolve()
        if not (local / "manifests").is_dir():
            raise SourceError(f"{local} has no manifests/ folder")
        return str(local)
    parts = urlsplit(url)
    if parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1"):
        return url.rstrip("/")
    if parts.scheme != "https" or not parts.hostname:
        raise SourceError(f"{url}: sources must use https:// (or be a local folder)")
    return url.rstrip("/")


class Source:
    def __init__(self, api: str | None = None, upstream: str | None = None, token: str | None = None,
                 name: str = config.OFFICIAL_SOURCE, token_env: str | None = None, allow_lan: bool = False,
                 fallback: bool | None = None):
        self.name = name
        self.api = (api or config.api_base()).rstrip("/")
        self.local = _local_path(self.api)
        self.upstream = upstream or config.get("upstream")
        self.token_env = token_env
        self.allow_lan = allow_lan
        self.fallback = (name == config.OFFICIAL_SOURCE) if fallback is None else fallback
        self.http = net.session()
        if token_env and os.environ.get(token_env):
            self.http.headers["Authorization"] = f"Bearer {os.environ[token_env]}"
        self._token = token
        self._index: dict | None = None
        self._packages: dict | None = None
        self._pending: list[dict] | None = None
        self.used_fallback = False

    @classmethod
    def from_config(cls, item: dict) -> "Source":
        if item.get("official"):
            return cls()
        return cls(item["url"], name=item["name"], token_env=item.get("token_env"),
                   allow_lan=bool(item.get("allow_lan")), fallback=False)

    # ------------------------------------------------------------------ transport
    def _local_packages(self) -> dict:
        if self._packages is None:
            from txa.ci.api import collect

            self._packages = collect(self.local)[0]
        return self._packages

    def _get_json(self, path: str) -> dict | None:
        if self.local is not None:
            from txa.ci.api import index_document, package_document

            packages = self._local_packages()
            if path == "index.json":
                return index_document(packages)
            package_id = path[len("packages/"):-len(".json")]
            return package_document(package_id, packages[package_id]) if package_id in packages else None
        try:
            response = self.http.get(f"{self.api}/{path}", timeout=30)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def download_headers(self, url: str) -> dict:
        """Send the source's credentials to installer URLs on the same host only."""
        auth = self.http.headers.get("Authorization")
        if auth and self.local is None and urlsplit(url).hostname == urlsplit(self.api).hostname:
            return {"Authorization": auth}
        return {}

    # ------------------------------------------------------------------ queries
    def index(self) -> dict:
        if self._index is None:
            self._index = self._get_json("index.json") or {"packages": []}
        return self._index

    def pending(self) -> list[dict]:
        """Packages whose pull request is open (the index's pending.json); empty for sources that do not publish it."""
        if self._pending is None:
            data = self._get_json("pending.json") if self.local is None else None
            self._pending = [e for e in (data or {}).get("packages", []) if isinstance(e, dict) and e.get("id") and e.get("version")]
        return self._pending

    def find_pending(self, query: str, version: str | None = None) -> dict | None:
        lowered = query.lower()
        namespaced = f"{config.get('namespace')}.{query}".lower()
        hits = []
        for entry in self.pending():
            names = {str(entry["id"]).lower(), str(entry.get("alias") or "").lower(),
                     *(str(a).lower() for a in entry.get("aliases", []))}
            if (lowered in names or str(entry["id"]).lower() == namespaced) and (not version or entry["version"] == version):
                hits.append(entry)
        valid = [h for h in hits if semver.is_valid(h["version"])]
        return max(valid, key=lambda h: semver.parse(h["version"])) if valid else (hits[0] if hits else None)

    def find(self, query: str) -> str | None:
        """Exact id, alias or <namespace>.<query> in this source's index, else None."""
        lowered = query.lower()
        namespaced = f"{config.get('namespace')}.{query}".lower()
        for entry in self.index().get("packages", []):
            names = {entry["id"].lower(), (entry.get("alias") or "").lower(), *(a.lower() for a in entry.get("aliases", []))}
            if lowered in names or entry["id"].lower() == namespaced:
                return entry["id"]
        return None

    def resolve(self, query: str) -> str:
        found = self.find(query)
        if found:
            return found
        return query if "." in query else f"{config.get('namespace')}.{query}"

    def search(self, text: str) -> list[dict]:
        """Every word of ``text`` must appear somewhere in the id, names, summary or tags ('-' counts as a space)."""
        from txa.core import i18n

        words = text.lower().replace("-", " ").split()
        hits = []
        for entry in self.index().get("packages", []):
            loc_summary = i18n.localize_summary(entry["id"], entry.get("summary", ""), entry.get("summaries"))
            haystack = " ".join([entry["id"], entry.get("alias") or "", " ".join(entry.get("aliases", [])),
                                 entry.get("name", ""), entry.get("summary", ""), loc_summary,
                                 " ".join(entry.get("tags", []))]).lower().replace("-", " ")
            if all(word in haystack for word in words):
                hits.append(entry)
        return hits

    def release(self, package_id: str, version: str | None = None) -> tuple[str, dict]:
        """Return (version, {core, build, about}) for the requested or newest version."""
        document = self._get_json(f"packages/{package_id}.json")
        if document:
            versions = document.get("versions", {})
            chosen = version or document.get("latest") or semver.latest(versions)
            if version and version not in versions:
                chosen = semver.resolve_prefix(version, versions) or version  # '--version 8' = newest 8.x.y
            if chosen not in versions:
                raise NotFound(f"{package_id} has no version {chosen} (available: {', '.join(versions)})")
            return chosen, versions[chosen]
        if not self.fallback:
            raise NotFound(f"package {package_id} not found in source '{self.name}'")
        return self._github_release(package_id, version)

    def versions(self, package_id: str) -> list[str]:
        document = self._get_json(f"packages/{package_id}.json")
        if document:
            return list(document.get("versions", {}))
        if not self.fallback:
            raise NotFound(f"package {package_id} not found in source '{self.name}'")
        return sorted(self._github_versions(package_id), key=semver.parse, reverse=True)

    # ------------------------------------------------------------------ GitHub fallback (official only)
    def _gh(self) -> GitHub:
        if self._token is None:
            from txa.core.credentials import load_token

            self._token = load_token()[0] or ""
        return GitHub(self._token or None)

    def _github_versions(self, package_id: str) -> list[str]:
        from txa.core.manifest import ManifestError

        try:
            split_id(package_id)
        except ManifestError:
            raise NotFound(f"package {package_id} not found in {self.upstream}") from None
        path = f"repos/{self.upstream}/contents/{package_dir(package_id)}"
        try:
            entries = self._gh().get(path)
        except GitHubError as exc:
            if exc.status == 401 and self._token:
                self._token = ""
                try:
                    entries = self._gh().get(path)
                except GitHubError as exc2:
                    if exc2.status in (401, 403, 404):
                        raise NotFound(f"package {package_id} not found in {self.upstream}") from None
                    raise
            elif exc.status in (401, 403, 404):
                raise NotFound(f"package {package_id} not found in {self.upstream}") from None
            else:
                raise
        return [e["name"] for e in entries if e["type"] == "dir" and semver.is_valid(e["name"])]

    def _github_release(self, package_id: str, version: str | None) -> tuple[str, dict]:
        self.used_fallback = True
        versions = self._github_versions(package_id)
        chosen = version or semver.latest(versions)
        if not chosen or chosen not in versions:
            raise NotFound(f"{package_id} has no version {version or '(none published)'}")
        path = f"{package_dir(package_id)}/{chosen}"
        gh = self._gh()
        texts = {}
        for entry in gh.get(f"repos/{self.upstream}/contents/{path}"):
            if entry["type"] == "file" and re.search(r"\.txa\.yaml$", entry["name"]):
                raw = self.http.get(entry["download_url"], timeout=30)
                raw.raise_for_status()
                texts[entry["name"]] = raw.content.decode("utf-8")
        bundle = Bundle.from_texts(path, texts)
        if bundle.problems or not bundle.core or not bundle.build:
            raise NotFound(f"{package_id} {chosen} has unreadable cards in {self.upstream}")
        return chosen, assemble(bundle)


class LocalRelease:
    """One release folder on disk (``txapm install --manifest <folder>``) - for testing a manifest before submitting it."""

    name = "local"
    allow_lan = False
    used_fallback = False

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.bundle = Bundle.read(self.folder)
        if not self.bundle.package_id or not self.bundle.version:
            raise SourceError(f"{self.folder}: no readable core.txa.yaml")
        problems = [f"{name}: {text}" for name, items in self.bundle.problems.items() for text in items]
        if problems or not self.bundle.build or not self.bundle.default_about():
            raise SourceError(f"{self.folder} is not a complete manifest: " + ("; ".join(problems) or
                              "it needs core.txa.yaml, build.txa.yaml and an about card"))

    @property
    def package_id(self) -> str:
        return self.bundle.package_id

    def release(self, package_id: str, version: str | None = None) -> tuple[str, dict]:
        return self.bundle.version, assemble(self.bundle)

    def download_headers(self, url: str) -> dict:
        return {}


class Sources:
    """All enabled sources, queried in priority order (the official source first)."""

    def __init__(self, only: str | None = None):
        configured = config.sources()
        if only:
            chosen = [s for s in configured if s["name"].lower() == only.lower()]
            if not chosen:
                from txa.core import console
                matches = console.suggest_words(only, [s["name"] for s in configured])
                hint = f" — did you mean '{matches[0]}'? (see `txapm source list`)" if matches else " (see `txapm source list`)"
                raise SourceError(f"no source named '{only}'{hint}")
        else:
            chosen = [s for s in configured if s.get("enabled", True)]
        if not chosen:
            raise SourceError("every source is disabled - `txapm source enable txa`")
        self.items = [Source.from_config(s) for s in chosen]

    def get(self, name: str) -> Source:
        for source in self.items:
            if source.name.lower() == name.lower():
                return source
        return Sources(name).items[0]

    def resolve(self, query: str) -> tuple[Source, str]:
        hits = []
        for source in self.items:
            try:
                found = source.find(query)
            except Exception:  # one unreachable source must not break the others
                found = None
            if found:
                hits.append((source, found))
        if len({s.name for s, _ in hits}) > 1:
            names = ", ".join(f"{pid} ({s.name})" for s, pid in hits)
            raise SourceError(f"'{query}' exists in several sources: {names} - pick one with --source")
        if hits:
            return hits[0]
        first = self.items[0]
        return first, first.resolve(query)  # lets the official GitHub fallback try

    def find_pending(self, query: str, version: str | None = None) -> tuple["Source", dict] | None:
        for source in self.items:
            try:
                entry = source.find_pending(query, version)
            except Exception:  # an unreachable source must not hide the others
                continue
            if entry:
                return source, entry
        return None

    def pending_matching(self, text: str) -> list[tuple["Source", dict]]:
        words = text.lower().replace("-", " ").split()
        out = []
        for source in self.items:
            try:
                entries = source.pending()
            except Exception:
                continue
            for entry in entries:
                haystack = " ".join([str(entry["id"]), str(entry.get("alias") or ""), " ".join(entry.get("aliases", [])),
                                     str(entry.get("name", "")), str(entry.get("summary", ""))]).lower().replace("-", " ")
                if all(word in haystack for word in words):
                    out.append((source, entry))
        return out

    def search(self, text: str) -> list[tuple[Source, dict]]:
        out = []
        for source in self.items:
            try:
                out += [(source, entry) for entry in source.search(text)]
            except Exception:
                continue
        return out

    def suggest(self, query: str, limit: int = 3) -> list[str]:
        """Suggest closest package IDs / aliases when a user mistypes a package name."""
        from txa.core import console

        q = query.strip().split(".")[-1] if "." in query else query.strip()
        if not q:
            return []
        lookup: dict[str, str] = {}
        for source in self.items:
            try:
                for entry in source.index().get("packages", []):
                    pkg_id = entry["id"]
                    alias = entry.get("alias")
                    label = f"{pkg_id} ({alias})" if alias else pkg_id
                    short = pkg_id.split(".")[-1]
                    lookup[short.lower()] = label
                    lookup[pkg_id.lower()] = label
                    if alias:
                        lookup[alias.lower()] = label
                    for a in entry.get("aliases", []):
                        lookup[str(a).lower()] = label
            except Exception:
                continue
        matched_keys = console.suggest_words(q, list(lookup.keys()), limit=limit * 2)
        out: list[str] = []
        for k in matched_keys:
            val = lookup[k]
            if val not in out:
                out.append(val)
            if len(out) >= limit:
                break
        return out
