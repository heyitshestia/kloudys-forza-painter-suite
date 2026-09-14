"""Bounded coordination before loading managed Qt dependencies."""
from __future__ import annotations

import time

from .bootstrap_log import record_startup
from .ipc import forward_before_qt, instance_name
from .update_guard import acquire_update_guard, updater_state_root

GUARD_WAIT_SECONDS = 10


def acquire_or_forward(app_root, runtime, request):
    """Return a lease, or None after ONE acknowledged delivery to an existing host."""
    name = instance_name(app_root, runtime)
    deadline = time.monotonic() + GUARD_WAIT_SECONDS
    waiting = False
    while True:
        try:
            return acquire_update_guard(updater_state_root(app_root))
        except RuntimeError as error:
            if getattr(error, "winerror", None) not in (32, 33):
                raise
            if forward_before_qt(name, request):
                record_startup(runtime, "existing-instance-forwarded")
                return None
            if not waiting:
                record_startup(runtime, "update-guard-wait", winerror=error.winerror)
                waiting = True
            if time.monotonic() >= deadline:
                record_startup(runtime, "update-guard-timeout", winerror=error.winerror)
                raise RuntimeError("The editor or updater still holds this installation, but the editor is not responding. Finish the update or close the existing editor and try again. No running process or saved work was removed.") from error
            time.sleep(0.1)
