"""Laboratory-only match adapter; RulesState owns all rules and ending decisions.

Match presentation is duck-typed to avoid importing the server or its Personal
model. Legacy matches never use this adapter. No search or research runs here.
"""

from actions import RulesAction, RulesState, apply_action, legal_actions
from lab_game import LabGame
from lab_opponent import lab_native_public
from lab_spec import LAB_REGISTRY, LAB_SPECS, get_lab_spec
from varde import BLACK, WHITE, Illegal, control, groups_of


LAB_ALIAS_ROUTES = {
    "/api/play": "play", "/api/pass": "pass", "/api/swap": "swap",
    "/api/resume": "resume", "/api/extend": "extend",
    "/api/finish-extensions": "finish-extension",
}


def is_lab_game(game):
    return isinstance(game, LabGame)


def lab_computer_settings(difficulty="standard", profile=None):
    if profile is not None:
        raise ValueError("laboratory opponents cannot use Classic or Personal profiles")
    if difficulty not in ("casual", "standard"):
        raise ValueError("laboratory difficulty must be casual or standard")
    return difficulty, None


def validate_lab_profiles(body):
    for key in ("profile", "black_profile", "white_profile"):
        if body.get(key) is not None:
            raise ValueError("laboratory opponents cannot use Classic or Personal profiles")


def validate_lab_match(match):
    if match.mode not in ("hotseat", "computer", "watch") or set(match.seats) != {BLACK, WHITE}:
        raise ValueError("invalid laboratory match mode or seats")
    expected_computers = {"hotseat": 0, "computer": 1, "watch": 2}[match.mode]
    if sum(seat.kind == "computer" for seat in match.seats.values()) != expected_computers:
        raise ValueError("laboratory seat kinds do not match the saved mode")
    identities = set()
    for seat in match.seats.values():
        if (seat.kind not in ("human", "computer")
                or not isinstance(seat.identity, str) or not seat.identity
                or not isinstance(seat.name, str) or not seat.name):
            raise ValueError("invalid laboratory seat identity or name")
        identities.add(seat.identity)
        if seat.kind == "computer":
            lab_computer_settings(seat.difficulty, seat.profile)
            if type(seat.seed) is not int:
                raise ValueError("laboratory seat seed must be an integer")
        elif seat.difficulty is not None or seat.profile is not None:
            raise ValueError("human laboratory seats cannot have computer settings")
    if len(identities) != 2:
        raise ValueError("laboratory seat identities must be unique")


def attach_lab_state(game, match, state=None, *, saved_end_decided=None):
    """Bind once at creation/load; never rebuild ending state on each request."""
    if not is_lab_game(game) or game.rules not in LAB_REGISTRY:
        raise ValueError("research-only static controls cannot be played in the browser")
    validate_lab_match(match)
    identities = {color: match.seats[color].identity for color in (BLACK, WHITE)}
    names = {color: match.seats[color].name for color in (BLACK, WHITE)}
    if state is None:
        state = RulesState(game, seats=identities)
    if (state.game is not game or state.seats != identities or game.players != names
            or state.end_acceptances != match.end_acceptances):
        raise ValueError("laboratory match and rules-state envelopes disagree")
    if saved_end_decided is not None and saved_end_decided != state.accepted:
        raise ValueError("laboratory accepted-ending flags disagree")
    match.lab_state = state
    # Alias, not a second authority. Shared actions clear/add this same set.
    match.end_acceptances = state.end_acceptances
    return state


def lab_state(game, match):
    state = match.lab_state
    if state is None or state.game is not game:
        raise ValueError("laboratory match has no bound rules state")
    if (state.seats != {color: seat.identity for color, seat in match.seats.items()}
            or game.players != {color: seat.name for color, seat in match.seats.items()}
            or state.end_acceptances != match.end_acceptances):
        raise ValueError("laboratory match binding changed outside the shared action adapter")
    return state


def lab_computer_color(game, match):
    state = lab_state(game, match)
    color = state.actor_color
    return color if color and match.seats[color].kind == "computer" else None


def assert_lab_actor(game, match, kind):
    state = lab_state(game, match)
    color = state.actor_color
    if color is None:
        raise Illegal("the laboratory result has already been accepted")
    if match.seats[color].kind != kind:
        raise Illegal("wait for the computer's move" if kind == "human" else "it is not the computer's turn")
    return state


def apply_lab_action(game, match, action, *, actor_kind="human"):
    """Commit exactly one legal rules action; seat presentation follows takeover."""
    if actor_kind not in ("human", "computer"):
        raise ValueError("invalid action actor kind")
    if not isinstance(action, RulesAction):
        raise ValueError("a structured RulesAction is required")
    state = assert_lab_actor(game, match, actor_kind)
    apply_action(state, action, copy=False)
    if action.kind == "swap":
        # The shared adapter already swapped the game players and identity map.
        # Swap complete Seat objects once, without invoking game.take_over again.
        match.swap_owners(game)
    lab_state(game, match)
    return state


def action_from_alias(route, body):
    if route not in LAB_ALIAS_ROUTES or not isinstance(body, dict) or "action" in body:
        raise ValueError("invalid laboratory action alias")
    return RulesAction.from_dict({"action": LAB_ALIAS_ROUTES[route], **body})


def lab_catalog_entries():
    entries = []
    for spec in LAB_SPECS:
        item = spec.public_dict()
        item.update(
            experimental=True, experimental_available=True, public_new_game=False,
            status="experimental", rules_revision=spec.revision,
            family=spec.id, min_size=min(spec.allowed_sizes), max_size=max(spec.allowed_sizes),
            archival_reason=None, scoring_description=spec.description,
            analysis_status="unmeasured", native_evaluator_revision="lab-native-objective-v1",
            native_opponent=lab_native_public(),
        )
        entries.append(item)
    return entries


def laboratory_public_view(game, match, *, decision=None, learning=None):
    """Public projection with one shared legal-action enumeration per request."""
    state = lab_state(game, match)
    actions = legal_actions(state)
    legal_points = {action.point for action in actions if action.kind == "play"}
    legal_builds = {}
    for action in actions:
        if action.kind in ("construct", "plant"):
            legal_builds.setdefault(action.point, []).append(action.orientation)
    board = game.board
    original = frozenset(getattr(board, "original_points", board.points))
    centers = getattr(board, "active_centers", frozenset())
    scoreable = original if game.rules != "gjerde-majority" else frozenset()
    group_liberties = {}
    for color in (BLACK, WHITE):
        for group in groups_of(board, game.state, color):
            liberties = {nb for point in group for nb in board.neighbors[point] if not game.state[nb]}
            group_liberties.update({point: len(liberties) for point in group})
    points = [{
        "coord": list(point), "stack": list(game.state[point]),
        "rim": point in board.rim, "phantoms": board.phantoms[point],
        "deep": point in board.deep, "legal": point in legal_points,
        "extension": False, "sky": False, "group_libs": group_liberties.get(point),
        "segment": [list(v) for v in board.segments[point]] if hasattr(board, "segments") else None,
        "original": point in original, "scoring": point in scoreable,
        "center": point in centers, "neighbors": [list(nb) for nb in board.neighbors[point]],
    } for point in board.points]
    spec = get_lab_spec(game.rules)
    topology = {(q, r): orientation for q, r, orientation in game.topology}
    sites = []
    if spec.construction != "none":
        for face, corners in board.faces.items():
            sites.append({
                "face": list(face), "center": list(board.centers[face]),
                "corners": [list(point) for point in corners],
                "active": face in topology, "orientation": topology.get(face),
                "legal_orientations": legal_builds.get(face, []),
                "kind": "plant" if spec.construction == "planted-y" else "construct",
                "orientations": [list(indices) for indices in spec.orientation_sets],
            })
    cells = []
    if game.rules == "gjerde-majority":
        for q, r in board.cells:
            edges = board.cell_edges[(q, r)]
            counts = {color: sum(control(game.state, p) == color for p in edges) for color in (BLACK, WHITE)}
            cells.append({
                "face": [q, r], "center": [6 * q, 4 * r + 2 * q],
                "edges": [list(point) for point in edges], "counts": counts,
                "owner": next((color for color in (BLACK, WHITE) if counts[color] >= 4), None),
            })
    computer = lab_computer_color(game, match)
    return {
        "n": board.n, "rules": game.rules, "experimental": True,
        "rules_revision": spec.revision, "flat": True,
        "points": points,
        "edges": [[list(point), list(nb)] for point in board.points for nb in board.neighbors[point] if point < nb],
        "to_move": game.to_move,
        "current_player": match.seats[state.actor_color].name if state.actor_color else None,
        "players": dict(game.players), "moves_played": game.moves_played,
        "placements_played": game.placements_played, "constructions_played": game.constructions_played,
        "consecutive_passes": game.consecutive_passes, "finished": game.finished,
        "no_progress_end": False, "extension_only_turn": False,
        "resumption_available": not state.accepted and game.resumption_available,
        "resumption_used": game.resumption_used, "swap_available": game.swap_available,
        "accepted": state.accepted, "actor_color": state.actor_color, "actor_seat": state.actor_seat,
        "score": game.score(), "control": game.control_count(),
        "original_control": game.original_control_count(), "cells": cells,
        "topology": [list(row) for row in game.topology],
        "legal_actions": [action.to_dict() for action in actions], "construction_sites": sites,
        "capture_waves": [[list(point) for point in wave] for wave in game.last_capture_waves],
        "match": {
            "mode": match.mode, "seats": {color: match.seats[color].to_dict() for color in (BLACK, WHITE)},
            "human_color": match.human_color, "computer_color": match.computer_color,
            "difficulty": match.difficulty, "profile": None, "explain": match.explain,
            "computer_turn": not game.finished and computer is not None,
            "computer_can_act": computer is not None,
            "pending_end_deciders": [state.actor_color] if game.finished and not state.accepted else [],
            "end_acceptances": sorted(state.end_acceptances),
        },
        "learning": learning, "computer_decision": decision,
        "analysis_status": "unmeasured",
        "mcts_admission": {"status": "unmeasured", "comparative_games": 0},
        "native_opponent": lab_native_public(),
    }
