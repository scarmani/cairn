"""Deterministic rules-action adapter shared by research agents.

The engine remains the sole authority for placement legality.  This layer adds
the identity state needed to represent pie takeover and the two players'
separate first-ending accept/resume decisions without changing saved games.
"""

from dataclasses import dataclass, field

from varde import BLACK, WHITE, Game, Illegal, get_ruleset_spec, other, signature


ACTION_ORDER = {
    "swap": 0,
    "extend": 1,
    "play": 2,
    "pass": 3,
    "finish-extension": 4,
    "resume": 5,
    "accept": 6,
    "construct": 7,
    "plant": 8,
}


@dataclass(frozen=True, order=True)
class RulesAction:
    kind: str
    point: tuple | None = None
    # Construction uses an axial face ID, serialized as `face`, not an active
    # intersection. Keep legacy repr/tie inputs byte-identical.
    orientation: int | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.kind not in ACTION_ORDER:
            raise ValueError("unknown rules action")
        located = self.kind in ("play", "extend", "construct", "plant")
        if located != (self.point is not None):
            raise ValueError("only placement and construction actions have coordinates")
        if self.kind in ("construct", "plant"):
            if type(self.point) is not tuple or not _coordinate(self.point):
                raise ValueError("invalid construction face")
            if type(self.orientation) is not int or not 0 <= self.orientation <= 2:
                raise ValueError("invalid construction orientation")
        elif self.orientation is not None:
            raise ValueError("only construction actions have an orientation")

    def sort_key(self):
        if self.kind in ("construct", "plant"):
            return (ACTION_ORDER[self.kind], self.point, self.orientation)
        return (ACTION_ORDER[self.kind], self.point or ())

    def to_dict(self):
        payload = {"action": self.kind}
        if self.kind in ("construct", "plant"):
            payload.update(face=list(self.point), orientation=self.orientation)
        elif self.point is not None:
            payload["point"] = list(self.point)
        return payload

    @classmethod
    def from_dict(cls, payload):
        """Parse a single unambiguous structured action for API/replay/search."""
        if not isinstance(payload, dict) or not isinstance(payload.get("action"), str):
            raise ValueError("invalid structured action")
        kind = payload["action"]
        if kind not in ACTION_ORDER:
            raise ValueError("unknown rules action")
        fields = {"action"}
        coordinate_name = None
        if kind in ("construct", "plant"):
            coordinate_name = "face"
            fields.update(("face", "orientation"))
        elif kind in ("play", "extend"):
            coordinate_name = "point"
            fields.add("point")
        if set(payload) != fields:
            raise ValueError("invalid structured action fields")
        point = None
        if coordinate_name:
            raw = payload[coordinate_name]
            if not isinstance(raw, list) or not _coordinate(raw):
                raise ValueError("invalid action coordinates")
            point = tuple(raw)
        return cls(kind, point, orientation=payload.get("orientation"))


def _coordinate(value):
    return (
        isinstance(value, (tuple, list)) and len(value) == 2
        and all(type(item) is int for item in value)
    )


@dataclass
class RulesState:
    game: Game
    seats: dict = field(
        default_factory=lambda: {BLACK: "seat-black", WHITE: "seat-white"}
    )
    end_acceptances: set = field(default_factory=set)
    end_decider: str | None = None
    accepted: bool = False

    def __post_init__(self):
        if set(self.seats) != {BLACK, WHITE}:
            raise ValueError("rules state requires Black and White seats")
        if len(set(self.seats.values())) != 2:
            raise ValueError("rules state seats must be distinct")
        if self.end_decider not in (None, BLACK, WHITE):
            raise ValueError("invalid end decider")
        if self.game.finished and self.end_decider is None and not self.accepted:
            self.end_decider = self.game.to_move

    @classmethod
    def from_game(cls, game):
        return cls(game.clone())

    def clone(self):
        return RulesState(
            self.game.clone(),
            seats=dict(self.seats),
            end_acceptances=set(self.end_acceptances),
            end_decider=self.end_decider,
            accepted=self.accepted,
        )

    @property
    def terminal(self):
        return self.accepted

    @property
    def actor_color(self):
        if self.terminal:
            return None
        if self.game.finished:
            return self.end_decider
        return self.game.to_move

    @property
    def actor_seat(self):
        color = self.actor_color
        return self.seats[color] if color else None

    def color_for_seat(self, seat):
        for color, identity in self.seats.items():
            if identity == seat:
                return color
        raise ValueError("unknown seat")

    def key(self):
        if hasattr(self.game, "repetition_key"):
            return self.analysis_key()
        game = self.game
        return (
            signature(game.board, game.state, game.to_move),
            *self._phase_key(),
        )

    def _phase_key(self):
        game = self.game
        return (
            game.rules,
            game.moves_played,
            game.consecutive_passes,
            game.quiet_moves,
            game.finished,
            game.no_progress_end,
            game.resumption_used,
            game.extension_used,
            tuple(game.extension_points),
            game.swap_decided,
            tuple((color, self.seats[color]) for color in (BLACK, WHITE)),
            tuple(sorted(self.end_acceptances)),
            self.end_decider,
            self.accepted,
        )

    def analysis_key(self):
        """Complete rules-state identity; old seeded `key()` stays unchanged."""
        game = self.game
        if hasattr(game, "repetition_key"):
            repetition = game.repetition_key()
            revision = game.rules_revision
        else:
            repetition = signature(game.board, game.state, game.to_move)
            revision = get_ruleset_spec(game.rules).revision
        return (
            "rules-analysis-v1", game.rules, revision, game.board.n, repetition,
            tuple(sorted(game.history, key=repr)), self._phase_key(),
            tuple(sorted(game.players.items())),
            getattr(game, "placements_played", None),
            getattr(game, "constructions_played", None),
        )

    def to_dict(self):
        """A game snapshot plus the seat identity/accepted-terminal envelope."""
        return self.game.to_dict() | {"rules_state": {
            "version": 1,
            "seats": dict(self.seats),
            "end_acceptances": sorted(self.end_acceptances),
            "end_decider": self.end_decider,
            "accepted": self.accepted,
        }}

    @classmethod
    def from_dict(cls, payload):
        from game_factory import load_game

        game = load_game(payload)
        raw = payload.get("rules_state")
        if raw is None:
            return cls(game)
        fields = {"version", "seats", "end_acceptances", "end_decider", "accepted"}
        if not isinstance(raw, dict) or set(raw) != fields:
            raise ValueError("invalid rules-state envelope")
        if type(raw["version"]) is not int or raw["version"] != 1:
            raise ValueError("unsupported rules-state envelope")
        seats = raw["seats"]
        if (
            not isinstance(seats, dict) or set(seats) != {BLACK, WHITE}
            or not all(isinstance(value, str) and value for value in seats.values())
            or len(set(seats.values())) != 2
        ):
            raise ValueError("invalid seat identities")
        acceptances = raw["end_acceptances"]
        if (
            not isinstance(acceptances, list)
            or not all(isinstance(seat, str) and seat in seats.values() for seat in acceptances)
            or len(set(acceptances)) != len(acceptances)
            or type(raw["accepted"]) is not bool
            or raw["end_decider"] not in (None, BLACK, WHITE)
        ):
            raise ValueError("invalid ending decisions")
        accepted, decider = raw["accepted"], raw["end_decider"]
        if not game.finished:
            if accepted or acceptances or decider is not None:
                raise ValueError("unfinished game cannot contain ending decisions")
        elif accepted:
            required = 1 if game.resumption_used or game.no_progress_end else 2
            if (
                len(acceptances) != required or decider is not None
                or (required == 1 and acceptances != [seats[game.to_move]])
            ):
                raise ValueError("terminal score lacks required seat acceptances")
        else:
            expected_decider = game.to_move
            if acceptances:
                if (
                    acceptances != [seats[game.to_move]]
                    or game.resumption_used or game.no_progress_end
                ):
                    raise ValueError("invalid acceptance sequence")
                expected_decider = other(game.to_move)
            if decider != expected_decider:
                raise ValueError("invalid pending end decision")
        return cls(
            game, seats=dict(seats), end_acceptances=set(acceptances),
            end_decider=decider, accepted=accepted,
        )


def legal_actions(state):
    """Enumerate every legal rules action in a stable order."""
    if state.terminal:
        return ()
    game = state.game
    if game.finished:
        actions = []
        if game.resumption_available:
            actions.append(RulesAction("resume"))
        actions.append(RulesAction("accept"))
        return tuple(actions)

    actions = []
    if game.swap_available:
        actions.append(RulesAction("swap"))
    actions.extend(
        RulesAction("extend", point)
        for point in game.extension_candidates()
    )
    if game.extension_only_turn:
        actions.append(RulesAction("finish-extension"))
    else:
        actions.extend(
            RulesAction("play", point) for point in game.legal_placements()
        )
        if game.moves_played > 0:
            actions.append(RulesAction("pass"))
        if hasattr(game, "construction_actions"):
            actions.extend(game.construction_actions())
    return tuple(actions)


def _apply_in_place(state, action, *, validate):
    if validate and action not in legal_actions(state):
        raise Illegal("action is not legal in this rules state")
    game = state.game
    if action.kind == "play":
        game.play(action.point)
        state.end_acceptances.clear()
        state.end_decider = game.to_move if game.finished else None
    elif action.kind in ("construct", "plant"):
        method = getattr(game, action.kind, None)
        if method is None:
            raise Illegal("construction is unavailable in this ruleset")
        method(action.point, action.orientation)
        state.end_acceptances.clear()
        state.end_decider = None
    elif action.kind == "pass":
        game.play_pass()
        state.end_decider = game.to_move if game.finished else None
    elif action.kind == "swap":
        game.take_over()
        state.seats[BLACK], state.seats[WHITE] = (
            state.seats[WHITE],
            state.seats[BLACK],
        )
    elif action.kind == "extend":
        game.play_extension(action.point)
        state.end_acceptances.clear()
    elif action.kind == "finish-extension":
        game.finish_extensions()
        state.end_acceptances.clear()
        state.end_decider = None
    elif action.kind == "resume":
        game.demand_resumption()
        state.end_acceptances.clear()
        state.end_decider = None
    elif action.kind == "accept":
        seat = state.actor_seat
        state.end_acceptances.add(seat)
        if game.resumption_used or game.no_progress_end:
            state.accepted = True
            state.end_decider = None
        else:
            other_color = other(state.end_decider)
            other_seat = state.seats[other_color]
            if other_seat in state.end_acceptances:
                state.accepted = True
                state.end_decider = None
            else:
                state.end_decider = other_color
    return state


def apply_action(state, action, *, copy=True, validate=True):
    """Apply a legal action, cloning by default so analysis is non-mutating."""
    target = state.clone() if copy else state
    return _apply_in_place(target, action, validate=validate)
