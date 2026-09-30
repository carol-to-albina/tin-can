from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from tincan import files
from tincan.room import Room, init, join
from tincan.types import (
    AuthError,
    CotDraft,
    GrantClosed,
    GrantRequestDraft,
    Kind,
    MemberId,
    ProtocolError,
    SpeechDraft,
    TaskDraft,
    TaskState,
)
from tincan.ui import seed_pair, serve

REPO = Path(__file__).resolve().parents[2]
CAROL = ("rainbowpuffpuff", "rainbowpuffpuff@users.noreply.github.com")
ALBINA = ("enjojoy", "enjojoy@users.noreply.github.com")
ENV_KEYS = (
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
    "GIT_COMMITTER_DATE",
    "HOME",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "TINCAN_ME",
    "TINCAN_REPO",
    "GITHUB_EVENT_PATH",
)


class LoopCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self._prior = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["HOME"] = str(self.base)
        os.environ["GIT_CONFIG_GLOBAL"] = str(self.base / "gitconfig")
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        for key, value in self._prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def git(self, cwd: Path, *args: str, identity: tuple[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        command = ["git"]
        if identity:
            command += ["-c", f"user.name={identity[0]}", "-c", f"user.email={identity[1]}"]
        command += list(args)
        run = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr or run.stdout)
        return run

    def pair(self) -> tuple[Path, Path]:
        remote = self.base / "remote.git"
        self.git(self.base, "init", "--bare", "-b", "master", str(remote))
        carol = self.base / "carol"
        self.git(self.base, "clone", str(remote), str(carol))
        init("tincan", "local/tincan", MemberId("carol"), CAROL[0], "Carol", root=carol)
        path = carol / ".tincan" / "room.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["members"]["albina"] = {"github": ALBINA[0], "display": "Albina"}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        self.git(carol, "add", "--", ".tincan")
        self.git(carol, "commit", "-m", "room", identity=CAROL)
        self.git(carol, "push", "-u", "origin", "master")
        albina = self.base / "albina"
        self.git(self.base, "clone", str(remote), str(albina))
        join(MemberId("carol"), root=carol)
        join(MemberId("albina"), root=albina)
        return carol, albina

    def cli(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO)
        return subprocess.run(
            [sys.executable, "-m", "tincan", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_two_clones_hand_off_a_task(self) -> None:
        carol, albina = self.pair()
        carol_room = Room(carol, MemberId("carol"))
        albina_room = Room(albina, MemberId("albina"))
        carol_room.post(SpeechDraft(MemberId("albina"), "the reply is on its way"))
        task = carol_room.post(TaskDraft(MemberId("albina"), "tie the string"))
        carol_room.publish()

        inbox = albina_room.sync()
        self.assertEqual([event.body for event in inbox.speech], ["the reply is on its way"])
        self.assertEqual([task.body for task in inbox.waiting_human], ["tie the string"])
        self.assertEqual(inbox.actionable, ())

        claim = albina_room.claim(task.meta.ref())
        self.assertIsNotNone(claim)
        self.assertEqual(claim.kind, Kind.CLAIM)
        again = albina_room.claim(task.meta.ref())
        self.assertEqual(again, claim)
        done = albina_room.done(task.meta.ref(), "tied")
        self.assertEqual(albina_room.done(task.meta.ref(), "tied"), done)
        albina_room.publish()

        seen = carol_room.sync()
        kinds = [event.kind for event in seen.unread]
        self.assertEqual(kinds, [Kind.CLAIM, Kind.DONE])
        self.assertEqual(seen.unread[1].body, "tied")
        self.assertEqual(albina_room.tasks()[0].state, TaskState.DONE)

    def test_observe_cannot_claim(self) -> None:
        carol, albina = self.pair()
        who = albina / ".tincan" / "who" / "albina.json"
        data = json.loads(who.read_text(encoding="utf-8"))
        data["autonomy"] = "observe"
        who.write_text(json.dumps(data) + "\n", encoding="utf-8")
        carol_room = Room(carol, MemberId("carol"))
        task = carol_room.post(TaskDraft(MemberId("albina"), "watch"))
        carol_room.publish()
        albina_room = Room(albina, MemberId("albina"))
        albina_room.sync()
        with self.assertRaises(ProtocolError):
            albina_room.claim(task.meta.ref())
        self.assertFalse((albina / ".tincan" / "out" / "albina.ndjson").exists())

    def test_cot_needs_a_live_grant(self) -> None:
        carol, albina = self.pair()
        carol_room = Room(carol, MemberId("carol"))
        albina_room = Room(albina, MemberId("albina"))
        request = carol_room.post(
            GrantRequestDraft(MemberId("albina"), "borrow the plan", ("share_hidden_cot",))
        )
        with self.assertRaises(GrantClosed):
            carol_room.post(CotDraft(MemberId("carol"), request.meta.ref(), "hidden"))
        carol_room.publish()
        albina_room.sync()
        albina_room.approve(request.meta.ref())
        albina_room.publish()
        carol_room.sync()
        albina_room.post(CotDraft(MemberId("carol"), request.meta.ref(), "here is the plan"))
        albina_room.publish()
        inbox = carol_room.sync()
        self.assertEqual([event.body for event in inbox.cots], ["here is the plan"])

    def test_publish_keeps_the_roster_login_when_author_env_is_set(self) -> None:
        carol, _albina = self.pair()
        os.environ["GIT_AUTHOR_NAME"] = "forger"
        os.environ["GIT_AUTHOR_EMAIL"] = "forger@example.com"
        os.environ["GIT_COMMITTER_NAME"] = "forger"
        os.environ["GIT_COMMITTER_EMAIL"] = "forger@example.com"
        room = Room(carol, MemberId("carol"))
        room.post(SpeechDraft("all", "still carol"))
        room.publish()
        line = self.git(carol, "log", "-1", "--format=%an%x09%ae").stdout.strip()
        self.assertEqual(line, "rainbowpuffpuff\trainbowpuffpuff@users.noreply.github.com")

    def test_a_forged_author_is_refused(self) -> None:
        carol, albina = self.pair()
        room = Room(carol, MemberId("carol"))
        room.post(SpeechDraft("all", "forged"))
        self.git(carol, "add", "--", ".tincan/out/carol.ndjson")
        self.git(carol, "commit", "-m", "forged", identity=("someone", "someone@example.com"))
        self.git(carol, "push")
        with self.assertRaises(AuthError) as caught:
            Room(albina, MemberId("albina")).sync()
        self.assertIn("rainbowpuffpuff", str(caught.exception))

    def test_cli_ack_clears_the_next_sync(self) -> None:
        carol, albina = self.pair()
        sent = self.cli(
            carol,
            "post",
            "--me",
            "carol",
            "--to",
            "albina",
            "--kind",
            "speech",
            "--body",
            "via cli",
            "--push",
        )
        self.assertEqual(sent.returncode, 0, sent.stderr)
        first = self.cli(albina, "sync", "--me", "albina", "--format", "chat")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("**Carol:** via cli", first.stdout)
        acked = self.cli(albina, "sync", "--me", "albina", "--ack", "--push")
        self.assertEqual(acked.returncode, 0, acked.stderr)
        second = self.cli(albina, "sync", "--me", "albina")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["unread"], [])

    def test_migrate_rewrites_grant_status(self) -> None:
        root = self.base / "old"
        (root / ".room" / "out").mkdir(parents=True)
        (root / ".room" / "hook").mkdir()
        members = {
            "room": "tincan",
            "repo": "carol-to-albina/tincan",
            "members": {
                "carol": {"github": CAROL[0], "display": "Carol"},
                "albina": {"github": ALBINA[0], "display": "Albina"},
            },
        }
        (root / ".room" / "members.json").write_text(json.dumps(members), encoding="utf-8")
        (root / ".room" / "out" / "carol.ndjson").write_text(
            json.dumps(
                {
                    "id": "g1",
                    "ts": "2026-09-20T12:00:00Z",
                    "actor": "carol",
                    "to": "albina",
                    "kind": "grant_request",
                    "body": "look",
                    "capabilities": "share_hidden_cot",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / ".room" / "out" / "albina.ndjson").write_text(
            json.dumps(
                {
                    "id": "g2",
                    "ts": "2026-09-20T12:00:01Z",
                    "actor": "albina",
                    "to": "carol",
                    "kind": "grant",
                    "grant_status": "denied",
                    "grant_id": "g1",
                    "body": "no",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / ".room" / "hook" / "albina.json").write_text(
            json.dumps({"url": "https://example.test/wake", "key": "sek"}),
            encoding="utf-8",
        )
        workflow = root / ".github" / "workflows" / "tincan-notify.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text(
            '".room/out/**"\npython3 scripts/tincan.py hook-notify\n',
            encoding="utf-8",
        )
        paths = files.migrate_v2(root, MemberId("carol"))
        rel = {path.relative_to(root).as_posix() for path in paths}
        self.assertIn(".tincan/room.json", rel)
        self.assertIn(".github/workflows/tincan-notify.yml", rel)
        self.assertFalse(any(part == "local" for path in rel for part in Path(path).parts))
        line = json.loads((root / ".tincan" / "out" / "albina.ndjson").read_text(encoding="utf-8"))
        self.assertEqual(line["kind"], "deny")
        self.assertEqual(line["ref"], "carol:1")
        self.assertNotIn("actor", line)
        self.assertNotIn("id", line)
        request = json.loads((root / ".tincan" / "out" / "carol.ndjson").read_text(encoding="utf-8"))
        self.assertEqual(request["capabilities"], ["share_hidden_cot"])
        who = json.loads((root / ".tincan" / "who" / "albina.json").read_text(encoding="utf-8"))
        self.assertEqual(who["wake"]["type"], "http")
        self.assertIn(".tincan/out/**", workflow.read_text(encoding="utf-8"))
        self.assertIn("python3 -m tincan notify", workflow.read_text(encoding="utf-8"))
        files.load_all_events(root, files.load_members(root))
        with self.assertRaises(ProtocolError):
            files.migrate_v2(root, MemberId("carol"))

    def test_local_chat_sends_speech_across_seats(self) -> None:
        clones = seed_pair(self.base / "ui")
        httpd, url = serve(clones)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.shutdown)
        self.addCleanup(httpd.server_close)
        with urllib.request.urlopen(url, timeout=5) as page:
            html = page.read().decode("utf-8")
        self.assertIn('name="viewport"', html)
        self.assertIn('id="box"', html)
        self.assertIn("Send as a task", html)
        with urllib.request.urlopen(url + "state?me=carol", timeout=5) as page:
            state = json.loads(page.read().decode("utf-8"))
        self.assertTrue(state["ok"])
        self.assertEqual({row["display"] for row in state["members"]}, {"Carol", "Albina"})
        self.assertIn("Local room", state["connection"]["detail"])
        body = json.dumps({"me": "carol", "op": "speech", "body": "across the room"}).encode()
        request = urllib.request.Request(
            url + "act",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as page:
            posted = json.loads(page.read().decode("utf-8"))
        self.assertTrue(posted["ok"])
        with urllib.request.urlopen(url + "state?me=albina", timeout=10) as page:
            other = json.loads(page.read().decode("utf-8"))
        self.assertTrue(any(line["body"] == "across the room" for line in other["lines"]))
        task = json.dumps({"me": "carol", "op": "task", "body": "tie the string"}).encode()
        task_request = urllib.request.Request(
            url + "act",
            data=task,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(task_request, timeout=10) as page:
            self.assertTrue(json.loads(page.read().decode("utf-8"))["ok"])
        with urllib.request.urlopen(url + "state?me=albina", timeout=10) as page:
            jobs = json.loads(page.read().decode("utf-8"))
        open_job = next(row for row in jobs["tasks"] if row["body"] == "tie the string")
        self.assertTrue(open_job["can_claim"])
        claim = json.dumps({"me": "albina", "op": "claim", "ref": open_job["ref"]}).encode()
        claim_request = urllib.request.Request(
            url + "act",
            data=claim,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(claim_request, timeout=10) as page:
            claimed = json.loads(page.read().decode("utf-8"))
        self.assertTrue(claimed["won"])
        with urllib.request.urlopen(url + "state?me=carol", timeout=10) as page:
            back = json.loads(page.read().decode("utf-8"))
        self.assertTrue(any(line["kind"] == "claim" for line in back["lines"]))


if __name__ == "__main__":
    unittest.main()
