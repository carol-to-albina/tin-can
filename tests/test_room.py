#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOM = ROOT / "scripts" / "room.py"


def run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOM), *args],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=ROOT,
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


if __name__ == "__main__":
    unittest.main()
