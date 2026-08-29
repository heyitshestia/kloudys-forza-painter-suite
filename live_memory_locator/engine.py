from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping

import psutil

from game_adapters import get_adapter
from native import process_memory_session

from .cache import LocatorCache
from .contracts import LocatorRequest, LocatorSelection
from .diagnostics import build_diagnostic, persist_diagnostic
from .fh6_recovery import force_local_recovery_requested
from .validation import select_fallback_candidate, validate_fast_payload


class LiveMemoryLocatorEngine:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.cache = LocatorCache(
            self.root / "runtime" / "live-memory" / "locator-cache.json",
            legacy_path=self.root / "runtime" / "fh6-rtti" / "live-locator-cache.json",
        )

    @staticmethod
    def _process_identity(pid: int) -> dict[str, Any]:
        process = psutil.Process(pid)
        try:
            executable = process.exe()
        except (psutil.Error, OSError):
            executable = ""
        return {
            "pid": int(pid),
            "name": process.name(),
            "started": float(process.create_time()),
            "executable": executable,
        }

    @staticmethod
    def _profile_identity(adapter: Any, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        profile_id = str(payload.get("rtti_profile_id") or "").strip()
        if not profile_id:
            code = str(payload.get("rtti_update_code") or "").strip()
            offset = payload.get("rtti_descriptor_offset")
            profile_id = f"{adapter.locator.key}:{code}:{offset}" if code or offset else adapter.locator.key
        return {
            "game": adapter.key,
            "strategy": adapter.locator.key,
            "source_policy": adapter.locator.profile_source,
            "profile_id": profile_id,
            "matched_source": payload.get("rtti_source"),
            "update_code": payload.get("rtti_update_code"),
            "descriptor_offset": payload.get("rtti_descriptor_offset"),
        }

    @staticmethod
    def _validate_process_identity(process: Mapping[str, Any], adapter: Any) -> None:
        actual = str(process.get("name") or "").casefold()
        expected = {str(name).casefold() for name in adapter.process_names}
        if actual not in expected:
            names = ", ".join(adapter.process_names)
            raise RuntimeError(
                f"pid {process.get('pid')} is {process.get('name') or 'an unknown process'}, "
                f"not a supported {adapter.short_label} process ({names})"
            )

    @staticmethod
    def _same_process_instance(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
        return (
            int(before.get("pid") or 0) == int(after.get("pid") or 0)
            and str(before.get("name") or "").casefold() == str(after.get("name") or "").casefold()
            and abs(float(before.get("started") or 0.0) - float(after.get("started") or 0.0)) < 0.001
        )

    @staticmethod
    def _attempt(name: str, started: float, **fields: Any) -> dict[str, Any]:
        return {
            "name": name,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            **fields,
        }

    @staticmethod
    def _operation_refusal_reason(reason: str, purpose: str) -> str:
        reason = str(reason or "Live vinyl was refused by safety policy.")
        labels = {"import": "Import", "export": "Export", "diagnostic": "Transfer"}
        label = labels.get(str(purpose).lower(), "Transfer")
        for prefix in ("Export refused:", "Import refused:", "Transfer refused:"):
            if reason.casefold().startswith(prefix.casefold()):
                return f"{label} refused:{reason[len(prefix):]}"
        return reason

    def _fast_locate(
        self,
        request: LocatorRequest,
        adapter: Any,
        *,
        calibrated_profiles: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        import fh6_probe

        started = time.monotonic()
        forced_recovery_test = (
            adapter.key == "fh6"
            and calibrated_profiles is None
            and force_local_recovery_requested()
        )
        profiles = [] if forced_recovery_test else calibrated_profiles
        if forced_recovery_test:
            print(
                "FH6 local compatibility recovery test mode: ignoring known profiles for this lookup.",
                flush=True,
            )
        with process_memory_session(request.pid):
            payload = fh6_probe.auto_locate_count_table(
                request.pid,
                adapter.memory_profile,
                request.layer_count,
                request.limit_mb,
                request.max_matches,
                64,
                request.inspect_radius,
                output_path=None,
                max_seconds=request.fast_seconds,
                return_failure_payload=True,
                calibrated_profiles=profiles,
                defer_unmatched_profile_fallback=(
                    forced_recovery_test or calibrated_profiles is None
                ),
            )
        payload = dict(payload or {})
        return payload, self._attempt(
            "profile_locator",
            started,
            status=(
                "refused" if payload.get("refused") else "no_match" if payload.get("no_match") else "located"
            ),
            authoritative=bool(payload.get("authoritative_no_match")),
            forced_local_profile_recovery=forced_recovery_test,
            locator_diagnostics=payload.get("locator_diagnostics") or {},
        )

    @staticmethod
    def _needs_fh6_profile_recovery(payload: Mapping[str, Any], adapter: Any) -> bool:
        if adapter.key != "fh6" or payload.get("refused") is True:
            return False
        profile_diagnostic = (payload.get("locator_diagnostics") or {}).get("rtti_profile") or {}
        return payload.get("profile_recovery_required") is True or profile_diagnostic.get("matched") is False

    def _recover_fh6_profile(
        self,
        request: LocatorRequest,
        adapter: Any,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        from .fh6_recovery import recover_local_profile

        with process_memory_session(request.pid):
            return recover_local_profile(
                self.root,
                request.pid,
                adapter.memory_profile,
                request.layer_count,
                seed_payload=payload,
                process_identity=self._process_identity,
            )

    def _research_locate(
        self, request: LocatorRequest, adapter: Any
    ) -> tuple[LocatorSelection | None, tuple[str, ...], dict[str, Any]]:
        import fh6_group1000_probe as research_probe

        started = time.monotonic()
        handle = research_probe.open_process(request.pid)
        try:
            candidates, scanner = research_probe.scan_groups(
                handle,
                request.layer_count,
                request.research_seconds,
                request.report_layers,
            )
        finally:
            research_probe.close_handle(handle)
        validation = select_fallback_candidate(candidates, request, adapter)
        attempt = self._attempt(
            "research_count_table",
            started,
            status="located" if validation.ok else "no_match",
            candidate_count=len(candidates),
            rejection_reasons=list(validation.reasons[:12]),
            scanner=scanner,
        )
        return validation.selection, validation.reasons, attempt

    def locate(self, request: LocatorRequest) -> dict[str, Any]:
        adapter = get_adapter(request.game)
        if not adapter.supports(f"live_{request.purpose}") and request.purpose != "diagnostic":
            raise ValueError(f"{adapter.short_label} does not support live {request.purpose}")
        process = self._process_identity(request.pid)
        self._validate_process_identity(process, adapter)
        attempts: list[dict[str, Any]] = []
        backend_diagnostics: dict[str, Any] = {}
        selection: LocatorSelection | None = None
        status = "no_match"
        reason = "No safe live vinyl group matched the request."
        authoritative = False

        fast_payload: dict[str, Any] = {}
        fast_error = ""
        try:
            fast_payload, attempt = self._fast_locate(request, adapter)
            attempts.append(attempt)
            backend_diagnostics["profile_locator"] = fast_payload.get("locator_diagnostics") or {}
            if attempt.get("forced_local_profile_recovery"):
                backend_diagnostics["test_mode"] = {
                    "forced_local_profile_recovery": True,
                    "scope": "first_fh6_live_transfer_in_this_kfps_launch",
                    "publication": "disabled",
                }
        except Exception as exc:
            fast_error = f"Profile locator failed unexpectedly: {exc}"
            attempts.append({"name": "profile_locator", "status": "error", "error": str(exc)})

        if not fast_error and self._needs_fh6_profile_recovery(fast_payload, adapter):
            print(
                "No matching FH6 compatibility profile is available. "
                "Running one local allocator recovery pass.",
                flush=True,
            )
            recovery_started = time.monotonic()
            try:
                recovery = self._recover_fh6_profile(request, adapter, fast_payload)
            except Exception as exc:
                recovery = {
                    "status": "error",
                    "reason": f"Local FH6 compatibility recovery failed unexpectedly: {exc}",
                    "publication": "disabled",
                }
            recovery_profile = recovery.pop("profile", None)
            attempts.append(
                self._attempt(
                    "local_profile_recovery",
                    recovery_started,
                    **recovery,
                )
            )
            backend_diagnostics["local_profile_recovery"] = recovery

            if recovery.get("status") == "derived" and isinstance(recovery_profile, dict):
                try:
                    process_before_retry = self._process_identity(request.pid)
                except Exception as exc:
                    process_before_retry = {}
                    attempts.append(
                        {
                            "name": "local_profile_process_recheck",
                            "status": "error",
                            "error": str(exc),
                        }
                    )
                if not self._same_process_instance(process, process_before_retry):
                    fast_payload = {
                        **fast_payload,
                        "no_match": True,
                        "authoritative_no_match": True,
                        "failure_reason": (
                            "The FH6 process changed before local compatibility recovery could be revalidated."
                        ),
                    }
                else:
                    print("Revalidating the recovered FH6 profile with the exact locator.", flush=True)
                    try:
                        retry_payload, retry_attempt = self._fast_locate(
                            request,
                            adapter,
                            calibrated_profiles=[recovery_profile],
                        )
                    except Exception as exc:
                        retry_payload = {
                            "no_match": True,
                            "authoritative_no_match": True,
                            "failure_reason": f"Recovered FH6 profile revalidation failed: {exc}",
                        }
                        retry_attempt = {
                            "name": "recovered_profile_locator",
                            "status": "error",
                            "error": str(exc),
                        }
                    else:
                        retry_attempt = {**retry_attempt, "name": "recovered_profile_locator"}
                    attempts.append(retry_attempt)
                    backend_diagnostics["recovered_profile_locator"] = (
                        retry_payload.get("locator_diagnostics") or {}
                    )
                    retry_validation = validate_fast_payload(retry_payload, request, adapter)
                    expected_profile_id = str(recovery_profile.get("profile_id") or "")
                    located_profile_id = str(retry_payload.get("rtti_profile_id") or "")
                    exact_verified = (
                        retry_validation.ok
                        and bool(expected_profile_id)
                        and located_profile_id == expected_profile_id
                    )
                    access_refusal_verified = (
                        retry_payload.get("refused") is True
                        and bool((retry_payload.get("locator_details") or {}).get("access_status"))
                        and str(retry_payload.get("rtti_profile_id") or "") == expected_profile_id
                    )
                    if exact_verified or access_refusal_verified:
                        from .fh6_recovery import persist_local_profile

                        try:
                            persisted = persist_local_profile(self.root, recovery_profile)
                        except Exception as exc:
                            attempts.append(
                                {
                                    "name": "local_profile_persistence",
                                    "status": "error",
                                    "error": str(exc),
                                }
                            )
                        else:
                            attempts.append(
                                {
                                    "name": "local_profile_persistence",
                                    "status": "saved",
                                    "profile_id": persisted["profile_id"],
                                    "publication": "disabled",
                                }
                            )
                            print(
                                "Local FH6 compatibility recovery was verified and saved for this game build.",
                                flush=True,
                            )
                    else:
                        print(
                            "The recovered FH6 profile did not pass exact revalidation and was not saved.",
                            flush=True,
                        )
                    fast_payload = retry_payload
            else:
                fast_payload = {
                    **fast_payload,
                    "no_match": True,
                    "authoritative_no_match": True,
                    "failure_reason": str(
                        recovery.get("reason")
                        or "Local FH6 compatibility recovery did not produce one exact profile."
                    ),
                }

        profile = self._profile_identity(adapter, fast_payload)
        session_key = self.cache.session_key(
            adapter.key,
            str(profile.get("profile_id") or "unmatched"),
            float(process["started"]),
            request.purpose,
        )
        previous = self.cache.previous_session(session_key)
        cache_info = {
            "session_key": session_key,
            "previous_session": previous,
            "raw_live_pointers_persisted": False,
        }

        if fast_error:
            status = "error"
            authoritative = True
            reason = fast_error
        elif fast_payload.get("refused") is True:
            status = "refused"
            authoritative = True
            reason = self._operation_refusal_reason(
                str(
                    fast_payload.get("refusal_reason")
                    or "Live vinyl was refused by safety policy."
                ),
                request.purpose,
            )
        else:
            validation = validate_fast_payload(fast_payload, request, adapter)
            if validation.ok:
                selection = validation.selection
                status = "located"
                reason = "Live vinyl group located and deterministically validated."
                authoritative = True
            elif fast_payload.get("authoritative_no_match") is True:
                status = "no_match"
                authoritative = True
                reason = str(fast_payload.get("failure_reason") or "; ".join(validation.reasons))
            elif not adapter.locator.allow_research_fallback:
                status = "no_match"
                authoritative = True
                reason = str(fast_payload.get("failure_reason") or "; ".join(validation.reasons))
            else:
                selection, fallback_reasons, attempt = self._research_locate(request, adapter)
                attempts.append(attempt)
                backend_diagnostics["research_count_table"] = attempt.get("scanner") or {}
                if selection:
                    status = "located"
                    reason = "Live vinyl group located by the independently validated research fallback."
                    authoritative = True
                else:
                    status = "no_match"
                    reason = "; ".join(fallback_reasons[:5]) or str(
                        fast_payload.get("failure_reason") or reason
                    )

        if selection is not None:
            try:
                process_after_scan = self._process_identity(request.pid)
            except Exception as exc:
                selection = None
                status = "error"
                authoritative = True
                reason = f"The game process ended before locator validation completed: {exc}"
                attempts.append(
                    {"name": "process_identity_recheck", "status": "error", "error": str(exc)}
                )
            else:
                if not self._same_process_instance(process, process_after_scan):
                    selection = None
                    status = "error"
                    authoritative = True
                    reason = "The game process changed while the locator was scanning; no address was accepted."
                    attempts.append(
                        {
                            "name": "process_identity_recheck",
                            "status": "error",
                            "before": process,
                            "after": process_after_scan,
                        }
                    )
                else:
                    attempts.append(
                        {"name": "process_identity_recheck", "status": "verified"}
                    )

        report = build_diagnostic(
            request=request,
            root=self.root,
            process=process,
            profile=profile,
            status=status,
            reason=reason,
            authoritative=authoritative,
            attempts=attempts,
            selection=selection,
            cache=cache_info,
            backend_diagnostics=backend_diagnostics,
        )
        report = persist_diagnostic(self.root, request.output_path, report)
        try:
            self.cache.record_session(
                session_key,
                {
                    "game": request.game,
                    "purpose": request.purpose,
                    "layer_count": request.layer_count,
                    "status": status,
                    "authoritative": authoritative,
                    "locator": selection.locator if selection else "",
                    "diagnostic_id": report["diagnostic_id"],
                },
            )
        except OSError as exc:
            report["cache"]["write_error"] = str(exc)
            report = persist_diagnostic(self.root, request.output_path, report)
        return report
