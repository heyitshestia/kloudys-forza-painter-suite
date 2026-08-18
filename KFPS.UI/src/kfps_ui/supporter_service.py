from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog

from .activation_client import ActivationClient
from .activation_config import MIGRATION_GRACE_DAYS, activation_endpoint, enforcement_enabled
from .activation_crypto import (
    SupporterKey,
    b64url_encode,
    read_supporter_key,
    verify_activation_decision,
    verify_activation_receipt,
    verify_activation_status,
    verify_community_entitlement,
)
from .activation_storage import (
    ActivationStorageError,
    ActivationStore,
    decode_receipt,
    encode_receipt,
)
from .theme_catalog import DEFAULT_THEME, SUPPORTER_THEME_NAMES, available_theme_names


SUPPORTER_THEME_NAME = SUPPORTER_THEME_NAMES[0] if SUPPORTER_THEME_NAMES else DEFAULT_THEME
RETRY_DELAYS_SECONDS = (30 * 60, 2 * 60 * 60, 12 * 60 * 60, 24 * 60 * 60)


class SupporterService(QObject):
    changed = Signal()
    communityEntitlementReady = Signal(object)

    def __init__(
        self,
        app_root: Path,
        parent=None,
        *,
        store: ActivationStore | None = None,
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
        self._key_state: dict = {}
        self._device_id = ""
        self._status = "No local unlock installed."
        self._activation_state = "no_key"
        self._access_allowed = False
        self._problem_active = False
        self._problem_dismissed = False
        self._has_key_candidate = False
        self._validation_cache: dict[str, SupporterKey] = {}
        self._reload_in_progress = False
        self._started = False
        self._inflight_operation = ""
        self._status_checked_key_id = ""
        self._pending_community_subject = ""
        self._community_request_subject = ""
        self._clock = clock or time.time
        self._endpoint = activation_endpoint() if endpoint is None else str(endpoint).strip()
        self._enforce_activation = enforcement_enabled() if enforce_activation is None else bool(enforce_activation)
        self._store = store
        self._client = client or ActivationClient(self._endpoint, self)
        self._client.completed.connect(self._handle_client_result)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self.reload)
        self._watcher.directoryChanged.connect(self.reload)
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._maybe_activate)
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
            self._device_id,
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
        if self._reload_in_progress:
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
                if ok and self._is_legacy_key(key_path):
                    if self._install_key(key_path, payload or {}, status, remove_source=True, emit=False):
                        break
                elif ok:
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
        if self._started:
            self._schedule_activation_check()

    def _evaluate_local_activation(self):
        if self._payload is None:
            return
        if not self._enforce_activation:
            self._set_activation("local_only", "Local unlock verified.", True)
            return
        if self._key is None:
            self._set_activation("invalid_key", "Unlock metadata could not be prepared for activation.", False, problem=True)
            return
        try:
            store = self._activation_store()
            _secret, self._device_id = store.load_or_create_identity()
            self._key_state = store.key_state(self._key.key_id)
        except ActivationStorageError as exc:
            self._set_activation("local_storage_error", str(exc), False, problem=True)
            return

        if self._key_state.get("manual_deactivated"):
            self._set_activation(
                "deactivated",
                "Activation was released on this device. Repair activation to register it again.",
                False,
            )
            return

        revocation = self._key_state.get("revocation")
        revocation_nonce = self._key_state.get("revocation_nonce")
        if isinstance(revocation, dict) and isinstance(revocation_nonce, str):
            verified, _error = verify_activation_status(
                revocation,
                key_id=self._key.key_id,
                device_id=self._device_id,
                nonce=revocation_nonce,
            )
            if verified is not None and verified.get("status") == "revoked":
                self._set_activation(
                    "revoked",
                    "This supporter key was revoked. Its offline activation receipt was removed.",
                    False,
                    problem=True,
                )
                return

        receipt_text = self._key_state.get("receipt")
        if isinstance(receipt_text, str) and receipt_text:
            try:
                receipt = decode_receipt(receipt_text)
            except Exception:
                receipt = None
            verified, _error = verify_activation_receipt(
                receipt,
                key_id=self._key.key_id,
                device_id=self._device_id,
            )
            if verified is not None:
                self._set_activation("active", "Activated on this device.", True)
                return

        decision = self._key_state.get("decision")
        decision_nonce = self._key_state.get("decision_nonce")
        if isinstance(decision, dict) and isinstance(decision_nonce, str):
            verified, _error = verify_activation_decision(
                decision,
                key_id=self._key.key_id,
                device_id=self._device_id,
                nonce=decision_nonce,
            )
            if verified is not None:
                if verified.get("status") == "already_activated":
                    self._set_activation(
                        "duplicate",
                        "This supporter key is already activated on another device.",
                        False,
                        problem=True,
                    )
                    return
                if verified.get("status") == "not_eligible":
                    self._set_activation(
                        "not_eligible",
                        "This supporter key could not be registered. Contact KFPS support with the support code.",
                        False,
                        problem=True,
                    )
                    return

        now = float(self._clock())
        grace_started = self._number(self._key_state.get("grace_started_at"))
        if grace_started is None:
            grace_started = now
            self._key_state["grace_started_at"] = grace_started
            try:
                self._save_key_state()
            except ActivationStorageError as exc:
                self._set_activation("local_storage_error", str(exc), False, problem=True)
                return
        grace_active = now < grace_started + MIGRATION_GRACE_DAYS * 86400
        last_error = str(self._key_state.get("last_error_kind") or "")

        if not self._client.configured:
            self._set_activation(
                "service_unconfigured",
                "Supporter activation service is not configured in this test build.",
                grace_active,
                problem=not grace_active,
            )
        elif grace_active:
            status = "Supporter access is active while registration completes in the background."
            if last_error:
                status = "Supporter access remains active; registration will retry automatically."
            self._set_activation("grace", status, True)
        elif last_error == "network_error":
            self._set_activation(
                "network_error",
                "The activation service could not be reached. Public features remain available and KFPS will retry.",
                False,
                problem=True,
            )
        elif last_error:
            self._set_activation(
                "service_error",
                "The activation service returned an invalid response. KFPS will retry safely.",
                False,
                problem=True,
            )
        else:
            self._set_activation("pending", "Supporter activation is pending.", False)

    @staticmethod
    def _number(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _jittered_delay(base_seconds: int) -> int:
        jitter = max(15, int(base_seconds * 0.08))
        return base_seconds + secrets.randbelow(jitter + 1)

    def _activation_store(self) -> ActivationStore:
        if self._store is None:
            self._store = ActivationStore()
        return self._store

    def _save_key_state(self):
        if self._key is None:
            raise ActivationStorageError("No supporter key is available for local activation state.")
        self._activation_store().save_key_state(self._key.key_id, self._key_state)

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

    def _is_legacy_key(self, path: Path) -> bool:
        resolved = self._path_key(path)
        return any(resolved == self._path_key(legacy) for legacy in (self._legacy_installed_key, self._legacy_temp_key) if legacy.exists())

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

    def _schedule_activation_check(self):
        if self._closed:
            return
        if not self._started or not self._enforce_activation or self._key is None or self._inflight_operation:
            return
        if self._key_state.get("manual_deactivated"):
            return
        if self._activation_state in {"active", "revoked"} and self._status_checked_key_id == self._key.key_id:
            return
        next_retry = self._number(self._key_state.get("next_retry_at")) or 0
        delay_seconds = max(0.0, next_retry - float(self._clock()))
        if delay_seconds <= 0:
            self._defer(self._maybe_activate)
            return
        self._retry_timer.start(min(2_147_000_000, max(1, int(delay_seconds * 1000))))

    @Slot()
    def startActivation(self):
        self._started = True
        self._maybe_activate()

    @Slot()
    def repairActivation(self):
        if self._key is None or not self._enforce_activation:
            return
        previous = self._snapshot()
        was_revoked = self._activation_state == "revoked"
        self._problem_dismissed = False
        self._key_state.pop("decision", None)
        self._key_state.pop("decision_nonce", None)
        self._key_state.pop("revocation", None)
        self._key_state.pop("revocation_nonce", None)
        self._key_state.pop("last_error_kind", None)
        self._key_state.pop("next_retry_at", None)
        self._key_state["manual_deactivated"] = False
        if was_revoked:
            self._key_state["grace_started_at"] = (
                float(self._clock()) - MIGRATION_GRACE_DAYS * 86400 - 1
            )
        try:
            self._save_key_state()
        except ActivationStorageError as exc:
            self._set_activation("local_storage_error", str(exc), False, problem=True)
            self._emit_if_changed(previous)
            return
        self._evaluate_local_activation()
        self._emit_if_changed(previous)
        self._maybe_activate(force=True)

    @Slot()
    def deactivateDevice(self):
        if self._activation_state != "active" or self._key is None or not self._device_id or self._inflight_operation:
            return
        self._send_activation_request("deactivate")

    @Slot(str)
    def requestCommunityEntitlement(self, subject: str):
        subject = str(subject or "").strip()
        if not subject:
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
            or not self._device_id
            or not self._client.configured
        ):
            self._pending_community_subject = ""
            self.communityEntitlementReady.emit({
                "ok": False,
                "subject": subject,
                "code": "supporter_not_active",
                "message": "A connected, active supporter registration is required.",
            })
            return
        self._pending_community_subject = ""
        self._community_request_subject = subject
        self._send_activation_request("community-entitlement", community_subject=subject)

    def _maybe_activate(self, force: bool = False):
        if not self._started or not self._enforce_activation or self._key is None or not self._device_id or self._inflight_operation:
            return
        if self._activation_state in {"active", "revoked"} and not force:
            if self._status_checked_key_id != self._key.key_id and self._client.configured:
                self._status_checked_key_id = self._key.key_id
                self._send_activation_request("status")
            return
        if (self._key_state.get("manual_deactivated") or self._activation_state == "revoked") and not force:
            return
        next_retry = self._number(self._key_state.get("next_retry_at")) or 0
        if not force and next_retry > float(self._clock()):
            self._schedule_activation_check()
            return
        if not self._client.configured:
            return
        self._send_activation_request("activate")

    def _send_activation_request(self, operation: str, *, community_subject: str = ""):
        if self._key is None:
            return
        nonce = b64url_encode(secrets.token_bytes(32))
        self._inflight_operation = operation
        self._key_state["last_request_at"] = float(self._clock())
        try:
            self._save_key_state()
        except ActivationStorageError as exc:
            previous = self._snapshot()
            self._inflight_operation = ""
            self._set_activation("local_storage_error", str(exc), False, problem=True)
            self._emit_if_changed(previous)
            return
        sender = {
            "activate": self._client.activate,
            "deactivate": self._client.deactivate,
            "status": self._client.status,
        }.get(operation)
        if operation == "community-entitlement":
            self._client.community_entitlement(
                key_id=self._key.key_id,
                key_proof=self._key.key_proof,
                device_id=self._device_id,
                nonce=nonce,
                community_subject=community_subject,
            )
            return
        if sender is None:
            self._inflight_operation = ""
            return
        sender(
            key_id=self._key.key_id,
            key_proof=self._key.key_proof,
            device_id=self._device_id,
            nonce=nonce,
        )

    @Slot(object)
    def _handle_client_result(self, result: object):
        if self._closed:
            return
        if not isinstance(result, dict):
            return
        operation = str(result.get("operation") or "")
        if operation != self._inflight_operation:
            return
        self._inflight_operation = ""
        self._defer(self._drain_community_entitlement)
        previous = self._snapshot()
        nonce = str(result.get("nonce") or "")
        status = int(result.get("http_status") or 0)
        body = result.get("body")
        network_error = str(result.get("network_error") or "")
        parse_error = str(result.get("parse_error") or "")

        if operation == "community-entitlement":
            subject = self._community_request_subject
            self._community_request_subject = ""
            entitlement = body.get("entitlement") if isinstance(body, dict) else None
            verified, verify_error = verify_community_entitlement(
                entitlement,
                subject=subject,
                nonce=nonce,
                now=float(self._clock()),
            )
            if status == 200 and verified is not None:
                self.communityEntitlementReady.emit({
                    "ok": True,
                    "subject": subject,
                    "entitlement": entitlement,
                })
            else:
                code = str(body.get("error") or "supporter_entitlement_failed") if isinstance(body, dict) else "supporter_entitlement_failed"
                if status == 404 and code == "not_found":
                    message = "This activation server version does not support supporter Community access yet."
                elif code == "community_account_already_bound":
                    message = "This supporter key is already connected to another Community account."
                elif code == "not_eligible":
                    message = "An active supporter registration was not found for this device."
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

        if operation == "status":
            if status == 200 and isinstance(body, dict) and body.get("status") in {"active", "revoked"}:
                decision = body.get("decision")
                verified, _error = verify_activation_status(
                    decision,
                    key_id=self._key.key_id if self._key else "",
                    device_id=self._device_id,
                    nonce=nonce,
                )
                if verified is not None and verified.get("status") == "revoked":
                    self._key_state.pop("receipt", None)
                    self._clear_retry_and_decision()
                    self._key_state["revocation"] = decision
                    self._key_state["revocation_nonce"] = nonce
                    self._problem_dismissed = False
                    if self._save_response_state(previous):
                        self._evaluate_local_activation()
                    self._emit_if_changed(previous)
                    return
                if verified is not None and verified.get("status") == "active" and self._activation_state == "revoked":
                    self._clear_retry_and_decision()
                    self._key_state["grace_started_at"] = (
                        float(self._clock()) - MIGRATION_GRACE_DAYS * 86400 - 1
                    )
                    self._problem_dismissed = False
                    if self._save_response_state(previous):
                        self._set_activation(
                            "pending",
                            "This supporter key was restored. Registration is being repaired.",
                            False,
                        )
                        self._send_activation_request("activate")
                    self._emit_if_changed(previous)
                    return
            # Status checks change local access only when a signed revoke/restore is verified.
            self._emit_if_changed(previous)
            return

        if operation == "activate" and status == 200 and isinstance(body, dict) and body.get("status") == "active":
            receipt = body.get("receipt")
            verified, _error = verify_activation_receipt(
                receipt,
                key_id=self._key.key_id if self._key else "",
                device_id=self._device_id,
            )
            if verified is not None:
                self._key_state["receipt"] = encode_receipt(receipt)
                self._key_state["manual_deactivated"] = False
                self._clear_retry_and_decision()
                if self._save_response_state(previous):
                    self._set_activation("active", "Activated on this device.", True)
                    self._problem_dismissed = False
                self._emit_if_changed(previous)
                return

        if operation == "deactivate" and status == 200 and isinstance(body, dict):
            decision = body.get("decision")
            verified, _error = verify_activation_decision(
                decision,
                key_id=self._key.key_id if self._key else "",
                device_id=self._device_id,
                nonce=nonce,
            )
            if verified is not None and verified.get("status") == "deactivated":
                self._key_state.pop("receipt", None)
                self._clear_retry_and_decision()
                self._key_state["manual_deactivated"] = True
                if self._save_response_state(previous):
                    self._set_activation(
                        "deactivated",
                        "Activation was released on this device. Repair activation to register it again.",
                        False,
                    )
                self._emit_if_changed(previous)
                return

        if operation == "activate" and status in {403, 409} and isinstance(body, dict):
            decision = body.get("decision")
            verified, _error = verify_activation_decision(
                decision,
                key_id=self._key.key_id if self._key else "",
                device_id=self._device_id,
                nonce=nonce,
            )
            if verified is not None and verified.get("status") in {"already_activated", "not_eligible"}:
                self._key_state.pop("receipt", None)
                self._key_state["decision"] = decision
                self._key_state["decision_nonce"] = nonce
                self._key_state["next_retry_at"] = float(self._clock()) + self._jittered_delay(86400)
                self._key_state["retry_attempt"] = 0
                self._key_state.pop("last_error_kind", None)
                self._problem_dismissed = False
                if self._save_response_state(previous):
                    self._evaluate_local_activation()
                self._emit_if_changed(previous)
                self._schedule_activation_check()
                return

        error_kind = "network_error" if network_error or status == 0 or status >= 500 or status == 429 else "service_error"
        if parse_error:
            error_kind = "service_error"
        self._record_transient_error(error_kind, previous)

    def _clear_retry_and_decision(self):
        for key in (
            "decision",
            "decision_nonce",
            "revocation",
            "revocation_nonce",
            "last_error_kind",
            "next_retry_at",
            "retry_attempt",
        ):
            self._key_state.pop(key, None)

    def _save_response_state(self, previous: tuple) -> bool:
        try:
            self._save_key_state()
            return True
        except ActivationStorageError as exc:
            self._set_activation("local_storage_error", str(exc), False, problem=True)
            self._emit_if_changed(previous)
            return False

    def _record_transient_error(self, kind: str, previous: tuple):
        attempt = int(self._key_state.get("retry_attempt") or 0)
        base_delay = RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS) - 1)]
        delay = self._jittered_delay(base_delay)
        self._key_state["retry_attempt"] = attempt + 1
        self._key_state["last_error_kind"] = kind
        self._key_state["next_retry_at"] = float(self._clock()) + delay
        if self._save_response_state(previous):
            self._evaluate_local_activation()
        self._emit_if_changed(previous)
        self._schedule_activation_check()

    @Property(bool, notify=changed)
    def unlocked(self):
        return bool(self._payload and self._access_allowed)

    @Property(bool, notify=changed)
    def keyValid(self):
        return self._payload is not None

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def activationState(self):
        return self._activation_state

    @Property(str, notify=changed)
    def activationStateLabel(self):
        labels = {
            "no_key": "No supporter key",
            "invalid_key": "Invalid supporter key",
            "local_only": "Local unlock active",
            "service_unconfigured": "Activation test mode",
            "pending": "Activation pending",
            "grace": "Registering in background",
            "active": "Activated on this device",
            "duplicate": "Already activated elsewhere",
            "not_eligible": "Activation needs attention",
            "network_error": "Activation service unavailable",
            "service_error": "Activation response error",
            "local_storage_error": "Local activation error",
            "deactivated": "Activation released",
            "revoked": "Supporter key revoked",
        }
        return labels.get(self._activation_state, "Supporter activation")

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
        if not self._payload:
            return []
        values = self._payload.get("entitlements")
        return [str(item) for item in values] if isinstance(values, list) else []

    @Property(bool, notify=changed)
    def problemVisible(self):
        return self._problem_active and not self._problem_dismissed

    @Property(str, notify=changed)
    def problemTitle(self):
        if self._activation_state == "duplicate":
            return "Supporter key already activated"
        if self._activation_state == "invalid_key":
            return "Supporter key could not be verified"
        if self._activation_state == "local_storage_error":
            return "Activation could not be saved"
        if self._activation_state == "revoked":
            return "Supporter key revoked"
        if self._activation_state in {"network_error", "service_error", "service_unconfigured"}:
            return "Supporter activation needs attention"
        return "Supporter activation needs attention"

    @Property(str, notify=changed)
    def problemMessage(self):
        if self._activation_state == "duplicate":
            return "This key is registered to another device. Public KFPS features remain available."
        return self._status

    @Property(str, notify=changed)
    def supportCode(self):
        prefix = self._key.key_id[:8] if self._key else "NO-KEY"
        category = {
            "duplicate": "409",
            "not_eligible": "403",
            "revoked": "REVOKED",
            "invalid_key": "KEY",
            "local_storage_error": "LOCAL",
            "network_error": "NET",
            "service_error": "SERVICE",
            "service_unconfigured": "CONFIG",
        }.get(self._activation_state, "INFO")
        return f"KFPS-ACT-{category}-{prefix}"

    @Property(bool, notify=changed)
    def canRepair(self):
        return bool(self._key and self._enforce_activation and self._client.configured and not self._inflight_operation)

    @Property(bool, notify=changed)
    def canDeactivate(self):
        return self._activation_state == "active" and not self._inflight_operation

    @Slot(str, result=bool)
    def hasEntitlement(self, name: str):
        if not self.unlocked:
            return False
        target = str(name or "").strip()
        values = set(self.entitlements)
        return bool(target and (target in values or "supporter" in values or "all_features" in values))

    @Slot(result=bool)
    def importKey(self):
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Import KFPS unlock",
            str(Path.home()),
            "KFPS unlock (*.kfpskey);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return False
        source = Path(path)
        ok, payload, status = self._validate_file(source)
        if not ok or payload is None:
            previous = self._snapshot()
            self._payload = None
            self._key = None
            self._set_activation("invalid_key", status, False, problem=True)
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
        self._root.mkdir(parents=True, exist_ok=True)
        source = Path(source)
        destination = self._destination_for_source(source)
        temp_path: Path | None = None
        try:
            if self._path_key(source) != self._path_key(destination):
                fd, temp_name = tempfile.mkstemp(prefix="supporter-", suffix=".tmp", dir=self._root)
                os.close(fd)
                temp_path = Path(temp_name)
                shutil.copyfile(source, temp_path)
                os.replace(temp_path, destination)
                temp_path = None
            self._payload = payload
            installed_key, _installed_status = read_supporter_key(destination)
            self._key = installed_key
            if remove_source:
                self._remove_legacy_source(source)
            self._evaluate_local_activation()
            self._refresh_watchers()
            if emit:
                self._emit_if_changed(previous)
                if self._started:
                    self._schedule_activation_check()
            return True
        except Exception as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            self._set_activation("local_storage_error", f"Could not install unlock file: {exc}", False, problem=True)
            if emit:
                self._emit_if_changed(previous)
            return False

    def _destination_for_source(self, source: Path) -> Path:
        name = source.name if source.suffix.lower() == ".kfpskey" else f"{source.stem or 'supporter'}.kfpskey"
        return self._app_root / name

    def _remove_legacy_source(self, source: Path):
        resolved = self._path_key(source)
        for legacy in (self._legacy_installed_key, self._legacy_temp_key):
            try:
                if legacy.exists() and self._path_key(legacy) == resolved:
                    legacy.unlink()
                    return
            except OSError:
                pass

    @Slot()
    def removeKey(self):
        previous = self._snapshot()
        failures = []
        for key in self._root_key_paths():
            try:
                key.unlink()
            except FileNotFoundError:
                pass
            except Exception as exc:
                failures.append(str(exc))
        for legacy in (self._legacy_installed_key, self._legacy_temp_key):
            try:
                legacy.unlink()
            except (FileNotFoundError, OSError):
                pass
        self._payload = None
        self._key = None
        self._device_id = ""
        self._key_state = {}
        self._status_checked_key_id = ""
        if failures:
            self._set_activation("local_storage_error", f"Could not remove unlock file: {failures[0]}", False, problem=True)
        else:
            self._set_activation("no_key", "Local unlock removed.", False)
        self._refresh_watchers()
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
        self._retry_timer.stop()
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
