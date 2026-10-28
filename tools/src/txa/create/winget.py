"""WinGet bridge for ``txacreate`` and ``winget-import``.

Resolves package names or WinGet IDs (including installed programs from ``txapm list --all``)
into official HTTPS installer URLs and metadata so ``txacreate new`` can run automatically
without manual URL hunting.
"""
from __future__ import annotations

import re
import subprocess
from typing import Any

import yaml

from txa.core import config, licenses

ENGINE_MAP = {
    "inno": "inno",
    "nullsoft": "nsis",
    "nsis": "nsis",
    "msi": "msi",
    "wix": "msi",
    "burn": "wix",
    "zip": "portable",
    "portable": "portable",
    "exe": "exe",
}

DEFAULT_SWITCHES = {
    "inno": {"silent": "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-", "progress": "/SILENT /SUPPRESSMSGBOXES /NORESTART /SP-"},
    "nsis": {"silent": "/S", "progress": "/S"},
    "msi": {"silent": "/qn /norestart", "progress": "/qb! /norestart"},
    "wix": {"silent": "/quiet /norestart", "progress": "/passive /norestart"},
    "exe": {"silent": "/S", "progress": "/S"},
}

_TOP_KEY_RE = re.compile(r"^([A-Za-z0-9 ]+):\s*(.*)$")
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")

# Skip system runtimes / store extensions / MSIX-only built-ins when scanning installed programs
_SKIP_ID_PREFIXES = (
    "ARP\\",
    "MSIX\\",
    "Microsoft.VCRedist.",
    "Microsoft.VCLibs.",
    "Microsoft.UI.Xaml.",
    "Microsoft.WindowsAppRuntime.",
    "Microsoft.DotNet.Native.",
    "Microsoft.CLRTypesSQLServer.",
    "Microsoft.AppInstaller",
    "Microsoft.WindowsTerminal",
    "Microsoft.Teams",
    "Python.Launcher",
    "Python.PythonInstallManager",
)

_GENERIC_APP_PARTS = {
    "cli", "launcher", "connect", "community", "professional", "enterprise",
    "desktop", "client", "runtime", "sdk", "server", "agent", "installer",
    "manager", "hub", "studio", "code", "app", "player", "viewer",
}


def derive_txa_app_name(pkg_id_raw: str, raw_name: str) -> str:
    """Derive a clean, non-colliding PascalCase AppName from WinGet ID and display name."""
    from txa.create.draft import pascal

    parts = [p for p in pkg_id_raw.split(".") if p]
    app_part = parts[-1] if parts else "App"
    if len(parts) >= 3 or len(app_part) <= 3 or app_part.isdigit() or app_part.lower() in _GENERIC_APP_PARTS:
        if len(parts) == 2 and parts[0].lower() != parts[1].lower():
            candidate = f"{parts[0]} {parts[1]}"
        else:
            candidate = clean_query_name(raw_name)
            if "dotnet" in pkg_id_raw.lower() and "net" not in candidate.lower():
                candidate = re.sub(r"^Microsoft\b", "Microsoft NET", candidate, flags=re.I)
    else:
        candidate = app_part
    pascal_app = pascal(candidate)
    digits = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}
    if pascal_app and pascal_app[0] in digits:
        pascal_app = digits[pascal_app[0]] + pascal_app[1:]
    return re.sub(r"^[^A-Za-z0-9]+", "", pascal_app)[:48] or "App"


def clean_query_name(name: str) -> str:
    """Strip version suffixes and parentheticals from installed program display names."""
    s = name.strip()
    s = re.sub(r"\s*\((?:User|Machine|x64|x86|64-bit|32-bit|remove only)\)\s*", " ", s, flags=re.I)
    s = re.sub(r"(?:\s*[-–—]\s*|\s+)(?:version\s+)?v?\d+(?:\.\d+)+[^\s]*.*$", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def normalize_version(v: str) -> str:
    """Coerce any version string into strict X.Y.Z semver."""
    if not v:
        return "1.0.0"
    v_clean = re.sub(r"^[vV]", "", str(v).strip())
    parts = re.findall(r"\d+", v_clean)
    if not parts:
        return "1.0.0"
    if len(parts) == 1:
        return f"{int(parts[0])}.0.0"
    if len(parts) == 2:
        return f"{int(parts[0])}.{int(parts[1])}.0"
    return f"{int(parts[0])}.{int(parts[1])}.{int(parts[2])}"


def clean_tag(tag: str) -> str | None:
    t = re.sub(r"[^a-z0-9-]", "", str(tag).strip().lower()).strip("-")
    if 2 <= len(t) <= 32 and _TAG_RE.match(t):
        return t
    return None


def parse_winget_show(text: str) -> dict[str, Any] | None:
    """Parse output of ``winget show`` robustly."""
    lines = text.strip().splitlines()
    if not lines:
        return None

    pkg_name = None
    pkg_id = None
    first = lines[0].strip()
    match = re.search(r"Found\s+(.+?)\s+\[([^\]]+)\]", first)
    if match:
        pkg_name = match.group(1).strip()
        pkg_id = match.group(2).strip()
        body_lines = lines[1:]
    else:
        body_lines = lines

    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in body_lines:
        m = _TOP_KEY_RE.match(line)
        if m and not line.startswith(" "):
            if current_key:
                sections[current_key] = current_lines
            current_key = m.group(1).strip()
            rest = m.group(2).strip()
            current_lines = [rest] if rest else []
        else:
            if current_key is not None:
                current_lines.append(line)

    if current_key:
        sections[current_key] = current_lines

    data: dict[str, Any] = {}
    if pkg_name:
        data["PackageName"] = pkg_name
    if pkg_id:
        data["PackageIdentifier"] = pkg_id

    for k in ["Version", "Publisher", "Publisher Url", "Publisher Support Url", "Author", "Moniker",
              "Homepage", "License", "License Url", "Copyright"]:
        if k in sections and sections[k]:
            data[k] = sections[k][0]

    if "Description" in sections:
        desc_lines = [l.strip() for l in sections["Description"] if l.strip()]
        data["Description"] = " ".join(desc_lines)

    if "Tags" in sections:
        tags = [l.strip().lstrip("-").strip() for l in sections["Tags"] if l.strip()]
        data["Tags"] = tags

    if "Installer" in sections:
        inst_block = "\n".join(sections["Installer"])
        try:
            inst_dict = yaml.safe_load(inst_block)
            if isinstance(inst_dict, dict):
                data["Installer"] = inst_dict
        except Exception:
            pass

    return data


def query_winget_package(package_id: str, arches: tuple[str, ...] = ("x64", "arm64", "x86")) -> dict[str, Any] | None:
    """Query WinGet CLI across CPU architectures and combine installer targets."""
    combined: dict[str, Any] = {}
    targets_by_arch: dict[str, dict[str, Any]] = {}

    def _fetch_one(arch: str, inst_type_flag: str | None = None) -> dict[str, Any] | None:
        cmd = ["winget", "show", "--id", package_id, "-e", "-a", arch, "-s", "winget", "--disable-interactivity", "--nowarn"]
        if inst_type_flag:
            cmd += ["--installer-type", inst_type_flag]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=20)
        except Exception:
            return None
        if res.returncode != 0 or not res.stdout:
            return None
        return parse_winget_show(res.stdout)

    for arch in arches:
        parsed = _fetch_one(arch)
        if not parsed:
            continue
        if not combined:
            combined = parsed

        inst = parsed.get("Installer")
        if isinstance(inst, dict):
            inst_type = str(inst.get("Installer Type", "exe")).lower()
            # If default installer is msix/appx, try traditional Win32 installer types
            if inst_type in ("msix", "appx", "msstore"):
                for alt_type in ("nullsoft", "inno", "wix", "msi", "exe", "burn", "zip", "portable"):
                    alt_parsed = _fetch_one(arch, alt_type)
                    if alt_parsed and isinstance(alt_parsed.get("Installer"), dict):
                        inst = alt_parsed["Installer"]
                        inst_type = str(inst.get("Installer Type", alt_type)).lower()
                        break

            url = str(inst.get("Installer Url") or "").strip()
            sha = str(inst.get("Installer SHA256") or "").strip().upper()
            clean_url = url.split("?")[0].lower()
            if clean_url.endswith(".zip") or inst_type in ("zip", "portable"):
                engine = "portable"
            else:
                engine = ENGINE_MAP.get(inst_type, "exe")
            if url.startswith("https://") and len(sha) == 64 and inst_type not in ("msix", "appx", "msstore"):
                targets_by_arch[arch] = {
                    "arch": arch,
                    "url": url,
                    "sha256": sha,
                    "type": inst_type,
                    "engine": engine,
                    "switches": inst.get("Installer Switches") or {},
                }

    if not combined or not targets_by_arch:
        return None

    combined["_targets"] = targets_by_arch
    return combined


def _parse_winget_table(stdout: str) -> list[dict[str, str]]:
    """Parse fixed-width table output from ``winget search`` or ``winget list`` using header column offsets."""
    lines = stdout.splitlines()
    header_idx = -1
    for i, line in enumerate(lines):
        if "Name" in line and "Id" in line and "Version" in line:
            header_idx = i
            break
    if header_idx == -1 or header_idx + 2 >= len(lines):
        return []

    header = lines[header_idx]
    id_col = header.find("Id")
    ver_col = header.find("Version")
    avail_col = header.find("Available")
    match_col = header.find("Match")
    src_col = header.find("Source")

    after_ver_cols = [c for c in (avail_col, match_col, src_col) if c > ver_col]
    end_ver_col = min(after_ver_cols) if after_ver_cols else -1

    rows: list[dict[str, str]] = []
    for line in lines[header_idx + 2:]:
        if not line.strip() or line.startswith("---"):
            continue
        name = line[:id_col].strip()
        pkg_id = line[id_col:ver_col].strip() if ver_col > id_col else line[id_col:].strip()
        end_ver = end_ver_col if end_ver_col != -1 else len(line)
        version = line[ver_col:end_ver].strip() if ver_col != -1 else ""
        source = line[src_col:].strip() if src_col != -1 and len(line) > src_col else ""
        if name and pkg_id:
            rows.append({"name": name, "id": pkg_id, "version": version, "source": source})
    return rows


def search_winget(query: str, limit: int = 15) -> list[dict[str, str]]:
    """Search WinGet for matching packages by keyword or PackageIdentifier."""
    q = query.strip()
    if not q:
        return []

    # 1. Standard general search (searches Name, Id, Moniker, Tags)
    for candidate in ([q] + ([clean_query_name(q)] if clean_query_name(q).lower() != q.lower() else [])):
        if not candidate:
            continue
        cmd = ["winget", "search", candidate, "-s", "winget", "--disable-interactivity", "--nowarn"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=20)
            rows = _parse_winget_table(res.stdout)
            if rows:
                return rows[:limit]
        except Exception:
            pass

    # 2. Fallback: search explicitly by --id if query contains a dot
    if "." in q and " " not in q:
        cmd = ["winget", "search", "--id", q, "-s", "winget", "--disable-interactivity", "--nowarn"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=20)
            rows = _parse_winget_table(res.stdout)
            if rows:
                return rows[:limit]
        except Exception:
            pass

    return []


def resolve_to_winget_id(query: str) -> str | None:
    """Resolve an arbitrary app name or WinGet ID to an exact WinGet PackageIdentifier."""
    q = query.strip()
    if not q:
        return None

    # 1. If it looks like a Publisher.App ID, try exact ID match first
    if "." in q and " " not in q:
        cmd = ["winget", "show", "--id", q, "-e", "-s", "winget", "--disable-interactivity", "--nowarn"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
            if res.returncode == 0 and "Found " in res.stdout:
                m = re.search(r"Found\s+.+?\s+\[([^\]]+)\]", res.stdout.splitlines()[0])
                return m.group(1).strip() if m else q
        except Exception:
            pass

    # 2. Search winget by query (and cleaned query if it has version numbers)
    candidates = [q]
    cleaned = clean_query_name(q)
    if cleaned and cleaned.lower() != q.lower():
        candidates.append(cleaned)

    for candidate in candidates:
        cmd = ["winget", "search", candidate, "-s", "winget", "--disable-interactivity", "--nowarn"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=20)
        except Exception:
            continue
        rows = _parse_winget_table(res.stdout)
        if not rows:
            continue

        cand_lower = candidate.lower()
        for r in rows:
            if r["name"].lower() == cand_lower or r["id"].lower() == cand_lower:
                return r["id"]
        for r in rows:
            if r["name"].lower().startswith(cand_lower) or r["id"].lower().endswith("." + cand_lower):
                return r["id"]
        return rows[0]["id"]

    return None


def scan_installed_winget_packages(include_existing: bool = False, repo_root=None) -> list[dict[str, str]]:
    """Scan installed programs via ``winget list`` and filter out ones already in TXA."""
    from pathlib import Path
    from txa.core.manifest import find_repo_root

    existing_ids: set[str] = set()
    existing_names: set[str] = set()
    ns = config.get("namespace")
    if repo_root is None:
        repo_root = find_repo_root(Path.cwd())
    if not include_existing:
        try:
            from txa.pm.source import Sources
            for source in Sources().items:
                try:
                    for entry in source.index().get("packages", []):
                        existing_ids.add(entry["id"].lower())
                        existing_names.add(entry["name"].lower())
                        if entry.get("alias"):
                            existing_names.add(entry["alias"].lower())
                except Exception:
                    continue
        except Exception:
            pass
        if repo_root is not None:
            ns_dir = Path(repo_root) / "manifests" / ns[0].lower() / ns
            if ns_dir.is_dir():
                for child in ns_dir.iterdir():
                    if child.is_dir():
                        existing_ids.add(f"{ns}.{child.name}".lower())

    cmd = ["winget", "list", "--disable-interactivity", "--nowarn"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
    except Exception:
        return []

    rows = _parse_winget_table(res.stdout)
    found: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for r in rows:
        if r["source"] != "winget":
            continue
        name, pkg_id, version = r["name"], r["id"], r["version"]
        if any(pkg_id.startswith(prefix) for prefix in _SKIP_ID_PREFIXES):
            continue
        if pkg_id.lower() in seen_ids:
            continue

        non_digit_parts = [p.lower() for p in pkg_id.split(".") if p and not p.isdigit()]
        app_slug = non_digit_parts[-1] if non_digit_parts else pkg_id.split(".")[-1].lower()
        derived_app = derive_txa_app_name(pkg_id, name).lower()
        derived_no_digits = re.sub(r"\d+$", "", derived_app)
        name_clean = clean_query_name(name).lower()
        if not include_existing:
            if name.lower() in existing_names or name_clean in existing_names or app_slug in existing_names:
                continue
            if f"{ns}.{app_slug}".lower() in existing_ids:
                continue
            if f"{ns}.{derived_app}".lower() in existing_ids or f"{ns}.{derived_no_digits}".lower() in existing_ids:
                continue

        seen_ids.add(pkg_id.lower())
        found.append({"name": name, "id": pkg_id, "version": version})

    return found


def populate_args_from_winget(args, data: dict[str, Any], namespace: str) -> list[str]:
    """Populate ``txacreate new`` argparse Namespace from WinGet metadata and return unique URLs."""
    pkg_id_raw = data.get("PackageIdentifier") or "App.Tool"
    raw_name = data.get("PackageName") or pkg_id_raw.split(".")[-1]
    raw_version = str(data.get("Version") or "1.0.0")

    if not getattr(args, "id", None):
        pascal_app = derive_txa_app_name(pkg_id_raw, raw_name)
        args.id = f"{namespace}.{pascal_app}"

    if not getattr(args, "version", None):
        args.version = normalize_version(raw_version)

    if not getattr(args, "name", None):
        name = clean_query_name(raw_name)[:64] or raw_name[:64]
        args.name = name if len(name) >= 2 else f"{name} App"

    pub = str(data.get("Publisher") or data.get("Author") or namespace).strip()[:128]
    if len(pub) < 2:
        pub = f"{pub} Team"
    if not getattr(args, "publisher", None):
        args.publisher = pub
    if not getattr(args, "author", None):
        author = str(data.get("Author") or pub).strip()[:128]
        args.author = author if len(author) >= 2 else pub

    if not getattr(args, "summary", None):
        summary = str(data.get("ShortDescription") or data.get("Description") or f"{args.name} installer for Windows.").strip()
        summary = re.sub(r"\s+", " ", summary)
        if len(summary) < 10:
            summary = f"{args.name} official installer for Windows."
        if len(summary) > 160:
            cutoff = summary[:157].rfind(" ")
            summary = summary[:cutoff if cutoff > 50 else 157] + "..."
        args.summary = summary

    if not getattr(args, "homepage", None):
        hp = str(data.get("Homepage") or data.get("Publisher Url") or "").strip()
        if hp.startswith("https://"):
            args.homepage = hp

    if not getattr(args, "license", None):
        raw_lic = str(data.get("License") or "").strip()
        norm_lic = licenses.normalize(raw_lic) if raw_lic else None
        if norm_lic and (norm_lic in licenses.SPDX or norm_lic in licenses.NEEDS_URL):
            lic_name = norm_lic
        elif "mit" in raw_lic.lower():
            lic_name = "MIT"
        elif "apache" in raw_lic.lower():
            lic_name = "Apache-2.0"
        elif "gpl" in raw_lic.lower():
            lic_name = "GPL-3.0-or-later"
        elif "bsd" in raw_lic.lower():
            lic_name = "BSD-3-Clause"
        else:
            lic_name = "Proprietary"
        args.license = lic_name

    if not getattr(args, "license_url", None):
        lic_url = str(data.get("License Url") or "").strip()
        if lic_url.startswith("https://"):
            args.license_url = lic_url
        elif args.license in licenses.NEEDS_URL:
            args.license_url = getattr(args, "homepage", None) or f"https://github.com/{config.get('upstream')}"

    if not getattr(args, "alias", None):
        moniker = str(data.get("Moniker") or "").strip().lower()
        alias = re.sub(r"[^a-z0-9-]", "", moniker).strip("-")
        if not (2 <= len(alias) <= 40):
            alias = re.sub(r"[^a-z0-9-]", "", args.id.split(".")[-1].lower()).strip("-")
        if 2 <= len(alias) <= 40:
            args.alias = alias

    if not getattr(args, "tags", None):
        raw_tags = data.get("Tags") or []
        cleaned = []
        for t in raw_tags:
            ct = clean_tag(t)
            if ct and ct not in cleaned:
                cleaned.append(ct)
            if len(cleaned) >= 16:
                break
        if cleaned:
            args.tags = ",".join(cleaned)

    targets = data.get("_targets") or {}
    # Deduplicate URLs when the same universal installer is served for multiple arches
    unique_targets: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for arch in ("x64", "arm64", "x86"):
        t = targets.get(arch)
        if t and t["url"] not in seen_urls:
            seen_urls.add(t["url"])
            unique_targets.append(t)

    if unique_targets:
        if not getattr(args, "arch", None):
            args.arch = ",".join(t["arch"] for t in unique_targets)
        if not getattr(args, "engine", None):
            args.engine = ",".join(t["engine"] for t in unique_targets)
        first_sw = unique_targets[0].get("switches") or {}
        def_sw = DEFAULT_SWITCHES.get(unique_targets[0]["engine"], {})
        if not getattr(args, "silent", None):
            args.silent = str(first_sw.get("Silent") or def_sw.get("silent") or "/S").strip()
        if not getattr(args, "progress", None):
            args.progress = str(first_sw.get("SilentWithProgress") or def_sw.get("progress") or args.silent).strip()

    return [t["url"] for t in unique_targets]


def sanitize_alias(moniker: str | None) -> str | None:
    if not moniker:
        return None
    alias = re.sub(r"[^a-z0-9-]", "", moniker.strip().lower()).strip("-")
    if 2 <= len(alias) <= 40 and re.match(r"^[a-z0-9][a-z0-9-]{1,39}$", alias):
        return alias
    return None


def convert_winget_to_draft(data: dict[str, Any], namespace: str = "TXAVL", override_id: str | None = None):
    """Convert WinGet metadata dictionary into a TXA Draft object."""
    import textwrap
    from pathlib import Path
    from txa.create.draft import Draft, TargetDraft

    pkg_id_raw = data.get("PackageIdentifier") or data.get("Id") or "App.Tool"
    raw_name = data.get("PackageName") or data.get("Name") or pkg_id_raw.split(".")[-1]
    raw_version = str(data.get("Version") or data.get("PackageVersion") or "1.0.0")

    version = normalize_version(raw_version)

    if override_id:
        pkg_id = override_id
    else:
        pascal_app = derive_txa_app_name(pkg_id_raw, raw_name)
        pkg_id = f"{namespace}.{pascal_app}"

    name = (raw_name.strip() or "Tool")[:64]
    if len(name) < 2:
        name = f"{name} App"

    pub = str(data.get("Publisher") or data.get("Author") or namespace).strip()[:128]
    if len(pub) < 2:
        pub = f"{pub} Team"
    author = str(data.get("Author") or pub).strip()[:128]
    if len(author) < 2:
        author = pub

    summary = str(data.get("ShortDescription") or data.get("Description") or f"{name} package for Windows.").strip()
    summary = re.sub(r"\s+", " ", summary)
    if len(summary) < 10:
        summary = f"{name} official installer for Windows."
    if len(summary) > 160:
        cutoff = summary[:157].rfind(" ")
        summary = summary[:cutoff if cutoff > 50 else 157] + "..."

    description = str(data.get("Description") or "").strip()[:4000] or None
    if description and summary and (description.lower() == summary.lower() or len(description) <= len(summary)):
        description = None
    elif description:
        wrapped_lines = []
        for paragraph in description.split("\n"):
            p = paragraph.strip()
            if p:
                wrapped_lines.append(textwrap.fill(p, width=120))
        description = "\n".join(wrapped_lines) if wrapped_lines else None

    homepage = str(data.get("Homepage") or data.get("Publisher Url") or "").strip()
    if not homepage.startswith("https://"):
        homepage = None

    raw_lic = str(data.get("License") or "").strip()
    norm_lic = licenses.normalize(raw_lic) if raw_lic else None
    if norm_lic and (norm_lic in licenses.SPDX or norm_lic in licenses.NEEDS_URL):
        lic_name = norm_lic
    elif "mit" in raw_lic.lower():
        lic_name = "MIT"
    elif "apache" in raw_lic.lower():
        lic_name = "Apache-2.0"
    elif "gpl" in raw_lic.lower():
        lic_name = "GPL-3.0-or-later"
    elif "bsd" in raw_lic.lower():
        lic_name = "BSD-3-Clause"
    else:
        lic_name = "Proprietary"

    lic_url = str(data.get("License Url") or "").strip()
    if not lic_url.startswith("https://"):
        lic_url = homepage if (homepage and lic_name in licenses.NEEDS_URL) else (
            f"https://github.com/{config.get('upstream')}" if lic_name in licenses.NEEDS_URL else None
        )

    moniker = data.get("Moniker")
    alias = sanitize_alias(moniker)
    if not alias:
        short = sanitize_alias(pkg_id.split(".")[-1])
        if short and short != pkg_id.lower():
            alias = short

    raw_tags = data.get("Tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    cleaned_tags = []
    for t in raw_tags:
        ct = clean_tag(t)
        if ct and ct not in cleaned_tags:
            cleaned_tags.append(ct)
        if len(cleaned_tags) >= 16:
            break

    targets_data = data.get("_targets") or {}
    target_drafts = []

    for arch, tinfo in targets_data.items():
        url = tinfo["url"]
        if not url.startswith("https://"):
            continue
        sha = tinfo["sha256"]
        engine = tinfo.get("engine") or ENGINE_MAP.get(tinfo.get("type", "exe").lower(), "exe")

        switches = dict(DEFAULT_SWITCHES.get(engine, {}))
        custom_sw = tinfo.get("switches", {})
        if isinstance(custom_sw, dict):
            if custom_sw.get("Silent"):
                switches["silent"] = str(custom_sw["Silent"]).strip()
            if custom_sw.get("SilentWithProgress"):
                switches["progress"] = str(custom_sw["SilentWithProgress"]).strip()
            if custom_sw.get("Custom"):
                switches["custom"] = str(custom_sw["Custom"]).strip()

        portable_dict = {}
        if engine == "portable":
            portable_dict = {"path": ["."]}

        target_drafts.append(TargetDraft(
            url=url,
            arch=arch,
            engine=engine,
            sha256=sha,
            size=1,
            payload=Path(""),
            switches=switches,
            portable=portable_dict,
        ))

    return Draft(
        package_id=pkg_id,
        version=version,
        name=name,
        publisher=pub,
        author=author,
        summary=summary,
        description=description,
        homepage=homepage,
        license_name=lic_name,
        license_url=lic_url,
        alias=alias,
        tags=cleaned_tags,
        targets=target_drafts,
    )


def validate_draft(draft) -> list[str]:
    """Validate Draft against TXA JSON schemas."""
    from txa.core.manifest import BUILD_FILE, CORE_FILE, about_file, schema_errors

    cards = draft.cards()
    errors = []
    for kind, card in [("core", cards[CORE_FILE]), ("build", cards[BUILD_FILE]), ("about", cards[about_file(draft.lang)])]:
        errs = schema_errors(kind, card)
        for e in errs:
            errors.append(f"{kind}: {e}")
    return errors


def save_draft_manifests(draft, root_dir, dry_run: bool = False):
    """Save rendered manifests to <root_dir>/manifests/<shard>/<Namespace>/<AppName>/<Version>/ with LF endings."""
    from pathlib import Path

    root_path = Path(root_dir)
    rel_path = draft.directory
    target_dir = root_path / rel_path
    if dry_run:
        return target_dir

    target_dir.mkdir(parents=True, exist_ok=True)
    rendered = draft.render()
    for filename, content in rendered.items():
        content_lf = content.replace("\r\n", "\n")
        (target_dir / filename).write_text(content_lf, encoding="utf-8", newline="\n")
    return target_dir


# Hand-written / non-WinGet packages that must NEVER be overwritten by automatic WinGet sync
_HANDWRITTEN_APPS = {
    "CanhCutTeamLauncher",
    "TXAWinSetup",
    "Warframe",
}

# Deterministic mapping from TXAVL AppName -> exact WinGet PackageIdentifier
_TXAVL_WINGET_MAP: dict[str, str] = {
    "Audacity": "Audacity.Audacity",
    "Brave": "Brave.Brave",
    "Chrome": "Google.Chrome.EXE",
    "Claude": "Anthropic.Claude",
    "Cloudflared": "Cloudflare.cloudflared",
    "CocCoc": "CocCoc.CocCoc",
    "Discord": "Discord.Discord",
    "Edge": "Microsoft.Edge",
    "FFmpeg": "Gyan.FFmpeg.Essentials",
    "Firefox": "Mozilla.Firefox",
    "Garena": "Garena.Garena",
    "GIMP": "GIMP.GIMP.3",
    "Git": "Git.Git",
    "GitHubCLI": "GitHub.cli",
    "GitHubDesktop": "GitHub.GitHubDesktop",
    "MicrosoftBuildOfOpenJDKWithHotspot17": "Microsoft.OpenJDK.17",
    "MicrosoftNETSDK": "Microsoft.DotNet.SDK.10",
    "MicrosoftNETWindowsDesktopRuntime": "Microsoft.DotNet.DesktopRuntime.8",
    "NodeJS": "OpenJS.NodeJS.LTS",
    "NotepadPlusPlus": "Notepad++.Notepad++",
    "NSIS": "NSIS.NSIS",
    "NTLite": "Nlitesoft.NTLite",
    "NVM": "CoreyButler.NVMforWindows",
    "Obsidian": "Obsidian.Obsidian",
    "OBSStudio": "OBSProject.OBSStudio",
    "OhMyPosh": "JanDeDobbeleer.OhMyPosh",
    "OneDrive": "Microsoft.OneDrive",
    "PhysX": "Nvidia.PhysX",
    "Postman": "Postman.Postman",
    "PowerToys": "Microsoft.PowerToys",
    "PuTTY": "PuTTY.PuTTY",
    "Python": "Python.Python.3.14",
    "QEMUGuestAgent": "RedHat.QemuGA",
    "RockstarGamesLauncher": "RockstarGames.Launcher",
    "Rustup": "Rustlang.Rustup",
    "SevenZip": "7zip.7zip",
    "ShareX": "ShareX.ShareX",
    "Spotify": "Spotify.Spotify",
    "Steam": "Valve.Steam",
    "Sunshine": "LizardByte.Sunshine",
    "TelegramDesktop": "Telegram.TelegramDesktop",
    "UbisoftConnect": "Ubisoft.Connect",
    "Unity": "Unity.Unity.2020",
    "UnityHub": "Unity.UnityHub",
    "ViGEmBus": "Nefarius.ViGEmBus",
    "VisualStudioCode": "Microsoft.VisualStudioCode",
    "VisualStudioCommunity2026": "Microsoft.VisualStudio.Community",
    "VLC": "VideoLAN.VLC",
    "WinSCP": "WinSCP.WinSCP",
}


def _check_antigravity_ide_upstream() -> tuple[str, dict[str, str]] | None:
    """Scrape https://antigravity.google/download for the latest stable Windows x64/arm64 URLs."""
    from txa.core import net

    try:
        resp = net.session().get("https://antigravity.google/download", timeout=15)
        if resp.status_code != 200:
            return None
        text = resp.text
        m_x64 = re.search(
            r"(https://edgedl\.me\.gvt1\.com/edgedl/release2/[^\"'\s]+/antigravity/stable/([0-9]+\.[0-9]+\.[0-9]+)-[0-9]+/windows-x64/Antigravity%20IDE\.exe)",
            text,
        )
        m_arm64 = re.search(
            r"(https://edgedl\.me\.gvt1\.com/edgedl/release2/[^\"'\s]+/antigravity/stable/[0-9]+\.[0-9]+\.[0-9]+-[0-9]+/windows-arm64/Antigravity%20IDE\.exe)",
            text,
        )
        if not m_x64:
            return None
        ver = normalize_version(m_x64.group(2))
        urls = {"x64": m_x64.group(1)}
        if m_arm64:
            urls["arm64"] = m_arm64.group(1)
        return ver, urls
    except Exception:
        return None


def sync_txavl_packages(
    repo_root,
    namespace: str = "TXAVL",
    keep_old: bool = False,
    dry_run: bool = False,
    only_filter: str | None = None,
) -> dict[str, Any]:
    """Automatically check and update all managed ``TXAVL`` packages in ``repo_root`` to their latest upstream version.

    Skips hand-written packages and any package outside ``namespace`` so community/manual manifests are untouched.
    """
    import shutil
    import tempfile
    from pathlib import Path
    from txa.core import console, net, semver
    from txa.core.manifest import Bundle
    from txa.create.draft import Draft, TargetDraft

    root = Path(repo_root)
    ns_dir = root / "manifests" / namespace[0].lower() / namespace
    updated: list[str] = []
    up_to_date: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    if not ns_dir.is_dir():
        return {"updated": updated, "up_to_date": up_to_date, "skipped": skipped, "failed": failed}

    for app_dir in sorted(ns_dir.iterdir(), key=lambda p: p.name.lower()):
        if not app_dir.is_dir() or app_dir.name.startswith("."):
            continue
        app_name = app_dir.name
        pkg_id = f"{namespace}.{app_name}"
        if only_filter and only_filter.lower() not in (app_name.lower(), pkg_id.lower()):
            continue

        ver_dirs = [d for d in app_dir.iterdir() if d.is_dir() and semver.is_valid(d.name)]
        if not ver_dirs:
            continue
        ver_dirs.sort(key=lambda d: semver.parse(d.name))
        latest_dir = ver_dirs[-1]
        current_ver = latest_dir.name

        core_path = latest_dir / "core.txa.yaml"
        raw_core = core_path.read_text("utf-8") if core_path.is_file() else ""
        if app_name in _HANDWRITTEN_APPS or "hand-written" in raw_core.lower() or "auto-update: false" in raw_core.lower():
            console.say(f"  {console.paint('[SKIP]', 'yellow')} {pkg_id}@{current_ver} (hand-written / pinned)")
            skipped.append(pkg_id)
            continue

        bundle = Bundle.read(latest_dir)
        prev_core = bundle.core or {}
        prev_about = bundle.default_about() or {}
        prev_pkg = prev_core.get("package") or {}

        # Special handler for AntigravityIDE (direct from antigravity.google/download)
        if app_name == "AntigravityIDE":
            ag = _check_antigravity_ide_upstream()
            if not ag:
                skipped.append(pkg_id)
                continue
            new_ver, ag_urls = ag
            if semver.parse(new_ver) <= semver.parse(current_ver):
                console.say(f"  {console.paint('[OK]', 'gray')}   {pkg_id}@{current_ver}")
                up_to_date.append(pkg_id)
                continue
            console.say(f"  {console.paint('[UP]', 'green', 'bold')}   {pkg_id}: {current_ver} -> {new_ver}")
            if not dry_run:
                work = Path(tempfile.mkdtemp(prefix="ag-sync-", dir=config.temp_root()))
                targets: list[TargetDraft] = []
                for arch, url in ag_urls.items():
                    dl = net.download(net.session(), url, work / f"ag-{arch}.exe", 4 * 1024 * 1024 * 1024)
                    targets.append(TargetDraft(
                        url=url,
                        arch=arch,
                        engine="inno",
                        sha256=dl.sha256,
                        size=1,
                        payload=Path(""),
                        switches=dict(DEFAULT_SWITCHES["inno"]),
                        portable={},
                    ))
                lic = prev_about.get("license") or {}
                draft = Draft(
                    package_id=pkg_id,
                    version=new_ver,
                    name=prev_about.get("name", "Antigravity IDE"),
                    publisher=prev_about.get("publisher", "Google"),
                    author=prev_about.get("author", "Google LLC"),
                    summary=prev_about.get("summary", ""),
                    description=prev_about.get("description"),
                    homepage=prev_about.get("homepage"),
                    license_name=lic.get("name", "Proprietary"),
                    license_url=lic.get("url"),
                    alias=prev_pkg.get("alias"),
                    aliases=prev_pkg.get("aliases", []),
                    tags=prev_core.get("tags", []),
                    targets=targets,
                )
                save_draft_manifests(draft, root, dry_run=False)
                if not keep_old:
                    for old_d in ver_dirs:
                        if old_d.name != new_ver:
                            shutil.rmtree(old_d, ignore_errors=True)
            updated.append(f"{pkg_id} ({current_ver} -> {new_ver})")
            continue

        # Standard WinGet-backed TXAVL package
        wg_id = _TXAVL_WINGET_MAP.get(app_name) or resolve_to_winget_id(prev_about.get("name") or app_name)
        if not wg_id:
            console.say(f"  {console.paint('[SKIP]', 'yellow')} {pkg_id}@{current_ver} (not on WinGet)")
            skipped.append(pkg_id)
            continue

        data = query_winget_package(wg_id)
        if not data:
            console.say(f"  {console.paint('[SKIP]', 'yellow')} {pkg_id}@{current_ver} (no HTTPS installer on WinGet)")
            skipped.append(pkg_id)
            continue

        new_ver = normalize_version(str(data.get("Version") or current_ver))
        if semver.parse(new_ver) <= semver.parse(current_ver):
            console.say(f"  {console.paint('[OK]', 'gray')}   {pkg_id}@{current_ver}")
            up_to_date.append(pkg_id)
            continue

        draft = convert_winget_to_draft(data, namespace=namespace, override_id=pkg_id)
        # Preserve curated metadata from the existing TXAVL manifest
        if prev_pkg.get("alias"):
            draft.alias = prev_pkg["alias"]
        if prev_pkg.get("aliases"):
            draft.aliases = list(prev_pkg["aliases"])
        if prev_core.get("tags"):
            draft.tags = list(prev_core["tags"])
        if prev_about.get("name"):
            draft.name = prev_about["name"]
        if prev_about.get("summary"):
            draft.summary = prev_about["summary"]
        if prev_about.get("description"):
            draft.description = prev_about["description"]
        if prev_about.get("homepage"):
            draft.homepage = prev_about["homepage"]
        prev_lic = prev_about.get("license") or {}
        if prev_lic.get("name"):
            draft.license_name = prev_lic["name"]
            draft.license_url = prev_lic.get("url")

        errs = validate_draft(draft)
        if errs:
            console.say(f"  {console.paint('[FAIL]', 'red')} {pkg_id}@{new_ver}: {'; '.join(errs)}")
            failed.append(pkg_id)
            continue

        console.say(f"  {console.paint('[UP]', 'green', 'bold')}   {pkg_id}: {current_ver} -> {new_ver} (from {wg_id})")
        save_draft_manifests(draft, root, dry_run=dry_run)
        if not dry_run and not keep_old:
            for old_d in ver_dirs:
                if old_d.name != new_ver:
                    shutil.rmtree(old_d, ignore_errors=True)
        updated.append(f"{pkg_id} ({current_ver} -> {new_ver})")

    return {"updated": updated, "up_to_date": up_to_date, "skipped": skipped, "failed": failed}


