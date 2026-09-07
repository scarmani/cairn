"""Shared research transition batches and rule-event ordering descriptors.

No search or proof runs here. Frozen certificate providers remain uncached.
Source identity is checked at construction/provider access and identity(); a
real decision wrapper must call identity() on entry AND exit. This avoids file
hash scans in every rollout callback without claiming origin attestation.
"""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
from pathlib import Path
import pickle
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
for directory in (REPOSITORY, REPOSITORY / "engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from actions import RulesAction, RulesState, apply_action, legal_actions  # noqa: E402
from lab_actions import TransitionCache, legal_transitions  # noqa: E402
from lab_game import LabGame  # noqa: E402
from varde import control, groups_of, has_sky, other, score_cells  # noqa: E402
from research.harness.lab_research_adapter import production_provider  # noqa: E402
from research.harness.lab_terminal_cert import action_id, canonical_hash, canonical_json  # noqa: E402

REVISION = "0.1"
RECIPE = "lab-shared-transition-facts-0.1"
ADMINISTRATIVE = frozenset(("swap", "pass", "resume", "accept", "finish-extension"))
SOURCE_PATHS = (
    "research/harness/lab_search_adapter.py", "research/harness/lab_research_adapter.py",
    "research/harness/lab_terminal_cert.py", "engine/actions.py", "engine/lab_actions.py",
    "engine/varde.py", "engine/lab_game.py", "engine/lab_graph.py", "engine/lab_spec.py",
    "engine/game_factory.py", "docs/rules-lab-specs.md", "docs/rules-lab-mcts-contract.md",
)
FACT_SPEC = {
    "capture": "positive per-column enemy color-mass loss; original/hub split; not top control",
    "defense": "one ordinary liberty and no strict sky before; all old control retained and >1 liberties or strict sky after",
    "new_top_sky": "newly placed or extended top cannot provide a strict sky in this transition",
    "cells": "positive NET actor-owned cell-count gain for gjerde/gjerde-go/majority only",
    "administrative": "zero capture/defense/cells; extension flag for actual extend/finish-extension",
    "authority": "lab single legal_transitions; legacy complete legal_actions then apply validated members",
}


class SearchAdapterIntegrityError(ValueError):
    """Source, state, domain, or snapshot ownership contract was violated."""


def _copy(value):
    return json.loads(canonical_json(value))


def _actual_sources():
    try:
        return {label: hashlib.sha256((REPOSITORY / label).read_bytes()).hexdigest() for label in SOURCE_PATHS}
    except OSError as error:
        raise SearchAdapterIntegrityError("search adapter dependency unavailable") from error


_LOADED_SOURCES = canonical_json(_actual_sources())


def _check_sources():
    sources = _actual_sources()
    if canonical_json(sources) != _LOADED_SOURCES:
        raise SearchAdapterIntegrityError("search adapter dependency bytes changed since import")
    return sources


@dataclass(frozen=True)
class SearchFacts:
    action_kind: str
    extension_action: bool = False
    captured_original: int = 0
    captured_junction: int = 0
    defended_group_count: int = 0
    completed_cells: int = 0

    def __post_init__(self):
        if type(self.action_kind) is not str or not self.action_kind or type(self.extension_action) is not bool:
            raise SearchAdapterIntegrityError("invalid action fact types")
        for name in ("captured_original", "captured_junction", "defended_group_count", "completed_cells"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise SearchAdapterIntegrityError("event counts must be exact nonnegative integers")

    @property
    def captured_enemy_stones(self):
        return self.captured_original + self.captured_junction


@dataclass(frozen=True, init=False)
class SearchTransition:
    """No cached mutable state escapes, including legacy mutable Board geometry.

    Bytes are made solely by pickling a trusted local state object passed to this
    constructor. No external pickle path/wire is accepted or loaded. This is an
    ownership mechanism, not a semantic identity or external save format.
    """
    _action_json: str
    facts: SearchFacts
    _state_bytes: bytes = field(repr=False, compare=False)
    _returned: object = field(repr=False, compare=False)

    def __init__(self, action, facts, successor_state, *, _returned=None):
        if type(action) is not dict or type(facts) is not SearchFacts:
            raise SearchAdapterIntegrityError("a full action wire and immutable SearchFacts are required")
        identifier = action_id(action)
        if action.get("action") != facts.action_kind:
            raise SearchAdapterIntegrityError("action and event facts disagree")
        try:
            data = pickle.dumps(successor_state, protocol=5)
        except Exception as error:
            raise SearchAdapterIntegrityError("trusted successor state cannot be isolated") from error
        object.__setattr__(self, "_action_json", identifier)
        object.__setattr__(self, "facts", facts)
        object.__setattr__(self, "_state_bytes", data)
        object.__setattr__(self, "_returned", _returned)

    @property
    def action(self):
        return json.loads(self._action_json)

    @property
    def action_id(self):
        return self._action_json

    def successor(self):
        try:
            result = pickle.loads(self._state_bytes)
        except Exception as error:
            raise SearchAdapterIntegrityError("internal trusted successor cannot be restored") from error
        if self._returned is not None:
            self._returned()
        return result


def _liberties(game, group):
    return {neighbor for point in group for neighbor in game.board.neighbors[point] if not game.state[neighbor]}


def _sky(game, group, placed=None):
    return any(has_sky(game.board, game.state, point, placed) for point in group)


def _cells(game, color):
    if game.rules in ("gjerde", "gjerde-go"):
        return score_cells(game.board, game.state)[color]
    if game.rules == "gjerde-majority":
        return game.score()[color]
    return 0


def _context(state):
    game, color = state.game, state.actor_color
    if color is None:
        return None
    threatened = tuple(frozenset(group) for group in groups_of(game.board, game.state, color)
                       if len(_liberties(game, group)) == 1 and not _sky(game, group))
    return {"color": color, "enemy": other(color), "threatened": threatened,
            "original": frozenset(getattr(game.board, "original_points", game.board.points)),
            "cells": _cells(game, color)}


def _facts(before, after, action, context):
    kind = action.kind
    extension = kind in ("extend", "finish-extension")
    if kind in ADMINISTRATIVE:
        return SearchFacts(kind, extension)
    if context is None:
        raise SearchAdapterIntegrityError("substantive transition lacks a current actor")
    enemy, original = context["enemy"], context["original"]
    captured_original = captured_junction = 0
    for point, stack in before.game.state.items():
        loss = max(0, stack.count(enemy) - after.game.state.get(point, ()).count(enemy))
        if point in original:
            captured_original += loss
        else:
            captured_junction += loss
    defenses = 0
    if context["threatened"]:
        game, color = after.game, context["color"]
        groups = groups_of(game.board, game.state, color)
        by_point = {point: group for group in groups for point in group}
        placed = action.point if kind in ("play", "extend") else game.board.centers[action.point] if kind == "plant" else None
        for old in context["threatened"]:
            if not all(point in game.state and control(game.state, point) == color for point in old):
                continue
            group = by_point[next(iter(old))]
            if len(_liberties(game, group)) > 1 or _sky(game, group, placed):
                defenses += 1
    cells = max(0, _cells(after.game, context["color"]) - context["cells"])
    return SearchFacts(kind, extension, captured_original, captured_junction, defenses, cells)


@dataclass(frozen=True)
class SearchAdapterCounters:
    expand_calls: int = 0
    batch_cache_hits: int = 0
    batches_resolved: int = 0
    fingerprint_calls: int = 0
    legacy_domain_enumerations: int = 0
    legacy_actions_enumerated: int = 0
    legacy_candidate_applications: int = 0
    lab_candidate_attempts: int = 0
    lab_legal_transitions: int = 0
    context_passes: int = 0
    fact_passes: int = 0
    successors_serialized: int = 0
    successors_returned: int = 0
    transition_requests: int = 0

    def to_dict(self):
        return asdict(self)


class SearchTransitionCache:
    """Decision-local LRU; exact member validation never re-enumerates a batch."""

    def __init__(self, rules_id, max_batches=2):
        if type(max_batches) is not int or max_batches < 1:
            raise SearchAdapterIntegrityError("cache capacity must be a positive exact integer")
        sources = _check_sources()
        self._base = production_provider(rules_id)
        self._max_batches = max_batches
        self._batches = OrderedDict()
        self._counts = SearchAdapterCounters().to_dict()
        self._identity = {"format": "varde-lab-search-adapter", "revision": REVISION, "recipe": RECIPE,
                          "base_provider": self._base.identity(), "sources": sources,
                          "cache_configuration": {"max_batches": max_batches},
                          "facts": FACT_SPEC,
                          "counter_limit": "Legacy legal_actions internally resolves candidates; those internal resolutions are not claimed counted here."}
        self._identity = _copy(self._identity)
        self._implementation_hash = canonical_hash(self._identity)
        self._provider = replace(self._base,
                                 provider_id=self._base.provider_id + "+search-cache-" + REVISION,
                                 implementation_hash=self._implementation_hash,
                                 legal_actions=self.legal_actions, transition=self.transition)

    @property
    def provider(self):
        self.identity()
        return self._provider

    @property
    def counters(self):
        return SearchAdapterCounters(**self._counts)

    @property
    def cached_batches(self):
        return len(self._batches)

    @property
    def max_batches(self):
        return self._max_batches

    def identity(self):
        _check_sources()
        if (type(self._max_batches) is not int
                or self._max_batches != self._identity["cache_configuration"]["max_batches"]):
            raise SearchAdapterIntegrityError("effective cache capacity differs from its frozen identity")
        return _copy(self._identity) | {"implementation_hash": self._implementation_hash}

    def _returned(self):
        self._counts["successors_returned"] += 1

    def expand(self, state):
        if not isinstance(state, RulesState):
            raise SearchAdapterIntegrityError("production RulesState required")
        self._counts["expand_calls"] += 1
        self._counts["fingerprint_calls"] += 1
        # Even a broken/injected identity callback must only see an isolated
        # object, and must not silently turn that object into another state.
        source = deepcopy(state)
        before = pickle.dumps(source, protocol=5)
        try:
            fingerprint = self._base.fingerprint(source)
            snapshot_json = canonical_json(self._base.snapshot(source))
        finally:
            if pickle.dumps(source, protocol=5) != before:
                raise SearchAdapterIntegrityError("identity callback mutated its input")
        if fingerprint in self._batches:
            previous_snapshot, rows = self._batches[fingerprint]
            if snapshot_json != previous_snapshot:
                raise SearchAdapterIntegrityError("same full fingerprint has a different snapshot")
            self._counts["batch_cache_hits"] += 1
            self._batches.move_to_end(fingerprint)
            return rows
        resolved = []
        try:
            context = _context(source)
            self._counts["context_passes"] += 1
            if isinstance(source.game, LabGame):
                lab_cache = TransitionCache(max_batches=1)
                try:
                    rows = legal_transitions(source, cache=lab_cache)
                finally:
                    self._counts["lab_candidate_attempts"] += lab_cache.transition_attempts
                    self._counts["lab_legal_transitions"] += lab_cache.legal_transition_count
                for row in rows:
                    resolved.append((row.action, row.successor()))
            else:
                self._counts["legacy_domain_enumerations"] += 1
                domain = []
                for action in legal_actions(source):
                    self._counts["legacy_actions_enumerated"] += 1
                    domain.append(action)
                for action in domain:
                    self._counts["legacy_candidate_applications"] += 1
                    resolved.append((action, apply_action(source, action, copy=True, validate=False)))
            output, seen = [], set()
            for action, child in resolved:
                wire = action.to_dict()
                identifier = action_id(wire)
                if identifier in seen:
                    raise SearchAdapterIntegrityError("duplicate complete action in legal domain")
                seen.add(identifier)
                child_before = pickle.dumps(child, protocol=5)
                try:
                    self._base.snapshot(child)
                finally:
                    if pickle.dumps(child, protocol=5) != child_before:
                        raise SearchAdapterIntegrityError("successor validation mutated its input")
                facts = _facts(source, child, action, context)
                self._counts["fact_passes"] += 1
                output.append(SearchTransition(wire, facts, child, _returned=self._returned))
                self._counts["successors_serialized"] += 1
            result = tuple(output)
        finally:
            if pickle.dumps(source, protocol=5) != before:
                raise SearchAdapterIntegrityError("legal transition generation mutated its source")
        self._counts["batches_resolved"] += 1
        self._batches[fingerprint] = snapshot_json, result
        if len(self._batches) > self.max_batches:
            self._batches.popitem(last=False)
        return result

    def legal_actions(self, state):
        return tuple(row.action for row in self.expand(state))

    def transition(self, state, wire):
        self._counts["transition_requests"] += 1
        try:
            parsed = RulesAction.from_dict(wire)
        except (ValueError, TypeError) as error:
            raise SearchAdapterIntegrityError("invalid complete transition wire") from error
        identifier = action_id(wire)
        if identifier != action_id(parsed.to_dict()):
            raise SearchAdapterIntegrityError("transition wire is not canonical semantic data")
        for row in self.expand(state):
            if row.action_id == identifier:
                return row.successor()
        raise SearchAdapterIntegrityError("action is not a member of this exact state's legal domain")
