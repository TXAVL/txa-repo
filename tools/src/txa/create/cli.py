"""txacreate - publish installers to txa-repo through a pull request.

    txacreate new <url> [<url> ...]        analyse, write cards, pre-flight, then fork + branch + commit + PR
                                           (GitHub access is requested only at the fork step)
    txacreate new <url> --dry-run          only write the cards to ./txa-out
    txacreate update <id> <url> [...]      new version of an existing package, metadata carried over
    txacreate hash <file|url>              SHA-256 + engine + architecture of an installer
    txacreate submit <folder>              PR for a hand-written release folder
    txacreate show <id>                    print the published cards of a package
    txacreate token [--store [-t PAT]] [--clear]   optional: pre-authorize, or forget, GitHub access
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import webbrowser
from pathlib import Path

from txa import __version__
from txa.ci import steps
from txa.ci.context import init_local
from txa.ci.report import build_report, quick_check, render_console, run_live
from txa.core import config, console, credentials, engines, licenses, net, semver, winos
from txa.core.i18n import is_vi
from txa.core.github import GitHub, GitHubError, device_flow
from txa.core.manifest import ManifestError, split_id
from txa.create import ghmeta, wizard
from txa.create.draft import Draft, Item, guess_arch, known_arch, name_from_filename, pascal

MAX_DOWNLOAD = 4 * 1024 * 1024 * 1024


def _die(message: str) -> int:
    console.error("txacreate", message)
    return 1


# --------------------------------------------------------------------------- auth


SCOPES = "public_repo user:email"


def _verified(token: str) -> tuple[GitHub, dict, str | None]:
    """Check a token against GitHub -> (client, user, email). Warns when it cannot open PRs."""
    gh = GitHub(token)
    response = gh.request("GET", "user")
    user = response.json()
    scopes = response.headers.get("X-OAuth-Scopes")
    if scopes is not None and not {"repo", "public_repo"} & {x.strip() for x in scopes.split(",")}:
        console.say("  ! this token has no repo/public_repo scope - forking and opening PRs will fail")
    return gh, user, _primary_email(gh, user)


def _device_login(reason: str) -> tuple[str, str]:
    """GitHub Device Code Flow: show a one-time code, open the browser, wait for approval."""
    def show(code: dict) -> None:
        print(f"\n{console.paint(reason, 'bold')}")
        print(f"  1. Open   {console.paint(code['verification_uri'], 'cyan')}")
        print(f"  2. Enter  {console.paint(code['user_code'], 'yellow', 'bold')}\n")
        webbrowser.open(code["verification_uri"])
        print(console.paint("  Waiting for you to authorize TXA in the browser…", "gray"))

    return device_flow(config.get("client_id"), SCOPES, show), "device flow"


def _sign_in(token_arg: str | None = None) -> tuple[GitHub, str]:
    """Credentials for the fork step. Order: --token, TXA_TOKEN, stored login, GH_TOKEN, then the browser.

    Only a device-flow login is stored; a token passed explicitly is used once and never saved.
    """
    token, source = (token_arg, "--token") if token_arg else credentials.load_token()
    saved = False
    if not token:
        token, source = _device_login("GitHub access is needed to fork the repository and open the pull request:")
        saved = True
    try:
        gh, user, email = _verified(token)
    except GitHubError as exc:
        if exc.status != 401 or saved or not source.startswith("stored credential"):
            raise
        console.say("  ! the stored GitHub login has expired - signing in again")
        credentials.clear_token()
        token, source = _device_login("Authorize TXA again:")
        saved = True
        gh, user, email = _verified(token)
    if saved:
        path = credentials.save_token(token, user["login"], "device flow", email)
        console.say(f"✓ signed in as {user['login']} <{email or 'email hidden'}> (kept encrypted in {path})")
    else:
        console.say(f"→ using GitHub account {user['login']} ({source})")
    return gh, user["login"]


def _primary_email(gh: GitHub, user: dict) -> str | None:
    """Public profile email, else the primary verified one (needs the user:email scope)."""
    if user.get("email"):
        return user["email"]
    response = gh.request("GET", "user/emails", ok=(403, 404))
    if response.status_code != 200:
        return None
    emails = response.json()
    primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
    return (primary or next(iter(emails), {})).get("email")


def cmd_token(args) -> int:
    """Optional helper: authorize ahead of time, show the stored login, or forget it."""
    if args.clear:
        console.say("✓ stored GitHub login removed" if credentials.clear_token() else "no stored GitHub login")
        return 0
    if args.store:
        if args.token:
            token, source = args.token.strip(), "personal access token"
        else:
            token, source = _device_login("Authorize TXA on GitHub:")
        _, user, email = _verified(token)
        path = credentials.save_token(token, user["login"], source, email)
        console.say(f"✓ stored login for {user['login']} <{email or 'email hidden'}> via {source}")
        print(console.paint(f"  {path} (encrypted for this Windows account)", "gray"))
        return 0
    token, source = credentials.load_token()
    if not token:
        console.say("! not signed in - this is fine: txacreate asks for GitHub access only when it opens a pull request")
        return 0
    _, user, email = _verified(token)
    for key, value in (("user", console.paint(user["login"], "bold", "cyan")), ("email", email or "(hidden)"),
                       ("token", source), ("upstream", config.get("upstream"))):
        print(f"{console.label(key, 10)}{value}")
    return 0


def cmd_config(args) -> int:
    cfg = config.load_config()
    if args.action == "list":
        for key in config.keys():
            print(f"{console.label(key, 10)}{config.get(key) or '-'}")
        print(f"{console.label('api_base', 10)}{config.api_base()}  {console.paint('(derived)', 'gray')}")
    elif args.action == "get":
        print(config.get(args.key))
    elif args.action == "set":
        config.get(args.key)  # validates the key name
        cfg[args.key] = args.value
        config.save_config(cfg)
        console.say(f"✓ {args.key} = {args.value}")
    elif args.action == "unset":
        cfg.pop(args.key, None)
        config.save_config(cfg)
        console.say(f"✓ {args.key} reset to default")
    return 0


# --------------------------------------------------------------------------- new


def _ask_until(prompt: str, default: str | None, check=None) -> str:
    while True:
        value = console.ask(prompt, default)
        problem = check(value) if check else (None if value else "required")
        if not problem:
            return value
        console.say(f"    ✗ {problem}")


ENGINE_NAMES = {
    "inno": "Inno Setup installer", "nsis": "NSIS (Nullsoft) installer", "msi": "Windows Installer (.msi)",
    "wix": "WiX Burn bundle", "exe": "generic .exe installer", "portable": "portable ZIP (unpacked, not installed)",
}


def _describe_installer(dl, found, engine: str, arch: str, display_name: str | None = None) -> None:
    """What kind of file this is, how TXA will run it, and for which CPU - in plain words."""
    from txa.core import i18n

    paint = console.paint
    fname = display_name or dl.path.name
    print(f"  {paint(fname, 'bold')}  {dl.bytes / 1048576:.2f} MiB")
    print(f"    {console.label('SHA-256', 11)}{paint(dl.sha256, 'gray')}")
    print(f"    {console.label('type', 11)}{paint(i18n.tr(ENGINE_NAMES.get(engine, engine)), 'magenta', 'bold')}")
    if engine == "portable":
        spec = found.portable or {}
        msg = i18n.tr(f"unpacked into the TXA apps folder, PATH gets: {', '.join(spec.get('path', [])) or '-'}")
        print(f"    {console.label('install', 11)}{msg}")
    else:
        switches = engines.DEFAULT_SWITCHES.get(engine, {}).get("silent")
        print(f"    {console.label('silent', 11)}{paint(switches, 'cyan') if switches else paint(i18n.tr('you must give --silent'), 'yellow')}")
    wrapper = ""
    if found.machine and found.machine != arch and found.format == "pe":
        wrapper = paint("  " + i18n.tr(f"(the installer program itself is {found.machine}, that is normal)"), "gray")
    print(f"    {console.label('CPU', 11)}{paint(arch, 'yellow', 'bold')}{wrapper}")


def _open_pull_request(url: str, args) -> None:
    """Open the new pull request in the default browser (skip with --no-browser)."""
    if getattr(args, "no_browser", False):
        return
    try:
        opened = webbrowser.open(url)
    except webbrowser.Error:
        opened = False
    console.say(f"→ {'opening the pull request in your browser' if opened else 'open this link in your browser'}"
                f"{'' if opened else ': ' + console.paint(url, 'cyan', 'bold')}")


def _resolve_license(draft: Draft, interactive: bool) -> str | None:
    """Make draft.license_name a recognised identifier. Returns an error message, or None when fine."""
    name = licenses.normalize(draft.license_name) if draft.license_name else None
    if draft.license_name and not name:
        hint = licenses.suggest(draft.license_name)
        problem = f"'{draft.license_name}' is not a recognised license" + (f" (did you mean {', '.join(hint)}?)" if hint else "")
        if not interactive:
            return problem + " - use an SPDX id such as MIT, or Freeware / Proprietary together with --license-url"
        console.say(f"! {problem}")
    if not name:
        if not interactive:
            return "missing --license (e.g. --license MIT)"
        draft.license_name = ""
        wizard.ask_license(draft)  # the same list-with-explanations the guided flow uses
        return None
    draft.license_name = name
    if licenses.needs_url(name) and not draft.license_url:
        if not interactive:
            return f"license '{name}' needs --license-url (a link to its terms)"
        draft.license_url = _ask_until(f"Link to the {name} terms (https://…)", None,
                                       lambda v: None if v.startswith("https://") else "must start with https://")
    return None


def _per_url(value: str | None, count: int) -> list[str | None]:
    if not value:
        return [None] * count
    items = [v.strip() or None for v in value.split(",")]
    if len(items) != count:
        raise SystemExit(f"txacreate: expected {count} comma-separated value(s), got '{value}'")
    return items


def _allowed_namespaces(upstream: str) -> list[str]:
    """Namespaces the repository accepts (policy.txa.yaml on its main branch); best effort."""
    try:
        import yaml

        text = net.session().get(f"https://raw.githubusercontent.com/{upstream}/main/policy.txa.yaml", timeout=6).text
        found = (yaml.safe_load(text) or {}).get("namespaces") or []
        return [str(n) for n in found] or [config.get("namespace")]
    except Exception:  # offline or no policy file: fall back to the default namespace
        return [config.get("namespace")]


def _download_all(args, guided: bool) -> list[Item] | None:
    """Download every URL into a temp folder and look inside; prints the report for each file."""
    work = Path(tempfile.mkdtemp(prefix="create-", dir=config.temp_root()))
    session = net.session()
    arches, engine_overrides = _per_url(args.arch, len(args.urls)), _per_url(args.engine, len(args.urls))
    items: list[Item] = []
    for index, url in enumerate(args.urls):
        print(f"      {console.paint(url, 'cyan')}")
        try:
            dl = net.download(session, url, work / f"payload{index}", MAX_DOWNLOAD, on_progress=console.progress("      "))
        except net.NetError as exc:
            console.done_line()
            _die(str(exc))
            return None
        console.done_line()
        found = engines.inspect(dl.path)
        if found.format == "zip":
            engine = "portable"
        else:
            engine = engine_overrides[index] or found.engine
        if not engine:
            _die(f"{dl.path.name}: unsupported payload ({found.label}); pass --engine")
            return None
        orig_name = Path(url.split("?")[0].rstrip("/")).name or dl.path.name
        known = arches[index] or known_arch(orig_name, found)
        arch = known or guess_arch(orig_name, found)
        _describe_installer(dl, found, engine, arch, display_name=orig_name)
        item = Item(url, dl, found, engine, arch, arch_known=bool(known),
                    mirrors=list(args.mirror or []) if len(args.urls) == 1 else [])
        if engine == "portable":
            item.portable = dict(found.portable) if found.format == "zip" else {}
            if args.path:
                item.portable["path"] = [p.strip() for p in args.path.split(",") if p.strip()]
            if args.strip is not None:
                item.portable["strip"] = args.strip
        else:
            item.switches = dict(engines.DEFAULT_SWITCHES.get(engine, {}))
        items.append(item)
    arch_list = [i.arch for i in items]
    if len(set(arch_list)) != len(arch_list) and not guided:
        _die(f"two installers resolve to the same architecture ({', '.join(arch_list)}) - use --arch x64,x86,…")
        return None
    return items


def _initial_draft(args, items: list[Item], previous: dict, github: dict | None, namespace: str) -> Draft:
    """Suggested answers: flags, then the published version, then the file, then the GitHub project."""
    first = items[0]
    github = github or {}
    prev_core = previous.get("core") or {}
    prev_build = previous.get("build") or {}
    prev_lang = (prev_core.get("locale") or {}).get("default")
    prev_about = (previous.get("about") or {}).get(prev_lang or "", {})
    prev_license = prev_about.get("license") or {}
    prev_package = prev_core.get("package") or {}
    info = first.found
    description = (info.pe.version_info.get("FileDescription") if info.pe else None) or ""
    typed_names = [n.strip() for n in args.alias.split(",") if n.strip()] if args.alias else []
    name = args.name or prev_about.get("name") or info.product_name or github.get("name") \
        or name_from_filename(first.dl.path.name)
    version = args.version or semver.coerce(info.product_version) or github.get("version") \
        or semver.coerce(first.dl.path.name) or semver.coerce(first.url) or ""
    draft = Draft(
        package_id=args.id or f"{namespace}.{pascal(name)}",
        version=version,
        lang=args.lang or prev_lang or "en-US",
        channel=args.channel or prev_package.get("channel", "stable"),
        alias=typed_names[0] if typed_names else prev_package.get("alias"),
        aliases=typed_names[1:] if typed_names else prev_package.get("aliases", []),
        tags=[t.strip() for t in args.tags.split(",")] if args.tags else prev_core.get("tags") or github.get("tags", []),
        min_build=args.min_build or (prev_build.get("platform") or {}).get("min_build") or "10.0.17763",
        scope=args.scope or prev_build.get("scope") or ("user" if all(i.engine == "portable" for i in items) else "machine"),
        name=name,
        publisher=args.publisher or prev_about.get("publisher") or info.company or github.get("publisher") or "",
        author=args.author or prev_about.get("author") or "",
        summary=args.summary or prev_about.get("summary") or github.get("summary")
        or (description if len(description) >= 10 else ""),
        description=args.description or prev_about.get("description"),
        homepage=args.homepage or prev_about.get("homepage") or github.get("homepage"),
        license_name=args.license or prev_license.get("name") or github.get("license") or "",
        license_url=args.license_url or prev_license.get("url") or github.get("license_url"),
        extra_abouts={k: v for k, v in (previous.get("about") or {}).items() if k != prev_lang},
    )
    draft.author = draft.author or draft.publisher
    return draft


def _fill_from_flags(args, draft: Draft, items: list[Item], interactive: bool) -> str | None:
    """Script mode: every answer must come from flags (or the published version); returns an error text."""
    required = {
        "version": ("Version (X.Y.Z)", lambda v: None if semver.is_valid(v) else "use strict X.Y.Z"),
        "name": ("Display name", None),
        "publisher": ("Publisher", None),
        "author": ("Author", None),
        "summary": ("Short description (10-160 chars)", lambda v: None if 10 <= len(v) <= 160 else "10-160 characters"),
    }
    missing = [key for key in required if not getattr(draft, key)]
    if draft.version and not semver.is_valid(draft.version):
        missing.insert(0, "version")
    if missing and not interactive:
        return "missing " + ", ".join(f"--{k.replace('_name', '').replace('_', '-')}" for k in missing)
    for key in missing:
        prompt, check = required[key]
        setattr(draft, key, _ask_until(prompt, getattr(draft, key) or None, check))
    problem = _resolve_license(draft, interactive)
    if problem:
        return problem
    for item in items:
        if item.engine == "portable":
            if not item.portable.get("path"):
                return f"{item.dl.path.name}: no program folder found - pass --path <folder[,folder]> (and --strip N)"
            continue
        if args.silent:
            item.switches["silent"] = args.silent
        if args.progress:
            item.switches["progress"] = args.progress
        if args.custom:
            item.switches["custom"] = args.custom
        if item.engine == "exe" and not item.switches.get("silent"):
            if not interactive:
                return "engine 'exe' needs --silent (and ideally --progress)"
            item.switches["silent"] = _ask_until("Silent switches for this .exe", None)
            item.switches["progress"] = console.ask("Switches for install with progress UI", item.switches["silent"])
    return None


def _materialise(draft: Draft, items: list[Item], root: Path) -> dict[str, str]:
    """Write the three cards under ``root/<release directory>`` and return {file name: text}."""
    draft.targets = [item.target() for item in items]
    release = root / draft.directory
    release.mkdir(parents=True, exist_ok=True)
    rendered = draft.render()
    for filename, text in rendered.items():
        (release / filename).write_text(text, "utf-8", newline="\n")
    return rendered


def _preview(draft: Draft, rendered: dict[str, str], root: Path, published: list[str]) -> dict:
    """Print the three cards, then 'Manifest validation succeeded: True/False' like the reference flow."""
    paint = console.paint
    print("\nGenerating a preview of your manifests...")
    preview_items = [
        ("Core card", "core.txa.yaml"),
        ("Build card", "build.txa.yaml"),
        ("About card", f"about.{draft.lang}.txa.yaml"),
    ]
    if "about.vi-VN.txa.yaml" in rendered and draft.lang != "vi-VN":
        preview_items.append(("About card (vi-VN)", "about.vi-VN.txa.yaml"))
    for title, filename in preview_items:
        print(f"\n{paint(title + ' preview:', 'bold', 'cyan')}")
        print(rendered.get(filename, ""))
    ctx = init_local([root / draft.directory], offline=True)
    if published:
        ctx.targets[0].update({"mode": "new-version", "existing_versions": published})
    report = quick_check(ctx, quiet=True)
    ok = report["verdict"] != "fail"
    print(f"Manifest validation succeeded: {paint(str(ok), 'green' if ok else 'red', 'bold')}")
    if not ok:
        for row in report["results"]:
            for message in row["messages"]:
                if message["level"] == "fail":
                    console.say(f"✗ STEP {row['step']:02d}: {message['text']}")
    return report


def _show_path(path: Path) -> str:
    home = str(Path.home())
    text = str(path)
    return "%USERPROFILE%" + text[len(home):] if text.lower().startswith(home.lower()) else text


def _already_published_versions(package_id: str) -> list[str]:
    """Return published versions of ``package_id`` across configured sources (or empty list)."""
    try:
        from txa.pm.source import Source
        return Source().versions(package_id)
    except Exception:
        return []


def _clone_args_for_query(args, query: str):
    """Resolve a non-URL package name or WinGet ID into a cloned args namespace with URLs + metadata."""
    import copy
    from txa.create import winget

    console.say(f"→ resolving '{console.paint(query, 'cyan', 'bold')}' via WinGet…")
    wg_id = winget.resolve_to_winget_id(query)
    if not wg_id:
        _die(f"could not find '{query}' on WinGet - pass a direct https:// installer URL instead")
        return None
    data = winget.query_winget_package(wg_id)
    if not data:
        _die(f"found '{wg_id}' on WinGet, but no supported HTTPS installer was available")
        return None
    cloned = copy.deepcopy(args)
    namespace = config.get("namespace")
    urls = winget.populate_args_from_winget(cloned, data, namespace)
    if not urls:
        _die(f"no HTTPS installer URLs found for '{wg_id}'")
        return None
    cloned.urls = urls
    cloned.yes = getattr(args, "yes", False)
    cloned._from_query = True
    console.say(f"✓ matched {console.paint(wg_id, 'green', 'bold')} → {console.paint(cloned.id, 'bold')} "
                f"{cloned.version} ({len(urls)} installer URL(s))")
    return cloned


def cmd_new(args) -> int:
    if getattr(args, "from_installed", False):
        from txa.create import winget

        console.say("→ scanning installed programs not yet in TXA…")
        untracked = winget.scan_installed_winget_packages()
        if not untracked:
            console.say("✓ all detected WinGet programs on this machine are already in TXA!")
            return 0
        print(console.head(f"\n{'#':<4} {'Name':<38} {'WinGet Id':<36} {'Version'}"))
        for idx, item in enumerate(untracked, 1):
            print(f"{console.paint(f'{idx}.', 'yellow'):<13} {item['name'][:38]:<38} "
                  f"{console.paint(item['id'], 'cyan'):<45} {item['version']}")
        if args.yes or not sys.stdin.isatty():
            picked = untracked
        else:
            options = [console.Option("all", "All programs", f"import all {len(untracked)} program(s)")]
            for item in untracked:
                options.append(console.Option(item, item["name"][:24], f"{item['id']} ({item['version']})"))
            chosen = console.choose("\nSelect program to add (use ↑/↓ or type number, Enter to confirm)", "program", options, default=0)
            picked = untracked if chosen.value == "all" else [chosen.value]
        if not picked:
            return _die("no programs selected")
        rc = 0
        for item in picked:
            cloned = _clone_args_for_query(args, item["id"])
            if not cloned or _cmd_new_single(cloned) != 0:
                rc = 1
        return rc

    if not args.urls:
        return _die("pass an installer URL, a package name (e.g. `txacreate new \"GitHub CLI\"`), or `--from-installed`")

    # If any positional argument is not an https:// URL, treat positional args as package queries
    if any(not u.lower().startswith("https://") for u in args.urls):
        rc = 0
        for query in args.urls:
            if query.lower().startswith("https://"):
                import copy
                cloned = copy.deepcopy(args)
                cloned.urls = [query]
                if _cmd_new_single(cloned) != 0:
                    rc = 1
            else:
                cloned = _clone_args_for_query(args, query)
                if not cloned or _cmd_new_single(cloned) != 0:
                    rc = 1
        return rc

    return _cmd_new_single(args)


def _cmd_new_single(args) -> int:
    upstream = config.get("upstream")
    namespace = config.get("namespace")
    interactive = sys.stdin.isatty() and not args.yes
    guided = interactive and sys.stdout.isatty()
    total = (3 if args.dry_run else 4) if guided else (4 if args.dry_run else 5)

    # Fast pre-flight before downloading 100+ MB of installers when id & version are already known
    if getattr(args, "id", None) and getattr(args, "version", None) and not getattr(args, "force", False):
        published_pre = _already_published_versions(args.id)
        if args.version in published_pre:
            if getattr(args, "_from_query", False) or getattr(args, "from_installed", False):
                console.say(f"✓ {args.id} {args.version} is already published in TXA - skipped (use --force to overwrite)")
                return 0
            return _die(f"{args.id} {args.version} is already published - bump the version (or pass --force)")

    if not args.dry_run:
        console.say(f"→ target repository {upstream}")

    # 1. download + analyse every installer
    console.stage(1, total, f"Downloading and analysing {len(args.urls)} file(s)")
    items = _download_all(args, guided)
    if items is None:
        return 1

    # 2. identity, suggested answers, questions
    console.stage(2, total, "Package details" if guided else "Resolving the package identity and metadata")
    github = ghmeta.from_release_url(items[0].url, _github_client()) if guided else None
    draft = _initial_draft(args, items, {}, github, namespace)
    previous: dict = {}
    published: list[str] = []

    def lookup(package_id: str) -> None:
        nonlocal previous, published
        try:
            from txa.pm.source import Source

            src = Source()
            latest, found_cards = src.release(package_id)
            published, previous = src.versions(package_id), found_cards
            console.say(f"→ {package_id} already published (latest {latest}) - reusing its metadata")
        except Exception:
            previous, published = {}, []
            if getattr(args, "update", False):
                raise LookupError(f"{package_id} is not published yet - use `txacreate new`") from None
            console.say(f"→ {package_id} is a new package")

    try:
        split_id(draft.package_id)
        lookup(draft.package_id)
    except (ManifestError, LookupError) as exc:
        if not guided or getattr(args, "update", False):
            return _die(str(exc))
    if previous:
        draft = _initial_draft(args, items, previous, github, namespace)

    namespaces = _allowed_namespaces(upstream) if guided else []
    if guided:
        suggested_id = draft.package_id
        wizard.collect(draft, items, lock_id=bool(getattr(args, "update", False)), namespaces=namespaces, github=github)
        if draft.package_id != suggested_id:
            lookup(draft.package_id)
    else:
        problem = _fill_from_flags(args, draft, items, interactive)
        if problem:
            return _die(problem)
    if published and draft.version in published and not args.force:
        return _die(f"{draft.package_id} {draft.version} is already published - bump the version (or pass --force)")

    # 3. cards: write, preview, let the user change their mind, save
    console.stage(3, total, "Preview and save the TXA cards" if guided else "Writing the TXA cards")
    work_root = Path(tempfile.mkdtemp(prefix="tree-", dir=config.temp_root()))
    report = None
    if guided:
        while True:
            rendered = _materialise(draft, items, work_root)
            check = _preview(draft, rendered, work_root, published)
            broken = check["verdict"] == "fail"
            if not console.confirm("Would you like to make changes to this manifest?", default=broken):
                break
            wizard.collect(draft, items, lock_id=bool(getattr(args, "update", False)), namespaces=namespaces,
                           github=github, first_time=False)
        if broken and not args.force:
            return _die("the cards have problems - fix them, or pass --force to open the PR anyway")
        save_root = Path(args.out) if args.out else Path.home() / "manifests"
        draft_path = Path(draft.directory)
        if save_root.name.lower() == "manifests" and draft_path.parts and draft_path.parts[0].lower() == "manifests":
            rel_dir = Path(*draft_path.parts[1:])
        else:
            rel_dir = draft_path
        saved = save_root / rel_dir
        saved.mkdir(parents=True, exist_ok=True)
        for filename, text in rendered.items():
            (saved / filename).write_text(text, "utf-8", newline="\n")
        console.say(f"→ Manifest saved to {console.paint(_show_path(saved), 'cyan', 'bold')}")
        if args.check:
            report = run_live(init_local([saved], offline=args.offline, payloads={
                saved.relative_to(save_root).as_posix(): {i.arch: i.dl.path for i in items}}))
    else:
        out_root = Path(args.out) if args.out else (Path.cwd() / "txa-out" if args.dry_run else work_root)
        rendered = _materialise(draft, items, out_root)
        release = out_root / draft.directory
        console.say(f"→ wrote {len(rendered)} card(s) to {release}")
        if not args.no_validate:
            rel = release.relative_to(out_root).as_posix()
            ctx = init_local([release], offline=args.offline, payloads={rel: {i.arch: i.dl.path for i in items}})
            if published:
                ctx.targets[0].update({"mode": "new-version", "existing_versions": published})
            if args.check:
                console.stage(4, total, "Running the 14 bot checks locally (--check)")
                report = run_live(ctx)
            else:
                ctx.data["offline"] = True
                console.stage(4, total, "Quick check of the cards (the repository bot runs the full 14 steps on your pull request)")
                checked = quick_check(ctx)
                report = checked if checked["verdict"] == "fail" else None
            if report and report["verdict"] == "fail" and not args.force:
                return _die("the cards have problems - fix the issues above, or pass --force to open the PR anyway")
            if not args.check:
                report = None  # the PR body should not claim a full pre-flight that did not run

    if args.dry_run:
        console.say("✓ dry run complete - nothing was sent to GitHub")
        return 0
    if guided and not console.confirm("Would you like to submit your manifest to the TXA repository?", default=True):
        print(f"Nothing was sent. Submit it later with: txacreate submit \"{saved}\"")
        return 0

    # 4. fork → branch → commit → PR  (the first step that needs GitHub access)
    console.stage(total, total, "Forking the repository and opening the pull request")
    try:
        gh, login = _sign_in(args.token)
    except GitHubError as exc:
        return _die(f"{exc}\n  (or pass --token <PAT> / set TXA_TOKEN)")
    existing_pr = None if args.force else _safe(lambda: _find_pr(gh, upstream, draft))
    if existing_pr:
        return _die(f"an open pull request already covers {draft.package_id} {draft.version}: {existing_pr}")
    kind = "New version" if published else "New package"
    files = {f"{draft.directory}/{name}": text for name, text in rendered.items()}
    console.say("Submitting pull request for manifest...")
    try:
        from txa.create.submit import submit

        result = submit(gh, upstream, login, draft.package_id, draft.version, files,
                        f"{kind}: {draft.package_id} {draft.version}", _pr_body(kind, draft, items, report),
                        direct=args.direct)
    except GitHubError as exc:
        return _die(str(exc))
    console.say(f"\n✓ pull request #{result.number} opened. Pull request can be found here: "
                f"{console.paint(result.url, 'cyan', 'bold')}")
    _open_pull_request(result.url, args)
    if is_vi():
        print(console.paint(f"  nhánh {result.head_repo}@{result.branch} · hãy tích đầy đủ các ô checklist và bình luận '@txa-repo agree' trên PR để bot bắt đầu chạy 16 bước kiểm tra.", "gray"))
    else:
        print(console.paint(f"  branch {result.head_repo}@{result.branch} · please tick the checklist in the PR description and comment '@txa-repo agree' for the TXA bot to start verification.", "gray"))
    return 0


def _github_client() -> GitHub:
    token = credentials.load_token()[0]
    return GitHub(token) if token else GitHub()


def _safe(fn):
    try:
        return fn()
    except GitHubError:
        return None


def _find_pr(gh: GitHub, upstream: str, draft: Draft) -> str | None:
    from txa.create.submit import find_open_pr

    return find_open_pr(gh, upstream, draft.package_id, draft.version)


def _checklist(repo: str) -> list[str]:
    """The checklist of the pull request description (empty boxes for the author to tick on GitHub)."""
    return [
        "## ✅ Checklist", "",
        f"- [ ] Signed the [Contributor Agreement](https://github.com/{repo}#readme) (the bot asks you to confirm with `@txa-repo agree`)",
        "- [ ] Linked to an issue (if applicable)", "  - Resolves #[Issue Number]", "",
        "## 📦 Manifest Checklist", "",
        f"- [ ] Checked that there aren't other open [pull requests](https://github.com/{repo}/pulls) for the same manifest update/change",
        "- [ ] This PR only modifies one (1) manifest",
        "- [ ] Validated manifest locally with `txacreate validate <path>`",
        "- [ ] Tested manifest locally with `txapm install --manifest <path>`",
        f"- [ ] Manifest conforms to the [v1 schema](https://github.com/{repo}/blob/main/docs/manifest-schema.md)", "",
        "> **Note:** `<path>` is the directory containing the manifest you're submitting.",
    ]


def _pr_body(kind: str, draft: Draft, items: list[Item], report: dict | None) -> str:
    """The pull request description: what it is, plus a checklist the contributor ticks to confirm."""
    repo = config.get("upstream")
    path = draft.directory
    lines = [
        "## 📖 Description", "",
        f"{kind}: **{draft.name}** (`{draft.package_id}`) {draft.version} - {draft.summary}", "",
        "| Publisher | License | Minimum Windows | Scope |", "|---|---|---|---|",
        f"| {draft.publisher} | {draft.license_name} | {draft.min_build} ({winos.describe(winos.parse_build(draft.min_build))}) | {draft.scope} |", "",
        "| CPU | Type | Size | SHA-256 |", "|---|---|---|---|",
    ]
    for item in items:
        lines.append(f"| {item.arch} | {ENGINE_NAMES.get(item.engine, item.engine)} | {item.dl.bytes / 1048576:.2f} MiB | `{item.dl.sha256}` |")
    lines += ["", *_checklist(repo), "", "---", f"<sub>Submitted with txacreate {__version__} · cards in `{path}/`</sub>"]
    if report:
        counts: dict[str, int] = {}
        for row in report["results"]:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        lines.insert(len(lines) - 2, f"**Local pre-flight (txaci):** {' · '.join(f'{k} {v}' for k, v in sorted(counts.items()))}")
    return "\n".join(lines)


def cmd_update(args) -> int:
    """Like `new`, but for a package that already exists: every field is carried over."""
    args.id, args.update = args.package, True
    return cmd_new(args)


def cmd_hash(args) -> int:
    source = args.target
    if source.lower().startswith("https://"):
        work = Path(tempfile.mkdtemp(prefix="hash-", dir=config.temp_root()))
        path = net.download(net.session(), source, work, MAX_DOWNLOAD, on_progress=console.progress("download")).path
        console.done_line()
    else:
        path = Path(source)
        if not path.is_file():
            return _die(f"{source}: no such file")
    found = engines.inspect(path)
    print(f"{console.label('sha256', 9)}{console.paint(net.sha256_file(path), 'green')}")
    print(f"{console.label('size', 9)}{path.stat().st_size:,} bytes")
    print(f"{console.label('engine', 9)}{console.paint(found.engine or '-', 'magenta', 'bold')} ({found.label})")
    print(f"{console.label('arch', 9)}{console.paint(guess_arch(path.name, found), 'yellow', 'bold')} (installer CPU {found.machine or '-'})")
    if found.product_name or found.product_version:
        print(f"{console.label('product', 9)}{found.product_name or '-'} {found.product_version or ''}".rstrip())
    return 0


def cmd_submit(args) -> int:
    """Open a PR for a hand-written release folder, repo root, or built API folder."""
    from txa.core.manifest import Bundle, discover_releases, kind_of, release_dir
    from txa.create.submit import find_open_pr, submit

    raw_folder = Path(args.folder)
    releases = discover_releases(raw_folder)
    if not releases:
        return _die(f"{raw_folder}: no readable core.txa.yaml")
    if len(releases) > 1 or releases[0].resolve() != raw_folder.resolve():
        console.say(f"→ found {len(releases)} release(s) under {console.paint(str(raw_folder), 'cyan')}: "
                    + ", ".join(f"{Bundle.read(r).package_id}@{Bundle.read(r).version}" for r in releases))

    gh, login = None, ""
    upstream = config.get("upstream")
    failures = 0

    for idx, folder in enumerate(releases, 1):
        bundle = Bundle.read(folder)
        if not bundle.package_id or not bundle.version:
            console.say(f"✗ {folder}: no readable core.txa.yaml")
            failures += 1
            continue
        package_id, version = bundle.package_id, bundle.version
        if len(releases) > 1:
            print(f"\n{console.paint(f'── [{idx}/{len(releases)}] {package_id} {version}', 'bold', 'magenta')}")
        if not args.no_validate:
            ctx = init_local([folder], offline=args.offline)
            if args.check:
                console.stage(1, 2, f"Validating {console.paint(package_id, 'bold')} {version} with the 14 bot checks")
                report = run_live(ctx)
            else:
                ctx.data["offline"] = True
                console.stage(1, 2, f"Quick check of {console.paint(package_id, 'bold')} {version} (the bot runs all 14 steps on the PR)")
                report = quick_check(ctx)
            if report["verdict"] == "fail" and not args.force:
                _die(f"{package_id} {version}: validation failed - fix the issues above or pass --force")
                failures += 1
                continue
        if getattr(args, "dry_run", False):
            console.say(f"✓ {package_id} {version} validated (--dry-run: skipped opening pull request)")
            continue
        console.stage(2 if not args.no_validate else 1, 2 if not args.no_validate else 1,
                      "Forking the repository and opening the pull request")
        if gh is None:
            try:
                gh, login = _sign_in(args.token)
            except GitHubError as exc:
                return _die(f"{exc}\n  (or pass --token <PAT> / set TXA_TOKEN)")
        if not args.force:
            existing = find_open_pr(gh, upstream, package_id, version)
            if existing:
                console.say(f"! an open pull request already covers {package_id} {version}: {existing}")
                continue
        try:
            from txa.pm.source import Source

            published = Source().versions(package_id)
        except Exception:
            published = []
        kind = "New version" if published else "New package"
        target_dir = release_dir(package_id, version)
        files = {f"{target_dir}/{name}": raw.decode("utf-8") for name, raw in bundle.files.items() if kind_of(name)}
        body = "\n".join([f"## 📖 Description", "", f"{kind}: `{package_id}` {version} - submitted from a local folder with "
                          f"`txacreate submit` ({len(files)} card(s) in `{target_dir}/`).", "",
                          *_checklist(upstream), "", "---", f"<sub>Submitted with txacreate {__version__}</sub>"])
        result = submit(gh, upstream, login, package_id, version, files, f"{kind}: {package_id} {version}", body,
                        direct=args.direct)
        console.say(f"\n✓ pull request #{result.number} opened: {console.paint(result.url, 'cyan', 'bold')}")
        if idx == 1:
            _open_pull_request(result.url, args)
    return 1 if failures else 0


def cmd_show(args) -> int:
    from txa.core.manifest import dump_card
    from txa.pm.source import Source

    src = Source()
    package_id = src.resolve(args.package)
    version, cards = src.release(package_id, args.version)
    documents = [("core.txa.yaml", cards["core"]), ("build.txa.yaml", cards["build"])]
    documents += [(f"about.{lang}.txa.yaml", card) for lang, card in cards["about"].items()]
    for name, card in documents:
        print(console.paint(f"# ---- {package_id} {version} · {name}", "bold", "cyan"))
        print(dump_card(card))
    return 0


def cmd_validate(args) -> int:
    from txa.ci.cli import main as txaci_main

    return txaci_main(["validate", *args.paths, *(["--offline"] if args.offline else [])])


# --------------------------------------------------------------------------- entry


def _release_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--version", help="X.Y.Z (default: read from the installer)")
    p.add_argument("--name")
    p.add_argument("--publisher")
    p.add_argument("--author")
    p.add_argument("--summary")
    p.add_argument("--description")
    p.add_argument("--homepage")
    p.add_argument("--license")
    p.add_argument("--license-url")
    p.add_argument("--lang", help="default locale (default en-US)")
    p.add_argument("--alias", help="short name(s) for txapm, comma separated: node,npm")
    p.add_argument("--strip", type=int, help="portable ZIP: leading folders to drop (default: detected)")
    p.add_argument("--path", help="portable ZIP: folder(s) to add to PATH, comma separated (default: detected)")
    p.add_argument("--tags", help="comma separated")
    p.add_argument("--channel", choices=["stable", "beta"])
    p.add_argument("--arch", help="override per URL, comma separated: x64,x86,arm64")
    p.add_argument("--engine", help="override per URL, comma separated: inno,nsis,msi,wix,exe")
    p.add_argument("--scope", choices=["user", "machine"])
    p.add_argument("--min-build", help="minimum Windows build, e.g. 10.0.17763")
    p.add_argument("--silent", help="silent switches (required for engine exe)")
    p.add_argument("--progress", help="switches for install with a progress UI")
    p.add_argument("--custom", help="extra switches always appended")
    p.add_argument("--mirror", action="append", help="additional download mirror (repeatable)")
    p.add_argument("--out", help="write cards under this folder (default ./txa-out for --dry-run)")
    p.add_argument("--dry-run", action="store_true", help="write cards and pre-flight only, no GitHub calls")
    p.add_argument("--offline", action="store_true", help="skip network checks in the pre-flight")
    p.add_argument("--no-validate", action="store_true", help="skip the quick check of the cards")
    p.add_argument("--check", action="store_true", help="run all 14 bot checks locally (slow: downloads, CDN, signature)")
    p.add_argument("--no-browser", action="store_true", help="do not open the pull request in the browser")
    p.add_argument("--direct", action="store_true", help="branch in upstream instead of a fork (needs push rights)")
    p.add_argument("--force", action="store_true", help="open the PR even if pre-flight fails or a PR exists")
    p.add_argument("-y", "--yes", action="store_true", help="never prompt; fail on missing fields")
    p.add_argument("-t", "--token", help="GitHub personal access token for this run (default: browser sign-in when needed)")


def main(argv: list[str] | None = None) -> int:
    console.setup()
    parser = console.SmartArgumentParser(
        prog="txacreate",
        description="Publish installers to the TXA repository",
        epilog=(
            "examples:\n"
            "  txacreate new https://vendor.example/app-1.2.3-x64.exe\n"
            "  txacreate new \"GitHub CLI\" --dry-run\n"
            "  txacreate new Microsoft.PowerToys --dry-run\n"
            "  txacreate new -i --dry-run\n"
            "  txacreate update TXAVL.HelloTool https://vendor.example/app-1.2.4-x64.exe\n"
            "  txacreate submit C:\\my-txa-repo --dry-run\n"
            "  txacreate validate C:\\my-txa-repo --offline\n"
            "  txacreate hash setup.exe\n"
            "  txacreate config set lang vi"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"txacreate {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("token", help="optional: sign in to GitHub ahead of time, show or forget the stored login")
    p.add_argument("--store", action="store_true", help="authorize now (browser) and keep the login")
    p.add_argument("--clear", action="store_true", help="forget the stored login")
    p.add_argument("-t", "--token", help="with --store: keep this personal access token instead of using the browser")
    p.set_defaults(func=cmd_token)

    p = sub.add_parser("config", help="read or change settings (upstream, client_id, namespace, api)")
    p.add_argument("action", choices=["list", "get", "set", "unset"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("new", help="create a release from installer URL(s), app name(s), or --from-installed")
    p.add_argument("urls", nargs="*", metavar="URL_OR_NAME", help="HTTPS URL(s), WinGet ID(s), or app name(s) from `txapm list --all`")
    p.add_argument("--id", help="Namespace.AppName (default: <namespace>.<ProductName>)")
    p.add_argument("-i", "--from-installed", action="store_true", help="scan installed programs (like `txapm list --all`) and auto-create missing packages")
    _release_options(p)
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("update", help="new version of an existing package (metadata carried over)")
    p.add_argument("package", help="existing package id, e.g. TXAVL.HelloTool")
    p.add_argument("urls", nargs="+", metavar="URL")
    _release_options(p)
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("submit", help="open a pull request for a release folder, repo root, or built API folder")
    p.add_argument("folder", help="folder containing core.txa.yaml, manifests/, or built txa.v1 API")
    p.add_argument("--dry-run", action="store_true", help="validate only without opening a pull request")
    p.add_argument("--offline", action="store_true", help="skip network checks in the validation")
    p.add_argument("--no-validate", action="store_true")
    p.add_argument("--check", action="store_true", help="run all 14 bot checks locally instead of the quick check")
    p.add_argument("--no-browser", action="store_true", help="do not open the pull request in the browser")
    p.add_argument("--direct", action="store_true", help="branch in upstream instead of a fork (needs push rights)")
    p.add_argument("--force", action="store_true", help="submit even if validation fails or a PR exists")
    p.add_argument("-t", "--token", help="GitHub personal access token for this run")
    p.set_defaults(func=cmd_submit)

    p = sub.add_parser("show", help="print the published cards of a package")
    p.add_argument("package")
    p.add_argument("--version", dest="version")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("hash", help="SHA-256, engine and architecture of a local file or HTTPS URL")
    p.add_argument("target")
    p.set_defaults(func=cmd_hash)

    p = sub.add_parser("validate", help="run the 14 bot checks against local release folders")
    p.add_argument("paths", nargs="+")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("help", help="show help for txacreate or a specific command")
    p.add_argument("topic", nargs="?", help="command name")

    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] in ("--clear", "--store"):
        raw_argv = ["token", *raw_argv]
    elif raw_argv and raw_argv[0] in ("-i", "--from-installed"):
        raw_argv = ["new", *raw_argv]

    args = parser.parse_args(raw_argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "config" and args.action in ("get", "set", "unset") and not args.key:
        parser.error("config get/set/unset needs a key")
    if args.command == "config" and args.action == "set" and args.value is None:
        parser.error("config set needs a value")
    try:
        return args.func(args)
    except (GitHubError, net.NetError, LookupError) as exc:  # LookupError covers source.NotFound
        return _die(str(exc))
    except KeyboardInterrupt:
        return _die("cancelled")


if __name__ == "__main__":
    sys.exit(main())
