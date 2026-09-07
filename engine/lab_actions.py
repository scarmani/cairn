"""Single-resolution laboratory transitions with decision-local ownership.

Candidate enumeration is only a structural superset. The shared apply_action
and LabGame transitions remain the sole capture, superko and turn authorities.
Legacy games never enter this module. No research or Personal model is loaded.
"""

from collections import OrderedDict
from dataclasses import dataclass, field

from actions import RulesAction, RulesState, apply_action
from lab_game import LabGame
from lab_spec import get_experiment_spec
from varde import Illegal, other


@dataclass(frozen=True)
class TransitionFacts:
    action_kind: str
    captured_original: int = 0
    captured_junction: int = 0

    @property
    def captured_total(self):
        return self.captured_original + self.captured_junction


@dataclass(frozen=True)
class LegalTransition:
    action: RulesAction
    facts: TransitionFacts
    _resolved: RulesState = field(repr=False, compare=False)

    def successor(self):
        """Return caller-owned state, never the cache's mutable snapshot."""
        return self._resolved.clone()


def _require_lab(state):
    if not isinstance(state, RulesState) or not isinstance(state.game, LabGame):
        raise ValueError("laboratory transitions require a laboratory RulesState")


def _candidates(state):
    if state.terminal:
        return
    game = state.game
    if game.finished:
        if game.resumption_available:
            yield RulesAction("resume")
        yield RulesAction("accept")
        return
    if game.swap_available:
        yield RulesAction("swap")
    original = getattr(game.board, "scoring_points", game.board.points)
    for point in game.board.points:
        if not game.state[point] and (game.moves_played or point in original):
            yield RulesAction("play", point)
    if game.moves_played:
        yield RulesAction("pass")
        spec = get_experiment_spec(game.rules)
        kind = next((kind for kind in ("construct", "plant")
                     if kind in spec.supported_actions), None)
        if kind is not None:
            for face in game.board.faces:
                if game.board.centers[face] in game.board.active_centers:
                    continue
                for orientation in range(len(spec.orientation_sets)):
                    yield RulesAction(kind, face, orientation=orientation)


def _replay_key(game):
    # analysis_key intentionally describes rule semantics rather than a unique
    # replay. A cached full successor must also preserve its exact source prefix.
    journal = tuple(
        (action.kind, action.point, action.orientation)
        for action in map(RulesAction.from_dict, game.action_journal)
    )
    return journal, getattr(game, "topology_seed", None), getattr(game, "initial_topology", ())


def _facts(before, after, action):
    enemy = other(before.actor_color)
    original = frozenset(getattr(before.game.board, "original_points", before.game.board.points))
    captured = {
        point for point, stack in before.game.state.items()
        if stack == (enemy,) and after.game.state.get(point) != (enemy,)
    }
    return TransitionFacts(action.kind, len(captured & original), len(captured - original))


class TransitionCache:
    """Bounded per-decision LRU; never shared between matches or threads."""

    def __init__(self, max_batches=2):
        if type(max_batches) is not int or max_batches < 1:
            raise ValueError("transition cache capacity must be a positive integer")
        self.max_batches = max_batches
        self.transition_attempts = 0
        self.legal_transition_count = 0
        self.cache_hits = 0
        self._batches = OrderedDict()

    def expand(self, state):
        _require_lab(state)
        # One complete-history key per expansion, not per candidate or leaf.
        key = state.analysis_key(), _replay_key(state.game)
        if key in self._batches:
            self.cache_hits += 1
            self._batches.move_to_end(key)
            return self._batches[key]
        transitions = []
        for action in _candidates(state):
            self.transition_attempts += 1
            try:
                child = apply_action(state, action, copy=True, validate=False)
            except Illegal:
                continue
            self.legal_transition_count += 1
            transitions.append(LegalTransition(action, _facts(state, child, action), child))
        result = tuple(transitions)
        self._batches[key] = result
        if len(self._batches) > self.max_batches:
            self._batches.popitem(last=False)
        return result


def legal_transitions(state, *, cache=None):
    """Resolve each candidate once; returned action order matches legal_actions."""
    return (cache if cache is not None else TransitionCache()).expand(state)
