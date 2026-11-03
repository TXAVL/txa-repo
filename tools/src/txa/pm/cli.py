"""txapm - install and manage packages from the TXA repository.

    txapm install <id|alias> [--version X.Y.Z] [--arch x64] [--progress|--interactive] [--ignore-checksum]
    txapm upgrade [<id>] [--all]       txapm uninstall <id>
    txapm list [--upgrade-available]   txapm show <id>      txapm search <text>
    txapm export <file>                txapm import <file>
    txapm pin add|remove|list [<id>]   txapm download <id> [-d dir]
    txapm list --all                   txapm source list|add|remove|enable|disable|update|reset
    txapm winget|wg <search|install|import|scan> [...]
    txapm doctor                       txapm clean [--all|--logs]
    txapm log [<id>] [-n 50]           txapm which <id>
    txapm lang [en|vi]                 txapm help [<command>]
    txapm --info                       txapm hash <file|url>     txapm validate <folder>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from txa import __version__
from txa.core import config, console, net, retention, semver, winos
from txa.pm import installer, uninstall
from txa.pm.installer import InstallError
from txa.pm.source import LocalRelease, NotFound, Source, SourceError, Sources, check_url


P = console.paint  # colour a string
C = console.cell   # pad to a column width, then colour


def _die(message: str) -> int:
    console.error("txapm", message)
    return 1


def _about(cards: dict, package_id: str = "") -> dict:
    from txa.core import i18n

    abouts = cards.get("about") or {}
    default_loc = (cards.get("core") or {}).get("locale", {}).get("default")
    if i18n.is_vi():
        chosen = abouts.get("vi-VN") or abouts.get("vi") or abouts.get(default_loc) or next(iter(abouts.values()))
    else:
        chosen = abouts.get("en-US") or abouts.get("en") or abouts.get(default_loc) or next(iter(abouts.values()))
    result = dict(chosen)
    summaries_map = {loc: ab.get("summary", "") for loc, ab in abouts.items() if isinstance(ab, dict) and ab.get("summary")}
    result["summary"] = i18n.localize_summary(package_id, result.get("summary", ""), summaries_map)
    return result


def _pick(args, query: str) -> tuple[Source, str]:
    """(source, package id) honouring --source; refuses ids that exist in several sources."""
    return Sources(getattr(args, "source", None)).resolve(query)


_WAITING = {
    "awaiting-review": "waiting for a Contributor/moderator to review and approve it",
    "approved": "approved and about to be merged - it appears in the library in a few minutes",
    "validating": "the automatic checks are still running",
    "needs-confirmation": "the author has not yet ticked the pull request checklist",
    "fix-required": "changes are needed (a check failed or a moderator asked for changes) - the author has to update the pull request",
}


def _waiting_text(entry: dict) -> str:
    return _WAITING.get(entry.get("status"), "waiting for review")


def _refuse_pending(source: Source, entry: dict) -> int:
    safe = console.safe
    console.error("txapm", f"{safe(entry['id'])} {safe(entry['version'])} cannot be installed yet - {_waiting_text(entry)}.")
    console.say(f"  {console.label('pull request', 14)}{P(safe(entry['url']), 'cyan')}  (#{safe(entry['pr'])}, by {safe(entry.get('by', '?'))})")
    console.say("  A package is installable only after a Contributor approves its pull request and it is merged into the library.")
    return 1


def _pending_for_install(args, query: str, version: str | None) -> tuple[Source, dict] | None:
    """The waiting entry to refuse instead of failing with 'not found' (or None when the request can go ahead)."""
    try:
        sources = Sources(getattr(args, "source", None))
        found = sources.find_pending(query, version)
        if not found:
            return None
        source, entry = found
        published = source.find(query)
        if published and not version:
            return None  # the published version installs normally; only an explicit pending version is refused
        if published and entry["version"] in source.versions(published):
            return None
        return found
    except (SourceError, NotFound, net.NetError):
        return None


def _source_of(record: dict | None) -> Source:
    name = (record or {}).get("source") or config.OFFICIAL_SOURCE
    try:
        return Sources(name).items[0]
    except SourceError:
        return Source()


def _install(src: Source, package_id: str, version: str | None, args, header: str | None = None) -> int:
    """Resolve -> download -> verify -> install -> record, announcing each phase as [n/N]."""
    started = time.monotonic()
    download_only = getattr(args, "download_only", False)
    total = 3 if download_only else 5
    if header:
        print(f"\n{P(header, 'bold', 'magenta')}")

    # [1] resolve
    version, cards = src.release(package_id, version)
    build, about = cards["build"], _about(cards)
    target = installer.pick_target(build, getattr(args, "arch", None))
    engine, scope = target["engine"], build.get("scope", "machine")
    origin = "" if src.name == config.OFFICIAL_SOURCE else f" from source {P(src.name, 'magenta')}"
    fallback = P(" (via GitHub fallback)", "gray") if src.used_fallback else ""
    console.stage(1, total, f"Resolved {P(about['name'], 'bold')} {P(version, 'green', 'bold')} "
                            f"{P('(' + package_id + ')', 'gray')} · {target['arch']} · {P(engine, 'magenta')}{origin}{fallback}")
    if not download_only and not getattr(args, "skip_os_check", False):
        installer.check_os(build)
    current = winos.current()
    if current:
        console.say(f"      {P('Windows', 'gray')} needs {build['platform']['min_build']}+, this PC runs {winos.fmt(current)}")
    previous = installer.installed().get(package_id)
    if previous and previous["version"] == version and not getattr(args, "force", False) and not download_only:
        console.say(f"✓ {package_id} {version} is already installed (use --force to reinstall)")
        return 0

    # [2] download
    size = target["source"].get("size")
    file_name = target["source"]["url"].split("?", 1)[0].rsplit("/", 1)[-1]
    host = target["source"]["url"].split("/")[2]
    size_tag = P(f" ({console.human_size(size)})", "gray") if (size and size > 1) else ""
    console.stage(2, total, f"Downloading {P(file_name, 'bold')}{size_tag} from {P(host, 'cyan')}")
    result = installer.download_payload(package_id, version, target, console.progress("      "), source=src)
    console.done_line()

    # [3] verify
    try:
        digest = installer.verify_payload(result, target, ignore_checksum=getattr(args, "ignore_checksum", False))
    except InstallError as exc:
        console.stage(3, total, P("Verifying SHA-256", "red", "bold"))
        return _die(str(exc))
    signer = getattr(result, "verified_signer", None)
    if signer:
        console.stage(3, total, f"Verified SHA-256 {P(digest[:16] + '…', 'gray')} {P(f'Authenticode signed by {signer} (evergreen installer)', 'green')}")
    else:
        console.stage(3, total, f"Verified SHA-256 {P(digest[:16] + '…', 'gray')} {P('matches the manifest', 'green')}")
    payload = result.path
    if download_only:
        console.say(f"✓ saved to {payload}")
        return 0

    # [4] install
    from txa.core import i18n

    extra: dict = {}
    if engine == "portable":
        console.stage(4, total, "Unpacking the portable archive and adding it to PATH")
        bar = console.progress("      ")
        try:
            extra = installer.install_portable(package_id, version, target, payload, bar)
        finally:
            console.done_line()
        code, meaning = 0, i18n.translate("unpacked")
        scope = "user"
        payload.unlink(missing_ok=True)
        print(f"      {P('folder', 'gray')} {extra['dir']}")
        for directory in extra["path_dirs"]:
            print(f"      {P('PATH  ', 'gray')} {directory}")
    else:
        mode = "interactive" if getattr(args, "interactive", False) else "progress" if getattr(args, "progress", False) else "silent"
        log = config.txa_home() / "logs" / f"{package_id}-{version}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        executable, params = installer.build_command(target, payload, mode, log)
        elevate = scope == "machine"
        needs_uac = elevate and not installer.is_admin()
        console.stage(4, total, f"Running the {P(engine, 'magenta')} installer ({mode})"
                                f"{P(' - approve the UAC prompt', 'yellow') if needs_uac else ''}")
        with console.working("installing…" if mode != "interactive" else "waiting for the installer window…", "      ") as busy:
            code = installer.run(executable, params, elevate)
        meaning = i18n.translate(installer.EXIT_CODES.get(code, "see the installer log"))
        if code not in set(target.get("success_codes") or []) | installer.SUCCESS:
            return _die(f"installer exited with {code}: {meaning} (log: {log})")
        console.say(f"      {P('finished in ' + console.human_time(busy.elapsed), 'gray')} · exit code {code} ({meaning})")

    # [5] record
    installer.record(package_id, version, target, code, about["name"], scope, src.name, extra)
    console.stage(5, total, "Recorded in the TXA install list")
    console.say(f"✓ {P(about['name'], 'bold')} {P(version, 'green', 'bold')} installed in "
                f"{console.human_time(time.monotonic() - started)} ({meaning})")
    if engine == "portable":
        console.say(P("  Open a new terminal so the updated PATH is picked up.", "yellow"))
    return 0


def _available(records: dict) -> dict[str, str]:
    """package id -> newer version published in the source each package was installed from."""
    latest: dict[str, dict[str, str]] = {}
    out = {}
    for package_id, info in records.items():
        name = info.get("source") or config.OFFICIAL_SOURCE
        if name not in latest:
            try:
                latest[name] = {p["id"]: p["latest"] for p in _source_of(info).index().get("packages", [])}
            except Exception:  # source offline: no upgrade info for its packages
                latest[name] = {}
        newest = latest[name].get(package_id)
        if newest and semver.is_valid(info["version"]) and semver.parse(newest) > semver.parse(info["version"]):
            out[package_id] = newest
    return out


# --------------------------------------------------------------------------- commands


def cmd_install(args) -> int:
    if args.manifest:
        # Test a manifest folder before submitting it: same checks, same download + SHA-256 + install path.
        from txa.ci.context import init_local
        from txa.ci.report import quick_check

        folder = Path(args.manifest)
        local = LocalRelease(folder)
        console.say(f"→ installing {P(local.package_id, 'bold')} {local.bundle.version} from the local manifest {P(str(folder), 'cyan')}")
        report = quick_check(init_local([folder], offline=True), quiet=True)
        if report["verdict"] == "fail":
            for row in report["results"]:
                for message in row["messages"]:
                    if message["level"] == "fail":
                        console.say(f"✗ STEP {row['step']:02d}: {message['text']}")
            return _die("the manifest has problems - fix them first (txacreate validate <folder>)")
        return _install(local, local.package_id, local.bundle.version, args)
    if not args.package:
        return _die("which package? use `txapm install <id>` or `txapm install --manifest <folder>`")
    waiting = _pending_for_install(args, args.package, args.version)
    if waiting:
        return _refuse_pending(*waiting)
    src, package_id = _pick(args, args.package)
    if getattr(args, "choose", False) and not args.version:
        chosen = _choose_version(src, package_id)
        if chosen is None:
            return 1
        args.version = chosen
    return _install(src, package_id, args.version, args)


def cmd_upgrade(args) -> int:
    records = installer.installed()
    if args.package:
        package_id = next((k for k in records if k.lower() == args.package.lower()), None) \
            or _pick(args, args.package)[1]
        if package_id not in records:
            return _die(f"{package_id} was not installed with txapm - use `txapm install`")
        if package_id in installer.pins() and not args.include_pinned:
            return _die(f"{package_id} is pinned - use --include-pinned or `txapm pin remove {package_id}`")
        todo = {package_id: _available({package_id: records[package_id]}).get(package_id)}
        if not todo[package_id]:
            console.say(f"✓ {package_id} {records[package_id]['version']} is up to date")
            return 0
    else:
        todo = _available(records)
        pinned = installer.pins()
        for package_id in sorted(k for k in list(todo) if k in pinned and not args.include_pinned):
            todo.pop(package_id)
            console.say(f"! {package_id} is pinned at {pinned[package_id]} - skipped (txapm pin remove {package_id})")
        if not todo:
            console.say("✓ everything is up to date")
            return 0
        for package_id, newest in sorted(todo.items()):
            print(f"  {C(package_id, 40, 'bold')} {C(records[package_id]['version'], 10, 'gray')} "
                  f"{P('→', 'cyan')} {P(newest, 'green', 'bold')}")
        if not args.all:
            console.say(f"! {len(todo)} upgrade(s) available - run {P('txapm upgrade --all', 'bold')} to apply")
            return 0
    failures = 0
    items = sorted(todo.items())
    for index, (package_id, newest) in enumerate(items, 1):
        args.arch = args.arch or records[package_id].get("arch")
        header = f"── {index}/{len(items)}  {package_id}  {records[package_id]['version']} → {newest}"
        try:
            failures += _install(_source_of(records[package_id]), package_id, newest, args, header) != 0
        except (InstallError, NotFound, net.NetError) as exc:
            failures += 1
            _die(f"{package_id}: {exc}")
        args.arch = None
    if len(items) > 1:
        console.say(f"{'✓' if not failures else '!'} upgraded {len(items) - failures} of {len(items)} package(s)")
    return 1 if failures else 0


def cmd_uninstall(args) -> int:
    records = installer.installed()
    package_id = next((k for k in records if k.lower() == args.package.lower()), None)
    src = _source_of(records.get(package_id)) if package_id else None
    if not package_id:
        src, package_id = _pick(args, args.package)
    record = records.get(package_id)
    name = (record or {}).get("name")
    engine = (record or {}).get("engine", "exe")
    scope = (record or {}).get("scope", "machine")
    if not name:
        _, cards = src.release(package_id)
        name, engine = _about(cards)["name"], installer.pick_target(cards["build"])["engine"]
        scope = cards["build"].get("scope", "machine")
    started = time.monotonic()
    if engine == "portable":
        console.stage(1, 2, f"Removing {P(name, 'bold')} from the user PATH")
        with console.working("deleting its folder…", "      "):
            folder = installer.uninstall_portable(package_id)
        console.stage(2, 2, f"Deleted {folder}" if folder else "Nothing left on disk")
        installer.forget(package_id)
        console.say(f"✓ {package_id} uninstalled in {console.human_time(time.monotonic() - started)}")
        return 0
    console.stage(1, 2, f"Looking for {P(name, 'bold')} in the installed programs")
    matches = uninstall.find(name, uninstall.installed_programs())
    if not matches:
        return _die(f"'{name}' is not in the list of installed programs")
    if len(matches) > 1 and not args.all_matches:
        listing = ", ".join(f"{m.name} {m.version or ''}".strip() for m in matches)
        return _die(f"several programs match '{name}': {listing} (use --all-matches)")
    for program in matches:
        executable, params = uninstall.split_command(uninstall.command(program, engine, args.interactive))
        console.stage(2, 2, f"Running the uninstaller for {P((program.name + ' ' + (program.version or '')).strip(), 'bold')}"
                            f"{P(' - approve the UAC prompt', 'yellow') if scope == 'machine' and not installer.is_admin() else ''}")
        with console.working("uninstalling…", "      "):
            code = installer.run(executable, params, scope == "machine")
        if code not in installer.SUCCESS:
            return _die(f"uninstaller exited with {code}: {installer.EXIT_CODES.get(code, 'unknown error')}")
    installer.forget(package_id)
    console.say(f"✓ {package_id} uninstalled in {console.human_time(time.monotonic() - started)}")
    return 0


def cmd_list(args) -> int:
    if args.all:
        return _list_machine(args)
    records = installer.installed()
    if not records:
        console.say("! nothing installed through txapm yet - try `txapm search <name>`")
        return 0
    try:
        available = _available(records)
    except Exception:  # offline: still list what is installed
        available = {}
    rows = sorted(records.items())
    if args.upgrade_available:
        rows = [r for r in rows if r[0] in available]
    pinned = installer.pins()
    print(console.head(f"{'Id':<40} {'Version':<10} {'Available':<10} {'Arch':<6} {'Source':<10} Pin"))
    for package_id, info in rows:
        print(f"{C(package_id, 40, 'bold')} {C(info['version'], 10, 'green')} "
              f"{C(available.get(package_id, ''), 10, 'yellow', 'bold')} {C(info['arch'], 6, 'gray')} "
              f"{C(info.get('source', config.OFFICIAL_SOURCE), 10, 'magenta')} {P(pinned.get(package_id, ''), 'yellow')}")
    return 0


def _list_machine(args) -> int:
    """Every program Windows knows about; those also in TXA get an Id, Available and Source."""
    index: dict[str, tuple[str, dict]] = {}
    slug_index: dict[str, tuple[str, dict]] = {}
    for source in Sources().items:
        try:
            for entry in source.index().get("packages", []):
                pair = (source.name, entry)
                index.setdefault(entry["name"].lower(), pair)
                app_slug = re.sub(r"[^a-z0-9]", "", entry["id"].split(".")[-1].lower())
                if app_slug:
                    slug_index.setdefault(app_slug, pair)
                if entry.get("alias"):
                    slug_index.setdefault(re.sub(r"[^a-z0-9]", "", entry["alias"].lower()), pair)
        except Exception:  # offline source: still list the machine
            continue
    rows = []
    for program in sorted(uninstall.installed_programs(), key=lambda p: p.name.lower()):
        if not program.name:
            continue
        lowered = program.name.lower()
        cleaned = re.sub(r"\s*\((?:user|machine|x64|x86|64-bit|32-bit|remove only)\)\s*", " ", lowered).strip()
        cleaned = re.sub(r"\s+(?:version\s+)?v?\d+(?:\.\d+)+.*$", "", cleaned).strip()
        collapsed = re.sub(r"[^a-z0-9]", "", cleaned)
        match = (
            index.get(lowered)
            or index.get(cleaned)
            or next((v for n, v in index.items() if lowered.startswith(n + " ") or cleaned.startswith(n + " ")), None)
            or (slug_index.get(collapsed) if len(collapsed) >= 3 else None)
        )
        origin, entry = match if match else ("", None)
        version = program.version or ""
        newest = ""
        if entry:
            current = semver.coerce(version) or version
            if semver.is_valid(current) and semver.parse(entry["latest"]) > semver.parse(current):
                newest = entry["latest"]
        if args.upgrade_available and not newest:
            continue
        rows.append((program.name[:38], entry["id"] if entry else "", version[:14], newest, origin))
    print(console.head(f"{'Name':<38} {'Id':<32} {'Version':<14} {'Available':<10} Source"))
    for name, package_id, version, newest, source in rows:
        known = bool(package_id)
        print(f"{C(name, 38, 'bold' if known else 'dim')} {C(package_id, 32, 'cyan')} {C(version, 14, 'green' if known else 'gray')} "
              f"{C(newest, 10, 'yellow', 'bold')} {P(source, 'magenta')}")
    console.say(f"{P(str(len(rows)), 'bold')} program(s)")
    return 0


def cmd_pin(args) -> int:
    pinned = installer.pins()
    if args.action == "list":
        if not pinned:
            console.say("! no pins")
        for package_id, version in sorted(pinned.items()):
            print(f"{C(package_id, 40, 'bold')} {P(version, 'yellow')}")
        return 0
    if not args.package:
        return _die(f"pin {args.action} needs a package id")
    package_id = _pick(args, args.package)[1]
    if args.action == "remove":
        installer.set_pin(package_id, None)
        console.say(f"✓ {package_id} unpinned")
        return 0
    version = args.version or (installer.installed().get(package_id) or {}).get("version") or "*"
    installer.set_pin(package_id, version)
    console.say(f"✓ {package_id} pinned at {version} - `txapm upgrade --all` will skip it")
    return 0


def cmd_download(args) -> int:
    src, package_id = _pick(args, args.package)
    version, cards = src.release(package_id, args.version)
    target = installer.pick_target(cards["build"], args.arch)
    payload = installer.fetch(package_id, version, target, console.progress("download"), source=src)
    console.done_line()
    out = Path(args.dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    dest = out / payload.name
    shutil.copy2(payload, dest)
    manifest = out / f"{package_id}-{version}.txa.json"
    manifest.write_text(json.dumps({"version": version, **cards}, indent=2, ensure_ascii=False), "utf-8")
    console.say(f"✓ {dest} (SHA-256 verified)")
    console.say(f"✓ {manifest}")
    return 0


def cmd_source(args) -> int:
    items = config.sources()
    official_enabled = items[0]["enabled"]
    custom = items[1:]
    by_name = {i["name"].lower(): i for i in items}
    action, name = args.action, args.name
    if action in ("add", "remove", "enable", "disable") and not name:
        return _die(f"source {action} needs a name")
    if action == "add":
        if not args.url:
            return _die("usage: txapm source add <name> <url|folder> [--token-env VAR] [--allow-lan]")
        if name.lower() in by_name:
            return _die(f"a source named '{name}' already exists")
        if not name.replace("-", "").replace("_", "").isalnum():
            return _die("source names may only contain letters, digits, - and _")
        url = check_url(args.url)
        probe = Source(url, name=name, token_env=args.token_env, allow_lan=args.allow_lan, fallback=False)
        index = probe._get_json("index.json")
        if not index or index.get("api") != "txa.v1":
            return _die(f"{url} does not serve a txa.v1 index (expected {url}/index.json)")
        entry = {"name": name, "url": url}
        if args.token_env:
            entry["token_env"] = args.token_env
        if args.allow_lan:
            entry["allow_lan"] = True
        config.save_custom_sources([*custom, entry], official_enabled)
        console.say(f"✓ source '{name}' added - {index.get('count', 0)} package(s)")
    elif action == "remove":
        if name.lower() == config.OFFICIAL_SOURCE:
            return _die("the official source cannot be removed - use `txapm source disable txa`")
        if name.lower() not in by_name:
            return _die(f"no source named '{name}'")
        config.save_custom_sources([c for c in custom if c["name"].lower() != name.lower()], official_enabled)
        console.say(f"✓ source '{name}' removed")
    elif action in ("enable", "disable"):
        if name.lower() not in by_name:
            return _die(f"no source named '{name}'")
        flag = action == "enable"
        if name.lower() == config.OFFICIAL_SOURCE:
            config.save_custom_sources(custom, flag)
        else:
            config.save_custom_sources([{**c, "enabled": flag} if c["name"].lower() == name.lower() else c
                                        for c in custom], official_enabled)
        console.say(f"✓ source '{name}' {action}d")
    elif action == "reset":
        config.save_custom_sources([], True)
        cfg = config.load_config()
        cfg.pop("api", None)
        config.save_config(cfg)
        console.say("✓ sources reset to the official txa source only")
    elif action == "update":
        for source in Sources(name).items:
            try:
                console.say(f"✓ {source.name}: {source.index().get('count', 0)} package(s)")
            except Exception as exc:
                console.say(f"✗ {source.name}: {exc}")
        return 0
    elif action == "export":
        print(json.dumps([{k: v for k, v in i.items() if k != "official"} for i in custom], indent=2))
        return 0
    print(console.head(f"{'Name':<12} {'Enabled':<8} {'Argument':<58} Options"))
    for item in config.sources():
        options = ", ".join(filter(None, [
            "official" if item.get("official") else "",
            f"token from %{item['token_env']}%" if item.get("token_env") else "",
            "LAN allowed" if item.get("allow_lan") else "",
        ]))
        on = item.get("enabled", True)
        print(f"{C(item['name'], 12, 'bold', 'magenta')} {C('yes' if on else 'no', 8, 'green' if on else 'red')} "
              f"{C(item['url'], 58, 'cyan')} {P(options, 'gray')}")
    return 0


def cmd_info() -> int:
    from txa.core import credentials, i18n

    record = credentials.stored() or {}
    current = winos.current()
    email = f" <{record['email']}>" if record.get("email") else ""
    enabled = [i["name"] for i in config.sources() if i.get("enabled", True)]
    cur_lang = config.lang()
    lang_label = "vi (Vietnamese)" if cur_lang == "vi" else "en (English)"
    rows = [
        ("windows", f"{winos.fmt(current) if current else '-'} · {winos.native_arch()}"),
        ("language", lang_label),
        ("sources", ", ".join(enabled) or i18n.translate("(none enabled)")),
        ("repository", str(config.get("upstream"))),
        ("home", str(config.txa_home())),
        ("downloads", str(config.temp_root())),
        ("logs", str(config.txa_home() / "logs")),
        ("installed", i18n.translate(f"{len(installer.installed())} package(s), {len(installer.pins())} pin(s)")),
        ("github", f"{record.get('login', '-')}{email}"),
    ]
    print(f"{P('txapm', 'bold', 'cyan')} {P(__version__, 'green', 'bold')}")
    for key, value in rows:
        print(f"{console.label(key, 12)}{value}")
    return 0


def cmd_hash(args) -> int:
    from txa.create.cli import main as create_main

    return create_main(["hash", args.target])


def cmd_validate(args) -> int:
    from txa.ci.cli import main as txaci_main

    return txaci_main(["validate", *args.paths, *(["--offline"] if args.offline else [])])


def _show_waiting(source: Source, entry: dict) -> None:
    from txa.core import i18n

    safe = console.safe
    print(f"{P(safe(entry['name']), 'bold', 'cyan')} {P(safe(entry['version']), 'yellow', 'bold')}  {P('(' + safe(entry['id']) + ')', 'gray')}"
          f"  {P('[source: ' + source.name + ']', 'magenta')}  {P('WAITING FOR REVIEW', 'yellow', 'bold')}")
    if entry.get("summary"):
        print(f"  {safe(i18n.localize_summary(entry.get('id', ''), entry['summary']))}")
    print(f"  {console.label('publisher')}{safe(entry.get('publisher') or '?')}   {P('submitted by', 'gray')} {safe(entry.get('by', '?'))}")
    print(f"  {console.label('status')}{_waiting_text(entry)}")
    print(f"  {console.label('pull request', 14)}{P(safe(entry['url']), 'cyan')}")
    console.say("! it cannot be installed until a Contributor approves the pull request")


def _version_rows(src: Source, package_id: str) -> list[dict]:
    """Every version kept in the repository, newest first, with the CPUs/languages it ships and whether it is installed."""
    versions = sorted(src.versions(package_id), key=lambda v: semver.parse(v) if semver.is_valid(v) else (0, 0, 0), reverse=True)
    installed = (installer.installed().get(package_id) or {}).get("version")
    rows = []
    for index, version in enumerate(versions):
        try:
            _, cards = src.release(package_id, version)
            targets = cards["build"]["targets"]
            ships = ", ".join(dict.fromkeys(t["arch"] + (f" {t['locale']}" if t.get("locale") else "") for t in targets))
        except Exception:  # noqa: BLE001 - a broken old release must not hide the others
            ships = "?"
        rows.append({"version": version, "latest": index == 0, "installed": version == installed, "ships": ships})
    return rows


def _print_versions(src: Source, package_id: str) -> None:
    rows = _version_rows(src, package_id)
    print(console.head(f"{package_id} - {len(rows)} version(s) in the repository (the newest {retention.KEEP} are kept)"))
    for row in rows:
        marks = " ".join(m for m, on in (("latest", row["latest"]), ("installed", row["installed"])) if on)
        print(f"  {C(row['version'], 14, 'green', 'bold')} {C(row['ships'], 28, 'yellow')} {P(marks, 'cyan')}")
    console.say(f"install one with {P('txapm install ' + package_id + ' --version <version>', 'bold')} or pick from a list with {P('--choose', 'bold')}")


def _choose_version(src: Source, package_id: str) -> str | None:
    rows = _version_rows(src, package_id)
    if len(rows) == 1:
        return rows[0]["version"]
    if not console._raw_available():
        _print_versions(src, package_id)
        _die("--choose needs an interactive terminal; pass --version <version> instead")
        return None
    options = [console.Option(r["version"], r["version"], " ".join(m for m, on in (("latest", r["latest"]), ("installed", r["installed"])) if on)
                              or r["ships"]) for r in rows]
    return console.choose(f"Which version of {package_id} do you want to install?", "version", options).value


def cmd_show(args) -> int:
    try:
        src, package_id = _pick(args, args.package)
        version, cards = src.release(package_id, args.version)
    except NotFound:
        waiting = Sources(getattr(args, "source", None)).find_pending(args.package, args.version)
        if not waiting:
            raise
        _show_waiting(*waiting)
        return 0
    build, about = cards["build"], _about(cards, package_id)
    if args.versions:
        _print_versions(src, package_id)
        return 0
    minimum = winos.parse_build(build["platform"]["min_build"])
    print(f"{P(about['name'], 'bold', 'cyan')} {P(version, 'green', 'bold')}  {P('(' + package_id + ')', 'gray')}"
          f"  {P('[source: ' + src.name + ']', 'magenta')}")
    print(f"  {about['summary']}")
    print(f"  {console.label('publisher')}{about['publisher']}   {P('author', 'gray')} {about['author']}")
    license_url = about["license"].get("url")
    print(f"  {console.label('license')}{about['license']['name']}" + (f"  {P(license_url, 'cyan')}" if license_url else ""))
    if about.get("homepage"):
        print(f"  {console.label('homepage')}{P(about['homepage'], 'cyan')}")
    print(f"  {console.label('windows')}{build['platform']['min_build']}+ ({winos.describe(minimum)}) · scope {build.get('scope', 'machine')}")
    for target in build["targets"]:
        arch_tag = P("[" + target["arch"] + (" " + target["locale"] if target.get("locale") else "") + "]", "yellow", "bold")
        engine_tag = P(target["engine"].ljust(5), "magenta")
        print(f"  {arch_tag} {engine_tag} {P(target['source']['url'], 'cyan')}")
        print(f"        {P('sha256', 'gray')} {target['source']['sha256']}")
    newer = src.find_pending(package_id)
    if newer and newer["version"] != version and (not semver.is_valid(newer["version"]) or semver.parse(newer["version"]) > semver.parse(version)):
        console.say(f"! version {console.safe(newer['version'])} is waiting for review ({console.safe(newer['url'])}) - not installable yet")
    return 0


def cmd_search(args) -> int:
    sources = Sources(args.source)
    hits = sources.search(args.text)
    waiting = sources.pending_matching(args.text)
    if not hits and not waiting:
        console.say(f"! no packages found for '{args.text}' - the repository may be empty or the name differs")
        suggestions = sources.suggest(args.text)
        if suggestions:
            styled = ", ".join(P(s, "green", "bold") for s in suggestions)
            console.say(f"  {P('→ Did you mean:', 'cyan', 'bold')} {styled}")
        if args.source:
            try:
                other_hits = Sources(None).search(args.text)
                if other_hits:
                    found_in = ", ".join(f"{h['id']} ({s.name})" for s, h in other_hits[:3])
                    console.say(f"  hint: found in other source(s): {P(found_in, 'cyan')} — omit '-s {args.source}' to search all sources")
            except Exception:
                pass
        return 1
    safe = console.safe
    if hits:
        from txa.core import i18n

        width = max(len(h["id"]) for _, h in hits)
        print(console.head(f"{'Id':<{width}}  {'Version':<10} {'Source':<10} Summary"))
        for source, hit in hits:
            loc_summary = i18n.localize_summary(hit["id"], hit.get("summary", ""), hit.get("summaries"))
            print(f"{C(safe(hit['id']), width, 'bold')}  {C(safe(hit['latest']), 10, 'green')} {C(source.name, 10, 'magenta')} {safe(loc_summary)}")
        console.say(f"{P(str(len(hits)), 'bold')} package(s) - install with {P('txapm install <Id>', 'bold')}")
    if waiting:
        width = max(len(e["id"]) for _, e in waiting)
        print()
        print(console.head(f"Waiting for review - cannot be installed yet"))
        for source, entry in waiting:
            print(f"{C(safe(entry['id']), width, 'bold')}  {C(safe(entry['version']), 10, 'yellow')} "
                  f"{C('PR #' + str(entry['pr']), 8, 'magenta')} {P(_waiting_text(entry), 'gray')}")
        console.say(f"{P(str(len(waiting)), 'bold')} package(s) need a Contributor to approve them first - see them with {P('txapm show <Id>', 'bold')}")
    return 0


def cmd_export(args) -> int:
    records = installer.installed()
    document = {
        "txa": 1, "kind": "export", "exported": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "packages": [{"id": k, "version": v["version"], "arch": v["arch"], "source": v.get("source", config.OFFICIAL_SOURCE)}
                     for k, v in sorted(records.items())],
    }
    Path(args.file).write_text(json.dumps(document, indent=2) + "\n", "utf-8")
    console.say(f"✓ exported {len(records)} package(s) to {args.file}")
    return 0


def cmd_import(args) -> int:
    try:
        document = json.loads(Path(args.file).read_text("utf-8"))
    except (OSError, ValueError) as exc:
        return _die(f"cannot read {args.file}: {exc}")
    if document.get("kind") != "export":
        return _die(f"{args.file} is not a txapm export file")
    failures = 0
    packages = document.get("packages", [])
    for index, item in enumerate(packages, 1):
        args.arch = item.get("arch")
        header = f"── {index}/{len(packages)}  {item['id']}"
        try:
            src = _source_of(item)
            failures += _install(src, item["id"], item["version"] if args.exact_versions else None, args, header) != 0
        except (InstallError, NotFound, SourceError, net.NetError) as exc:
            failures += 1
            console.error("txapm", f"{item['id']}: {exc}")
    console.say(f"{'✓' if not failures else '!'} import finished: {len(packages) - failures} of {len(packages)} installed, "
                f"{failures} failure(s)")
    return 1 if failures else 0


def cmd_clean(args) -> int:
    """Clean temporary installer downloads and optionally install logs."""
    freed = 0
    removed_files = 0
    targets = [("downloads", config.temp_root())]
    if getattr(args, "logs", False) or getattr(args, "all", False):
        targets.append(("logs", config.txa_home() / "logs"))

    for label, folder in targets:
        if not folder.is_dir():
            continue
        for item in list(folder.iterdir()):
            try:
                if item.is_file():
                    freed += item.stat().st_size
                    item.unlink(missing_ok=True)
                    removed_files += 1
                elif item.is_dir():
                    for sub in item.rglob("*"):
                        if sub.is_file():
                            freed += sub.stat().st_size
                            removed_files += 1
                    shutil.rmtree(item, ignore_errors=True)
            except OSError:
                continue
    console.say(f"✓ cleaned {removed_files} file(s) ({console.human_size(freed)} freed)")
    return 0


def cmd_log(args) -> int:
    """List or view installer logs from ~/.txa/logs."""
    log_dir = config.txa_home() / "logs"
    if not log_dir.is_dir():
        console.say("! no installer logs yet")
        return 0
    logs = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        console.say("! no installer logs yet")
        return 0
    if not args.package:
        print(console.head(f"{'Log File':<44} {'Size':<12} Modified"))
        for lg in logs[:25]:
            st = lg.stat()
            mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{C(lg.name, 44, 'cyan')} {C(console.human_size(st.st_size), 12, 'gray')} {mtime}")
        return 0
    q = args.package.lower()
    matched = next((lg for lg in logs if q in lg.name.lower()), None)
    if not matched:
        return _die(f"no log found matching '{args.package}'")
    print(console.paint(f"# {matched} ({console.human_size(matched.stat().st_size)})", "bold", "cyan"))
    lines = matched.read_text("utf-8", errors="replace").splitlines()
    tail = args.tail or 50
    for line in lines[-tail:]:
        print(line)
    return 0


def cmd_which(args) -> int:
    """Show installation details, paths, and logs for an installed package."""
    records = installer.installed()
    q = args.package.lower()
    pkg_id = next((k for k in records if k.lower() == q or k.split(".")[-1].lower() == q), None)
    if not pkg_id:
        return _die(f"'{args.package}' is not recorded as installed through txapm (try `txapm list --all`)")
    info = records[pkg_id]
    print(f"{P(info.get('name', pkg_id), 'bold', 'cyan')} {P(info['version'], 'green', 'bold')}  {P('(' + pkg_id + ')', 'gray')}")
    rows = [
        ("arch", info.get("arch", "-")),
        ("engine", info.get("engine", "-")),
        ("scope", info.get("scope", "machine")),
        ("source", info.get("source", config.OFFICIAL_SOURCE)),
        ("installed", info.get("installed", "-")),
    ]
    if info.get("dir"):
        rows.append(("folder", info["dir"]))
    if info.get("path_dirs"):
        rows.append(("PATH", ", ".join(info["path_dirs"])))
    log_file = config.txa_home() / "logs" / f"{pkg_id}-{info['version']}.log"
    if log_file.is_file():
        rows.append(("log", str(log_file)))
    for k, v in rows:
        print(f"  {console.label(k, 11)}{v}")
    return 0


def cmd_doctor(args) -> int:
    """Run health diagnostics on txapm, sources, WinGet, and local environment."""
    import subprocess
    from txa.core import credentials, i18n

    print(f"{P('TXA Doctor', 'bold', 'cyan')} · txapm {P(__version__, 'green', 'bold')}\n")
    current = winos.current()
    cur_lang = "Vietnamese (vi)" if i18n.is_vi() else "English (en)"
    console.say(f"  {P('✓', 'green')} Windows:     {winos.fmt(current) if current else 'unknown'} ({winos.native_arch()}) · admin={installer.is_admin()}")
    console.say(f"  {P('✓', 'green')} Language:    {P(cur_lang, 'cyan')} (change with `txapm lang`)")

    # Sources check
    for src_cfg in config.sources():
        if not src_cfg.get("enabled", True):
            console.say(f"  {P('-', 'gray')} Source '{src_cfg['name']}': disabled ({src_cfg['url']})")
            continue
        try:
            s = Sources(src_cfg["name"]).items[0]
            cnt = s.index().get("count", 0)
            console.say(f"  {P('✓', 'green')} Source '{P(src_cfg['name'], 'magenta')}': online · {P(str(cnt), 'bold')} package(s) ({src_cfg['url']})")
        except Exception as exc:
            console.say(f"  {P('✗', 'red')} Source '{src_cfg['name']}': error ({exc})")

    # WinGet check
    try:
        res = subprocess.run(["winget", "--version"], capture_output=True, text=True, timeout=5)
        wg_ver = res.stdout.strip() if res.returncode == 0 else None
    except Exception:
        wg_ver = None
    if wg_ver:
        console.say(f"  {P('✓', 'green')} WinGet CLI:  {wg_ver} (ready for `txacli` & `txapm winget`)")
    else:
        console.say(f"  {P('!', 'yellow')} WinGet CLI:  not found in PATH")

    # GitHub credentials
    rec = credentials.stored()
    if rec and rec.get("login"):
        console.say(f"  {P('✓', 'green')} GitHub Auth: signed in as {P(rec['login'], 'cyan')}")
    else:
        console.say(f"  {P('-', 'gray')} GitHub Auth: not signed in (optional; run `txacreate token --store` for PRs)")

    # Installed & cache stats
    records = installer.installed()
    temp_bytes = sum(f.stat().st_size for f in config.temp_root().rglob("*") if f.is_file()) if config.temp_root().is_dir() else 0
    console.say(f"  {P('✓', 'green')} Installed:   {len(records)} package(s) managed by txapm · {len(installer.pins())} pinned")
    console.say(f"  {P('✓', 'green')} Cache size:  {console.human_size(temp_bytes)} in {config.temp_root()} (clean with `txapm clean`)")
    return 0


def cmd_lang(args) -> int:
    """View or switch TXA display language (en / vi)."""
    if getattr(args, "code", None):
        chosen = config.set_lang(args.code)
    else:
        default_idx = 1 if config.lang() == "vi" else 0
        opts = [
            console.Option("en", "English", "Display all CLI messages in English"),
            console.Option("vi", "Vietnamese", "Translate all CLI messages into Vietnamese"),
        ]
        picked = console.choose("Language (use ↑/↓ or 1-2, Enter to confirm)", "lang", opts, default=default_idx)
        chosen = config.set_lang(str(picked.value))
    target_label = "Vietnamese (vi)" if chosen == "vi" else "English (en)"
    console.say(f"✓ Language set to {P(target_label, 'cyan', 'bold')}")
    return 0


def cmd_winget(args) -> int:
    """Search, install, scan, or import packages directly from WinGet inside txapm."""
    import tempfile
    from txa.cli import do_import, do_scan, do_search
    from txa.create import winget as wg

    action = (args.action or "").lower()
    rest = list(args.targets or [])

    if getattr(args, "search_query", None):
        return do_search(args.search_query)

    if action in ("search", "find", "s"):
        q = " ".join(rest).strip()
        if not q:
            return _die("usage: txapm winget search <query>")
        return do_search(q)

    if action in ("scan", "list", "ls"):
        do_scan()
        return 0

    if action in ("install", "add"):
        if not rest:
            return _die("usage: txapm winget install <package_name_or_winget_id>")
        failures = 0
        for query in rest:
            console.say(f"→ resolving '{P(query, 'cyan')}' from WinGet…")
            wg_id = wg.resolve_to_winget_id(query)
            if not wg_id:
                console.say(f"✗ could not find '{query}' on WinGet")
                failures += 1
                continue
            data = wg.query_winget_package(wg_id)
            if not data:
                console.say(f"✗ no supported HTTPS installer found for '{wg_id}'")
                failures += 1
                continue
            draft = wg.convert_winget_to_draft(data)
            work_root = Path(tempfile.mkdtemp(prefix="wg-install-", dir=config.temp_root()))
            rel_dir = wg.save_draft_manifests(draft, work_root)
            args.manifest = str(rel_dir)
            args.package = None
            args.version = None
            args.download_only = False
            failures += cmd_install(args) != 0
        return 1 if failures else 0

    if action in ("import", "in"):
        args.packages = rest
        return do_import(args)

    # If no explicit sub-action word was given, treat `action` as a package name to import (or scan if -i)
    if getattr(args, "from_installed", False):
        args.packages = ([ args.action ] if args.action else []) + rest
        return do_import(args)
    if args.action:
        args.packages = [args.action, *rest]
        return do_import(args)

    console.say("usage: txapm winget <search|install|import|scan> [args...]")
    return 0


# --------------------------------------------------------------------------- entry


def _install_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--arch", choices=["x64", "x86", "arm64"])
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--progress", action="store_true", help="unattended, but show the installer's progress UI")
    mode.add_argument("--interactive", action="store_true", help="run the normal installer UI")
    p.add_argument("--force", action="store_true", help="reinstall even if this version is recorded")
    p.add_argument("--ignore-checksum", action="store_true", help="bypass SHA-256 mismatch check")
    p.add_argument("--skip-os-check", action="store_true")


def main(argv: list[str] | None = None) -> int:
    console.setup()
    parser = console.SmartArgumentParser(
        prog="txapm",
        description="TXA package manager",
        epilog=(
            "examples:\n"
            "  txapm search chrome                  # search packages in TXA index\n"
            "  txapm install chrome                 # install by ID or short alias\n"
            "  txapm install chrome --ignore-checksum\n"
            "  txapm list --all                     # list all PC programs matched to TXA\n"
            "  txapm upgrade --all                  # upgrade all outdated packages\n"
            "  txapm uninstall TXAVL.Chrome         # silent uninstall\n"
            "  txapm wg search PowerToys            # search directly on WinGet\n"
            "  txapm wg install Microsoft.PowerToys # convert & install from WinGet\n"
            "  txapm wg -i                          # scan PC & import missing apps from WinGet\n"
            "  txapm doctor                         # check system, sources, WinGet & cache\n"
            "  txapm clean --all                    # clean temporary downloads & logs\n"
            "  txapm log chrome                     # view latest installer log\n"
            "  txapm which chrome                   # show install record, scope & paths\n"
            "  txapm lang vi                        # switch CLI language (en / vi)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"txapm {__version__}")
    parser.add_argument("--info", action="store_true", help="show version, paths, source and account")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("install", aliases=["add"], help="download, verify and silently install a package")
    p.add_argument("-s", "--source", help="only look in this source (see `txapm source list`)")
    p.add_argument("package", nargs="?", help="package id (TXAVL.HelloTool) or alias")
    p.add_argument("--manifest", metavar="FOLDER", help="install from a local manifest folder (to test it before submitting)")
    p.add_argument("--version", dest="version", help="install this X.Y.Z instead of the newest")
    p.add_argument("--choose", action="store_true", help="pick the version from the list of versions in the repository")
    p.add_argument("--download-only", action="store_true", help="stop after downloading and verifying")
    _install_options(p)
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("upgrade", aliases=["update"], help="upgrade one package, or list/apply all upgrades")
    p.add_argument("-s", "--source", help="only look in this source (see `txapm source list`)")
    p.add_argument("package", nargs="?")
    p.add_argument("--all", action="store_true", help="upgrade every package with a newer version")
    p.add_argument("--include-pinned", action="store_true", help="also upgrade pinned packages")
    _install_options(p)
    p.set_defaults(func=cmd_upgrade)

    p = sub.add_parser("uninstall", aliases=["remove", "rm"], help="silently uninstall a package")
    p.add_argument("-s", "--source", help="only look in this source (see `txapm source list`)")
    p.add_argument("package")
    p.add_argument("--interactive", action="store_true", help="run the normal uninstaller UI")
    p.add_argument("--all-matches", action="store_true", help="remove every program matching the name")
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("list", aliases=["ls"], help="packages installed through txapm (--all: every program)")
    p.add_argument("--upgrade-available", action="store_true", help="only packages with a newer version")
    p.add_argument("--all", action="store_true", help="every installed program on this PC, matched against TXA")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", aliases=["view"], help="show package details")
    p.add_argument("-s", "--source", help="only look in this source (see `txapm source list`)")
    p.add_argument("package")
    p.add_argument("--version", dest="version")
    p.add_argument("--versions", action="store_true", help="list every published version")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("search", aliases=["find"], help="search the package index")
    p.add_argument("-s", "--source", help="only look in this source (see `txapm source list`)")
    p.add_argument("text")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("export", help="save the list of installed packages to a JSON file")
    p.add_argument("file")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import", help="install every package from an export file")
    p.add_argument("file")
    p.add_argument("--exact-versions", action="store_true", help="install the exported versions, not the newest")
    _install_options(p)
    p.set_defaults(func=cmd_import, download_only=False)

    p = sub.add_parser("pin", help="hold a package at its version so upgrade --all skips it")
    p.add_argument("-s", "--source", help="only look in this source (see `txapm source list`)")
    p.add_argument("action", choices=["add", "remove", "list"])
    p.add_argument("package", nargs="?")
    p.add_argument("--version", dest="version", help="pin to this version (default: installed version)")
    p.set_defaults(func=cmd_pin)

    p = sub.add_parser("download", help="download and verify an installer plus its manifest into a folder")
    p.add_argument("-s", "--source", help="only look in this source (see `txapm source list`)")
    p.add_argument("package")
    p.add_argument("--version", dest="version")
    p.add_argument("--arch", choices=["x64", "x86", "arm64"])
    p.add_argument("-d", "--dir", default=str(Path.home() / "Downloads"), help="target folder (default Downloads)")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("source", help="manage package sources: list, add, remove, enable, disable, update, reset")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "add", "remove", "enable", "disable", "update", "reset", "export"])
    p.add_argument("name", nargs="?", help="source name")
    p.add_argument("url", nargs="?", help="https:// URL serving txa.v1, or a local folder with manifests/")
    p.add_argument("--token-env", help="environment variable holding a bearer token for a private source")
    p.add_argument("--allow-lan", action="store_true", help="allow installers on private/LAN addresses")
    p.set_defaults(func=cmd_source)

    p = sub.add_parser("hash", help="SHA-256, engine and architecture of an installer file or URL")
    p.add_argument("target")
    p.set_defaults(func=cmd_hash)

    p = sub.add_parser("validate", help="run the repository bot checks on a local manifest folder")
    p.add_argument("paths", nargs="+")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("winget", aliases=["wg"], help="search, install, scan, or import packages from WinGet")
    p.add_argument("action", nargs="?", help="search | install | import | scan (or package name)")
    p.add_argument("targets", nargs="*", help="query or package names/IDs")
    p.add_argument("-s", "--search", dest="search_query", help="search WinGet for matching packages")
    p.add_argument("-i", "--from-installed", action="store_true", help="scan installed PC apps and import missing ones")
    p.add_argument("-o", "--out", default=None, help="output repo directory for import")
    p.add_argument("--build-api", action="store_true", help="build static txa.v1 REST API after import")
    p.add_argument("--api-out", default="dist/api", help="destination folder for built API")
    p.add_argument("--add-source", metavar="NAME", help="register output repo as a txapm source")
    p.add_argument("--submit", action="store_true", help="open a pull request after importing")
    p.add_argument("--dry-run", action="store_true", help="preview generated manifests without writing")
    p.add_argument("-y", "--yes", action="store_true", help="do not prompt when importing")
    _install_options(p)
    p.set_defaults(func=cmd_winget)

    p = sub.add_parser("clean", aliases=["cache", "clear"], help="clean temporary installer downloads and logs")
    p.add_argument("--logs", action="store_true", help="also delete installer log files")
    p.add_argument("--all", action="store_true", help="delete both cached downloads and logs")
    p.set_defaults(func=cmd_clean)

    p = sub.add_parser("log", aliases=["logs"], help="list or view installer logs")
    p.add_argument("package", nargs="?", help="package id or name to view its latest log")
    p.add_argument("-n", "--tail", type=int, default=50, help="number of lines to show (default: 50)")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("which", aliases=["where"], help="show local installation path, scope, and record of a package")
    p.add_argument("package", help="package id or short name")
    p.set_defaults(func=cmd_which)

    p = sub.add_parser("doctor", aliases=["check", "status"], help="check system health, sources, WinGet, and cache")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("lang", aliases=["language"], help="view or switch display language (en / vi)")
    p.add_argument("code", nargs="?", choices=["en", "vi"], help="en (English) or vi (Vietnamese)")
    p.set_defaults(func=cmd_lang)

    p = sub.add_parser("help", help="show help for txapm or a specific command")
    p.add_argument("topic", nargs="?", help="command name")

    args = parser.parse_args(argv)
    if args.info:
        return cmd_info()
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except NotFound as exc:
        rc = _die(str(exc))
        pkg_arg = getattr(args, "package", None)
        if pkg_arg:
            try:
                suggestions = Sources(getattr(args, "source", None)).suggest(pkg_arg)
                if suggestions:
                    styled = ", ".join(P(s, "green", "bold") for s in suggestions)
                    console.say(f"  {P('→ Did you mean:', 'cyan', 'bold')} {styled}")
            except Exception:
                pass
        return rc
    except Exception as exc:
        from txa.core.github import GitHubError
        from txa.core.manifest import ManifestError

        if isinstance(exc, (InstallError, SourceError, net.NetError, GitHubError, ManifestError)):
            return _die(str(exc))
        raise
    except KeyboardInterrupt:
        return _die("cancelled")


if __name__ == "__main__":
    sys.exit(main())
