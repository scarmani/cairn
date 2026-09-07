"""Strict local lab-record shapes and mechanical shared-action replay.

Version-1 human-study records are deliberately not accepted or modified here.
No server, opponent or Personal model is imported. CLI reads one local file and
prints a separate verification report; it never stores or submits a record.
"""

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[2] / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from actions import RulesAction, RulesState, apply_action  # noqa: E402
from game_factory import new_game  # noqa: E402
from lab_spec import LAB_REGISTRY  # noqa: E402
from varde import Illegal  # noqa: E402


FORMAT = "varde-lab-playtest"
VERSION = 2
MAX_INTEGER = 2**53 - 1
SEATS = {"S1", "S2"}
COLORS = {"B", "W"}
TOP_FIELDS = {"format", "version", "source", "session_id", "rules", "board_size",
              "catalog_version", "initial_seats", "status", "actions", "final_score"}
ROW_FIELDS = {"index", "action", "actor", "elapsed_ms", "captures", "after"}
AFTER_FIELDS = {"to_move", "actor_color", "actor_seat", "seats", "end_acceptances",
                "finished", "accepted", "resumption_used", "consecutive_passes", "swap_available",
                "moves_played", "placements_played", "constructions_played", "topology", "score", "original_control"}
CONSTRUCTION = {"junction-y": ("construct", 2), "junction-six": ("construct", 1),
                "junction-planted": ("plant", 2), "junction-passage": ("construct", 3)}
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _detached_json_numbers(value):
    """Match parsed JS Number semantics without relaxing engine action parsing."""
    if type(value) is float:
        if not math.isfinite(value) or not value.is_integer() or abs(value) > MAX_INTEGER:
            raise ValueError("record numbers must be finite safe integers")
        return int(value)
    if type(value) is dict:
        return {key: _detached_json_numbers(item) for key, item in value.items()}
    if type(value) is list:
        return [_detached_json_numbers(item) for item in value]
    # Booleans remain booleans: an integer field must still reject them.
    return deepcopy(value)


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"invalid {label} fields")


def _integer(value, label, *, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_INTEGER:
        raise ValueError(f"invalid {label} integer")


def _point(value):
    if type(value) is not list or len(value) != 2:
        raise ValueError("invalid coordinate")
    for coordinate in value:
        _integer(coordinate, "coordinate", minimum=-MAX_INTEGER)


def _score(value, label):
    _fields(value, COLORS, label)
    for score in value.values():
        _integer(score, label, minimum=-MAX_INTEGER if label == "score" else 0)


def _seats(value):
    _fields(value, COLORS, "seats")
    if any(type(seat) is not str for seat in value.values()) or set(value.values()) != SEATS:
        raise ValueError("only bijective S1/S2 neutral seats are allowed")


def _action(value, rules):
    parsed = RulesAction.from_dict(value)
    kind = parsed.kind
    if kind in ("construct", "plant"):
        expected, count = CONSTRUCTION.get(rules, (None, 0))
        if kind != expected or parsed.orientation >= count:
            raise ValueError("action or orientation unavailable for these rules")
    elif kind not in ("play", "pass", "swap", "accept", "resume"):
        raise ValueError("unsupported lab record action")
    if parsed.point is not None:
        _point(value["face" if kind in ("construct", "plant") else "point"])
    return parsed


def _after(value, rules):
    _fields(value, AFTER_FIELDS, "after projection")
    _seats(value["seats"])
    if type(value["to_move"]) is not str or value["to_move"] not in COLORS:
        raise ValueError("invalid next color")
    for key in ("finished", "accepted", "resumption_used", "swap_available"):
        if type(value[key]) is not bool:
            raise ValueError(f"invalid {key} flag")
    for key in ("consecutive_passes", "moves_played", "placements_played", "constructions_played"):
        _integer(value[key], key)
    if value["consecutive_passes"] > 2 or value["finished"] != (value["consecutive_passes"] == 2):
        raise ValueError("inconsistent ending/pass projection")
    accepts = value["end_acceptances"]
    if (type(accepts) is not list or any(type(seat) is not str or seat not in SEATS for seat in accepts)
            or accepts != sorted(set(accepts))):
        raise ValueError("invalid neutral acceptance list")
    if value["accepted"]:
        if not value["finished"] or value["actor_color"] is not None or value["actor_seat"] is not None:
            raise ValueError("accepted state must have no next actor")
        if len(accepts) != (1 if value["resumption_used"] else 2):
            raise ValueError("invalid terminal acceptance count")
    else:
        color = value["actor_color"]
        if type(color) is not str or color not in COLORS or value["actor_seat"] != value["seats"][color]:
            raise ValueError("invalid acting neutral seat")
        if not value["finished"] and (accepts or color != value["to_move"]):
            raise ValueError("invalid live actor or acceptance")
        if value["finished"] and len(accepts) > 1:
            raise ValueError("too many pending acceptances")
    topology = value["topology"]
    if type(topology) is not list:
        raise ValueError("invalid topology")
    count = CONSTRUCTION.get(rules, (None, 0))[1]
    faces = set()
    for row in topology:
        if type(row) is not list or len(row) != 3:
            raise ValueError("invalid topology row")
        _point(row[:2])
        _integer(row[2], "orientation")
        if row[2] >= count or tuple(row[:2]) in faces:
            raise ValueError("invalid or duplicate topology face")
        faces.add(tuple(row[:2]))
    if topology != sorted(topology) or len(topology) != value["constructions_played"]:
        raise ValueError("noncanonical topology or construction count")
    _score(value["score"], "score")
    _score(value["original_control"], "original control")


def _captures(value):
    _fields(value, {"original", "junction", "waves"}, "captures")
    _integer(value["original"], "original captures")
    _integer(value["junction"], "junction captures")
    if type(value["waves"]) is not list:
        raise ValueError("invalid capture waves")
    seen = set()
    for wave in value["waves"]:
        if type(wave) is not list or not wave:
            raise ValueError("invalid empty capture wave")
        for point in wave:
            _point(point)
            if tuple(point) in seen:
                raise ValueError("duplicate captured coordinate")
            seen.add(tuple(point))
        if wave != sorted(wave):
            raise ValueError("capture wave points must be canonical")
    if len(seen) != value["original"] + value["junction"]:
        raise ValueError("capture totals and wave coordinates differ")


def validate_lab_record_shape(record):
    """Return detached strict structural data, not a mechanical certificate."""
    record = _detached_json_numbers(record)
    _fields(record, TOP_FIELDS, "lab record")
    if record["format"] != FORMAT or type(record["version"]) is not int or record["version"] != VERSION:
        raise ValueError("unsupported lab record")
    if record["source"] != "browser-local-hotseat" or not isinstance(record["session_id"], str) or not UUID.fullmatch(record["session_id"]):
        raise ValueError("invalid local source or UUID")
    _fields(record["rules"], {"id", "revision"}, "rules")
    rules = record["rules"]["id"]
    if not isinstance(rules, str) or rules not in LAB_REGISTRY or record["rules"]["revision"] != "0.1":
        raise ValueError("unsupported lab rules/revision")
    _integer(record["board_size"], "board size")
    if record["board_size"] not in (3, 4, 5, 6):
        raise ValueError("unsupported lab board size")
    _integer(record["catalog_version"], "catalog version", minimum=1)
    _seats(record["initial_seats"])
    if record["initial_seats"] != {"B": "S1", "W": "S2"}:
        raise ValueError("initial neutral seats must be B:S1/W:S2")
    if record["status"] not in ("active", "complete") or type(record["actions"]) is not list:
        raise ValueError("invalid record status or action list")
    previous = None
    seats = record["initial_seats"]
    counters = {"moves_played": 0, "placements_played": 0, "constructions_played": 0}
    for index, row in enumerate(record["actions"]):
        _fields(row, ROW_FIELDS, "action row")
        _integer(row["index"], "action index")
        if row["index"] != index:
            raise ValueError("nonsequential action index")
        action = _action(row["action"], rules)
        _fields(row["actor"], {"seat", "color"}, "actor")
        expected_actor = {"seat": "S1", "color": "B"} if previous is None else {
            "seat": previous["actor_seat"], "color": previous["actor_color"]}
        if row["actor"] != expected_actor or expected_actor["seat"] is None:
            raise ValueError("action actor differs from recorded predecessor")
        if index == 0 and action.kind != "play":
            raise ValueError("first action must be original placement")
        _integer(row["elapsed_ms"], "elapsed time")
        _captures(row["captures"])
        if action.kind not in ("play", "plant") and row["captures"] != {"original": 0, "junction": 0, "waves": []}:
            raise ValueError("administrative or empty construction action cannot capture")
        after = row["after"]
        _after(after, rules)
        expected_seats = {"B": seats["W"], "W": seats["B"]} if action.kind == "swap" else seats
        if after["seats"] != expected_seats:
            raise ValueError("unexplained neutral seat reassignment")
        deltas = {"moves_played": int(action.kind in ("play", "plant", "construct", "pass")),
                  "placements_played": int(action.kind in ("play", "plant")),
                  "constructions_played": int(action.kind in ("construct", "plant"))}
        for key in counters:
            counters[key] += deltas[key]
            if after[key] != counters[key]:
                raise ValueError("action/counter structure differs")
        seats, previous = after["seats"], after
    complete = previous is not None and previous["accepted"]
    if (record["status"] == "complete") != complete:
        raise ValueError("completion requires accepted terminal")
    if complete:
        _score(record["final_score"], "score")
        if record["final_score"] != previous["score"]:
            raise ValueError("final score differs from last accepted score")
    elif record["final_score"] is not None:
        raise ValueError("active record cannot have final score")
    return deepcopy(record)


def _projection(state):
    game = state.game
    return {"to_move": game.to_move, "actor_color": state.actor_color, "actor_seat": state.actor_seat,
            "seats": dict(state.seats), "end_acceptances": sorted(state.end_acceptances),
            "finished": game.finished, "accepted": state.accepted, "resumption_used": game.resumption_used,
            "consecutive_passes": game.consecutive_passes, "swap_available": game.swap_available,
            "moves_played": game.moves_played, "placements_played": game.placements_played,
            "constructions_played": game.constructions_played,
            "topology": [list(row) for row in game.topology], "score": game.score(),
            "original_control": game.original_control_count()}


def _capture_projection(before, after, action):
    original = frozenset(getattr(before.game.board, "original_points", before.game.board.points))
    removed = {point for point, stack in before.game.state.items() if stack and not after.game.state.get(point)}
    waves = after.game.last_capture_waves if action.kind in ("play", "plant") else []
    return {"original": len(removed & original), "junction": len(removed - original),
            "waves": [[list(point) for point in sorted(wave)] for wave in waves]}


@dataclass(frozen=True)
class LabRecordReplay:
    action_count: int
    accepted: bool
    replay_hash: str
    mechanically_verified: bool = True

    def to_dict(self):
        return {"format": "varde-lab-record-replay", "version": 1,
                "mechanically_verified": self.mechanically_verified, "action_count": self.action_count,
                "accepted": self.accepted, "replay_hash": self.replay_hash,
                "claim_limit": "mechanical replay only; not a qualified human study or game-quality finding"}


def replay_lab_record(record):
    record = validate_lab_record_shape(record)
    game = new_game(record["board_size"], rules=record["rules"]["id"], experimental=True)
    game.players = {"B": "S1", "W": "S2"}
    state = RulesState(game, seats=dict(record["initial_seats"]))
    for row in record["actions"]:
        index = row["index"]
        if row["actor"] != {"seat": state.actor_seat, "color": state.actor_color}:
            raise ValueError(f"action {index}: actor mismatch")
        action = RulesAction.from_dict(row["action"])
        before = state
        try:
            state = apply_action(state, action)
        except (Illegal, ValueError, RuntimeError) as error:
            raise ValueError(f"action {index}: illegal recorded transition") from error
        if row["after"] != _projection(state):
            raise ValueError(f"action {index}: replayed state/telemetry mismatch")
        if row["captures"] != _capture_projection(before, state, action):
            raise ValueError(f"action {index}: replayed captures mismatch")
    semantic = {"rules": record["rules"], "board_size": record["board_size"],
                "actions": [row["action"] for row in record["actions"]], "state": state.to_dict()}
    digest = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return LabRecordReplay(len(record["actions"]), state.accepted, digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="local version-2 lab record JSON")
    args = parser.parse_args()
    try:
        with args.input.open() as stream:
            record = json.load(stream)
        result = replay_lab_record(record)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result.to_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
