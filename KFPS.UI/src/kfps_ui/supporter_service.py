from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from dataclasses import replace

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog

from .activation_client import ActivationClient
from .activation_config import activation_endpoint
from .activation_crypto import (
    SupporterKey,
    b64url_encode,
    read_supporter_key,
    verify_community_entitlement,
    verify_community_legacy_verified_grant,
)
from .theme_catalog import DEFAULT_THEME, SUPPORTER_THEME_NAMES, available_theme_names


SUPPORTER_THEME_NAME = SUPPORTER_THEME_NAMES[0] if SUPPORTER_THEME_NAMES else DEFAULT_THEME


class SupporterService(QObject):
    changed = Signal()
    communityEntitlementReady = Signal(object)

    def __init__(
        self,
        app_root: Path,
        parent=None,
        *,
        store=None,
        client: ActivationClient | None = None,
        endpoint: str | None = None,
        enforce_activation: bool | None = None,
        clock=None,
    ):
        super().__init__(parent)
        self._closed = False
        self._deferred_timers: set[QTimer] = set()
        self._app_root = Path(app_root)
        self._root = self._app_root
        self._legacy_root = self._app_root / "runtime" / "supporter"
        self._legacy_installed_key = self._legacy_root / "supporter.kfpskey"
        self._legacy_temp_key = self._legacy_root / "supporter.tmp"
        self._payload: dict | None = None
        self._key: SupporterKey | None = None
        self._status = "No local unlock installed."
        self._activation_state = "no_key"
        self._access_allowed = False
        self._problem_active = False
        self._problem_dismissed = False
        self._has_key_candidate = False
        self._validation_cache: dict[str, SupporterKey] = {}
        self._reload_in_progress = False
        self._inflight_operation = ""
        self._pending_community_subject = ""
        self._community_request_subject = ""
        self._community_request_nonce = ""
        self._community_request_key_id = ""
        self._clock = clock or time.time
        self._endpoint = activation_endpoint() if endpoint is None else str(endpoint).strip()
        # Legacy constructor options are accepted but never enable PC activation.
        self._client = client or ActivationClient(self._endpoint, self)
        self._client.completed.connect(self._handle_client_result)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self.reload)
        self._watcher.directoryChanged.connect(self.reload)
        self.reload()

    def _defer(self, callback):
        if self._closed:
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        self._deferred_timers.add(timer)

        def run():
            self._deferred_timers.discard(timer)
            timer.stop()
            timer.setParent(None)
            if not self._closed:
                callback()

        timer.timeout.connect(run)
        timer.start(0)

    def _snapshot(self) -> tuple:
        return (
            self.unlocked,
            self._status,
            self.supporterLabel,
            self._activation_state,
            self._problem_active,
            self._problem_dismissed,
            self._key.key_id if self._key else "",
        )

    def _emit_if_changed(self, previous: tuple):
        if previous != self._snapshot():
            self.changed.emit()

    def _set_activation(self, state: str, status: str, access: bool, *, problem: bool = False):
        self._activation_state = state
        self._status = status
        self._access_allowed = bool(access)
        self._problem_active = bool(problem)

    @staticmethod
    def _path_key(path: Path) -> str:
        try:
            return str(path.resolve()).lower()
        except OSError:
            return str(path).lower()

    def _validate_file(self, path: Path) -> tuple[bool, dict | None, str]:
        key, status = read_supporter_key(path)
        cache_key = self._path_key(path)
        if key is None:
            self._validation_cache.pop(cache_key, None)
            return False, None, status
        self._validation_cache[cache_key] = key
        return True, key.payload, status

    def reload(self):
        if self._closed or self._reload_in_progress:
            return
        self._reload_in_progress = True
        previous = self._snapshot()
        try:
            self._payload = None
            self._key = None
            self._has_key_candidate = False
            fallback_status = "No local unlock installed."
            for key_path in self._candidate_key_paths():
                self._has_key_candidate = True
                ok, payload, status = self._validate_file(key_path)
                if ok:
                    self._payload = payload
                    self._key = self._validation_cache.get(self._path_key(key_path))
                    fallback_status = status
                    break
                else:
                    fallback_status = status
            if self._payload is None:
                if self._has_key_candidate:
                    self._set_activation("invalid_key", fallback_status, False, problem=True)
                else:
                    self._set_activation("no_key", "No local unlock installed.", False)
            else:
                self._evaluate_local_activation()
            self._refresh_watchers()
        finally:
            self._reload_in_progress = False
        self._emit_if_changed(previous)

    def _evaluate_local_activation(self):
        # Theme access is determined exclusively by the signed local key.
        if self._payload is not None and self._key is not None:
            self._set_activation("active", "Supporter themes unlocked. No PC registration is required.", True)
        else:
            self._set_activation("invalid_key", "Supporter theme key could not be verified.", False, problem=True)

    def _root_key_paths(self) -> list[Path]:
        keys = [path for path in self._app_root.glob("*.kfpskey") if path.is_file()]
        return sorted(keys, key=lambda path: (path.stat().st_mtime, path.name.lower()), reverse=True)

    def _candidate_key_paths(self) -> list[Path]:
        candidates = [*self._root_key_paths(), self._legacy_installed_key, self._legacy_temp_key]
        result: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate.is_file():
                key = self._path_key(candidate)
                if key not in seen:
                    seen.add(key)
                    result.append(candidate)
        return result

    def _refresh_watchers(self):
        self._root.mkdir(parents=True, exist_ok=True)
        watched = set(self._watcher.files() + self._watcher.directories())
        wanted = {str(self._root)}
        if self._legacy_root.exists():
            wanted.add(str(self._legacy_root))
        for key in self._root_key_paths():
            wanted.add(str(key))
        for legacy in (self._legacy_installed_key, self._legacy_temp_key):
            if legacy.is_file():
                wanted.add(str(legacy))
        for path in watched - wanted:
            self._watcher.removePath(path)
        for path in wanted - watched:
            if Path(path).exists():
                self._watcher.addPath(path)

    @Slot()
    def startActivation(self):
        # Retained for older host callers. There is no activation job to start.
        return

    @Slot()
    def repairActivation(self):
        return

    @Slot()
    def deactivateDevice(self):
        return

    @Slot(str)
    def requestCommunityEntitlement(self, subject: str):
        subject = str(subject or "").strip()
        if self._closed or not subject:
            return
        self._pending_community_subject = subject
        self._drain_community_entitlement()

    def _drain_community_entitlement(self):
        subject = self._pending_community_subject
        if not subject or self._inflight_operation:
            return
        if (
            self._activation_state != "active"
            or self._key is None
            or not self._client.configured
        ):
            self._pending_community_subject = ""
            self.communityEntitlementReady.emit({
                "ok": False,
                "subject": subject,
                "code": "supporter_not_active",
                "message": "An existing valid key and a connection are required for the one-time Verified migration.",
            })
            return
        self._pending_community_subject = ""
        self._community_request_subject = subject
        self._community_request_key_id = self._key.key_id
        nonce = b64url_encode(secrets.token_bytes(32))
        self._community_request_nonce = nonce
        self._inflight_operation = "community-entitlement"
        self._client.community_entitlement(
            key_id=self._key.key_id,
            key_proof=self._key.key_proof,
            nonce=nonce,
            community_subject=subject,
        )

    @Slot(object)
    def _handle_client_result(self, result: object):
        if self._closed:
            return
        if not isinstance(result, dict):
            return
        operation = str(result.get("operation") or "")
        if operation != "community-entitlement" or operation != self._inflight_operation:
            return
        if operation == "community-entitlement" and (
            not self._community_request_nonce or result.get("nonce") != self._community_request_nonce
        ):
            # A late response must not consume a newer Community request.
            return
        self._inflight_operation = ""
        self._defer(self._drain_community_entitlement)
        nonce = str(result.get("nonce") or "")
        try:
            status = int(result.get("http_status") or 0)
        except (TypeError, ValueError):
            status = 0
        body = result.get("body")
        network_error = str(result.get("network_error") or "")
        parse_error = str(result.get("parse_error") or "")

        if operation == "community-entitlement":
            subject = self._community_request_subject
            self._community_request_subject = ""
            nonce = self._community_request_nonce
            self._community_request_nonce = ""
            request_key = self._community_request_key_id
            self._community_request_key_id = ""
            if self._key is None or self._key.key_id != request_key:
                self.communityEntitlementReady.emit({
                    "ok": False, "subject": subject, "code": "key_changed",
                    "message": "The local theme key changed while verifying the existing-holder grant.",
                })
                return
            entitlement = body.get("entitlement") if isinstance(body, dict) else None
            current = float(self._clock())
            verified, verify_error = verify_community_entitlement(
                entitlement,
                subject=subject,
                nonce=nonce,
                now=current,
            )
            grant_present = isinstance(body, dict) and "legacy_verified_grant" in body
            if verified is not None and grant_present:
                verified, verify_error = verify_community_legacy_verified_grant(
                    body["legacy_verified_grant"], entitlement=entitlement,
                    subject=subject, nonce=nonce, now=current,
                )
            if status == 200 and verified is not None:
                response = {
                    "ok": True,
                    "subject": subject,
                    "entitlement": entitlement,
                }
                if grant_present:
                    response["legacy_verified_grant"] = body["legacy_verified_grant"]
                self.communityEntitlementReady.emit(response)
            else:
                code = str(body.get("error") or "supporter_entitlement_failed") if isinstance(body, dict) else "supporter_entitlement_failed"
                if status in {400, 404}:
                    message = "The Community migration service needs an update. Local supporter themes remain unlocked."
                elif code == "community_account_already_bound":
                    message = "This supporter key is already connected to another Community account."
                elif code == "not_eligible":
                    message = "This key is not eligible for the existing-holder Community grant. Local themes are unchanged."
                elif parse_error:
                    message = "The activation service returned an unreadable supporter verification response."
                elif network_error or status == 0:
                    message = "The activation service could not be reached to verify Community access."
                elif status == 200 and verify_error:
                    message = "The activation service returned an invalid supporter verification response."
                else:
                    message = "Supporter Community verification was rejected by the activation service."
                self.communityEntitlementReady.emit({
                    "ok": False,
                    "subject": subject,
                    "code": code,
                    "message": message,
                })
            return

    @Property(bool, notify=changed)
    def unlocked(self):
        return bool(self._payload and self._access_allowed)

    @Property(bool, notify=changed)
    def keyValid(self):
        return self._payload is not None

    @Property(str, notify=changed)
    def themeKeyId(self):
        return self._key.key_id if self._key else ""

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def activationState(self):
        return self._activation_state

    @Property(str, notify=changed)
    def activationStateLabel(self):
        return {
            "no_key": "Supporter themes locked",
            "invalid_key": "Theme key needs attention",
            "active": "Supporter themes unlocked",
            "local_storage_error": "Theme key could not be saved",
        }.get(self._activation_state, "Supporter themes")

    @Property(str, notify=changed)
    def supporterLabel(self):
        if not self._payload:
            return "Not unlocked"
        name = str(self._payload.get("supporter_name") or "").strip()
        return name or "Supporter"

    @Property("QStringList", notify=changed)
    def availableThemes(self):
        return available_theme_names(self.unlocked)

    @Property(str, notify=changed)
    def preferredTheme(self):
        return SUPPORTER_THEME_NAME

    @Property("QStringList", notify=changed)
    def entitlements(self):
        return ["supporter_theme"] if self.unlocked else []

    @Property(bool, notify=changed)
    def problemVisible(self):
        return self._problem_active and not self._problem_dismissed

    @Property(str, notify=changed)
    def problemTitle(self):
        return "Supporter theme key needs attention"

    @Property(str, notify=changed)
    def problemMessage(self):
        return self._status

    @Property(str, notify=changed)
    def supportCode(self):
        prefix = self._key.key_id[:8] if self._key else "NO-KEY"
        return f"KFPS-THEME-{prefix}"

    @Property(bool, notify=changed)
    def canRepair(self):
        return False

    @Property(bool, notify=changed)
    def canDeactivate(self):
        return False

    @Slot(str, result=bool)
    def hasEntitlement(self, name: str):
        return self.unlocked and str(name or "").strip() == "supporter_theme"

    @Slot(result=bool)
    def importKey(self):
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Import supporter theme key",
            str(Path.home()),
            "Supporter theme key (*.kfpskey);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return False
        source = Path(path)
        ok, payload, status = self._validate_file(source)
        if not ok or payload is None:
            previous = self._snapshot()
            self._status = f"Theme key was not imported: {status}"
            self._problem_active = True
            self._problem_dismissed = False
            self._emit_if_changed(previous)
            return False
        return self._install_key(source, payload, status)

    def _install_key(
        self,
        source: Path,
        payload: dict,
        status: str,
        remove_source: bool = False,
        emit: bool = True,
    ) -> bool:
        previous = self._snapshot()
        source = Path(source)
        destination = self._destination_for_source(source)
        temp_path: Path | None = None
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            staged = source
            if self._path_key(source) != self._path_key(destination):
                fd, temp_name = tempfile.mkstemp(prefix="supporter-", suffix=".tmp", dir=self._root)
                os.close(fd)
                temp_path = Path(temp_name)
                shutil.copyfile(source, temp_path)
                staged = temp_path
            installed_key, error = read_supporter_key(staged)
            if installed_key is None:
                raise ValueError(error)
            if temp_path is not None:
                os.replace(temp_path, destination)
                temp_path = None
            self._key = replace(installed_key, path=destination)
            self._payload = installed_key.payload
            self._problem_dismissed = False
            self._evaluate_local_activation()
            self._refresh_watchers()
            if emit:
                self._emit_if_changed(previous)
            return True
        except Exception as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            self._status = f"Could not install theme key: {exc}"
            self._problem_active = True
            if emit:
                self._emit_if_changed(previous)
            return False

    def _destination_for_source(self, source: Path) -> Path:
        name = source.name if source.suffix.lower() == ".kfpskey" else f"{source.stem or 'supporter'}.kfpskey"
        return self._app_root / name

    @Slot()
    def removeKey(self):
        previous = self._snapshot()
        failures = []
        for key in [*self._root_key_paths(), self._legacy_installed_key, self._legacy_temp_key]:
            try:
                key.unlink()
            except FileNotFoundError:
                pass
            except Exception as exc:
                failures.append(str(exc))
        # Locked/read-only files still determine access; never claim their removal.
        self.reload()
        self._problem_dismissed = False
        if failures:
            self._status = f"Could not remove theme key: {failures[0]}"
            self._problem_active = True
        else:
            self._set_activation("no_key", "Local unlock removed.", False)
        self._emit_if_changed(previous)

    @Slot()
    def dismissProblem(self):
        previous = self._snapshot()
        self._problem_dismissed = True
        self._emit_if_changed(previous)

    @Slot()
    def copySupportCode(self):
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.supportCode)

    @Slot()
    def refresh(self):
        self._defer(self.reload)

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        for timer in list(self._deferred_timers):
            timer.stop()
            timer.setParent(None)
        self._deferred_timers.clear()
        watched = self._watcher.files() + self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
