# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Astro (static output, no UI framework needed). Chosen by the user from "framework (Astro, Vite...)"; the specific framework was delegated, so Astro was picked because the page is a prerendered list built from `api/txa/v1/index.json`. It replaces the HTML template that is currently inlined in `tools/src/txa/ci/api.py`. Deploy target stays GitHub Pages via the "TXA Publish API" workflow, so the Astro build must run after `txaci build-api` and publish into the same `site/` folder.

## Users

Primary: Windows users (Windows 10 1809+, x64 or ARM64) who open the package index to find a program and copy the command that installs it (`txapm install <alias>`), or the one-line command that installs TXA itself. Secondary: package contributors and the moderator checking what is published and what is waiting for review. Most visitors read Vietnamese; English is a full second language.

## Product Purpose

TXA installs Windows software from one command: it downloads the installer from the publisher's official site, verifies the digital signature and SHA-256, then installs silently. The index page is the public shop window of that repository (`TXAVL/txa-repo`): it lists every published package with its latest version, install command and summary, and links to the machine-readable API. Success = a visitor finds a package in seconds and copies a working command.

## Positioning

A package repository whose every release passes a 14-step validator (including size, SHA-256 and Authenticode checks) before it is published, with Vietnamese and English metadata for every package.

## Operating Context

The page is generated, not hand-edited: the "TXA Publish API" workflow rebuilds it on every push that touches manifests, every 6 hours, and when review pull requests change. Data comes from `api/txa/v1/index.json` (59 packages at the time of writing), `api/txa/v1/pending.json` (releases waiting for review) and `api/txa/v1/packages/<Id>.json`. Each package has an id (e.g. `TXAVL.Python`), a latest version, an alias used in the install command, and per-language summaries (`vi-VN`, `en-US`).

## Capabilities and Constraints

- Search by name, package id, alias or summary, in either language; live count of matches.
- Language switch Vietnamese / English, remembered in the browser.
- Copy-to-clipboard for the install command and for the TXA install one-liner `irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1 | iex`.
- Links: `index.json`, `pending.json`, GitHub repository, each package's JSON.
- Shows the generation timestamp (UTC).
- Must stay a static site on GitHub Pages; no server, no secrets at runtime.
- Undecided: whether to show per-package detail pages, the pending list on the page, and the install count or categories (none of that data exists yet).

## Brand Commitments

Name: TXA (Kho gói phần mềm TXA / TXA Package Index). Bilingual vi/en. CLI names `txapm`, `txacli`, `txacreate`, `txaci`. No logo or brand colours defined yet.

## Evidence on Hand

Real data only: the 59 packages in `manifests/t/TXAVL/` and the generated JSON API. No testimonials, user counts, download statistics or press exist; none may be invented.

## Product Principles

1. The command is the product: finding a package and copying its install command takes no more than a search and a click.
2. Trustworthy by showing real facts (version, id, generation time), never invented numbers.
3. Vietnamese first, English equal: neither language is a translation afterthought.
4. Stays fast and readable with 60 to several hundred packages and works without a server.
5. Everything on the page comes from the generated data, so a package added to `manifests/` appears with no manual edit.

## Accessibility & Inclusion

Keyboard-operable search, language switch and copy actions with visible focus; sufficient contrast in both light and dark colour schemes (the current page already follows `prefers-color-scheme`); the copy action must give visible confirmation, not only a tooltip.
