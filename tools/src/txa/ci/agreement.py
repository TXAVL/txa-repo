"""Contributor Agreement & PR Checklist verification.

The bot asks the author to:
1. Complete and tick the required checkboxes in the PR description.
2. Accept the TXA Contributor Agreement by commenting "@txa-repo agree" (or "@txa-bot agree").

For new packages, both the checklist and agreement comment are strictly required.
Once both requirements are satisfied, the bot removes the agreement comment,
updates its own comment with `signed=<author>`, removes `txa:needs-agreement`,
sets `txa/agreement` to success, and triggers the 16 validation checks.
"""
from __future__ import annotations

import re

from txa.constants import LABELS, STATUS_CONTEXT
from txa.core.github import GitHub, GitHubError

MARK = "<!-- txa-bot:agreement"
PHRASE = "@txa-repo agree"
_PHRASE_RE = re.compile(r'^\s*@?(?:txa-repo|txa-bot)\s+agree(?:\s+company\s*=\s*"([^"\r\n]{1,80})")?\s*[.!]?\s*$', re.I)
LABEL = LABELS["agree"][0]
CONTEXT = "txa/agreement"
EXEMPT = {"MEMBER", "COLLABORATOR"}  # For updates only; new packages always require explicit agreement


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


def _needs_action_text(login: str, pending_items: list[str], needs_agree: bool, is_new_pkg: bool) -> str:
    lines = [
        f"Hello @{login},", "",
        "Thank you for opening this pull request! Before the automatic 16-step verification checks can proceed, "
        "the following requirements must be completed:", "",
    ]
    step_num = 1
    if pending_items:
        lines.append(f"{step_num}. 🔲 **Complete the PR Checklist**:")
        lines.append("   Please tick all required checkboxes in the pull request description above "
                     "(edit the description or click the checkboxes directly on GitHub):")
        for item in pending_items:
            lines.append(f"   - [ ] {item}")
        lines.append("")
        step_num += 1

    if needs_agree:
        new_pkg_note = " *(Mandatory for new packages)*" if is_new_pkg else ""
        lines.append(f"{step_num}. ✍️ **TXA Contributor Agreement**:{new_pkg_note}")
        lines.append("   You confirm that you have the right to submit this manifest, that the installer is the "
                     "vendor's own official download, and that the package follows repository policy.")
        lines.append(f"   To accept, reply to this pull request with a single comment:\n   ```\n   {PHRASE}\n   ```")
        lines.append(f"   *(Contributing for a company? Use `{PHRASE} company=\"Example Ltd\"`)*\n")
        step_num += 1

    if not pending_items and needs_agree:
        lines.append("✓ *The PR checklist is complete!* Waiting for your agreement comment above.\n")
    elif pending_items and not needs_agree:
        lines.append("✓ *Contributor Agreement confirmed!* Waiting for you to check the remaining items in the PR checklist above.\n")

    lines.append("Once all requirements are satisfied, the bot will accept the agreement and automatically run all 16 pipeline checks.\n")
    lines.append("<sub>Template: txabot/needsAgreement</sub>")
    return "\n".join(lines)


def _signed_text(login: str, how: str = "", company: str = "") -> str:
    extra = f" ({how})" if how else ""
    firm = f" on behalf of **{company}**" if company else ""
    return (f"{MARK} signed={login} -->\n✅ **Contributor Agreement & Checklist accepted** by @{login}{firm}{extra}. "
            "Thank you - the automatic 16 checks go on.\n\n<sub>Template: txabot/agreementSigned</sub>")


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


def _returning(gh: GitHub, repo: str, login: str) -> bool:
    """Someone who accepted the agreement on a pull request that was merged has signed once for good."""
    try:
        data = gh.get("search/issues", params={"q": f"repo:{repo} is:pr is:merged author:{login}", "per_page": 5})
        return any(_is_signed_comment(find(gh, repo, item["number"]), login) for item in data.get("items", []))
    except GitHubError:
        return False


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

    # New packages ALWAYS require explicit agreement comment from the author.
    # For existing package updates, previous agreements or maintainer status can be recognized.
    if not is_new_pkg and not has_agreed:
        if pr.get("author_association") in EXEMPT:
            has_agreed, how = True, "maintainer, exempt"
        elif _returning(gh, repo, author):
            has_agreed, how = True, "agreed on an earlier pull request"

    # Verify checklist checkboxes in PR body
    pending = pending_checklist_items(body)
    checklist_done = (len(pending) == 0)

    signed = checklist_done and has_agreed

    from txa.ci.gate import set_labels  # late: gate imports this module

    if signed:
        signed_body = _signed_text(author, how, company)
        if bot and "signed=" not in bot["body"].split("\n", 1)[0]:
            gh.patch(f"repos/{repo}/issues/comments/{bot['id']}", json={"body": signed_body})
        elif not bot:
            gh.post(f"repos/{repo}/issues/{number}/comments", json={"body": signed_body})
        set_labels(gh, repo, number, current, add=set(), remove={LABEL})
        _set_status(gh, repo, pr, True)
        _rerun_gate(gh, repo, pr)
        print(f"agreement: PR #{number} accepted by {author} (checklist complete and agreed)")
        return 0

    # Still waiting for checklist and/or agreement
    header = f"{MARK} pending author={author}{f' agreed={author}' if has_agreed else ''}{f' company=\"{company}\"' if company else ''} -->"
    action_body = f"{header}\n" + _needs_action_text(author, pending, not has_agreed, is_new_pkg)
    if bot:
        gh.patch(f"repos/{repo}/issues/comments/{bot['id']}", json={"body": action_body})
    else:
        gh.post(f"repos/{repo}/issues/{number}/comments", json={"body": action_body})

    stale = {LABELS[key][0] for key in ("validating", "verified", "fix", "review", "approved", "confirm")}
    set_labels(gh, repo, number, current, add={LABEL}, remove=stale)
    _set_status(gh, repo, pr, False, "Checklist or agreement pending")
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
