"""Uncached proof providers and bounded, caller-owned research transitions.

This module neither searches nor certifies a position. A snapshot and its game
journal are not evidence of a complete seat-action replay. The certificate
checker uses provider callbacks directly, never ResearchAdapter's cache.
"""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
ENGINE_ROOT = REPOSITORY / "engine"
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from actions import RulesAction, RulesState, apply_action, legal_actions  # noqa: E402
from lab_game import LabGame  # noqa: E402
from lab_spec import EXPERIMENT_REGISTRY  # noqa: E402
from varde import NO_PROGRESS_LIMIT, get_ruleset_spec  # noqa: E402
from research.harness import lab_oracle as oracle  # noqa: E402
from research.harness.lab_terminal_cert import (  # noqa: E402
    TerminalProvider, action_id, canonical_hash, canonical_json,
)


LEGACY_CANDIDATES = ("classic", "rosette", "breath", "breath-run", "gjerde", "gjerde-go")
PRODUCTION_RULESETS = LEGACY_CANDIDATES + tuple(EXPERIMENT_REGISTRY)
ADAPTER_REVISION = "0.1"
PROVENANCE_LIMIT = (
    "Current state and forbidden-history identity only. No complete seat-action "
    "trail, reachability certificate, or corpus admissibility is established. "
    "A game journal and current ending envelope cannot recover historic seat "
    "acceptances or the actor of every resumption."
)


class AdapterIntegrityError(ValueError):
    """A provider changed its input or returned contradictory mechanics."""


def _detached(value):
    return json.loads(canonical_json(value))


def _json_key(value):
    """Convert native immutable tuple keys, then enforce finite JSON."""
    if type(value) in (tuple, list):
        return [_json_key(item) for item in value]
    if type(value) is dict:
        return {key: _json_key(item) for key, item in value.items()}
    return value


def canonical_action_id(wire):
    """Complete semantic action JSON, never a coordinate-only identifier."""
    if type(wire) is not dict or type(wire.get("action")) is not str or not wire["action"]:
        raise ValueError("a structured action object is required")
    return action_id(wire)


def _domain(actions):
    result, seen = [], set()
    for wire in actions:
        identifier = canonical_action_id(wire)
        if identifier in seen:
            raise AdapterIntegrityError("duplicate legal action ID")
        seen.add(identifier)
        result.append(_detached(wire))
    return tuple(result)


def _source_hash(paths):
    """Hash source bytes with stable relative labels, never machine paths."""
    return canonical_hash({
        "format": "rules-lab-source-bundle-v1",
        "sources": [{"path": path, "sha256": hashlib.sha256((REPOSITORY / path).read_bytes()).hexdigest()}
                    for path in sorted(paths)],
    })


def _rules_hash(rules, revision):
    source = "engine/varde.py" if rules in LEGACY_CANDIDATES else "docs/rules-lab-specs.md"
    return canonical_hash({"format": "rules-lab-rule-source-v1", "rules": rules,
                           "revision": revision, "source_hash": _source_hash((source,))})


def _implementation_hash(independent, laboratory):
    paths = ["research/harness/lab_research_adapter.py", "research/harness/lab_terminal_cert.py"]
    if independent:
        paths += ["research/harness/lab_oracle.py", "research/harness/lab_oracle_geometry.py"]
    else:
        paths += ["engine/actions.py", "engine/game_factory.py", "engine/varde.py"]
        if laboratory:
            paths += ["engine/lab_game.py", "engine/lab_graph.py", "engine/lab_spec.py"]
    return _source_hash(paths)


def _seat_map(value):
    if (type(value) is not dict or set(value) != {"B", "W"}
            or any(type(seat) is not str or not seat for seat in value.values())
            or len(set(value.values())) != 2):
        raise ValueError("provider requires bijective color-seat identities")
    return dict(value)


def _actor(state):
    value = {"seat": state.actor_seat, "color": state.actor_color}
    if state.accepted:
        if value != {"seat": None, "color": None}:
            raise AdapterIntegrityError("accepted state still has an actor")
    elif (type(value["seat"]) is not str or not value["seat"]
          or value["color"] not in ("B", "W")):
        raise AdapterIntegrityError("unaccepted state lacks an actual actor")
    return value


def _ending_envelope(state, game, seats, *, quiet_end_limit=None):
    """Reject internally contradictory endings, without certifying a replay.

    This is an input boundary, not a second resolution engine or a claim that
    arbitrary stones/history are reachable. The checker still reconstructs all
    proof edges through the real mechanics.
    """
    seats = _seat_map(seats)
    quiet_end = getattr(game, "no_progress_end", False)
    if (any(type(flag) is not bool for flag in (state.accepted, game.finished, game.resumption_used, quiet_end))
            or type(game.consecutive_passes) is not int or not 0 <= game.consecutive_passes <= 2
            or type(game.quiet_moves) is not int or game.quiet_moves < 0
            or game.to_move not in ("B", "W") or state.end_decider not in (None, "B", "W")
            or type(state.end_acceptances) not in (set, frozenset)
            or any(type(seat) is not str for seat in state.end_acceptances)
            or not state.end_acceptances <= set(seats.values())):
        raise ValueError("invalid provider ending envelope")
    if quiet_end and (quiet_end_limit is None or game.quiet_moves < quiet_end_limit):
        raise ValueError("unsupported or contradictory quiet ending")
    if game.finished != (game.consecutive_passes == 2 or quiet_end):
        raise ValueError("finished flag contradicts the recorded ending phase")
    acceptances = state.end_acceptances
    if not game.finished:
        valid = not state.accepted and not acceptances and state.end_decider is None
    elif state.accepted:
        required = 1 if game.resumption_used or quiet_end else 2
        valid = (len(acceptances) == required and state.end_decider is None
                 and (required == 2 or acceptances == {seats[game.to_move]}))
    else:
        expected_decider = game.to_move
        valid = not acceptances
        if acceptances:
            valid = (acceptances == {seats[game.to_move]} and not game.resumption_used and not quiet_end)
            expected_decider = "W" if game.to_move == "B" else "B"
        valid = valid and state.end_decider == expected_decider
    if not valid:
        raise ValueError("invalid provider accepted-seat or pending-actor envelope")


def _score_pair(value):
    if (type(value) is not dict or set(value) != {"B", "W"}
            or any(type(score) is not int for score in value.values())):
        raise AdapterIntegrityError("terminal score must be an exact integer color pair")
    return dict(value)


def _metadata(snapshot, *, geometry, mechanics, initial_topology, topology_seed):
    journal = snapshot.get("journal")
    return _detached({
        "format": "rules-lab-state-metadata-v1",
        "initial_geometry": {"family": geometry, "n": snapshot["n"],
                             "topology": _json_key(initial_topology), "seed": topology_seed},
        "initial_players": snapshot.get("initial_players"),
        "provenance": {
            "mechanics": mechanics, "origin": "unattested-state-snapshot",
            "full_action_replay": False, "historical_seat_acceptances_recorded": False,
            "journal_present": journal is not None,
            "journal_action_count": len(journal) if journal is not None else None,
            "claim_limit": PROVENANCE_LIMIT,
        },
    })


def _geometry_identity(board):
    """Legacy geometry is mutable by convention; include its actual rule data."""
    value = {
        "n": board.n, "points": _json_key(board.points),
        "neighbors": [[list(point), _json_key(board.neighbors[point])] for point in board.points],
        "phantoms": [[list(point), board.phantoms[point]] for point in board.points],
        "rim": _json_key(sorted(board.rim)), "deep": _json_key(sorted(board.deep)),
    }
    for field in ("cell_edges", "edge_cells", "segments", "index"):
        if hasattr(board, field):
            value[field] = [[list(key), _json_key(item)] for key, item in sorted(getattr(board, field).items())]
    if hasattr(board, "cells"):
        value["cells"] = _json_key(board.cells)
    return value


def production_provider(rules_id):
    """Shared production mechanics for exactly six legacy plus ten lab rules."""
    if type(rules_id) is not str or rules_id not in PRODUCTION_RULESETS:
        raise ValueError("unsupported production research ruleset")
    laboratory = rules_id in EXPERIMENT_REGISTRY
    spec = EXPERIMENT_REGISTRY[rules_id] if laboratory else get_ruleset_spec(rules_id)
    provider_id = "rules-lab-production-state-v1"
    rules_hash = _rules_hash(rules_id, spec.revision)
    implementation_hash = _implementation_hash(False, laboratory)

    def require(state):
        if (not isinstance(state, RulesState) or state.game.rules != rules_id
                or isinstance(state.game, LabGame) != laboratory
                or type(state.accepted) is not bool):
            raise ValueError("provider requires the configured production RulesState")
        if laboratory and state.game.rules_revision != spec.revision:
            raise ValueError("unsupported laboratory rules revision")
        _ending_envelope(state, state.game, state.seats,
                         quiet_end_limit=None if laboratory else NO_PROGRESS_LIMIT)

    def snapshot(state):
        require(state)
        return _detached(state.to_dict())

    def metadata(state):
        require(state)
        return _metadata(snapshot(state), geometry=spec.geometry, mechanics="shared-production-rules",
                         initial_topology=getattr(state.game, "initial_topology", ()),
                         topology_seed=getattr(state.game, "topology_seed", None))

    def fingerprint(state):
        require(state)
        return canonical_hash({
            "format": "rules-lab-provider-state-v1", "provider": provider_id,
            "rules_id": rules_id, "rules_revision": spec.revision,
            "rules_hash": rules_hash, "implementation_hash": implementation_hash,
            "analysis_key": _json_key(state.analysis_key()),
            "snapshot": snapshot(state), "metadata": metadata(state),
            "geometry": _geometry_identity(state.game.board),
            # Game.clone preserves these unsaved presentation facts too; a
            # cache hit must not substitute another caller's capture prefix.
            "capture_waves": _json_key(state.game.last_capture_waves),
        })

    def actor(state):
        require(state)
        return _actor(state)

    def seats(state):
        require(state)
        return _seat_map(state.seats)

    def accepted(state):
        require(state)
        return state.accepted

    def score(state):
        require(state)
        if not state.accepted:
            raise ValueError("score is available only for an accepted terminal state")
        return _score_pair(state.game.score())

    def actions(state):
        require(state)
        return _domain(action.to_dict() for action in legal_actions(state))

    def transition(state, wire):
        require(state)
        canonical_action_id(wire)
        action = RulesAction.from_dict(_detached(wire))
        # No private candidate shortcut, heuristic value, or transition cache.
        return apply_action(deepcopy(state), action, copy=False, validate=True)

    return TerminalProvider(
        provider_id=provider_id, rules_id=rules_id, rules_revision=spec.revision,
        rules_hash=rules_hash, implementation_hash=implementation_hash,
        fingerprint=fingerprint, snapshot=snapshot, metadata=metadata, actor=actor,
        seats=seats, accepted=accepted, score=score, legal_actions=actions, transition=transition,
    )


def independent_provider(rules_id):
    """Independent oracle mechanics for ten definitions, not legacy cascades."""
    if type(rules_id) is str and rules_id in LEGACY_CANDIDATES:
        raise ValueError("legacy research rules are unsupported by the independent oracle")
    if type(rules_id) is not str or rules_id not in oracle.RULES:
        raise ValueError("unsupported independent research ruleset")
    spec = oracle.RULES[rules_id]
    revision, provider_id = oracle.ORACLE_REVISION, "rules-lab-independent-oracle-v1"
    rules_hash = _rules_hash(rules_id, revision)
    implementation_hash = _implementation_hash(True, True)
    geometry = "kagome-lines" if spec.lines else "honeycomb-junctions" if spec.family != "none" else "honeycomb-vertices"

    def require(state):
        if (not isinstance(state, oracle.OracleState) or state.rules != rules_id
                or state.rules_revision != revision or type(state.accepted) is not bool):
            raise ValueError("provider requires the configured independent OracleState")
        _ending_envelope(state, state, dict(zip(("B", "W"), state.seats)))

    def snapshot(state):
        require(state)
        return _detached(state.to_dict())

    def metadata(state):
        require(state)
        return _metadata(snapshot(state), geometry=geometry, mechanics="independent-laboratory-oracle",
                         initial_topology=state.initial_topology, topology_seed=state.topology_seed)

    def fingerprint(state):
        require(state)
        return canonical_hash({
            "format": "rules-lab-provider-state-v1", "provider": provider_id,
            "rules_id": rules_id, "rules_revision": revision,
            "rules_hash": rules_hash, "implementation_hash": implementation_hash,
            "analysis_key": _json_key(state.analysis_key()),
            "snapshot": snapshot(state), "metadata": metadata(state),
        })

    def actor(state):
        require(state)
        return _actor(state)

    def seats(state):
        require(state)
        return _seat_map(dict(zip(("B", "W"), state.seats)))

    def accepted(state):
        require(state)
        return state.accepted

    def score(state):
        require(state)
        if not state.accepted:
            raise ValueError("score is available only for an accepted terminal state")
        return _score_pair(oracle.score(state))

    def actions(state):
        require(state)
        return _domain(action.to_dict() for action in oracle.legal_actions(state))

    def transition(state, wire):
        require(state)
        canonical_action_id(wire)
        result = oracle.transition(state, oracle.OracleAction.from_dict(_detached(wire))).state
        # OracleState is transitively immutable. No production transition or
        # snapshot loader is used, and no provenance token is manufactured.
        return result

    return TerminalProvider(
        provider_id=provider_id, rules_id=rules_id, rules_revision=revision,
        rules_hash=rules_hash, implementation_hash=implementation_hash,
        fingerprint=fingerprint, snapshot=snapshot, metadata=metadata, actor=actor,
        seats=seats, accepted=accepted, score=score, legal_actions=actions, transition=transition,
    )


@dataclass(frozen=True)
class AdapterCounters:
    legal_action_enumerations: int = 0
    transition_requests: int = 0
    transition_attempts: int = 0
    resolved_transitions: int = 0
    cache_hits: int = 0

    def to_dict(self):
        return asdict(self)


class ResearchAdapter:
    """Instance-local bounded LRU of isolated production successors.

    analysis_key exposes the engine's full semantic key (including forbidden
    history). fingerprint additionally owns the exact replay/geometry prefix.
    Counters count explicit adapter work, not hidden legal-validation scans or
    simulated nodes. Failures count as attempts, never resolved transitions.
    """

    def __init__(self, rules_id, *, max_transitions=256):
        if type(max_transitions) is not int or max_transitions < 1:
            raise ValueError("transition cache capacity must be a positive integer")
        self.provider = production_provider(rules_id)
        self.max_transitions = max_transitions
        self._cache = OrderedDict()
        self._counts = AdapterCounters().to_dict()

    @property
    def counters(self):
        return AdapterCounters(**self._counts)

    @property
    def cached_transition_count(self):
        return len(self._cache)

    def analysis_key(self, state):
        self.provider.snapshot(state)  # type/rules and finite-JSON validation
        return deepcopy(state.analysis_key())

    def fingerprint(self, state):
        return self.provider.fingerprint(state)

    def _guarded(self, state, callback, *args):
        before = self.fingerprint(state)
        source = deepcopy(state)
        if self.fingerprint(source) != before:
            raise AdapterIntegrityError("input clone changed complete state identity")
        arguments = canonical_json(list(args))
        try:
            return callback(source, *args)
        finally:
            try:
                changed = (self.fingerprint(source) != before or self.fingerprint(state) != before
                           or canonical_json(list(args)) != arguments)
            except Exception as error:
                raise AdapterIntegrityError("provider mutated or invalidated its input") from error
            if changed:
                raise AdapterIntegrityError("provider mutated its input")

    def legal_actions(self, state):
        self._counts["legal_action_enumerations"] += 1
        # Materialize generators inside the guard, not after it has finished.
        return self._guarded(state, lambda source: _domain(self.provider.legal_actions(source)))

    def transition(self, state, wire):
        self._counts["transition_requests"] += 1
        identifier = canonical_action_id(wire)
        key = self.fingerprint(state), identifier
        if key in self._cache:
            self._counts["cache_hits"] += 1
            self._cache.move_to_end(key)
            return deepcopy(self._cache[key])
        self._counts["transition_attempts"] += 1
        def resolve(source, action):
            result = self.provider.transition(source, action)
            if not isinstance(result, RulesState) or result is source or result.game is source.game:
                raise AdapterIntegrityError("provider did not return an isolated RulesState")
            return result

        result = self._guarded(state, resolve, _detached(wire))
        self.provider.snapshot(result)
        stored = deepcopy(result)
        self._cache[key] = stored
        self._cache.move_to_end(key)
        if len(self._cache) > self.max_transitions:
            self._cache.popitem(last=False)
        self._counts["resolved_transitions"] += 1
        return deepcopy(stored)
