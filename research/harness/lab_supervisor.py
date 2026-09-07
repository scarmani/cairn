"""Owned local processes for fixed tasks; no research bootstrap is launched here.

Trusted callbacks must not detach or launch unrelated work. Cleanup owns only
fresh process groups held through live Popen handles, never persisted/reused PIDs.
Explicit reconciliation is required for every interrupted attempt. Declared source
labels are matched to authoritative paths from local code, not manifest content.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import uuid

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPOSITORY), str(REPOSITORY / "engine")]
from research.harness.lab_budget import ResearchBudget  # noqa: E402
from research.harness.lab_fixed_tasks import FixedTaskManifest  # noqa: E402
from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402

FORMAT = "varde-lab-supervisor-checkpoint"
VERSION = 1
ACTIVE = {"reserved", "starting", "running"}
FAULTS = {"fault", "integrity-failure", "crash"}
TERMINAL = {"completed", "cancelled", "timeout"} | FAULTS
CHECKPOINT_FIELDS = {"format", "version", "manifest_hash", "worker", "budget_path", "task_ids",
                     "completed", "attempts", "cohorts", "reconciliations"}
ATTEMPT_FIELDS = {"ordinal", "nonce", "task_id", "task_hash", "cohort_id", "status", "pid", "pgid",
                  "started_at", "ended_at", "cleanup_confirmed", "error", "cpu_seconds"}
COHORT_FIELDS = {"id", "owner", "workers", "started_at", "ended_at", "status", "cleanup_confirmed",
                 "ledger_closed", "charged_before", "charged_after", "cpu_seconds", "error"}
MAX_MESSAGE = 16 * 1024 * 1024
GROUP_SNAPSHOT_TIMEOUT = .2
# These are the bytes present when this coordinator imported its framework.
# A later file rewrite cannot relabel already-loaded code as the new version.
_FRAMEWORK_PATHS = {
    "supervisor": Path(__file__).resolve(),
    "worker": Path(__file__).with_name("lab_worker.py").resolve(),
    **{name: Path(sys.modules[f"research.harness.{name}"].__file__).resolve()
       for name in ("lab_budget", "lab_fixed_tasks", "lab_terminal_cert")},
}
_FRAMEWORK_BASELINE = {label: hashlib.sha256(path.read_bytes()).hexdigest()
                       for label, path in _FRAMEWORK_PATHS.items()}


class SupervisorIntegrityError(ValueError):
    pass


def _copy(value):
    return json.loads(canonical_json(value))


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise SupervisorIntegrityError(f"invalid {label} fields")


def _number(value, *, positive=False):
    try:
        return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        return False


def _text(value):
    return type(value) is str and bool(value) and value.strip() == value


def _hex(value, width=64):
    return type(value) is str and len(value) == width and all(c in "0123456789abcdef" for c in value)


def _digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as error:
        raise SupervisorIntegrityError("authoritative source is unavailable") from error


@dataclass(frozen=True, init=False)
class TrustedWorker:
    module: str
    function: str
    _sources: tuple

    def __init__(self, module, function, sources):
        if (type(module) is not str or not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", module)
                or type(function) is not str or not function.isidentifier()
                or type(sources) is not dict or not sources or any(not _text(label) for label in sources)):
            raise SupervisorIntegrityError("trusted local callback and authoritative sources are required")
        paths = tuple(sorted((label, str(Path(path).expanduser().resolve())) for label, path in sources.items()))
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None or str(Path(spec.origin).resolve()) not in dict(paths).values():
            raise SupervisorIntegrityError("callback module must be among authoritative source paths")
        object.__setattr__(self, "module", module)
        object.__setattr__(self, "function", function)
        object.__setattr__(self, "_sources", paths)

    def source_hashes(self):
        return {label: _digest(path) for label, path in self._sources}

    def identity(self):
        runtime = {label: _digest(path) for label, path in _FRAMEWORK_PATHS.items()}
        if runtime != _FRAMEWORK_BASELINE:
            raise SupervisorIntegrityError("loaded supervisor framework source bytes changed")
        return {"module": self.module, "function": self.function, "sources": self.source_hashes(),
                "runtime": runtime,
                "scope": "authoritative supplied files plus import-bound supervisor/worker and three framework helpers; not all transitive imports or commit verification"}


@dataclass(frozen=True)
class Reconciliation:
    attempt_nonces: tuple
    job_ids: tuple
    reason: str
    externally_confirmed_stopped: bool = False

    def __post_init__(self):
        if (type(self.attempt_nonces) is not tuple or any(not _hex(nonce, 32) for nonce in self.attempt_nonces)
                or len(set(self.attempt_nonces)) != len(self.attempt_nonces)
                or type(self.job_ids) is not tuple or any(not _text(job) for job in self.job_ids)
                or len(set(self.job_ids)) != len(self.job_ids) or not _text(self.reason)
                or type(self.externally_confirmed_stopped) is not bool):
            raise SupervisorIntegrityError("invalid explicit reconciliation receipt")


@dataclass(frozen=True)
class SupervisorRun:
    _json: str

    def to_dict(self):
        return json.loads(self._json)

    @property
    def canonical_results_hash(self):
        return self.to_dict()["canonical_results_hash"]


def _task_hash(manifest, task):
    return canonical_hash({"manifest_hash": manifest["manifest_hash"], "id": task["id"], "payload_hash": task["payload_hash"]})


def _result(task_hash, value):
    return canonical_hash({"task_hash": task_hash, "result": value})


def _paths(output_dir):
    directory = Path(output_dir).expanduser().resolve()
    if directory == REPOSITORY or REPOSITORY in directory.parents:
        raise SupervisorIntegrityError("explicit external output directory required")
    return directory, directory / "supervisor-checkpoint.json"


def _verify_source(manifest, worker, identity=None):
    actual = worker.identity()
    if actual["sources"] != manifest["source"]["hashes"]:
        raise SupervisorIntegrityError("authoritative source bytes differ from frozen manifest")
    if identity is not None and actual != identity:
        raise SupervisorIntegrityError("worker implementation changed since checkpoint")
    return actual


def _validate(state, manifest, worker_identity):
    _fields(state, CHECKPOINT_FIELDS, "supervisor checkpoint")
    canonical_json(state)
    tasks = {task["id"]: task for task in manifest["tasks"]}
    if (state["format"] != FORMAT or type(state["version"]) is not int or state["version"] != VERSION
            or state["manifest_hash"] != manifest["manifest_hash"] or state["task_ids"] != list(tasks)
            or state["worker"] != worker_identity or not _text(state["budget_path"])):
        raise SupervisorIntegrityError("incompatible supervisor identity")
    for field in ("completed", "attempts", "cohorts", "reconciliations"):
        if type(state[field]) is not list:
            raise SupervisorIntegrityError("invalid supervisor accounting collection")
    cohorts = {}
    for cohort in state["cohorts"]:
        _fields(cohort, COHORT_FIELDS, "cohort")
        if (not _text(cohort["id"]) or cohort["id"] in cohorts or not _hex(cohort["owner"], 32)
                or type(cohort["workers"]) is not int or not 1 <= cohort["workers"] <= 8
                or not _number(cohort["started_at"]) or cohort["ended_at"] is not None and
                (not _number(cohort["ended_at"]) or cohort["ended_at"] < cohort["started_at"])
                or type(cohort["status"]) is not str or cohort["status"] not in {"active", "completed", "cancelled", "timeout", "failed"}
                or type(cohort["cleanup_confirmed"]) is not bool or type(cohort["ledger_closed"]) is not bool
                or not _number(cohort["charged_before"]) or cohort["charged_after"] is not None and
                (not _number(cohort["charged_after"]) or cohort["charged_after"] < cohort["charged_before"])
                or cohort["cpu_seconds"] is not None):
            raise SupervisorIntegrityError("invalid cohort accounting")
        if cohort["ledger_closed"] and not cohort["cleanup_confirmed"]:
            raise SupervisorIntegrityError("ledger closed before owned worker cleanup")
        if cohort["ledger_closed"] and (cohort["ended_at"] is None or cohort["charged_after"] is None or cohort["status"] == "active"):
            raise SupervisorIntegrityError("closed ledger lacks final cohort accounting")
        if cohort["status"] == "completed" and (not cohort["ledger_closed"] or cohort["error"] is not None):
            raise SupervisorIntegrityError("invalid completed cohort phase")
        if cohort["error"] is not None:
            _fields(cohort["error"], {"type", "message"}, "cohort error")
            if not _text(cohort["error"]["type"]) or type(cohort["error"]["message"]) is not str:
                raise SupervisorIntegrityError("invalid cohort error")
        cohorts[cohort["id"]] = cohort
    nonces, successful = {}, set()
    for index, attempt in enumerate(state["attempts"]):
        _fields(attempt, ATTEMPT_FIELDS, "worker attempt")
        if not _text(attempt["task_id"]) or not _text(attempt["cohort_id"]):
            raise SupervisorIntegrityError("invalid attempt task/cohort ID")
        task = tasks.get(attempt["task_id"])
        if (task is None or type(attempt["ordinal"]) is not int or attempt["ordinal"] != index + 1
                or not _hex(attempt["nonce"], 32) or attempt["nonce"] in nonces
                or attempt["task_hash"] != _task_hash(manifest, task) or attempt["cohort_id"] not in cohorts
                or type(attempt["status"]) is not str or attempt["status"] not in ACTIVE | TERMINAL
                or type(attempt["cleanup_confirmed"]) is not bool):
            raise SupervisorIntegrityError("invalid attempt identity")
        for field in ("pid", "pgid"):
            if attempt[field] is not None and (type(attempt[field]) is not int or attempt[field] <= 1):
                raise SupervisorIntegrityError("invalid owned process identity")
        if attempt["pid"] != attempt["pgid"]:
            raise SupervisorIntegrityError("worker does not own its process group")
        for field in ("started_at", "ended_at", "cpu_seconds"):
            if attempt[field] is not None and not _number(attempt[field]):
                raise SupervisorIntegrityError("invalid worker timing or CPU report")
        if attempt["ended_at"] is not None and attempt["started_at"] is not None and attempt["ended_at"] < attempt["started_at"]:
            raise SupervisorIntegrityError("worker timing ran backwards")
        if attempt["cleanup_confirmed"] and (attempt["status"] in ACTIVE or attempt["ended_at"] is None):
            raise SupervisorIntegrityError("active worker marked cleaned up")
        if attempt["error"] is not None:
            _fields(attempt["error"], {"type", "message"}, "worker error")
            if not _text(attempt["error"]["type"]) or type(attempt["error"]["message"]) is not str:
                raise SupervisorIntegrityError("invalid worker error")
        if attempt["status"] in FAULTS and attempt["error"] is None:
            raise SupervisorIntegrityError("worker fault lacks explicit error")
        if attempt["status"] == "completed":
            if (not attempt["cleanup_confirmed"] or attempt["task_id"] in successful or attempt["error"] is not None
                    or attempt["pid"] is None or attempt["started_at"] is None or attempt["cpu_seconds"] is None):
                raise SupervisorIntegrityError("invalid successful worker completion")
            successful.add(attempt["task_id"])
        if attempt["status"] in {"starting", "running"} and attempt["pid"] is None:
            raise SupervisorIntegrityError("started attempt lacks owned process identity")
        if attempt["status"] == "running" and attempt["started_at"] is None:
            raise SupervisorIntegrityError("running attempt lacks start authorization")
        if attempt["status"] == "reserved" and (attempt["pid"] is not None or attempt["started_at"] is not None):
            raise SupervisorIntegrityError("reserved attempt already started")
        nonces[attempt["nonce"]] = attempt
    reconciled = set()
    for receipt in state["reconciliations"]:
        _fields(receipt, {"attempt_nonces", "job_ids", "reason", "externally_confirmed_stopped"}, "reconciliation")
        if type(receipt["attempt_nonces"]) is not list or type(receipt["job_ids"]) is not list:
            raise SupervisorIntegrityError("invalid reconciliation lists")
        parsed = Reconciliation(tuple(receipt["attempt_nonces"]), tuple(receipt["job_ids"]),
                                receipt["reason"], receipt["externally_confirmed_stopped"])
        if not set(parsed.attempt_nonces) <= set(nonces) or not set(parsed.job_ids) <= set(cohorts):
            raise SupervisorIntegrityError("reconciliation names an unknown attempt or job")
        for nonce in parsed.attempt_nonces:
            attempt = nonces[nonce]
            if nonce in reconciled or attempt["status"] in FAULTS or attempt["status"] == "completed":
                raise SupervisorIntegrityError("invalid retry reconciliation")
            if not attempt["cleanup_confirmed"] and not parsed.externally_confirmed_stopped:
                raise SupervisorIntegrityError("unconfirmed stopped worker")
        reconciled.update(parsed.attempt_nonces)
    previous = {}
    for attempt in state["attempts"]:
        if attempt["task_id"] in previous and previous[attempt["task_id"]] not in reconciled:
            raise SupervisorIntegrityError("attempt retried without explicit reconciliation")
        previous[attempt["task_id"]] = attempt["nonce"]
    for cohort in cohorts.values():
        own = [a for a in state["attempts"] if a["cohort_id"] == cohort["id"]]
        if cohort["status"] == "completed" and (not own or any(a["status"] != "completed" for a in own)):
            raise SupervisorIntegrityError("completed cohort contains unfinished attempts")
        if cohort["cleanup_confirmed"] and any(not a["cleanup_confirmed"] for a in own):
            raise SupervisorIntegrityError("cohort cleanup contradicts owned attempts")
    order = {task: index for index, task in enumerate(tasks)}
    seen = []
    for record in state["completed"]:
        _fields(record, {"task_id", "task_hash", "result", "result_hash"}, "completed result")
        if not _text(record["task_id"]):
            raise SupervisorIntegrityError("invalid completed task ID")
        task = tasks.get(record["task_id"])
        if task is None or record["task_hash"] != _task_hash(manifest, task) or record["result_hash"] != _result(record["task_hash"], record["result"]):
            raise SupervisorIntegrityError("completed result hash mismatch")
        seen.append(record["task_id"])
    if seen != sorted(successful, key=order.get):
        raise SupervisorIntegrityError("completed results disagree with canonical attempt order")


def _parse(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SupervisorIntegrityError("duplicate checkpoint JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
        canonical_json(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise SupervisorIntegrityError("invalid supervisor JSON") from error


def _atomic(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write((canonical_json(value) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_supervisor_checkpoint(manifest, worker, output_dir):
    if not isinstance(manifest, FixedTaskManifest) or not isinstance(worker, TrustedWorker):
        raise SupervisorIntegrityError("validated manifest and trusted worker required")
    frozen = manifest.to_dict()
    identity = _verify_source(frozen, worker)
    _directory, path = _paths(output_dir)
    try:
        envelope = _parse(path.read_bytes())
    except OSError as error:
        raise SupervisorIntegrityError("checkpoint unavailable") from error
    _fields(envelope, {"payload", "sha256"}, "supervisor envelope")
    if not _hex(envelope["sha256"]) or canonical_hash(envelope["payload"]) != envelope["sha256"]:
        raise SupervisorIntegrityError("supervisor checksum mismatch")
    _validate(envelope["payload"], frozen, identity)
    return _copy(envelope["payload"])


@contextmanager
def _lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "supervisor.lock").open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise SupervisorIntegrityError("supervisor output has another active owner") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _report(state, manifest, status, reason):
    canonical = {"manifest_hash": manifest["manifest_hash"], "completed": state["completed"]}
    reconciled_jobs = {job for row in state["reconciliations"] for job in row["job_ids"]}
    complete = (len(state["completed"]) == len(manifest["tasks"])
                and not any(c["status"] == "failed" or c["status"] != "completed" and c["id"] not in reconciled_jobs
                            for c in state["cohorts"]))
    done = {record["task_id"] for record in state["completed"]}
    return SupervisorRun(canonical_json({
        "format": "varde-lab-supervisor-run", "version": VERSION,
        "status": "complete" if complete else status, "reason": "all-completed" if complete else reason,
        "complete": complete, "completed": state["completed"], "attempts": state["attempts"],
        "cohorts": state["cohorts"], "reconciliations": state["reconciliations"],
        "remaining_ids": [task["id"] for task in manifest["tasks"] if task["id"] not in done],
        "canonical_results_hash": canonical_hash(canonical), "manifest_hash": manifest["manifest_hash"],
        "source_verification": state["worker"], "source_commit_verified": False,
        "cpu_scope": "reported worker self CPU only; total including killed descendants unknown",
        "admission_record": False, "research_bootstrap_run": False,
        "containment": "owned same-group trusted workers only; malicious detached code excluded",
    }))


def _signal_owned_group(item, signum):
    process = item["process"]
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass
    except PermissionError:
        if sys.platform != "darwin":
            raise
        # Darwin reports EPERM for some all-zombie groups. Do not swallow a
        # genuine permission/containment error: keep the leader unreaped and
        # require an exited leader plus an exact-group empty/zombie snapshot.
        exited = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if exited is None or exited.si_pid != process.pid:
            raise
        observed = subprocess.run(["/bin/ps", "-g", str(process.pid), "-o", "pid=,pgid=,stat="],
                                  capture_output=True, text=True, timeout=GROUP_SNAPSHOT_TIMEOUT, check=False)
        if observed.returncode not in (0, 1) or observed.stderr.strip():
            raise SupervisorIntegrityError("cannot confirm exited owned process group")
        for line in observed.stdout.splitlines():
            fields = line.split()
            if (len(fields) != 3 or not fields[0].isdigit() or fields[1] != str(process.pid)
                    or not fields[2].startswith("Z")):
                raise SupervisorIntegrityError("EPERM with live or ambiguous owned group membership")


def cleanup_reservation(workers, term_grace, kill_grace, reap_timeout):
    """Worst-case serial successful cleanup plus bounded Darwin observations."""
    return workers * (term_grace + kill_grace + reap_timeout + 2 * GROUP_SNAPSHOT_TIMEOUT) + .05


def _cleanup(active, term_grace, kill_grace, reap_timeout):
    """Signal only still-owned handles; retain leaders until group signals finish."""
    for item in active:
        if item.get("reaped"):
            continue
        _signal_owned_group(item, signal.SIGTERM)
    if active:
        time.sleep(term_grace)
    for item in active:
        if item.get("reaped"):
            continue
        _signal_owned_group(item, signal.SIGKILL)
    if active:
        time.sleep(kill_grace)
    for item in active:
        if item.get("reaped"):
            continue
        process = item["process"]
        # Do not poll/wait before group KILL: an unreaped leader pins its PID,
        # so cleanup cannot accidentally signal a newly reused process group.
        process.wait(timeout=reap_timeout)
        item["reaped"] = True
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()
        item["attempt"]["cleanup_confirmed"] = True
        item["attempt"]["ended_at"] = time.monotonic()


def run_supervised(manifest, worker, *, output_dir, budget, job_id, kind, projected_seconds, measurement,
                   workers=1, task_timeout, cohort_timeout, deadline=None, cancelled=None,
                   reconcile=None, term_grace=.05, kill_grace=.05, reap_timeout=1.0):
    if not isinstance(manifest, FixedTaskManifest) or not isinstance(worker, TrustedWorker) or not isinstance(budget, ResearchBudget):
        raise SupervisorIntegrityError("manifest, worker and explicit ResearchBudget are required")
    if type(workers) is not int or not 1 <= workers <= 8:
        raise SupervisorIntegrityError("worker count must be an integer from one through eight")
    if any(not _number(value, positive=True) for value in (task_timeout, cohort_timeout, term_grace, kill_grace, reap_timeout, projected_seconds)):
        raise SupervisorIntegrityError("positive finite timeout, projection and cleanup bounds required")
    if not _text(job_id) or not _text(measurement) or kind not in ("proof", "calibration", "research"):
        raise SupervisorIntegrityError("explicit unique job identity/category and honest measurement provenance required")
    if (deadline is not None and not _number(deadline)) or (cancelled is not None and not callable(cancelled)):
        raise SupervisorIntegrityError("invalid deadline/cancellation control")
    if reconcile is not None and not isinstance(reconcile, Reconciliation):
        raise SupervisorIntegrityError("explicit typed reconciliation required")
    reserve = cleanup_reservation(workers, term_grace, kill_grace, reap_timeout)
    if cohort_timeout <= reserve:
        raise SupervisorIntegrityError("cohort cap must reserve bounded cleanup time")
    frozen, identity = manifest.to_dict(), _verify_source(manifest.to_dict(), worker)
    directory, checkpoint = _paths(output_dir)
    with _lock(directory):
        if checkpoint.exists():
            state = load_supervisor_checkpoint(manifest, worker, directory)
        else:
            state = {"format": FORMAT, "version": VERSION, "manifest_hash": frozen["manifest_hash"],
                     "worker": identity, "budget_path": str(budget.path),
                     "task_ids": [task["id"] for task in frozen["tasks"]],
                     "completed": [], "attempts": [], "cohorts": [], "reconciliations": []}
        if state["budget_path"] != str(budget.path):
            raise SupervisorIntegrityError("resume must preserve the original budget ledger")

        def persist():
            _validate(state, frozen, identity)
            _atomic(checkpoint, {"payload": state, "sha256": canonical_hash(state)})

        persist()
        reconciled = {nonce for row in state["reconciliations"] for nonce in row["attempt_nonces"]}
        pending = [attempt for attempt in state["attempts"] if attempt["status"] != "completed" and attempt["nonce"] not in reconciled]
        if any(attempt["status"] in FAULTS for attempt in pending):
            return _report(state, frozen, "blocked", "integrity-failure" if any(a["status"] == "integrity-failure" for a in pending) else "callback-error")
        if any(cohort["status"] == "failed" for cohort in state["cohorts"]):
            return _report(state, frozen, "blocked", "integrity-failure")
        reconciled_jobs = {job for row in state["reconciliations"] for job in row["job_ids"]}
        jobs = ({attempt["cohort_id"] for attempt in pending} |
                {cohort["id"] for cohort in state["cohorts"] if cohort["status"] in ("active", "cancelled", "timeout") and cohort["id"] not in reconciled_jobs})
        if pending or jobs:
            if reconcile is None:
                reason = "unreconciled-attempt" if any(not a["cleanup_confirmed"] for a in pending) else "reconciliation-required"
                return _report(state, frozen, "blocked", reason)
            if set(reconcile.attempt_nonces) != {a["nonce"] for a in pending} or set(reconcile.job_ids) != jobs:
                raise SupervisorIntegrityError("reconciliation must name every pending nonce and affected job")
            unknown_cleanup = (any(not a["cleanup_confirmed"] for a in pending) or
                               any(c["id"] in jobs and not c["cleanup_confirmed"] for c in state["cohorts"]))
            if unknown_cleanup and not reconcile.externally_confirmed_stopped:
                raise SupervisorIntegrityError("foreign crash residue needs explicit external stopped confirmation; persisted PIDs are never signaled")
            status = budget.status()
            if status["active_jobs"]:
                if not set(status["active_jobs"]) <= jobs:
                    raise SupervisorIntegrityError("other active ledger jobs need separate owner reconciliation")
                budget.reconcile(stopped_job_ids=status["active_jobs"], reason=reconcile.reason)
            state["reconciliations"].append({"attempt_nonces": list(reconcile.attempt_nonces),
                "job_ids": list(reconcile.job_ids), "reason": reconcile.reason,
                "externally_confirmed_stopped": reconcile.externally_confirmed_stopped})
            persist()
        elif reconcile is not None:
            raise SupervisorIntegrityError("no interrupted attempts require reconciliation")
        done = {row["task_id"] for row in state["completed"]}
        remaining = [task for task in frozen["tasks"] if task["id"] not in done]
        if not remaining:
            return _report(state, frozen, "complete", "all-completed")
        if any(cohort["id"] == job_id for cohort in state["cohorts"]):
            raise SupervisorIntegrityError("each supervised block needs a new job ID")
        prior = budget.status()
        begin = time.monotonic()
        owner = uuid.uuid4().hex
        lease = budget.start_job(job_id, kind=kind, workers=workers,
                                 projected_seconds=projected_seconds, measurement=measurement)
        cohort = {"id": job_id, "owner": owner, "workers": workers, "started_at": begin,
                  "ended_at": None, "status": "active", "cleanup_confirmed": False, "ledger_closed": False,
                  "charged_before": prior["charged_seconds"], "charged_after": None, "cpu_seconds": None, "error": None}
        state["cohorts"].append(cohort)
        active, cursor = {}, 0
        selector = None
        stop_reason, error = None, None
        budget_closed = False
        cap = None
        try:
            persist()
            selector = selectors.DefaultSelector()
            ledger_remaining = lease["deadline"] - budget.clock()
            cap = min(begin + cohort_timeout, begin + ledger_remaining,
                      deadline if deadline is not None else float("inf"))
            stop_at = cap - reserve
            if stop_at <= time.monotonic():
                stop_reason = "cohort-timeout"

            def controls():
                cancellation = cancelled() if cancelled is not None else False
                if type(cancellation) is not bool:
                    raise SupervisorIntegrityError("cancellation must return an exact Boolean")
                now = time.monotonic()
                if cancellation:
                    return "cancelled"
                if now >= stop_at:
                    return "cohort-timeout"
                if any(now - item["launched"] >= task_timeout for item in active.values()):
                    return "task-timeout"
                return None

            def queue_write(item, wire):
                data = (canonical_json(wire) + "\n").encode()
                if item.get("outbound") or len(data) > MAX_MESSAGE:
                    raise SupervisorIntegrityError("invalid or oversized outbound worker frame")
                item["outbound"] = data
                selector.register(item["process"].stdin, selectors.EVENT_WRITE, (item["attempt"]["nonce"], "write"))

            while not stop_reason and (active or cursor < len(remaining)):
                _verify_source(frozen, worker, identity)
                budget.checkpoint()
                stop_reason = controls()
                if stop_reason:
                    break
                while cursor < len(remaining) and len(active) < workers:
                    stop_reason = controls()
                    if stop_reason:
                        break
                    task = remaining[cursor]
                    cursor += 1
                    attempt = {"ordinal": len(state["attempts"]) + 1, "nonce": uuid.uuid4().hex,
                        "task_id": task["id"], "task_hash": _task_hash(frozen, task), "cohort_id": job_id,
                        "status": "reserved", "pid": None, "pgid": None, "started_at": None,
                        "ended_at": None, "cleanup_confirmed": False, "error": None, "cpu_seconds": None}
                    state["attempts"].append(attempt)
                    persist()
                    stop_reason = controls()
                    if stop_reason:
                        break
                    process = subprocess.Popen([sys.executable, "-m", "research.harness.lab_worker"],
                        cwd=REPOSITORY, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        start_new_session=True, bufsize=0)
                    item = {"process": process, "attempt": attempt, "task": task, "buffer": b"", "launched": time.monotonic()}
                    active[attempt["nonce"]] = item
                    attempt.update(status="starting", pid=process.pid, pgid=process.pid)
                    persist()
                    request = {"nonce": attempt["nonce"], "module": worker.module, "function": worker.function, "task": task,
                               "sources": ([{"path": path, "sha256": identity["sources"][label]} for label, path in worker._sources]
                                           + [{"path": str(path), "sha256": identity["runtime"][label]} for label, path in _FRAMEWORK_PATHS.items()])}
                    os.set_blocking(process.stdin.fileno(), False)
                    os.set_blocking(process.stdout.fileno(), False)
                    selector.register(process.stdout, selectors.EVENT_READ, (attempt["nonce"], "read"))
                    queue_write(item, request)
                if stop_reason:
                    break
                for key, _mask in selector.select(.01):
                    stop_reason = controls()
                    if stop_reason:
                        break
                    nonce, direction = key.data
                    if nonce not in active:
                        continue
                    item = active[nonce]
                    if direction == "write":
                        try:
                            sent = os.write(key.fileobj.fileno(), item["outbound"][:65536])
                        except BlockingIOError:
                            continue
                        if not sent:
                            raise SupervisorIntegrityError("worker request pipe made no progress")
                        item["outbound"] = item["outbound"][sent:]
                        if not item["outbound"]:
                            selector.unregister(key.fileobj)
                        continue
                    try:
                        chunk = os.read(key.fileobj.fileno(), 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        raise SupervisorIntegrityError("owned worker exited without an accepted result handshake")
                    item["buffer"] += chunk
                    if len(item["buffer"]) > MAX_MESSAGE:
                        raise SupervisorIntegrityError("worker protocol message exceeds bounded size")
                    while b"\n" in item["buffer"]:
                        stop_reason = controls()
                        if stop_reason:
                            break
                        line, item["buffer"] = item["buffer"].split(b"\n", 1)
                        message = _parse(line)
                        attempt = item["attempt"]
                        if type(message) is not dict or message.get("nonce") != nonce:
                            raise SupervisorIntegrityError("worker nonce handshake mismatch")
                        if message.get("event") == "ready":
                            _fields(message, {"event", "nonce", "pid", "pgid"}, "ready handshake")
                            if (attempt["status"] != "starting" or message["pid"] != item["process"].pid
                                    or message["pgid"] != item["process"].pid or os.getpgid(item["process"].pid) != message["pgid"]):
                                raise SupervisorIntegrityError("worker start ownership mismatch")
                            _verify_source(frozen, worker, identity)
                            if time.monotonic() >= stop_at:
                                stop_reason = "cohort-timeout"
                                break
                            attempt.update(status="running", started_at=time.monotonic())
                            persist()  # callback entry is authorized only after durable identity
                            stop_reason = controls()
                            if stop_reason:
                                break
                            queue_write(item, {"go": nonce})
                        elif message.get("event") in ("result", "error"):
                            if attempt["status"] != "running":
                                raise SupervisorIntegrityError("result arrived before start authorization")
                            if message["event"] == "error":
                                _fields(message, {"event", "nonce", "kind", "error"}, "worker error")
                                attempt.update(status="integrity-failure" if message["kind"] == "integrity-failure" else "fault", error=message["error"])
                                stop_reason = "integrity-failure" if attempt["status"] == "integrity-failure" else "callback-error"
                                break
                            _fields(message, {"event", "nonce", "result", "cpu_seconds"}, "worker result")
                            if not _number(message["cpu_seconds"]):
                                raise SupervisorIntegrityError("invalid worker CPU report")
                            _verify_source(frozen, worker, identity)
                            selector.unregister(item["process"].stdout)
                            _cleanup([item], term_grace, kill_grace, reap_timeout)
                            if item["process"].returncode != 0:
                                raise SupervisorIntegrityError("worker did not acknowledge a successful zero-exit stop")
                            attempt.update(status="completed", cpu_seconds=message["cpu_seconds"])
                            state["completed"].append({"task_id": attempt["task_id"], "task_hash": attempt["task_hash"],
                                "result": message["result"], "result_hash": _result(attempt["task_hash"], message["result"])})
                            state["completed"].sort(key=lambda row: state["task_ids"].index(row["task_id"]))
                            del active[nonce]
                            persist()
                            stop_reason = controls()
                            break
                        else:
                            raise SupervisorIntegrityError("unknown worker protocol event")
                    if stop_reason:
                        break
        except BaseException as caught:
            error = caught
            stop_reason = "integrity-failure"
        finally:
            if selector is not None:
                selector.close()
            try:
                _cleanup(list(active.values()), term_grace, kill_grace, reap_timeout)
                for item in active.values():
                    attempt = item["attempt"]
                    if attempt["status"] not in FAULTS:
                        attempt["status"] = "cancelled" if stop_reason == "cancelled" else "timeout" if stop_reason in ("task-timeout", "cohort-timeout") else "integrity-failure"
                        if attempt["status"] == "integrity-failure":
                            attempt["error"] = {"type": type(error).__name__ if error else "WorkerFailure",
                                                "message": str(error)[:4096] if error else str(stop_reason)}
                # Reserved attempt with a failed launch owns no process.
                for attempt in state["attempts"]:
                    if attempt["cohort_id"] == job_id and attempt["pid"] is None:
                        status = "cancelled" if stop_reason == "cancelled" else "timeout" if stop_reason in ("task-timeout", "cohort-timeout") else "integrity-failure"
                        attempt.update(status=status, cleanup_confirmed=True, ended_at=time.monotonic(),
                                       error={"type": "LaunchFailure", "message": str(error)[:4096]} if status == "integrity-failure" else None)
                cohort["cleanup_confirmed"] = all(a["cleanup_confirmed"] for a in state["attempts"] if a["cohort_id"] == job_id)
                if not cohort["cleanup_confirmed"]:
                    raise SupervisorIntegrityError("owned worker cleanup is unconfirmed; budget remains active")
                if cap is not None and time.monotonic() > cap:
                    stop_reason = "integrity-failure"
                    error = SupervisorIntegrityError("explicit cohort deadline overrun during bounded cleanup")
                outcome = "completed" if stop_reason is None else "cancelled" if stop_reason == "cancelled" else "failed"
                if error is not None:
                    cohort["error"] = {"type": type(error).__name__, "message": str(error)[:4096]}
                closing = budget.finish_job(job_id, outcome=outcome, cpu_seconds=None)
                budget_closed = True
                cohort.update(ledger_closed=True, charged_after=closing["charged_seconds"], ended_at=time.monotonic(),
                              status="completed" if stop_reason is None else "cancelled" if stop_reason == "cancelled" else "timeout" if stop_reason in ("task-timeout", "cohort-timeout") else "failed")
                if closing["overrun"]:
                    stop_reason = "integrity-failure"
                    error = SupervisorIntegrityError("budget overrun recorded; further launches blocked")
                    cohort.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
                if cap is not None and time.monotonic() > cap:
                    stop_reason = "integrity-failure"
                    error = SupervisorIntegrityError("explicit cohort deadline overrun during final accounting")
                    cohort.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
                persist()
            finally:
                if not budget_closed:
                    # Never close an allocation with live/unconfirmed workers.
                    # The durable lease and nonce require explicit reconciliation.
                    pass
        return _report(state, frozen, "cancelled" if stop_reason == "cancelled" else "timeout" if stop_reason in ("task-timeout", "cohort-timeout") else "blocked", stop_reason or "all-completed")
