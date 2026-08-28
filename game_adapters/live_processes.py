from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import psutil

from .contracts import GameAdapter
from .registry import get_adapter, iter_adapters


class LiveGameDetectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunningGameProcess:
    adapter: GameAdapter
    pid: int
    process_name: str


def _process_info(process) -> tuple[int, str]:
    info = process if isinstance(process, dict) else process.info
    return int(info["pid"]), str(info.get("name") or "")


def find_running_supported_games(processes: Iterable | None = None) -> list[RunningGameProcess]:
    process_names: dict[str, GameAdapter] = {}
    for adapter in iter_adapters():
        for name in adapter.process_names:
            process_names[name.casefold()] = adapter

    if processes is None:
        processes = psutil.process_iter(["pid", "name"])

    matches: dict[tuple[str, int], RunningGameProcess] = {}
    for process in processes:
        try:
            pid, name = _process_info(process)
            adapter = process_names.get(name.casefold())
            if adapter is not None and pid > 0:
                matches[(adapter.key, pid)] = RunningGameProcess(adapter, pid, name)
        except (psutil.Error, OSError, KeyError, TypeError, ValueError, AttributeError):
            continue
    return sorted(matches.values(), key=lambda match: (match.adapter.key, match.pid))


def detect_single_running_game(
    *,
    expected_game: str | None = None,
    expected_pid: int | None = None,
    processes: Iterable | None = None,
) -> RunningGameProcess:
    matches = find_running_supported_games(processes)
    if not matches:
        raise LiveGameDetectionError(
            "No supported Forza game is running. Start FH4, FH5, FH6, or FM8 and open the vinyl editor before "
            "starting a live transfer."
        )

    games = {match.adapter.key for match in matches}
    if len(games) > 1:
        details = ", ".join(f"{match.adapter.short_label} (pid={match.pid})" for match in matches)
        raise LiveGameDetectionError(
            f"Multiple supported Forza games are running: {details}. Close all but one before starting a live transfer."
        )

    if len(matches) > 1:
        label = matches[0].adapter.short_label
        pids = ", ".join(str(match.pid) for match in matches)
        raise LiveGameDetectionError(
            f"Multiple {label} processes are running (pids: {pids}). Close the extra process before starting a live "
            "transfer."
        )

    match = matches[0]
    if expected_game is not None:
        expected_adapter = get_adapter(expected_game)
        if expected_adapter.key != match.adapter.key:
            raise LiveGameDetectionError(
                f"KFPS detected {match.adapter.short_label}, but the transfer was prepared for "
                f"{expected_adapter.short_label}. Start the transfer again."
            )
    if expected_pid is not None and int(expected_pid) != match.pid:
        raise LiveGameDetectionError(
            f"The detected {match.adapter.short_label} process changed before the transfer started "
            f"(expected pid={int(expected_pid)}, found pid={match.pid}). Start the transfer again."
        )
    return match
