"""Research-only, crash-conservative Rules Laboratory wall-clock accounting.

Use an explicit ledger path OUTSIDE the repository. Create a new ``session_id``
for each coordinator lifetime and share it with that coordinator's workers; never
reuse it after a restart. A different session must explicitly reconcile stopped
jobs before launching work. This module neither stops processes nor limits games:
the research coordinator must checkpoint and stop workers at the returned deadline.

Wall time is the union of all active jobs, not the sum of worker durations. CPU
time is reported separately. A checksum detects corruption, not a malicious actor
who can rewrite both the file and checksum. No module can recover a deleted ledger;
the caller must preserve its external evidence directory.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Callable, Iterator, Mapping, Sequence, TypeVar


WINDOW_SECONDS = 43_200.0
MAX_WINDOWS = 3
MAX_WORKERS = 8
SAFETY_FACTOR = 1.30
VERSION = 1
KINDS = frozenset({"proof", "calibration", "research"})
OUTCOMES = frozenset({"completed", "cancelled", "failed", "reconciled"})
REPOSITORY = Path(__file__).resolve().parents[2]
T = TypeVar("T")


class BudgetError(ValueError):
    """Invalid accounting or a request outside the frozen allowance."""


class BudgetIntegrityError(BudgetError):
    """Persisted accounting cannot be trusted."""


class ReconciliationRequired(BudgetError):
    """An earlier coordinator left jobs active; stop and reconcile them."""


def _finite(value: object, *, positive: bool = False) -> bool:
    return (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and (value > 0 if positive else value >= 0)
    )


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _seal(payload: dict) -> dict:
    return {"payload": payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}


def round_robin_blocks(
    registry_order: Sequence[str], cells: Mapping[str, Sequence[T]]
) -> list[tuple[str, T]]:
    """Interleave frozen cells in registry order, never by outcomes or timings.

    Call separately for each collective rung. The complete returned ordering is a
    manifest input; a resumed run skips completed IDs, never reorders the remainder.
    """
    if len(set(registry_order)) != len(registry_order):
        raise BudgetError("duplicate ruleset in frozen registry")
    if set(cells) != set(registry_order):
        raise BudgetError("cells must include every frozen registry entry, even if empty")
    return [
        (ruleset, cells[ruleset][index])
        for index in range(max((len(cells[r]) for r in registry_order), default=0))
        for ruleset in registry_order
        if index < len(cells[ruleset])
    ]


class ResearchBudget:
    """A flock-serialized, atomically replaced external accounting ledger."""

    def __init__(
        self, path: str | Path, *, session_id: str, clock: Callable[[], float] = time.time
    ):
        self.path = Path(path).expanduser().resolve()
        if self.path == REPOSITORY or REPOSITORY in self.path.parents:
            raise BudgetError("raw research accounting must be outside the repository")
        if not isinstance(session_id, str) or not session_id.strip():
            raise BudgetError("a fresh nonempty coordinator session_id is required")
        self.session_id = session_id
        self.clock = clock

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        session_id: str,
        plan_sha256: str,
        clock: Callable[[], float] = time.time,
    ) -> ResearchBudget:
        if (
            not isinstance(plan_sha256, str)
            or len(plan_sha256) != 64
            or any(c not in "0123456789abcdef" for c in plan_sha256)
        ):
            raise BudgetError("plan_sha256 must be a lowercase SHA-256 digest")
        ledger = cls(path, session_id=session_id, clock=clock)
        ledger.path.parent.mkdir(parents=True, exist_ok=True)
        with ledger._lock():
            if ledger.path.exists():
                raise BudgetError("refusing to reset an existing research ledger")
            now = ledger._now()
            ledger._write({
                "version": VERSION,
                "plan_sha256": plan_sha256,
                "limits": {"windows": MAX_WINDOWS, "seconds": WINDOW_SECONDS,
                           "workers": MAX_WORKERS, "safety": SAFETY_FACTOR},
                "session_id": session_id,
                "created_at": now,
                "last_accounted_at": now,
                "windows": [],
                "jobs": {},
                "events": [],
            })
        return ledger

    @contextmanager
    def _lock(self) -> Iterator[None]:
        # A separate inode is essential: the JSON inode changes on atomic replace.
        with self.path.with_suffix(self.path.suffix + ".lock").open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _now(self) -> float:
        now = self.clock()
        if not _finite(now):
            raise BudgetIntegrityError("clock must return a finite nonnegative timestamp")
        return float(now)

    def _read(self) -> dict:
        try:
            envelope = json.loads(self.path.read_text())
            payload = envelope["payload"]
            digest = hashlib.sha256(_canonical(payload)).hexdigest()
            if not hmac.compare_digest(envelope["sha256"], digest):
                raise BudgetIntegrityError("ledger checksum mismatch")
            self._validate(payload)
            return payload
        except (OSError, TypeError, KeyError, ValueError) as exc:
            raise BudgetIntegrityError(f"unreadable or malformed research ledger: {exc}") from exc

    @staticmethod
    def _validate(state: dict) -> None:
        expected = {"windows": MAX_WINDOWS, "seconds": WINDOW_SECONDS,
                    "workers": MAX_WORKERS, "safety": SAFETY_FACTOR}
        if type(state["version"]) is not int or state["version"] != VERSION or state["limits"] != expected:
            raise BudgetIntegrityError("unsupported ledger version or changed frozen limits")
        digest = state["plan_sha256"]
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            raise BudgetIntegrityError("invalid frozen plan digest")
        if not isinstance(state["session_id"], str) or not state["session_id"]:
            raise BudgetIntegrityError("missing session identity")
        if not _finite(state["created_at"]) or not _finite(state["last_accounted_at"]):
            raise BudgetIntegrityError("invalid ledger timestamps")
        if state["last_accounted_at"] < state["created_at"]:
            raise BudgetIntegrityError("timestamps run backwards")
        windows = state["windows"]
        if not isinstance(windows, list) or len(windows) > MAX_WINDOWS:
            raise BudgetIntegrityError("invalid window count")
        for index, window in enumerate(windows):
            if (type(window["index"]) is not int or window["index"] != index + 1
                    or not _finite(window["charged_seconds"])
                    or not isinstance(window["closed"], bool)):
                raise BudgetIntegrityError("invalid window accounting")
            if (not _finite(window["opened_at"])
                    or not state["created_at"] <= window["opened_at"] <= state["last_accounted_at"]
                    or (index and window["opened_at"] < windows[index - 1]["opened_at"])):
                raise BudgetIntegrityError("invalid window timestamps")
            if index < len(windows) - 1 and not window["closed"]:
                raise BudgetIntegrityError("multiple open windows")
        if not isinstance(state["jobs"], dict) or not isinstance(state["events"], list):
            raise BudgetIntegrityError("invalid job or event records")
        workers = 0
        for job_id, job in state["jobs"].items():
            if not isinstance(job_id, str) or not job_id or job["kind"] not in KINDS:
                raise BudgetIntegrityError("invalid job identity or category")
            if type(job["workers"]) is not int or not 1 <= job["workers"] <= MAX_WORKERS:
                raise BudgetIntegrityError("invalid worker allocation")
            if not _finite(job["started_at"]) or job["started_at"] > state["last_accounted_at"]:
                raise BudgetIntegrityError("invalid job start time")
            if type(job["window"]) is not int or not 1 <= job["window"] <= len(windows):
                raise BudgetIntegrityError("job references absent window")
            if (job["started_at"] < windows[job["window"] - 1]["opened_at"]
                    or not _finite(job["projected_seconds"], positive=True)
                    or job["guarded_seconds"] != job["projected_seconds"] * SAFETY_FACTOR
                    or not isinstance(job["measurement"], str) or not job["measurement"].strip()):
                raise BudgetIntegrityError("invalid measured job projection or window")
            if job["ended_at"] is None:
                if job["outcome"] is not None or job["window"] != len(windows):
                    raise BudgetIntegrityError("invalid active job")
                if windows[-1]["closed"]:
                    raise BudgetIntegrityError("active job in closed window")
                workers += job["workers"]
            elif (not _finite(job["ended_at"]) or job["ended_at"] < job["started_at"]
                  or job["ended_at"] > state["last_accounted_at"]
                  or job["outcome"] not in OUTCOMES):
                raise BudgetIntegrityError("invalid finished job")
            if job["cpu_seconds"] is not None and not _finite(job["cpu_seconds"]):
                raise BudgetIntegrityError("invalid CPU accounting")
        if workers > MAX_WORKERS:
            raise BudgetIntegrityError("persisted worker ceiling exceeded")
        # Independently reconstruct the union from durable job intervals. A signed
        # but internally inconsistent record is malformed, not an accounting reset.
        for window in windows:
            intervals = sorted(
                (job["started_at"], state["last_accounted_at"] if job["ended_at"] is None
                 else job["ended_at"])
                for job in state["jobs"].values() if job["window"] == window["index"]
            )
            union = 0.0
            cursor = 0.0
            for start, end in intervals:
                if window["index"] < len(windows) and end > windows[window["index"]]["opened_at"]:
                    raise BudgetIntegrityError("job crosses a research window boundary")
                union += max(0.0, end - max(start, cursor))
                cursor = max(cursor, end)
            if not math.isclose(union, window["charged_seconds"], rel_tol=1e-12, abs_tol=1e-7):
                raise BudgetIntegrityError("charged wall time disagrees with active-job union")

    def _write(self, state: dict) -> None:
        contents = _canonical(_seal(state)) + b"\n"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as handle:
                temporary = handle.name
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary is not None:
                os.unlink(temporary)

    @staticmethod
    def _active(state: dict) -> dict:
        return {key: job for key, job in state["jobs"].items() if job["ended_at"] is None}

    def _update(self, operation: Callable[[dict, float], T], *, foreign_ok=False) -> T:
        with self._lock():
            state = self._read()
            now = self._now()
            if now < state["last_accounted_at"]:
                raise BudgetIntegrityError("clock moved backwards; manual accounting audit required")
            active = self._active(state)
            if active:
                state["windows"][-1]["charged_seconds"] += now - state["last_accounted_at"]
            state["last_accounted_at"] = now
            try:
                if active and state["session_id"] != self.session_id and not foreign_ok:
                    raise ReconciliationRequired("earlier-session jobs need explicit reconciliation")
                if not active:
                    state["session_id"] = self.session_id
                result = operation(state, now)
            except BudgetError:
                # Invalid requests cannot make already elapsed active time disappear.
                self._write(state)
                raise
            self._write(state)
            return result

    def _summary(self, state: dict) -> dict:
        windows = state["windows"]
        active = self._active(state)
        charged = sum(window["charged_seconds"] for window in windows)
        current = WINDOW_SECONDS - windows[-1]["charged_seconds"] if windows else WINDOW_SECONDS
        if windows and windows[-1]["closed"]:
            current = 0.0
        forfeited = sum(max(0.0, WINDOW_SECONDS - w["charged_seconds"])
                        for w in windows if w["closed"])
        return {
            "charged_seconds": charged,
            "total_remaining_seconds": max(0.0, MAX_WINDOWS * WINDOW_SECONDS - charged - forfeited),
            "forfeited_seconds": forfeited,
            "window_remaining_seconds": max(0.0, current),
            "windows_opened": len(windows),
            "active_workers": sum(job["workers"] for job in active.values()),
            "active_jobs": sorted(active),
            "requires_reconciliation": bool(active and state["session_id"] != self.session_id),
            "overrun": any(w["charged_seconds"] > WINDOW_SECONDS for w in windows),
            "cpu_seconds_reported": sum(j["cpu_seconds"] or 0.0 for j in state["jobs"].values()),
            "cpu_reports_missing": sum(j["ended_at"] is not None and j["cpu_seconds"] is None
                                       for j in state["jobs"].values()),
            "state": copy.deepcopy(state),
        }

    def status(self) -> dict:
        """Persist elapsed time even after a restart; expose reconciliation state."""
        return self._update(lambda state, now: self._summary(state), foreign_ok=True)

    def checkpoint(self) -> dict:
        """Charge active time and signal when workers must stop at the boundary."""
        def operation(state, now):
            result = self._summary(state)
            if result["overrun"] or result["window_remaining_seconds"] <= 0:
                raise BudgetError("research window exhausted; stop workers and checkpoint results")
            return result
        return self._update(operation)

    def start_job(
        self, job_id: str, *, kind: str, workers: int,
        projected_seconds: float, measurement: str,
    ) -> dict:
        """Admit one measured fixed block/cohort and reserve its worker allocation."""
        def operation(state, now):
            if not isinstance(job_id, str) or not job_id or job_id in state["jobs"]:
                raise BudgetError("job IDs must be unique and nonempty, including failed attempts")
            if kind not in KINDS or type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
                raise BudgetError("invalid research category or worker request")
            if not _finite(projected_seconds, positive=True) or not isinstance(measurement, str) or not measurement.strip():
                raise BudgetError("a positive measured projection and its provenance are required")
            summary = self._summary(state)
            if summary["active_workers"] + workers > MAX_WORKERS:
                raise BudgetError("eight-worker ceiling exceeded")
            if summary["overrun"]:
                raise BudgetError("prior budget overrun requires an audit; launches are blocked")
            guarded = projected_seconds * SAFETY_FACTOR
            if not math.isfinite(guarded) or guarded > min(
                summary["window_remaining_seconds"], summary["total_remaining_seconds"]
            ):
                raise BudgetError("measured projection with 30% safety does not fit")
            if not state["windows"]:
                state["windows"].append({"index": 1, "opened_at": now,
                                          "charged_seconds": 0.0, "closed": False})
            state["jobs"][job_id] = {
                "kind": kind, "workers": workers, "started_at": now, "ended_at": None,
                "window": len(state["windows"]), "outcome": None, "cpu_seconds": None,
                "projected_seconds": projected_seconds, "guarded_seconds": guarded,
                "measurement": measurement,
            }
            state["events"].append({"kind": "start", "job_id": job_id, "at": now})
            return {"job_id": job_id, "deadline": now + min(
                summary["window_remaining_seconds"], summary["total_remaining_seconds"]
            ), "guarded_seconds": guarded}
        return self._update(operation)

    def finish_job(self, job_id: str, *, outcome: str, cpu_seconds: float | None = None) -> dict:
        def operation(state, now):
            if outcome not in OUTCOMES - {"reconciled"} or job_id not in self._active(state):
                raise BudgetError("a currently active job and explicit terminal outcome are required")
            if cpu_seconds is not None and not _finite(cpu_seconds):
                raise BudgetError("CPU seconds must be finite and nonnegative, or explicitly unknown")
            state["jobs"][job_id].update(ended_at=now, outcome=outcome, cpu_seconds=cpu_seconds)
            state["events"].append({"kind": outcome, "job_id": job_id, "at": now})
            return self._summary(state)
        return self._update(operation)

    def reconcile(self, *, stopped_job_ids: Sequence[str], reason: str) -> dict:
        """Caller certifies all recorded jobs stopped; conservatively charge until now."""
        def operation(state, now):
            active = self._active(state)
            if (len(set(stopped_job_ids)) != len(stopped_job_ids)
                    or set(stopped_job_ids) != set(active)
                    or not isinstance(reason, str) or not reason.strip()):
                raise BudgetError("identify every stopped active job and provide an audit reason")
            for job in active.values():
                job.update(ended_at=now, outcome="reconciled")
            state["events"].append({"kind": "reconcile", "at": now,
                                    "jobs": sorted(active), "reason": reason,
                                    "previous_session": state["session_id"]})
            state["session_id"] = self.session_id
            return self._summary(state)
        return self._update(operation, foreign_ok=True)

    def advance_window(self) -> dict:
        """Explicit fixed-block boundary; unused time in the old window is forfeited."""
        def operation(state, now):
            if self._active(state):
                raise BudgetError("stop and reconcile all workers before advancing a window")
            if not state["windows"] or len(state["windows"]) >= MAX_WINDOWS:
                raise BudgetError("no next permitted research window")
            if self._summary(state)["overrun"]:
                raise BudgetError("prior overrun blocks dependent research")
            state["windows"][-1]["closed"] = True
            index = len(state["windows"]) + 1
            state["windows"].append({"index": index, "opened_at": now,
                                      "charged_seconds": 0.0, "closed": False})
            state["events"].append({"kind": "advance_window", "index": index, "at": now})
            return self._summary(state)
        return self._update(operation)
