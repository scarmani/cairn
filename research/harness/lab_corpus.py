"""Proof-free, deterministic candidate-origin compiler for the frozen lab round.

All input definitions are explicit trusted data. Only genuine production Illegal
actions become invalid-origin rows; source changes and oracle contradictions stop
compilation. Structural eligibility and spatial duplication imply no game value.
"""

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
for directory in (REPOSITORY, REPOSITORY / "engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from actions import RulesAction  # noqa: E402
from varde import Illegal  # noqa: E402
from research.harness.lab_origin import (  # noqa: E402
    LEGACY_LIMIT, OriginIntegrityError, OriginRecord, SOURCE_PATHS as ORIGIN_PATHS,
    create_origin, origin_configuration, runtime_sources, verify_origin,
)
from research.harness.lab_research_adapter import (  # noqa: E402
    LEGACY_CANDIDATES, PRODUCTION_RULESETS, production_provider,
)
from research.harness.lab_symmetry import symmetry_key  # noqa: E402
from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402

FORMAT = "varde-lab-candidate-corpus"
VERSION = 1
REVISION = "0.1"
SIZES = (3, 4)
MAX_PER_RULE_SIZE = 16
MAX_CANDIDATES = len(PRODUCTION_RULESETS) * len(SIZES) * MAX_PER_RULE_SIZE
SPLIT_SALT = "varde-rules-lab-corpus-split-0.1"
DISPOSITIONS = ("accepted-terminal", "single-action", "duplicate", "invalid-origin", "candidate")
CLAIM_LIMIT = (
    "Authored candidate origins and conservative spatial/phase screening only. "
    "No action values, independent certification, MCTS admission or game-quality evidence."
)
ORACLE_LIMIT = "Dual-mechanical origin replay is available; it is not accepted-terminal certification."
LOCAL_PATHS = ("research/harness/lab_corpus.py", "research/harness/lab_symmetry.py")
FIXED_PATHS = tuple(sorted(set(LOCAL_PATHS + ORIGIN_PATHS)))
DEFINITION_FIELDS = {"id", "configuration", "actions", "template_id", "family"}
ROW_FIELDS = {"id", "definition", "definition_hash", "disposition", "reason", "representative_id",
              "split", "origin", "origin_hash", "origin_receipt", "root_fingerprint", "spatial_key",
              "legal_action_count", "equivalence", "certified"}
MANIFEST_FIELDS = {"format", "version", "source_parent", "sources", "split_salt", "candidate_definitions_hash",
                   "candidates", "rulesets", "admission_record", "claim_limit", "manifest_hash"}


class CorpusIntegrityError(ValueError):
    """Malformed candidate input or an unverifiable compilation artifact."""


def _copy(value):
    return json.loads(canonical_json(value))


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise CorpusIntegrityError(f"invalid {label} fields")


def _same(left, right, label):
    if canonical_json(left) != canonical_json(right):
        raise CorpusIntegrityError(f"{label} mismatch")


def _text(value):
    if type(value) is not str or not value or value.strip() != value:
        raise CorpusIntegrityError("expected a nonempty exact string")


def _digest(value, width=64):
    if type(value) is not str or len(value) != width or any(c not in "0123456789abcdef" for c in value):
        raise CorpusIntegrityError("invalid hexadecimal source/hash identity")


def _file_hash(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except (TypeError, ValueError, OSError) as error:
        raise CorpusIntegrityError("authoritative corpus source unavailable") from error


_LOADED_LOCAL = {label: _file_hash(REPOSITORY / label) for label in LOCAL_PATHS}


def _trusted_paths(trusted_sources):
    if trusted_sources is None:
        return {}
    if type(trusted_sources) is not dict:
        raise CorpusIntegrityError("trusted sources must be a caller-owned label/path mapping")
    result = {}
    for label, path in trusted_sources.items():
        _text(label)
        if label in FIXED_PATHS:
            raise CorpusIntegrityError("trusted source labels cannot override fixed dependencies")
        try:
            result[label] = Path(path).expanduser().resolve()
        except (TypeError, ValueError, OSError) as error:
            raise CorpusIntegrityError("invalid trusted local source path") from error
    return result


def _sources(trusted_paths):
    local = {label: _file_hash(REPOSITORY / label) for label in LOCAL_PATHS}
    _same(local, _LOADED_LOCAL, "loaded corpus/symmetry source bytes")
    origin = runtime_sources()
    hashes = dict(origin["hashes"]) | local
    hashes.update({label: _file_hash(path) for label, path in trusted_paths.items()})
    value = {"revision": REVISION, "hashes": hashes, "origin_bundle_hash": origin["bundle_hash"],
             "trusted_labels": sorted(trusted_paths)}
    return value | {"source_hash": canonical_hash(value)}


def _definition(value):
    _fields(value, DEFINITION_FIELDS, "candidate definition")
    canonical_json(value)
    for key in ("id", "template_id", "family"):
        _text(value[key])
    config = value["configuration"]
    _fields(config, {"rules_id", "rules_revision", "n", "topology_seed", "initial_seats"}, "origin configuration")
    expected = origin_configuration(config["rules_id"], config["n"], seed=config["topology_seed"], seats=config["initial_seats"])
    _same(config, expected, "frozen rule configuration")
    if config["n"] not in SIZES:
        raise CorpusIntegrityError("this frozen candidate round uses n3 and n4 only")
    _same(config["initial_seats"], {"B": "S1", "W": "S2"}, "neutral initial seat labels")
    if type(value["actions"]) is not list:
        raise CorpusIntegrityError("complete action wires must be an ordered list")
    for action in value["actions"]:
        try:
            expected = RulesAction.from_dict(action).to_dict()
        except (ValueError, TypeError) as error:
            raise CorpusIntegrityError("malformed authored action") from error
        _same(action, expected, "complete semantic action")
    return _copy(value)


def _definitions(values):
    if type(values) is not list:
        raise CorpusIntegrityError("explicit candidate definitions must be a list")
    if len(values) > MAX_CANDIDATES:
        raise CorpusIntegrityError("candidate list exceeds the frozen 512-origin ceiling")
    definitions, seen, cells = [], set(), Counter()
    for value in values:
        definition = _definition(value)
        if definition["id"] in seen:
            raise CorpusIntegrityError("duplicate candidate ID")
        seen.add(definition["id"])
        config = definition["configuration"]
        cell = config["rules_id"], config["n"]
        cells[cell] += 1
        if cells[cell] > MAX_PER_RULE_SIZE:
            raise CorpusIntegrityError("candidate list exceeds sixteen templates per rule/size")
        definitions.append(definition)
    return sorted(definitions, key=lambda row: row["id"])


def _compile_one(definition):
    row = {"id": definition["id"], "definition": definition, "definition_hash": canonical_hash(definition),
           "disposition": "invalid-origin", "reason": None, "representative_id": None, "split": None,
           "origin": None, "origin_hash": None, "origin_receipt": None, "root_fingerprint": None,
           "spatial_key": None, "legal_action_count": None, "equivalence": "unknown", "certified": False}
    try:
        origin = create_origin(definition["configuration"], definition["actions"])
    except OriginIntegrityError as error:
        if not isinstance(error.__cause__, Illegal):
            raise
        row["reason"] = f"Authored production action rejected: {error}; {error.__cause__}"
        return row
    verified = verify_origin(origin)
    root = verified.production_root
    provider = production_provider(definition["configuration"]["rules_id"])
    domain = tuple(provider.legal_actions(root))
    if not root.accepted and not domain:
        raise CorpusIntegrityError("nonaccepted candidate has no legal rules actions")
    row.update(origin=origin.to_dict(), origin_hash=origin.record_hash, origin_receipt=verified.receipt,
               root_fingerprint=provider.fingerprint(root), spatial_key=symmetry_key(root),
               legal_action_count=len(domain), representative_id=definition["id"])
    if root.accepted:
        if domain:
            raise CorpusIntegrityError("accepted candidate still has legal actions")
        row.update(disposition="accepted-terminal", reason="Accepted terminal roots contain no decision.")
    elif len(domain) == 1:
        row.update(disposition="single-action", reason="Only one legal action; no choice is implied.")
    else:
        row.update(disposition="candidate", reason=None)
    return row


def _assign_splits(rows):
    # Structural exclusions precede eligible-class dedup. Histories that happen
    # to change legality are intentionally not promoted by the diagram filter.
    for rules in PRODUCTION_RULESETS:
        for n in SIZES:
            eligible = [row for row in rows if row["disposition"] == "candidate"
                        and row["definition"]["configuration"]["rules_id"] == rules
                        and row["definition"]["configuration"]["n"] == n]
            representatives = {}
            for row in sorted(eligible, key=lambda item: item["id"]):
                spatial = row["spatial_key"]
                if spatial in representatives:
                    row.update(disposition="duplicate", representative_id=representatives[spatial]["id"],
                               reason="Conservative diagram/phase duplicate; forbidden history is intentionally ignored.")
                else:
                    representatives[spatial] = row
            ordered = sorted(representatives.values(), key=lambda row: (
                canonical_hash({"salt": SPLIT_SALT, "rules": rules, "n": n, "spatial_key": row["spatial_key"]}),
                row["spatial_key"],
            ))
            for index, row in enumerate(ordered):
                row["split"] = "development" if index % 2 == 0 else "holdout"


def _rulesets(rows):
    result = []
    for rules in PRODUCTION_RULESETS:
        sizes = {}
        for n in SIZES:
            selected = [row for row in rows if row["definition"]["configuration"]["rules_id"] == rules
                        and row["definition"]["configuration"]["n"] == n]
            counts = Counter(row["disposition"] for row in selected)
            sizes[str(n)] = {"proposed": len(selected),
                             "dispositions": {kind: counts[kind] for kind in DISPOSITIONS},
                             "structural_counts": {split: sum(row["split"] == split for row in selected)
                                                   for split in ("development", "holdout")}}
        independent = rules not in LEGACY_CANDIDATES
        result.append({"rules_id": rules, "rules_revision": origin_configuration(rules)["rules_revision"],
                       "sizes": sizes, "dual_mechanical_origin_available": independent,
                       "independent_mechanics": independent,
                       "independence_status": "origin-only" if independent else "unqualified-shared-mechanics",
                       "mechanics_limit": ORACLE_LIMIT if independent else LEGACY_LIMIT,
                       "certified_counts": {"development": 0, "holdout": 0},
                       "required_certified_per_split": 8, "admission_status": "incomplete"})
    return result


def _validate(value):
    _fields(value, MANIFEST_FIELDS, "candidate manifest")
    canonical_json(value)
    if (value["format"] != FORMAT or type(value["version"]) is not int or value["version"] != VERSION
            or value["split_salt"] != SPLIT_SALT or value["claim_limit"] != CLAIM_LIMIT
            or value["admission_record"] is not False):
        raise CorpusIntegrityError("unsupported candidate manifest or claim")
    _digest(value["source_parent"], 40)
    sources = value["sources"]
    _fields(sources, {"revision", "hashes", "origin_bundle_hash", "trusted_labels", "source_hash"}, "source bundle")
    if sources["revision"] != REVISION or type(sources["trusted_labels"]) is not list:
        raise CorpusIntegrityError("invalid corpus source revision/labels")
    for label in sources["trusted_labels"]:
        _text(label)
    if sorted(set(sources["trusted_labels"])) != sources["trusted_labels"] or set(sources["trusted_labels"]) & set(FIXED_PATHS):
        raise CorpusIntegrityError("source labels duplicate or override fixed dependencies")
    _fields(sources["hashes"], set(FIXED_PATHS) | set(sources["trusted_labels"]), "closed source hashes")
    for digest in sources["hashes"].values():
        _digest(digest)
    _digest(sources["origin_bundle_hash"])
    if sources["source_hash"] != canonical_hash({k: v for k, v in sources.items() if k != "source_hash"}):
        raise CorpusIntegrityError("source bundle hash mismatch")
    if type(value["candidates"]) is not list:
        raise CorpusIntegrityError("candidate rows must be an ordered list")
    definitions = []
    for row in value["candidates"]:
        _fields(row, ROW_FIELDS, "candidate row")
        definition = _definition(row["definition"])
        definitions.append(definition)
        if row["id"] != definition["id"] or row["definition_hash"] != canonical_hash(definition):
            raise CorpusIntegrityError("candidate definition identity mismatch")
        if type(row["disposition"]) is not str or row["disposition"] not in DISPOSITIONS:
            raise CorpusIntegrityError("invalid structural disposition")
        if row["equivalence"] != "unknown" or row["certified"] is not False:
            raise CorpusIntegrityError("proof-free candidates cannot claim equivalent values or certification")
        if row["reason"] is not None:
            _text(row["reason"])
        if row["disposition"] == "invalid-origin":
            if any(row[k] is not None for k in ("origin", "origin_hash", "origin_receipt", "root_fingerprint", "spatial_key", "legal_action_count", "representative_id", "split")) or row["reason"] is None:
                raise CorpusIntegrityError("invalid origins cannot claim verified state identities")
        else:
            record = OriginRecord.from_dict(row["origin"])
            if row["origin_hash"] != record.record_hash or row["root_fingerprint"] != record.to_dict()["final"]["stamp"]["fingerprint"]:
                raise CorpusIntegrityError("origin/root hash mismatch")
            _digest(row["spatial_key"])
            _text(row["representative_id"])
            if type(row["origin_receipt"]) is not dict or type(row["legal_action_count"]) is not int or row["legal_action_count"] < 0:
                raise CorpusIntegrityError("invalid mechanical receipt or domain count")
            if row["disposition"] == "accepted-terminal" and row["legal_action_count"] != 0:
                raise CorpusIntegrityError("terminal root has a domain")
            if row["disposition"] == "single-action" and row["legal_action_count"] != 1:
                raise CorpusIntegrityError("single-action root has another domain width")
            if row["disposition"] in ("candidate", "duplicate") and row["legal_action_count"] < 2:
                raise CorpusIntegrityError("eligible root lacks an actual choice")
            if row["disposition"] == "candidate":
                if row["split"] not in ("development", "holdout") or row["representative_id"] != row["id"] or row["reason"] is not None:
                    raise CorpusIntegrityError("invalid candidate split/representative")
            elif row["split"] is not None or row["reason"] is None:
                raise CorpusIntegrityError("structural exclusions must be explained and unsplit")
    _same(definitions, _definitions(definitions), "canonical candidate order")
    if value["candidate_definitions_hash"] != canonical_hash(definitions):
        raise CorpusIntegrityError("candidate definition-list hash mismatch")
    _same(value["rulesets"], _rulesets(value["candidates"]), "all-ruleset status accounting")
    _digest(value["manifest_hash"])
    if value["manifest_hash"] != canonical_hash({k: v for k, v in value.items() if k != "manifest_hash"}):
        raise CorpusIntegrityError("candidate manifest hash mismatch")


@dataclass(frozen=True)
class CorpusManifest:
    """Canonical detached storage; use from_dict for runtime replay validation."""
    _json: str

    def __post_init__(self):
        if type(self._json) is not str:
            raise CorpusIntegrityError("manifest storage must be canonical JSON")
        def unique(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise CorpusIntegrityError("duplicate manifest JSON key")
                result[key] = item
            return result
        try:
            value = json.loads(self._json, object_pairs_hook=unique)
        except (TypeError, json.JSONDecodeError, RecursionError) as error:
            raise CorpusIntegrityError("malformed candidate JSON") from error
        _validate(value)
        if self._json != canonical_json(value):
            raise CorpusIntegrityError("candidate storage is not canonical")

    @classmethod
    def from_dict(cls, value, *, trusted_sources=None):
        """Regenerate mechanical origins/splits; never trust re-sealed counters."""
        _validate(value)
        trusted = _trusted_paths(trusted_sources)
        _same(value["sources"], _sources(trusted), "authoritative corpus sources")
        result = compile_corpus([row["definition"] for row in value["candidates"]],
                                source_parent=value["source_parent"], trusted_sources=trusted)
        _same(value, result.to_dict(), "independently regenerated candidate manifest")
        return result

    def to_dict(self):
        return json.loads(self._json)

    @property
    def manifest_hash(self):
        return self.to_dict()["manifest_hash"]

    def compact_index(self):
        value = self.to_dict()
        rows = []
        for row in value["candidates"]:
            definition = row["definition"]
            rows.append({key: row[key] for key in ("id", "definition_hash", "disposition", "reason", "representative_id",
                                                   "split", "origin_hash", "root_fingerprint", "spatial_key", "legal_action_count",
                                                   "equivalence", "certified")} |
                        {"rules_id": definition["configuration"]["rules_id"],
                         "rules_revision": definition["configuration"]["rules_revision"],
                         "n": definition["configuration"]["n"], "template_id": definition["template_id"], "family": definition["family"]})
        index = {"format": "varde-lab-candidate-index", "version": VERSION,
                 "source_parent": value["source_parent"], "sources": value["sources"],
                 "split_salt": value["split_salt"], "candidate_definitions_hash": value["candidate_definitions_hash"],
                 "raw_manifest_hash": value["manifest_hash"], "candidates": rows, "rulesets": value["rulesets"],
                 "admission_record": False, "claim_limit": CLAIM_LIMIT}
        return _copy(index | {"index_hash": canonical_hash(index)})


def compile_corpus(candidates, *, source_parent, trusted_sources=None):
    """Compile explicit authored n3/n4 origins without proof, search or repair."""
    _digest(source_parent, 40)
    # Validate the entire proposed list before executing its first origin action.
    definitions = _definitions(candidates)
    trusted = _trusted_paths(trusted_sources)
    sources = _sources(trusted)
    rows = [_compile_one(definition) for definition in definitions]
    _assign_splits(rows)
    _same(sources, _sources(trusted), "runtime sources after compilation")
    value = {"format": FORMAT, "version": VERSION, "source_parent": source_parent,
             "sources": sources, "split_salt": SPLIT_SALT, "candidate_definitions_hash": canonical_hash(definitions),
             "candidates": rows, "rulesets": _rulesets(rows), "admission_record": False, "claim_limit": CLAIM_LIMIT}
    return CorpusManifest(canonical_json(value | {"manifest_hash": canonical_hash(value)}))
