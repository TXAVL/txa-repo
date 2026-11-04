# TXA Contributor Agreement

**Version 1.0** · effective 2026-11-05 · applies to [`TXAVL/txa-repo`](https://github.com/TXAVL/txa-repo) and to any other repository that runs the TXA bot and lists this one as a trusted repository.

This is the document you confirm when you answer the bot with a single comment, `@txa-repo agree`. It is short and written to be readable. Read all of it before agreeing. **The bot does not run any check until you have agreed and ticked the whole checklist in the PR description**, so you have time to read.

---

## 1. What this repository does, so you know what you are contributing to

`txa-repo` is a Windows software package repository for the `txapm` tool. A package is **three YAML manifest cards** (`core`, `build`, `about`) in `manifests/t/TXAVL/<Name>/<Version>/`. A manifest **does not contain the software**: it only points to the publisher's official download link, with the SHA-256, size, CPU architecture and silent-install switches. Users run `txapm install <package>`; TXA downloads the installer from the publisher's site, checks the SHA-256, then installs it. TXA does not store or distribute installers.

Each package keeps its **newest 10 versions**. Adding a new version removes the oldest from the repository (not from the git history).

## 2. What you confirm when you comment `@txa-repo agree`

1. **You have the right to submit.** You wrote the files in the PR, or you are allowed to contribute them, and sending them does not infringe anyone's rights (copyright, trademark, confidentiality agreements, the software's license).
2. **The installer is the official one.** Every `source.url` is an **HTTPS** link to the software publisher's official download (or its official release channel, such as the project's GitHub Releases). Not a modified build, a repackaged copy, a cracked version, or an intermediary site that is not the publisher.
3. **The information is true.** The name, publisher, license (SPDX id), SHA-256, size, CPU architecture, minimum Windows version and silent-install switches are correct to the best of your knowledge. You took the SHA-256 and size from the real downloaded file, you did not guess.
4. **It does no harm.** You are not knowingly adding malware, hidden advertising, unauthorized data collection, or install switches that change the system beyond installing the software. You are not using a manifest to attack TXA users or the repository's infrastructure.
5. **It follows the repository policy.** The package fits the [manifest specification](manifest-schema.md) and `policy.txa.yaml`: software for Windows 10 (1809) or later, an installer of at most 2048 MB, a namespace on the allowed list (currently `TXAVL`), nothing illegal.
6. **You did the self-checks** listed in the PR checklist (no duplicate PR, only one manifest changed, `txacreate validate`, tried `txapm install --manifest`, valid schema) and ticked each box yourself.

## 3. License for what you contribute

What you contribute (the manifest files, and if any, code, documentation or translations) is licensed under the **MIT license**, the repository's own license (see the [`LICENSE`](https://github.com/TXAVL/txa-repo/blob/main/LICENSE) file). By agreeing you allow anyone to use, copy, modify, merge and distribute that contribution under the MIT terms, and you allow the repository owner to publish it in this repository, in the `txa.v1` REST API and on the index page.

This does **not** cover the software a manifest describes: the software, its name, logo and trademarks remain with their owners. The repository uses names and logos only to identify the software.

## 4. What the maintainers may do

The maintainers are the code owners in `.github/CODEOWNERS` (currently `@TXAVL` and `@TXADEV`). They may:

- review, ask for changes to, reject or close your PR without a long explanation;
- edit, translate, reformat or merge your manifest to keep the repository consistent;
- update a published package by hand or with automation (a new version, a new SHA-256);
- **remove** a published package or version if it is wrong, dangerous, infringing, or the publisher asks for it.

If you are the publisher and want a package removed or fixed, or you found a dangerous package, open an [issue](https://github.com/TXAVL/txa-repo/issues) or report it privately through GitHub's Security Advisory feature on the repository. The maintainers will handle it.

## 5. What the bot records

When you agree, the bot records **your GitHub account name** and the **agreement version** (`v=1.0`) in a hidden comment on the PR (`signed=<name> v=1.0`) and in the `txa/agreement` status. If you contribute for a company, the company name you type is recorded too. The bot does **not** collect your email, address or any other personal data. This trace is as public as any comment on a public PR.

## 6. How to agree, and how the bot remembers you

The flow is like `winget-pkgs`: **agree once, the bot remembers**.

1. You open a PR. The bot comments at once, adds the `txa:needs-agreement` label, and **runs no step**.
2. You reply with exactly one comment, `@txa-repo agree` (or `@txa-repo agree company="Company name"` when contributing for a company, which also confirms you have the authority to bind that company). Only the comment of the PR author counts. The bot deletes it, removes `txa:needs-agreement` and adds `txa:needs-confirmation`.
3. You tick every box in the PR description. Only when you have agreed **and** ticked everything does the bot run the 14 checks and the 16 gate checks; the label becomes `txa:validating`.

**Next time:** if you have agreed and had at least one PR merged in this repository or in any repository on the trusted list (by default `TXAVL/txa-repo`), and the agreement has not changed version, the bot **already has you on file**: a new PR goes straight to `txa:needs-confirmation` and you do not comment again. You **still tick the checklist** of every PR before the bot runs. Maintainers are not exempt: they must have agreed once like everyone else.

To stop the bot remembering you, simply stop contributing; to withdraw a merged contribution, open an issue as in section 4.

## 7. When the agreement changes

The agreement has a version number. When the maintainers change something important they raise the version, record it in the history below, and the bot will **ask you to agree again** on your next PR. Contributions you already sent stay under the version you agreed to.

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-05 | First version. |

## 8. Disclaimer

The repository and contributions are provided "as is", without warranty, as the MIT license says. The maintainers are not responsible for the third-party software a manifest points to. This document was written by the repository maintainers to make the contribution rules clear and is **not legal advice**. If your organization needs its own legal assurance, contact the owner through an issue before submitting.
