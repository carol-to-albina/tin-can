"""Concrete git shell. Pull ff-only, commit owned paths, push, blame, public probe."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .types import ConflictError, ProtocolError, Seq

GITHUB_API_ENV = "TINCAN_GITHUB_API"
GITHUB_API = "https://api.github.com"
API_TIMEOUT_SEC = 5


@dataclass(frozen=True)
class GitAuthor:
    name: str
    email: str


UNCOMMITTED = GitAuthor("", "")
"""author_of_line result for a line that no commit introduced yet."""


class GitMissing(ProtocolError):
    """The git binary is not on PATH."""


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    if not Path(root).is_dir():
        raise ProtocolError(f"{root} is not a directory")
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitMissing("git is not installed") from exc


def _why(run: subprocess.CompletedProcess[str]) -> str:
    return run.stderr.strip() or run.stdout.strip() or "git failed"


def _head_branch(root: Path) -> str:
    run = _run(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    return run.stdout.strip() if run.returncode == 0 else ""


def _upstream(root: Path) -> str:
    """The tracked ref, empty when it is unset or the remote has no commit yet."""
    run = _run(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    return run.stdout.strip() if run.returncode == 0 else ""


def _pathspec(root: Path, path: Path) -> str:
    inside = Path(path) if Path(path).is_absolute() else Path(root) / path
    try:
        return str(inside.resolve().relative_to(Path(root).resolve()))
    except ValueError:
        raise ProtocolError(f"{path} is outside {root}") from None


def _tracked(root: Path, spec: str) -> bool:
    return _run(root, "ls-files", "--error-unmatch", "--", spec).returncode == 0


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def _nonblank(text: str) -> int:
    return sum(1 for raw in text.splitlines() if raw.strip())


def _null_oid(rev: str) -> bool:
    return bool(rev) and set(rev) == {"0"}


def _github_slug(url: str) -> str:
    """owner/repo for a github.com remote. Empty for any other host."""
    raw = url.strip()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urlparse(raw)
        host, path = parsed.hostname or "", parsed.path
    else:
        head, _, path = raw.partition(":")
        host = head.rpartition("@")[2]
    if host.lower().removeprefix("www.") != "github.com":
        return ""
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) != 2:
        return ""
    return f"{parts[0]}/{parts[1].removesuffix('.git')}"


def _line_of_seq(path: Path, seq: Seq) -> int:
    """The 1-based file line holding that seq, or 0 when the file has no such line."""
    seen = 0
    for number, raw in enumerate(_read(path).splitlines(), start=1):
        if not raw.strip():
            continue
        seen += 1
        if seen == seq:
            return number
    return 0


def _porcelain_author(text: str) -> GitAuthor:
    if _null_oid(text.split(" ", 1)[0]):
        return UNCOMMITTED
    name = ""
    email = ""
    for raw in text.splitlines():
        if raw.startswith("author ") and not name:
            name = raw[len("author ") :].strip()
        elif raw.startswith("author-mail ") and not email:
            email = raw[len("author-mail ") :].strip().strip("<>")
    return GitAuthor(name, email)


def _remote(root: Path) -> str:
    run = _run(root, "remote")
    names = run.stdout.split() if run.returncode == 0 else []
    if "origin" in names:
        return "origin"
    return names[0] if names else ""


def require_repo(root: Path) -> None:
    run = _run(root, "rev-parse", "--is-inside-work-tree")
    if run.returncode != 0 or run.stdout.strip() != "true":
        raise ProtocolError(f"{root} is not a git work tree")


def require_branch(root: Path, branch: str) -> None:
    """Die unless HEAD equals the room branch."""
    require_repo(root)
    head = _head_branch(root)
    if head != branch:
        raise ProtocolError(f"HEAD is {head or 'detached'}; checkout {branch}")


def pull(root: Path) -> None:
    """git pull --ff-only. ConflictError on non-fast-forward."""
    require_repo(root)
    if _upstream(root):
        run = _run(root, "pull", "--ff-only")
        if run.returncode != 0:
            raise ConflictError(_why(run))
        return
    branch = _head_branch(root)
    if not branch:
        raise ProtocolError("HEAD is detached; cannot pull")
    remote = _remote(root)
    if not remote:
        return
    listing = _run(root, "ls-remote", "--heads", remote, branch)
    if listing.returncode != 0 or not listing.stdout.strip():
        return
    raise ConflictError(
        f"{remote}/{branch} exists and {branch} has no upstream; "
        f"push with git push -u {remote} {branch} or clone the branch"
    )


def commit_owned(root: Path, paths: list[Path], message: str, author: GitAuthor) -> None:
    """git add and git commit --only those paths as author.

    author comes from room.json, not from git config. No-op if the index is
    unchanged. Same dirty bytes become the same commit.
    """
    require_repo(root)
    specs = [
        spec
        for spec in (_pathspec(root, p) for p in paths)
        if (root / spec).exists() or _tracked(root, spec)
    ]
    if not specs:
        return
    add = _run(root, "add", "--", *specs)
    if add.returncode != 0:
        raise ProtocolError(_why(add))
    staged = _run(root, "diff", "--cached", "--quiet", "--", *specs)
    if staged.returncode == 0:
        return
    commit = _run(
        root,
        "-c",
        f"user.name={author.name}",
        "-c",
        f"user.email={author.email}",
        "commit",
        "--only",
        "-m",
        message,
        "--",
        *specs,
    )
    if commit.returncode != 0:
        raise ProtocolError(_why(commit))


def push(root: Path) -> None:
    require_repo(root)
    if _upstream(root):
        run = _run(root, "push")
    else:
        branch = _head_branch(root)
        if not branch:
            raise ProtocolError("HEAD is detached; cannot push")
        remote = _remote(root)
        if not remote:
            raise ProtocolError("no git remote; cannot push")
        run = _run(root, "push", "--set-upstream", remote, branch)
    if run.returncode != 0:
        raise ConflictError(_why(run))


def author_of_line(root: Path, path: Path, seq: Seq) -> GitAuthor:
    """Blame the line that carries seq. UNCOMMITTED when no commit holds it yet."""
    require_repo(root)
    spec = _pathspec(root, path)
    line = _line_of_seq(root / spec, seq)
    if not line:
        raise ProtocolError(f"{spec} has no line for seq {seq}")
    run = _run(root, "blame", "--line-porcelain", "-L", f"{line},{line}", "--", spec)
    if run.returncode != 0:
        if _run(root, "cat-file", "-e", f"HEAD:./{spec}").returncode == 0:
            raise ProtocolError(_why(run))
        return UNCOMMITTED
    return _porcelain_author(run.stdout)


def added_since(root: Path, path: Path, before_rev: str) -> list[int]:
    """The seqs in the working file that before_rev did not carry.

    An empty or all-zero rev is a first push, so the whole file is new.
    """
    require_repo(root)
    spec = _pathspec(root, path)
    rev = before_rev.strip()
    before = 0
    if rev and not _null_oid(rev):
        known = _run(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if known.returncode != 0:
            raise ProtocolError(f"unknown revision {rev}")
        shown = _run(root, "show", f"{rev}:./{spec}")
        before = _nonblank(shown.stdout) if shown.returncode == 0 else 0
    # seq is the non-blank line index, so every index past the old count is new.
    return list(range(before + 1, _nonblank(_read(root / spec)) + 1))


def remote_url(root: Path) -> str:
    require_repo(root)
    remote = _remote(root)
    if not remote:
        return ""
    run = _run(root, "remote", "get-url", remote)
    return run.stdout.strip() if run.returncode == 0 else ""


def remote_is_public(root: Path) -> bool:
    """True only when the GitHub API answers private false. Anything else is private."""
    slug = _github_slug(remote_url(root))
    if not slug:
        return False
    base = (os.environ.get(GITHUB_API_ENV) or GITHUB_API).rstrip("/")
    try:
        request = urllib.request.Request(
            f"{base}/repos/{slug}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "tincan"},
        )
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SEC) as answer:
            body = json.loads(answer.read().decode("utf-8"))
    except (OSError, ValueError, TimeoutError) as failure:
        if isinstance(failure, urllib.error.HTTPError):
            failure.close()  # an error status arrives as an open response
        return False
    return isinstance(body, dict) and body.get("private") is False
