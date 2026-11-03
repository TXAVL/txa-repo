"""Static JSON API (namespace txa.v1) published to GitHub Pages from txa-repo.

Layout under ``<out>/api/txa/v1/``::

    index.json                 every package, newest version summary
    packages/<Id>.json         every version of one package, all three cards
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from txa.constants import API_NAMESPACE
from txa.core import semver
from txa.core.manifest import Bundle, assemble, kind_of, schema_errors


def _valid(bundle: Bundle) -> list[str]:
    problems = [f"{name}: {p}" for name, items in bundle.problems.items() for p in items]
    for name, card in bundle.cards.items():
        problems += [f"{name}: {e}" for e in schema_errors(kind_of(name), card)]
    if not bundle.core or not bundle.build or not bundle.default_about():
        problems.append("incomplete release (core, build and default about cards are required)")
    return problems


def collect(repo_root: Path) -> tuple[dict[str, dict[str, dict]], list[dict]]:
    """Read every valid release under manifests/ -> ({id: {version: cards}}, skipped)."""
    packages: dict[str, dict[str, dict]] = {}
    skipped = []
    for release in sorted((repo_root / "manifests").glob("*/*/*/*")):
        if not release.is_dir() or not semver.is_valid(release.name):
            continue
        bundle = Bundle.read(release)
        problems = _valid(bundle)
        if problems:
            skipped.append({"path": release.relative_to(repo_root).as_posix(), "problems": problems[:5]})
            continue
        packages.setdefault(bundle.package_id, {})[bundle.version] = assemble(bundle)
    return packages, skipped


def package_document(package_id: str, versions: dict[str, dict]) -> dict:
    ordered = sorted(versions, key=semver.parse, reverse=True)
    return {"api": "txa.v1", "id": package_id, "latest": ordered[0], "versions": {v: versions[v] for v in ordered}}


def index_document(packages: dict[str, dict[str, dict]]) -> dict:
    from txa.core import i18n

    index = []
    for package_id in sorted(packages, key=str.lower):
        document = package_document(package_id, packages[package_id])
        latest = document["versions"][document["latest"]]
        about = latest["about"].get(latest["core"]["locale"]["default"]) or next(iter(latest["about"].values()))
        summaries = {loc: ab["summary"] for loc, ab in latest["about"].items() if isinstance(ab, dict) and ab.get("summary")}
        vi_sum = summaries.get("vi-VN") or i18n._SUMMARIES_VI.get(package_id.split(".")[-1].lower())
        if vi_sum:
            summaries.setdefault("vi-VN", vi_sum)
        en_sum = summaries.get("en-US") or i18n._SUMMARIES_EN.get(package_id.split(".")[-1].lower()) or about["summary"]
        if en_sum:
            summaries.setdefault("en-US", en_sum)
        index.append({
            "id": package_id,
            "alias": latest["core"]["package"].get("alias"),
            "aliases": latest["core"]["package"].get("aliases", []),
            "latest": document["latest"],
            "versions": list(document["versions"]),
            "name": about["name"],
            "publisher": about["publisher"],
            "summary": about["summary"],
            "summaries": summaries,
            "tags": latest["core"].get("tags", []),
            "arches": list(dict.fromkeys(t["arch"] for t in latest["build"]["targets"])),
        })
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {"api": "txa.v1", "generated": generated, "count": len(index), "packages": index}


def build_api(repo_root: Path, out: Path, pending: list[dict] | None = None) -> dict:
    import html

    packages, skipped = collect(repo_root)
    api = out / API_NAMESPACE
    (api / "packages").mkdir(parents=True, exist_ok=True)
    for package_id, versions in packages.items():
        document = package_document(package_id, versions)
        (api / "packages" / f"{package_id}.json").write_text(json.dumps(document, ensure_ascii=False, indent=1), "utf-8")
    manifest = index_document(packages)
    index, generated = manifest["packages"], manifest["generated"]
    waiting = sorted(pending or [], key=lambda e: (e["id"].lower(), e["version"]))
    (api / "pending.json").write_text(json.dumps(
        {"api": "txa.v1", "generated": generated, "count": len(waiting), "packages": waiting}, ensure_ascii=False, indent=1), "utf-8")
    (api / "index.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    (out / ".nojekyll").write_text("", "utf-8")

    rows_list = []
    for p in index:
        sums = p.get("summaries") or {}
        sum_en = html.escape(sums.get("en-US") or p.get("summary") or "")
        sum_vi = html.escape(sums.get("vi-VN") or p.get("summary") or "")
        pkg_id = html.escape(p["id"])
        latest = html.escape(p["latest"])
        alias = html.escape(p.get("alias") or p["id"])
        install_cmd = f"txapm install {alias}"
        rows_list.append(
            f"<tr data-search='{pkg_id.lower()} {alias.lower()} {sum_en.lower()} {sum_vi.lower()}'>"
            f"<td><a href='{API_NAMESPACE}/packages/{pkg_id}.json'><code>{pkg_id}</code></a></td>"
            f"<td><span class='ver'>{latest}</span></td>"
            f"<td><code class='cmd' onclick='navigator.clipboard.writeText(this.textContent)' title='Click to copy'>{install_cmd}</code></td>"
            f"<td class='sum' data-en='{sum_en}' data-vi='{sum_vi}'>{sum_vi}</td>"
            f"</tr>"
        )
    rows = "".join(rows_list)
    page_html = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TXA Package Index</title>
<style>
:root {{ --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#e6edf3; --muted:#8b949e; --accent:#58a6ff; --green:#3fb950; }}
@media (prefers-color-scheme: light) {{
  :root {{ --bg:#ffffff; --card:#f6f8fa; --border:#d0d7de; --text:#1f2328; --muted:#656d76; --accent:#0969da; --green:#1a7f37; }}
}}
* {{ box-sizing:border-box; }}
body {{ font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--text); margin:0; padding:2rem 1rem; }}
.wrap {{ max-width:74rem; margin:0 auto; }}
.top {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:1.2rem; }}
h1 {{ margin:0; font-size:1.65rem; }}
.meta {{ color:var(--muted); margin:.25rem 0 0; font-size:.92rem; }}
.meta a {{ color:var(--accent); text-decoration:none; }}
.lang-switch {{ display:inline-flex; border:1px solid var(--border); border-radius:8px; overflow:hidden; background:var(--card); }}
.lang-switch button {{ border:0; background:transparent; color:var(--muted); padding:.4rem .85rem; cursor:pointer; font-weight:600; font-size:.88rem; }}
.lang-switch button.active {{ background:var(--accent); color:#fff; }}
.bar {{ display:flex; flex-wrap:wrap; gap:.75rem; margin:1rem 0 1.25rem; align-items:center; }}
.search {{ flex:1; min-width:220px; padding:.55rem .85rem; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--text); font-size:.95rem; }}
.oneliner {{ padding:.5rem .8rem; background:var(--card); border:1px solid var(--border); border-radius:8px; font-family:ui-monospace,Consolas,monospace; font-size:.84rem; cursor:pointer; color:var(--accent); }}
table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--border); border-radius:10px; overflow:hidden; }}
th, td {{ padding:.6rem .85rem; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }}
th {{ background:rgba(127,127,127,.08); font-size:.86rem; text-transform:uppercase; letter-spacing:.03em; color:var(--muted); }}
tr:last-child td {{ border-bottom:0; }}
tr:hover td {{ background:rgba(88,166,255,.05); }}
code {{ font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:.88rem; }}
td a {{ color:var(--accent); text-decoration:none; font-weight:600; }}
.ver {{ color:var(--green); font-weight:600; font-family:ui-monospace,Consolas,monospace; font-size:.88rem; }}
.cmd {{ background:rgba(127,127,127,.14); padding:.18rem .45rem; border-radius:5px; cursor:pointer; white-space:nowrap; }}
.cmd:hover {{ outline:1px solid var(--accent); }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1 id="title">Kho gói phần mềm TXA (TXA Package Index)</h1>
      <p class="meta">
        <span id="pkg-count">{len(index)}</span> <span id="lbl-pkgs">gói phần mềm</span> ·
        <span id="lbl-gen">cập nhật</span> {generated} ·
        <a href="{API_NAMESPACE}/index.json">index.json</a> ·
        <a href="{API_NAMESPACE}/pending.json">pending.json</a> ·
        <a href="https://github.com/TXAVL/txa-repo">GitHub</a>
      </p>
    </div>
    <div class="lang-switch">
      <button id="btn-vi" onclick="setLang('vi')">🇻🇳 Tiếng Việt</button>
      <button id="btn-en" onclick="setLang('en')">🇬🇧 English</button>
    </div>
  </div>
  <div class="bar">
    <input id="q" class="search" type="search" placeholder="Tìm kiếm phần mềm theo tên, mã gói hoặc mô tả..." oninput="filterRows(this.value)">
    <div class="oneliner" onclick="navigator.clipboard.writeText('irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1 | iex')" title="Click to copy">
      irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1 | iex
    </div>
  </div>
  <table>
    <thead>
      <tr>
        <th id="th-id">Mã gói (Id)</th>
        <th id="th-ver">Phiên bản</th>
        <th id="th-cmd">Lệnh cài nhanh</th>
        <th id="th-sum">Mô tả</th>
      </tr>
    </thead>
    <tbody id="tbody">{rows}</tbody>
  </table>
</div>
<script>
const I18N = {{
  vi: {{
    title: "Kho gói phần mềm TXA",
    pkgs: "gói phần mềm",
    gen: "cập nhật",
    search: "Tìm kiếm phần mềm theo tên, mã gói hoặc mô tả (Tiếng Việt / Tiếng Anh)...",
    thId: "Mã gói (Id)",
    thVer: "Phiên bản",
    thCmd: "Lệnh cài nhanh",
    thSum: "Mô tả"
  }},
  en: {{
    title: "TXA Package Index",
    pkgs: "package(s)",
    gen: "generated",
    search: "Search packages by name, ID, alias, or description...",
    thId: "Id",
    thVer: "Latest",
    thCmd: "Install Command",
    thSum: "Summary"
  }}
}};
function setLang(lang) {{
  const t = I18N[lang] || I18N.vi;
  localStorage.setItem("txa_lang", lang);
  document.documentElement.lang = lang;
  document.getElementById("title").textContent = t.title;
  document.getElementById("lbl-pkgs").textContent = t.pkgs;
  document.getElementById("lbl-gen").textContent = t.gen;
  document.getElementById("q").placeholder = t.search;
  document.getElementById("th-id").textContent = t.thId;
  document.getElementById("th-ver").textContent = t.thVer;
  document.getElementById("th-cmd").textContent = t.thCmd;
  document.getElementById("th-sum").textContent = t.thSum;
  document.getElementById("btn-vi").classList.toggle("active", lang === "vi");
  document.getElementById("btn-en").classList.toggle("active", lang === "en");
  document.querySelectorAll("td.sum").forEach(td => {{
    td.textContent = td.getAttribute("data-" + lang) || td.textContent;
  }});
}}
function filterRows(q) {{
  const words = q.toLowerCase().trim().split(/\\s+/).filter(Boolean);
  let shown = 0;
  document.querySelectorAll("#tbody tr").forEach(tr => {{
    const hay = tr.getAttribute("data-search") || "";
    const ok = words.every(w => hay.includes(w));
    tr.style.display = ok ? "" : "none";
    if (ok) shown++;
  }});
  document.getElementById("pkg-count").textContent = shown;
}}
const saved = localStorage.getItem("txa_lang") || ((navigator.language || "").toLowerCase().startsWith("vi") ? "vi" : "vi");
setLang(saved);
</script>
</body>
</html>"""
    (out / "index.html").write_text(page_html, "utf-8")
    return {"packages": len(index), "pending": len(waiting), "skipped": skipped, "out": str(api)}
