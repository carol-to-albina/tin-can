from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tincan import git
from tincan.types import ProtocolError


class GitCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.root),
                "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.remote = self.root / "remote.git"
        self.git(self.root, "init", "--bare", "-b", "master", str(self.remote))

    def git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        run = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr or run.stdout)
        return run

    def clone(
        self,
        name: str,
        author: str = "Carol Calin",
        email: str = "carol@think2earn.local",
    ) -> Path:
        work = self.root / name
        self.git(self.root, "clone", str(self.remote), str(work))
        self.git(work, "config", "user.name", author)
        self.git(work, "config", "user.email", email)
        return work

    def seeded(self, name: str = "work") -> Path:
        work = self.clone(name)
        self.write(work, "room.json", '{"protocol": 3}\n')
        self.git(work, "add", "--", ".tincan/room.json")
        self.git(work, "commit", "-m", "seed")
        self.git(work, "push", "-u", "origin", "master")
        return work

    def write(self, work: Path, name: str, text: str) -> Path:
        path = work / ".tincan" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path


class RequireTests(GitCase):
    def test_require_repo_accepts_a_work_tree(self) -> None:
        self.assertIsNone(git.require_repo(self.seeded()))

    def test_require_repo_dies_outside_a_work_tree(self) -> None:
        plain = self.root / "plain"
        plain.mkdir()
        with self.assertRaises(ProtocolError):
            git.require_repo(plain)

    def test_require_branch_accepts_the_room_branch(self) -> None:
        self.assertIsNone(git.require_branch(self.seeded(), "master"))

    def test_require_branch_dies_on_another_branch(self) -> None:
        work = self.seeded()
        self.git(work, "checkout", "-b", "feat/work")
        with self.assertRaises(ProtocolError) as caught:
            git.require_branch(work, "master")
        self.assertIn("master", str(caught.exception))

    def test_require_branch_dies_on_a_detached_head(self) -> None:
        work = self.seeded()
        self.git(work, "checkout", "--detach")
        with self.assertRaises(ProtocolError):
            git.require_branch(work, "master")


if __name__ == "__main__":
    unittest.main()
