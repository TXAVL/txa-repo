"""Contributor Agreement & PR Checklist verification.

The bot asks the author to:
1. Complete and tick the required checkboxes in the PR description.
2. Accept the TXA Contributor Agreement by commenting "@txa-repo agree" (or "@txa-bot agree").

For new packages, both the checklist and agreement comment are strictly required.
Labels follow the steps: txa:needs-agreement the moment the PR opens, txa:needs-confirmation once the agreement
comment is in (the checklist is still open), then txa:validating when both are done. Nothing else runs before that:
the 14 steps, the live progress and the gate all wait for the `signed=` comment this module writes.
"""
from __future__ import annotations

import re

import os

from txa.constants import AGREEMENT_HOME, AGREEMENT_SOURCE, AGREEMENT_URL, AGREEMENT_VERSION, LABELS, STATUS_CONTEXT
from txa.core.github import GitHub, GitHubError

MARK = "<!-- txa-bot:agreement"
PHRASE = "@txa-repo agree"
_PHRASE_RE = re.compile(r'^\s*@?(?:txa-repo|txa-bot)\s+agree(?:\s+company\s*=\s*"([^"\r\n]{1,80})")?\s*[.!]?\s*$', re.I)
LABEL = LABELS["agree"][0]
CONTEXT = "txa/agreement"
# Like winget-pkgs: whoever accepted the agreement once (same version) on a merged pull request of this repository or of a
# trusted one is remembered and is not asked to comment again. The checklist is still required on every pull request.
# Set to False to make everyone comment on every pull request.
RECOGNISE_RETURNING = True
_VERSION_RE = re.compile(r"<!-- txa-bot:agreement-version=([\w.\-]+) -->")


def trusted_repos(repo: str) -> list[str]:
    """This repository plus the trusted ones: AGREEMENT_HOME by default, or TXA_AGREEMENT_REPOS (comma separated)."""
    extra = [r.strip() for r in os.environ.get("TXA_AGREEMENT_REPOS", AGREEMENT_HOME).split(",") if r.strip()]
    return list(dict.fromkeys([repo, *extra]))


def pending_checklist_items(body: str | None) -> list[str]:
    """Returns list of pending required checklist items from PR body."""
    items: list[str] = []
    for line in (body or "").splitlines():
        m = re.match(r"^\s*[-*+]\s*\[\s*\]\s+(.*)$", line)
        if m:
            text = m.group(1).strip()
            # Ignore optional items
            if "(if applicable)" in text.lower() or text.lower().startswith("resolves #"):
                continue
            items.append(text)
    return items


def _needs_action_text(login: str, pending_items: list[str], needs_agree: bool, is_new_pkg: bool, on_file: str = "") -> str:
    lines = [
        f"Hello @{login},", "",
        "Thank you for opening this pull request! The automatic checks do **not** start by themselves. "
        "They start only after both steps below are done, in this order:", "",
    ]
    if needs_agree:
        new_pkg_note = " *(Mandatory for new packages)*" if is_new_pkg else ""
        lines.append(f"1. ✍️ **Accept the TXA Contributor Agreement**:{new_pkg_note}")
        lines.append(f"   Read it first: [Contributor Agreement]({AGREEMENT_URL}) ([source]({AGREEMENT_SOURCE})). "
                     "It says you may submit this manifest, that the installer is the vendor's own official download, "
                     "and what the maintainers may do with it.")
        lines.append(f"   To accept, reply to this pull request with a single comment:\n   ```\n   {PHRASE}\n   ```")
        lines.append(f"   *(Contributing for a company? Use `{PHRASE} company=\"Example Ltd\"`)*\n")
    else:
        if on_file:
            lines.append(f"1. ✅ **Contributor Agreement already on file** (you accepted it on {on_file}; "
                         f"[read it again]({AGREEMENT_URL})). You do not need to comment again.\n")
        else:
            lines.append("1. ✅ **Contributor Agreement accepted.**\n")
    if pending_items:
        lines.append("2. 🔲 **Tick the PR checklist**:")
        lines.append("   Tick every required box in the pull request description above "
                     "(edit the description or click the boxes directly on GitHub). Still open:")
        for item in pending_items:
            lines.append(f"   - [ ] {item}")
        lines.append("")
    else:
        lines.append("2. ✅ **PR checklist complete.**\n")

    if not pending_items and needs_agree:
        lines.append("✓ *The checklist is complete.* Waiting for your agreement comment above.\n")
    elif pending_items and not needs_agree:
        lines.append("✓ *Agreement confirmed.* Waiting for you to tick the remaining boxes above.\n")
    lines.append("When both are done the bot starts the 14 checks and the live progress, then the labelling and merge gate.\n")
    lines.append("<sub>Template: txabot/needsAgreement</sub>")
    return "\n".join(lines)


def _signed_text(login: str, how: str = "", company: str = "") -> str:
    extra = f" ({how})" if how else ""
    firm = f" on behalf of **{company}**" if company else ""
    return (f"{MARK} signed={login} -->\n<!-- txa-bot:agreement-version={AGREEMENT_VERSION} -->\n✅ **Contributor Agreement & Checklist accepted** by @{login}{firm}{extra}. "
            "Thank you - the automatic checks start now.\n\n<sub>Template: txabot/agreementSigned</sub>")


def find(gh: GitHub, repo: str, number: int) -> dict | None:
    for comment in gh.paginate(f"repos/{repo}/issues/{number}/comments"):
        if comment["body"].startswith(MARK) and comment["user"]["type"] == "Bot":
            return comment
    return None


def _is_signed_comment(comment: dict | None, login: str) -> bool:
    return bool(comment) and f"signed={login} -->" in comment["body"].split("\n", 1)[0]


def _extract_agreed(comment: dict | None, login: str) -> tuple[bool, str]:
    if not comment:
        return False, ""
    header = comment["body"].split("\n", 1)[0]
    if f"signed={login}" in header:
        return True, ""
    m = re.search(rf'agreed={re.escape(login)}(?:\s+company="([^"]+)")?', header)
    if m:
        return True, m.group(1) or ""
    return False, ""


def is_signed(gh: GitHub, repo: str, pr: dict) -> bool:
    return _is_signed_comment(find(gh, repo, pr["number"]), pr["user"]["login"])


def _comment_version(comment: dict) -> str:
    m = _VERSION_RE.search(comment["body"])
    return m.group(1) if m else "1.0"  # comments written before versions existed are version 1.0


def _returning(gh: GitHub, repo: str, login: str) -> str:
    """'owner/repo#n' of a merged pull request where this person accepted the current agreement, or ''."""
    for source in trusted_repos(repo):
        try:
            data = gh.get("search/issues", params={"q": f"repo:{source} is:pr is:merged author:{login}", "per_page": 10})
            for item in data.get("items", []):
                comment = find(gh, source, item["number"])
                if _is_signed_comment(comment, login) and _comment_version(comment) == AGREEMENT_VERSION:
                    return f"{source}#{item['number']}"
        except GitHubError:
            continue
    return ""


def _set_status(gh: GitHub, repo: str, pr: dict, signed: bool, desc: str = "") -> None:
    """``txa/agreement`` shows the step in the merge box; while it is open the required status is held too."""
    sha = pr["head"]["sha"]
    default_desc = "Contributor Agreement accepted" if signed else f"Check PR checklist & comment {PHRASE}"
    gh.post(f"repos/{repo}/statuses/{sha}", json={
        "state": "success" if signed else "pending", "context": CONTEXT,
        "description": desc or default_desc})
    if not signed:
        gh.post(f"repos/{repo}/statuses/{sha}", json={
            "state": "pending", "context": STATUS_CONTEXT,
            "description": "Waiting for author to complete checklist & accept agreement"})


def process(gh: GitHub, repo: str, number: int, comment_id: int | None = None) -> int:
    """Process checklist and agreement verification for a pull request."""
    pr = gh.get(f"repos/{repo}/pulls/{number}")
    if pr["state"] != "open":
        return 0
    author = pr["user"]["login"]
    title = (pr.get("title") or "").strip().lower()
    body = pr.get("body") or ""
    is_new_pkg = title.startswith("new package") or "new package:" in body.lower()

    current = {label["name"] for label in pr.get("labels", [])}
    bot = find(gh, repo, number)
    if _is_signed_comment(bot, author):
        print(f"agreement: PR #{number} already accepted - nothing to do")
        return 0

    how, company = "", ""
    comment_agreed = False
    if comment_id:
        try:
            comment = gh.get(f"repos/{repo}/issues/comments/{comment_id}")
        except GitHubError:
            comment = None
        if comment and comment.get("user", {}).get("login") == author:
            match = _PHRASE_RE.match(comment.get("body", ""))
            if match:
                gh.delete(f"repos/{repo}/issues/comments/{comment_id}", ok=(404,))
                comment_agreed = True
                company = " ".join((match.group(1) or "").split())

    prior_agreed, prior_company = _extract_agreed(bot, author)
    if comment_agreed:
        has_agreed = True
    elif prior_agreed:
        has_agreed = True
        if not company:
            company = prior_company
    else:
        has_agreed = False

    # Automation (the scheduled auto-update, if it ever opens a pull request as the bot) has no one to ask.
    if not has_agreed and pr["user"].get("type") == "Bot":
        has_agreed, how = True, "automation"
    # Someone who already accepted this agreement version on a merged pull request (here or in a trusted repo).
    on_file = ""
    if RECOGNISE_RETURNING and not has_agreed:
        ref = _returning(gh, repo, author)
        if ref:
            has_agreed, how, on_file = True, f"already accepted on {ref}", ref

    # Verify checklist checkboxes in PR body
    pending = pending_checklist_items(body)
    checklist_done = (len(pending) == 0)

    signed = checklist_done and has_agreed

    from txa.ci.gate import set_labels  # late: gate imports this module

    names = {key: LABELS[key][0] for key in ("agree", "confirm", "validating", "verified", "fix", "review", "approved")}
    in_flight = {names[k] for k in ("validating", "verified", "fix", "review", "approved")}

    if signed:
        signed_body = _signed_text(author, how, company)
        if bot and "signed=" not in bot["body"].split("\n", 1)[0]:
            gh.patch(f"repos/{repo}/issues/comments/{bot['id']}", json={"body": signed_body})
        elif not bot:
            gh.post(f"repos/{repo}/issues/{number}/comments", json={"body": signed_body})
        # both steps are done: the waiting labels go, the run starts and "TXA Progress" adds txa:validating
        set_labels(gh, repo, number, current, add=set(), remove={names["agree"], names["confirm"]})
        _set_status(gh, repo, pr, True)
        _rerun_gate(gh, repo, pr)
        print(f"agreement: PR #{number} accepted by {author} (checklist complete and agreed) - checks start now")
        return 0

    # Still waiting. Step 1: the agreement. Step 2: the checklist.
    header = f"{MARK} pending author={author}{f' agreed={author}' if has_agreed else ''}{f' company=\"{company}\"' if company else ''} -->"
    action_body = f"{header}\n" + _needs_action_text(author, pending, not has_agreed, is_new_pkg, on_file)
    if bot:
        gh.patch(f"repos/{repo}/issues/comments/{bot['id']}", json={"body": action_body})
    else:
        gh.post(f"repos/{repo}/issues/{number}/comments", json={"body": action_body})

    if has_agreed:
        # the comment is in: needs-agreement goes, needs-confirmation (tick the boxes) comes
        set_labels(gh, repo, number, current, add={names["confirm"]}, remove=in_flight | {names["agree"]})
        _set_status(gh, repo, pr, False, "Agreement accepted - tick the checklist")
    else:
        set_labels(gh, repo, number, current, add={names["agree"]}, remove=in_flight | {names["confirm"]})
        _set_status(gh, repo, pr, False, f"Read the Contributor Agreement, then comment {PHRASE}")
    print(f"agreement: PR #{number} waiting for {author} (pending={len(pending)}, agreed={has_agreed})")
    return 0


def _rerun_gate(gh: GitHub, repo: str, pr: dict) -> None:
    """The agreement is signed: now the 16 steps may start (re-run a skipped validation, start the live checklist)."""
    from txa.ci.progress import find_validate_run

    sha = pr["head"]["sha"]
    try:
        run = find_validate_run(gh, repo, sha)
        if run and run.get("status") == "completed":
            gh.post(f"repos/{repo}/actions/runs/{run['id']}/rerun")
    except GitHubError as exc:
        print(f"::warning::could not re-run the checks ({exc})")
    try:
        gh.post(f"repos/{repo}/actions/workflows/txa-progress.yml/dispatches",
                json={"ref": pr["base"]["ref"], "inputs": {"pr": str(pr["number"]), "sha": sha}})
    except GitHubError as exc:
        print(f"::warning::could not start the live checklist ({exc})")
