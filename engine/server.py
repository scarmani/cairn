"""Dependency-free local web server for Varde play and AI training."""

import argparse
from dataclasses import dataclass, replace
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from actions import RulesAction, RulesState
from game_factory import new_game
from lab_match import (
    LAB_ALIAS_ROUTES, action_from_alias, apply_lab_action, assert_lab_actor,
    attach_lab_state, is_lab_game, lab_catalog_entries, lab_computer_color,
    lab_computer_settings, lab_state, laboratory_public_view, validate_lab_profiles,
)
from lab_spec import LAB_REGISTRY, STATIC_CONTROL_REGISTRY
from varde import (
    BLACK, BREATH_RULESETS, EXTENSION_RULES, RULESETS,
    WHITE, Game, Illegal, get_ruleset_spec, groups_of, has_sky, other,
    rulesets_public,
)
from learning import LearningModel, TRAINING_BATCHES, TrainingService
from native_evaluators import native_evaluators_public
from opponent import BotDecision, choose_decision, greedy_decision
from profiles import (
    get_profile,
    normalize_computer_settings,
    profiles_public,
)


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
GAME_LOCK = threading.Lock()


def _seed(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("seed must be an integer")
    return value


@dataclass
class Seat:
    identity: str
    kind: str
    name: str
    difficulty: str | None = None
    profile: str | None = None
    seed: int = 1

    def to_dict(self):
        payload = {
            "identity": self.identity,
            "kind": self.kind,
            "name": self.name,
        }
        if self.kind == "computer":
            payload.update(
                {
                    "difficulty": self.difficulty,
                    "profile": self.profile,
                    "seed": self.seed,
                }
            )
        return payload

    @classmethod
    def from_dict(cls, payload, *, experimental=False):
        if not isinstance(payload, dict) or payload.get("kind") not in ("human", "computer"):
            raise ValueError("invalid match seat")
        if experimental:
            required = {"identity", "kind", "name"}
            if payload["kind"] == "computer":
                required.update(("difficulty", "seed"))
            if not required <= set(payload) <= required | {"profile"}:
                raise ValueError("invalid laboratory seat fields")
            if any(not isinstance(payload[key], str) or not payload[key]
                   or len(payload[key]) > 40 for key in ("identity", "name")):
                raise ValueError("invalid laboratory seat identity or name")
            if payload.get("profile") is not None:
                raise ValueError("laboratory opponents cannot use Classic or Personal profiles")
        difficulty = payload.get("difficulty", "standard")
        profile = payload.get("profile")
        if payload["kind"] == "computer":
            settings = lab_computer_settings if experimental else normalize_computer_settings
            difficulty, profile = settings(
                difficulty, profile
            )
        if payload["kind"] == "human":
            difficulty = None
            profile = None
        seed = payload.get("seed", 1)
        seed = _seed(seed)
        return cls(
            identity=str(payload.get("identity", payload.get("name", "Player")))[:40],
            kind=payload["kind"],
            name=str(payload.get("name", "Player"))[:40],
            difficulty=difficulty,
            profile=profile,
            seed=seed,
        )


@dataclass
class MatchConfig:
    mode: str = "hotseat"
    seats: dict | None = None
    explain: bool = True
    end_acceptances: set | None = None
    lab_state: RulesState | None = None

    def __post_init__(self):
        if self.seats is None:
            self.seats = {
                BLACK: Seat("player-1", "human", "Player 1"),
                WHITE: Seat("player-2", "human", "Player 2"),
            }
        if self.end_acceptances is None:
            self.end_acceptances = set()

    @property
    def end_decided(self):
        """Legacy compatibility view: every computer seat has accepted."""
        if self.lab_state is not None:
            return self.lab_state.accepted
        computers = {
            seat.identity for seat in self.seats.values() if seat.kind == "computer"
        }
        return bool(computers) and computers <= self.end_acceptances

    @end_decided.setter
    def end_decided(self, decided):
        if self.lab_state is not None:
            raise ValueError("laboratory ending state requires a shared rules action")
        if decided:
            self.end_acceptances = {
                seat.identity
                for seat in self.seats.values()
                if seat.kind == "computer"
            }
        else:
            self.end_acceptances.clear()

    @property
    def human_color(self):
        colors = [color for color, seat in self.seats.items() if seat.kind == "human"]
        return colors[0] if len(colors) == 1 else None

    @human_color.setter
    def human_color(self, color):
        if color not in (BLACK, WHITE) or self.computer_color is None:
            raise ValueError("human color is only available in a one-computer match")
        if self.human_color != color:
            self.swap_owners()

    @property
    def computer_color(self):
        colors = [color for color, seat in self.seats.items() if seat.kind == "computer"]
        return colors[0] if len(colors) == 1 else None

    @computer_color.setter
    def computer_color(self, color):
        if color not in (BLACK, WHITE) or self.computer_color is None:
            raise ValueError("computer color is only available in a one-computer match")
        if self.computer_color != color:
            self.swap_owners()

    @property
    def difficulty(self):
        color = self.computer_color
        return self.seats[color].difficulty if color else "standard"

    @property
    def profile(self):
        color = self.computer_color
        return self.seats[color].profile if color else None

    @property
    def seed(self):
        color = self.computer_color
        return self.seats[color].seed if color else 1

    @classmethod
    def from_new_game(cls, game, body):
        experimental = is_lab_game(game)
        if experimental:
            validate_lab_profiles(body)
        settings = lab_computer_settings if experimental else normalize_computer_settings
        mode = body.get("mode", "hotseat")
        if mode == "computer_vs_computer":
            mode = "watch"
        if mode not in ("hotseat", "computer", "watch"):
            raise ValueError("mode must be hotseat, computer, or watch")
        explain = body.get("explain", True)
        if not isinstance(explain, bool):
            raise ValueError("explain must be boolean")
        if mode == "hotseat":
            players = body.get("players", {})
            if players and (
                not isinstance(players, dict)
                or set(players) != {BLACK, WHITE}
                or not all(isinstance(name, str) and name for name in players.values())
            ):
                raise ValueError("players must contain non-empty B and W names")
            match = cls(mode="hotseat", explain=explain)
            if players:
                match.seats[BLACK].name = players[BLACK][:40]
                match.seats[WHITE].name = players[WHITE][:40]
        elif mode == "computer":
            human_color = body.get("human_color", BLACK)
            if human_color not in (BLACK, WHITE):
                raise ValueError("human_color must be B or W")
            difficulty, profile = settings(
                body.get("difficulty", "standard"), body.get("profile")
            )
            computer_color = other(human_color)
            seats = {
                human_color: Seat("human", "human", "You"),
                computer_color: Seat(
                    "computer",
                    "computer",
                    "Computer",
                    difficulty=difficulty,
                    profile=profile,
                    seed=_seed(body.get("seed", 1)),
                ),
            }
            match = cls(mode="computer", seats=seats, explain=explain)
        else:
            black_difficulty, black_profile = settings(
                body.get("black_difficulty", "standard"),
                body.get("black_profile"),
            )
            white_difficulty, white_profile = settings(
                body.get("white_difficulty", "standard"),
                body.get("white_profile"),
            )
            base_seed = _seed(body.get("seed", 1))
            match = cls(
                mode="watch",
                seats={
                    BLACK: Seat(
                        "computer-black",
                        "computer",
                        "Black AI",
                        difficulty=black_difficulty,
                        profile=black_profile,
                        seed=base_seed,
                    ),
                    WHITE: Seat(
                        "computer-white",
                        "computer",
                        "White AI",
                        difficulty=white_difficulty,
                        profile=white_profile,
                        seed=base_seed + 1,
                    ),
                },
                explain=explain,
            )
        match.sync_players(game)
        if experimental:
            attach_lab_state(game, match)
        return match

    @classmethod
    def from_snapshot(cls, payload):
        experimental = payload.get("version") == 2
        saved_match = payload.get("match")
        if experimental and (
            not isinstance(saved_match, dict)
            or set(saved_match) != {"mode", "seats", "explain", "end_decided", "end_acceptances"}
        ):
            raise ValueError("a complete laboratory match envelope is required")
        if saved_match is not None:
            if not isinstance(saved_match, dict):
                raise ValueError("invalid match configuration")
            mode = saved_match.get("mode", "hotseat")
            if mode not in ("hotseat", "computer", "watch"):
                raise ValueError("invalid match mode")
            raw_seats = saved_match.get("seats", {})
            if experimental and not isinstance(raw_seats, dict):
                raise ValueError("invalid laboratory match seats")
            if set(raw_seats) != {BLACK, WHITE}:
                raise ValueError("invalid match seats")
            explain = saved_match.get("explain", True)
            end_decided = saved_match.get("end_decided", False)
            if not isinstance(explain, bool) or not isinstance(end_decided, bool):
                raise ValueError("invalid match flags")
            seats = {
                color: Seat.from_dict(raw_seats[color], experimental=experimental)
                for color in (BLACK, WHITE)
            }
            identities = {seat.identity for seat in seats.values()}
            if len(identities) != 2:
                raise ValueError("match seat identities must be unique")
            raw_acceptances = saved_match.get("end_acceptances")
            if experimental and not isinstance(raw_acceptances, list):
                raise ValueError("laboratory end acceptances must be a list")
            if raw_acceptances is None:
                acceptances = (
                    {
                        seat.identity
                        for seat in seats.values()
                        if seat.kind == "computer"
                    }
                    if end_decided
                    else set()
                )
            elif (
                not isinstance(raw_acceptances, list)
                or any(not isinstance(item, str) for item in raw_acceptances)
            ):
                raise ValueError("invalid match end acceptances")
            else:
                acceptances = set(raw_acceptances)
                if len(acceptances) != len(raw_acceptances) or not acceptances <= identities:
                    raise ValueError("invalid match end acceptances")
            return cls(
                mode=mode,
                seats=seats,
                explain=explain,
                end_acceptances=acceptances,
            )
        legacy = payload.get("computer")
        if legacy is None:
            return cls()
        if not isinstance(legacy, dict) or not legacy.get("enabled", False):
            raise ValueError("invalid computer configuration")
        computer_color = legacy.get("color")
        if computer_color not in (BLACK, WHITE):
            raise ValueError("invalid legacy computer configuration")
        difficulty, profile = normalize_computer_settings(
            legacy.get("difficulty", "standard"), legacy.get("profile")
        )
        explain = legacy.get("explain", True)
        if not isinstance(explain, bool):
            raise ValueError("invalid legacy computer configuration")
        return cls(
            mode="computer",
            seats={
                other(computer_color): Seat("human", "human", "You"),
                computer_color: Seat(
                    "computer",
                    "computer",
                    "Computer",
                    difficulty=difficulty,
                    profile=profile,
                    seed=_seed(legacy.get("seed", 1)),
                ),
            },
            explain=explain,
        )

    def sync_players(self, game):
        game.players = {color: self.seats[color].name for color in (BLACK, WHITE)}

    def computer_can_act(self, game):
        if self.lab_state is not None:
            return lab_computer_color(game, self) is not None
        if game.finished:
            return self.next_computer_color(game) is not None
        return self.seats[game.to_move].kind == "computer"

    def next_computer_color(self, game):
        """Return the next computer seat owed an ending decision."""
        if self.lab_state is not None:
            return lab_computer_color(game, self)
        if not game.finished:
            return game.to_move if self.seats[game.to_move].kind == "computer" else None
        if game.no_progress_end:
            return None
        computers = [
            color
            for color in (game.to_move, other(game.to_move))
            if self.seats[color].kind == "computer"
        ]
        if game.resumption_used:
            return None if self.end_acceptances else (computers[0] if computers else None)
        for color in computers:
            if self.seats[color].identity not in self.end_acceptances:
                return color
        return None

    def accept_end(self, game, color):
        if self.lab_state is not None:
            raise ValueError("laboratory acceptance requires a shared rules action")
        if game.resumption_used:
            self.end_acceptances = {
                seat.identity
                for seat in self.seats.values()
                if seat.kind == "computer"
            }
        else:
            self.end_acceptances.add(self.seats[color].identity)

    def clear_end_acceptances(self):
        if self.lab_state is not None:
            raise ValueError("laboratory ending state requires a shared rules action")
        self.end_acceptances.clear()

    def swap_owners(self, game=None):
        self.seats[BLACK], self.seats[WHITE] = self.seats[WHITE], self.seats[BLACK]
        if game is not None:
            self.sync_players(game)

    def snapshot_data(self):
        return {
            "mode": self.mode,
            "seats": {color: self.seats[color].to_dict() for color in (BLACK, WHITE)},
            "explain": self.explain,
            "end_decided": self.end_decided,
            "end_acceptances": sorted(self.end_acceptances),
        }


MODEL = LearningModel.load()
TRAINER = TrainingService(MODEL)
GAME = Game(3)
MATCH = MatchConfig()
LAST_DECISION = None


def snapshot_payload(game, match):
    payload = lab_state(game, match).to_dict() if is_lab_game(game) else game.to_dict()
    payload["match"] = match.snapshot_data()
    return payload


def ruleset_catalog_public():
    payload = rulesets_public()
    native = native_evaluators_public()
    evaluator_revisions = {
        rules: spec["revision"]
        for rules, spec in native["evaluators"].items()
    }
    for ruleset in payload["rulesets"]:
        ruleset["native_evaluator_revision"] = evaluator_revisions.get(
            ruleset["id"]
        )
    payload["native_evaluators"] = {
        "format": native["format"],
        "version": native["version"],
        "hash": native["hash"],
    }
    payload["rulesets"].extend(lab_catalog_entries())
    return payload


def validate_ruleset_size(rules, n, *, public_new_game):
    if rules not in RULESETS:
        raise ValueError("rules must be one of: " + ", ".join(RULESETS))
    spec = get_ruleset_spec(rules)
    if public_new_game and not spec.public_new_game:
        reason = f": {spec.archival_reason}" if spec.archival_reason else ""
        raise ValueError(
            f"{spec.label} is {spec.status} and cannot start a new public game{reason}"
        )
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("board size must be an integer")
    if not spec.min_size <= n <= spec.max_size:
        raise ValueError(
            f"board size must be {spec.min_size}-{spec.max_size} for {rules}"
        )
    return spec


def load_snapshot(payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid Varde snapshot")
    if payload.get("version") == 2:
        if payload.get("rules") not in LAB_REGISTRY:
            raise ValueError("unsupported browser laboratory ruleset; static controls are research-only")
        if "rules_state" not in payload or "match" not in payload:
            raise ValueError("laboratory snapshots require rules-state and match envelopes")
        state = RulesState.from_dict(payload)
        game = state.game
        match = MatchConfig.from_snapshot(payload)
        attach_lab_state(game, match, state, saved_end_decided=payload["match"]["end_decided"])
        return game, match
    validate_ruleset_size(
        payload.get("rules", "classic"),
        payload.get("n"),
        public_new_game=False,
    )
    game = Game.from_dict(payload)
    match = MatchConfig.from_snapshot(payload)
    if "match" not in payload and "computer" not in payload:
        match.seats[BLACK].name = game.players[BLACK]
        match.seats[WHITE].name = game.players[WHITE]
    match.sync_players(game)
    return game, match


def _decision_payload(decision, explain):
    if decision is None:
        return None
    payload = decision.to_dict()
    payload.pop("score", None)
    if not explain:
        payload["reason_text"] = ""
    elif getattr(decision, "profile", None):
        label = get_profile(decision.profile).label
        payload["reason_text"] = f"{label}: {payload['reason_text']}"
    return payload


def public_view(game, match=None, last_decision=None):
    match = match or MatchConfig()
    if is_lab_game(game):
        return laboratory_public_view(
            game, match, decision=_decision_payload(last_decision, match.explain),
            learning=MODEL.status(),
        )
    legal = set() if game.finished else set(game.legal_placements())
    extensions = set(game.extension_candidates())
    board = game.board
    # Flat rulesets: annotate every stone with its group's liberty count
    # so the client can warn about imperiled groups.
    group_libs = {}
    if game.rules in BREATH_RULESETS:
        for color in (BLACK, WHITE):
            for comp in groups_of(board, game.state, color):
                libs = len({
                    nb
                    for q in comp
                    for nb in board.neighbors[q]
                    if not game.state[nb]
                })
                for q in comp:
                    group_libs[q] = libs
    points = [
        {
            "coord": list(point),
            "stack": list(game.state[point]),
            "rim": point in board.rim,
            "phantoms": board.phantoms[point],
            "deep": point in board.deep,
            "legal": point in legal,
            "extension": point in extensions,
            "sky": has_sky(board, game.state, point, None),
            "group_libs": group_libs.get(point),
            "segment": (
                [list(v) for v in board.segments[point]]
                if hasattr(board, "segments")
                else None
            ),
        }
        for point in board.points
    ]
    edges = [
        [list(point), list(neighbor)]
        for point in board.points
        for neighbor in board.neighbors[point]
        if point < neighbor
    ]
    return {
        "n": board.n,
        "rules": game.rules,
        "points": points,
        "edges": edges,
        "to_move": game.to_move,
        "current_player": game.current_player,
        "players": dict(game.players),
        "moves_played": game.moves_played,
        "consecutive_passes": game.consecutive_passes,
        "finished": game.finished,
        "no_progress_end": game.no_progress_end,
        "extension_only_turn": game.extension_only_turn,
        "resumption_available": game.resumption_available,
        "resumption_used": game.resumption_used,
        "swap_available": game.swap_available,
        "score": game.score(),
        "control": game.control_count(),
        "capture_waves": [[list(point) for point in wave] for wave in game.last_capture_waves],
        "match": {
            "mode": match.mode,
            "seats": {color: match.seats[color].to_dict() for color in (BLACK, WHITE)},
            "human_color": match.human_color,
            "computer_color": match.computer_color,
            "difficulty": match.difficulty,
            "profile": match.profile,
            "explain": match.explain,
            "computer_turn": not game.finished and match.seats[game.to_move].kind == "computer",
            "computer_can_act": match.computer_can_act(game),
            "pending_end_deciders": (
                [match.next_computer_color(game)]
                if game.finished and match.next_computer_color(game)
                else []
            ),
            "end_acceptances": sorted(match.end_acceptances),
        },
        "learning": MODEL.status(),
        "computer_decision": _decision_payload(last_decision, match.explain),
    }


def assert_human_action(game, match):
    if is_lab_game(game):
        assert_lab_actor(game, match, "human")
        return
    if game.finished:
        if not any(seat.kind == "human" for seat in match.seats.values()):
            raise Illegal("no human player is seated in this match")
        return
    if not game.finished and match.seats[game.to_move].kind != "human":
        raise Illegal("wait for the computer's move")


def computer_take_extensions(game):
    """Take free extensions per the ruleset's economics.

    When a normal move still follows, extensions are pure gain: take
    them all. When extensions replace the move, rescue only if at
    least two stones are imperiled — a lone stone is cheaper to lose
    than a tempo.
    """
    spec = EXTENSION_RULES.get(game.rules)
    if spec is None:
        return
    if not spec["after_move"]:
        imperiled = 0
        for comp in groups_of(game.board, game.state, game.to_move):
            libs = {
                nb
                for q in comp
                for nb in game.board.neighbors[q]
                if not game.state[nb]
            }
            if len(libs) == 1:
                imperiled += len(comp)
        if imperiled < 2:
            return
    mover = game.to_move
    while True:
        candidates = game.extension_candidates()
        if not candidates:
            return False
        game.play_extension(candidates[0])
        if game.to_move != mover:
            return True


def apply_computer_action(game, match, model=None):
    if is_lab_game(game):
        assert_lab_actor(game, match, "computer")
        raise Illegal("laboratory computer opponent is not yet available")
    if not match.computer_can_act(game):
        raise Illegal("it is not the computer's turn")
    color = match.next_computer_color(game) if game.finished else game.to_move
    if color is None:
        raise Illegal("it is not the computer's turn")
    seat = match.seats[color]
    if seat.kind != "computer" and not game.finished:
        raise Illegal("it is not the computer's turn")
    selected_profile = get_profile(seat.profile)
    active_model = MODEL if model is None else model
    extension_finished = False
    if not game.finished:
        extension_finished = computer_take_extensions(game)
    if extension_finished:
        return BotDecision(
            action="extend",
            reason_code="extend",
            reason_text="Rescued an imperiled group until its run ended.",
            profile=seat.profile,
        )
    if game.extension_only_turn:
        game.finish_extensions()
        return BotDecision(
            action="extend",
            reason_code="extend",
            reason_text="Rescued imperiled groups with free extensions.",
            profile=seat.profile,
        )
    if seat.profile in ("attacker", "defender") and not game.finished:
        decision = greedy_decision(
            game, color, seat.profile, seed=seat.seed
        )
    else:
        decision = choose_decision(
            game,
            color,
            difficulty=seat.difficulty,
            seed=seat.seed,
            model=active_model if seat.profile == "personal" else None,
            weights=selected_profile.weights,
        )
    decision = replace(decision, profile=seat.profile)
    if decision.action == "play":
        game.play(decision.point)
    elif decision.action == "pass":
        game.play_pass()
    elif decision.action == "swap":
        game.take_over()
        match.swap_owners(game)
    elif decision.action == "resume":
        game.demand_resumption()
        match.clear_end_acceptances()
    elif decision.action == "accept":
        match.accept_end(game, color)
    else:
        raise ValueError("unsupported computer action")
    return decision


class VardeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _json(self, payload, status=200):
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON body") from exc

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/api/training":
            self._json(TRAINER.status())
            return
        if route == "/api/profiles":
            self._json(profiles_public(MODEL.status()))
            return
        if route == "/api/rulesets":
            self._json(ruleset_catalog_public())
            return
        if route == "/api/state":
            with GAME_LOCK:
                self._json(public_view(GAME, MATCH, LAST_DECISION))
            return
        if route == "/api/snapshot":
            with GAME_LOCK:
                self._json(snapshot_payload(GAME, MATCH))
            return
        super().do_GET()

    def do_POST(self):
        global GAME, MATCH, LAST_DECISION
        route = urlparse(self.path).path
        try:
            body = self._body()
            if not isinstance(body, dict):
                raise ValueError("JSON request body must be an object")
            if route.startswith("/api/training/"):
                if route == "/api/training/start":
                    games = body.get("games", 10)
                    if isinstance(games, bool) or not isinstance(games, int):
                        raise ValueError("training games must be 10, 50, or 200")
                    if games not in TRAINING_BATCHES:
                        raise ValueError("training games must be 10, 50, or 200")
                    training_seed = (
                        _seed(body["seed"]) if "seed" in body else None
                    )
                    TRAINER.start(games, training_seed)
                elif route == "/api/training/cancel":
                    TRAINER.cancel()
                elif route == "/api/training/reset":
                    TRAINER.reset()
                else:
                    self._json({"error": "unknown training route"}, 404)
                    return
                self._json(TRAINER.status())
                return
            with GAME_LOCK:
                if route == "/api/new":
                    raw_n = body.get("n", 3)
                    rules = body.get("rules", "classic")
                    experimental = body.get("experimental", False)
                    if type(experimental) is not bool:
                        raise ValueError("experimental must be boolean")
                    if rules in STATIC_CONTROL_REGISTRY:
                        raise ValueError("static controls are research-only")
                    if rules in LAB_REGISTRY:
                        game = new_game(raw_n, rules=rules, experimental=experimental)
                    else:
                        if isinstance(raw_n, bool):
                            raise ValueError("board size must be an integer")
                        n = int(raw_n)
                        validate_ruleset_size(rules, n, public_new_game=True)
                        game = Game(n, rules=rules)
                    match = MatchConfig.from_new_game(game, body)
                    GAME, MATCH = game, match
                    LAST_DECISION = None
                elif route == "/api/action":
                    if not is_lab_game(GAME):
                        raise Illegal("structured laboratory actions require an experimental game")
                    apply_lab_action(GAME, MATCH, RulesAction.from_dict(body))
                    LAST_DECISION = None
                elif is_lab_game(GAME) and route in LAB_ALIAS_ROUTES:
                    apply_lab_action(GAME, MATCH, action_from_alias(route, body))
                    LAST_DECISION = None
                elif route == "/api/play":
                    assert_human_action(GAME, MATCH)
                    raw = body.get("point")
                    if not isinstance(raw, list) or len(raw) != 2:
                        raise ValueError("point must be [x,y]")
                    point = (int(raw[0]), int(raw[1]))
                    if point not in GAME.state:
                        raise ValueError("point is off board")
                    GAME.play(point)
                    MATCH.clear_end_acceptances()
                elif route == "/api/extend":
                    assert_human_action(GAME, MATCH)
                    raw = body.get("point")
                    if not isinstance(raw, list) or len(raw) != 2:
                        raise ValueError("point must be [x,y]")
                    point = (int(raw[0]), int(raw[1]))
                    if point not in GAME.state:
                        raise ValueError("point is off board")
                    GAME.play_extension(point)
                    MATCH.clear_end_acceptances()
                elif route == "/api/finish-extensions":
                    assert_human_action(GAME, MATCH)
                    GAME.finish_extensions()
                    MATCH.clear_end_acceptances()
                elif route == "/api/pass":
                    assert_human_action(GAME, MATCH)
                    GAME.play_pass()
                elif route == "/api/swap":
                    assert_human_action(GAME, MATCH)
                    GAME.take_over()
                    MATCH.swap_owners(GAME)
                elif route == "/api/resume":
                    assert_human_action(GAME, MATCH)
                    GAME.demand_resumption()
                    MATCH.clear_end_acceptances()
                elif route == "/api/computer":
                    LAST_DECISION = apply_computer_action(GAME, MATCH)
                elif route == "/api/load":
                    loaded_game, loaded_match = load_snapshot(body)
                    GAME, MATCH = loaded_game, loaded_match
                    LAST_DECISION = None
                else:
                    self._json({"error": "unknown API route"}, 404)
                    return
                self._json(public_view(GAME, MATCH, LAST_DECISION))
        except (Illegal, ValueError, TypeError) as exc:
            self._json({"error": str(exc)}, 400)

    def log_message(self, format, *args):
        print(f"[varde] {self.address_string()} {format % args}")


def main():
    parser = argparse.ArgumentParser(description="Run the local Varde web game")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), VardeHandler)
    print(f"Varde ready at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
