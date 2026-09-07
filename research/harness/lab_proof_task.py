"""Trusted, separately checked proof paths and external content-addressed receipts.

No research runs at import. ``execute_paths`` is the synthetic testing seam: it
never attests an origin. Only ``run_proof_task`` can attach a freshly replayed,
source-pinned origin. The supervisor owns the *whole-task* hard deadline, including
replay, both paths and artifact I/O; this module starts no per-path allowance.
"""

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import re
import stat
import tempfile
import time
import uuid

from research.harness.lab_origin import bind_origin_provider, verify_origin
from research.harness.lab_proof_producer import ADMINISTRATIVE, produce_certificate
from research.harness.lab_terminal_cert import (
    TerminalCertificate, TerminalProvider, action_id, canonical_hash,
    canonical_json, check_certificate,
)


FORMAT = "varde-lab-proof-task-result"
VERSION = 1
ARTIFACT_ENV = "VARDE_LAB_ARTIFACT_ROOT"
REPOSITORY = Path(__file__).resolve().parents[2]
CLAIM_LIMIT = (
    "Accepted-terminal candidate certification only, conditional on verified "
    "full origin and independent mechanics agreement; not MCTS admission, "
    "strategic depth, strength, balance, or game quality."
)
_RESULT_FIELDS = {"format", "version", "context", "origin", "paths", "comparison",
                  "independently_certified", "admission_record", "claim_limit", "result_hash"}
_PATH_FIELDS = {"provider", "root_fingerprint", "root_actor", "root_seats",
                "root_accepted", "root_domain", "producer", "checker"}


class ProofTaskIntegrityError(ValueError):
    """An origin, mechanics path, source pin or persisted receipt contradicts."""


def _copy(value):
    return json.loads(canonical_json(value))


def _same(actual, expected, label):
    if canonical_json(actual) != canonical_json(expected):
        raise ProofTaskIntegrityError(f"{label} mismatch")


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise ProofTaskIntegrityError(f"invalid {label} fields")


def _sha(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


def _regular(path):
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ProofTaskIntegrityError("artifact is missing") from error
    if not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
        raise ProofTaskIntegrityError("artifact is not a regular non-symlink file")


def _directory(path):
    if path.is_symlink() or not path.is_dir():
        raise ProofTaskIntegrityError("artifact directory is missing, non-directory or symlink")


def _fsync_directory(path):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_json(path, payload):
    """Atomically publish immutable canonical JSON to a *trusted* local path.

    The destination parent must already exist. No overwrite, append or pickle
    deserialization is used. Existing identical bytes can be reused.
    """
    path = Path(path)
    _directory(path.parent)
    data = canonical_json(payload).encode("utf-8")
    if path.exists() or path.is_symlink():
        _regular(path)
        if path.read_bytes() != data:
            raise ProofTaskIntegrityError("immutable artifact collision")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".proof-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            _regular(path)
            if path.read_bytes() != data:
                raise ProofTaskIntegrityError("immutable artifact collision")
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class ArtifactStore:
    """Trusted external root; untrusted references are hashes, never paths."""

    def __init__(self, root):
        path = Path(root).expanduser().absolute()
        if path.is_symlink():
            raise ProofTaskIntegrityError("artifact root cannot be a symlink")
        resolved = path.resolve()
        if resolved == REPOSITORY or REPOSITORY in resolved.parents:
            raise ProofTaskIntegrityError("proof artifacts must be outside the repository")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ProofTaskIntegrityError("artifact root is unavailable or not a directory") from error
        _directory(path)
        self._root = path.resolve()
        if self._root != resolved:
            raise ProofTaskIntegrityError("artifact root changed during creation")
        self._anchor = (path.stat().st_dev, path.stat().st_ino)

    @property
    def root(self):
        return self._root

    def _check_root(self):
        _directory(self._root)
        current = self._root.stat()
        if self._root.resolve() != self._root or (current.st_dev, current.st_ino) != self._anchor:
            raise ProofTaskIntegrityError("artifact root was replaced")

    def _path(self, content_id, *, create=False):
        if type(content_id) is not str or re.fullmatch(r"sha256/[0-9a-f]{2}/[0-9a-f]{64}\.json", content_id) is None:
            raise ProofTaskIntegrityError("invalid content ID")
        parts = content_id.split("/")
        if parts[1] != parts[2][:2]:
            raise ProofTaskIntegrityError("content prefix mismatch")
        self._check_root()
        current = self._root
        for part in parts[:-1]:
            current = current / part
            if create:
                try:
                    current.mkdir(exist_ok=True)
                except OSError as error:
                    raise ProofTaskIntegrityError("artifact subdirectory is unavailable") from error
            _directory(current)
        path = current / parts[-1]
        if path.is_symlink():
            raise ProofTaskIntegrityError("artifact cannot be a symlink")
        return path

    def put_json(self, value):
        data = canonical_json(value).encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        reference = {"content_id": f"sha256/{digest[:2]}/{digest}.json", "bytes": len(data), "sha256": digest}
        publish_json(self._path(reference["content_id"], create=True), value)
        self.audit(reference)
        return reference

    def read(self, reference):
        _fields(reference, {"content_id", "bytes", "sha256"}, "artifact reference")
        if type(reference["bytes"]) is not int or reference["bytes"] < 1 or not _sha(reference["sha256"]):
            raise ProofTaskIntegrityError("invalid artifact length or SHA256")
        expected = f"sha256/{reference['sha256'][:2]}/{reference['sha256']}.json"
        if reference["content_id"] != expected:
            raise ProofTaskIntegrityError("artifact reference identity mismatch")
        path = self._path(reference["content_id"])
        _regular(path)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ProofTaskIntegrityError("artifact changed file type")
            data = stream.read()
        if len(data) != reference["bytes"] or hashlib.sha256(data).hexdigest() != reference["sha256"]:
            raise ProofTaskIntegrityError("artifact bytes do not match reference")
        try:
            value = json.loads(data)
            if canonical_json(value).encode("utf-8") != data:
                raise ValueError("noncanonical JSON")
        except (ValueError, UnicodeError) as error:
            raise ProofTaskIntegrityError("artifact is not canonical finite JSON") from error
        return data

    def read_json(self, reference):
        return json.loads(self.read(reference))

    def audit(self, reference):
        self.read_json(reference)
        return _copy(reference)

    def audit_result(self, result, *, task=None):
        return audit_result(result, self, task=task)

    def put_operational(self, value):
        """Machine-dependent timings are deliberately not semantic references."""
        self._check_root()
        directory = self._root / "operational"
        directory.mkdir(exist_ok=True)
        _directory(directory)
        publish_json(directory / f"{uuid.uuid4().hex}.json", value)


def _limits(producer_nodes, checker_nodes):
    for value in (producer_nodes, checker_nodes):
        if type(value) is not int or not 1 <= value <= 10000:
            raise ProofTaskIntegrityError("proof/checker node cap must be an exact integer in 1..10000")


def _time(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ProofTaskIntegrityError("clock and deadline must be finite numeric values")
    return value


def _elapsed(start, end):
    duration = _time(_time(end) - _time(start))
    if duration < 0:
        raise ProofTaskIntegrityError("monotonic clock moved backwards")
    return duration


def _domain(wires):
    if type(wires) is not list:
        raise ProofTaskIntegrityError("complete legal domain must be an array")
    result = {}
    for wire in _copy(wires):
        identity = action_id(wire)
        if identity in result:
            raise ProofTaskIntegrityError("duplicate complete legal action")
        result[identity] = wire
    return {identity: result[identity] for identity in sorted(result)}


def _validate_descriptor(value):
    _fields(value, _PATH_FIELDS - {"producer", "checker"}, "root descriptor")
    _fields(value["provider"], {"provider_id", "rules_id", "rules_revision", "rules_hash", "implementation_hash"}, "provider descriptor")
    for field in ("provider_id", "rules_id", "rules_revision"):
        if type(value["provider"][field]) is not str or not value["provider"][field].strip():
            raise ProofTaskIntegrityError("invalid provider descriptor label")
    if not _sha(value["provider"]["rules_hash"]) or not _sha(value["provider"]["implementation_hash"]):
        raise ProofTaskIntegrityError("invalid provider descriptor hash")
    actor, seats, accepted = value["root_actor"], value["root_seats"], value["root_accepted"]
    _fields(actor, {"seat", "color"}, "root actor")
    _fields(seats, {"B", "W"}, "root seats")
    if (not _sha(value["root_fingerprint"]) or type(accepted) is not bool
            or any(type(seat) is not str or not seat.strip() for seat in seats.values())
            or len(set(seats.values())) != 2):
        raise ProofTaskIntegrityError("invalid provider root envelope")
    if accepted:
        _same(actor, {"seat": None, "color": None}, "terminal root actor")
    elif actor["color"] not in ("B", "W") or actor["seat"] != seats[actor["color"]]:
        raise ProofTaskIntegrityError("root actor/seat mismatch")
    domain = list(_domain(value["root_domain"]).values())
    _same(value["root_domain"], domain, "canonical root legal domain")
    if bool(domain) == accepted:
        raise ProofTaskIntegrityError("accepted flag contradicts root legal domain")


def _root_descriptor(root, provider):
    if type(provider) is not TerminalProvider:
        raise ProofTaskIntegrityError("a frozen TerminalProvider is required")
    state = deepcopy(root)
    before = pickle.dumps(state, protocol=5)
    try:
        fingerprint = provider.fingerprint(state)
        snapshot = _copy(provider.snapshot(state))
        actor = _copy(provider.actor(state))
        seats = _copy(provider.seats(state))
        accepted = provider.accepted(state)
        wires = [_copy(wire) for wire in provider.legal_actions(state)]
        _same(provider.snapshot(state), snapshot, "provider root snapshot after enumeration")
        if provider.fingerprint(state) != fingerprint:
            raise ProofTaskIntegrityError("provider changed root fingerprint")
    finally:
        if pickle.dumps(state, protocol=5) != before:
            raise ProofTaskIntegrityError("provider mutated root during task enumeration")
    domain = list(_domain(wires).values())
    value = {"provider": _copy(provider.identity()), "root_fingerprint": fingerprint,
             "root_actor": actor, "root_seats": seats, "root_accepted": accepted,
             "root_domain": domain}
    _validate_descriptor(value)
    return value


def _bounds(value):
    if type(value) is not list or len(value) != 2 or any(type(v) is not int or v not in (-1, 0, 1) for v in value) or value[0] > value[1]:
        raise ProofTaskIntegrityError("invalid checked WDL bounds")
    return value


def _checked_claims(report, domain):
    if report is None:
        return None
    value = _copy(report)
    for flag in ("verified", "root_value_exact", "root_domain_complete", "decision_classified", "complete_optimal_action_set"):
        if type(value.get(flag)) is not bool:
            raise ProofTaskIntegrityError("checker report flag must be an exact Boolean")
    if type(value.get("terminal_root")) is not bool and not (value["verified"] is False and value.get("terminal_root") is None):
        raise ProofTaskIntegrityError("checker terminal flag must be known or explicitly unverified")
    _bounds(value["root_bounds"])
    actions = {}
    for row in value["action_results"]:
        _fields(row, {"id", "action", "bounds"}, "checked action")
        if row["id"] != action_id(row["action"]) or row["id"] in actions or row["id"] not in domain:
            raise ProofTaskIntegrityError("checked action does not match complete legal domain")
        _same(row["action"], domain[row["id"]], "checked action wire")
        actions[row["id"]] = _bounds(row["bounds"])
    if value["root_domain_complete"] and set(actions) != set(domain):
        raise ProofTaskIntegrityError("checker claimed an incomplete action domain complete")
    if value["verified"] and value["root_domain_complete"] and actions:
        # The frozen producer's objective is the root actor identity, so the
        # root is maximizing even when takeover or same-seat turns follow.
        aggregate = [max(bounds[index] for bounds in actions.values()) for index in (0, 1)]
        _same(value["root_bounds"], aggregate, "checked root aggregation")
    exact = value["verified"] and value["root_bounds"][0] == value["root_bounds"][1]
    if value["root_value_exact"] is not exact:
        raise ProofTaskIntegrityError("checker root exactness contradicts its bounds")
    _same(value["root_value"], value["root_bounds"][0] if exact else None, "checked root value")
    if value["complete_optimal_action_set"]:
        if not value["verified"] or not value["root_domain_complete"] or any(lo != hi for lo, hi in actions.values()):
            raise ProofTaskIntegrityError("invalid complete checked classification")
        optimal = sorted(identity for identity, bounds in actions.items() if bounds == value["root_bounds"])
        _same(value["optimal_action_ids"], optimal, "complete equivalent optimum set")
    return value, actions


def _audit_checked_certificate(report, certificate, path):
    """Bind a verified receipt to its stored claims, without replay or search.

    This is deliberately only artifact consistency. The frozen checker already
    verified the transitions and recomputed graph values in the charged task.
    A stopped checker has no verified values to copy from the producer.
    """
    claims = _checked_claims(report, _domain(path["root_domain"]))
    _same(report["claimed_resources"], certificate["resources"], "checker claimed producer resources")
    if not claims[0]["verified"]:
        return
    nodes = {node["fingerprint"]: node for node in certificate["graph"]}
    root = nodes[certificate["root"]["fingerprint"]]
    _same(report["root_bounds"], root["bounds"], "verified certificate root bounds")
    _same(report["terminal_root"], root["accepted"], "verified certificate terminal root")
    _same(report["root_domain_complete"], root["kind"] == "expanded", "verified certificate root domain status")
    expected = [{"id": edge["id"], "action": edge["action"],
                 "bounds": nodes[edge["child"]]["bounds"] if edge["child"] is not None else [-1, 1]}
                for edge in sorted(root["actions"], key=lambda edge: edge["id"])]
    _same(report["action_results"], expected, "verified certificate per-action WDL")
    _same(sorted(certificate["root_actions"], key=lambda row: row["id"]),
          [{"id": row["id"], "bounds": row["bounds"]} for row in expected],
          "certificate root action claims")


def compare_reports(production_report, independent_report, *, production_domain, independent_domain, objective):
    """Compare only checker-verified, same-original-seat semantic WDL claims."""
    _fields(objective, {"kind", "seat"}, "objective")
    if objective["kind"] != "accepted-terminal-wdl" or type(objective["seat"]) is not str or not objective["seat"]:
        raise ProofTaskIntegrityError("invalid original-seat WDL objective")
    production = _domain(production_domain)
    independent = None if independent_domain is None else _domain(independent_domain)
    if independent is not None:
        _same(production, independent, "independent complete root legal domains")
    left = _checked_claims(production_report, production)
    right = _checked_claims(independent_report, independent) if independent is not None else None
    if independent is None and independent_report is not None:
        raise ProofTaskIntegrityError("independent report without a mechanics domain")
    complete = False
    if left and right and left[0]["verified"] and right[0]["verified"]:
        for name, a, b in [("root", left[0]["root_bounds"], right[0]["root_bounds"])] + [
                (identity, left[1][identity], right[1][identity]) for identity in sorted(set(left[1]) & set(right[1]))]:
            if max(a[0], b[0]) > min(a[1], b[1]):
                raise ProofTaskIntegrityError(f"independent checked WDL contradiction: {name}")
        complete = (len(production) >= 2 and not left[0]["terminal_root"] and not right[0]["terminal_root"]
                    and left[0]["complete_optimal_action_set"] and right[0]["complete_optimal_action_set"])
        if complete:
            _same(left[1], right[1], "independent exact per-action WDL")
            _same(left[0]["optimal_action_ids"], right[0]["optimal_action_ids"], "independent equivalent optimum set")
    root_class = "partial"
    if left and left[0]["verified"]:
        if left[0]["terminal_root"]:
            root_class = "terminal"
        elif left[0]["complete_optimal_action_set"]:
            root_class = ("forced-administrative" if len(production) == 1 and next(iter(production.values()))["action"] in ADMINISTRATIVE else
                          "all-actions-equivalent" if len(set(tuple(v) for v in left[1].values())) == 1 else "discriminating")
    return {"status": "unqualified-shared-mechanics" if independent is None else "independent-complete" if complete else "independent-partial",
            "independent_complete": bool(complete), "root_domains_equal": independent is not None,
            "root_bounds": left[0]["root_bounds"] if left and left[0]["verified"] else [-1, 1],
            "optimal_action_ids": left[0]["optimal_action_ids"] if complete else [], "root_class": root_class}


def _seal(value):
    result = _copy(value)
    result.pop("result_hash", None)
    result["result_hash"] = canonical_hash(result)
    return result


def _objective(path):
    return {"kind": "accepted-terminal-wdl", "seat": path["root_seats"]["B"] if path["root_accepted"] else path["root_actor"]["seat"]}


def execute_paths(production_root, production_provider, *, independent_root=None,
                  independent_provider=None, store, producer_nodes=10000,
                  checker_nodes=10000, cancelled=None, deadline=None, clock=time.monotonic):
    """Run separately produced/checked paths; no supplied receipt can attest origin.

    Useful with finite synthetic providers. Real-game calls are research work and
    may only be made by the trusted charged coordinator. All roots are detached.
    """
    _limits(producer_nodes, checker_nodes)
    if type(store) is not ArtifactStore or (independent_root is None) != (independent_provider is None):
        raise ProofTaskIntegrityError("artifact store and paired independent root/provider required")
    if deadline is not None:
        _time(deadline)
    original = pickle.dumps((production_root, independent_root), protocol=5)
    start = None
    timing = {"format": "varde-lab-proof-task-timing", "version": 1, "paths": {},
              "stage_artifacts": {}, "outcome": "failed"}
    try:
        start = _time(clock())
        descriptors = {"production": _root_descriptor(production_root, production_provider)}
        if independent_provider is not None:
            descriptors["independent"] = _root_descriptor(independent_root, independent_provider)
            for name in ("root_actor", "root_seats", "root_accepted", "root_domain"):
                _same(descriptors["production"][name], descriptors["independent"][name], f"independent {name}")
        paths, reports = {"production": None, "independent": None}, {}

        def stop():
            if cancelled is not None:
                value = cancelled()
                if type(value) is not bool:
                    raise ProofTaskIntegrityError("cancellation must return an exact Boolean")
                if value:
                    return True
            return deadline is not None and _time(clock()) >= deadline

        for name, root, provider in (("production", production_root, production_provider),
                                     ("independent", independent_root, independent_provider)):
            if provider is None:
                continue
            state = deepcopy(root)
            production = produce_certificate(state, provider, node_limit=producer_nodes,
                                               cancelled=cancelled, deadline=deadline, clock=lambda: _time(clock()))
            canonical = production.canonical_dict()
            certificate = production.certificate
            if certificate is not None:
                payload = certificate.to_dict()
                _same(payload["provider"], descriptors[name]["provider"], "produced provider identity")
                _same(payload["objective"], _objective(descriptors[name]), "produced original-seat objective")
                if payload["root"]["fingerprint"] != descriptors[name]["root_fingerprint"]:
                    raise ProofTaskIntegrityError("producer returned a different root")
            producer_ref = store.put_json(canonical)
            timing["stage_artifacts"][name] = {"producer": producer_ref, "checker": None}
            before_check = _time(clock())
            report = check_certificate(certificate, deepcopy(root), provider, node_limit=checker_nodes,
                                       cancelled=stop).to_dict() if certificate is not None else None
            timing["paths"][name] = {"producer": production.timing, "checker_elapsed_seconds": _elapsed(before_check, clock())}
            checker_ref = store.put_json(report) if report is not None else None
            timing["stage_artifacts"][name]["checker"] = checker_ref
            paths[name] = descriptors[name] | {"producer": producer_ref, "checker": checker_ref}
            reports[name] = report
        comparison = compare_reports(reports["production"], reports.get("independent"),
                                     production_domain=paths["production"]["root_domain"],
                                     independent_domain=paths["independent"]["root_domain"] if paths["independent"] else None,
                                     objective=_objective(paths["production"]))
        result = _seal({"format": FORMAT, "version": VERSION, "context": None, "origin": None,
                        "paths": paths, "comparison": comparison, "independently_certified": False,
                        "admission_record": False, "claim_limit": CLAIM_LIMIT})
        audit_result(result, store)
        timing["outcome"] = "completed"
        return result
    except Exception as error:
        timing["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        try:
            if start is not None:
                timing["elapsed_seconds"] = _elapsed(start, clock())
                store.put_operational(timing)
        finally:
            if pickle.dumps((production_root, independent_root), protocol=5) != original:
                raise ProofTaskIntegrityError("task callbacks mutated an original caller root")


def _context(task, payload):
    row = payload["row"]
    return {"task_id": task["id"], "payload_hash": task["payload_hash"], "source": payload["source"],
            "row_hash": payload["row_hash"], "origin_hash": row["origin_hash"] if row else None}


def run_proof_task(task):
    """Trusted supervisor callback, with source guards on success and failure."""
    from research.harness.lab_proof_jobs import validate_proof_task, verify_runtime_source

    source = task.get("payload", {}).get("source") if type(task) is dict and type(task.get("payload")) is dict else None
    try:
        verify_runtime_source(source)
        payload = validate_proof_task(task)
        root = os.environ.get(ARTIFACT_ENV)
        if type(root) is not str or not root:
            raise ProofTaskIntegrityError("trusted coordinator artifact environment is required")
        store = ArtifactStore(root)
        row = payload["row"]
        context = _context(task, payload)
        if row is None:
            return _seal({"format": FORMAT, "version": VERSION, "context": context, "origin": None,
                          "paths": {"production": None, "independent": None},
                          "comparison": {"status": "missing", "independent_complete": False, "root_domains_equal": False,
                                         "root_bounds": [-1, 1], "optimal_action_ids": [], "root_class": "partial"},
                          "independently_certified": False, "admission_record": False, "claim_limit": CLAIM_LIMIT})
        verified = verify_origin(row["origin"])
        _same(verified.record.to_dict(), row["origin"], "full frozen origin record")
        _same(verified.receipt, row["origin_receipt"], "fresh origin receipt")
        if verified.receipt["root_fingerprint"] != row["root_fingerprint"]:
            raise ProofTaskIntegrityError("fresh origin root differs from selected row")
        production_root, independent_root = verified.production_root, verified.independent_root
        production = bind_origin_provider(verified, production_root)
        independent = bind_origin_provider(verified, independent_root, independent=True) if independent_root is not None else None
        descriptor = _root_descriptor(production_root, production)
        stamp = row["origin"]["final"]["stamp"]
        for name, actual in (("actor", descriptor["root_actor"]), ("seats", descriptor["root_seats"]), ("accepted", descriptor["root_accepted"])):
            _same(actual, stamp[name], f"fresh origin {name}")
        if len(descriptor["root_domain"]) != row["legal_action_count"]:
            raise ProofTaskIntegrityError("fresh root legal count differs from frozen row")
        result = execute_paths(production_root, production, independent_root=independent_root,
                               independent_provider=independent, store=store, **payload["limits"])
        result["context"] = context
        result["origin"] = {"record": store.put_json(verified.record.to_dict()), "receipt": store.put_json(verified.receipt)}
        result["independently_certified"] = (result["comparison"]["independent_complete"]
                                              and verified.receipt["full_action_replay"] is True
                                              and verified.receipt["factory_origin_verified"] is True
                                              and verified.receipt["independent_mechanics"] is True)
        result = _seal(result)
        return audit_result(result, store, task=task)
    finally:
        verify_runtime_source(source)


def audit_result(result, store, *, task=None):
    """Read and hash-audit every receipt without rerunning a proof or an origin.

    An expected task additionally prevents transplantation between candidate
    rows. This is artifact validation, not a new independent proof or admission.
    """
    value = _copy(result)
    _fields(value, _RESULT_FIELDS, "proof task result")
    if value["format"] != FORMAT or type(value["version"]) is not int or value["version"] != VERSION:
        raise ProofTaskIntegrityError("unsupported proof task result")
    if (type(value["independently_certified"]) is not bool or value["admission_record"] is not False
            or value["claim_limit"] != CLAIM_LIMIT or not _sha(value["result_hash"])):
        raise ProofTaskIntegrityError("invalid proof task claim or hash")
    _same(_seal(value), value, "proof task result hash")
    payload = None
    if task is not None:
        from research.harness.lab_proof_jobs import validate_proof_task
        payload = validate_proof_task(task)
        _same(value["context"], _context(task, payload), "expected manifested task")
    if value["context"] is not None:
        _fields(value["context"], {"task_id", "payload_hash", "source", "row_hash", "origin_hash"}, "result task context")
        if type(value["context"]["task_id"]) is not str or not _sha(value["context"]["payload_hash"]):
            raise ProofTaskIntegrityError("invalid task context identity")
    _fields(value["paths"], {"production", "independent"}, "mechanics paths")
    reports = {}
    for name, path in value["paths"].items():
        if path is None:
            continue
        _fields(path, _PATH_FIELDS, "proof path")
        _validate_descriptor({key: item for key, item in path.items() if key not in ("producer", "checker")})
        production = store.read_json(path["producer"])
        _fields(production, {"format", "version", "certificate", "telemetry"}, "canonical producer artifact")
        if production["format"] != "varde-lab-proof-production" or type(production["version"]) is not int or production["version"] != 1:
            raise ProofTaskIntegrityError("invalid canonical producer artifact")
        _same(production["telemetry"]["provider"], path["provider"], "producer artifact provider")
        certificate = production["certificate"]
        if certificate is None:
            if path["checker"] is not None:
                raise ProofTaskIntegrityError("checker receipt without a producer certificate")
            reports[name] = None
        else:
            certificate = TerminalCertificate.from_dict(certificate).to_dict()
            _same(certificate["provider"], path["provider"], "certificate provider")
            _same(certificate["objective"], _objective(path), "certificate original-seat objective")
            if certificate["root"]["fingerprint"] != path["root_fingerprint"]:
                raise ProofTaskIntegrityError("certificate root fingerprint mismatch")
            _same(certificate["root"]["actor"], path["root_actor"], "certificate root actor")
            graph_root = next(node for node in certificate["graph"] if node["fingerprint"] == path["root_fingerprint"])
            _same(graph_root["seats"], path["root_seats"], "certificate root seats")
            _same(graph_root["accepted"], path["root_accepted"], "certificate root accepted flag")
            report = store.read_json(path["checker"])
            if report["certificate_hash"] != canonical_hash(certificate):
                raise ProofTaskIntegrityError("checker receipt refers to a different certificate")
            _audit_checked_certificate(report, certificate, path)
            reports[name] = report
    paths = value["paths"]
    if paths["production"] is None:
        if paths["independent"] is not None or value["origin"] is not None or value["independently_certified"] or value["context"] is None:
            raise ProofTaskIntegrityError("invalid missing task result")
        expected = {"status": "missing", "independent_complete": False, "root_domains_equal": False,
                    "root_bounds": [-1, 1], "optimal_action_ids": [], "root_class": "partial"}
        if payload is not None and payload["row"] is not None:
            raise ProofTaskIntegrityError("existing candidate reported as missing")
    else:
        if paths["independent"]:
            for field in ("root_actor", "root_seats", "root_accepted", "root_domain"):
                _same(paths["production"][field], paths["independent"][field], f"artifact independent {field}")
        expected = compare_reports(reports["production"], reports.get("independent"),
                                   production_domain=paths["production"]["root_domain"],
                                   independent_domain=paths["independent"]["root_domain"] if paths["independent"] else None,
                                   objective=_objective(paths["production"]))
    _same(value["comparison"], expected, "checked semantic comparison")
    eligible = False
    if value["origin"] is not None:
        from research.harness.lab_origin import OriginRecord
        _fields(value["origin"], {"record", "receipt"}, "origin artifacts")
        record = OriginRecord.from_dict(store.read_json(value["origin"]["record"])).to_dict()
        receipt = store.read_json(value["origin"]["receipt"])
        body = dict(receipt)
        digest = body.pop("receipt_hash", None)
        if digest != canonical_hash(body) or receipt["record_hash"] != record["record_hash"]:
            raise ProofTaskIntegrityError("origin receipt checksum or record mismatch")
        if value["context"] is None or value["context"]["origin_hash"] != record["record_hash"]:
            raise ProofTaskIntegrityError("origin context mismatch")
        if payload is not None:
            if payload["row"] is None:
                raise ProofTaskIntegrityError("missing slot supplied an origin")
            _same(record, payload["row"]["origin"], "manifested origin artifact")
            _same(receipt, payload["row"]["origin_receipt"], "manifested origin receipt")
        for name, key in (("production", "root_fingerprint"), ("independent", "independent_root_fingerprint")):
            if paths[name] and paths[name]["root_fingerprint"] != receipt[key]:
                raise ProofTaskIntegrityError("origin-bound path fingerprint mismatch")
        eligible = (expected["independent_complete"] and receipt["factory_origin_verified"] is True
                    and receipt["full_action_replay"] is True and receipt["independent_mechanics"] is True)
    elif value["context"] is not None and paths["production"] is not None:
        raise ProofTaskIntegrityError("trusted task result is missing its origin")
    if value["independently_certified"] is not eligible:
        raise ProofTaskIntegrityError("certification label does not match checked origin-bound evidence")
    return value
