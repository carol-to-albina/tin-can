from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tincan import git
from tincan.types import ConflictError, ProtocolError, Seq

ROSTER = git.GitAuthor("rainbowpuffpuff", "rainbowpuffpuff@users.noreply.github.com")
ALBINA = git.GitAuthor("enjojoy", "enjojoy@users.noreply.github.com")


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


class PullTests(GitCase):
    def test_pull_is_quiet_when_the_remote_has_no_commits(self) -> None:
        self.assertIsNone(git.pull(self.clone("work")))

    def test_pull_is_quiet_when_the_branch_has_no_upstream_and_no_remote_branch(
        self,
    ) -> None:
        work = self.root / "fresh"
        work.mkdir()
        self.git(work, "init", "-b", "master")
        self.git(work, "remote", "add", "origin", str(self.remote))
        self.assertIsNone(git.pull(work))

    def test_pull_fast_forwards_after_another_clone_pushed(self) -> None:
        work = self.seeded()
        other = self.clone("other")
        self.write(other, "out/albina.ndjson", '{"seq":1}\n')
        self.git(other, "add", "--", ".tincan/out/albina.ndjson")
        self.git(other, "commit", "-m", "albina 1")
        self.git(other, "push")
        git.pull(work)
        self.assertTrue((work / ".tincan" / "out" / "albina.ndjson").exists())

    def test_pull_raises_conflict_on_a_divergent_local_commit(self) -> None:
        work = self.seeded()
        other = self.clone("other")
        self.write(other, "out/albina.ndjson", '{"seq":1}\n')
        self.git(other, "add", "--", ".tincan/out/albina.ndjson")
        self.git(other, "commit", "-m", "albina 1")
        self.git(other, "push")
        self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        self.git(work, "add", "--", ".tincan/out/carol.ndjson")
        self.git(work, "commit", "-m", "carol 1")
        with self.assertRaises(ConflictError):
            git.pull(work)

    def test_pull_raises_conflict_when_the_remote_branch_has_no_upstream(self) -> None:
        self.seeded()
        fork = self.root / "fork"
        fork.mkdir()
        self.git(fork, "init", "-b", "master")
        self.git(fork, "remote", "add", "origin", str(self.remote))
        self.git(fork, "config", "user.name", "Carol Calin")
        self.git(fork, "config", "user.email", "carol@think2earn.local")
        self.write(fork, "out/carol.ndjson", '{"seq":1}\n')
        self.git(fork, "add", "--", ".tincan/out/carol.ndjson")
        self.git(fork, "commit", "-m", "carol 1")
        with self.assertRaises(ConflictError):
            git.pull(fork)


class CommitOwnedTests(GitCase):
    def commits(self, work: Path) -> int:
        return int(self.git(work, "rev-list", "--count", "HEAD").stdout.strip())

    def author(self, work: Path) -> tuple[str, str]:
        line = self.git(work, "log", "-1", "--format=%an%x09%ae").stdout.strip()
        name, _, email = line.partition("\t")
        return name, email

    def test_commit_owned_stamps_the_roster_login_over_git_config(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        self.assertEqual(
            self.author(work),
            ("rainbowpuffpuff", "rainbowpuffpuff@users.noreply.github.com"),
        )
        self.assertEqual(
            self.git(work, "config", "user.name").stdout.strip(), "Carol Calin"
        )

    def test_commit_owned_twice_on_identical_bytes_makes_one_commit(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        before = self.commits(work)
        git.commit_owned(work, [out], "carol 1", ROSTER)
        git.commit_owned(work, [out], "carol 1", ROSTER)
        self.assertEqual(self.commits(work), before + 1)

    def test_commit_owned_leaves_dirty_files_outside_paths(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        self.write(work, "out/albina.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        named = self.git(work, "show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn(".tincan/out/carol.ndjson", named)
        self.assertNotIn("albina", named)
        self.assertIn("albina", self.git(work, "status", "--porcelain").stdout)

    def test_commit_owned_skips_an_owned_path_that_does_not_exist(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        who = work / ".tincan" / "who" / "carol.json"
        git.commit_owned(work, [out, who], "carol 1", ROSTER)
        named = self.git(work, "show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn(".tincan/out/carol.ndjson", named)

    def test_commit_owned_commits_nothing_when_no_owned_path_is_dirty(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        before = self.commits(work)
        git.commit_owned(work, [out], "carol 1 again", ROSTER)
        self.assertEqual(self.commits(work), before)

    def test_commit_owned_takes_a_path_relative_to_the_root(self) -> None:
        work = self.seeded()
        self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [Path(".tincan/out/carol.ndjson")], "carol 1", ROSTER)
        named = self.git(work, "show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn(".tincan/out/carol.ndjson", named)


class PushTests(GitCase):
    def test_push_sets_upstream_on_the_first_push(self) -> None:
        work = self.clone("work")
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        git.push(work)
        self.assertEqual(
            self.git(
                work, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
            ).stdout.strip(),
            "origin/master",
        )
        self.assertIn(
            "refs/heads/master",
            self.git(self.root, "ls-remote", "--heads", str(self.remote)).stdout,
        )

    def test_push_raises_conflict_when_the_remote_moved(self) -> None:
        work = self.seeded()
        other = self.clone("other")
        self.write(other, "out/albina.ndjson", '{"seq":1}\n')
        self.git(other, "add", "--", ".tincan/out/albina.ndjson")
        self.git(other, "commit", "-m", "albina 1")
        self.git(other, "push")
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        with self.assertRaises(ConflictError):
            git.push(work)

    def test_push_is_quiet_with_nothing_to_send(self) -> None:
        self.assertIsNone(git.push(self.seeded()))

    def test_push_dies_without_a_remote(self) -> None:
        work = self.root / "lonely"
        work.mkdir()
        self.git(work, "init", "-b", "master")
        with self.assertRaises(ProtocolError):
            git.push(work)


class AuthorOfLineTests(GitCase):
    def test_author_of_line_names_the_commit_that_introduced_each_seq(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        out.write_text('{"seq":1}\n{"seq":2}\n')
        git.commit_owned(work, [out], "carol 2", ALBINA)
        self.assertEqual(git.author_of_line(work, out, Seq(1)), ROSTER)
        self.assertEqual(git.author_of_line(work, out, Seq(2)), ALBINA)

    def test_author_of_line_skips_blank_lines(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        out.write_text('{"seq":1}\n\n{"seq":2}\n')
        git.commit_owned(work, [out], "carol 2", ALBINA)
        self.assertEqual(git.author_of_line(work, out, Seq(2)), ALBINA)

    def test_author_of_line_returns_the_sentinel_for_an_uncommitted_line(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        out.write_text('{"seq":1}\n{"seq":2}\n')
        self.assertEqual(git.author_of_line(work, out, Seq(2)), git.UNCOMMITTED)

    def test_author_of_line_returns_the_sentinel_for_an_untracked_file(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        self.assertEqual(git.author_of_line(work, out, Seq(1)), git.UNCOMMITTED)

    def test_author_of_line_dies_when_the_file_has_no_such_seq(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        with self.assertRaises(ProtocolError):
            git.author_of_line(work, out, Seq(2))


class AddedSinceTests(GitCase):
    def test_added_since_lists_the_seqs_a_revision_did_not_have(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n{"seq":2}\n')
        git.commit_owned(work, [out], "carol 2", ROSTER)
        before = self.git(work, "rev-parse", "HEAD").stdout.strip()
        out.write_text('{"seq":1}\n{"seq":2}\n{"seq":3}\n\n{"seq":4}\n')
        self.assertEqual(git.added_since(work, out, before), [3, 4])

    def test_added_since_treats_all_zeros_as_everything_new(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n{"seq":2}\n')
        git.commit_owned(work, [out], "carol 2", ROSTER)
        self.assertEqual(git.added_since(work, out, "0" * 40), [1, 2])
        self.assertEqual(git.added_since(work, out, ""), [1, 2])

    def test_added_since_treats_a_file_the_revision_lacked_as_all_new(self) -> None:
        work = self.seeded()
        before = self.git(work, "rev-parse", "HEAD").stdout.strip()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        self.assertEqual(git.added_since(work, out, before), [1])

    def test_added_since_is_empty_when_nothing_was_appended(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        git.commit_owned(work, [out], "carol 1", ROSTER)
        before = self.git(work, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(git.added_since(work, out, before), [])

    def test_added_since_dies_on_an_unknown_revision(self) -> None:
        work = self.seeded()
        out = self.write(work, "out/carol.ndjson", '{"seq":1}\n')
        with self.assertRaises(ProtocolError):
            git.added_since(work, out, "c0ffee" * 6 + "abcd")


if __name__ == "__main__":
    unittest.main()
