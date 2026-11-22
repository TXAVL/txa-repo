# For developers and repository maintainers

Tiếng Việt: [maintainers.md](maintainers.md)

## Repository layout

- `manifests/t/TXAVL/<AppName>/<X.Y.Z>/` — each version holds `core.txa.yaml`, `build.txa.yaml`,
  `about.<lang>.txa.yaml`. Field reference: [manifest-schema.en.md](manifest-schema.en.md);
  annotated sample: [examples](../examples/manifests/t/TXAVL/HelloTool/1.4.2/build.txa.yaml).
- `tools/` — Python source of `txapm`, `txacreate`, `txacli`, `txaci`
  (`cd tools && python -m pip install -e .`).
- `web/` — the index page (Astro), built from `api/txa/v1/index.json`.
- `scripts/` — `setup-github.ps1` (labels, CODEOWNERS, branch protection), `winget-import.ps1`.
- `policy.txa.yaml` — size limits, namespaces, CDN check regions.
- Public API: `https://txavl.github.io/txa-repo/api/txa/v1/index.json`.

## Workflows in `.github/workflows/`

| Workflow | Job |
|---|---|
| `txa-validate`, `txa-gate`, `txa-agreement`, `txa-progress`, `txa-lifecycle`, `txa-review-signal` | the pull-request bot: Contributor Agreement, 14 checks, triage (step 15), merge (step 16), `txa:*` labels |
| `txa-auto-update` | picks up new upstream versions automatically (WinGet, antigravity.google and the GitHub releases of T-Drop and TXAWinSetup; hand-written packages or ones marked `auto-update: false` are skipped) |
| `txa-publish-api` | `txaci build-api`, builds the index page, fetches icons and deploys to GitHub Pages; runs when manifests change, every 6 hours and when review PRs change |
| `txa-release` | builds `txa-windows-x64.zip` / `arm64.zip`, `SHA256SUMS.txt` and `install.ps1` when a `vX.Y.Z` tag is pushed |
| `txa-pypi` | uploads the `txa` package to PyPI when a `vX.Y.Z` tag is pushed (the tag must equal `txa.__version__`; needs the `PYPI_API_TOKEN` secret) |
| `txa-tools-ci` | smoke checks for `tools/`: the package installs, the commands start, every manifest in the repo still passes the offline checks |

A package with no usable WinGet installer but with GitHub releases is followed by adding `owner/repo` to `GITHUB_REPOS` in
`tools/src/txa/create/github_sync.py` (with the pattern a release tag must match); the bot reads that repository's newest release.
Currently: Codex, FFmpeg, Oh My Posh, ViGEmBus, MSYS2. Repositories of `TXAVL` are followed by default. A third-party project
**must be listed by hand**; the bot never trusts every GitHub link.

Each package keeps its **10 newest versions**: adding a new one removes the oldest in the same PR (or auto-update run).

## Releasing a new `txa` version

1. Change `__version__` in `tools/src/txa/__init__.py` and land it on `main`.
2. Push a tag with the same number: `git tag vX.Y.Z` then `git push origin vX.Y.Z`.
3. `txa-release` publishes the GitHub release (used by `install.ps1`) and `txa-pypi` publishes to PyPI (used by `pipx`).

## Administration

- A bot with its own name (`txa-repo[bot]`) instead of `github-actions`: [github-app.en.md](github-app.en.md).
- Contributor terms: [contributor-agreement.en.md](contributor-agreement.en.md).
- Bulk import from WinGet: [winget-import.en.md](winget-import.en.md).
- A private repository for an organization: [custom-source.en.md](custom-source.en.md).
