from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UI / "bridges"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402

import transfer_bridge  # noqa: E402
from game_adapters import (  # noqa: E402
    ADAPTERS,
    LiveGameDetectionError,
    RunningGameProcess,
    detect_single_running_game,
    find_running_supported_games,
)
from kfps_ui.app_paths import AppPaths  # noqa: E402
from kfps_ui.transfer_service import TransferService  # noqa: E402


APP = QCoreApplication.instance() or QCoreApplication([])


def process(pid: int, name: str):
    return SimpleNamespace(info={"pid": pid, "name": name})


class DummyLog:
    def __init__(self):
        self.messages = []

    def append(self, message, level="info", **_kwargs):
        self.messages.append((str(message), level))


class LiveGameProcessTests(unittest.TestCase):
    def test_supported_process_names_resolve_to_the_declared_adapter(self):
        matches = find_running_supported_games(
            [
                process(41, "ForzaHorizon6-Win64-Shipping.exe"),
                process(42, "forza_steamworks_release_final.exe"),
                process(99, "unrelated.exe"),
            ]
        )
        self.assertEqual([("fh6", 41), ("fm8", 42)], [(item.adapter.key, item.pid) for item in matches])

    def test_exactly_one_supported_game_is_selected(self):
        target = detect_single_running_game(processes=[process(123, "ForzaHorizon5.exe")])
        self.assertIs(ADAPTERS["fh5"], target.adapter)
        self.assertEqual(123, target.pid)

    def test_no_supported_game_fails_with_actionable_message(self):
        with self.assertRaisesRegex(LiveGameDetectionError, "No supported Forza game is running"):
            detect_single_running_game(processes=[process(1, "explorer.exe")])

    def test_multiple_supported_games_fail_instead_of_guessing(self):
        with self.assertRaisesRegex(LiveGameDetectionError, "Multiple supported Forza games are running"):
            detect_single_running_game(
                processes=[process(10, "ForzaHorizon4.exe"), process(20, "ForzaHorizon6.exe")]
            )

    def test_duplicate_processes_for_one_game_fail_instead_of_guessing(self):
        with self.assertRaisesRegex(LiveGameDetectionError, "Multiple FH6 processes are running"):
            detect_single_running_game(
                processes=[process(10, "ForzaHorizon6.exe"), process(20, "ForzaHorizon6.exe")]
            )

    def test_stale_game_and_pid_hints_are_rejected(self):
        running = [process(123, "ForzaHorizon5.exe")]
        with self.assertRaisesRegex(LiveGameDetectionError, "prepared for FH6"):
            detect_single_running_game(expected_game="fh6", processes=running)
        with self.assertRaisesRegex(LiveGameDetectionError, "process changed"):
            detect_single_running_game(expected_game="fh5", expected_pid=999, processes=running)

    def test_bridge_revalidates_the_game_and_pid_hints(self):
        target = RunningGameProcess(ADAPTERS["fh4"], 77, "ForzaHorizon4.exe")
        with patch.object(transfer_bridge, "detect_single_running_game", return_value=target) as detect:
            self.assertIs(target, transfer_bridge.resolve_live_target("fh4", 77))
        detect.assert_called_once_with(expected_game="fh4", expected_pid=77)

    def test_bridge_cli_does_not_default_to_a_game(self):
        with patch.object(sys, "argv", ["transfer_bridge.py", "export", "--layer-count", "31"]):
            args = transfer_bridge.parse_args()
        self.assertIsNone(args.game)
        self.assertIsNone(args.pid)


class TransferServiceDetectionTests(unittest.TestCase):
    def make_service(self, root: Path):
        paths = AppPaths(root, UI, UI / "qml", UI / "assets", root / "runtime", root / "python/python.exe")
        jsons = SimpleNamespace(
            setSource=lambda *_args: None,
            refresh=lambda: None,
            refreshRecent=lambda: None,
            selectPath=lambda *_args: None,
        )
        return TransferService(paths, DummyLog(), jsons)

    def test_live_export_passes_the_auto_detected_game_and_pid(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            self.addCleanup(service.close)
            target = RunningGameProcess(ADAPTERS["fm8"], 314, "ForzaMotorsport.exe")
            with patch("kfps_ui.transfer_service.detect_single_running_game", return_value=target), patch.object(
                service, "_start"
            ) as start:
                service.exportJson(65)
            start.assert_called_once_with(
                ["export", "--game", "fm", "--pid", "314", "--layer-count", "65"],
                "Exporting current FM8 group",
            )

    def test_live_import_passes_the_auto_detected_game_and_pid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "vinyl.json"
            source.write_text('{"shapes": []}', encoding="utf-8")
            service = self.make_service(root)
            self.addCleanup(service.close)
            target = RunningGameProcess(ADAPTERS["fh5"], 271, "ForzaHorizon5.exe")
            with patch("kfps_ui.transfer_service.detect_single_running_game", return_value=target), patch.object(
                service, "_start"
            ) as start:
                service.importJson(str(source), 3000, True)
            start.assert_called_once_with(
                [
                    "import",
                    "--game",
                    "fh5",
                    "--pid",
                    "271",
                    "--layer-count",
                    "3000",
                    "--json",
                    str(source),
                    "--clear-unused",
                ],
                "Importing JSON into FH5",
            )

    def test_detection_failure_does_not_start_a_transfer(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            self.addCleanup(service.close)
            error = LiveGameDetectionError("Multiple supported Forza games are running: FH5, FH6.")
            with patch("kfps_ui.transfer_service.detect_single_running_game", side_effect=error), patch.object(
                service, "_start"
            ) as start:
                service.exportJson(3000)
            start.assert_not_called()
            self.assertEqual("Live transfer blocked", service.status)
            self.assertIn("Multiple supported Forza games", service.liveLog)


if __name__ == "__main__":
    unittest.main()
