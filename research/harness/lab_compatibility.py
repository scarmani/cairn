#!/usr/bin/env python3
"""Freeze/verify legacy behavior; this is product regression, not match evidence.

Generation refuses an engine differing from the approved base. Verification
intentionally permits source refactors while enforcing recorded behavior and
byte preservation of historical evidence. No Personal model is loaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(ROOT / "engine"))

from actions import RulesAction, RulesState, apply_action, legal_actions  # noqa: E402
from opponent import choose_decision  # noqa: E402
from varde import BLACK, WHITE, Game, Illegal, get_ruleset_spec  # noqa: E402


BASE = "b620a11a72097f22e5addbfaf58b56073f9612cd"
RULESETS = ("classic", "rosette", "breath", "breath-run", "gjerde", "gjerde-go")
SIZES = (3, 4, 5, 6)
DIFFICULTIES = ("casual", "standard")
SEED = 2026090601
FIXTURE = ROOT / "research/fixtures/rules-lab-legacy-v1.json"
SOURCE_PATHS = (
    "engine/varde.py", "engine/actions.py", "engine/opponent.py",
    "engine/native_evaluators.py",
)


def canonical_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True,
    ).stdout


def source_protections():
    source = {
        path: hashlib.sha256(_git("show", f"{BASE}:{path}")).hexdigest()
        for path in SOURCE_PATHS
    }
    historical_paths = _git(
        "ls-tree", "-r", "--name-only", BASE,
        "research/manifests", "research/results", "research/fixtures",
    ).decode().splitlines()
    historical = {
        path: hashlib.sha256(_git("show", f"{BASE}:{path}")).hexdigest()
        for path in historical_paths
    }
    return {"generation_source_sha256": source, "historical_sha256": historical}


def action_from_dict(payload):
    return RulesAction(
        payload["action"],
        tuple(payload["point"]) if "point" in payload else None,
    )


def replay(rules, n, actions):
    state = RulesState.from_game(Game(n, rules=rules))
    for payload in actions:
        apply_action(state, action_from_dict(payload), copy=False)
    return state


def _seeded_setup(rules, n):
    rng = random.Random(f"rules-lab-legacy|{SEED}|{rules}|{n}")
    state = RulesState.from_game(Game(n, rules=rules))
    actions = []
    for _ in range(6):
        choices = [action for action in legal_actions(state) if action.kind == "play"]
        action = choices[rng.randrange(len(choices))]
        actions.append(action.to_dict())
        apply_action(state, action, copy=False)
    return actions


def _append(case_id, rules, n, setup):
    return {
        "id": f"{rules}-n{n}-{case_id}", "rules": rules, "n": n,
        "setup_actions": setup, "seed": SEED + n,
    }


def case_definitions():
    """Every fixture starts at the empty board and uses real legal actions."""
    cases = []
    for rules in RULESETS:
        for n in SIZES:
            cases.append(_append("fresh", rules, n, []))
            cases.append(_append("seeded-six", rules, n, _seeded_setup(rules, n)))
        opening = RulesAction("play", Game(3, rules=rules).board.points[0]).to_dict()
        setup = [opening]
        cases.append(_append("pie-offered", rules, 3, setup))
        setup = setup + [{"action": "swap"}]
        cases.append(_append("pie-taken", rules, 3, setup))
        setup = setup + [{"action": "pass"}]
        cases.append(_append("one-pass", rules, 3, setup))
        setup = setup + [{"action": "pass"}]
        cases.append(_append("first-ending", rules, 3, setup))
        accepted = setup + [{"action": "accept"}]
        cases.append(_append("first-acceptance", rules, 3, accepted))
        cases.append(_append("both-accept", rules, 3, accepted + [{"action": "accept"}]))
        resumed = accepted + [{"action": "resume"}]
        cases.append(_append("resumed", rules, 3, resumed))
        second_end = resumed + [{"action": "pass"}, {"action": "pass"}]
        cases.append(_append("second-ending", rules, 3, second_end))
        cases.append(_append("final-acceptance", rules, 3, second_end + [{"action": "accept"}]))

    # Actual reachable ko: no inserted or invented forbidden positions.
    board = Game(3).board
    recapture = next(
        point for point in sorted(board.rim)
        if all(len(board.neighbors[nb]) == 3 for nb in board.neighbors[point])
    )
    capture, white = board.neighbors[recapture]
    white_more = [p for p in board.neighbors[white] if p != recapture]
    black_more = [p for p in board.neighbors[capture] if p != recapture]
    points = [recapture, white, black_more[0], white_more[0], black_more[1], white_more[1]]
    setup = [RulesAction("play", point).to_dict() for point in points]
    setup += [{"action": "pass"}, RulesAction("play", capture).to_dict()]
    ko = _append("reachable-ko", "classic", 3, setup)
    ko["rejected_action"] = RulesAction("play", recapture).to_dict()
    ko["rejection_reason"] = "repetition"
    cases.append(ko)
    return cases


def state_observation(state):
    game = state.game
    board = game.board
    actions = [action.to_dict() for action in legal_actions(state)]
    return {
        "snapshot_sha256": digest(game.to_dict()),
        "geometry_sha256": digest([
            [list(point), [list(nb) for nb in board.neighbors[point]]]
            for point in board.points
        ]),
        "legal_actions_sha256": digest(actions),
        "legal_action_count": len(actions),
        "history_count": len(game.history),
        "score": game.score(), "controlled": game.control_count(),
        "seats": state.seats, "actor_color": state.actor_color,
        "actor_seat": state.actor_seat,
        "end_acceptances": sorted(state.end_acceptances),
        "terminal": state.terminal,
    }


def decision_observations(state, seed):
    if state.terminal:
        return []
    colors = (BLACK, WHITE) if state.game.finished else (state.actor_color,)
    before = canonical_bytes(state.game.to_dict())
    results = []
    legal = legal_actions(state)
    for color in colors:
        for difficulty in DIFFICULTIES:
            decision = choose_decision(state.game, color, difficulty, seed=seed)
            result = decision.to_dict()
            del result["elapsed_ms"]
            if canonical_bytes(state.game.to_dict()) != before:
                raise AssertionError("legacy opponent mutated analyzed game")
            action = RulesAction(decision.action, decision.point)
            if action not in legal:
                raise AssertionError(f"illegal legacy decision: {action}")
            results.append({"color": color, "difficulty": difficulty, **result})
    return results


def observe_case(case):
    state = replay(case["rules"], case["n"], case["setup_actions"])
    if "rejected_action" in case:
        try:
            apply_action(state, action_from_dict(case["rejected_action"]), validate=False)
        except Illegal as error:
            if str(error) != case["rejection_reason"]:
                raise AssertionError(f"changed ko rejection: {error}") from error
        else:
            raise AssertionError("reachable ko recapture was allowed")
    return {
        "state": state_observation(state),
        "decisions": decision_observations(state, case["seed"]),
    }


def save_examples():
    examples = []
    for index, rules in enumerate(RULESETS):
        for n in SIZES:
            setup = _seeded_setup(rules, n)
            state = replay(rules, n, setup)
            payload = state.game.to_dict()
            payload["format"] = "cairn-game" if index % 2 == 0 else "varde-game"
            continuation = [
                {"action": "pass"}, {"action": "pass"}, {"action": "accept"},
                {"action": "resume"}, {"action": "pass"}, {"action": "pass"},
                {"action": "accept"},
            ]
            restored = RulesState.from_game(Game.from_dict(payload))
            for action in continuation:
                apply_action(restored, action_from_dict(action), copy=False)
            examples.append({
                "id": f"{rules}-n{n}-legacy-v1", "setup_actions": setup,
                "payload": payload, "continuation": continuation,
                "final": state_observation(restored),
            })
    return examples


def generate():
    protections = source_protections()
    for path, expected in protections["generation_source_sha256"].items():
        if file_digest(ROOT / path) != expected:
            raise ValueError(f"refusing to regenerate from modified baseline: {path}")
    cases = []
    for definition in case_definitions():
        cases.append({**definition, **observe_case(definition)})
    payload = {
        "format": "varde-rules-lab-legacy-compatibility", "version": 1,
        "source_base": BASE, "purpose": "product-regression-only",
        "rules_revisions": {
            rules: get_ruleset_spec(rules).revision for rules in RULESETS
        },
        "matrix": {"rulesets": list(RULESETS), "sizes": list(SIZES),
                   "difficulties": list(DIFFICULTIES), "seed": SEED},
        "claim_limit": "No tactical certification or comparative match evidence.",
        "protections": protections, "cases": cases, "saves": save_examples(),
    }
    return {**payload, "content_sha256": digest(payload)}


def load_fixture(path=FIXTURE):
    payload = json.loads(Path(path).read_text())
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("content_sha256") != digest(content):
        raise ValueError("legacy compatibility fixture hash mismatch")
    if (
        payload.get("format") != "varde-rules-lab-legacy-compatibility"
        or payload.get("source_base") != BASE
        or payload.get("version") != 1
    ):
        raise ValueError("unsupported legacy compatibility fixture")
    return payload


def verify(payload):
    for path, expected in payload["protections"]["historical_sha256"].items():
        if file_digest(ROOT / path) != expected:
            raise AssertionError(f"historical evidence changed: {path}")
    for case in payload["cases"]:
        actual = observe_case(case)
        for field in ("state", "decisions"):
            if actual[field] != case[field]:
                raise AssertionError(f"legacy {field} changed: {case['id']}")
    for example in payload["saves"]:
        state = RulesState.from_game(Game.from_dict(example["payload"]))
        for action in example["continuation"]:
            apply_action(state, action_from_dict(action), copy=False)
        if state_observation(state) != example["final"]:
            raise AssertionError(f"legacy save/replay changed: {example['id']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "verify"))
    parser.add_argument("--output", type=Path, default=FIXTURE)
    args = parser.parse_args()
    if args.command == "generate":
        payload = generate()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_bytes(canonical_bytes(payload) + b"\n")
        temporary.replace(args.output)
    else:
        payload = load_fixture(args.output)
        verify(payload)
    print(json.dumps({
        "status": "ok", "command": args.command, "cases": len(payload["cases"]),
        "decisions": sum(len(case["decisions"]) for case in payload["cases"]),
        "saves": len(payload["saves"]), "content_sha256": payload["content_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
