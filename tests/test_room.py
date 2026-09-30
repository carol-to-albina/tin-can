#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOM = ROOT / "scripts" / "room.py"


def run(
    args: list[str],
    stdin: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("ROOM_ROOT", None)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(ROOM), *args],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=merged,
    )


class RoomTests(unittest.TestCase):
    def test_validate_speech(self) -> None:
        ev = """---
actor: carol
kind: speech
to: albina
---

can your research bot look at T
"""
        p = run(["validate"], ev)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        self.assertEqual(data["actor"], "carol")
        self.assertEqual(data["kind"], "speech")
        self.assertIn("look at T", data["body"])

    def test_render_speech_as_them(self) -> None:
        ev = """---
actor: albina
kind: speech
to: carol
---

yes, sending CoT
"""
        p = run(["render-event"], ev)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "**Albina:** yes, sending CoT")

    def test_cot_needs_grant(self) -> None:
        ev = """---
actor: albina
kind: cot
to: carol
---

secret thoughts
"""
        p = run(["validate"], ev)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("grant_id", p.stderr)

    def test_same_actor_rejected(self) -> None:
        ev = """---
actor: carol
kind: speech
to: carol
---

hi
"""
        p = run(["validate"], ev)
        self.assertNotEqual(p.returncode, 0)

    def test_unknown_kind_rejected(self) -> None:
        ev = """---
actor: carol
kind: vibe
to: albina
---

hi
"""
        p = run(["validate"], ev)
        self.assertNotEqual(p.returncode, 0)

    def test_render_grant_request(self) -> None:
        ev = """---
actor: carol
kind: grant_request
to: albina
capabilities: share_hidden_cot
---

task T until 16:00
"""
        p = run(["render-event"], ev)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("**Carol:** [asks for share_hidden_cot]", p.stdout)
        self.assertIn("task T", p.stdout)

    def test_start_prompts_share_one_pact(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        member = text[text.index("### Prompt for Albina") : text.index("### Prompt for Carol")]
        host = text[text.index("### Prompt for Carol") : text.index("## Host only")]
        member_fence = member[member.index("```") : member.rindex("```")]
        host_fence = host[host.index("```") : host.rindex("```")]
        member_pact = member_fence[member_fence.index("ROOM PACT") : member_fence.index("SETUP (once")]
        host_pact = host_fence[host_fence.index("ROOM PACT") : host_fence.index("SETUP (once")]
        self.assertEqual(member_pact, host_pact)
        self.assertTrue(member_pact.startswith("ROOM PACT"))
        self.assertNotIn("If I have not said they may write this repo", member)
        self.assertNotIn("If I have not said they may write this repo", host)
        self.assertNotIn("scripts/room.py pact", text)
        self.assertIn("Ask me to re-confirm ROOM PACT", member)
        self.assertIn("Ask me to re-confirm ROOM PACT", host)
        self.assertIn("--kind task", member_fence)
        self.assertIn("--kind task", host_fence)
        self.assertIn("scripts/room.py sync", member_fence)
        self.assertIn("scripts/room.py sync", host_fence)
        self.assertIn("[task]", member_pact)
        self.assertIn("--ack-tasks", member_fence)
        self.assertIn("checkout master", member_fence)
        self.assertNotIn("only render --ack", member_fence)
        self.assertNotIn("If I give someone a task, post speech", host_fence)

    def test_validate_task(self) -> None:
        ev = """---
actor: carol
kind: task
to: albina
---

make posters about tunnelling
"""
        p = run(["validate"], ev)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        self.assertEqual(data["kind"], "task")
        self.assertIn("posters", data["body"])

    def test_render_task_as_them(self) -> None:
        ev = """---
actor: carol
kind: task
to: albina
---

make posters about tunnelling
"""
        p = run(["render-event"], ev)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "**Carol:** [task] make posters about tunnelling")

    def test_workflow_push_only_with_history(self) -> None:
        text = (ROOT / ".github" / "workflows" / "room-notify.yml").read_text(encoding="utf-8")
        self.assertIn("fetch-depth: 0", text)
        self.assertNotIn("\n  issues:", text)
        self.assertNotIn("pull_request:", text)

    def test_validate_file(self) -> None:
        text = """---
actor: carol
kind: receipt
to: albina
grant_id: 9
---

wrote cot under grant 9
"""
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            p = run(["validate", "--file", path])
        finally:
            Path(path).unlink()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["grant_id"], "9")


class OutboxRoomTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        room = self.root / ".room"
        room.mkdir()
        members = json.loads((ROOT / ".room" / "members.json").read_text(encoding="utf-8"))
        members["members"]["dana"] = {"github": "dana", "display": "Dana"}
        (room / "members.json").write_text(json.dumps(members, indent=2) + "\n", encoding="utf-8")
        (room / "out").mkdir()
        (room / "ack").mkdir()
        self.env = {"ROOM_ROOT": str(self.root)}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def room(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return run(args, env=self.env)

    def ok(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        p = self.room(args)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        return p

    def post(self, me: str, to: str, kind: str, body: str, **extra: str) -> dict:
        args = ["post", "--me", me, "--to", to, "--kind", kind, "--body", body]
        for key, val in extra.items():
            args.extend([f"--{key.replace('_', '-')}", val])
        return json.loads(self.ok(args).stdout)

    def test_directed_speech_then_ack(self) -> None:
        self.post("carol", "albina", "speech", "can your research bot look at T")
        albina = self.ok(["render", "--me", "albina"])
        self.assertEqual(albina.stdout.strip(), "**Carol:** can your research bot look at T")
        carol = self.ok(["render", "--me", "carol"])
        self.assertEqual(carol.stdout.strip(), "(no new room events)")
        self.ok(["render", "--me", "albina", "--ack"])
        again = self.ok(["render", "--me", "albina"])
        self.assertEqual(again.stdout.strip(), "(no new room events)")

    def test_to_all_reaches_other_members(self) -> None:
        self.post("carol", "all", "speech", "hello room")
        albina = self.ok(["render", "--me", "albina"])
        dana = self.ok(["render", "--me", "dana"])
        carol = self.ok(["render", "--me", "carol"])
        self.assertEqual(albina.stdout.strip(), "**Carol:** hello room")
        self.assertEqual(dana.stdout.strip(), "**Carol:** hello room")
        self.assertEqual(carol.stdout.strip(), "(no new room events)")

    def test_concurrent_writers_ordered_by_ts_then_id(self) -> None:
        carol = self.post("carol", "dana", "speech", "from carol")
        albina = self.post("albina", "dana", "speech", "from albina")
        self.assertTrue((self.root / ".room" / "out" / "carol.ndjson").is_file())
        self.assertTrue((self.root / ".room" / "out" / "albina.ndjson").is_file())
        expected = sorted((carol, albina), key=lambda e: (e["ts"], e["id"]))
        lines = [f"**{e['actor'].title()}:** {e['body']}" for e in expected]
        rendered = self.ok(["render", "--me", "dana"])
        self.assertEqual(rendered.stdout.strip(), "\n\n".join(lines))

    def test_post_writes_only_own_outbox(self) -> None:
        self.post("dana", "albina", "speech", "hi albina")
        self.assertTrue((self.root / ".room" / "out" / "dana.ndjson").is_file())
        self.assertFalse((self.root / ".room" / "out" / "carol.ndjson").exists())

    def test_approve_appends_grant_and_keeps_request(self) -> None:
        req = self.post(
            "carol",
            "albina",
            "grant_request",
            "task T. need hidden CoT.",
            capabilities="share_hidden_cot",
        )
        carol_path = self.root / ".room" / "out" / "carol.ndjson"
        before = carol_path.read_text(encoding="utf-8")
        approved = json.loads(self.ok(["approve", "--me", "albina", "--id", req["id"]]).stdout)
        self.assertEqual(approved["kind"], "grant")
        self.assertEqual(approved["grant_id"], req["id"])
        self.assertEqual(approved["grant_status"], "live")
        self.assertEqual(approved["to"], "carol")
        self.assertEqual(carol_path.read_text(encoding="utf-8"), before)
        shown = self.ok(["render", "--me", "carol"])
        self.assertIn("[grant live]", shown.stdout)
        self.assertIn("**Albina:**", shown.stdout)

    def test_post_task_then_ack(self) -> None:
        self.post("carol", "albina", "task", "make posters about tunnelling")
        shown = self.ok(["render", "--me", "albina"])
        self.assertEqual(shown.stdout.strip(), "**Carol:** [task] make posters about tunnelling")
        self.ok(["render", "--me", "albina", "--ack"])
        still = self.ok(["render", "--me", "albina"])
        self.assertEqual(still.stdout.strip(), "**Carol:** [task] make posters about tunnelling")
        self.ok(["render", "--me", "albina", "--ack-tasks"])
        again = self.ok(["render", "--me", "albina"])
        self.assertEqual(again.stdout.strip(), "(no new room events)")

    def test_ack_skips_task_but_clears_speech(self) -> None:
        self.post("carol", "albina", "speech", "hi")
        self.post("carol", "albina", "task", "make posters")
        self.ok(["render", "--me", "albina", "--ack"])
        left = self.ok(["render", "--me", "albina"])
        self.assertEqual(left.stdout.strip(), "**Carol:** [task] make posters")

    def test_outbox_actor_must_match_filename(self) -> None:
        path = self.root / ".room" / "out" / "carol.ndjson"
        path.write_text(
            json.dumps(
                {
                    "id": "deadbeef0001",
                    "ts": "2026-09-18T00:00:00Z",
                    "actor": "albina",
                    "to": "albina",
                    "kind": "task",
                    "body": "forged",
                    "grant_id": "",
                    "expires": "",
                    "capabilities": "",
                    "grant_status": "",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        p = self.room(["render", "--me", "albina"])
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("actor", p.stderr)

    def test_sync_without_git_dies(self) -> None:
        p = self.room(["sync", "--me", "albina"])
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("git", p.stderr.lower())

    def test_sync_pulls_then_renders_task(self) -> None:
        remote = self.root / "remote.git"
        albina = self.root / "albina-clone"
        self._git(["init", "--bare", str(remote)])
        self._git(["init"])
        self._git(["-c", "user.email=t@t", "-c", "user.name=t", "add", ".room/members.json"])
        self._git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "seed"])
        self._git(["remote", "add", "origin", str(remote)])
        self._git(["branch", "-M", "master"])
        self._git(["push", "-u", "origin", "master"])
        subprocess.run(
            ["git", "clone", str(remote), str(albina)],
            check=True,
            capture_output=True,
            text=True,
        )
        stale = run(["render", "--me", "albina"], env={"ROOM_ROOT": str(albina)})
        self.assertEqual(stale.returncode, 0, stale.stderr)
        self.assertEqual(stale.stdout.strip(), "(no new room events)")
        self.post("carol", "albina", "task", "make posters about tunnelling")
        self._git(["-c", "user.email=t@t", "-c", "user.name=t", "add", ".room/out/carol.ndjson"])
        self._git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "task"])
        self._git(["push"])
        still_stale = run(["render", "--me", "albina"], env={"ROOM_ROOT": str(albina)})
        self.assertEqual(still_stale.stdout.strip(), "(no new room events)")
        pulled = run(["sync", "--me", "albina"], env={"ROOM_ROOT": str(albina)})
        self.assertEqual(pulled.returncode, 0, pulled.stderr + pulled.stdout)
        self.assertEqual(pulled.stdout.strip(), "**Carol:** [task] make posters about tunnelling")

    def test_push_refuses_other_branch(self) -> None:
        self._git(["init"])
        self._git(["-c", "user.email=t@t", "-c", "user.name=t", "add", ".room/members.json"])
        self._git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "seed"])
        self._git(["branch", "-M", "master"])
        self._git(["checkout", "-b", "feat/work"])
        p = self.room(
            [
                "post",
                "--me",
                "carol",
                "--to",
                "albina",
                "--kind",
                "speech",
                "--body",
                "from a pr branch",
                "--push",
            ]
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("checkout master", p.stderr)

    def test_hook_notify_push_lists_directed_recipient(self) -> None:
        first = self.post("carol", "albina", "speech", "old ping")
        self._git(["init"])
        self._git(["add", ".room/out/carol.ndjson"])
        self._git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "first"])
        before = self._git(["rev-parse", "HEAD"]).stdout.strip()
        second = self.post("carol", "albina", "speech", "new ping")
        self._git(["add", ".room/out/carol.ndjson"])
        self._git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "second"])
        event_path = self.root / "push.json"
        event_path.write_text(
            json.dumps(
                {
                    "ref": "refs/heads/master",
                    "before": before,
                    "commits": [
                        {
                            "added": [],
                            "modified": [".room/out/carol.ndjson"],
                            "removed": [],
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        env = dict(self.env)
        env["GITHUB_EVENT_PATH"] = str(event_path)
        p = run(["hook-notify"], env=env)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        data = json.loads(p.stdout)
        self.assertEqual(data["recipients"], ["albina"])
        self.assertEqual(data["events"]["albina"], [second["id"]])
        self.assertNotIn(first["id"], data["events"]["albina"])

    def _git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        p = subprocess.run(
            ["git", *args],
            cwd=self.root,
            text=True,
            capture_output=True,
        )
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        return p


if __name__ == "__main__":
    unittest.main()
