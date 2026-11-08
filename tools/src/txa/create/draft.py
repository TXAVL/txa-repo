"""Turn analysed installers + metadata into the three TXA cards."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from txa import __version__
from txa.constants import UPSTREAM_REPO
from txa.core import engines
from txa.core.manifest import (
    BUILD_FILE, CORE_FILE, SCHEMA_URL, about_file, dump_card, ref_of, release_dir,
)

_ARCH_HINTS = [
    ("arm64", r"arm64|aarch64"),
    ("x64", r"x64|amd64|win64|x86_64|x86-64|64-?bit"),
    ("x86", r"x86|win32|ia32|i[3-6]86|32-?bit"),
]


def known_arch(filename: str, found: engines.Inspection) -> str | None:
    """The CPU the software targets when the file itself says so (MSI/ZIP contents, or the file name)."""
    if found.payload_arch:
        return found.payload_arch
    lowered = filename.lower()
    for arch, pattern in _ARCH_HINTS:
        if re.search(rf"(?<![a-z0-9])(?:{pattern})(?![a-z0-9])", lowered):
            return arch
    return None


def guess_arch(filename: str, found: engines.Inspection) -> str:
    return known_arch(filename, found) or (found.machine if found.machine in ("x64", "x86", "arm64") else "x64")


def name_from_filename(filename: str) -> str:
    stem = re.sub(r"\.(exe|msi)$", "", filename, flags=re.I)
    stem = re.sub(r"[-_. ]?v?\d+(\.\d+)+.*$", "", stem)
    stem = re.sub(r"(?i)[-_. ](setup|installer|install|x64|x86|arm64|win64|win32|amd64)(?=$|[-_. ])", "", stem)
    return stem or filename


def pascal(text: str) -> str:
    text = text.replace("+", " Plus ").replace("#", " Sharp ").replace("&", " And ")
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(w[:1].upper() + w[1:] for w in words)[:64] or "App"


@dataclass
class TargetDraft:
    url: str
    arch: str
    engine: str
    sha256: str
    size: int
    payload: Path
    switches: dict[str, str] = field(default_factory=dict)
    mirrors: list[str] = field(default_factory=list)
    portable: dict = field(default_factory=dict)  # {"strip": n, "path": [...]} - engine "portable" only

    def card(self) -> dict:
        source = {"url": self.url, "sha256": self.sha256, "size": self.size}
        if self.mirrors:
            source["mirrors"] = self.mirrors
        entry = {"arch": self.arch, "engine": self.engine, "source": source}
        if self.engine == "portable":
            entry["portable"] = {k: v for k, v in self.portable.items() if k != "strip" or v}
            return entry
        switches = {k: v for k, v in self.switches.items() if v}
        if switches:
            entry["switches"] = switches
        return entry


@dataclass
class Item:
    """One downloaded installer while the user is still answering questions about it."""

    url: str
    dl: object  # net.Download
    found: engines.Inspection
    engine: str
    arch: str
    arch_known: bool = False  # True when the file itself (or its name) says which CPU it targets
    switches: dict = field(default_factory=dict)
    mirrors: list = field(default_factory=list)
    portable: dict = field(default_factory=dict)

    def target(self) -> "TargetDraft":
        return TargetDraft(self.url, self.arch, self.engine, self.dl.sha256, self.dl.bytes, self.dl.path,
                           {} if self.engine == "portable" else dict(self.switches), list(self.mirrors),
                           dict(self.portable))


@dataclass
class Draft:
    package_id: str
    version: str
    lang: str = "en-US"
    channel: str = "stable"
    alias: str | None = None
    aliases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    min_build: str = "10.0.17763"
    scope: str = "machine"
    name: str = ""
    publisher: str = ""
    author: str = ""
    summary: str = ""
    description: str | None = None
    homepage: str | None = None
    license_name: str = ""
    license_url: str | None = None
    targets: list[TargetDraft] = field(default_factory=list)
    extra_abouts: dict[str, dict] = field(default_factory=dict)  # carried over translations

    @property
    def ref(self) -> str:
        return ref_of(self.package_id, self.version)

    @property
    def directory(self) -> str:
        return release_dir(self.package_id, self.version)

    def cards(self) -> dict[str, dict]:
        package = {"id": self.package_id, "version": self.version, "channel": self.channel}
        if self.alias:
            package["alias"] = self.alias
        if self.aliases:
            package["aliases"] = self.aliases
        core = {"txa": 1, "kind": "core", "package": package, "locale": {"default": self.lang}}
        if self.tags:
            core["tags"] = self.tags
        build = {
            "txa": 1, "kind": "build", "ref": self.ref,
            "platform": {"os": "windows", "min_build": self.min_build},
            "scope": self.scope,
            "targets": [t.card() for t in sorted(self.targets, key=lambda t: ("x64", "arm64", "x86").index(t.arch))],
        }
        about = {"txa": 1, "kind": "about", "ref": self.ref, "lang": self.lang, "name": self.name,
                 "publisher": self.publisher, "author": self.author, "summary": self.summary}
        if self.description:
            about["description"] = self.description
        if self.homepage:
            about["homepage"] = self.homepage
        about["license"] = {"name": self.license_name, **({"url": self.license_url} if self.license_url else {})}
        cards = {CORE_FILE: core, BUILD_FILE: build, about_file(self.lang): about}
        for lang, translated in self.extra_abouts.items():
            if lang != self.lang:
                cards[about_file(lang)] = {**translated, "ref": self.ref, "license": about["license"]}

        # Auto-generate vi-VN about card if default is en-US and translation or pattern exists
        if self.lang.lower().startswith("en") and "vi-VN" not in self.extra_abouts:
            from txa.core import i18n
            vi_summary = i18n._SUMMARIES_VI.get(self.package_id.split(".")[-1].lower())
            if not vi_summary:
                out_sum = self.summary
                for pat, repl in i18n._SUMMARY_PATTERNS_VI:
                    out_sum = pat.sub(repl, out_sum)
                if out_sum != self.summary and len(out_sum) >= 10:
                    vi_summary = out_sum
            if vi_summary:
                vi_about = {
                    "txa": 1, "kind": "about", "ref": self.ref, "lang": "vi-VN", "name": self.name,
                    "publisher": self.publisher, "author": self.author, "summary": vi_summary,
                }
                if self.homepage:
                    vi_about["homepage"] = self.homepage
                vi_about["license"] = dict(about["license"])
                cards[about_file("vi-VN")] = vi_about

        return cards

    def render(self) -> dict[str, str]:
        out = {}
        for filename, card in self.cards().items():
            kind = card["kind"]
            header = [
                f"yaml-language-server: $schema={SCHEMA_URL.format(repo=UPSTREAM_REPO, kind=kind)}",
                f"TXA {kind} card · {self.ref} · generated by txacreate {__version__}",
            ]
            out[filename] = dump_card(card, header)
        return out
