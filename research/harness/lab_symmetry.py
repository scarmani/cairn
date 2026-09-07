"""Conservative spatial corpus deduplication, never a gameplay/search key.

Includes actual current and fixed-initial edges, scoring/original points, cell
boundaries, permanent hub spokes, ordered stone columns, and actor/seat/ending/
extension phase. Ignores forbidden history, journal order, ordinary move and
placement/construction counts, seed labels, player display names and capture
animation. Opening eligibility and pass/quiet-ending counters remain phases.
Distinct strategic histories may deliberately collide. Full-history analysis
keys and origin fingerprints MUST remain separate. No color interchange,
reachability, source identity, optimality, or proof claim is made here.
"""

import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
for directory in (REPOSITORY, REPOSITORY / "engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from actions import RulesState  # noqa: E402
from lab_graph import GraphBoard, graph_board  # noqa: E402
from lab_spec import EXPERIMENT_REGISTRY  # noqa: E402
from varde import get_ruleset_spec  # noqa: E402
from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402

D6 = tuple(range(12))
LEGACY_RULESETS = ("classic", "rosette", "breath", "breath-run", "gjerde", "gjerde-go")
RULESETS = LEGACY_RULESETS + tuple(EXPERIMENT_REGISTRY)
FORMAT = "varde-lab-diagram"
VERSION = 1
TOP_FIELDS = {"format", "version", "rules_id", "rules_revision", "board_size", "geometry",
              "current_graph", "initial_graph", "stones", "phase"}
GRAPH_FIELDS = {"points", "edges", "original_points", "scoring_points", "rim", "phantoms", "cells", "topology"}
PHASE_FIELDS = {"to_move", "actor_color", "actor_seat", "seats", "end_decider", "accepted",
                "end_acceptances", "consecutive_passes", "quiet_moves", "finished", "no_progress_end",
                "resumption_used", "swap_decided", "opening_phase", "extension_used", "extension_points"}


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"invalid {label} fields")


def _point(point):
    if (type(point) not in (list, tuple) or len(point) != 2
            or any(type(value) is not int for value in point)):
        raise ValueError("coordinates must be exact integer pairs")
    x, y = point
    if (x + y) % 2:
        raise ValueError("coordinate is outside the integer honeycomb embedding")
    return x, y


def transform_coordinate(point, symmetry):
    """R^k for IDs0..5; R^k after reflection(x,-y) for IDs6..11."""
    if type(symmetry) is not int or symmetry not in D6:
        raise ValueError("spatial symmetry must be an integer from zero through eleven")
    x, y = _point(point)
    if symmetry >= 6:
        y = -y
    for _ in range(symmetry % 6):
        a, b = x - 3 * y, x + y
        if a % 2 or b % 2:
            raise ValueError("rotation is not exactly integral")
        x, y = a // 2, b // 2
    return x, y


def _wire_point(value):
    if type(value) is not list:
        raise ValueError("diagram coordinates must be JSON arrays")
    return _point(value)


def _points(value, label, *, universe=None, ordered=False):
    if type(value) is not list:
        raise ValueError(f"{label} must be a list")
    points = [_wire_point(point) for point in value]
    if len(set(points)) != len(points) or universe is not None and not set(points) <= universe:
        raise ValueError(f"duplicate or absent {label}")
    return [list(point) for point in (points if ordered else sorted(points))]


def _spec(rules):
    if type(rules) is not str or rules not in RULESETS:
        raise ValueError("unsupported frozen diagram ruleset")
    return EXPERIMENT_REGISTRY[rules] if rules in EXPERIMENT_REGISTRY else get_ruleset_spec(rules)


def _graph(value):
    _fields(value, GRAPH_FIELDS, "diagram graph")
    result = {"points": _points(value["points"], "graph points")}
    universe = set(map(tuple, result["points"]))
    if not universe:
        raise ValueError("diagram graph must not be empty")
    for name in ("original_points", "scoring_points", "rim"):
        result[name] = _points(value[name], name, universe=universe)
    originals = set(map(tuple, result["original_points"]))
    if not set(map(tuple, result["scoring_points"])) <= originals:
        raise ValueError("zero-point hubs cannot be scoring originals")
    if type(value["edges"]) is not list:
        raise ValueError("edges must be a list")
    edges = []
    neighbors = {point: set() for point in universe}
    for edge in value["edges"]:
        if type(edge) is not list or len(edge) != 2:
            raise ValueError("edges require two distinct endpoints")
        points = _points(edge, "edge endpoints", universe=universe)
        a, b = map(tuple, points)
        neighbors[a].add(b)
        neighbors[b].add(a)
        edges.append((a, b))
    if len(set(edges)) != len(edges):
        raise ValueError("duplicate undirected edge")
    result["edges"] = [[list(a), list(b)] for a, b in sorted(edges)]
    if type(value["phantoms"]) is not list:
        raise ValueError("phantom counts must be a list")
    counts = {}
    for row in value["phantoms"]:
        _fields(row, {"point", "count"}, "phantom count")
        point = _wire_point(row["point"])
        if point in counts or point not in universe or type(row["count"]) is not int or row["count"] < 0:
            raise ValueError("invalid phantom count")
        counts[point] = row["count"]
    if set(counts) != universe:
        raise ValueError("phantom counts must cover every graph point")
    result["phantoms"] = [{"point": list(point), "count": counts[point]} for point in sorted(counts)]
    for field, row_fields, neighbor_field in (("cells", {"center", "boundary"}, "boundary"),
                                             ("topology", {"center", "neighbors"}, "neighbors")):
        if type(value[field]) is not list:
            raise ValueError(f"{field} must be a list")
        rows = {}
        for row in value[field]:
            _fields(row, row_fields, field)
            center = _wire_point(row["center"])
            points = _points(row[neighbor_field], neighbor_field, universe=universe)
            if center in rows:
                raise ValueError(f"duplicate {field} center")
            if field == "cells" and len(points) != 6:
                raise ValueError("a hexagonal cell must retain six boundary lines")
            if field == "topology" and (center not in universe - originals or
                                        set(map(tuple, points)) != neighbors[center]):
                raise ValueError("topology must retain the actual hub spokes")
            rows[center] = points
        if field == "topology" and set(rows) != universe - originals:
            raise ValueError("every zero-point center must have topology metadata")
        result[field] = [{"center": list(center), neighbor_field: rows[center]} for center in sorted(rows)]
    return result


def _phase(value, universe):
    _fields(value, PHASE_FIELDS, "diagram phase")
    for flag in ("accepted", "finished", "no_progress_end", "resumption_used", "swap_decided", "extension_used"):
        if type(value[flag]) is not bool:
            raise ValueError("phase flags must be exact Booleans")
    for count in ("consecutive_passes", "quiet_moves"):
        if type(value[count]) is not int or value[count] < 0:
            raise ValueError("phase counters must be nonnegative integers")
    seats = value["seats"]
    if (type(seats) is not dict or set(seats) != {"B", "W"}
            or any(type(seat) is not str or not seat for seat in seats.values())
            or len(set(seats.values())) != 2):
        raise ValueError("invalid diagram seats")
    if type(value["to_move"]) is not str or value["to_move"] not in ("B", "W"):
        raise ValueError("invalid next color")
    for field in ("actor_color", "end_decider"):
        if value[field] is not None and (type(value[field]) is not str or value[field] not in ("B", "W")):
            raise ValueError("invalid actor/ending color")
    actor = None if value["accepted"] else value["end_decider"] if value["finished"] else value["to_move"]
    if value["actor_color"] != actor or value["actor_seat"] != (seats[actor] if actor else None):
        raise ValueError("diagram actor contradicts ending/seat phase")
    acceptances = value["end_acceptances"]
    if (type(acceptances) is not list or any(type(seat) is not str or seat not in seats.values() for seat in acceptances)
            or len(set(acceptances)) != len(acceptances)):
        raise ValueError("invalid ending acceptance identities")
    if not value["finished"]:
        if value["accepted"] or acceptances or value["end_decider"] is not None:
            raise ValueError("unfinished diagram contains ending decisions")
    elif value["accepted"]:
        needed = 1 if value["resumption_used"] or value["no_progress_end"] else 2
        if len(acceptances) != needed or value["end_decider"] is not None or needed == 1 and acceptances != [seats[value["to_move"]]]:
            raise ValueError("accepted diagram lacks required seat decisions")
    else:
        expected = value["to_move"]
        if acceptances:
            if acceptances != [seats[expected]] or value["resumption_used"] or value["no_progress_end"]:
                raise ValueError("invalid first acceptance phase")
            expected = "W" if expected == "B" else "B"
        if value["end_decider"] != expected:
            raise ValueError("invalid pending ending actor")
    if type(value["opening_phase"]) is not str or value["opening_phase"] not in ("unopened", "pie-window", "ordinary"):
        raise ValueError("invalid opening phase")
    result = json.loads(canonical_json(value))
    result["end_acceptances"] = sorted(acceptances)
    result["extension_points"] = _points(value["extension_points"], "extension points", universe=universe, ordered=True)
    return result


def _projection(value):
    _fields(value, TOP_FIELDS, "diagram projection")
    canonical_json(value)
    spec = _spec(value["rules_id"])
    if (value["format"] != FORMAT or type(value["version"]) is not int or value["version"] != VERSION
            or value["rules_revision"] != spec.revision or value["geometry"] != spec.geometry
            or type(value["board_size"]) is not int or value["board_size"] not in (3, 4, 5, 6)):
        raise ValueError("unsupported diagram specification")
    current, initial = _graph(value["current_graph"]), _graph(value["initial_graph"])
    universe = set(map(tuple, current["points"]))
    if (not set(map(tuple, initial["points"])) <= universe
            or current["original_points"] != initial["original_points"]
            or current["scoring_points"] != initial["scoring_points"]
            or not {canonical_json(edge) for edge in initial["edges"]} <= {canonical_json(edge) for edge in current["edges"]}
            or not {canonical_json(row) for row in initial["topology"]} <= {canonical_json(row) for row in current["topology"]}):
        raise ValueError("initial geometry must remain part of the permanent current graph")
    if type(value["stones"]) is not list:
        raise ValueError("stone columns must be a list")
    stones = {}
    for row in value["stones"]:
        _fields(row, {"point", "column"}, "stone column")
        point = _wire_point(row["point"])
        column = row["column"]
        if (point in stones or point not in universe or type(column) is not list
                or any(type(color) is not str or color not in ("B", "W") for color in column)):
            raise ValueError("invalid or duplicate stone column")
        stones[point] = list(column)
    if set(stones) != universe:
        raise ValueError("columns must cover every actual graph point")
    return {"format": FORMAT, "version": VERSION, "rules_id": spec.id, "rules_revision": spec.revision,
            "board_size": value["board_size"], "geometry": spec.geometry,
            "current_graph": current, "initial_graph": initial,
            "stones": [{"point": list(point), "column": stones[point]} for point in sorted(stones)],
            "phase": _phase(value["phase"], universe)}


def _board_projection(board, rules_id):
    points = list(board.points)
    universe = set(points)
    if len(universe) != len(points) or set(board.neighbors) != universe:
        raise ValueError("actual graph point/neighbor domain mismatch")
    edges = set()
    for point in points:
        adjacent = tuple(board.neighbors[point])
        if len(set(adjacent)) != len(adjacent):
            raise ValueError("duplicate actual adjacency")
        for neighbor in adjacent:
            if neighbor not in universe or point not in board.neighbors[neighbor] or point == neighbor:
                raise ValueError("actual graph adjacency must be simple and undirected")
            edges.add(tuple(sorted((point, neighbor))))
    originals = set(getattr(board, "original_points", points))
    scoring = set(getattr(board, "scoring_points", originals))
    if rules_id in ("gjerde", "gjerde-go", "gjerde-majority"):
        scoring = set()
    return {"points": [list(p) for p in points], "edges": [[list(a), list(b)] for a, b in sorted(edges)],
            "original_points": [list(p) for p in sorted(originals)], "scoring_points": [list(p) for p in sorted(scoring)],
            "rim": [list(p) for p in sorted(board.rim)],
            "phantoms": [{"point": list(p), "count": board.phantoms[p]} for p in points],
            "cells": [{"center": [6 * q, 4 * r + 2 * q], "boundary": [list(p) for p in boundaries]}
                      for (q, r), boundaries in sorted(getattr(board, "cell_edges", {}).items())],
            "topology": [{"center": list(p), "neighbors": [list(q) for q in board.neighbors[p]]}
                         for p in sorted(universe - originals)]}


def diagram_projection(state):
    """Read geometry/snapshot only; produce no successor or playable state."""
    if not isinstance(state, RulesState):
        raise ValueError("production RulesState required")
    game = state.game
    spec = _spec(game.rules)
    if (type(state.seats) is not dict or set(state.seats) != {"B", "W"}
            or any(type(seat) is not str or not seat for seat in state.seats.values())
            or len(set(state.seats.values())) != 2
            or type(game.to_move) is not str or game.to_move not in ("B", "W")
            or state.end_decider is not None and (type(state.end_decider) is not str or state.end_decider not in ("B", "W"))):
        raise ValueError("malformed production actor or seat envelope")
    if (set(game.state) != set(game.board.points)
            or any(type(column) not in (tuple, list) for column in game.state.values())):
        raise ValueError("stone columns must match the actual graph domain")
    snapshot = state.to_dict()
    if getattr(game, "rules_revision", spec.revision) != spec.revision:
        raise ValueError("unsupported production rules revision")
    current = _board_projection(game.board, game.rules)
    initial = current
    if isinstance(game.board, GraphBoard):
        if game.board.topology != game.topology:
            raise ValueError("game and actual graph topology disagree")
        initial_board = graph_board(game.board.n, game.board.spoke_family, game.initial_topology)
        initial = _board_projection(initial_board, game.rules)
    envelope = snapshot["rules_state"]
    phase = {name: snapshot[name] for name in ("to_move", "consecutive_passes", "quiet_moves", "finished",
             "no_progress_end", "resumption_used", "swap_decided", "extension_used", "extension_points")}
    phase.update({name: envelope[name] for name in ("seats", "end_decider", "accepted", "end_acceptances")})
    moves = snapshot["moves_played"]
    if type(moves) is not int or moves < 0:
        raise ValueError("invalid opening phase counter")
    phase.update(actor_color=state.actor_color, actor_seat=state.actor_seat,
                 opening_phase="unopened" if moves == 0 else "pie-window" if moves == 1 and not game.swap_decided else "ordinary")
    return _projection({"format": FORMAT, "version": VERSION, "rules_id": game.rules,
        "rules_revision": spec.revision, "board_size": game.board.n, "geometry": spec.geometry,
        "current_graph": current, "initial_graph": initial,
        "stones": [{"point": list(point), "column": list(game.state[point])} for point in game.board.points],
        "phase": phase})


def transform_projection(projection, symmetry):
    """Transform every spatial field together; validate and detach the result."""
    value = _projection(projection)
    transform_coordinate((0, 0), symmetry)
    def point(value):
        return list(transform_coordinate(value, symmetry))
    for name in ("current_graph", "initial_graph"):
        graph = value[name]
        for field in ("points", "original_points", "scoring_points", "rim"):
            graph[field] = [point(p) for p in graph[field]]
        graph["edges"] = [[point(a), point(b)] for a, b in graph["edges"]]
        graph["phantoms"] = [{"point": point(row["point"]), "count": row["count"]} for row in graph["phantoms"]]
        for field, neighbor_field in (("cells", "boundary"), ("topology", "neighbors")):
            graph[field] = [{"center": point(row["center"]), neighbor_field: [point(p) for p in row[neighbor_field]]}
                            for row in graph[field]]
    value["stones"] = [{"point": point(row["point"]), "column": row["column"]} for row in value["stones"]]
    value["phase"]["extension_points"] = [point(p) for p in value["phase"]["extension_points"]]
    return _projection(value)


def symmetry_key(state_or_projection):
    """SHA256 of the minimum D6 diagram; deliberately NOT full-history identity."""
    projection = diagram_projection(state_or_projection) if isinstance(state_or_projection, RulesState) else _projection(state_or_projection)
    canonical = min(canonical_json(transform_projection(projection, symmetry)) for symmetry in D6)
    return canonical_hash({"format": "varde-lab-spatial-class-v1", "diagram": json.loads(canonical)})
