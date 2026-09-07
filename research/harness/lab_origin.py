"""Full-action factory-origin replay, not a proof or admission certificate.

Records contain no executable paths. The ten laboratory definitions receive a
second replay through the independent oracle; the six legacy definitions retain
an explicit shared-mechanics limitation. Bound metadata attests one exact root,
never an arbitrary descendant or the optimality of any decision.
"""

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
for directory in (REPOSITORY, REPOSITORY / "engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from actions import RulesAction, RulesState  # noqa: E402
from game_factory import new_game  # noqa: E402
from lab_spec import EXPERIMENT_REGISTRY  # noqa: E402
from varde import get_ruleset_spec  # noqa: E402
from research.harness import lab_oracle as oracle  # noqa: E402
from research.harness.lab_research_adapter import (  # noqa: E402
    LEGACY_CANDIDATES, PRODUCTION_RULESETS, independent_provider, production_provider,
)
from research.harness.lab_terminal_cert import (  # noqa: E402
    action_id, canonical_hash, canonical_json,
)

FORMAT = "varde-lab-full-action-origin"
REVISION = "0.1"
VERSION = 1
CLAIM_LIMIT = (
    "Complete explicit factory-action replay for the declared source bytes only; "
    "not an optimal-action certificate, strategic result, or MCTS admission."
)
LEGACY_LIMIT = (
    "Legacy rules use shared production mechanics. No independent legacy "
    "resolution engine is supplied, and research independence remains unqualified."
)
SOURCE_PATHS = (
    "research/harness/lab_origin.py", "research/harness/lab_research_adapter.py",
    "research/harness/lab_terminal_cert.py", "research/harness/lab_oracle.py",
    "research/harness/lab_oracle_geometry.py", "engine/actions.py",
    "engine/game_factory.py", "engine/varde.py", "engine/lab_game.py",
    "engine/lab_graph.py", "engine/lab_spec.py", "docs/rules-lab-specs.md",
)
RECORD_FIELDS = {"format", "version", "configuration", "normalization", "sources",
                 "providers", "initial", "actions", "final", "claim_limit", "record_hash"}
STAMP_FIELDS = {"fingerprint", "independent_fingerprint", "snapshot_hash", "analysis_hash",
                "history_hash", "actor", "seats", "accepted"}


class OriginIntegrityError(ValueError):
    """An origin, trace, dependency or exact-root binding cannot be verified."""


def _copy(value):
    return json.loads(canonical_json(value))


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise OriginIntegrityError(f"invalid {label} fields")


def _same(left, right, label):
    if canonical_json(left) != canonical_json(right):
        raise OriginIntegrityError(f"{label} mismatch")


def _digest(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise OriginIntegrityError("invalid SHA256 identity")


def _seat_map(value):
    _fields(value, {"B", "W"}, "initial seats")
    if (any(type(v) is not str or not v or v.strip() != v for v in value.values())
            or len(set(value.values())) != 2):
        raise OriginIntegrityError("seat identities must be distinct nonempty strings")


def _actual_sources():
    # Never use a caller-supplied source path. Labels are a closed implementation
    # constant; the record can only assert the hashes that this code reads.
    try:
        hashes = {label: hashlib.sha256((REPOSITORY / label).read_bytes()).hexdigest()
                  for label in SOURCE_PATHS}
    except OSError as error:
        raise OriginIntegrityError("authoritative origin dependency unavailable") from error
    return {"revision": REVISION, "hashes": hashes, "bundle_hash": canonical_hash(hashes)}


_LOADED_SOURCES = canonical_json(_actual_sources())


def runtime_sources():
    """Actual closed-set dependency bytes, also checked against this import."""
    value = _actual_sources()
    if canonical_json(value) != _LOADED_SOURCES:
        raise OriginIntegrityError("origin dependencies changed since module import")
    return value


def _configuration(config):
    _fields(config, {"rules_id", "rules_revision", "n", "topology_seed", "initial_seats"}, "origin configuration")
    rules = config["rules_id"]
    if type(rules) is not str or rules not in PRODUCTION_RULESETS:
        raise OriginIntegrityError("unsupported origin ruleset")
    spec = EXPERIMENT_REGISTRY[rules] if rules in EXPERIMENT_REGISTRY else get_ruleset_spec(rules)
    if type(config["rules_revision"]) is not str or config["rules_revision"] != spec.revision:
        raise OriginIntegrityError("unsupported origin rules revision")
    if type(config["n"]) is not int or config["n"] not in (3, 4, 5, 6):
        raise OriginIntegrityError("origin size must be an integer from three through six")
    if type(config["topology_seed"]) is not int:
        raise OriginIntegrityError("origin topology seed must be an exact integer")
    _seat_map(config["initial_seats"])
    return _copy(config)


def origin_configuration(rules_id, n=3, *, seed=0, seats=None):
    if type(rules_id) is not str or rules_id not in PRODUCTION_RULESETS:
        raise OriginIntegrityError("unsupported origin ruleset")
    spec = EXPERIMENT_REGISTRY[rules_id] if rules_id in EXPERIMENT_REGISTRY else get_ruleset_spec(rules_id)
    return _configuration({"rules_id": rules_id, "rules_revision": spec.revision, "n": n,
                           "topology_seed": seed, "initial_seats": {"B": "S1", "W": "S2"} if seats is None else seats})


def _normalization(config):
    rules, seed = config["rules_id"], config["topology_seed"]
    laboratory = rules in EXPERIMENT_REGISTRY
    prebuilt = laboratory and EXPERIMENT_REGISTRY[rules].construction.startswith("prebuilt-")
    return {"requested_seed": seed, "effective_seed": seed if prebuilt else 0,
            "seed_semantics": "prebuilt-topology-retains-seed" if prebuilt else "factory-ignores-seed",
            "experimental": laboratory, "research": True,
            "players": {"B": "Player 1", "W": "Player 2"}}


def _new_production(config):
    norm = _normalization(config)
    game = new_game(config["n"], config["rules_id"], experimental=norm["experimental"],
                    research=True, seed=config["topology_seed"])
    game.players = dict(norm["players"])
    return RulesState(game, seats=dict(config["initial_seats"]))


def _new_independent(config):
    if config["rules_id"] in LEGACY_CANDIDATES:
        return None
    return oracle.new_state(config["rules_id"], config["n"], seed=_normalization(config)["effective_seed"],
                            seats=config["initial_seats"], players=("Player 1", "Player 2"))


def _json_key(value):
    if type(value) in (tuple, list):
        return [_json_key(item) for item in value]
    if type(value) is dict:
        return {key: _json_key(item) for key, item in value.items()}
    return value


def _stamp(state, provider, independent_state, independent):
    snapshot = provider.snapshot(state)
    independent_fingerprint = None
    if independent is not None:
        _same(snapshot, independent.snapshot(independent_state), "independent semantic snapshot")
        _same(provider.actor(state), independent.actor(independent_state), "independent actor")
        _same(provider.seats(state), independent.seats(independent_state), "independent seats")
        independent_fingerprint = independent.fingerprint(independent_state)
    return {"fingerprint": provider.fingerprint(state), "independent_fingerprint": independent_fingerprint,
            "snapshot_hash": canonical_hash(snapshot), "analysis_hash": canonical_hash(_json_key(state.analysis_key())),
            "history_hash": canonical_hash(snapshot["history"]), "actor": provider.actor(state),
            "seats": provider.seats(state), "accepted": provider.accepted(state)}


def _point(state, provider, independent_state, independent):
    return {"snapshot": provider.snapshot(state), "stamp": _stamp(state, provider, independent_state, independent)}


def _wire(value):
    canonical_json(value)
    if type(value) is not dict:
        raise OriginIntegrityError("origin actions must be semantic JSON objects")
    try:
        normalized = RulesAction.from_dict(value).to_dict()
    except (ValueError, TypeError) as error:
        raise OriginIntegrityError("malformed origin action") from error
    _same(value, normalized, "semantic action")
    return _copy(value)


def _validate_stamp(value):
    _fields(value, STAMP_FIELDS, "origin stamp")
    for field in ("fingerprint", "snapshot_hash", "analysis_hash", "history_hash"):
        _digest(value[field])
    if value["independent_fingerprint"] is not None:
        _digest(value["independent_fingerprint"])
    _seat_map(value["seats"])
    _fields(value["actor"], {"seat", "color"}, "actor")
    if type(value["accepted"]) is not bool:
        raise OriginIntegrityError("accepted must be an exact Boolean")
    if value["accepted"]:
        _same(value["actor"], {"seat": None, "color": None}, "accepted actor")
    elif (type(value["actor"]["color"]) is not str or value["actor"]["color"] not in ("B", "W")
          or type(value["actor"]["seat"]) is not str
          or value["actor"]["seat"] != value["seats"][value["actor"]["color"]]):
        raise OriginIntegrityError("invalid active actor")


def _validate_record(value):
    _fields(value, RECORD_FIELDS, "origin record")
    canonical_json(value)
    if value["format"] != FORMAT or type(value["version"]) is not int or value["version"] != VERSION or value["claim_limit"] != CLAIM_LIMIT:
        raise OriginIntegrityError("unsupported origin record")
    config = _configuration(value["configuration"])
    _same(value["normalization"], _normalization(config), "factory normalization")
    _fields(value["sources"], {"revision", "hashes", "bundle_hash"}, "source identity")
    _fields(value["sources"]["hashes"], SOURCE_PATHS, "authoritative source set")
    for digest in value["sources"]["hashes"].values():
        _digest(digest)
    if value["sources"]["revision"] != REVISION or value["sources"]["bundle_hash"] != canonical_hash(value["sources"]["hashes"]):
        raise OriginIntegrityError("invalid source bundle hash")
    _fields(value["providers"], {"production", "independent"}, "provider set")
    for name, identity in value["providers"].items():
        if name == "independent" and identity is None and config["rules_id"] in LEGACY_CANDIDATES:
            continue
        _fields(identity, {"provider_id", "rules_id", "rules_revision", "rules_hash", "implementation_hash"}, "provider identity")
        for field in ("provider_id", "rules_id", "rules_revision"):
            if type(identity[field]) is not str or not identity[field]:
                raise OriginIntegrityError("invalid provider identity")
        _digest(identity["rules_hash"])
        _digest(identity["implementation_hash"])
    for key in ("initial", "final"):
        point = value[key]
        _fields(point, {"snapshot", "stamp"}, "origin state")
        if type(point["snapshot"]) is not dict:
            raise OriginIntegrityError("origin snapshot must be an object")
        _validate_stamp(point["stamp"])
        if point["stamp"]["snapshot_hash"] != canonical_hash(point["snapshot"]):
            raise OriginIntegrityError("snapshot hash mismatch")
    if type(value["actions"]) is not list:
        raise OriginIntegrityError("origin actions must be an ordered list")
    before = value["initial"]["stamp"]
    for index, row in enumerate(value["actions"]):
        _fields(row, {"index", "id", "action", "before", "after"}, "origin trace")
        if type(row["index"]) is not int or row["index"] != index or row["id"] != action_id(_wire(row["action"])):
            raise OriginIntegrityError("invalid action index or semantic ID")
        _validate_stamp(row["before"])
        _validate_stamp(row["after"])
        _same(row["before"], before, "trace continuity")
        before = row["after"]
    _same(before, value["final"]["stamp"], "final trace")
    _digest(value["record_hash"])
    if value["record_hash"] != canonical_hash({key: item for key, item in value.items() if key != "record_hash"}):
        raise OriginIntegrityError("origin record hash mismatch")


def _parse(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise OriginIntegrityError("duplicate origin JSON key")
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique)
    except (TypeError, json.JSONDecodeError, RecursionError) as error:
        raise OriginIntegrityError("invalid origin JSON") from error


@dataclass(frozen=True)
class OriginRecord:
    _json: str

    def __post_init__(self):
        if type(self._json) is not str:
            raise OriginIntegrityError("origin storage must be canonical JSON")
        value = _parse(self._json)
        _validate_record(value)
        if self._json != canonical_json(value):
            raise OriginIntegrityError("origin storage is not canonical")

    @classmethod
    def from_dict(cls, value):
        _validate_record(value)
        return cls(canonical_json(value))

    def to_dict(self):
        return json.loads(self._json)

    @property
    def record_hash(self):
        return self.to_dict()["record_hash"]


def create_origin(configuration, actions):
    """Serialize a fresh replay; callers must separately invoke verification."""
    config, sources = _configuration(configuration), runtime_sources()
    if type(actions) is not list:
        raise OriginIntegrityError("a complete ordered action list is required")
    wires = [_wire(action) for action in actions]
    provider = production_provider(config["rules_id"])
    independent = None if config["rules_id"] in LEGACY_CANDIDATES else independent_provider(config["rules_id"])
    state, other = _new_production(config), _new_independent(config)
    initial, rows = _point(state, provider, other, independent), []
    for index, wire in enumerate(wires):
        before = _stamp(state, provider, other, independent)
        try:
            state = provider.transition(state, wire)
            if independent is not None:
                other = independent.transition(other, wire)
        except Exception as error:
            raise OriginIntegrityError(f"illegal origin action at index {index}") from error
        rows.append({"index": index, "id": action_id(wire), "action": wire,
                     "before": before, "after": _stamp(state, provider, other, independent)})
    value = {"format": FORMAT, "version": VERSION, "configuration": config,
             "normalization": _normalization(config), "sources": sources,
             "providers": {"production": provider.identity(), "independent": independent.identity() if independent else None},
             "initial": initial, "actions": rows, "final": _point(state, provider, other, independent),
             "claim_limit": CLAIM_LIMIT}
    _same(runtime_sources(), sources, "runtime sources after serialization")
    return OriginRecord.from_dict(value | {"record_hash": canonical_hash(value)})


@dataclass(frozen=True)
class VerifiedOrigin:
    """Detached convenience result. Binding re-verifies, never trusts this object."""
    record: OriginRecord
    _receipt_json: str
    _production: object
    _independent: object

    @property
    def receipt(self):
        return json.loads(self._receipt_json)

    @property
    def production_root(self):
        return deepcopy(self._production)

    @property
    def independent_root(self):
        return deepcopy(self._independent)


def verify_origin(record):
    """Independently replay every supplied edge from the declared fresh origin.

    No snapshot loader, game journal suffix or reconstructed administrative action
    is accepted as a starting point. Exact JSON comparisons distinguish bool/int.
    """
    record = OriginRecord.from_dict(record.to_dict() if isinstance(record, OriginRecord) else record)
    value = record.to_dict()
    _same(value["sources"], runtime_sources(), "authoritative runtime source identity")
    config = value["configuration"]
    provider = production_provider(config["rules_id"])
    independent = None if config["rules_id"] in LEGACY_CANDIDATES else independent_provider(config["rules_id"])
    _same(value["providers"], {"production": provider.identity(), "independent": independent.identity() if independent else None}, "runtime provider identity")
    state = _new_production(config)
    other = _new_independent(config)
    _same(value["initial"], _point(state, provider, other, independent), "fresh initial state")
    for index, row in enumerate(value["actions"]):
        _same(row["before"], _stamp(state, provider, other, independent), f"before action {index}")
        try:
            state = provider.transition(state, _copy(row["action"]))
            if independent is not None:
                other = independent.transition(other, _copy(row["action"]))
        except Exception as error:
            raise OriginIntegrityError(f"replay rejected action {index}") from error
        _same(row["after"], _stamp(state, provider, other, independent), f"after action {index}")
    _same(value["final"], _point(state, provider, other, independent), "replayed final state")
    _same(value["sources"], runtime_sources(), "runtime sources after verification")
    receipt = {"format": "varde-lab-origin-receipt", "version": VERSION,
               "record_hash": record.record_hash, "source_hash": value["sources"]["bundle_hash"],
               "factory_origin_verified": True, "full_action_replay": True,
               "independent_mechanics": independent is not None,
               "mechanics_limit": None if independent else LEGACY_LIMIT,
               "action_count": len(value["actions"]),
               "initial_fingerprint": value["initial"]["stamp"]["fingerprint"],
               "root_fingerprint": value["final"]["stamp"]["fingerprint"],
               "independent_root_fingerprint": value["final"]["stamp"]["independent_fingerprint"],
               "admission_record": False, "claim_limit": CLAIM_LIMIT}
    receipt["receipt_hash"] = canonical_hash(receipt)
    return VerifiedOrigin(record, canonical_json(receipt), deepcopy(state), deepcopy(other))


def bind_origin_provider(verified, root_state=None, *, independent=False):
    """Bind origin metadata to exactly one reverified root, not its descendants.

    A forged result/receipt is not a capability: record replay and source checks
    repeat here. Source bytes are rechecked on every subsequent provider call.
    """
    if type(verified) is not VerifiedOrigin or type(independent) is not bool:
        raise OriginIntegrityError("a verified origin and exact Boolean provider selection are required")
    fresh = verify_origin(verified.record)
    _same(verified.receipt, fresh.receipt, "verified receipt")
    for supplied, expected, kind in ((verified.production_root, fresh.production_root, "production"),
                                     (verified.independent_root, fresh.independent_root, "independent")):
        if kind == "independent" and expected is None:
            if supplied is not None:
                raise OriginIntegrityError("legacy record has no independent root")
            continue
        base = independent_provider(fresh.record.to_dict()["configuration"]["rules_id"]) if kind == "independent" else production_provider(fresh.record.to_dict()["configuration"]["rules_id"])
        _same(base.snapshot(supplied), base.snapshot(expected), f"stored {kind} root")
        if base.fingerprint(supplied) != base.fingerprint(expected):
            raise OriginIntegrityError(f"stored {kind} root fingerprint mismatch")
    expected = fresh.independent_root if independent else fresh.production_root
    if expected is None:
        raise OriginIntegrityError("legacy mechanics have no independent origin provider")
    config = fresh.record.to_dict()["configuration"]
    base = independent_provider(config["rules_id"]) if independent else production_provider(config["rules_id"])
    candidate = deepcopy(expected if root_state is None else root_state)
    _same(base.snapshot(candidate), base.snapshot(expected), "bound root snapshot")
    fingerprint = base.fingerprint(expected)
    if base.fingerprint(candidate) != fingerprint:
        raise OriginIntegrityError("bound root fingerprint mismatch")
    source_json, snapshot_json = canonical_json(runtime_sources()), canonical_json(base.snapshot(expected))
    receipt_json = canonical_json(fresh.receipt)

    def wrap(callback):
        def guarded(state, *args):
            if canonical_json(runtime_sources()) != source_json:
                raise OriginIntegrityError("bound provider sources are stale")
            return callback(state, *args)
        return guarded

    def metadata(state):
        value = _copy(base.metadata(state))
        if base.fingerprint(state) == fingerprint:
            if canonical_json(base.snapshot(state)) != snapshot_json:
                raise OriginIntegrityError("bound root fingerprint collision")
            value["provenance"].update(origin="verified-full-action-factory-origin",
                                       full_action_replay=True, historical_seat_acceptances_recorded=True,
                                       origin_receipt=json.loads(receipt_json), claim_limit=CLAIM_LIMIT)
        return value

    implementation_hash = canonical_hash({"base_provider": base.identity(),
                                          "origin_source_bundle": fresh.record.to_dict()["sources"]["bundle_hash"],
                                          "wrapper_revision": REVISION})
    return replace(base, provider_id=base.provider_id + "+full-origin-" + REVISION,
                   implementation_hash=implementation_hash,
                   fingerprint=wrap(base.fingerprint), snapshot=wrap(base.snapshot),
                   metadata=wrap(metadata), actor=wrap(base.actor), seats=wrap(base.seats),
                   accepted=wrap(base.accepted), score=wrap(base.score),
                   legal_actions=wrap(base.legal_actions), transition=wrap(base.transition))
