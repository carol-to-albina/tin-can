from __future__ import annotations

import importlib
import unittest

MODULES = (
    "tincan",
    "tincan.types",
    "tincan.files",
    "tincan.git",
    "tincan.wake",
    "tincan.room",
    "tincan.cli",
    "tincan.adapters.chat",
)


class ScaffoldTests(unittest.TestCase):
    def test_every_module_imports(self) -> None:
        for name in MODULES:
            importlib.import_module(name)

    def test_public_names(self) -> None:
        import tincan

        self.assertEqual(
            set(tincan.__all__),
            {
                "Autonomy",
                "Draft",
                "Event",
                "EventRef",
                "Grant",
                "Inbox",
                "Kind",
                "Member",
                "Mode",
                "Position",
                "Room",
                "Task",
                "TaskState",
                "WakeType",
                "hook_set",
                "init",
                "join",
            },
        )


if __name__ == "__main__":
    unittest.main()
