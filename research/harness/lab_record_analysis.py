"""Mechanical analysis of supplied engineering records, never strategy research.

The unchanged record verifier performs one required legal replay. A second replay
of precisely the same recorded wires obtains frames. There are no newly selected
actions. Source SHA256 values are references authenticated by the caller's pinned
input manifest, not raw-byte claims independently established from a JSON object.
"""

from collections import Counter
from dataclasses import dataclass
from html import escape
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
for directory in (REPOSITORY, REPOSITORY / "engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from actions import RulesAction, RulesState, apply_action  # noqa: E402
from game_factory import new_game  # noqa: E402
from lab_spec import EXPERIMENT_REGISTRY  # noqa: E402
from varde import get_ruleset_spec  # noqa: E402
from research.harness.lab_record import replay_lab_record, validate_lab_record_shape  # noqa: E402
from research.harness.lab_symmetry import (  # noqa: E402
    D6, RULESETS, diagram_projection, symmetry_key, transform_projection,
)
from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402

FORMAT = "varde-lab-record-analysis"
VERSION = 1
SOURCE_KIND = "engineering-ui-automation"
CLAIM_LIMIT = (
    "Scripted UI mechanical observations only; not independent games, human "
    "observations, best-move labels, strategic motifs, comparative statistics, "
    "search admission, or evidence of game quality."
)
CONTACT_DEFINITION = (
    "Each placement counts once if at least one actual pre-placement neighbor "
    "has the respective color; planted construction uses its newly activated "
    "spokes and pre-action stones. Empty construction is not a placement."
)
COUNTERS = ("rules_actions", "placements", "constructions", "passes", "swaps", "acceptances", "resumptions")
CONTACTS = ("placements", "friendly", "enemy", "both", "neither")
HEATMAP_KINDS = ("original-placement", "junction-placement", "construction", "friendly-contact", "enemy-contact", "capture-original", "capture-junction")


def _copy(value):
    return json.loads(canonical_json(value))


def _scope():
    return {"kind": SOURCE_KIND, "admitted_games": 0, "human_observations": 0,
            "comparative_headline_allowed": False, "qualified_shortlist": [],
            "strategic_depth": None, "strategic_variety": None, "beauty": None,
            "readability": None, "replay_desire": None, "memorable_understanding": None,
            "admitted_match_heatmaps": None,
            "uncertainty": "Authored interaction scripts are not a sample of independent play."}


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError(f"invalid {label} fields")


def _provenance(value, digest):
    _fields(value, {"kind", "source_id"}, "engineering provenance")
    label = value["source_id"]
    if value["kind"] != SOURCE_KIND or type(label) is not str or not label or label.strip() != label:
        raise ValueError("only explicit engineering UI provenance is accepted")
    if ("\\" in label or ":" in label or any(ord(c) < 32 for c in label)
            or PurePosixPath(label).is_absolute() or any(part in (".", "..", "") for part in label.split("/"))):
        raise ValueError("source ID must be a safe relative logical label, never path authority")
    if type(digest) is not str or re.fullmatch("[0-9a-f]{64}", digest) is None:
        raise ValueError("source_sha256 must be a lowercase SHA256 reference")
    return _copy(value)


@dataclass(frozen=True)
class RecordAnalysis:
    _json: str

    def to_dict(self):
        return json.loads(self._json)


@dataclass(frozen=True)
class AnalysisSummary:
    _json: str

    def to_dict(self):
        return json.loads(self._json)


def canonical_diagram(projection):
    """Deterministic full-board D6 representative; never history equivalence."""
    candidates = [(canonical_json(transform_projection(projection, symmetry)), symmetry) for symmetry in D6]
    encoded, symmetry = min(candidates)
    value = json.loads(encoded)
    return {"key": symmetry_key(value), "symmetry": symmetry, "projection": value}


def _frame(state, index):
    projection = diagram_projection(state)
    return {"action_index": index, "projection": projection, "spatial_key": symmetry_key(projection)}


def _heat_rows(counts):
    return [{"kind": kind, "point": list(point), "seat": seat, "color": color, "count": count}
            for (kind, point, seat, color), count in sorted(counts.items())]


def _heat_add(counts, kind, point, actor):
    counts[(kind, tuple(point), actor["seat"], actor["color"])] += 1


def _observation(before, after, row, counters, contact, captures, heatmaps):
    wire, actor = row["action"], row["actor"]
    kind = wire["action"]
    counters["rules_actions"] += 1
    for counter, condition in (("placements", kind in ("play", "plant")),
                               ("constructions", kind in ("construct", "plant")),
                               ("passes", kind == "pass"), ("swaps", kind == "swap"),
                               ("acceptances", kind == "accept"), ("resumptions", kind == "resume")):
        counters[counter] += int(condition)
    is_build = kind in ("construct", "plant")
    is_placement = kind in ("play", "plant")
    coordinate = (after.game.board.centers[tuple(wire["face"])] if is_build else
                  tuple(wire["point"]) if kind == "play" else None)
    if is_build:
        _heat_add(heatmaps, "construction", coordinate, actor)
    friendly, enemy, placement_kind = None, None, None
    originals = set(getattr(before.game.board, "original_points", before.game.board.points))
    if is_placement:
        graph = after.game.board if kind == "plant" else before.game.board
        neighbors = graph.neighbors[coordinate]
        colors = {before.game.state.get(point, ())[-1] for point in neighbors if before.game.state.get(point)}
        friendly = actor["color"] in colors
        enemy = ("W" if actor["color"] == "B" else "B") in colors
        contact["placements"] += 1
        contact["friendly"] += int(friendly)
        contact["enemy"] += int(enemy)
        contact["both"] += int(friendly and enemy)
        contact["neither"] += int(not friendly and not enemy)
        placement_kind = "original" if coordinate in originals else "junction"
        _heat_add(heatmaps, placement_kind + "-placement", coordinate, actor)
        if friendly:
            _heat_add(heatmaps, "friendly-contact", coordinate, actor)
        if enemy:
            _heat_add(heatmaps, "enemy-contact", coordinate, actor)
    for key in ("original", "junction"):
        captures[key] += row["captures"][key]
    for wave in row["captures"]["waves"]:
        for point in wave:
            _heat_add(heatmaps, "capture-original" if tuple(point) in originals else "capture-junction", point, actor)
    return {"index": row["index"], "action": _copy(wire), "actor": _copy(actor),
            "coordinate": list(coordinate) if coordinate is not None else None,
            "placement_kind": placement_kind, "friendly_contact": friendly, "enemy_contact": enemy,
            "captures": _copy(row["captures"]), "after_counters": dict(counters),
            "current_objective_score": _copy(row["after"]["score"]),
            "original_control": _copy(row["after"]["original_control"]),
            "objective_score_status": "accepted-terminal" if row["after"]["accepted"] else "provisional-position",
            "topology": [list(item) for item in after.game.topology]}


def analyze_record(record, *, provenance, source_sha256):
    provenance = _provenance(provenance, source_sha256)
    record = validate_lab_record_shape(record)
    receipt = replay_lab_record(record).to_dict()
    # A receipt alone has no frames. Perform the explicitly declared second
    # replay, keeping ordinary validation intact on every recorded action.
    game = new_game(record["board_size"], rules=record["rules"]["id"], experimental=True)
    game.players = {"B": "S1", "W": "S2"}
    state = RulesState(game, seats=dict(record["initial_seats"]))
    frames, observations = [_frame(state, -1)], []
    counters, contact = dict.fromkeys(COUNTERS, 0), dict.fromkeys(CONTACTS, 0)
    captures, heatmaps = {"original": 0, "junction": 0}, Counter()
    for row in record["actions"]:
        before = state
        state = apply_action(state, RulesAction.from_dict(row["action"]))
        observations.append(_observation(before, state, row, counters, contact, captures, heatmaps))
        frames.append(_frame(state, row["index"]))
    semantic = {"rules": record["rules"], "board_size": record["board_size"],
                "actions": [row["action"] for row in record["actions"]], "state": state.to_dict()}
    if canonical_hash(semantic) != receipt["replay_hash"] or state.accepted != receipt["accepted"]:
        raise ValueError("second recorded-action replay disagrees with verified receipt")
    payload = {"format": FORMAT, "version": VERSION, "claim_limit": CLAIM_LIMIT, "scope": _scope(),
               "provenance": provenance, "source_sha256": source_sha256,
               "source_hash_scope": "Raw-byte reference authenticated by caller input manifest, not by this JSON-only analyzer.",
               "rules": record["rules"], "board_size": record["board_size"],
               "replay_passes": 2, "replay": receipt, "trace_hash": receipt["replay_hash"],
               "status": record["status"], "accepted": state.accepted, "final_score": record["final_score"],
               "counters": counters, "captures": captures, "contact": contact,
               "contact_definition": CONTACT_DEFINITION,
               "objective_score_definition": "Recorded objective counts and occupied original-point control have different units; provisional positions are not accepted game results.",
               "heatmap_definition": "Raw executed-coordinate counts; captures credited to acting capturer; not preferences or rates.",
               "heatmaps": _heat_rows(heatmaps), "actions": observations, "frames": frames}
    payload["analysis_hash"] = canonical_hash(payload)
    return RecordAnalysis(canonical_json(payload))


def analyze_records(entries):
    if type(entries) is not list:
        raise ValueError("analysis entries must be an explicit list")
    seen_sources = set()
    prepared = []
    # Validate the complete input envelope before performing any replay.
    for entry in entries:
        _fields(entry, {"record", "provenance", "source_sha256"}, "analysis entry")
        source = _provenance(entry["provenance"], entry["source_sha256"])["source_id"]
        if source in seen_sources:
            raise ValueError("duplicate source ID")
        seen_sources.add(source)
        prepared.append({"record": validate_lab_record_shape(entry["record"]),
                         "provenance": _copy(entry["provenance"]), "source_sha256": entry["source_sha256"]})
    analyzed = [analyze_record(**entry).to_dict() for entry in sorted(prepared, key=lambda row: row["provenance"]["source_id"])]
    representatives, duplicates = {}, []
    for record in analyzed:
        digest = record["trace_hash"]
        if digest in representatives:
            duplicates.append({"source_id": record["provenance"]["source_id"],
                               "representative": representatives[digest]["provenance"]["source_id"], "trace_hash": digest})
        else:
            representatives[digest] = record
    records = sorted(representatives.values(), key=lambda row: (RULESETS.index(row["rules"]["id"]), row["board_size"], row["provenance"]["source_id"]))
    strata, atlas = {}, {}
    canonical_cache = {}
    for record in records:
        key = (record["rules"]["id"], record["board_size"], record["provenance"]["kind"])
        if key not in strata:
            strata[key] = {"rules": record["rules"], "board_size": key[1], "source_kind": key[2],
                           "distinct_traces": 0, "accepted_traces": 0,
                           "counters": dict.fromkeys(COUNTERS, 0), "captures": {"original": 0, "junction": 0},
                           "contact": dict.fromkeys(CONTACTS, 0), "heatmaps": Counter(),
                           "base_projection": record["frames"][0]["projection"]}
        stratum = strata[key]
        stratum["distinct_traces"] += 1
        stratum["accepted_traces"] += int(record["accepted"])
        for name in ("counters", "captures", "contact"):
            for counter, value in record[name].items():
                stratum[name][counter] += value
        for row in record["heatmaps"]:
            stratum["heatmaps"][(row["kind"], tuple(row["point"]), row["seat"], row["color"])] += row["count"]
        for frame in record["frames"]:
            spatial = frame["spatial_key"]
            if spatial not in atlas:
                encoded = canonical_json(frame["projection"])
                if encoded not in canonical_cache:
                    canonical_cache[encoded] = canonical_diagram(frame["projection"])
                representative = canonical_cache[encoded]
                if representative["key"] != spatial:
                    raise ValueError("diagram representative disagrees with spatial key")
                atlas[spatial] = {"key": spatial, "projection": representative["projection"], "members": [],
                                  "occurrences": 0, "claim_limit": "Recorded full-board spatial/phase class, not strategic equivalence or repeated discovery."}
            atlas[spatial]["members"].append({"source_id": record["provenance"]["source_id"],
                                              "trace_hash": record["trace_hash"], "action_index": frame["action_index"]})
            atlas[spatial]["occurrences"] += 1
    rows = []
    for key in sorted(strata, key=lambda value: (RULESETS.index(value[0]), value[1], value[2])):
        row = strata[key]
        row["heatmaps"] = _heat_rows(row["heatmaps"])
        rows.append(row)
    coverage = []
    for rules in RULESETS:
        spec = EXPERIMENT_REGISTRY[rules] if rules in EXPERIMENT_REGISTRY else get_ruleset_spec(rules)
        observed = [row for row in rows if row["rules"]["id"] == rules]
        coverage.append({"rules_id": rules, "revision": spec.revision,
                         "observation": {"distinct_traces": sum(row["distinct_traces"] for row in observed),
                                         "board_sizes": sorted({row["board_size"] for row in observed}),
                                         "source_kind": SOURCE_KIND} if observed else None})
    payload = {"format": "varde-lab-record-analysis-summary", "version": VERSION,
               "claim_limit": CLAIM_LIMIT, "scope": _scope(), "input_records": len(entries),
               "distinct_traces": len(records), "duplicate_records": duplicates,
               "records": records, "strata": rows, "coverage": coverage,
               "atlas": [atlas[key] for key in sorted(atlas)]}
    payload["analysis_hash"] = canonical_hash(payload)
    return AnalysisSummary(canonical_json(payload))


def render_diagram(projection, annotation=None):
    """Pure SVG from actual geometry; no external resources or executable text."""
    projection = transform_projection(projection, 0)
    if annotation is not None and (type(annotation) is not str or len(annotation) > 1000):
        raise ValueError("annotation must be a short plain-text string")
    graph = projection["current_graph"]
    points = [tuple(point) for point in graph["points"]]
    originals, scoring = set(map(tuple, graph["original_points"])), set(map(tuple, graph["scoring_points"]))
    stones = {tuple(row["point"]): row["column"] for row in projection["stones"]}
    coords = {point: (point[0], -point[1] * math.sqrt(3)) for point in points}
    min_x, max_x = min(x for x, _ in coords.values()), max(x for x, _ in coords.values())
    min_y, max_y = min(y for _, y in coords.values()), max(y for _, y in coords.values())
    scale = min(640 / max(1, max_x - min_x), 600 / max(1, max_y - min_y))

    def xy(point):
        x, y = point[0], -point[1] * math.sqrt(3)
        return (400 + (x - (min_x + max_x) / 2) * scale,
                378 + (y - (min_y + max_y) / 2) * scale)

    def num(number):
        return f"{number:.3f}"

    distances = [math.hypot(a[0] - b[0], math.sqrt(3) * (a[1] - b[1])) for a, b in graph["edges"]]
    radius = min(15, max(2, min(distances, default=2) * scale * .29))
    rules = escape(projection["rules_id"])
    title = f"{rules} · n={projection['board_size']} · recorded mechanical diagram"
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 780" role="img" aria-label="{title}">',
           f"<title>{title}</title>", '<rect width="800" height="780" fill="#f7f3e9"/>',
           f'<text x="28" y="30" font-family="sans-serif" font-size="18" fill="#24372e">{title}</text>']
    if annotation:
        svg.append(f'<text x="28" y="54" font-family="sans-serif" font-size="13" fill="#40564a">{escape(annotation)}</text>')
    for cell in graph["cells"]:
        center = cell["center"]
        boundary = sorted(cell["boundary"], key=lambda p: math.atan2(p[1] - center[1], p[0] - center[0]))
        polygon = " ".join(f"{num(x)},{num(y)}" for x, y in map(xy, boundary))
        counts = {color: sum(bool(stones[tuple(point)]) and stones[tuple(point)][-1] == color for point in boundary) for color in ("B", "W")}
        majority = projection["rules_id"] == "gjerde-majority"
        owner = next((color for color in ("B", "W") if counts[color] >= 4), None) if majority else None
        fill = "#b8cbbd" if owner == "B" else "#ede1af" if owner == "W" else "none"
        svg.append(f'<polygon class="cell" points="{polygon}" fill="{fill}" stroke="#c7cbbd" stroke-width="1"/>')
        if majority:
            x, y = xy(center)
            svg.append(f'<text class="cell-count" x="{num(x)}" y="{num(y + 3)}" text-anchor="middle" font-family="sans-serif" font-size="10">B{counts["B"]}/W{counts["W"]}</text>')
    for a, b in graph["edges"]:
        ax, ay = xy(a)
        bx, by = xy(b)
        hub_edge = tuple(a) not in originals or tuple(b) not in originals
        color = "#78579c" if hub_edge else "#849486"
        svg.append(f'<line class="graph-edge" x1="{num(ax)}" y1="{num(ay)}" x2="{num(bx)}" y2="{num(by)}" stroke="{color}" stroke-width="{2 if hub_edge else 1.2}"/>')
    for point in points:
        x, y = xy(point)
        tag = f"{point[0]},{point[1]}"
        if point not in originals:
            svg.append(f'<g class="junction" data-point="{tag}"><title>Neutral permanent zero-point junction {tag}; actual spokes shown</title>')
            svg.append(f'<rect x="{num(x-radius*.6)}" y="{num(y-radius*.6)}" width="{num(radius*1.2)}" height="{num(radius*1.2)}" transform="rotate(45 {num(x)} {num(y)})" fill="#eee7f5" stroke="#78579c" stroke-width="1.5"/></g>')
        else:
            role = "scoring" if point in scoring else "original-nonscoring"
            svg.append(f'<circle class="{role}" data-point="{tag}" cx="{num(x)}" cy="{num(y)}" r="2.3" fill="#566955"><title>{role} original point {tag}</title></circle>')
        if stones[point]:
            color = stones[point][-1]
            fill, stroke = ("#24332b", "#142219") if color == "B" else ("#fffdf6", "#53664f")
            svg.append(f'<circle class="stone {color}" data-point="{tag}" cx="{num(x)}" cy="{num(y)}" r="{num(radius)}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"><title>{color} at {tag}; height {len(stones[point])}</title></circle>')
            if len(stones[point]) > 1:
                text_color = "white" if color == "B" else "#24332b"
                svg.append(f'<text x="{num(x)}" y="{num(y+4)}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="{text_color}">{len(stones[point])}</text>')
    legend = "Dots: original points · Diamonds/purple spokes: neutral zero-point junctions"
    if graph["cells"]:
        if projection["rules_id"] == "gjerde-majority":
            legend = "Cells: B/W controlled boundary counts; ≥4 scores one cell"
        elif projection["rules_id"] in ("gjerde", "gjerde-go"):
            legend = "Dots: line positions · Cells score through single-color fenced regions"
        else:
            legend = "Dots: original line positions · Cell outlines do not add score here"
    svg.extend([f'<text x="28" y="732" font-family="sans-serif" font-size="13" fill="#40564a">{escape(legend)}</text>',
                '<text x="28" y="757" font-family="sans-serif" font-size="12" fill="#647168">Engineering demonstration, not a best move or strategic equivalence claim.</text>', "</svg>"])
    return "\n".join(svg)
