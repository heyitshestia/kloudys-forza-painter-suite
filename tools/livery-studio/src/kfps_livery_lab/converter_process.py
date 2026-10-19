"""Bounded, hidden Windows converter adapter with isolated output staging.

The baseline must be loaded by the caller before conversion. It remains read-only.
Windows job containment is established before the suspended child can execute;
kill-on-close also covers descendants which outlive the converter or inherit pipes.
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

import psutil

MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_PROCESS_BYTES = 2 * 1024 * 1024 * 1024
CREATE_SUSPENDED = 0x00000004


class _ProcessFailure(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _JobAccounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in (
        "TotalUserTime", "TotalKernelTime", "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")]
    _fields_ += [(name, wintypes.DWORD) for name in (
        "TotalPageFaultCount", "TotalProcesses", "ActiveProcesses", "TotalTerminatedProcesses")]


class _WindowsJob:
    def __init__(self):
        self.handle = None
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "OpenThread": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def resume(self, process):
        # Popen closes the initial thread handle. Reopen it while still suspended.
        threads = psutil.Process(process.pid).threads()
        if len(threads) != 1:
            raise _ProcessFailure("containment-failed", "Cannot identify the suspended converter thread.")
        thread = self.api.OpenThread(0x0002, False, threads[0].id)  # THREAD_SUSPEND_RESUME
        if not thread:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if self.api.ResumeThread(thread) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(thread)

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            members = []
            try:
                members = self._member_handles(handle)
                if not self.api.TerminateJobObject(handle, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
                # Termination is asynchronous. EOF alone does not prove child exit.
                deadline = time.monotonic() + 5
                for member in members:
                    remaining = max(0, int((deadline - time.monotonic()) * 1000))
                    if self.api.WaitForSingleObject(member, remaining) != 0:
                        raise OSError("Converter job member did not finish terminating.")
                accounting = _JobAccounting()
                while True:
                    if not self.api.QueryInformationJobObject(
                            handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if not accounting.ActiveProcesses:
                        break
                    if time.monotonic() >= deadline:
                        raise OSError("Converter job still has active processes after termination.")
                    time.sleep(.01)
            finally:
                for member in members:
                    self.api.CloseHandle(member)
                if not self.api.CloseHandle(handle):
                    raise ctypes.WinError(ctypes.get_last_error())

    def _member_handles(self, job):
        # Retain exact process identities across termination, not reusable PIDs.
        capacity = 16
        while capacity <= 65536:
            data = ctypes.create_string_buffer(8 + capacity * ctypes.sizeof(ctypes.c_size_t))
            if self.api.QueryInformationJobObject(job, 3, data, len(data), None):
                break
            if ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
                raise ctypes.WinError(ctypes.get_last_error())
            capacity *= 2
        else:
            raise OSError("Converter job exceeds the supported process inventory.")
        count = ctypes.c_uint32.from_buffer(data, 4).value
        handles = []
        try:
            for index in range(count):
                pid = ctypes.c_size_t.from_buffer(data, 8 + index * ctypes.sizeof(ctypes.c_size_t)).value
                handle = self.api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                if handle:
                    handles.append(handle)
                elif ctypes.get_last_error() != 87:  # Already exited.
                    raise ctypes.WinError(ctypes.get_last_error())
            return handles
        except BaseException:
            for handle in handles:
                self.api.CloseHandle(handle)
            raise


class _Capture:
    def __init__(self, limit):
        self.limit = limit
        self.lock = threading.Lock()
        self.exceeded = threading.Event()
        self.total = 0
        self.buffers = {name: bytearray() for name in ("stdout", "stderr")}
        self.counts = dict.fromkeys(self.buffers, 0)
        self.errors = []

    def drain(self, name, stream):
        try:
            while chunk := stream.read(65536):
                with self.lock:
                    retained = max(0, self.limit - self.total)
                    self.buffers[name].extend(chunk[:retained])
                    self.counts[name] += len(chunk)
                    self.total += len(chunk)
                    if self.total > self.limit:
                        self.exceeded.set()
        except OSError as exc:
            with self.lock:
                self.errors.append(f"{name}: {exc}")


def _execute(command, cwd, detail, timeout, memory_limit, output_limit, cancel_event, resident_bytes):
    capture = _Capture(output_limit)
    process = job = None
    readers = []
    began = time.monotonic()
    detail.update(status="starting", containment="windows-job-kill-on-close", peak_resident_bytes=0,
                  timeout_seconds=timeout, max_process_bytes=memory_limit, max_output_bytes=output_limit)
    try:
        job = _WindowsJob()
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   bufsize=0, close_fds=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW | CREATE_SUSPENDED)
        detail["pid"] = process.pid
        job.assign(process)
        for name in ("stdout", "stderr"):
            thread = threading.Thread(target=capture.drain, args=(name, getattr(process, name)),
                                      name=f"KfpsConverter-{process.pid}-{name}")
            thread.start()
            readers.append(thread)
        job.resume(process)
        detail["status"] = "running"
        while process.poll() is None:
            if capture.exceeded.is_set():
                raise _ProcessFailure("output-limit", "Converter exceeded the combined stdout/stderr output limit.")
            if capture.errors:
                raise _ProcessFailure("pipe-error", "Converter output could not be read.")
            if cancel_event is not None and cancel_event.is_set():
                raise _ProcessFailure("cancelled", "Local chassis preparation was cancelled.")
            if time.monotonic() - began >= timeout:
                raise _ProcessFailure("timeout", "Local chassis conversion timed out.")
            used = resident_bytes(process.pid)
            detail["peak_resident_bytes"] = max(detail["peak_resident_bytes"], used)
            if used > memory_limit:
                raise _ProcessFailure("memory-limit", "Converter exceeded its process-tree memory limit.")
            capture.exceeded.wait(.02)
    finally:
        cleanup_errors = []
        if job is not None:
            try:
                job.close()
            except OSError as exc:
                cleanup_errors.append(str(exc))
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired) as exc:
                cleanup_errors.append(str(exc))
        for reader in readers:
            reader.join(timeout=5)
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            for reader in readers:
                if reader.is_alive():
                    reader.join(timeout=1)
                    if reader.is_alive():
                        cleanup_errors.append(f"Reader did not stop: {reader.name}")
            detail["exit_code"] = process.returncode
            # Popen normally defers this handle to garbage collection.
            process._handle.Close()
        detail["elapsed_seconds"] = round(time.monotonic() - began, 6)
        detail["cleanup_errors"] = cleanup_errors
        detail["pipe_errors"] = list(capture.errors)
        for name in ("stdout", "stderr"):
            detail[name + "_bytes"] = capture.counts[name]
            detail[name + "_captured_bytes"] = len(capture.buffers[name])
            detail[name] = capture.buffers[name].decode("utf-8", errors="replace")
        if cleanup_errors:
            raise _ProcessFailure("cleanup-failed", "Converter process cleanup failed: " + "; ".join(cleanup_errors))
    if capture.exceeded.is_set():
        raise _ProcessFailure("output-limit", "Converter exceeded the combined stdout/stderr output limit.")
    if capture.errors:
        raise _ProcessFailure("pipe-error", "Converter output could not be read.")
    if process.returncode:
        message = detail["stderr"].strip() or detail["stdout"].strip() or "no diagnostic output"
        raise _ProcessFailure("converter-failed", f"Local chassis conversion failed ({process.returncode}): {message[-2048:]}")
    return bytes(capture.buffers["stdout"])


def convert_vehicle_model_to_glb(asset, output, converter_path, diagnostics=None, *,
                                timeout_seconds=300.0, max_process_bytes=MAX_PROCESS_BYTES,
                                max_output_bytes=MAX_OUTPUT_BYTES, cancel_event=None):
    """Convert using baseline inspection/validation, without touching the baseline.

    Diagnostics contain bounded local stdout/stderr, the parsed converter report,
    timings, exit/limit/cleanup details, and the backwards-compatible peak RSS.
    The time and sampled RSS bounds apply to the child process tree. Existing
    output is replaced atomically only after success and independent validation.
    """
    from tools.livery import portable_mesh_converter as baseline

    detail = {"format": "kfps-converter-process-v1", "status": "validation", "exit_code": None}
    if diagnostics is not None:
        diagnostics["process"] = detail
    try:
        if os.name != "nt":
            raise _ProcessFailure("unsupported-platform", "The isolated component converter requires Windows.")
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (float, int))
                or not math.isfinite(timeout_seconds) or timeout_seconds <= 0
                or type(max_process_bytes) is not int or max_process_bytes <= 0
                or type(max_output_bytes) is not int or max_output_bytes <= 0):
            raise _ProcessFailure("invalid-limits", "Converter limits must be finite positive numbers.")
        converter = Path(converter_path).resolve(strict=True)
        archive = Path(asset.archive_path).resolve(strict=True)
        destination = Path(output).resolve()
        if not converter.is_file() or not archive.is_file():
            raise _ProcessFailure("missing-input", "Converter executable or source archive is missing.")
        if destination in (archive, converter):
            raise _ProcessFailure("input-alias", "Converter output cannot replace the source archive or executable.")
        if cancel_event is not None and cancel_event.is_set():
            raise _ProcessFailure("cancelled", "Local chassis preparation was cancelled.")
        detail.update(executable=str(converter), output=str(destination))
        entries = baseline.inspection_model_entries(asset)
        carbin_entry = baseline.inspection_carbin_entry(asset)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Only this private directory is cleaned on failure; no guessed temp globs.
        with tempfile.TemporaryDirectory(prefix=".kfps-convert-", dir=destination.parent) as temporary:
            work = Path(temporary)
            staged = work / "vehicle.glb"
            request = work / "request.json"
            request.write_text(json.dumps({"archive": str(archive), "output": str(staged),
                                           "entries": entries, "carbin_entry": carbin_entry}), encoding="utf-8")
            stdout = _execute([str(converter), "--request", str(request)], converter.parent, detail,
                              timeout_seconds, max_process_bytes, max_output_bytes, cancel_event,
                              baseline._process_tree_resident_bytes)
            try:
                report = json.loads(stdout.decode("utf-8-sig"),
                                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                if not isinstance(report, dict):
                    raise ValueError("Expected an object report.")
                unresolved = report.get("unresolved_instance_count")
                if type(unresolved) is not int or unresolved < 0:
                    raise ValueError("Missing or invalid unresolved-instance count.")
                if not isinstance(report.get("output"), str) or Path(report["output"]).resolve() != staged:
                    raise ValueError("Converter reported a different output path.")
            except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
                raise _ProcessFailure("invalid-report", "Converter returned an invalid report: " + str(exc)) from exc
            detail["report"] = report
            if unresolved:
                raise _ProcessFailure("unresolved", f"Converter could not resolve {unresolved} required model instances.")
            if staged.is_symlink() or staged.resolve() != staged:
                raise _ProcessFailure("invalid-output", "Converter output escaped its private staging directory.")
            try:
                detail["validation"] = baseline.validate_local_chassis_glb(staged)
            except (OSError, ValueError, RuntimeError) as exc:
                raise _ProcessFailure("invalid-output", "Converted GLB failed validation: " + str(exc)) from exc
            if cancel_event is not None and cancel_event.is_set():
                raise _ProcessFailure("cancelled", "Local chassis preparation was cancelled.")
            os.replace(staged, destination)
        detail["status"] = "success"
        return destination
    except _ProcessFailure as exc:
        detail.update(status=exc.status, error=str(exc))
        error = baseline.ChassisConversionCancelled if exc.status == "cancelled" else baseline.PortableMeshConverterError
        raise error(str(exc)) from exc
    except (OSError, ValueError, RuntimeError, psutil.Error, subprocess.SubprocessError) as exc:
        detail.update(status="adapter-failed", error=str(exc))
        raise baseline.PortableMeshConverterError("Local converter adapter failed: " + str(exc)) from exc
    finally:
        if diagnostics is not None:
            diagnostics["peak_resident_bytes"] = detail.get("peak_resident_bytes", 0)
