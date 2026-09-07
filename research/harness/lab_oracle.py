"""Independent revision-0.1 laboratory mechanics, with no production imports.

This is a mechanical reference, not a proof runner or admitted game-playing agent.
The game journal and the current seat envelope have distinct provenance limits.
"""

from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json

from research.harness.lab_oracle_geometry import (
    ORIENTATIONS, REVISION, RULES, OracleGeometry, build_geometry,
    canonical_topology, initial_topology, rule_spec,
)


COLORS = ("B", "W")
ACTION_KINDS = ("play", "construct", "plant", "pass", "swap", "resume", "accept")
ORACLE_REVISION = "0.1"


class OracleIllegal(ValueError):
    """A well-formed action is not legal in this oracle state."""


def _opponent(color):
    return "W" if color == "B" else "B"


def _coordinate(value):
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(type(v) is int for v in value)


def _named_pair(value, label):
    if isinstance(value, dict):
        if set(value) != set(COLORS):
            raise ValueError(f"invalid {label}")
        value = tuple(value[color] for color in COLORS)
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(item, str) and item for item in value)):
        raise ValueError(f"invalid {label}")
    result = tuple(value)
    if label == "seats" and len(set(result)) != 2:
        raise ValueError("seat identities must be distinct")
    return result


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class OracleAction:
    kind: str
    point: tuple | None = None
    orientation: int | None = None

    def __post_init__(self):
        if self.kind not in ACTION_KINDS:
            raise ValueError("unsupported oracle action")
        if self.kind in ("play", "construct", "plant"):
            if type(self.point) is not tuple or not _coordinate(self.point):
                raise ValueError("invalid action coordinate")
        elif self.point is not None:
            raise ValueError("administrative actions have no coordinate")
        if self.kind in ("construct", "plant"):
            if type(self.orientation) is not int or not 0 <= self.orientation <= 2:
                raise ValueError("invalid construction orientation")
        elif self.orientation is not None:
            raise ValueError("only construction actions have an orientation")

    @classmethod
    def from_dict(cls, payload):
        if type(payload) is not dict or not isinstance(payload.get("action"), str):
            raise ValueError("invalid oracle action dictionary")
        kind = payload["action"]
        if kind not in ACTION_KINDS:
            raise ValueError("unsupported oracle action")
        key = "face" if kind in ("construct", "plant") else "point" if kind == "play" else None
        fields = {"action"} | ({key} if key else set())
        if kind in ("construct", "plant"):
            fields.add("orientation")
        if set(payload) != fields:
            raise ValueError("invalid oracle action fields")
        if key and (type(payload[key]) is not list or not _coordinate(payload[key])):
            raise ValueError("invalid action coordinate array")
        return cls(kind, tuple(payload[key]) if key else None, payload.get("orientation"))

    def to_dict(self):
        result = {"action": self.kind}
        if self.kind in ("construct", "plant"):
            result.update(face=list(self.point), orientation=self.orientation)
        elif self.kind == "play":
            result["point"] = list(self.point)
        return result


@dataclass(frozen=True)
class OracleState:
    rules: str
    n: int
    stones: tuple
    topology: tuple = ()
    initial_topology: tuple = ()
    topology_seed: int = 0
    rules_revision: str = REVISION
    to_move: str = "B"
    players: tuple = ("Player 1", "Player 2")
    initial_players: tuple = ("Player 1", "Player 2")
    seats: tuple = ("seat-black", "seat-white")
    history: frozenset = frozenset()
    journal: tuple = ()
    moves_played: int = 0
    placements_played: int = 0
    constructions_played: int = 0
    consecutive_passes: int = 0
    quiet_moves: int = 0
    finished: bool = False
    swap_decided: bool = False
    resumption_used: bool = False
    end_acceptances: frozenset = frozenset()
    end_decider: str | None = None
    accepted: bool = False

    def __post_init__(self):
        rule_spec(self.rules, self.n)
        if self.rules_revision != REVISION or self.to_move not in COLORS:
            raise ValueError("invalid oracle state revision or next color")
        if (type(self.topology) is not tuple or type(self.initial_topology) is not tuple
                or any(type(row) is not tuple or len(row) != 3
                       or any(type(value) is not int for value in row)
                       for row in self.topology + self.initial_topology)
                or type(self.topology_seed) is not int
                or type(self.history) is not frozenset or type(self.journal) is not tuple
                or not all(isinstance(action, OracleAction) for action in self.journal)
                or type(self.end_acceptances) is not frozenset):
            raise ValueError("oracle state collections must be immutable")
        board = geometry(self)
        if (board.topology != self.topology
                or _state_geometry(self.rules, self.n, self.initial_topology).topology != self.initial_topology):
            raise ValueError("oracle topology must be canonical")
        if type(self.stones) is not tuple or len(self.stones) != len(board.points):
            raise ValueError("invalid oracle stone vector")
        if any(stone not in (None, *COLORS) for stone in self.stones):
            raise ValueError("invalid oracle stone")
        if any(type(pair) is not tuple for pair in (self.players, self.initial_players, self.seats)):
            raise ValueError("oracle identity collections must be immutable")
        _named_pair(self.players, "players")
        _named_pair(self.initial_players, "players")
        _named_pair(self.seats, "seats")
        for value in (self.moves_played, self.placements_played, self.constructions_played,
                      self.consecutive_passes, self.quiet_moves):
            if type(value) is not int or value < 0:
                raise ValueError("invalid oracle integer counter")
        for value in (self.finished, self.swap_decided, self.resumption_used, self.accepted):
            if type(value) is not bool:
                raise ValueError("invalid oracle Boolean flag")
        if self.end_decider not in (None, *COLORS) or not self.end_acceptances <= set(self.seats):
            raise ValueError("invalid oracle ending identity")

    @property
    def terminal(self):
        return self.accepted

    @property
    def actor_color(self):
        return None if self.accepted else self.end_decider if self.finished else self.to_move

    @property
    def actor_seat(self):
        return self.seats[COLORS.index(self.actor_color)] if self.actor_color else None

    @property
    def swap_available(self):
        return self.moves_played == 1 and self.to_move == "W" and not self.swap_decided and not self.finished and not self.accepted

    @property
    def resumption_available(self):
        return self.finished and not self.resumption_used and not self.accepted

    def color_for_seat(self, identity):
        if identity not in self.seats:
            raise ValueError("unknown oracle seat")
        return COLORS[self.seats.index(identity)]

    def at(self, point):
        return self.stones[geometry(self).index[point]]

    def repetition_key(self):
        return (self.rules, self.rules_revision, self.n, self.topology, self.to_move,
                tuple(() if stone is None else (stone,) for stone in self.stones))

    def analysis_key(self):
        return (self.repetition_key(), tuple(sorted(self.history, key=repr)), self.players, self.seats,
                self.moves_played, self.placements_played, self.constructions_played,
                self.consecutive_passes, self.quiet_moves, self.finished, self.swap_decided,
                self.resumption_used, tuple(sorted(self.end_acceptances)), self.end_decider, self.accepted)

    def to_dict(self):
        result = {
            "format": "varde-game", "version": 2, "rules": self.rules,
            "rules_revision": self.rules_revision, "n": self.n,
            "topology": [list(row) for row in self.topology],
            "stacks": [[] if stone is None else [stone] for stone in self.stones],
            "to_move": self.to_move,
            "history": [_history_record(key) for key in sorted(self.history, key=repr)],
            "moves_played": self.moves_played, "placements_played": self.placements_played,
            "constructions_played": self.constructions_played,
            "consecutive_passes": self.consecutive_passes, "quiet_moves": self.quiet_moves,
            "finished": self.finished, "no_progress_end": False,
            "resumption_used": self.resumption_used, "swap_decided": self.swap_decided,
            "extension_used": False, "extension_points": [],
            "players": dict(zip(COLORS, self.players)),
            "initial_players": dict(zip(COLORS, self.initial_players)),
            "journal": [action.to_dict() for action in self.journal],
            "rules_state": {"version": 1, "seats": dict(zip(COLORS, self.seats)),
                            "end_acceptances": sorted(self.end_acceptances),
                            "end_decider": self.end_decider, "accepted": self.accepted},
        }
        if self.rules not in ("line-breath", "gjerde-majority", "breath-connection"):
            result.update(topology_seed=self.topology_seed,
                          initial_topology=[list(row) for row in self.initial_topology])
        return result


@dataclass(frozen=True)
class OracleTransition:
    state: OracleState
    action: OracleAction
    captured_original: int = 0
    captured_junction: int = 0
    captured_points: frozenset = frozenset()

    @property
    def captured_total(self):
        return self.captured_original + self.captured_junction


@dataclass(frozen=True)
class ActorTrace:
    index: int
    action: OracleAction
    actor_seat: str | None
    actor_color: str | None
    next_actor_seat: str | None
    next_actor_color: str | None


@dataclass(frozen=True)
class OracleImport:
    state: OracleState
    mechanical_journal_verified: bool
    current_envelope_verified: bool
    full_action_replay: bool
    input_sha256: str
    assumptions: tuple = ()
    actor_trace: tuple = ()


@lru_cache(maxsize=128)
def _state_geometry(rules, n, topology):
    # Immutable states validate once per distinct topology, not once per stone
    # query. Retained snapshots own their geometry even after cache eviction.
    return build_geometry(rules, n, topology)


def geometry(state) -> OracleGeometry:
    return _state_geometry(state.rules, state.n, state.topology)


def new_state(rules, n=3, *, seed=0, seats=("seat-black", "seat-white"), players=("Player 1", "Player 2")):
    topology = initial_topology(rules, n, seed)
    board = build_geometry(rules, n, topology)
    players = _named_pair(players, "players")
    state = OracleState(rules, n, (None,) * len(board.points), topology=topology,
                        initial_topology=topology, topology_seed=seed,
                        seats=_named_pair(seats, "seats"), players=players, initial_players=players)
    return replace(state, history=frozenset((state.repetition_key(),)))


def groups(state, color):
    """Independent union-find, returning components in coordinate order."""
    if color not in COLORS:
        raise ValueError("invalid group color")
    board = geometry(state)
    parents = {point: point for point in board.points if state.stones[board.index[point]] == color}

    def find(point):
        while parents[point] != point:
            parents[point] = parents[parents[point]]
            point = parents[point]
        return point

    for a, b in board.edges:
        if a in parents and b in parents:
            root_a, root_b = find(a), find(b)
            if root_a != root_b:
                parents[max(root_a, root_b)] = min(root_a, root_b)
    components = {}
    for point in parents:
        components.setdefault(find(point), set()).add(point)
    return tuple(frozenset(points) for _, points in sorted(components.items()))


def liberties(state, members):
    if _coordinate(members):
        point = tuple(members)
        color = state.at(point)
        if color is None:
            raise ValueError("a group point must be occupied")
        members = next(group for group in groups(state, color) if point in group)
    board = geometry(state)
    return frozenset(neighbor for point in members for neighbor in board.neighbors[point]
                     if state.stones[board.index[neighbor]] is None)


def score(state):
    board = geometry(state)
    spec = RULES[state.rules]
    result = {"B": 0, "W": 0}
    if spec.scoring == "majority":
        for edges in board.cell_edges.values():
            for color in COLORS:
                result[color] += sum(state.at(point) == color for point in edges) >= 4
        return result
    original = frozenset(board.original_points)
    for point in original:
        color = state.at(point)
        if color is not None:
            result[color] += 1
    unseen = {point for point in board.points if state.at(point) is None}
    while unseen:
        first = min(unseen)
        unseen.remove(first)
        frontier, region, border = [first], {first}, set()
        while frontier:
            point = frontier.pop()
            for neighbor in board.neighbors[point]:
                color = state.at(neighbor)
                if color is not None:
                    border.add(color)
                elif neighbor in unseen:
                    unseen.remove(neighbor)
                    region.add(neighbor)
                    frontier.append(neighbor)
        if len(border) == 1:
            result[next(iter(border))] += len(region & original)
    if spec.scoring == "connection":
        for color in COLORS:
            result[color] -= len(groups(state, color))
    return result


def _placement(state, point):
    board = geometry(state)
    if point not in board.index or state.at(point) is not None:
        raise OracleIllegal("placement requires an active empty point")
    if not state.moves_played and point not in board.original_points:
        raise OracleIllegal("opening must be on an original point")
    stones = list(state.stones)
    stones[board.index[point]] = state.to_move
    provisional = replace(state, stones=tuple(stones))
    if RULES[state.rules].breath_first and not liberties(provisional, point):
        raise OracleIllegal("suicide before capture")
    enemy = _opponent(state.to_move)
    captured = frozenset(point for group in groups(provisional, enemy)
                         if not liberties(provisional, group) for point in group)
    for removed in captured:
        stones[board.index[removed]] = None
    result = replace(state, stones=tuple(stones))
    if any(not liberties(result, group) for group in groups(result, state.to_move)):
        raise OracleIllegal("suicide")
    return result, captured


def transition(state, action):
    if isinstance(action, dict):
        action = OracleAction.from_dict(action)
    if not isinstance(action, OracleAction):
        raise ValueError("an OracleAction is required")
    if state.terminal:
        raise OracleIllegal("accepted game has no further actions")
    if state.finished and action.kind not in ("resume", "accept"):
        raise OracleIllegal("the game is awaiting an ending decision")
    if not state.finished and action.kind in ("resume", "accept"):
        raise OracleIllegal("no ending decision is available")
    captured = frozenset()
    if action.kind == "accept":
        acceptances = state.end_acceptances | {state.actor_seat}
        accepted = state.resumption_used or len(acceptances) == 2
        child = replace(state, end_acceptances=frozenset(acceptances), accepted=accepted,
                        end_decider=None if accepted else _opponent(state.end_decider))
    elif action.kind == "resume":
        if not state.resumption_available:
            raise OracleIllegal("resumption is unavailable")
        child = replace(state, resumption_used=True, finished=False, consecutive_passes=0,
                        quiet_moves=0, end_acceptances=frozenset(), end_decider=None,
                        journal=state.journal + (action,))
    elif action.kind == "swap":
        if not state.swap_available:
            raise OracleIllegal("takeover is unavailable")
        child = replace(state, players=state.players[::-1], seats=state.seats[::-1],
                        swap_decided=True, journal=state.journal + (action,))
    elif action.kind == "pass":
        if not state.moves_played:
            raise OracleIllegal("opening must be a placement")
        next_color = _opponent(state.to_move)
        finished = state.consecutive_passes + 1 == 2
        child = replace(state, to_move=next_color, moves_played=state.moves_played + 1,
                        consecutive_passes=state.consecutive_passes + 1, quiet_moves=state.quiet_moves + 1,
                        finished=finished, end_decider=next_color if finished else None,
                        swap_decided=state.swap_decided or state.moves_played == 1,
                        journal=state.journal + (action,))
        child = replace(child, history=state.history | {child.repetition_key()})
    else:
        child = state
        if action.kind in ("construct", "plant"):
            spec = RULES[state.rules]
            if spec.construction != action.kind or not state.moves_played:
                raise OracleIllegal("construction is unavailable")
            if action.point in {(q, r) for q, r, _ in state.topology}:
                raise OracleIllegal("face is already active")
            try:
                topology = canonical_topology(state.rules, state.n, state.topology + ((*action.point, action.orientation),))
                board = build_geometry(state.rules, state.n, topology)
            except ValueError as error:
                raise OracleIllegal(str(error)) from error
            previous = dict(zip(geometry(state).points, state.stones))
            child = replace(state, topology=topology, stones=tuple(previous.get(point) for point in board.points))
            if action.kind == "plant":
                child, captured = _placement(child, board.centers[action.point])
        else:
            child, captured = _placement(child, action.point)
        child = replace(child, to_move=_opponent(state.to_move), moves_played=state.moves_played + 1,
                        placements_played=state.placements_played + (action.kind in ("play", "plant")),
                        constructions_played=state.constructions_played + (action.kind in ("construct", "plant")),
                        consecutive_passes=0, quiet_moves=0,
                        swap_decided=state.swap_decided or state.moves_played == 1,
                        end_acceptances=frozenset(), end_decider=None,
                        journal=state.journal + (action,))
        if child.repetition_key() in state.history:
            raise OracleIllegal("repetition")
        child = replace(child, history=state.history | {child.repetition_key()})
    original = frozenset(geometry(state).original_points)
    return OracleTransition(child, action, len(captured & original), len(captured - original), captured)


def legal_actions(state):
    if state.terminal:
        return ()
    if state.finished:
        return ((OracleAction("resume"),) if state.resumption_available else ()) + (OracleAction("accept"),)
    candidates = [OracleAction("swap")] if state.swap_available else []
    candidates.extend(OracleAction("play", point) for point in geometry(state).points if state.at(point) is None)
    if state.moves_played:
        candidates.append(OracleAction("pass"))
        spec = RULES[state.rules]
        if spec.construction:
            used = {(q, r) for q, r, _ in state.topology}
            candidates.extend(OracleAction(spec.construction, face, orientation)
                              for face in geometry(state).faces if face not in used
                              for orientation in range(len(ORIENTATIONS[spec.family])))
    legal = []
    for action in candidates:
        try:
            transition(state, action)
        except OracleIllegal:
            continue
        legal.append(action)
    return tuple(legal)


def replay(initial, actions):
    """Replay a supplied sequence, certifying full history only from fresh state.

    A continuation retains its actor trace but cannot recover omitted historical
    seat actions from an imported game journal or a constructed starting state.
    """
    source_actions = tuple(action if isinstance(action, OracleAction) else OracleAction.from_dict(action)
                           for action in actions)
    state, traces = initial, []
    for index, action in enumerate(source_actions):
        before_seat, before_color = state.actor_seat, state.actor_color
        state = transition(state, action).state
        traces.append(ActorTrace(index, action, before_seat, before_color, state.actor_seat, state.actor_color))
    fresh = new_state(initial.rules, initial.n, seed=initial.topology_seed,
                      seats=initial.seats, players=initial.players)
    starts_at_initial = initial == fresh
    assumptions = () if starts_at_initial else ("Only the supplied continuation was replayed; starting-position reachability is not certified.",)
    return OracleImport(state, starts_at_initial, True, starts_at_initial,
                        _digest({"initial": initial.to_dict(), "actions": [action.to_dict() for action in source_actions]}),
                        assumptions, tuple(traces))


def _history_record(key):
    rules, revision, n, topology, color, stacks = key
    return {"rules": rules, "rules_revision": revision, "n": n,
            "topology": [list(row) for row in topology], "to_move": color,
            "stacks": [list(stack) for stack in stacks]}


def _strict_stones(raw, board):
    if type(raw) is not list or len(raw) != len(board.points):
        raise ValueError("invalid snapshot stone array")
    if any(type(stack) is not list or len(stack) > 1 or any(stone not in COLORS for stone in stack) for stack in raw):
        raise ValueError("invalid flat snapshot stone")


def _strict_topology(raw, rules, n):
    if type(raw) is not list or any(type(row) is not list for row in raw):
        raise ValueError("invalid snapshot topology array")
    canonical = canonical_topology(rules, n, raw)
    if raw != [list(row) for row in canonical]:
        raise ValueError("snapshot topology is not canonical")
    return canonical


def _envelope(raw, state):
    fields = {"version", "seats", "end_acceptances", "end_decider", "accepted"}
    if type(raw) is not dict or set(raw) != fields or type(raw["version"]) is not int or raw["version"] != 1:
        raise ValueError("invalid oracle rules-state envelope")
    if _named_pair(raw["seats"], "seats") != state.seats:
        raise ValueError("envelope seat identities do not match replay")
    acceptances = raw["end_acceptances"]
    if (type(acceptances) is not list or any(not isinstance(seat, str) for seat in acceptances)
            or len(set(acceptances)) != len(acceptances) or not set(acceptances) <= set(state.seats)
            or type(raw["accepted"]) is not bool or raw["end_decider"] not in (None, *COLORS)):
        raise ValueError("invalid oracle ending envelope")
    if not state.finished and (acceptances or raw["accepted"] or raw["end_decider"] is not None):
        raise ValueError("unfinished game cannot contain ending decisions")
    # Establish consistency, not observation: these actions are absent from the
    # saved game journal and are never added to the import's actor trace.
    for _ in acceptances:
        state = transition(state, OracleAction("accept")).state
    # The wire list is a set of identities, not a historical action sequence.
    # Accept both list orders while preserving duplicate/identity validation.
    normalized = raw | {"end_acceptances": sorted(acceptances)}
    if state.to_dict()["rules_state"] != normalized:
        raise ValueError("rules-state envelope is inconsistent with ending order")
    return state


def load_snapshot(payload):
    if type(payload) is not dict or payload.get("format") not in ("varde-game", "cairn-game") or type(payload.get("version")) is not int or payload["version"] != 2:
        raise ValueError("unsupported oracle snapshot")
    if payload.get("rules_revision") != REVISION:
        raise ValueError("unsupported oracle rules revision")
    rules, n = payload.get("rules"), payload.get("n")
    rule_spec(rules, n)
    seed = payload.get("topology_seed", 0)
    if type(seed) is not int:
        raise ValueError("invalid topology seed")
    players = _named_pair(payload.get("initial_players"), "players")
    _named_pair(payload.get("players"), "players")
    journal = payload.get("journal")
    if type(journal) is not list:
        raise ValueError("complete game journal is required")
    journal = tuple(OracleAction.from_dict(event) for event in journal)
    if any(action.kind == "accept" for action in journal):
        raise ValueError("seat acceptance cannot occur in the game journal")
    raw_envelope = payload.get("rules_state")
    seats = ("seat-black", "seat-white")
    if raw_envelope is not None:
        if type(raw_envelope) is not dict:
            raise ValueError("invalid rules-state envelope")
        seats = _named_pair(raw_envelope.get("seats"), "seats")
        if sum(action.kind == "swap" for action in journal) % 2:
            seats = seats[::-1]
    state = new_state(rules, n, seed=seed, seats=seats, players=players)
    expected_fields = set(state.to_dict()) - {"rules_state"}
    if set(payload) - {"match", "rules_state"} != expected_fields:
        raise ValueError("missing or unsupported snapshot fields")
    for field in ("moves_played", "placements_played", "constructions_played", "consecutive_passes", "quiet_moves"):
        if type(payload[field]) is not int or payload[field] < 0:
            raise ValueError("invalid snapshot integer counter")
    for field in ("finished", "no_progress_end", "resumption_used", "swap_decided", "extension_used"):
        if type(payload[field]) is not bool:
            raise ValueError("invalid snapshot Boolean flag")
    if payload["no_progress_end"] or payload["extension_used"] or type(payload["extension_points"]) is not list or payload["extension_points"]:
        raise ValueError("invented laboratory extension or quiet ending")
    current_topology = _strict_topology(payload["topology"], rules, n)
    if "initial_topology" in payload and _strict_topology(payload["initial_topology"], rules, n) != state.initial_topology:
        raise ValueError("initial topology differs from the rules and seed")
    _strict_stones(payload["stacks"], build_geometry(rules, n, current_topology))
    if payload["to_move"] not in COLORS:
        raise ValueError("invalid snapshot next color")
    history = payload["history"]
    if type(history) is not list or not history:
        raise ValueError("complete snapshot history is required")
    history_fields = set(_history_record(state.repetition_key()))
    for row in history:
        if type(row) is not dict or set(row) != history_fields:
            raise ValueError("invalid history record fields")
        if (row["rules"] != rules or row["rules_revision"] != REVISION
                or type(row["n"]) is not int or row["n"] != n or row["to_move"] not in COLORS):
            raise ValueError("incompatible history record")
        topology = _strict_topology(row["topology"], rules, n)
        if not set(state.initial_topology) <= set(topology) <= set(current_topology):
            raise ValueError("history contains a removed, rotated, or future junction")
        _strict_stones(row["stacks"], build_geometry(rules, n, topology))
    for action in journal:
        state = transition(state, action).state
    actual = {key: value for key, value in payload.items() if key not in ("format", "rules_state", "match")}
    expected = {key: value for key, value in state.to_dict().items() if key not in ("format", "rules_state")}
    if actual != expected:
        raise ValueError("game journal does not reproduce the supplied state and complete history")
    assumptions = ["Game journal verified; historical seat acceptances and resumption actor identities were not recorded."]
    if raw_envelope is not None:
        state = _envelope(raw_envelope, state)
    else:
        assumptions.append("No seat envelope supplied; default seat identities and a pending first ending are assumed.")
    if "match" in payload:
        assumptions.append("Match presentation/configuration is outside the mechanical verification scope.")
    return OracleImport(state, True, raw_envelope is not None, False, _digest(payload), tuple(assumptions))
