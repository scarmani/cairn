"""Read-only, evidence-graded reporting from frozen laboratory artifacts.

No replay, search, proof checking or budget writer is used here. The public
from_dict/validate interfaces validate interchange data, not external bytes;
load_evidence_inputs is the file-authentication boundary. An evidence parent's
commit and current report-tool hashes are deliberately different provenance.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
for directory in (REPOSITORY, REPOSITORY / "engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from lab_evidence import empty_card, entry, validate_card  # noqa: E402
from lab_spec import EXPERIMENT_REGISTRY  # noqa: E402
from varde import get_ruleset_spec  # noqa: E402
from research.harness.lab_record import validate_lab_record_shape  # noqa: E402
from research.harness.lab_research_adapter import LEGACY_CANDIDATES, PRODUCTION_RULESETS  # noqa: E402
from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402

INPUT_FORMAT = "varde-lab-evidence-inputs"
BUNDLE_FORMAT = "varde-lab-evidence-bundle"
VERSION = 1
CLAIM_LIMIT = (
    "Engineering verification, specification inventories and one incomplete operational bootstrap only. "
    "No independently certified decisions, admitted agents, comparative games, strategic ranking, "
    "human observations or game-quality conclusions."
)
INDEX_PINS = {
    "corpus": ("docs/elves/rules-lab-v1-candidate-index.json", "5b0cedefb4b8ced6ce8786ac5cb197b79d8c9c76117a8eccc5e59eeb8c123561"),
    "browser": ("docs/elves/rules-lab-v1-batch4d-artifacts.json", "c6d87b0d052365d89f75111492793d36b265c8db7831edf425057cbbf5b2c2ff"),
    "bootstrap": ("docs/elves/rules-lab-v1-batch5g-artifacts.json", "197468deca08caf5c83ef435682ce86a45430c84d40fcefd4369d4a129488af5"),
}
CORPUS_MANIFEST_HASH = "e6331d93f1a2cf887eedc8c7c95f01585808cdc7a09b0b903433d765da9b64b8"
CORPUS_INDEX_HASH = "bd9b9c7cac33876c43af7060c7892a4ee556ba67dddeb2a47dac024f2d2fa9c7"
BROWSER_RAW = "batch-4d-artifacts.json"
BROWSER_AUDIT = "batch-4d-browser/matrix-2-and-3-mechanical-replay.json"
MAJORITY_RECEIPT = "batch-4d-browser/majority-four-edges-replay.json"
MAJORITY_RECORD = "batch-4d-browser/objectives-2/majority-four-edges-record.json"
BOOTSTRAP_FILES = ("batch-5g-summary.json", "batch-5g-run.json", "batch-5g-audit.json")
RECORD_NAMES = (
    "breath-connection-record.json", "gjerde-majority-record.json",
    "junction-passage-0-record.json", "junction-passage-1-record.json", "junction-passage-2-record.json",
    "junction-planted-0-record.json", "junction-planted-1-record.json", "junction-six-0-record.json",
    "junction-y-0-record.json", "junction-y-1-record.json", "junction-y-complete-record.json", "line-breath-record.json",
)
SELECTED_PATHS = tuple(f"batch-4d-browser/matrix-3/{name}" for name in RECORD_NAMES) + (MAJORITY_RECORD,)
EXCLUDED_PATHS = tuple(f"batch-4d-browser/matrix-2/{name}" for name in RECORD_NAMES)
SOURCE_PATHS = (
    "research/harness/lab_evidence_bundle.py", "engine/lab_evidence.py", "engine/lab_spec.py",
    "engine/varde.py", "research/harness/lab_record.py", "research/harness/lab_research_adapter.py",
    "research/harness/lab_terminal_cert.py", "docs/rules-lab-evidence.md", "docs/rules-lab-specs.md",
    "docs/rules-lab-browser.md", "docs/rules-lab-analysis-contract.md",
)
INPUT_FIELDS = {"format", "version", "source", "pins", "catalog", "candidate_inventory", "bootstrap", "selected_records", "excluded_records"}
BUNDLE_FIELDS = {"format", "version", "source", "pins", "cards", "candidate_inventory", "bootstrap", "script_coverage", "record_selection", "comparative_shortlist", "claim_limit", "bundle_hash"}
RECEIPT_FIELDS = {"format", "version", "mechanically_verified", "action_count", "accepted", "replay_hash", "claim_limit"}
METADATA_FIELDS = {"path", "sha256", "provenance", "replay_receipt", "ruleset", "revision", "board_size", "action_count", "accepted"}
PIN_PATHS = {key: path for key, (path, _) in INDEX_PINS.items()} | {"browser_raw": BROWSER_RAW} | {
    path: path for path in (BROWSER_AUDIT, MAJORITY_RECEIPT) + SELECTED_PATHS + EXCLUDED_PATHS + BOOTSTRAP_FILES
}


class EvidenceBundleIntegrityError(ValueError):
    """Input corruption or an evidence claim beyond the frozen scope."""


def _copy(value):
    try:
        return json.loads(canonical_json(value))
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise EvidenceBundleIntegrityError("expected finite JSON evidence") from error


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise EvidenceBundleIntegrityError(f"invalid {label} fields")


def _same(actual, expected, label):
    if canonical_json(actual) != canonical_json(expected):
        raise EvidenceBundleIntegrityError(f"{label} mismatch")


def _hash(value, width=64):
    if type(value) is not str or len(value) != width or any(c not in "0123456789abcdef" for c in value):
        raise EvidenceBundleIntegrityError("invalid evidence hash")


def _integer(value, *, low=0):
    if type(value) is not int or value < low:
        raise EvidenceBundleIntegrityError("evidence count must be an exact nonnegative integer")


def _path(value):
    if (type(value) is not str or not value or "\\" in value or "\x00" in value
            or PurePosixPath(value).is_absolute() or str(PurePosixPath(value)) != value
            or any(part in (".", "..") for part in PurePosixPath(value).parts)):
        raise EvidenceBundleIntegrityError("artifact must have a canonical relative path")
    return value


def _read(root, relative):
    relative = _path(relative)
    try:
        root = Path(root).resolve(strict=True)
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise EvidenceBundleIntegrityError("artifact escapes its explicit input root")
        return path.read_bytes()
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, EvidenceBundleIntegrityError):
            raise
        raise EvidenceBundleIntegrityError("evidence input unavailable") from error


def _parse(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceBundleIntegrityError("duplicate evidence JSON key")
            result[key] = value
        return result
    try:
        return _copy(json.loads(data, object_pairs_hook=unique,
                                parse_constant=lambda _: (_ for _ in ()).throw(EvidenceBundleIntegrityError("nonfinite JSON"))))
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise EvidenceBundleIntegrityError("malformed evidence JSON") from error


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _read_pinned(root, path, digest, *, size=None):
    _hash(digest)
    data = _read(root, path)
    if _digest(data) != digest or (size is not None and len(data) != size):
        raise EvidenceBundleIntegrityError(f"artifact bytes/hash mismatch: {path}")
    return _parse(data)


def _references(rows):
    if type(rows) is not list:
        raise EvidenceBundleIntegrityError("artifact references must be a list")
    result = {}
    for row in rows:
        if type(row) is not dict or set(row) not in ({"path", "sha256"}, {"path", "sha256", "bytes"}, {"path", "sha256", "kind"}):
            raise EvidenceBundleIntegrityError("invalid historical artifact reference")
        path = _path(row["path"])
        _hash(row["sha256"])
        if "bytes" in row:
            _integer(row["bytes"])
        if path in result:
            raise EvidenceBundleIntegrityError("duplicate artifact reference")
        result[path] = row
    return result


def _ref_read(root, refs, path):
    if path not in refs:
        raise EvidenceBundleIntegrityError(f"required frozen artifact is absent: {path}")
    ref = refs[path]
    return _read_pinned(root, path, ref["sha256"], size=ref.get("bytes"))


def _catalog():
    result = []
    for rules in PRODUCTION_RULESETS:
        if rules in LEGACY_CANDIDATES:
            spec = get_ruleset_spec(rules).public_dict()
            availability, concepts, hypothesis = "legacy-candidate", None, None
        else:
            spec = EXPERIMENT_REGISTRY[rules].public_dict()
            availability = spec["experimental_availability"]
            concepts, hypothesis = spec["rule_concepts"], spec["hypothesis"]
        result.append({"id": rules, "revision": spec["revision"], "label": spec["label"],
                       "availability": availability, "geometry": spec["geometry"], "scoring": spec["scoring"],
                       "description": spec["description"], "rule_concepts": concepts, "hypothesis": hypothesis,
                       "rules_hash": canonical_hash(spec), "rules_hash_scope": "frozen-registry-specification-descriptor"})
    return result


_LOADED_SOURCES = {path: _digest(_read(REPOSITORY, path)) for path in SOURCE_PATHS}


def _source(source_commit):
    _hash(source_commit, 40)
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", source_commit, "HEAD"], cwd=REPOSITORY,
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        for path, digest in INDEX_PINS.values():
            committed = subprocess.run(["git", "show", f"{source_commit}:{path}"], cwd=REPOSITORY,
                                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            if _digest(committed.stdout) != digest:
                raise EvidenceBundleIntegrityError("declared evidence parent lacks the exact frozen indices")
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceBundleIntegrityError("declared evidence parent is not a known ancestor") from error
    hashes = {path: _digest(_read(REPOSITORY, path)) for path in SOURCE_PATHS}
    _same(hashes, _LOADED_SOURCES, "loaded reporting dependencies")
    return {"commit": source_commit, "commit_role": "evidence-parent", "hashes": hashes,
            "hash_scope": "actual-report-tool-and-frozen-dependencies"}


def _check_source(source):
    _fields(source, {"commit", "commit_role", "hashes", "hash_scope"}, "report source")
    _hash(source["commit"], 40)
    if source["commit_role"] != "evidence-parent" or source["hash_scope"] != "actual-report-tool-and-frozen-dependencies":
        raise EvidenceBundleIntegrityError("source parent/tool scope is ambiguous")
    _fields(source["hashes"], SOURCE_PATHS, "closed report source hashes")
    for digest in source["hashes"].values():
        _hash(digest)


def _receipt(value, record):
    _receipt_metadata(value, action_count=len(record["actions"]), accepted=record["status"] == "complete")


def _receipt_metadata(value, *, action_count, accepted):
    _fields(value, RECEIPT_FIELDS, "existing mechanical replay receipt")
    if (value["format"] != "varde-lab-record-replay" or type(value["version"]) is not int or value["version"] != 1
            or value["mechanically_verified"] is not True or type(value["accepted"]) is not bool):
        raise EvidenceBundleIntegrityError("invalid historical replay claim")
    _hash(value["replay_hash"])
    _integer(value["action_count"])
    if value["action_count"] != action_count or value["accepted"] != accepted:
        raise EvidenceBundleIntegrityError("historical receipt/record counters disagree")
    if value["claim_limit"] != "mechanical replay only; not a qualified human study or game-quality finding":
        raise EvidenceBundleIntegrityError("historical replay claim changed")


def _record_metadata(item):
    record = item["record"]
    return {key: item[key] for key in ("path", "sha256", "provenance", "replay_receipt")} | {
        "ruleset": record["rules"]["id"], "revision": record["rules"]["revision"], "board_size": record["board_size"],
        "action_count": len(record["actions"]), "accepted": record["status"] == "complete",
    }


def _load_records(root, refs, audit, majority_receipt):
    matrices = audit.get("matrices")
    if type(matrices) is not list or [row.get("matrix") for row in matrices] != [2, 3]:
        raise EvidenceBundleIntegrityError("expected historical Matrix2 and final Matrix3 audits")
    receipt_by_path = {}
    for matrix in matrices:
        if matrix["exported_records"] != 12 or matrix["successful_replays"] != 12 or matrix["export_replay_errors"] != 0:
            raise EvidenceBundleIntegrityError("historical export accounting changed")
        entries = matrix["entries"]
        exports = [entry for entry in entries if entry.get("artifact_kind") == "exported-record"]
        if sorted(entry["file"] for entry in exports) != sorted(RECORD_NAMES):
            raise EvidenceBundleIntegrityError("frozen export role membership changed")
        for item in exports:
            path = f"batch-4d-browser/matrix-{matrix['matrix']}/{item['file']}"
            if item["exit_code"] != 0 or item["source_sha256"] != refs[path]["sha256"]:
                raise EvidenceBundleIntegrityError("export/replay source hash mismatch")
            receipt_by_path[path] = {key: item[key] for key in RECEIPT_FIELDS}
    receipt_by_path[MAJORITY_RECORD] = majority_receipt
    selected, excluded = [], []
    for path in SELECTED_PATHS + EXCLUDED_PATHS:
        raw = _ref_read(root, refs, path)
        record = validate_lab_record_shape(raw)
        receipt = receipt_by_path[path]
        _receipt(receipt, record)
        item = {"path": path, "sha256": refs[path]["sha256"], "record": record,
                "provenance": {"kind": "engineering-ui-automation", "source_id": path}, "replay_receipt": receipt}
        if path in SELECTED_PATHS:
            selected.append(item)
        else:
            excluded.append(_record_metadata(item) | {"reason": "superseded-matrix-2"})
    return selected, excluded


def _validate_inventory(inventory, catalog):
    if type(inventory) is not list or [row.get("rules_id") for row in inventory] != list(PRODUCTION_RULESETS):
        raise EvidenceBundleIntegrityError("candidate inventory must preserve all sixteen identities")
    for row, spec in zip(inventory, catalog):
        _fields(row, {"rules_id", "rules_revision", "sizes", "dual_mechanical_origin_available", "independent_mechanics",
                      "independence_status", "mechanics_limit", "certified_counts", "required_certified_per_split",
                      "admission_status"}, "candidate inventory row")
        _same(row["certified_counts"], {"development": 0, "holdout": 0}, "uncertified inventory counts")
        _same(row["required_certified_per_split"], 8, "required certificates")
        independent = row["rules_id"] not in LEGACY_CANDIDATES
        if (row["dual_mechanical_origin_available"] is not independent or row["independent_mechanics"] is not independent
                or row["independence_status"] != ("origin-only" if independent else "unqualified-shared-mechanics")
                or type(row["mechanics_limit"]) is not str or not row["mechanics_limit"].strip()):
            raise EvidenceBundleIntegrityError("mechanical independence metadata changed")
        if row["rules_revision"] != spec["revision"]:
            raise EvidenceBundleIntegrityError("candidate inventory cannot imply certification")
        _fields(row["sizes"], {"3", "4"}, "candidate sizes")
        if row["admission_status"] != "incomplete":
            raise EvidenceBundleIntegrityError("invalid candidate coverage")
        for counts in row["sizes"].values():
            _fields(counts, {"proposed", "dispositions", "structural_counts"}, "candidate size counts")
            _fields(counts["dispositions"], {"accepted-terminal", "single-action", "duplicate", "invalid-origin", "candidate"}, "candidate dispositions")
            _fields(counts["structural_counts"], {"development", "holdout"}, "structural counts")
            _integer(counts["proposed"])
            for value in counts["dispositions"].values():
                _integer(value)
            for value in counts["structural_counts"].values():
                _integer(value)
            if sum(counts["dispositions"].values()) != counts["proposed"]:
                raise EvidenceBundleIntegrityError("candidate accounting mismatch")
            if sum(counts["structural_counts"].values()) != counts["dispositions"]["candidate"]:
                raise EvidenceBundleIntegrityError("structural candidates are not certificates")


def _validate_pins(pins):
    _fields(pins, PIN_PATHS, "closed evidence input pins")
    for key, path in PIN_PATHS.items():
        ref = pins[key]
        _fields(ref, {"path", "sha256"}, "input pin")
        if _path(ref["path"]) != path:
            raise EvidenceBundleIntegrityError("input pin path/role mismatch")
        _hash(ref["sha256"])
    for key, (path, digest) in INDEX_PINS.items():
        _same(pins[key], {"path": path, "sha256": digest}, "fixed index pin")


def _expected_record_rule(path):
    if path not in SELECTED_PATHS + EXCLUDED_PATHS:
        raise EvidenceBundleIntegrityError("record path has no frozen export role")
    name = path.rsplit("/", 1)[1]
    if name == "majority-four-edges-record.json":
        return "gjerde-majority"
    return next(rule for rule in PRODUCTION_RULESETS if rule not in LEGACY_CANDIDATES and name.startswith(rule + "-"))


def _validate_metadata(item, pins, *, excluded=False):
    _fields(item, METADATA_FIELDS | ({"reason"} if excluded else set()), "record metadata")
    if item["path"] not in (EXCLUDED_PATHS if excluded else SELECTED_PATHS):
        raise EvidenceBundleIntegrityError("record assigned to the wrong role")
    if excluded and item["reason"] != "superseded-matrix-2":
        raise EvidenceBundleIntegrityError("superseded export exclusion changed")
    _same(item["sha256"], pins[item["path"]]["sha256"], "record source pin")
    _same(item["provenance"], {"kind": "engineering-ui-automation", "source_id": item["path"]}, "script provenance")
    if item["ruleset"] != _expected_record_rule(item["path"]) or item["revision"] != "0.1":
        raise EvidenceBundleIntegrityError("frozen record rule identity mismatch")
    _integer(item["action_count"])
    if type(item["accepted"]) is not bool or type(item["board_size"]) is not int or item["board_size"] not in (3, 4, 5, 6):
        raise EvidenceBundleIntegrityError("invalid trace metadata")
    _receipt_metadata(item["replay_receipt"], action_count=item["action_count"], accepted=item["accepted"])


def _validate_bootstrap(bootstrap):
    _fields(bootstrap, {"semantic", "accounting"}, "bootstrap evidence")
    accounting = bootstrap["accounting"]
    _same(accounting, {"status": "timeout", "reason": "task-timeout", "task_count": 32,
                       "attempted": 14, "completed": 6, "interrupted": 8, "unstarted": 18,
                       "independently_certified": 0, "admitted_agents": 0, "all_cleanup_confirmed": True}, "frozen bootstrap accounting")
    semantic = bootstrap["semantic"]
    _fields(semantic, {"admission_record", "canonical_results_hash", "completed", "manifest_hash", "not_completed"}, "bootstrap semantics")
    if (semantic["admission_record"] is not False or type(semantic["completed"]) is not list
            or len(semantic["completed"]) != 6 or type(semantic["not_completed"]) is not list):
        raise EvidenceBundleIntegrityError("bootstrap cannot establish admission")
    _hash(semantic["manifest_hash"])
    _hash(semantic["canonical_results_hash"])
    ids = [f"bootstrap-{index:03d}-{rules}-n{size}" for index, (size, rules) in enumerate(
        (size, rules) for size in (3, 4) for rules in PRODUCTION_RULESETS)]
    _same(semantic["not_completed"], ids[6:], "uncompleted frozen bootstrap slots")
    for index, row in enumerate(semantic["completed"]):
        _fields(row, {"cell", "comparison", "independently_certified", "paths", "result_hash", "task_id"}, "completed bootstrap task")
        if row["independently_certified"] is not False or row["task_id"] != ids[index]:
            raise EvidenceBundleIntegrityError("legacy partial result was promoted")
        _same(row["cell"], {"n": 3, "rules_id": LEGACY_CANDIDATES[index]}, "completed legacy bootstrap cell")
        _hash(row["result_hash"])
        _same(row["comparison"], {"independent_complete": False, "optimal_action_ids": [], "root_bounds": [-1, 1],
                                  "root_class": "partial", "root_domains_equal": False,
                                  "status": "unqualified-shared-mechanics"}, "unqualified partial comparison")
        _fields(row["paths"], {"independent", "production"}, "bootstrap proof paths")
        if row["paths"]["independent"] is not None:
            raise EvidenceBundleIntegrityError("no independent bootstrap task completed")
        production = row["paths"]["production"]
        _fields(production, {"checker_reason", "checker_status", "checker_verified", "checker_work", "producer_reason",
                             "producer_status", "producer_work", "root_width"}, "partial production path")
        for key, expected in (("checker_reason", "node-limit"), ("checker_status", "unknown"),
                              ("checker_verified", False), ("producer_reason", "node-limit"), ("producer_status", "partial")):
            _same(production[key], expected, "partial bootstrap proof status")
        _integer(production["root_width"], low=2)
        for key, fields in (("checker_work", {"callback_calls", "legal_action_enumerations", "nodes_checked", "terminal_scores_checked",
                                              "terminal_simulation_backups", "transition_attempts", "unknown_successors_checked"}),
                            ("producer_work", {"actions_enumerated", "callback_calls", "legal_action_enumerations", "memo_hits", "nodes",
                                               "terminal_leaves", "terminal_simulation_backups", "transition_attempts"})):
            _fields(production[key], fields, "bootstrap work counters")
            for count in production[key].values():
                _integer(count)
            if production[key]["terminal_simulation_backups"] != 0:
                raise EvidenceBundleIntegrityError("bootstrap proof work is not MCTS simulation evidence")


def validate_evidence_inputs(value):
    """Pure interchange validation; does not authenticate external file bytes."""
    try:
        value = _copy(value)
        _fields(value, INPUT_FIELDS, "evidence inputs")
        if value["format"] != INPUT_FORMAT or type(value["version"]) is not int or value["version"] != VERSION:
            raise EvidenceBundleIntegrityError("unsupported evidence inputs")
        _check_source(value["source"])
        _same(value["catalog"], _catalog(), "frozen sixteen-rule catalog")
        _validate_inventory(value["candidate_inventory"], value["catalog"])
        _validate_bootstrap(value["bootstrap"])
        _validate_pins(value["pins"])
        selected, excluded = value["selected_records"], value["excluded_records"]
        if type(selected) is not list or [row.get("path") for row in selected] != list(SELECTED_PATHS):
            raise EvidenceBundleIntegrityError("analysis must select the final thirteen scripted exports")
        if type(excluded) is not list or [row.get("path") for row in excluded] != list(EXCLUDED_PATHS):
            raise EvidenceBundleIntegrityError("all twelve superseded exports must remain excluded")
        for item in selected:
            _fields(item, {"path", "sha256", "record", "provenance", "replay_receipt"}, "selected script")
            _hash(item["sha256"])
            _same(item["provenance"], {"kind": "engineering-ui-automation", "source_id": item["path"]}, "script provenance")
            record = validate_lab_record_shape(item["record"])
            _same(record, item["record"], "canonical script shape")
            _receipt(item["replay_receipt"], record)
            _validate_metadata(_record_metadata(item), value["pins"])
        for item in excluded:
            _validate_metadata(item, value["pins"], excluded=True)
        return value
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
        if isinstance(error, EvidenceBundleIntegrityError):
            raise
        raise EvidenceBundleIntegrityError("malformed evidence input structure") from error


@dataclass(frozen=True)
class EvidenceInputs:
    _json: str

    def __post_init__(self):
        _same(validate_evidence_inputs(_parse(self._json)), _parse(self._json), "canonical evidence inputs")

    @classmethod
    def from_dict(cls, value):
        return cls(canonical_json(validate_evidence_inputs(value)))

    def to_dict(self):
        return _parse(self._json)

    @property
    def canonical_hash(self):
        return canonical_hash(self.to_dict())


def load_evidence_inputs(*, external_root, source_commit):
    """Authenticate the frozen bytes. No game/proof/replay function is called."""
    try:
        source = _source(source_commit)
        indices = {key: _read_pinned(REPOSITORY, path, digest) for key, (path, digest) in INDEX_PINS.items()}
        corpus, browser, bootstrap = (indices[k] for k in ("corpus", "browser", "bootstrap"))
        if corpus["raw_manifest_hash"] != CORPUS_MANIFEST_HASH or corpus["index_hash"] != CORPUS_INDEX_HASH:
            raise EvidenceBundleIntegrityError("frozen corpus semantic identity changed")
        _same(canonical_hash({k: v for k, v in corpus.items() if k != "index_hash"}), CORPUS_INDEX_HASH, "compact index hash")
        # These historical source labels are authenticated by fixed index bytes.
        # They may locate only repository-contained files, never executable code.
        for label, digest in corpus["sources"]["hashes"].items():
            if _digest(_read(REPOSITORY, label)) != digest:
                raise EvidenceBundleIntegrityError("frozen corpus source drift")
        for ref in browser["sources"]:
            if _digest(_read(REPOSITORY, ref["path"])) != ref["sha256"]:
                raise EvidenceBundleIntegrityError("frozen browser source drift")
        raw_ref = browser["raw_manifest"]
        if raw_ref["path"] != BROWSER_RAW:
            raise EvidenceBundleIntegrityError("unexpected browser inventory identity")
        raw = _read_pinned(external_root, BROWSER_RAW, raw_ref["sha256"])
        refs = _references(raw["artifacts"])
        _same(raw["sources"], browser["sources"], "browser historical source bundle")
        audit = _ref_read(external_root, refs, BROWSER_AUDIT)
        majority_receipt = _ref_read(external_root, refs, MAJORITY_RECEIPT)
        selected, excluded = _load_records(external_root, refs, audit, majority_receipt)
        bootrefs = _references(bootstrap["artifacts"])
        loaded = {path: _ref_read(external_root, bootrefs, path) for path in BOOTSTRAP_FILES}
        summary, run, checked = (loaded[path] for path in BOOTSTRAP_FILES)
        if canonical_hash(summary["semantic"]) != summary["semantic_hash"]:
            raise EvidenceBundleIntegrityError("bootstrap summary semantic hash mismatch")
        for actual, expected in ((summary["inputs"]["run_sha256"], bootrefs["batch-5g-run.json"]["sha256"]),
                                 (summary["semantic"]["canonical_results_hash"], run["run"]["canonical_results_hash"]),
                                 (summary["semantic"]["manifest_hash"], run["run"]["manifest_hash"])):
            _same(actual, expected, "bootstrap cross-artifact identity")
        if run["source_commit_verified"] is not True or run["status"] != "timeout":
            raise EvidenceBundleIntegrityError("bootstrap source/stop evidence changed")
        if checked.get("independently_certified", checked.get("artifact_audit", {}).get("independently_certified")) not in (None, 0):
            raise EvidenceBundleIntegrityError("bootstrap audit cannot imply certification")
        accounting_keys = ("status", "reason", "task_count", "attempted", "completed", "interrupted", "unstarted", "independently_certified", "admitted_agents", "all_cleanup_confirmed")
        accounting = {key: bootstrap["bootstrap"][key] for key in accounting_keys}
        pins = {key: {"path": path, "sha256": digest} for key, (path, digest) in INDEX_PINS.items()}
        pins["browser_raw"] = {"path": BROWSER_RAW, "sha256": raw_ref["sha256"]}
        for path in (BROWSER_AUDIT, MAJORITY_RECEIPT) + SELECTED_PATHS + EXCLUDED_PATHS:
            pins[path] = {"path": path, "sha256": refs[path]["sha256"]}
        for path in BOOTSTRAP_FILES:
            pins[path] = {"path": path, "sha256": bootrefs[path]["sha256"]}
        result = EvidenceInputs.from_dict({"format": INPUT_FORMAT, "version": VERSION, "source": source, "pins": pins,
            "catalog": _catalog(), "candidate_inventory": corpus["rulesets"],
            "bootstrap": {"semantic": summary["semantic"], "accounting": accounting},
            "selected_records": selected, "excluded_records": excluded})
        _same(_source(source_commit), source, "report source after loading")
        return result
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        if isinstance(error, EvidenceBundleIntegrityError):
            raise
        raise EvidenceBundleIntegrityError("invalid frozen evidence artifact") from error


def _script_coverage(selected, excluded):
    result = []
    for rules in PRODUCTION_RULESETS:
        chosen = [row for row in selected if row["ruleset"] == rules]
        omitted = [row for row in excluded if row["ruleset"] == rules]
        result.append({"ruleset": rules, "source_kind": "engineering-ui-automation",
                       "selected_exports": len(chosen), "excluded_exports": len(omitted),
                       "audited_exports": len(chosen) + len(omitted),
                       "recorded_actions": sum(row["action_count"] for row in chosen),
                       "accepted_traces": sum(row["accepted"] for row in chosen),
                       "observation_status": "observed" if chosen else "unmeasured",
                       "comparative_games": 0, "human_observations": 0})
    return result


def _cards(source, pins):
    cards = []
    for spec in _catalog():
        card = empty_card(spec["id"], spec["revision"], source_commit=source["commit"], rules_hash=spec["rules_hash"])
        # The whole product-suite receipt is scoped, not a per-ruleset count.
        card["dimensions"]["correctness"] = entry("observed", value={"product_verification": "passed-scoped-engineering-checks"},
            provenance=[f"sha256:{pins['bootstrap']['sha256']}"], sample_size=0,
            uncertainty="Tests cover specified cases; no all-position correctness or accepted-terminal proof is inferred.",
            scope="Shared product regression evidence, not a per-ruleset sampled game count.", source_kind="computer")
        if spec["rule_concepts"] is not None:
            card["dimensions"]["rule_economy"] = entry("verified", value={"concept_inventory": spec["rule_concepts"]},
                provenance=[f"sha256:{source['hashes']['engine/lab_spec.py']}"], sample_size=0,
                uncertainty="A specification inventory, not a numerical complexity, elegance or beauty rating.",
                scope="Named concepts in the frozen laboratory specification.", source_kind="design")
            card["dimensions"]["aesthetic_potential"] = entry("provisional", value={"design_hypothesis": spec["hypothesis"]},
                provenance=[f"sha256:{source['hashes']['engine/lab_spec.py']}"], sample_size=0,
                uncertainty="Unmeasured design hypothesis; no player beauty, readability or replay observations.",
                scope="Specification hypothesis, not demonstrated strategic character.", source_kind="design")
        cards.append(validate_card(card))
    return cards


def _bundle_content(inputs):
    selected = [_record_metadata(item) for item in inputs["selected_records"]]
    excluded = inputs["excluded_records"]
    return {"format": BUNDLE_FORMAT, "version": VERSION, "source": inputs["source"], "pins": inputs["pins"],
            "cards": _cards(inputs["source"], inputs["pins"]), "candidate_inventory": inputs["candidate_inventory"],
            "bootstrap": inputs["bootstrap"], "script_coverage": _script_coverage(selected, excluded),
            "record_selection": {"audited": 25, "selected": selected, "excluded": excluded},
            "comparative_shortlist": [], "claim_limit": CLAIM_LIMIT}


def validate_evidence_bundle(value):
    """Strict reporting scope; schema validity alone never upgrades evidence."""
    try:
        value = _copy(value)
        _fields(value, BUNDLE_FIELDS, "evidence bundle")
        if value["format"] != BUNDLE_FORMAT or type(value["version"]) is not int or value["version"] != VERSION:
            raise EvidenceBundleIntegrityError("unsupported evidence bundle")
        _check_source(value["source"])
        _validate_pins(value["pins"])
        _validate_inventory(value["candidate_inventory"], _catalog())
        _validate_bootstrap(value["bootstrap"])
        _same(value["cards"], _cards(value["source"], value["pins"]), "frozen cards and missingness")
        for card in value["cards"]:
            validate_card(card)
        selection = value["record_selection"]
        _fields(selection, {"audited", "selected", "excluded"}, "record selection")
        if selection["audited"] != 25 or type(selection["audited"]) is not int:
            raise EvidenceBundleIntegrityError("exactly 25 audited exports are accounted")
        if [row["path"] for row in selection["selected"]] != list(SELECTED_PATHS) or [row["path"] for row in selection["excluded"]] != list(EXCLUDED_PATHS):
            raise EvidenceBundleIntegrityError("selected/excluded script roles changed")
        for item in selection["selected"] + selection["excluded"]:
            _validate_metadata(item, value["pins"], excluded=item["path"] in EXCLUDED_PATHS)
        _same(value["script_coverage"], _script_coverage(selection["selected"], selection["excluded"]), "script coverage")
        if value["comparative_shortlist"] != [] or value["claim_limit"] != CLAIM_LIMIT:
            raise EvidenceBundleIntegrityError("no qualified shortlist or expanded claim is authorized")
        _hash(value["bundle_hash"])
        _same(value["bundle_hash"], canonical_hash({k: v for k, v in value.items() if k != "bundle_hash"}), "bundle hash")
        return value
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
        if isinstance(error, EvidenceBundleIntegrityError):
            raise
        raise EvidenceBundleIntegrityError("malformed evidence bundle") from error


@dataclass(frozen=True)
class EvidenceBundle:
    _json: str

    def __post_init__(self):
        validate_evidence_bundle(_parse(self._json))

    @classmethod
    def from_dict(cls, value):
        return cls(canonical_json(validate_evidence_bundle(value)))

    def to_dict(self):
        return _parse(self._json)

    @property
    def canonical_hash(self):
        return self.to_dict()["bundle_hash"]


def build_evidence_bundle(inputs):
    if type(inputs) is not EvidenceInputs:
        raise EvidenceBundleIntegrityError("validated evidence inputs are required")
    content = _bundle_content(validate_evidence_inputs(inputs.to_dict()))
    return EvidenceBundle.from_dict(content | {"bundle_hash": canonical_hash(content)})


def render_evidence_markdown(bundle):
    wire = validate_evidence_bundle(bundle.to_dict() if isinstance(bundle, EvidenceBundle) else bundle)
    lines = ["# Rules Laboratory evidence cards", "", CLAIM_LIMIT, "",
             "Comparative shortlist: **empty**. All 16 definitions have zero admitted agents, zero independently certified "
             "development/holdout decisions, and zero comparative games. MCTS itself remains unmeasured.", "",
             "The bootstrap stopped operationally: 6 completed partial legacy tasks, 8 interrupted tasks and 18 unstarted slots. "
             "Sibling timeout labels do not mean every task exhausted its own guard. This is not a rules defect.", "",
             "Script coverage: 25 audited exports; 13 final engineering scripts selected, 12 Matrix2 exports excluded as superseded. "
             "These are not strategic samples or human observations.", "",
             "| Definition | Selected scripts | Candidate development / holdout | MCTS |", "| --- | ---: | ---: | --- |"]
    for card, coverage, inventory in zip(wire["cards"], wire["script_coverage"], wire["candidate_inventory"]):
        counts = {split: sum(size["structural_counts"][split] for size in inventory["sizes"].values()) for split in ("development", "holdout")}
        lines.append(f"| {card['ruleset']} {card['revision']} | {coverage['selected_exports']} | {counts['development']} / {counts['holdout']} candidates, not certificates | unmeasured |")
    for card in wire["cards"]:
        lines += ["", f"## {card['ruleset']} · {card['revision']}", ""]
        for name, fact in card["dimensions"].items():
            detail = canonical_json(fact["value"]) if fact["value"] is not None else "No observation or rating."
            lines.append(f"- {name.replace('_', ' ')} — {fact['status']}: {detail} {fact['uncertainty']}")
        lines += ["", "Human readability, beauty, replay desire and memorable understanding: unmeasured."]
    lines += ["", f"Evidence bundle SHA-256: `{wire['bundle_hash']}`", ""]
    return "\n".join(lines)
