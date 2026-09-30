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


def _pathspec(root: Path, path: Path) -> str:
    """A path already under the root stays as given. An absolute path is relativized."""
    if not Path(path).is_absolute():
        return str(path)
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        raise ProtocolError(f"{path} is outside {root}") from None


def _tracked(root: Path, spec: str) -> bool:
    return _run(root, "ls-files", "--error-unmatch", "--", spec).returncode == 0


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
    """Blame the line that carries seq."""
    raise NotImplementedError


def remote_url(root: Path) -> str:
    raise NotImplementedError


def remote_is_public(root: Path) -> bool:
    raise NotImplementedError
