"""Experimental flat games, isolated from the legacy reference engine.

Version-two loading checks both schema and legal replay. An arbitrary constructed
mechanical-test position is not thereby journal-certified reachable evidence.
Seat acceptances belong to RulesState/the match envelope, not this game journal.
"""

from collections import deque
from copy import deepcopy

from lab_spec import get_experiment_spec
from varde import (
    BLACK, WHITE, Game, Illegal, control, groups_of, other, resolve,
)


SCORING_RULESETS = ("line-breath", "gjerde-majority", "breath-connection")
RESOLUTION_ALIASES = {
    "line-breath": "gjerde", "gjerde-majority": "gjerde",
    "breath-connection": "breath",
}
SNAPSHOT_FORMATS = ("varde-game", "cairn-game")
SNAPSHOT_VERSION = 2
OUTER_FIELDS = frozenset({"match", "rules_state"})


def _strict_point(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(type(component) is not int for component in value)):
        raise ValueError("point must contain two integer coordinates")
    return tuple(value)


def _players(value):
    if (type(value) is not dict or set(value) != {BLACK, WHITE}
            or any(not isinstance(name, str) or not name for name in value.values())):
        raise ValueError("invalid laboratory player names")
    return dict(value)


class LabGame(Game):
    """The three frozen scoring variants; construction games arrive separately."""

    def __init__(self, n=3, rules="breath-connection"):
        spec = get_experiment_spec(rules)
        if rules not in SCORING_RULESETS:
            raise ValueError("laboratory ruleset is not implemented yet")
        if type(n) is not int or n not in spec.allowed_sizes:
            raise ValueError("laboratory board size must be an integer from 3 through 6")
        super().__init__(n, rules=RESOLUTION_ALIASES[rules])
        self.rules = rules
        self.rules_revision = spec.revision
        self.topology = ()
        self.placements_played = 0
        self.constructions_played = 0
        self.action_journal = []
        self.history = {self.repetition_key()}

    def clone(self):
        target = object.__new__(type(self))
        for name, value in self.__dict__.items():
            # Geometry and tuple topology are shared, never modified. All game-
            # owned mutable collections (including nested journal points) copy.
            setattr(target, name, deepcopy(value) if isinstance(value, (dict, list, set)) else value)
        return target

    def repetition_key(self, state=None, to_move=None):
        state = self.state if state is None else state
        to_move = self.to_move if to_move is None else to_move
        return (
            self.rules, self.rules_revision, self.board.n, self.topology,
            to_move, tuple(state[point] for point in self.board.points),
        )

    def _resolve_placement(self, point, *, trace=None):
        if self.finished:
            raise Illegal("game over")
        try:
            point = _strict_point(point)
        except ValueError as error:
            raise Illegal(str(error)) from error
        if point not in self.state:
            raise Illegal("point is not an active intersection")
        # Alias only the local flat resolution rule. Laboratory repetition has
        # a different key, and must be checked after this real transition.
        state, captured = resolve(
            self.board, self.state, point, self.to_move, set(),
            trace=trace, rules=RESOLUTION_ALIASES[self.rules],
        )
        if self.repetition_key(state, other(self.to_move)) in self.history:
            raise Illegal("repetition")
        return point, state, captured

    def try_play(self, point):
        _point, state, captured = self._resolve_placement(point)
        return state, captured

    def legal_placements(self):
        if self.finished:
            return []
        choices = []
        for point in self.board.points:
            try:
                self.try_play(point)
            except Illegal:
                continue
            choices.append(point)
        return choices

    def play(self, point):
        waves = []
        point, state, captured = self._resolve_placement(point, trace=waves)
        was_swap_reply = self.moves_played == 1
        self.state = state
        self.to_move = other(self.to_move)
        self.moves_played += 1
        self.placements_played += 1
        self.consecutive_passes = 0
        self.quiet_moves = 0
        self.extension_used = False
        self.extension_points = []
        self.last_capture_waves = waves
        if was_swap_reply:
            self.swap_decided = True
        self.history.add(self.repetition_key())
        self.action_journal.append({"action": "play", "point": list(point)})
        return captured

    def play_pass(self):
        if self.finished:
            raise Illegal("game over")
        if self.moves_played == 0:
            raise Illegal("first move must be a placement")
        if self.moves_played == 1:
            self.swap_decided = True
        self.to_move = other(self.to_move)
        self.moves_played += 1
        self.consecutive_passes += 1
        self.quiet_moves += 1
        self.finished = self.consecutive_passes == 2
        self.last_capture_waves = []
        self.history.add(self.repetition_key())
        self.action_journal.append({"action": "pass"})

    def take_over(self):
        super().take_over()
        self.action_journal.append({"action": "swap"})

    def demand_resumption(self):
        super().demand_resumption()
        self.action_journal.append({"action": "resume"})

    def _area_score(self):
        score = self.control_count()
        seen = set()
        for point in self.board.points:
            if point in seen or self.state[point]:
                continue
            queue = deque([point])
            seen.add(point)
            region = []
            borders = set()
            while queue:
                current = queue.popleft()
                region.append(current)
                for neighbor in self.board.neighbors[current]:
                    if self.state[neighbor]:
                        borders.add(control(self.state, neighbor))
                    elif neighbor not in seen:
                        seen.add(neighbor)
                        queue.append(neighbor)
            if len(borders) == 1:
                score[next(iter(borders))] += len(region)
        return score

    def score(self):
        if self.rules == "gjerde-majority":
            score = {BLACK: 0, WHITE: 0}
            for cell in self.board.cells:
                edges = self.board.cell_edges[cell]
                for color in (BLACK, WHITE):
                    if sum(control(self.state, point) == color for point in edges) >= 4:
                        score[color] += 1
            return score
        score = self._area_score()
        if self.rules == "breath-connection":
            for color in (BLACK, WHITE):
                score[color] -= len(groups_of(self.board, self.state, color))
        return score

    @staticmethod
    def _history_record(key):
        rules, revision, n, topology, color, stacks = key
        return {
            "rules": rules, "rules_revision": revision, "n": n,
            "topology": [list(item) for item in topology], "to_move": color,
            "stacks": [list(stack) for stack in stacks],
        }

    def to_dict(self):
        initial_players = dict(self.players)
        if sum(event["action"] == "swap" for event in self.action_journal) % 2:
            initial_players[BLACK], initial_players[WHITE] = initial_players[WHITE], initial_players[BLACK]
        return {
            "format": "varde-game", "version": SNAPSHOT_VERSION,
            "rules": self.rules, "rules_revision": self.rules_revision,
            "n": self.board.n, "topology": [list(item) for item in self.topology],
            "stacks": [list(self.state[point]) for point in self.board.points],
            "to_move": self.to_move,
            "history": [self._history_record(key) for key in sorted(self.history, key=repr)],
            "moves_played": self.moves_played,
            "placements_played": self.placements_played,
            "constructions_played": self.constructions_played,
            "consecutive_passes": self.consecutive_passes, "quiet_moves": self.quiet_moves,
            "finished": self.finished, "no_progress_end": self.no_progress_end,
            "resumption_used": self.resumption_used, "swap_decided": self.swap_decided,
            "extension_used": self.extension_used, "extension_points": list(self.extension_points),
            "players": dict(self.players), "initial_players": initial_players,
            "journal": deepcopy(self.action_journal),
        }

    @classmethod
    def from_dict(cls, payload):
        """Validate schema, then certify the entire supplied state by legal replay.

        This checks reachability from the initial board and history completeness,
        not the truth of externally supplied tactical or strategic annotations.
        """
        if type(payload) is not dict:
            raise ValueError("invalid laboratory snapshot")
        if (payload.get("format") not in SNAPSHOT_FORMATS
                or type(payload.get("version")) is not int
                or payload["version"] != SNAPSHOT_VERSION):
            raise ValueError("unsupported laboratory snapshot")
        game = cls(payload.get("n"), rules=payload.get("rules"))
        expected_fields = set(game.to_dict())
        if set(payload) - OUTER_FIELDS != expected_fields:
            raise ValueError("missing or unsupported laboratory snapshot fields")
        if payload["rules_revision"] != game.rules_revision:
            raise ValueError("unsupported laboratory rules revision")
        for field in ("moves_played", "placements_played", "constructions_played",
                      "consecutive_passes", "quiet_moves"):
            if type(payload[field]) is not int or payload[field] < 0:
                raise ValueError(f"invalid integer laboratory counter: {field}")
        for field in ("finished", "no_progress_end", "resumption_used",
                      "swap_decided", "extension_used"):
            if type(payload[field]) is not bool:
                raise ValueError(f"invalid Boolean laboratory state: {field}")
        if payload["topology"] != [] or type(payload["topology"]) is not list:
            raise ValueError("scoring variants have no constructed topology")
        if (payload["constructions_played"] != 0 or payload["no_progress_end"]
                or payload["extension_used"] or payload["extension_points"] != []
                or type(payload["extension_points"]) is not list):
            raise ValueError("invented construction, extension, or stagnation state")
        game.players = _players(payload["initial_players"])
        _players(payload["players"])
        if payload["to_move"] not in (BLACK, WHITE):
            raise ValueError("invalid next color")

        def validate_stacks(stacks):
            if type(stacks) is not list or len(stacks) != len(game.board.points):
                raise ValueError("invalid flat stone array")
            for stack in stacks:
                if (type(stack) is not list or len(stack) > 1
                        or any(color not in (BLACK, WHITE) for color in stack)):
                    raise ValueError("invalid flat stack")

        validate_stacks(payload["stacks"])
        if type(payload["history"]) is not list or not payload["history"]:
            raise ValueError("complete laboratory history is required")
        history_fields = set(game._history_record(game.repetition_key()))
        for record in payload["history"]:
            if type(record) is not dict or set(record) != history_fields:
                raise ValueError("invalid laboratory history entry")
            if (record["rules"] != game.rules or record["rules_revision"] != game.rules_revision
                    or type(record["n"]) is not int or record["n"] != game.board.n
                    or type(record["topology"]) is not list or record["topology"] != []
                    or record["to_move"] not in (BLACK, WHITE)):
                raise ValueError("incompatible laboratory history entry")
            validate_stacks(record["stacks"])
        if type(payload["journal"]) is not list:
            raise ValueError("complete laboratory action journal is required")
        # Local import keeps factory -> LabGame -> adapter loading acyclic.
        # API, replay, and agents must agree on the one action representation.
        from actions import RulesAction

        for event in payload["journal"]:
            action = RulesAction.from_dict(event)
            if action.kind not in ("play", "pass", "swap", "resume"):
                raise ValueError("unsupported laboratory journal action")
            try:
                if action.kind == "play":
                    game.play(action.point)
                elif action.kind == "pass":
                    game.play_pass()
                elif action.kind == "swap":
                    game.take_over()
                else:
                    game.demand_resumption()
            except Illegal as error:
                raise ValueError(f"illegal laboratory journal transition: {error}") from error
        actual = {key: value for key, value in payload.items() if key not in OUTER_FIELDS}
        actual["format"] = "varde-game"
        if actual != game.to_dict():
            raise ValueError("laboratory journal does not reproduce supplied state or complete history")
        return game
