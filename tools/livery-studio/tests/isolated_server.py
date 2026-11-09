"""Run the real Studio server with test-only settings, projects and recoveries."""
from pathlib import Path
import os
import sys

root = Path(os.environ["KFPS_TEST_ROOT"]) / "tools/livery-studio" if "KFPS_TEST_ROOT" in os.environ else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from kfps_livery_lab import server

original = server.LiveryLabServer


def isolated_server(prepared, workspace, kfps_root, **kwargs):
    from tools.kfps_release_announcement import ReleaseAnnouncement
    from kfps_livery_lab import host_bridge

    session = Path(workspace) / "test-session"
    host_bridge.HANDOFF_ROOT = Path(workspace) / "test-handoffs"
    return original(prepared, workspace, kfps_root, **kwargs,
                    session_data_root=session, activity_counter=False,
                    release_announcement=ReleaseAnnouncement(session))


server.LiveryLabServer = isolated_server
server.main()
