"""Pinned, proof-free job preparation for the frozen Rules Laboratory corpus.

All paths that can be read as source are code-owned constants. Corpus and task
JSON are data, never imports or commands. Loading authenticates historical bytes
and structure only: it does not replay origins, enumerate actions, or certify a
decision. Selected origins must be replayed by the later charged worker.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from research.harness.lab_corpus import (  # noqa: E402
    CorpusManifest, FIXED_PATHS as CORPUS_PATHS, ROW_FIELDS,
)
from research.harness.lab_fixed_tasks import FixedTaskManifest  # noqa: E402
from research.harness.lab_origin import (  # noqa: E402
    CLAIM_LIMIT as ORIGIN_CLAIM_LIMIT, LEGACY_LIMIT, OriginRecord,
    runtime_sources as origin_runtime_sources,
)
from research.harness.lab_research_adapter import LEGACY_CANDIDATES, PRODUCTION_RULESETS  # noqa: E402
from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402

VERSION = 1
TASK_FORMAT = "varde-lab-proof-task"
CONFIG_FORMAT = "varde-lab-proof-jobs"
RAW_SHA256 = "d1dc7d7bd23b036862ddcffe9915fb5b7932147c838f93c4ef29fea9e255f7fc"
MANIFEST_HASH = "e6331d93f1a2cf887eedc8c7c95f01585808cdc7a09b0b903433d765da9b64b8"
INDEX_SHA256 = "5b0cedefb4b8ced6ce8786ac5cb197b79d8c9c76117a8eccc5e59eeb8c123561"
INDEX_PATH = "docs/elves/rules-lab-v1-candidate-index.json"
SIZES = (3, 4)
SPLITS = ("development", "holdout")
STAGES = ("bootstrap", "certification")
BOOTSTRAP_LIMITS = {"producer_nodes": 32, "checker_nodes": 128}
BOOTSTRAP_EXECUTION = {"workers": 8, "task_timeout": 20, "cohort_timeout": 120,
                       "reserved_capacity": 156, "projection_kind": "declared-hard-reservation"}
CLAIM_LIMIT = (
    "Authenticated historical candidate data and fixed proof tasks only; no new "
    "origin replay, terminal certification, throughput measurement, MCTS admission, "
    "or game-quality evidence."
)
SOURCE_PATHS = tuple(sorted(set(CORPUS_PATHS) | {
    "docs/rules-lab-corpus-contract.md", "research/harness/lab_corpus_candidates.py",
    INDEX_PATH, "docs/rules-lab-proof-jobs-contract.md",
    "research/harness/lab_proof_jobs.py", "research/harness/lab_proof_task.py",
    "research/harness/lab_research_cli.py", "research/harness/lab_proof_producer.py",
    "research/harness/lab_fixed_tasks.py", "research/harness/lab_supervisor.py",
    "research/harness/lab_worker.py", "research/harness/lab_budget.py",
}))
HISTORICAL_SOURCE_PATHS = tuple(sorted(set(CORPUS_PATHS) | {
    "docs/rules-lab-corpus-contract.md", "research/harness/lab_corpus_candidates.py",
}))
INDEX_ROW_FIELDS = {
    "id", "definition_hash", "disposition", "reason", "representative_id", "split",
    "origin_hash", "root_fingerprint", "spatial_key", "legal_action_count",
    "equivalence", "certified", "rules_id", "rules_revision", "n", "template_id", "family",
}
TASK_FIELDS = {"format", "version", "stage", "slot", "cell", "corpus", "source", "row", "row_hash", "limits"}
CONFIG_FIELDS = {"format", "version", "stage", "corpus", "limits", "order", "execution", "claim_limit"}


class ProofJobIntegrityError(ValueError):
    """Malformed or drifted proof-job inputs; never permission to retry work."""


def _copy(value):
    try:
        return json.loads(canonical_json(value))
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise ProofJobIntegrityError("expected finite JSON data") from error


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise ProofJobIntegrityError(f"invalid {label} fields")


def _same(left, right, label):
    if canonical_json(left) != canonical_json(right):
        raise ProofJobIntegrityError(f"{label} mismatch")


def _hash(value, label, width=64):
    if type(value) is not str or len(value) != width or any(c not in "0123456789abcdef" for c in value):
        raise ProofJobIntegrityError(f"invalid {label} hash")


def _text(value, label):
    if type(value) is not str or not value or value.strip() != value:
        raise ProofJobIntegrityError(f"invalid {label}")


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ProofJobIntegrityError(f"invalid {label}")


def _parse(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProofJobIntegrityError("duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ProofJobIntegrityError("nonfinite JSON")))
        return _copy(value)
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise ProofJobIntegrityError("malformed proof-job JSON") from error


def _read(path):
    try:
        return Path(path).read_bytes()
    except (OSError, TypeError, ValueError) as error:
        raise ProofJobIntegrityError("authoritative input is unavailable") from error


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def authoritative_sources():
    """Closed trusted paths for TrustedWorker; no data-supplied path is opened."""
    result = {}
    root = REPOSITORY.resolve()
    for label in SOURCE_PATHS:
        path = REPOSITORY / label
        if not path.resolve().is_relative_to(root):
            raise ProofJobIntegrityError("authoritative source escapes the repository")
        result[label] = path
    return result


# Existing modules at this import cannot later be relabeled as changed code.
# New sibling files absent during staging are still required by runtime checks.
_LOADED_SOURCES = {label: _digest(path.read_bytes()) for label, path in authoritative_sources().items()
                   if path.is_file()}


def runtime_source_hashes():
    """Read the closed source set and guard files observed at module import."""
    hashes = {label: _digest(_read(path)) for label, path in authoritative_sources().items()}
    for label, digest in _LOADED_SOURCES.items():
        if hashes[label] != digest:
            raise ProofJobIntegrityError("proof-job dependencies changed since import")
    try:
        origin_runtime_sources()
    except ValueError as error:
        raise ProofJobIntegrityError("origin runtime source drift") from error
    return hashes


def _source(source):
    _fields(source, {"commit", "hashes"}, "source")
    _hash(source["commit"], "source commit", 40)
    _fields(source["hashes"], SOURCE_PATHS, "closed source hash mapping")
    for digest in source["hashes"].values():
        _hash(digest, "source file")


def verify_runtime_source(source):
    """Verify actual bytes only; commit ancestry is a coordinator check."""
    _source(source)
    _same(runtime_source_hashes(), source["hashes"], "runtime source bytes")


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=REPOSITORY, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ProofJobIntegrityError("committed source verification failed") from error


def validate_committed_source(source=None):
    """Bind HEAD on preparation, or accept an unchanged ancestor on resume.

    Only fixed repository labels are read by git-show. The source must already
    be committed; a dirty or newly created closed dependency cannot be launched.
    Unrelated documentation changes need not invalidate an unchanged ancestor.
    """
    hashes = runtime_source_hashes()
    head = _git("rev-parse", "HEAD").decode("ascii").strip()
    _hash(head, "HEAD", 40)
    value = {"commit": head, "hashes": hashes} if source is None else _copy(source)
    _source(value)
    _same(hashes, value["hashes"], "declared source bytes")
    _git("merge-base", "--is-ancestor", value["commit"], head)
    for label in SOURCE_PATHS:
        if _digest(_git("show", f"{value['commit']}:{label}")) != hashes[label]:
            raise ProofJobIntegrityError(f"worktree/committed source mismatch: {label}")
    _same(runtime_source_hashes(), hashes, "source bytes after commit validation")
    return _copy(value)


def corpus_identity():
    return {"raw_sha256": RAW_SHA256, "manifest_hash": MANIFEST_HASH, "index_sha256": INDEX_SHA256}


def _historical_sources(index):
    hashes = index["sources"]["hashes"]
    _fields(hashes, HISTORICAL_SOURCE_PATHS, "frozen corpus sources")
    # The corpus cannot choose paths: only the closed code-owned labels above.
    for label in HISTORICAL_SOURCE_PATHS:
        if _digest(_read(REPOSITORY / label)) != hashes[label]:
            raise ProofJobIntegrityError(f"frozen corpus source drift: {label}")
    try:
        origin_runtime_sources()
    except ValueError as error:
        raise ProofJobIntegrityError("loaded historical source drift") from error


def _compact_index():
    data = _read(REPOSITORY / INDEX_PATH)
    if _digest(data) != INDEX_SHA256:
        raise ProofJobIntegrityError("frozen compact index physical hash mismatch")
    index = _parse(data)
    if index["raw_manifest_hash"] != MANIFEST_HASH:
        raise ProofJobIntegrityError("frozen compact semantic corpus mismatch")
    if index["index_hash"] != canonical_hash({k: v for k, v in index.items() if k != "index_hash"}):
        raise ProofJobIntegrityError("frozen compact index semantic hash mismatch")
    _historical_sources(index)
    return index


@dataclass(frozen=True)
class AuthenticatedCorpus:
    """Immutable pinned bytes; structural authentication is not fresh replay."""

    _raw_bytes: bytes

    def __post_init__(self):
        if type(self._raw_bytes) is not bytes or _digest(self._raw_bytes) != RAW_SHA256:
            raise ProofJobIntegrityError("frozen raw corpus physical hash mismatch")
        value = _parse(self._raw_bytes)
        try:
            # Direct canonical construction is structure-only. from_dict would
            # replay every origin and is deliberately not used here.
            manifest = CorpusManifest(canonical_json(value))
        except (ValueError, TypeError, KeyError) as error:
            raise ProofJobIntegrityError("invalid frozen corpus structure") from error
        if manifest.manifest_hash != MANIFEST_HASH:
            raise ProofJobIntegrityError("frozen corpus semantic hash mismatch")
        _same(manifest.compact_index(), _compact_index(), "raw/compact correspondence")

    @property
    def identity(self):
        return corpus_identity()

    def to_dict(self):
        return _parse(self._raw_bytes)

    @property
    def rows(self):
        return tuple(self.to_dict()["candidates"])


def load_frozen_corpus(raw_path):
    """Read an explicit trusted input path without origin/proof execution."""
    return AuthenticatedCorpus(_read(raw_path))


def _selector_rows(index_rows):
    if type(index_rows) not in (list, tuple) or len(index_rows) > 512:
        raise ProofJobIntegrityError("selector needs at most 512 indexed rows")
    rows, seen, counts = [], set(), {}
    required = {"id", "rules_id", "n", "split", "disposition"}
    for original in index_rows:
        if type(original) is not dict or not required <= set(original) <= INDEX_ROW_FIELDS:
            raise ProofJobIntegrityError("invalid indexed selector row")
        row = _copy(original)
        _text(row["id"], "candidate ID")
        if row["id"] in seen:
            raise ProofJobIntegrityError("duplicate indexed candidate ID")
        seen.add(row["id"])
        if type(row["rules_id"]) is not str or row["rules_id"] not in PRODUCTION_RULESETS:
            raise ProofJobIntegrityError("unknown indexed ruleset")
        _integer(row["n"], 3, 4, "indexed board size")
        if type(row["disposition"]) is not str or row["disposition"] not in (
                "candidate", "accepted-terminal", "single-action", "duplicate", "invalid-origin"):
            raise ProofJobIntegrityError("invalid indexed disposition")
        if row["disposition"] == "candidate":
            if type(row["split"]) is not str or row["split"] not in SPLITS:
                raise ProofJobIntegrityError("candidate needs a fixed split")
        elif row["split"] is not None:
            raise ProofJobIntegrityError("excluded row cannot have a split")
        cell = row["rules_id"], row["n"]
        counts[cell] = counts.get(cell, 0) + 1
        if counts[cell] > 16:
            raise ProofJobIntegrityError("indexed cell exceeds sixteen frozen candidates")
        rows.append(row)
    return rows


def select_bootstrap_rows(index_rows):
    """Pure structural selector; synthetic rows confer no production authority."""
    rows = _selector_rows(index_rows)
    result = []
    for n in SIZES:
        for rules in PRODUCTION_RULESETS:
            eligible = sorted(row["id"] for row in rows if row["rules_id"] == rules and row["n"] == n
                              and row["disposition"] == "candidate" and row["split"] == "development")
            result.append({"slot": len(result), "rules_id": rules, "n": n,
                           "candidate_id": eligible[0] if eligible else None})
    return tuple(result)


def select_certification_rows(index_rows):
    """Round robin rules after ordinal interleaving their four fixed subcells."""
    rows = _selector_rows(index_rows)
    buckets = []
    for rules in PRODUCTION_RULESETS:
        cells = [sorted((row for row in rows if row["rules_id"] == rules
                         and row["disposition"] == "candidate" and row["n"] == n and row["split"] == split),
                        key=lambda row: row["id"])
                 for n in SIZES for split in SPLITS]
        buckets.append([cell[offset] for offset in range(max(map(len, cells), default=0))
                        for cell in cells if offset < len(cell)])
    return tuple(bucket[offset]["id"] for offset in range(max(map(len, buckets), default=0))
                 for bucket in buckets if offset < len(bucket))


def _limits(value, stage):
    _fields(value, {"producer_nodes", "checker_nodes"}, "per-path node limits")
    for number in value.values():
        _integer(number, 1, 10000, "per-path node ceiling")
    if stage == "bootstrap":
        _same(value, BOOTSTRAP_LIMITS, "frozen bootstrap node limits")


def _indexed(row):
    result = {key: row[key] for key in INDEX_ROW_FIELDS if key in row}
    definition = row["definition"]
    result.update({key: definition["configuration"][key] for key in ("rules_id", "rules_revision", "n")})
    result.update({key: definition[key] for key in ("template_id", "family")})
    return result


def _validate_row(row, expected):
    _fields(row, ROW_FIELDS, "selected frozen row")
    _same(_indexed(row), expected, "frozen compact candidate identity")
    try:
        origin = OriginRecord.from_dict(row["origin"]).to_dict()
    except (ValueError, TypeError, KeyError) as error:
        raise ProofJobIntegrityError("invalid selected origin structure") from error
    _same(row["definition"], {
        "id": expected["id"], "configuration": origin["configuration"],
        "actions": [edge["action"] for edge in origin["actions"]],
        "template_id": expected["template_id"], "family": expected["family"],
    }, "definition/origin correspondence")
    if canonical_hash(row["definition"]) != expected["definition_hash"] or origin["record_hash"] != expected["origin_hash"]:
        raise ProofJobIntegrityError("selected definition/origin hash mismatch")
    if origin["final"]["stamp"]["fingerprint"] != expected["root_fingerprint"]:
        raise ProofJobIntegrityError("selected root fingerprint mismatch")
    # This checks historical receipt structure, not a new replay. The exact
    # origin hash is already bound by the physically pinned compact index.
    independent = expected["rules_id"] not in LEGACY_CANDIDATES
    receipt = {"format": "varde-lab-origin-receipt", "version": 1,
               "record_hash": origin["record_hash"], "source_hash": origin["sources"]["bundle_hash"],
               "factory_origin_verified": True, "full_action_replay": True,
               "independent_mechanics": independent, "mechanics_limit": None if independent else LEGACY_LIMIT,
               "action_count": len(origin["actions"]),
               "initial_fingerprint": origin["initial"]["stamp"]["fingerprint"],
               "root_fingerprint": origin["final"]["stamp"]["fingerprint"],
               "independent_root_fingerprint": origin["final"]["stamp"]["independent_fingerprint"],
               "admission_record": False, "claim_limit": ORIGIN_CLAIM_LIMIT}
    receipt["receipt_hash"] = canonical_hash(receipt)
    _same(row["origin_receipt"], receipt, "historical origin receipt")


def _task_id(stage, slot, rules, n):
    return f"{stage}-{slot:03d}-{rules}-n{n}"


def _validate_task(task, index):
    _fields(task, {"id", "payload", "payload_hash"}, "proof task envelope")
    _hash(task["payload_hash"], "payload")
    payload = task["payload"]
    _fields(payload, TASK_FIELDS, "proof task payload")
    if task["payload_hash"] != canonical_hash(payload):
        raise ProofJobIntegrityError("proof task payload hash mismatch")
    if payload["format"] != TASK_FORMAT or type(payload["version"]) is not int or payload["version"] != VERSION:
        raise ProofJobIntegrityError("unsupported proof task")
    stage = payload["stage"]
    if type(stage) is not str or stage not in STAGES:
        raise ProofJobIntegrityError("unknown proof task stage")
    _integer(payload["slot"], 0, 31 if stage == "bootstrap" else 511, "task slot")
    _fields(payload["cell"], {"rules_id", "n"}, "task cell")
    rules, n = payload["cell"]["rules_id"], payload["cell"]["n"]
    if type(rules) is not str or rules not in PRODUCTION_RULESETS:
        raise ProofJobIntegrityError("unknown task ruleset")
    _integer(n, 3, 4, "task board size")
    if task["id"] != _task_id(stage, payload["slot"], rules, n):
        raise ProofJobIntegrityError("task ID/order identity mismatch")
    _same(payload["corpus"], corpus_identity(), "frozen corpus pins")
    _source(payload["source"])
    _limits(payload["limits"], stage)
    indexed = {row["id"]: row for row in index["candidates"]}
    if stage == "bootstrap":
        selected = select_bootstrap_rows(index["candidates"])[payload["slot"]]
        _same(payload["cell"], {"rules_id": selected["rules_id"], "n": selected["n"]}, "bootstrap slot cell")
        expected_id = selected["candidate_id"]
    else:
        ordered = select_certification_rows(index["candidates"])
        if payload["slot"] >= len(ordered):
            raise ProofJobIntegrityError("certification slot exceeds frozen candidates")
        expected_id = ordered[payload["slot"]]
    row = payload["row"]
    if expected_id is None:
        if row is not None or payload["row_hash"] is not None:
            raise ProofJobIntegrityError("missing slot cannot contain a substitute")
    else:
        expected = indexed[expected_id]
        _same(payload["cell"], {"rules_id": expected["rules_id"], "n": expected["n"]}, "selected cell")
        _hash(payload["row_hash"], "selected row")
        if row is None or payload["row_hash"] != canonical_hash(row):
            raise ProofJobIntegrityError("selected row hash mismatch")
        _validate_row(row, expected)
    return _copy(payload)


def validate_proof_task(task):
    """Validate detached data against the pinned index, without replay/search."""
    try:
        return _validate_task(_copy(task), _compact_index())
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ProofJobIntegrityError("malformed proof task structure") from error


def _configuration(stage, limits):
    return {"format": CONFIG_FORMAT, "version": VERSION, "stage": stage,
            "corpus": corpus_identity(), "limits": _copy(limits),
            "order": "size-then-rules-development-first-id" if stage == "bootstrap" else "rules-round-robin-four-subcell-ordinal-id",
            "execution": _copy(BOOTSTRAP_EXECUTION) if stage == "bootstrap" else None,
            "claim_limit": CLAIM_LIMIT}


def validate_proof_manifest(value):
    """Validate a complete fixed manifest. Runtime/Git checks remain explicit."""
    try:
        manifest = FixedTaskManifest.from_dict(value.to_dict() if isinstance(value, FixedTaskManifest) else value)
        wire = manifest.to_dict()
        config = wire["configuration"]
        _fields(config, CONFIG_FIELDS, "proof configuration")
        stage = config["stage"]
        if type(stage) is not str or stage not in STAGES:
            raise ProofJobIntegrityError("unknown proof manifest stage")
        _limits(config["limits"], stage)
        _same(config, _configuration(stage, config["limits"]), "fixed proof configuration")
        _source(wire["source"])
        index = _compact_index()
        count = 32 if stage == "bootstrap" else len(select_certification_rows(index["candidates"]))
        if len(wire["tasks"]) != count:
            raise ProofJobIntegrityError("manifest omits or adds frozen task slots")
        for ordinal, task in enumerate(wire["tasks"]):
            payload = _validate_task(task, index)
            if payload["stage"] != stage or payload["slot"] != ordinal:
                raise ProofJobIntegrityError("manifest changes frozen task order")
            _same(payload["source"], wire["source"], "task/manifest source")
            _same(payload["limits"], config["limits"], "task/manifest limits")
        return manifest
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ProofJobIntegrityError("malformed proof manifest structure") from error
    except ValueError as error:
        if isinstance(error, ProofJobIntegrityError):
            raise
        raise ProofJobIntegrityError("invalid fixed proof manifest") from error


def _build(corpus, stage, limits, source):
    if type(corpus) is not AuthenticatedCorpus:
        raise ProofJobIntegrityError("production manifests require the authenticated frozen corpus")
    _limits(limits, stage)
    index = _compact_index()
    source = validate_committed_source(source)
    rows = {row["id"]: row for row in corpus.rows}
    if stage == "bootstrap":
        selected = select_bootstrap_rows(index["candidates"])
    else:
        by_id = {row["id"]: row for row in index["candidates"]}
        selected = tuple({"slot": slot, "rules_id": by_id[name]["rules_id"], "n": by_id[name]["n"], "candidate_id": name}
                         for slot, name in enumerate(select_certification_rows(index["candidates"])))
    tasks = []
    for item in selected:
        row = rows[item["candidate_id"]] if item["candidate_id"] is not None else None
        payload = {"format": TASK_FORMAT, "version": VERSION, "stage": stage, "slot": item["slot"],
                   "cell": {"rules_id": item["rules_id"], "n": item["n"]},
                   "corpus": corpus_identity(), "source": source, "row": row,
                   "row_hash": canonical_hash(row) if row is not None else None, "limits": limits}
        tasks.append({"id": _task_id(stage, item["slot"], item["rules_id"], item["n"]), "payload": payload})
    manifest = FixedTaskManifest.create(source=source, configuration=_configuration(stage, limits), tasks=tasks)
    result = validate_proof_manifest(manifest)
    verify_runtime_source(source)
    return result


def build_bootstrap_manifest(corpus, *, source=None):
    return _build(corpus, "bootstrap", _copy(BOOTSTRAP_LIMITS), source)


def build_certification_manifest(corpus, *, source=None, producer_nodes=10000, checker_nodes=10000):
    return _build(corpus, "certification", {"producer_nodes": producer_nodes, "checker_nodes": checker_nodes}, source)
