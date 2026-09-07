"""Frozen, provisional native opponents for the experimental Rules Laboratory.

These UI opponents are neither MCTS-admitted nor evidence of game quality.
Every successor uses shared legal transitions; no Classic profile or Personal
model is imported. Search limits are agent policy, never live-game rule limits.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from time import perf_counter
from types import MappingProxyType

from actions import RulesAction, RulesState
from lab_actions import TransitionCache, legal_transitions
from lab_game import LabGame
from lab_spec import EXPERIMENT_SPECS
from varde import BLACK, WHITE, Illegal, groups_of, other


LAB_NATIVE_REVISION = "0.1"
LAB_NATIVE_RECIPE = "lab-native-objective-v1"
LAB_NATIVE_WEIGHTS = MappingProxyType({
    "occupied_objective": 1.0,
    "late_empty_area": 1.0,
    "connection_group_tax": -1.0,
    "majority_owned": 1.0,
    "majority_three_edges": 0.10,
    "majority_line_control": 0.10,
    "liberty_health": 0.20,
    "vulnerable_mass": -1.50,
    "capture_transition": 0.50,
})
STANDARD_ROOT_WIDTH = 10
CASUAL_CHOICES = 8
CASUAL_WINDOW = 0.20
PASS_IMPROVEMENT = 0.10
AREA_OCCUPANCY_GATE = 0.55
TERMINAL_OUTCOME_SCALE = 10.0
LAB_NATIVE_RECIPE_SPEC = MappingProxyType({
    "recipe": LAB_NATIVE_RECIPE, "revision": LAB_NATIVE_REVISION,
    "weights": tuple(LAB_NATIVE_WEIGHTS.items()),
    "rules": tuple((spec.id, spec.revision) for spec in EXPERIMENT_SPECS),
    "standard_root_width": STANDARD_ROOT_WIDTH, "casual_choices": CASUAL_CHOICES,
    "casual_window_per_original_point": CASUAL_WINDOW,
    "pass_improvement_per_original_point": PASS_IMPROVEMENT,
    "area_occupancy_gate": AREA_OCCUPANCY_GATE,
    "terminal_outcome_scale": TERMINAL_OUTCOME_SCALE,
    "liberties": "original-group-mass * min(distinct-empty-neighbors,3)/3 / P",
    "vulnerability": "original-group-mass in one-liberty groups / P",
    "captures": "all captured stones / P; original and junction telemetry separate",
    "majority_threat": "three controlled edges and at least one empty edge / cells",
    "terminal": "sign(actual margin)*10 + actual margin/scoreable area; accepted only",
    "pass": "no substantive move; or P placements and no improvement; or nonlosing pass reply",
    "ending": "losing actor resumes once if legal; otherwise accepts",
    "search": "original-seat minimax; top10 substantive roots plus eligible administration; all replies",
    "ties": "sha256 canonical complete root analysis key, seed, shared action dictionary",
})


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _agent_hash():
    paths = ("varde.py", "actions.py", "lab_game.py", "lab_graph.py", "lab_spec.py",
             "lab_actions.py", "lab_opponent.py")
    sources = {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
               for name in paths}
    return hashlib.sha256(_canonical({"recipe": dict(LAB_NATIVE_RECIPE_SPEC), "sources": sources})).hexdigest()


LAB_NATIVE_HASH = _agent_hash()


def lab_native_public():
    return {
        "status": "provisional", "provisional": True,
        "revision": LAB_NATIVE_REVISION, "recipe": LAB_NATIVE_RECIPE,
        "agent_hash": LAB_NATIVE_HASH, "difficulties": ["casual", "standard"],
    }


@dataclass(frozen=True)
class LabDecision:
    action: RulesAction
    reason_code: str = ""
    reason_text: str = ""
    nodes: int = 0
    elapsed_ms: float = 0.0
    transition_attempts: int = 0
    cache_hits: int = 0

    def to_dict(self):
        return self.action.to_dict() | {
            "reason_code": self.reason_code, "reason_text": self.reason_text,
            "nodes": self.nodes, "elapsed_ms": round(self.elapsed_ms, 2),
            "transition_attempts": self.transition_attempts, "cache_hits": self.cache_hits,
            "provisional": True, "agent_revision": LAB_NATIVE_REVISION,
            "agent_hash": LAB_NATIVE_HASH, "recipe": LAB_NATIVE_RECIPE,
        }


def _original_points(game):
    return frozenset(getattr(game.board, "original_points", game.board.points))


def _group_data(game, original):
    data = {}
    for color in (BLACK, WHITE):
        groups = groups_of(game.board, game.state, color)
        health = vulnerable = 0.0
        for group in groups:
            liberties = {neighbor for point in group for neighbor in game.board.neighbors[point]
                         if not game.state[neighbor]}
            mass = len(original.intersection(group))
            health += mass * min(len(liberties), 3) / 3
            vulnerable += mass if len(liberties) == 1 else 0
        data[color] = len(groups), health, vulnerable
    return data


def lab_features(game, color):
    """Finite color-antisymmetric state features; capture is a transition term."""
    if not isinstance(game, LabGame) or color not in (BLACK, WHITE):
        raise ValueError("laboratory features require a laboratory game and color")
    original = _original_points(game)
    points = len(original)
    enemy = other(color)
    controlled = game.original_control_count()
    groups = _group_data(game, original)
    values = {key: 0.0 for key in LAB_NATIVE_WEIGHTS if key != "capture_transition"}
    values["liberty_health"] = (groups[color][1] - groups[enemy][1]) / points
    values["vulnerable_mass"] = (groups[color][2] - groups[enemy][2]) / points
    if game.rules == "gjerde-majority":
        score = game.score()
        cells = len(game.board.cells)
        values["majority_owned"] = (score[color] - score[enemy]) / cells
        values["majority_line_control"] = (controlled[color] - controlled[enemy]) / points
        near = {BLACK: 0, WHITE: 0}
        for edges in game.board.cell_edges.values():
            if not any(not game.state[point] for point in edges):
                continue
            for side in (BLACK, WHITE):
                near[side] += sum(game.state[point] == (side,) for point in edges) == 3
        values["majority_three_edges"] = (near[color] - near[enemy]) / cells
    else:
        values["occupied_objective"] = (controlled[color] - controlled[enemy]) / points
        if game.rules == "breath-connection":
            values["connection_group_tax"] = (groups[color][0] - groups[enemy][0]) / points
        if sum(controlled.values()) >= AREA_OCCUPANCY_GATE * points:
            # Early evaluation never uses empty area: do not flood all empty
            # regions only to discard the result at every shallow-search leaf.
            score = game.score()
            if game.rules == "breath-connection":
                # The rules score already subtracts groups; recover empty area once.
                score = {side: score[side] + groups[side][0] for side in (BLACK, WHITE)}
            values["late_empty_area"] = (
                score[color] - controlled[color] - score[enemy] + controlled[enemy]
            ) / points
    return values


def evaluate_state(state, perspective_seat):
    color = state.color_for_seat(perspective_seat)
    if state.terminal:
        score = state.game.score()
        margin = score[color] - score[other(color)]
        area = len(state.game.board.cells) if state.game.rules == "gjerde-majority" else len(_original_points(state.game))
        return (1 if margin > 0 else -1 if margin < 0 else 0) * TERMINAL_OUTCOME_SCALE + margin / area
    return sum(LAB_NATIVE_WEIGHTS[name] * value for name, value in lab_features(state.game, color).items())


def _capture_bonus(transition, actor_seat, perspective_seat, points):
    direction = 1 if actor_seat == perspective_seat else -1
    return direction * LAB_NATIVE_WEIGHTS["capture_transition"] * transition.facts.captured_total / points


def _threatened(game, color):
    result = set()
    original = _original_points(game)
    for group in groups_of(game.board, game.state, color):
        liberties = {neighbor for point in group for neighbor in game.board.neighbors[point]
                     if not game.state[neighbor]}
        if len(liberties) == 1:
            result.update(original.intersection(group))
    return result


def _rationale(state, transition, perspective):
    action = transition.action
    if action.kind == "swap":
        return "swap", "Took Black; the original first player now plays White."
    if action.kind == "resume":
        return "resume", "Used the once-only resumption while behind."
    if action.kind == "accept":
        return "accept", "Accepted the current score; any other required seat decision remains."
    if action.kind == "pass":
        return "pass", "Passed under the provisional opponent's settling policy."
    if transition.facts.captured_total:
        facts = transition.facts
        return "capture", f"Captured {facts.captured_original} original stones and {facts.captured_junction} junction stones."
    child = transition.successor()
    color = child.color_for_seat(perspective)
    before_color = state.color_for_seat(perspective)
    rescued = {point for point in _threatened(state.game, before_color)
               if child.game.state.get(point) == (color,)} - _threatened(child.game, color)
    if rescued:
        return "defend", "Protected threatened original stones by improving their liberties."
    if state.game.rules == "gjerde-majority" and child.game.score()[color] > state.game.score()[before_color]:
        return "majority", "Completed a four-edge cell majority."
    if action.kind == "construct":
        return "construct", "Opened a neutral junction; either player may occupy it."
    if action.kind == "plant":
        return "plant", "Planted a stone while creating a Y junction."
    if action.point not in _original_points(state.game):
        return "junction", "Occupied an existing zero-point junction."
    if state.game.rules == "gjerde-majority":
        return "develop", "Played a line toward cell majorities."
    return "develop", "Played on an original scoring point."


def choose_lab_decision(state, difficulty="standard", seed=1):
    if not isinstance(state, RulesState) or not isinstance(state.game, LabGame):
        raise ValueError("a laboratory RulesState is required")
    if difficulty not in ("casual", "standard"):
        raise ValueError("laboratory difficulty must be casual or standard")
    if type(seed) is not int:
        raise ValueError("laboratory opponent seed must be an integer")
    if state.terminal:
        raise Illegal("the laboratory result has already been accepted")
    started = perf_counter()
    cache = TransitionCache()
    transitions = legal_transitions(state, cache=cache)
    if not transitions:
        raise Illegal("no legal laboratory action")
    perspective = state.actor_seat
    points = len(_original_points(state.game))
    if state.game.finished:
        score = state.game.score()
        color = state.color_for_seat(perspective)
        kind = "resume" if state.game.resumption_available and score[color] < score[other(color)] else "accept"
        chosen = next(transition for transition in transitions if transition.action.kind == kind)
    else:
        prefix = _canonical((state.analysis_key(), seed))
        ties = {transition.action: hashlib.sha256(prefix + _canonical(transition.action.to_dict())).hexdigest()
                for transition in transitions}
        values = {
            transition.action: evaluate_state(transition.successor(), perspective)
            + _capture_bonus(transition, perspective, perspective, points)
            for transition in transitions
        }
        substantive = [transition for transition in transitions
                       if transition.action.kind in ("play", "construct", "plant")]
        score = state.game.score()
        color = state.color_for_seat(perspective)
        pass_allowed = (
            not substantive
            or (state.game.consecutive_passes > 0 and score[color] >= score[other(color)])
            or (state.game.placements_played >= points
                and max(values[transition.action] for transition in substantive)
                <= evaluate_state(state, perspective) + PASS_IMPROVEMENT / points)
        )
        eligible = [transition for transition in transitions
                    if transition.action.kind != "pass" or pass_allowed]
        ranked = sorted(eligible, key=lambda transition: (-values[transition.action], ties[transition.action]))
        if difficulty == "casual":
            best = values[ranked[0].action]
            choices = [transition for transition in ranked[:CASUAL_CHOICES]
                       if values[transition.action] >= best - CASUAL_WINDOW / points]
            chosen = min(choices, key=lambda transition: ties[transition.action])
        else:
            searched = [transition for transition in ranked
                        if transition.action.kind in ("play", "construct", "plant")][:STANDARD_ROOT_WIDTH]
            searched += [transition for transition in ranked
                         if transition.action.kind not in ("play", "construct", "plant")]
            worst = {}
            for transition in searched:
                child = transition.successor()
                root_bonus = _capture_bonus(transition, perspective, perspective, points)
                replies = legal_transitions(child, cache=cache)
                if not replies:
                    worst[transition.action] = evaluate_state(child, perspective) + root_bonus
                    continue
                reply_values = [
                    evaluate_state(reply.successor(), perspective) + root_bonus
                    + _capture_bonus(reply, child.actor_seat, perspective, points)
                    for reply in replies
                ]
                reducer = max if child.actor_seat == perspective else min
                worst[transition.action] = reducer(reply_values)
            chosen = min(searched, key=lambda transition: (-worst[transition.action], ties[transition.action]))
    reason_code, reason_text = _rationale(state, chosen, perspective)
    return LabDecision(
        chosen.action, reason_code, reason_text, cache.legal_transition_count,
        (perf_counter() - started) * 1000, cache.transition_attempts, cache.cache_hits,
    )
