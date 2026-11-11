"""The 16 TXA checks. Steps 01-14 validate a release; 15-16 live in ci/gate.py."""
from __future__ import annotations

import hmac
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from txa.ci.context import Context
from txa.core import engines, net, pe, portable, retention, semver, signing, winos
from txa.core.licenses import NEEDS_URL, SPDX
from txa.core.manifest import (
    ABOUT_RE, BUILD_FILE, CORE_FILE, ID_RE, LANG_RE, ManifestError, about_file, kind_of, parse_card, ref_of,
    release_dir, schema_errors,
)

TITLES = {
    1: "Character Encoding & BOM Sanity",
    2: "Strict YAML Structure & Indentation Guard",
    3: "Namespace & ID Naming Convention",
    4: "Semantic Versioning & Upgrade Path Check",
    5: "Localization & License Policy Audit",
    6: "Secure Protocol & Redirect Loop Analysis",
    7: "Payload Size Limit & Server Header Inspection",
    8: "CDN Availability & Mirror Reachability",
    9: "Binary Stream Integrity & Download Verification",
    10: "Authenticode & Digital Certificate Verification",
    11: "High-Precision SHA-256 Checksum Match",
    12: "PE Binary Architecture & Installer Engine Detection",
    13: "Windows OS Minimum Version Compatibility",
    14: "Silent Install Command Switches Verification",
    15: "Automated Triage & Custom TXA Labeling",
    16: "Auto-Merge Gate & Code Owner Review Lock",
}
NETWORK_STEPS = {6, 7, 8}  # step 09 decides itself: a supplied payload needs no network
_MAX_MESSAGES = 40


@dataclass
class Outcome:
    messages: list[dict] = field(default_factory=list)

    def _add(self, level: str, text: str) -> None:
        if len(self.messages) < _MAX_MESSAGES:
            self.messages.append({"level": level, "text": text})
        elif len(self.messages) == _MAX_MESSAGES:
            self.messages.append({"level": "info", "text": "… more findings truncated"})

    def fail(self, text: str) -> None:
        self._add("fail", text)

    def warn(self, text: str) -> None:
        self._add("warn", text)

    def ok(self, text: str) -> None:
        self._add("ok", text)

    def info(self, text: str) -> None:
        self._add("info", text)

    def skip(self, text: str) -> None:
        self._add("skip", text)

    @property
    def status(self) -> str:
        levels = {m["level"] for m in self.messages}
        if "fail" in levels:
            return "FAIL"
        if "warn" in levels:
            return "WARN"
        if levels & {"ok", "info"}:
            return "PASS"
        return "SKIP"


StepFn = Callable[[Context, dict, Outcome], None]
REGISTRY: dict[int, StepFn] = {}


def step(number: int):
    def register(fn: StepFn) -> StepFn:
        REGISTRY[number] = fn
        return fn
    return register


def run_step(ctx: Context, number: int) -> list[tuple[dict, Outcome]]:
    fn = REGISTRY[number]
    results = []
    for target in ctx.targets:
        out = Outcome()
        if target["mode"] == "removal":
            out.skip("release is being removed - only a moderator can approve removals")
        elif number in NETWORK_STEPS and ctx.offline:
            out.skip("offline mode")
        else:
            try:
                fn(ctx, target, out)
            except Exception as exc:  # a crashing check must surface as a failure, never a pass
                out.fail(f"internal error in step {number:02d}: {type(exc).__name__}: {exc}")
        ctx.record(number, target, out.status, out.messages)
        results.append((target, out))
    return results


def _targets_or_skip(ctx: Context, target: dict, out: Outcome) -> list[dict]:
    bundle = ctx.bundle(target)
    if bundle.build is None or schema_errors("build", bundle.build):
        out.skip("build card is missing or invalid (see STEP 02)")
        return []
    return bundle.targets()


def _slot(item: dict) -> str:
    """Key/label of one installer: the CPU, plus the language when one CPU has several (x64-vi)."""
    locale = (item.get("locale") or "").split("-")[0]
    return f"{item['arch']}-{locale}" if locale else item["arch"]


def _artifact_file(ctx: Context, target: dict, slot: str) -> Path | None:
    file = ctx.artifact(target, slot).get("file")
    return Path(file) if file and Path(file).exists() else None


# =========================================================================== 01

_INVISIBLE = {
    "​": "zero-width space", "‌": "zero-width non-joiner", "‍": "zero-width joiner",
    "⁠": "word joiner", "﻿": "zero-width no-break space", "­": "soft hyphen",
    "‪": "bidi LRE", "‫": "bidi RLE", "‬": "bidi PDF", "‭": "bidi LRO", "‮": "bidi RLO",
    "⁦": "bidi LRI", "⁧": "bidi RLI", "⁨": "bidi FSI", "⁩": "bidi PDI",
}


@step(1)
def encoding(ctx: Context, target: dict, out: Outcome) -> None:
    bundle = ctx.bundle(target)
    if not bundle.files:
        out.fail("release directory is empty")
        return
    for name, raw in sorted(bundle.files.items()):
        if raw.startswith(b"\xef\xbb\xbf"):
            out.fail(f"{name}: UTF-8 BOM found - save the file as UTF-8 *without* BOM")
        elif raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            out.fail(f"{name}: UTF-16 encoded - TXA cards must be UTF-8")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            out.fail(f"{name}: invalid UTF-8 byte 0x{raw[exc.start]:02X} at offset {exc.start}")
            continue
        if "\r" in text:
            out.fail(f"{name}: CR/CRLF line endings - use LF only")
        hits = 0
        for lineno, line in enumerate(text.split("\n"), 1):
            for col, char in enumerate(line, 1):
                if lineno == 1 and col == 1 and char == "﻿":
                    continue
                code = ord(char)
                problem = None
                if char in _INVISIBLE:
                    problem = f"invisible U+{code:04X} ({_INVISIBLE[char]})"
                elif (code < 0x20 and char not in "\t\r") or 0x7F <= code < 0xA0:
                    problem = f"control character U+{code:04X}"
                elif char == " ":
                    out.warn(f"{name}:{lineno}:{col}: no-break space U+00A0 - use a normal space")
                if problem:
                    hits += 1
                    if hits <= 5:
                        out.fail(f"{name}:{lineno}:{col}: {problem}")
        if raw and not raw.endswith(b"\n"):
            out.warn(f"{name}: no newline at end of file")
    if out.status in ("PASS", "SKIP"):
        out.ok(f"{len(bundle.files)} file(s): UTF-8 without BOM, LF endings, no hidden characters")


# =========================================================================== 02

_BLOCK_SCALAR = re.compile(r"(?:^|:\s|-\s)[|>][-+1-9]{0,2}\s*(?:#.*)?$")


def _line_problems(text: str, max_len: int) -> list[str]:
    problems = []
    block_indent: int | None = None
    for lineno, line in enumerate(text.split("\n"), 1):
        indent = len(line) - len(line.lstrip(" "))
        if block_indent is not None:
            if not line.strip() or indent > block_indent:
                continue
            block_indent = None
        if "\t" in line:
            problems.append(f"line {lineno}: tab character - indent with spaces")
        if line != line.rstrip(" \t"):
            problems.append(f"line {lineno}: trailing whitespace")
        if len(line) > max_len:
            problems.append(f"line {lineno}: {len(line)} characters (limit {max_len})")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if indent % 2:
            problems.append(f"line {lineno}: indentation of {indent} spaces - use multiples of 2")
        if stripped == "...":
            problems.append(f"line {lineno}: document end marker '...' is not allowed")
        if _BLOCK_SCALAR.search(stripped):
            block_indent = indent
        if re.search(r":\s*\{", stripped) or stripped.startswith("{"):
            problems.append(f"line {lineno}: flow mappings {{...}} are not allowed - use block style")
    return problems


@step(2)
def structure(ctx: Context, target: dict, out: Outcome) -> None:
    bundle = ctx.bundle(target)
    max_len = int(ctx.policy["limits"]["max_line_length"])
    checked = 0
    for name in sorted(bundle.files):
        kind = kind_of(name)
        if kind is None:
            continue
        checked += 1
        text = bundle.files[name].decode("utf-8", errors="replace").lstrip("﻿").replace("\r\n", "\n")
        for problem in _line_problems(text, max_len):
            out.fail(f"{name}: {problem}")
        for problem in bundle.problems.get(name, []):
            out.fail(f"{name}: {problem}")
        card = bundle.cards.get(name)
        if card is None:
            continue
        for problem in schema_errors(kind, card):
            out.fail(f"{name}: {problem}")
    build = bundle.build or {}
    arches = [(t.get("arch"), t.get("locale")) for t in build.get("targets") or [] if isinstance(t, dict)]
    for arch, locale in sorted({a for a in arches if arches.count(a) > 1}, key=str):
        out.fail(f"{BUILD_FILE}: architecture '{arch}'{f' / locale {locale}' if locale else ''} is declared more than once")
    if not checked:
        out.fail("no TXA cards found in this directory")
    elif out.status in ("PASS", "SKIP"):
        out.ok(f"{checked} card(s): 2-space block YAML, single document, no duplicate keys, schema v1 valid")


# =========================================================================== 03


@step(3)
def naming(ctx: Context, target: dict, out: Outcome) -> None:
    bundle = ctx.bundle(target)
    parts = target["path"].split("/")
    if ctx.mode == "ci":
        added = [t for t in ctx.targets if t.get("mode") != "removal"]
        packages = {"/".join(t["path"].split("/")[:4]) for t in ctx.targets}
        # one new release of one package; dropping that package's oldest versions (the keep-10 rule) rides along
        if len(added) > 1 or len(packages) > 1:
            out.fail(f"this pull request touches {len(ctx.targets)} releases - submit exactly one release per PR")
    if len(parts) != 5 or parts[0] != "manifests":
        out.fail(f"'{target['path']}' does not follow manifests/<shard>/<Namespace>/<AppName>/<X.Y.Z>/")
    if bundle.subdirs:
        out.fail(f"sub-directories are not allowed inside a release: {', '.join(bundle.subdirs)}")
    package_id, version = bundle.package_id, bundle.version
    if not package_id or not version:
        out.skip("core card unavailable (see STEP 02)")
        return
    match = ID_RE.match(package_id)
    if not match:
        out.fail(f"'{package_id}' is not Namespace.AppName (PascalCase namespace, letters/digits/dashes)")
        return
    namespace, app = match["namespace"], match["app"]
    allowed = ctx.policy.get("namespaces") or []
    if allowed and namespace not in allowed:
        out.fail(f"namespace '{namespace}' is not registered in policy.txa.yaml (allowed: {', '.join(allowed)})")
    if not app[0].isupper():
        out.warn(f"AppName '{app}' should start with an upper-case letter (PascalCase)")
    expected = release_dir(package_id, version)
    if len(parts) == 5 and target["path"] != expected:
        out.fail(f"directory '{target['path']}' does not match the core card - expected '{expected}'")
    ref = ref_of(package_id, version)
    for name, card in sorted(bundle.cards.items()):
        if kind_of(name) in ("build", "about") and card.get("ref") != ref:
            out.fail(f"{name}: ref is '{card.get('ref')}', expected '{ref}'")
    required = {CORE_FILE, BUILD_FILE}
    if bundle.default_lang:
        required.add(about_file(bundle.default_lang))
    for missing in sorted(required - set(bundle.files)):
        out.fail(f"missing required card {missing}")
    for name in sorted(bundle.files):
        if kind_of(name) is None:
            out.fail(f"unexpected file '{name}' - only core.txa.yaml, build.txa.yaml and about.<lang>.txa.yaml")
    _check_collisions(ctx, package_id, _names_of((bundle.core or {}).get("package", {})), out)
    if out.status in ("PASS", "SKIP"):
        out.ok(f"{package_id} → {expected} (namespace '{namespace}' registered)")


def _names_of(package: dict) -> set[str]:
    """Short names a package answers to: alias + aliases."""
    names = set(package.get("aliases") or [])
    if package.get("alias"):
        names.add(package["alias"])
    return names


def _check_collisions(ctx: Context, package_id: str, names: set[str], out: Outcome) -> None:
    root = ctx.repo_root / "manifests"
    if not root.is_dir():
        return
    lowered = package_id.lower()
    for app_dir in root.glob("*/*/*"):
        if not app_dir.is_dir() or app_dir.name.startswith("."):
            continue
        other_id = f"{app_dir.parent.name}.{app_dir.name}"
        if other_id == package_id:
            continue
        if other_id.lower() == lowered:
            out.fail(f"'{package_id}' differs only by letter case from existing package '{other_id}'")
        if not names:
            continue
        versions = [p.name for p in app_dir.iterdir() if p.is_dir() and semver.is_valid(p.name)]
        newest = semver.latest(versions)
        core = app_dir / newest / CORE_FILE if newest else None
        if not (core and core.exists()):
            continue
        try:
            other = parse_card(core.read_text("utf-8")).get("package") or {}
        except ManifestError:
            continue
        for name in sorted(names & _names_of(other)):
            out.fail(f"short name '{name}' is already used by {other_id}")
        for name in sorted(names & {app.lower() for app in [app_dir.name]}):
            out.fail(f"short name '{name}' is the name of package {other_id}")


# =========================================================================== 04


@step(4)
def versioning(ctx: Context, target: dict, out: Outcome) -> None:
    bundle = ctx.bundle(target)
    folder = target["path"].rsplit("/", 1)[-1]
    if not semver.is_valid(folder):
        out.fail(f"release folder '{folder}' is not a strict X.Y.Z version")
    version = bundle.version
    if not version:
        out.skip("core card unavailable (see STEP 02)")
        return
    if not semver.is_valid(version):
        out.fail(f"package.version '{version}' is not a strict X.Y.Z version")
        return
    if version != folder:
        out.fail(f"package.version '{version}' does not match folder '{folder}'")
    existing = [v for v in target.get("existing_versions", []) if semver.is_valid(v)]
    newest = semver.latest(existing)
    if target["mode"] == "update":
        out.ok(f"edits already published {version}; upgrade path unchanged")
    elif not newest:
        out.ok(f"first release {version}")
    elif semver.parse(version) <= semver.parse(newest):
        others = [v for v in existing if v != version]
        newer = sum(1 for v in others if semver.parse(v) > semver.parse(version))
        if version in existing and ctx.mode == "ci":
            out.fail(f"{version} is already published - edit it as an update or pick a new version")
        elif newer < retention.KEEP:
            # the repository keeps the newest KEEP versions, so an older release that still fits is fine
            out.ok(f"older release {version} (newest is {newest}; {newer} newer version(s), the newest {retention.KEEP} are kept)")
        else:
            out.fail(f"{version} is older than the {retention.KEEP} newest versions (newest {newest}) and would be dropped at once")
    else:
        old, new = semver.parse(newest), semver.parse(version)
        bump = "major" if new[0] > old[0] else "minor" if new[1] > old[1] else "patch"
        out.ok(f"upgrade path {newest} → {version} ({bump} bump, {len(existing)} older release(s))")


# =========================================================================== 05

_PLACEHOLDER = re.compile(r"^(todo|tbd|tba|n/?a|none|null|unknown|test|example|xxx+|\.\.\.|-+|lorem ipsum.*)$", re.I)


@step(5)
def localization(ctx: Context, target: dict, out: Outcome) -> None:
    bundle = ctx.bundle(target)
    default = bundle.default_lang
    abouts = bundle.abouts
    if not default:
        out.skip("core card unavailable (see STEP 02)")
        return
    if default not in abouts:
        out.fail(f"default locale '{default}' has no {about_file(default)}")
    reference = abouts.get(default) or {}
    for lang, card in sorted(abouts.items()):
        file = about_file(lang)
        if not LANG_RE.match(lang):
            out.fail(f"{file}: '{lang}' is not a valid language tag (e.g. en-US, vi-VN)")
        if card.get("lang") != lang:
            out.fail(f"{file}: lang is '{card.get('lang')}' but the file name says '{lang}'")
        for key in ("name", "publisher", "author", "summary", "description"):
            value = card.get(key)
            if isinstance(value, str) and (_PLACEHOLDER.match(value.strip()) or re.search(r"<[^>]+>", value)):
                out.fail(f"{file}: {key} looks like a placeholder ({value!r})")
        summary, name = str(card.get("summary", "")), str(card.get("name", ""))
        if summary and summary.strip().lower() == name.strip().lower():
            out.fail(f"{file}: summary must describe the software, not repeat its name")
        if card.get("description") and str(card["description"]).strip() == summary.strip():
            out.warn(f"{file}: description repeats the summary - expand it or drop it")
        license_ = card.get("license") or {}
        license_name = str(license_.get("name", "")).strip()
        if not license_name:
            out.fail(f"{file}: license.name is required")
        elif license_name in NEEDS_URL and not license_.get("url"):
            out.fail(f"{file}: '{license_name}' license needs license.url pointing at the EULA/terms")
        elif license_name not in SPDX and license_name not in NEEDS_URL and not license_.get("url"):
            out.fail(f"{file}: '{license_name}' is not an SPDX id - add license.url or use an SPDX identifier")
        if lang != default and reference:
            same = [k for k in ("summary", "description") if card.get(k) and card.get(k) == reference.get(k)]
            if same:
                out.info(f"{file}: {', '.join(same)} identical to {default} (untranslated)")
        if lang != default and reference and card.get("license") != reference.get("license"):
            out.fail(f"{file}: license differs from the default locale - licenses are not translatable")
    if out.status in ("PASS", "SKIP") and reference:
        lic = reference.get("license", {}).get("name")
        out.ok(f"{len(abouts)} locale(s) [{', '.join(sorted(abouts))}], publisher '{reference.get('publisher')}', license {lic}")


# =========================================================================== 06

_SIGNED_QUERY = re.compile(r"(x-amz-(expires|signature)|[?&](expires|signature|token|sig)=)", re.I)


@step(6)
def protocol(ctx: Context, target: dict, out: Outcome) -> None:
    limits = ctx.policy["limits"]
    s = net.session()
    for item in _targets_or_skip(ctx, target, out):
        arch, source = item["arch"], item["source"]
        slot = _slot(item)
        art = ctx.artifact(target, slot)
        art["mirrors"] = {}
        for role, url in [("primary", source["url"]), *(("mirror", m) for m in source.get("mirrors", []))]:
            if _SIGNED_QUERY.search(url):
                out.warn(f"[{slot}] {url}: looks like a signed/expiring link - it will stop working")
            try:
                result = net.probe(s, url, int(limits["max_redirects"]), float(limits["http_timeout_s"]))
            except net.RedirectLoop as exc:
                out.fail(f"[{slot}] redirect loop: {exc}")
                continue
            except net.UnsafeURL as exc:
                out.fail(f"[{slot}] insecure hop: {exc}")
                continue
            except Exception as exc:  # DNS, TLS, timeouts - all mean "unreachable"
                out.fail(f"[{slot}] {role} unreachable: {type(exc).__name__}: {exc}")
                continue
            record = {
                "final_url": result.final_url, "status": result.status, "length": result.length,
                "headers": result.headers, "hops": [h.url for h in result.hops], "method": result.method,
                "elapsed_ms": result.elapsed_ms,
            }
            if role == "primary":
                art["probe"] = record
            else:
                art["mirrors"][url] = record
            chain = len(result.hops) - 1
            if result.status not in (200, 206):
                out.fail(f"[{slot}] {role} answered HTTP {result.status} after {chain} redirect(s)")
            else:
                out.ok(f"[{slot}] {role}: HTTPS end-to-end, {chain} redirect(s), HTTP {result.status} in {result.elapsed_ms} ms")


# =========================================================================== 07

_WEB_TYPES = {"text/html", "application/xhtml+xml", "application/json", "text/plain", "application/xml", "text/xml"}


@step(7)
def payload_headers(ctx: Context, target: dict, out: Outcome) -> None:
    max_bytes = int(ctx.policy["limits"]["max_payload_mb"]) * 1024 * 1024
    for item in _targets_or_skip(ctx, target, out):
        arch = item["arch"]
        slot = _slot(item)
        probe = ctx.artifact(target, slot).get("probe")
        if not probe:
            out.skip(f"[{slot}] no probe result (see STEP 06)")
            continue
        headers, length = probe["headers"], probe["length"]
        if length is None:
            out.warn(f"[{slot}] server sends no Content-Length - size limit enforced while streaming instead")
        elif length > max_bytes:
            out.fail(f"[{slot}] payload is {length / 1048576:.1f} MiB, limit is {max_bytes // 1048576} MiB")
        declared = item["source"].get("size")
        if declared and length and declared != length:
            out.fail(f"[{slot}] source.size says {declared} bytes, server says {length}")
        ctype = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if ctype in _WEB_TYPES:
            out.fail(f"[{slot}] Content-Type '{ctype}' - the URL serves a web page, not an installer")
        elif not ctype:
            out.warn(f"[{slot}] no Content-Type header")
        wanted = {"msi": ".msi", "portable": ".zip"}.get(item["engine"], ".exe")
        names = [probe["final_url"].split("?", 1)[0].rsplit("/", 1)[-1]]
        disposition = headers.get("content-disposition", "")
        if "filename=" in disposition:
            names.insert(0, disposition.split("filename=", 1)[1].split(";", 1)[0].strip().strip('"'))
        if not any(n.lower().endswith(wanted) for n in names):
            out.warn(f"[{slot}] file name '{names[0]}' does not end with {wanted} for engine '{item['engine']}'")
        cdn = net.cdn_fingerprint(headers) or "unknown"
        server = headers.get("server", "n/a")
        resumable = "yes" if headers.get("accept-ranges", "").lower() == "bytes" or probe["method"].startswith("GET") else "no"
        size = f"{length / 1048576:.2f} MiB" if length else "unknown size"
        out.ok(f"[{slot}] {size}, type {ctype or 'n/a'}, server '{server}', CDN {cdn}, resumable {resumable}, "
               f"last-modified {headers.get('last-modified', 'n/a')}")


# =========================================================================== 08


@step(8)
def availability(ctx: Context, target: dict, out: Outcome) -> None:
    network = ctx.policy["network"]
    regions: dict[str, str] = network.get("regions") or {}
    need = int(network.get("min_regions_ok", 3))
    s = net.session()
    from urllib.parse import urlsplit

    for item in _targets_or_skip(ctx, target, out):
        arch = item["arch"]
        slot = _slot(item)
        art = ctx.artifact(target, slot)
        probe = art.get("probe")
        if not probe:
            out.skip(f"[{slot}] no probe result (see STEP 06)")
            continue
        url = probe["final_url"]
        host = urlsplit(url).hostname or ""
        edges = []
        doh_failed = 0
        for region, subnet in regions.items():
            try:
                addresses = net.doh_resolve(s, host, subnet)
            except Exception:  # DoH outage must not fail the release, see fallback below
                doh_failed += 1
                continue
            if not addresses:
                edges.append(net.EdgeResult(region, None, None, None, "no A record"))
                continue
            edges.append(net.edge_probe(url, addresses[0], region))
        art["edges"] = [e.__dict__ for e in edges]
        if doh_failed == len(regions) or not regions:
            # Fallback: three consecutive probes from the runner itself.
            ok = 0
            for _ in range(3):
                try:
                    if net.probe(s, url).status in (200, 206):
                        ok += 1
                except Exception:
                    pass
            if ok == 3:
                out.warn(f"[{slot}] geo DNS unavailable - {host} answered 3/3 probes from the runner only")
            else:
                out.fail(f"[{slot}] {host} answered only {ok}/3 probes from the runner")
        else:
            good = [e for e in edges if e.ok]
            unique = {e.address for e in good}
            summary = ", ".join(f"{e.region}:{e.status or 'x'}" + (f"/{e.elapsed_ms}ms" if e.elapsed_ms else "") for e in edges)
            anycast = " (anycast edge)" if len(unique) == 1 and len(good) > 1 else ""
            if len(good) >= need:
                out.ok(f"[{slot}] {host}: {len(good)}/{len(edges)} regions healthy{anycast} - {summary}")
            elif good:
                out.warn(f"[{slot}] {host}: only {len(good)}/{len(edges)} regions healthy (want {need}) - {summary}")
            else:
                out.fail(f"[{slot}] {host}: no region could reach the CDN - {summary}")
            for edge in edges:
                if edge.error and not edge.ok:
                    out.info(f"[{slot}] {edge.region} @ {edge.address or '-'}: {edge.error}")
        for mirror, record in (art.get("mirrors") or {}).items():
            if record["status"] not in (200, 206):
                out.fail(f"[{slot}] mirror {mirror} answered HTTP {record['status']}")
            elif record["length"] and probe["length"] and record["length"] != probe["length"]:
                out.fail(f"[{slot}] mirror {mirror} serves {record['length']} bytes, primary serves {probe['length']}")
            else:
                out.ok(f"[{slot}] mirror {urlsplit(mirror).hostname} in sync with primary")


# =========================================================================== 09


@step(9)
def download(ctx: Context, target: dict, out: Outcome) -> None:
    limits = ctx.policy["limits"]
    max_bytes = int(limits["max_payload_mb"]) * 1024 * 1024
    supplied = ctx.payloads.get(target["path"], {})
    s = net.session()
    for item in _targets_or_skip(ctx, target, out):
        arch = item["arch"]
        slot = _slot(item)
        art = ctx.artifact(target, slot)
        if slot not in supplied and arch not in supplied and ctx.offline:
            out.skip(f"[{slot}] offline mode and no local payload")
            continue
        if slot in supplied or arch in supplied:
            path = Path(supplied.get(slot) or supplied[arch])
            art.update({"file": str(path), "bytes": path.stat().st_size, "stream_sha256": None})
            out.ok(f"[{slot}] using local payload {path.name} ({path.stat().st_size} bytes)")
        else:
            try:
                result = net.download(s, item["source"]["url"], ctx.payload_dir(target, slot), max_bytes,
                                      int(limits["max_redirects"]), float(limits["http_timeout_s"]) * 2)
            except Exception as exc:
                out.fail(f"[{slot}] download failed: {type(exc).__name__}: {exc}")
                continue
            art.update({"file": str(result.path), "bytes": result.bytes, "stream_sha256": result.sha256})
            if result.expected is not None and result.bytes != result.expected:
                out.fail(f"[{slot}] truncated stream: {result.bytes}/{result.expected} bytes")
                continue
            probe_len = (art.get("probe") or {}).get("length")
            if probe_len and probe_len != result.bytes:
                out.fail(f"[{slot}] probe announced {probe_len} bytes but {result.bytes} arrived")
                continue
            extra = f", resumed after {result.attempts - 1} interruption(s)" if result.resumed else \
                f", {result.attempts} attempt(s)" if result.attempts > 1 else ""
            out.ok(f"[{slot}] {result.path.name}: {result.bytes} bytes received intact{extra}")
        with open(art["file"], "rb") as fh:
            head = fh.read(16)
        is_zip = head[:4] == b"PK\x03\x04"
        if head[:2] != b"MZ" and head[:8] != engines.CFB_MAGIC and not (is_zip and item["engine"] == "portable"):
            sniff = head[:15].decode("ascii", "replace")
            out.fail(f"[{slot}] payload is not a Windows installer or portable ZIP (starts with {sniff!r})")


# =========================================================================== 10


_NOISE = {"corporation", "corp", "limited", "ltd", "company", "co", "inc", "llc", "software", "technologies", "gmbh", "jsc"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in _NOISE}


def _resembles(publisher: str, signer: str) -> bool:
    """Same company name, ignoring case, spacing and legal suffixes ("Coc Coc Co., Ltd." ~ "Coc Coc Company Limited")."""
    squash = lambda text: "".join(sorted_tokens(text))  # noqa: E731
    sorted_tokens = lambda text: [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _NOISE]  # noqa: E731
    one, two = squash(publisher), squash(signer)
    return bool(one and two and (one in two or two in one)) or bool(_tokens(publisher) & _tokens(signer))


@step(10)
def authenticode(ctx: Context, target: dict, out: Outcome) -> None:
    bundle = ctx.bundle(target)
    publisher = (bundle.default_about() or {}).get("publisher", "")
    require = bool(ctx.policy["signature"].get("require"))
    for item in _targets_or_skip(ctx, target, out):
        arch = item["arch"]
        slot = _slot(item)
        file = _artifact_file(ctx, target, slot)
        if not file:
            out.skip(f"[{slot}] no payload (see STEP 09)")
            continue
        if item["engine"] == "portable":
            out.skip(f"[{slot}] portable ZIP - an archive cannot carry an Authenticode signature")
            continue
        sig = signing.verify(file)
        ctx.artifact(target, slot)["signature"] = {
            "status": sig.status, "signer": sig.signer_cn, "issuer": sig.issuer,
            "thumbprint": sig.thumbprint, "timestamped": sig.timestamped, "engine": sig.engine,
        }
        if sig.status == "valid":
            stamp = "timestamped" if sig.timestamped else "NOT timestamped"
            out.ok(f"[{slot}] valid signature by '{sig.signer_cn}' ({stamp}, verified via {sig.engine})")
            if publisher and sig.signer_cn and not _resembles(publisher, sig.signer_cn):
                out.warn(f"[{slot}] signer '{sig.signer_cn}' does not resemble publisher '{publisher}'")
            if not sig.timestamped:
                out.warn(f"[{slot}] signature is not timestamped - it becomes invalid when the certificate expires")
        elif sig.status == "unsigned":
            (out.fail if require else out.warn)(f"[{slot}] installer is not Authenticode-signed")
        elif sig.status in ("invalid", "untrusted"):
            out.fail(f"[{slot}] signature {sig.status}: {sig.detail}")
        else:
            out.warn(f"[{slot}] signature could not be verified here: {sig.detail}")


# =========================================================================== 11


@step(11)
def checksum(ctx: Context, target: dict, out: Outcome) -> None:
    for item in _targets_or_skip(ctx, target, out):
        arch = item["arch"]
        slot = _slot(item)
        file = _artifact_file(ctx, target, slot)
        if not file:
            out.skip(f"[{slot}] no payload (see STEP 09)")
            continue
        art = ctx.artifact(target, slot)
        disk = net.sha256_file(file)
        art["sha256"] = disk
        stream = art.get("stream_sha256")
        if stream and stream != disk:
            out.fail(f"[{slot}] streamed hash {stream} differs from on-disk hash {disk} - payload changed on disk")
            continue
        declared = str(item["source"]["sha256"]).upper()
        if hmac.compare_digest(declared, disk):
            passes = "2 independent passes" if stream else "1 pass"
            out.ok(f"[{slot}] SHA-256 {disk} matches the manifest ({passes}, {file.stat().st_size} bytes)")
        else:
            out.fail(f"[{slot}] SHA-256 mismatch - manifest {declared}, actual {disk}")


# =========================================================================== 12


def _check_portable(item: dict, file: Path, found: engines.Inspection, out: Outcome) -> None:
    """Portable ZIP: safe to unpack, declared strip/PATH folders hold programs, CPU matches."""
    arch = item["arch"]
    slot = _slot(item)
    if found.format != "zip":
        out.fail(f"[{slot}] engine 'portable' declared but the payload is {found.label}")
        return
    if item["engine"] != "portable":
        out.fail(f"[{slot}] the payload is a ZIP archive - declare engine: portable")
        return
    spec = item["portable"]
    strip, folders = int(spec.get("strip", 0)), spec["path"]
    try:
        by_folder = portable.exes(file, strip)
    except portable.ZipProblem as exc:
        out.fail(f"[{slot}] unsafe archive: {exc}")
        return
    ok = True
    for folder in folders:
        if folder not in by_folder:
            hint = f" (found programs in: {', '.join(by_folder)})" if by_folder else " (the archive has no .exe)"
            out.fail(f"[{slot}] PATH folder '{folder}' has no .exe after strip={strip}{hint}")
            ok = False
    if not ok:
        return
    sample = None
    machine = found.payload_arch if folders[0] == (found.portable.get("path") or [None])[0] and strip == found.portable.get("strip") else None
    if machine is None:
        entry = portable.find_exe(file, strip, folders[0])
        sample = portable.read_member(file, entry) if entry else None
        try:
            machine = pe.read_pe(sample, with_version=False).machine if sample else None
        except pe.PEError as exc:
            out.fail(f"[{slot}] {entry.parts[-1]}: {exc}")
            return
        finally:
            if sample:
                shutil.rmtree(sample.parent, ignore_errors=True)
    programs = ", ".join(sorted({name for f in folders for name in by_folder[f]}))
    layout = found.layout
    summary = f"{layout.files} files, {layout.unpacked / 1048576:.0f} MiB unpacked, PATH {', '.join(folders)} → {programs}"
    if machine == arch:
        out.ok(f"[{slot}] portable ZIP, native {machine} programs; {summary}")
    elif machine == "x86" and arch in ("x64", "arm64"):
        out.warn(f"[{slot}] portable ZIP holds 32-bit programs; {summary}")
    else:
        out.fail(f"[{slot}] programs in '{folders[0]}' are {machine}, which cannot be declared as {arch}")


@step(12)
def binary(ctx: Context, target: dict, out: Outcome) -> None:
    for item in _targets_or_skip(ctx, target, out):
        arch, engine = item["arch"], item["engine"]
        slot = _slot(item)
        file = _artifact_file(ctx, target, slot)
        if not file:
            out.skip(f"[{slot}] no payload (see STEP 09)")
            continue
        found = engines.inspect(file)
        record = {"format": found.format, "engine": found.engine, "label": found.label,
                  "machine": found.machine, "payload_arch": found.payload_arch, "notes": found.notes}
        if found.pe:
            record.update({"os_version": list(found.pe.os_version), "subsystem_version": list(found.pe.subsystem_version),
                           "product_version": found.product_version, "company": found.company})
        ctx.artifact(target, slot)["inspection"] = record
        for note in found.notes:
            out.info(f"[{slot}] {note}")
        if found.format == "unknown":
            out.fail(f"[{slot}] unsupported payload format ({found.label})")
            continue
        if engine == "portable" or found.format == "zip":
            _check_portable(item, file, found, out)
            continue
        if engine == "msi" and found.format != "msi":
            out.fail(f"[{slot}] engine 'msi' declared but the payload is a {found.label}")
            continue
        if engine != "msi" and found.format == "msi":
            out.fail(f"[{slot}] payload is a Windows Installer package - declare engine: msi")
            continue
        if engine != "msi":
            if found.engine == engine:
                pass
            elif engine == "exe":
                if found.engine != "exe":
                    out.warn(f"[{slot}] detected {found.label} - declare engine: {found.engine} to get verified default switches")
            elif engine in ("nsis", "inno") and found.label == "7-Zip SFX":
                # Mozilla (Firefox, Thunderbird) wraps its NSIS setup.exe in a 7-Zip SFX that forwards the switches
                out.warn(f"[{slot}] 7-Zip SFX wrapper around a {engine} setup - switches are forwarded to the inner setup")
            else:
                out.fail(f"[{slot}] engine '{engine}' declared but {found.label} detected")
                continue
        if found.format == "msi":
            if found.payload_arch == "x64" and arch == "arm64":
                # x64 template runs on ARM64 through emulation; some vendors (Blender) tag their ARM64 MSI this way
                out.warn(f"[{slot}] MSI template targets x64 but manifest says arm64 - runs through emulation, confirm the payload is native")
            elif found.payload_arch and found.payload_arch != arch:
                out.fail(f"[{slot}] MSI template targets {found.payload_arch}, manifest says {arch}")
                continue
            out.ok(f"[{slot}] {found.label}, template '{found.msi.get('template')}'")
            continue
        machine = found.machine
        if machine == arch:
            out.ok(f"[{slot}] native {machine} PE, engine {found.label}")
        elif machine == "x86" and arch in ("x64", "arm64"):
            note = f"[{slot}] 32-bit {found.label} bootstrapper installing {arch} payload"
            (out.warn if engine == "exe" else out.ok)(note + ("" if engine != "exe" else " - confirm manually"))
        else:
            out.fail(f"[{slot}] PE machine is {machine}, which cannot be declared as {arch}")


# =========================================================================== 13


@step(13)
def os_compat(ctx: Context, target: dict, out: Outcome) -> None:
    bundle = ctx.bundle(target)
    items = _targets_or_skip(ctx, target, out)
    if not items:
        return
    text = bundle.build["platform"]["min_build"]
    try:
        declared = winos.parse_build(text)
    except ValueError as exc:
        out.fail(str(exc))
        return
    floor = winos.parse_build(ctx.policy["os"]["floor"])
    if declared > winos.NEWEST_GA:
        out.fail(f"min_build {text} is newer than the newest released build {winos.fmt(winos.NEWEST_GA)} - nobody could install it")
        return
    if declared not in winos.BUILDS:
        out.warn(f"min_build {text} is not a known GA build ({winos.describe(declared)})")
    if declared < (6, 1, 0):
        out.fail(f"min_build {text} predates Windows 7 - not supported by TXA")
    for item in items:
        arch = item["arch"]
        slot = _slot(item)
        if arch == "arm64" and declared < winos.ARM64_FLOOR:
            out.fail(f"[arm64] arm64 desktop apps need {winos.fmt(winos.ARM64_FLOOR)} or newer, min_build is {text}")
        inspection = ctx.artifact(target, slot).get("inspection") or {}
        needs = max(tuple(inspection.get("os_version") or (0, 0)), tuple(inspection.get("subsystem_version") or (0, 0)))
        if needs > declared[:2]:
            out.fail(f"[{slot}] binary header requires Windows NT {needs[0]}.{needs[1]}, but min_build says {text}")
        elif inspection.get("format") == "pe":
            out.ok(f"[{slot}] PE header needs NT {needs[0]}.{needs[1]} ≤ declared {declared[0]}.{declared[1]}")
    where = "below" if declared < floor else "at/above"
    out.ok(f"min_build {text} = {winos.describe(declared)} ({where} TXA floor {winos.fmt(floor)})")


# =========================================================================== 14


@step(14)
def switches(ctx: Context, target: dict, out: Outcome) -> None:
    for item in _targets_or_skip(ctx, target, out):
        arch, engine = item["arch"], item["engine"]
        slot = _slot(item)
        if engine == "portable":
            out.ok(f"[{slot}] portable: txapm unpacks the archive and edits PATH - nothing is executed, no switches")
            continue
        effective = engines.effective_switches(item)
        errors, warnings = engines.check_switches(engine, effective)
        if engine == "msi" and any(t.lower() in ("/i", "/package", "/x") for t in engines.tokens(" ".join(effective.values()))):
            errors.append("do not include /i or /x - txapm calls `msiexec /i <file>` itself")
        codes = item.get("success_codes")
        if codes and 0 not in codes:
            warnings.append("success_codes does not include 0")
        for error in errors:
            out.fail(f"[{slot}] {error}")
        for warning in warnings:
            out.warn(f"[{slot}] {warning}")
        if not errors:
            source = "declared" if item.get("switches") else "TXA defaults"
            out.ok(f"[{slot}] {engine}: silent '{effective['silent']}', progress '{effective['progress']}' ({source})")
