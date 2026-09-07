"""Deterministic in-process tasks, not a research launcher or worker supervisor.

The trusted callback is sequential and cannot be interrupted by this scaffold.
Cancellation/deadline checks occur between tasks only. An external supervisor and
budget integration are still required before charged work. Source hashes are
caller declarations: paths/commands in manifest content are never opened/run.

Checkpoints detect corruption, not an attacker who can rewrite all bound hashes.
A durable running attempt precedes each callback. Ambiguous crash residue and
callback/integrity failures block automatic retry. Successful result hashes omit
timings and attempts; complete records retain the frozen manifest order.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import fcntl
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402


MANIFEST_FORMAT = "varde-lab-fixed-tasks"
CHECKPOINT_FORMAT = "varde-lab-fixed-task-checkpoint"
RUN_FORMAT = "varde-lab-fixed-task-run"
VERSION = 1
MANIFEST_FIELDS = {"format", "version", "source", "source_hash", "configuration",
                   "configuration_hash", "tasks", "manifest_hash"}
CHECKPOINT_FIELDS = {"format", "version", "manifest_hash", "task_ids", "completed", "attempts"}
ATTEMPT_FIELDS = {"ordinal", "task_id", "task_hash", "status", "started", "elapsed_seconds", "error"}
STATUSES = {"running", "completed", "cancelled", "deadline", "failed", "integrity-failure", "interrupted"}
BLOCKING = {"running", "failed", "integrity-failure", "interrupted"}
CLAIM_LIMIT = (
    "Sequential trusted-callback scaffold only; not a research launcher, worker "
    "supervisor, hard-deadline enforcement, origin attestation, or admission record."
)


class FixedTaskIntegrityError(ValueError):
    """Invalid manifests/checkpoints, callback mutation, or ambiguous execution."""


def _copy_json(value):
    return json.loads(canonical_json(value))


def _fields(value, expected, label):
    if type(value) is not dict or set(value) != expected:
        raise FixedTaskIntegrityError(f"invalid {label} fields")


def _text(value, label):
    if type(value) is not str or not value or value.strip() != value:
        raise FixedTaskIntegrityError(f"invalid {label}")


def _hash(value, label, width=64):
    if type(value) is not str or len(value) != width or any(char not in "0123456789abcdef" for char in value):
        raise FixedTaskIntegrityError(f"invalid {label} hash")


def _finite_time(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _source(value):
    _fields(value, {"commit", "hashes"}, "source")
    _hash(value["commit"], "source commit", 40)
    hashes = value["hashes"]
    if type(hashes) is not dict or not hashes:
        raise FixedTaskIntegrityError("source hashes must be a nonempty named mapping")
    for label, digest in hashes.items():
        _text(label, "source label")
        _hash(digest, "source file")


def _validate_manifest(value):
    _fields(value, MANIFEST_FIELDS, "manifest")
    canonical_json(value)
    if value["format"] != MANIFEST_FORMAT or type(value["version"]) is not int or value["version"] != VERSION:
        raise FixedTaskIntegrityError("unsupported fixed-task manifest")
    _source(value["source"])
    if type(value["configuration"]) is not dict:
        raise FixedTaskIntegrityError("configuration must be a complete JSON object")
    for field, content in (("source_hash", "source"), ("configuration_hash", "configuration")):
        _hash(value[field], field)
        if value[field] != canonical_hash(value[content]):
            raise FixedTaskIntegrityError(f"mismatched {field}")
    if type(value["tasks"]) is not list or not value["tasks"]:
        raise FixedTaskIntegrityError("a frozen nonempty task list is required")
    seen = set()
    for task in value["tasks"]:
        _fields(task, {"id", "payload", "payload_hash"}, "task")
        _text(task["id"], "task ID")
        if task["id"] in seen:
            raise FixedTaskIntegrityError("duplicate task ID")
        seen.add(task["id"])
        _hash(task["payload_hash"], "task payload")
        if task["payload_hash"] != canonical_hash(task["payload"]):
            raise FixedTaskIntegrityError("mismatched task payload hash")
    _hash(value["manifest_hash"], "manifest")
    if value["manifest_hash"] != canonical_hash({key: item for key, item in value.items() if key != "manifest_hash"}):
        raise FixedTaskIntegrityError("mismatched manifest hash")


@dataclass(frozen=True)
class FixedTaskManifest:
    """Immutable canonical wire storage; every returned object is detached."""

    _json: str

    def __post_init__(self):
        if type(self._json) is not str:
            raise FixedTaskIntegrityError("manifest storage must be canonical JSON")
        value = _parse_json(self._json)
        _validate_manifest(value)
        if canonical_json(value) != self._json:
            raise FixedTaskIntegrityError("manifest storage is not canonical")

    @classmethod
    def create(cls, *, source, configuration, tasks):
        if type(tasks) is not list:
            raise FixedTaskIntegrityError("task declarations must be an ordered list")
        rows = []
        for task in tasks:
            _fields(task, {"id", "payload"}, "task declaration")
            rows.append(_copy_json(task) | {"payload_hash": canonical_hash(task["payload"])})
        value = {"format": MANIFEST_FORMAT, "version": VERSION,
                 "source": _copy_json(source), "source_hash": canonical_hash(source),
                 "configuration": _copy_json(configuration), "configuration_hash": canonical_hash(configuration),
                 "tasks": rows}
        value["manifest_hash"] = canonical_hash(value)
        return cls.from_dict(value)

    @classmethod
    def from_dict(cls, value):
        _validate_manifest(value)
        return cls(canonical_json(value))

    def to_dict(self):
        return json.loads(self._json)

    @property
    def manifest_hash(self):
        return self.to_dict()["manifest_hash"]


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise FixedTaskIntegrityError("duplicate JSON object key")
        value[key] = item
    return value


def _parse_json(text):
    try:
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(FixedTaskIntegrityError("nonfinite JSON")))
    except (TypeError, json.JSONDecodeError, RecursionError) as error:
        raise FixedTaskIntegrityError("malformed fixed-task JSON") from error


def _task_hash(manifest_hash, task):
    return canonical_hash({"manifest_hash": manifest_hash, "id": task["id"], "payload_hash": task["payload_hash"]})


def _result_hash(task_hash, result):
    return canonical_hash({"task_hash": task_hash, "result": result})


def _validate_checkpoint(state, manifest):
    _fields(state, CHECKPOINT_FIELDS, "checkpoint")
    canonical_json(state)
    if state["format"] != CHECKPOINT_FORMAT or type(state["version"]) is not int or state["version"] != VERSION:
        raise FixedTaskIntegrityError("unsupported fixed-task checkpoint")
    tasks = manifest["tasks"]
    if state["manifest_hash"] != manifest["manifest_hash"] or state["task_ids"] != [task["id"] for task in tasks]:
        raise FixedTaskIntegrityError("checkpoint belongs to a different frozen manifest")
    completed, attempts = state["completed"], state["attempts"]
    if type(completed) is not list or len(completed) > len(tasks) or type(attempts) is not list:
        raise FixedTaskIntegrityError("invalid checkpoint task accounting")
    for index, record in enumerate(completed):
        _fields(record, {"task_id", "task_hash", "result", "result_hash"}, "completed result")
        expected_hash = _task_hash(manifest["manifest_hash"], tasks[index])
        if record["task_id"] != tasks[index]["id"] or record["task_hash"] != expected_hash:
            raise FixedTaskIntegrityError("completed results must be a manifest-ordered prefix")
        if record["result_hash"] != _result_hash(expected_hash, record["result"]):
            raise FixedTaskIntegrityError("mismatched completed result hash")
    cursor = 0
    for index, attempt in enumerate(attempts):
        _fields(attempt, ATTEMPT_FIELDS, "attempt")
        if cursor >= len(tasks):
            raise FixedTaskIntegrityError("attempt recorded after manifest completion")
        if (type(attempt["ordinal"]) is not int or attempt["ordinal"] != index + 1
                or attempt["task_id"] != tasks[cursor]["id"]
                or attempt["task_hash"] != _task_hash(manifest["manifest_hash"], tasks[cursor])
                or type(attempt["status"]) is not str or attempt["status"] not in STATUSES
                or type(attempt["started"]) is not bool):
            raise FixedTaskIntegrityError("attempt violates fixed task order or identity")
        status, started, elapsed, error = (attempt[key] for key in ("status", "started", "elapsed_seconds", "error"))
        if elapsed is not None and not _finite_time(elapsed):
            raise FixedTaskIntegrityError("invalid attempt timing")
        if not started and elapsed != 0:
            raise FixedTaskIntegrityError("unstarted callback cannot claim elapsed execution")
        if error is not None:
            _fields(error, {"type", "message"}, "attempt error")
            _text(error["type"], "error type")
            if type(error["message"]) is not str:
                raise FixedTaskIntegrityError("invalid error message")
        if status in ("running", "interrupted") and (not started or elapsed is not None):
            raise FixedTaskIntegrityError("ambiguous attempt must retain unknown elapsed time")
        if status == "completed":
            if not started or elapsed is None or error is not None:
                raise FixedTaskIntegrityError("invalid completed attempt")
            cursor += 1
        if status in ("cancelled", "deadline") and (started or elapsed != 0 or error is not None):
            raise FixedTaskIntegrityError("between-task stop cannot claim callback execution")
        if status in ("failed", "integrity-failure", "interrupted") and error is None:
            raise FixedTaskIntegrityError("fault is missing explicit error accounting")
        if status == "running" and error is not None:
            raise FixedTaskIntegrityError("running attempt cannot contain an error outcome")
        if status in BLOCKING and index != len(attempts) - 1:
            raise FixedTaskIntegrityError("blocked attempt was automatically retried")
    if cursor != len(completed):
        raise FixedTaskIntegrityError("completed results disagree with attempt accounting")


def _external_path(value):
    try:
        path = Path(value).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise FixedTaskIntegrityError("explicit external checkpoint path required") from error
    if path == REPOSITORY or REPOSITORY in path.parents:
        raise FixedTaskIntegrityError("checkpoints must be outside the repository")
    return path


def load_checkpoint(manifest, checkpoint_path):
    """Read and detach a checksummed checkpoint; never execute its content."""
    if not isinstance(manifest, FixedTaskManifest):
        raise FixedTaskIntegrityError("a validated FixedTaskManifest is required")
    path = _external_path(checkpoint_path)
    try:
        envelope = _parse_json(path.read_text())
        _fields(envelope, {"payload", "sha256"}, "checkpoint envelope")
        _hash(envelope["sha256"], "checkpoint checksum")
        if envelope["sha256"] != canonical_hash(envelope["payload"]):
            raise FixedTaskIntegrityError("checkpoint checksum mismatch")
        _validate_checkpoint(envelope["payload"], manifest.to_dict())
        return _copy_json(envelope["payload"])
    except (OSError, UnicodeError) as error:
        raise FixedTaskIntegrityError("unreadable external checkpoint") from error


def _write_checkpoint(path, state, manifest):
    _validate_checkpoint(state, manifest)
    envelope = {"payload": state, "sha256": canonical_hash(state)}
    contents = (canonical_json(envelope) + "\n").encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=path.name + ".", suffix=".tmp",
                                         dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise FixedTaskIntegrityError("checkpoint persistence failed; inspect durable state before continuation") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _ownership(path):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.with_suffix(path.suffix + ".lock").open("a+b")
    except OSError as error:
        raise FixedTaskIntegrityError("checkpoint ownership unavailable") from error
    with handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise FixedTaskIntegrityError("checkpoint is already owned; no concurrent callback allowed") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class FixedTaskRun:
    _json: str

    def to_dict(self):
        return json.loads(self._json)

    @property
    def canonical_results_hash(self):
        return self.to_dict()["canonical_results_hash"]


def _report(state, manifest):
    complete = len(state["completed"]) == len(manifest["tasks"])
    last = state["attempts"][-1]["status"] if state["attempts"] else None
    if complete:
        status, reason = "complete", "all-completed"
    elif last in BLOCKING:
        status = "blocked"
        reason = {"running": "unreconciled-attempt", "interrupted": "unreconciled-attempt",
                  "failed": "callback-error", "integrity-failure": "integrity-failure"}[last]
    else:
        status, reason = "partial", last if last in ("cancelled", "deadline") else "not-started"
    canonical = {"manifest_hash": manifest["manifest_hash"], "completed": state["completed"]}
    value = {"format": RUN_FORMAT, "version": VERSION, "manifest_hash": manifest["manifest_hash"],
             "status": status, "reason": reason, "complete": complete,
             "declared_tasks": len(manifest["tasks"]), "completed": state["completed"],
             "remaining_ids": [task["id"] for task in manifest["tasks"][len(state["completed"]):]],
             "canonical_results_hash": canonical_hash(canonical), "attempts": state["attempts"],
             "hard_deadline_enforced": False, "admission_record": False, "claim_limit": CLAIM_LIMIT,
             "source_identity_verified": False}
    return FixedTaskRun(canonical_json(value))


def _error(error):
    try:
        message = str(error)[:4096]
    except Exception:
        message = "Exception message could not be formatted."
    return {"type": type(error).__name__, "message": message}


def _execute(callback, task):
    detached = deepcopy(task)
    before = canonical_json(detached)
    try:
        result = callback(detached)
    finally:
        try:
            changed = canonical_json(detached) != before
        except ValueError as error:
            raise FixedTaskIntegrityError("callback invalidated its task input") from error
        if changed:
            raise FixedTaskIntegrityError("callback mutated its task input")
    try:
        return _copy_json(result)
    except ValueError as error:
        raise FixedTaskIntegrityError("callback result is not finite JSON") from error


def run_fixed_tasks(manifest, callback, *, checkpoint_path, clock=time.monotonic,
                    deadline=None, cancelled=None):
    """Run frozen tasks sequentially, stopping only BETWEEN callback invocations.

    Running callbacks cannot be interrupted here. A fault or an ambiguous prior
    invocation blocks without retry; callers need a later explicit reconciliation
    protocol, not deletion/resealing of this checkpoint, to resolve that state.
    """
    if not isinstance(manifest, FixedTaskManifest):
        raise FixedTaskIntegrityError("a validated FixedTaskManifest is required")
    if not callable(callback) or not callable(clock) or (cancelled is not None and not callable(cancelled)):
        raise FixedTaskIntegrityError("trusted local callbacks are required")
    if deadline is not None and not _finite_time(deadline):
        raise FixedTaskIntegrityError("deadline must be a finite nonnegative clock value")
    path, frozen = _external_path(checkpoint_path), manifest.to_dict()
    previous_time = None

    def now():
        nonlocal previous_time
        value = clock()
        if not _finite_time(value) or (previous_time is not None and value < previous_time):
            raise FixedTaskIntegrityError("clock is invalid or ran backwards")
        previous_time = value
        return value

    with _ownership(path):
        if path.exists():
            state = load_checkpoint(manifest, path)
        else:
            state = {"format": CHECKPOINT_FORMAT, "version": VERSION,
                     "manifest_hash": frozen["manifest_hash"], "task_ids": [task["id"] for task in frozen["tasks"]],
                     "completed": [], "attempts": []}
            _write_checkpoint(path, state, frozen)
        if state["attempts"] and state["attempts"][-1]["status"] in BLOCKING:
            # Preserve the original running record; elapsed work is unknown and
            # this scaffold cannot assert that its external effects never ran.
            return _report(state, frozen)
        for task in frozen["tasks"][len(state["completed"]):]:
            task_hash = _task_hash(frozen["manifest_hash"], task)
            attempt = {"ordinal": len(state["attempts"]) + 1, "task_id": task["id"],
                       "task_hash": task_hash, "status": "running", "started": False,
                       "elapsed_seconds": 0, "error": None}
            try:
                start = now()
                cancellation = cancelled() if cancelled is not None else False
                if type(cancellation) is not bool:
                    raise FixedTaskIntegrityError("cancellation callback must return an exact Boolean")
                start = now()  # control callback time cannot make a deadline stale
            except BaseException as error:
                attempt.update(status="integrity-failure" if isinstance(error, FixedTaskIntegrityError) else "failed",
                               error=_error(error))
                state["attempts"].append(attempt)
                _write_checkpoint(path, state, frozen)
                return _report(state, frozen)
            if cancellation or (deadline is not None and start >= deadline):
                attempt["status"] = "cancelled" if cancellation else "deadline"
                state["attempts"].append(attempt)
                _write_checkpoint(path, state, frozen)
                return _report(state, frozen)
            attempt.update(started=True, elapsed_seconds=None)
            state["attempts"].append(attempt)
            _write_checkpoint(path, state, frozen)
            try:
                result = _execute(callback, task)
                elapsed = now() - start
            except BaseException as error:
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    status = "interrupted"
                else:
                    status = "integrity-failure" if isinstance(error, FixedTaskIntegrityError) else "failed"
                attempt.update(status=status, error=_error(error))
                if status != "interrupted":
                    try:
                        attempt["elapsed_seconds"] = now() - start
                    except BaseException:
                        pass  # unknown timing is explicit, never a zero substitute
                _write_checkpoint(path, state, frozen)
                return _report(state, frozen)
            attempt.update(status="completed", elapsed_seconds=elapsed)
            state["completed"].append({"task_id": task["id"], "task_hash": task_hash,
                                       "result": result, "result_hash": _result_hash(task_hash, result)})
            _write_checkpoint(path, state, frozen)
        return _report(state, frozen)
