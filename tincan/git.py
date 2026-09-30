"""Concrete git shell. Pull ff-only, commit owned paths, push, blame, public probe."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .types import ConflictError, ProtocolError, Seq


@dataclass(frozen=True)
class GitAuthor:
    name: str
    email: str


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
    remote = _remote(root)
    if not branch or not remote:
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
    raise NotImplementedError


def push(root: Path) -> None:
    raise NotImplementedError


def author_of_line(root: Path, path: Path, seq: Seq) -> GitAuthor:
    """Blame the line that carries seq."""
    raise NotImplementedError


def remote_url(root: Path) -> str:
    raise NotImplementedError


def remote_is_public(root: Path) -> bool:
    raise NotImplementedError
