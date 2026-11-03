"""Fork txa-repo, create `<Id>-<Version>` branch, commit the cards in one commit, open the PR."""
from __future__ import annotations

import time
from dataclasses import dataclass

from txa.core import retention
from txa.core.github import GitHub, GitHubError
from txa.core.manifest import package_dir


@dataclass
class Submission:
    url: str
    number: int
    branch: str
    head_repo: str


def find_open_pr(gh: GitHub, upstream: str, package_id: str, version: str) -> str | None:
    needle = f"{package_id} {version}"
    for pr in gh.paginate(f"repos/{upstream}/pulls", {"state": "open"}):
        if needle in pr["title"]:
            return pr["html_url"]
    return None


def _wait_for_branch(gh: GitHub, repo: str, branch: str, seconds: int = 90) -> str:
    deadline = time.monotonic() + seconds
    while True:
        response = gh.request("GET", f"repos/{repo}/git/ref/heads/{branch}", ok=(404, 409))
        if response.status_code == 200:
            return response.json()["object"]["sha"]
        if time.monotonic() > deadline:
            raise GitHubError(response.status_code, f"{repo} is still not ready after {seconds}s")
        time.sleep(3)


def _free_branch(gh: GitHub, repo: str, name: str) -> str:
    candidate, n = name, 1
    while gh.request("GET", f"repos/{repo}/git/ref/heads/{candidate}", ok=(404,)).status_code != 404:
        n += 1
        candidate = f"{name}-{n}"
    return candidate


def stale_paths(gh: GitHub, repo: str, base_tree: str, package_id: str, version: str) -> list[str]:
    """Files of the oldest releases that must go so that, with ``version`` added, only the newest KEEP remain."""
    prefix = package_dir(package_id).rstrip("/") + "/"
    try:
        listing = gh.get(f"repos/{repo}/git/trees/{base_tree}", params={"recursive": "1"})
    except GitHubError:
        return []
    by_version: dict[str, list[str]] = {}
    for entry in listing.get("tree", []):
        if entry.get("type") == "blob" and entry["path"].startswith(prefix):
            by_version.setdefault(entry["path"][len(prefix):].split("/")[0], []).append(entry["path"])
    by_version.setdefault(version, [])
    return [path for stale in retention.stale_versions(list(by_version), protect=version) for path in by_version[stale]]


def submit(gh: GitHub, upstream: str, login: str, package_id: str, version: str, files: dict[str, str],
           title: str, body: str, direct: bool = False, log=print) -> Submission:
    """`files` maps repo-relative paths to file contents."""
    repo = gh.get(f"repos/{upstream}")
    base_branch = repo["default_branch"]
    owner = upstream.split("/", 1)[0]
    use_fork = not (direct or owner.lower() == login.lower())

    if use_fork:
        log(f"→ forking {upstream} (reuses your existing fork)")
        fork = gh.post(f"repos/{upstream}/forks", json={"default_branch_only": True})
        head_repo = fork["full_name"]
        _wait_for_branch(gh, head_repo, base_branch)
        try:
            gh.post(f"repos/{head_repo}/merge-upstream", json={"branch": base_branch})
            log(f"→ fork {head_repo} synced with {upstream}@{base_branch}")
        except GitHubError:
            # Fork sync may be skipped if upstream workflows changed without workflow scope or if diverged
            pass
    else:
        head_repo = upstream
        log(f"→ you can push to {upstream} - creating the branch there directly")

    base_sha = _wait_for_branch(gh, head_repo, base_branch, 30)
    base_tree = gh.get(f"repos/{head_repo}/git/commits/{base_sha}")["tree"]["sha"]
    entries = [{"path": path, "mode": "100644", "type": "blob", "content": text} for path, text in sorted(files.items())]
    dropped = stale_paths(gh, head_repo, base_tree, package_id, version)
    entries += [{"path": path, "mode": "100644", "type": "blob", "sha": None} for path in dropped]
    if dropped:
        log(f"→ the repository keeps the newest {retention.KEEP} versions - removing the oldest ({len(dropped)} file(s))")
    tree = gh.post(f"repos/{head_repo}/git/trees", json={"base_tree": base_tree, "tree": entries})
    commit = gh.post(f"repos/{head_repo}/git/commits", json={
        "message": f"{title}\n\nSubmitted with txacreate.",
        "tree": tree["sha"],
        "parents": [base_sha],
    })
    branch = _free_branch(gh, head_repo, f"{package_id}-{version}")
    gh.post(f"repos/{head_repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    log(f"→ committed {len(files)} card(s) to {head_repo}@{branch} ({commit['sha'][:10]})")

    payload = {"title": title, "base": base_branch, "body": body,
               "head": f"{head_repo.split('/', 1)[0]}:{branch}" if use_fork else branch}
    if use_fork:
        payload["maintainer_can_modify"] = True
    pr = gh.post(f"repos/{upstream}/pulls", json=payload)
    return Submission(pr["html_url"], pr["number"], branch, head_repo)
