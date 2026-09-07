"""Exact legacy server-data gate captured before laboratory API integration.

Regenerate only from the pinned server source with::

    PYTHONPATH=engine python3 engine/test_lab_server_legacy_parity.py --generate

This is product verification, not agent calibration or game-quality evidence.
Complete public/save payloads are hashed without removing any fields. Personal
status is a fixed in-memory model, the trainer is idle, and serializer decisions
are synthetic (elapsed_ms=0), so neither user files nor measured timing enters
the fixture. The source hashes document capture provenance, not a permanent
source-code freeze: later implementations must preserve the observed behavior.
"""

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

import learning


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "research/fixtures/rules-lab-server-legacy-v1.json"
BASE = "496a1fef19a45b8faea1c67c5e08993d5ccbb5a1"
RULESETS = ("classic", "rosette", "breath", "breath-run", "gjerde", "gjerde-go")
SIZES = (3, 4, 5, 6)
FORMATS = ("varde-game", "cairn-game")
PHASES = (
    "fresh", "opening", "pie-taken", "one-pass", "first-ending",
    "first-acceptance", "resumed", "second-ending", "final-acceptance",
)
DEPENDENCIES = (
    "engine/varde.py", "engine/learning.py", "engine/opponent.py",
    "engine/profiles.py", "engine/native_evaluators.py",
)
CONFIGURATIONS = {
    "hotseat": {
        "mode": "hotseat", "players": {"B": "Ada", "W": "Grace"},
    },
    "human-black": {
        "mode": "computer", "human_color": "B", "difficulty": "casual",
        "profile": "balanced", "seed": 73, "explain": False,
    },
    "human-white": {
        "mode": "computer", "human_color": "W", "difficulty": "standard",
        "profile": "personal", "seed": 91, "explain": True,
    },
    "advanced-alias": {
        "mode": "computer", "human_color": "B", "difficulty": "advanced",
        "seed": 101,
    },
    "watch": {
        "mode": "watch", "black_difficulty": "casual",
        "black_profile": "balanced", "white_difficulty": "standard",
        "white_profile": "personal", "seed": 211, "explain": True,
    },
    "watch-alias": {
        "mode": "computer_vs_computer", "black_difficulty": "standard",
        "white_difficulty": "casual", "seed": 307, "explain": False,
    },
    "defaults": {},
}
SAVE_KINDS = (
    "bare", "single-computer", "single-advanced", "normalized-match",
    "legacy-seat-advanced", "old-end-decided", "one-end-acceptance",
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def source_at_base(path):
    return subprocess.run(
        ["git", "show", f"{BASE}:{path}"], cwd=ROOT, check=True,
        capture_output=True,
    ).stdout


def fixed_model():
    # Constructor only: load() is patched before the isolated server executes.
    # This path is never read, saved, or passed to a running training job.
    return learning.LearningModel(
        path=Path("/not-used/rules-lab-server-parity-model.json"),
        weights={name: 0.0 for name in learning.FEATURE_NAMES},
        games_attempted=13, games_trained=12, training_seed=941,
        updated_at="2000-01-01T00:00:00+00:00",
    )


@contextmanager
def isolated_server(source=None):
    """Import without binding the suite's server module or reading Personal."""
    name = "_rules_lab_legacy_parity_server"
    previous = sys.modules.get(name)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / "engine/server.py")
    sys.modules[name] = module  # dataclasses resolves the declaring module.
    model = fixed_model()
    source = source if source is not None else (ROOT / "engine/server.py").read_bytes()
    try:
        with patch.object(learning.LearningModel, "load", return_value=model):
            exec(compile(source, module.__file__, "exec"), module.__dict__)
        # Creating TrainingService starts no thread. Freeze and check its exact
        # idle state below, including all status fields, rather than discarding it.
        if module.TRAINER.thread is not None or module.TRAINER.running:
            raise AssertionError("server import unexpectedly launched training")
        yield module
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def observation(server, game, match, decision=None):
    view = server.public_view(game, match, decision)
    snapshot = server.snapshot_payload(game, match)
    return {
        "public_sha256": digest(view),
        "save_sha256": digest(snapshot),
        "geometry_sha256": digest({key: view[key] for key in ("points", "edges")}),
        "point_count": len(view["points"]),
        "state": {key: view[key] for key in (
            "to_move", "moves_played", "finished", "swap_available",
            "resumption_available", "resumption_used", "score", "control",
        )},
    }


def advance(server, game, match, phase):
    """One reachable scripted flow; no generated or invented superko history."""
    if phase == "fresh":
        return
    if phase == "opening":
        game.play(game.board.points[0])
    elif phase == "pie-taken":
        game.take_over()
        match.swap_owners(game)
    elif phase in ("one-pass", "first-ending"):
        game.play_pass()
    elif phase in ("first-acceptance", "final-acceptance"):
        match.accept_end(game, match.next_computer_color(game))
    elif phase == "resumed":
        game.demand_resumption()
        match.clear_end_acceptances()
    elif phase == "second-ending":
        game.play_pass()
        game.play_pass()
    else:
        raise ValueError(f"unknown fixture phase: {phase}")


def observe_flow(server, rules, size):
    game = server.Game(size, rules=rules)
    match = server.MatchConfig.from_new_game(game, deepcopy(CONFIGURATIONS["watch"]))
    result = []
    for phase in PHASES:
        advance(server, game, match, phase)
        result.append({"phase": phase, **observation(server, game, match)})
    return result


def observe_configuration(server, body):
    game = server.Game(3)
    match = server.MatchConfig.from_new_game(game, deepcopy(body))
    before = match.snapshot_data()
    game.play(game.board.points[0])
    opening = server.public_view(game, match)
    decision = server.BotDecision(
        action="play", point=game.board.points[0], reason_code="develop",
        reason_text="Fixed serializer example; not a searched move.",
        score=12.34, nodes=7, elapsed_ms=0.0,
        profile=match.profile or "balanced",
    )
    shown = server.public_view(game, match, decision)
    game.take_over()
    match.swap_owners(game)
    return {
        "configuration": before,
        "opening": {key: opening[key] for key in ("players", "match")},
        "decision": shown["computer_decision"],
        "after_takeover": match.snapshot_data(),
        "public_after_takeover_sha256": digest(server.public_view(game, match)),
    }


def save_payload(server, rules, size, kind):
    game = server.Game(size, rules=rules)
    game.players = {"B": "Saved Black", "W": "Saved White"}
    game.play(game.board.points[0])
    if kind == "bare":
        return game.to_dict()
    if kind in ("single-computer", "single-advanced"):
        payload = game.to_dict()
        payload["computer"] = {
            "enabled": True, "color": "W", "explain": False, "seed": 43,
            "difficulty": "advanced" if kind == "single-advanced" else "casual",
        }
        return payload
    match = server.MatchConfig.from_new_game(game, deepcopy(CONFIGURATIONS["watch"]))
    if kind in ("old-end-decided", "one-end-acceptance"):
        game.play_pass()
        game.play_pass()
        if kind == "old-end-decided":
            match.end_decided = True
        else:
            match.accept_end(game, match.next_computer_color(game))
    payload = server.snapshot_payload(game, match)
    if kind == "legacy-seat-advanced":
        payload["match"]["seats"]["W"].pop("profile")
        payload["match"]["seats"]["W"]["difficulty"] = "advanced"
    elif kind == "old-end-decided":
        payload["match"].pop("end_acceptances")
    elif kind not in ("normalized-match", "one-end-acceptance"):
        raise ValueError(f"unknown legacy save kind: {kind}")
    return payload


def observe_save(server, payload):
    game, match = server.load_snapshot(deepcopy(payload))
    loaded = observation(server, game, match)
    # Continue a loaded opening through pie and a pass, or reopen the loaded
    # first ending. This protects continuation, not merely accepted JSON shape.
    if game.finished:
        game.demand_resumption()
        match.clear_end_acceptances()
    else:
        game.take_over()
        match.swap_owners(game)
        game.play_pass()
    return {
        "loaded": loaded,
        "configuration": match.snapshot_data(),
        "continued": observation(server, game, match),
    }


def generate():
    # Dependencies remain those at the pinned capture base. They may be
    # refactored later; this guard applies only to baseline regeneration.
    sources = {path: hashlib.sha256(source_at_base(path)).hexdigest()
               for path in ("engine/server.py", *DEPENDENCIES)}
    for path in DEPENDENCIES:
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != sources[path]:
            raise ValueError(f"baseline dependency changed: {path}")
    with isolated_server(source_at_base("engine/server.py")) as server:
        flows = [
            {"rules": rules, "n": size, "observations": observe_flow(server, rules, size)}
            for rules in RULESETS for size in SIZES
        ]
        saves = []
        for rules in RULESETS:
            for size in SIZES:
                for kind in SAVE_KINDS:
                    payload = save_payload(server, rules, size, kind)
                    frozen_input = deepcopy(payload)
                    # Both wire identifiers are independently loaded below.
                    observations = {}
                    for format_id in FORMATS:
                        payload["format"] = format_id
                        observations[format_id] = observe_save(server, payload)
                    saves.append({
                        "rules": rules, "n": size, "kind": kind,
                        "payload": frozen_input,
                        "observations": observations,
                    })
        result = {
            "format": "varde-rules-lab-server-legacy-parity", "version": 1,
            "source_base": BASE, "capture_source_sha256": sources,
            "purpose": "product-regression-only",
            "claim_limit": "No agent search, tactical certification, or comparative matches.",
            "normalization": {
                "excluded_public_fields": [], "excluded_save_fields": [],
                "model": "Fixed in-memory model; no user model file read or written.",
                "trainer": "Idle in-memory service; no worker launched.",
                "decision": "Synthetic serialization example; elapsed_ms is fixed at zero.",
                "catalog": "Existing entries and metadata exact; new lab entries may be appended.",
            },
            "matrix": {"rulesets": list(RULESETS), "sizes": list(SIZES),
                       "phases": list(PHASES), "formats": list(FORMATS)},
            "model_status": server.MODEL.status(),
            "trainer_status": server.TRAINER.status(),
            "catalog": server.ruleset_catalog_public(),
            "profiles": server.profiles_public(server.MODEL.status()),
            "configurations": {
                key: {"request": body, "expected": observe_configuration(server, body)}
                for key, body in CONFIGURATIONS.items()
            },
            "flows": flows, "saves": saves,
        }
    return {**result, "content_sha256": digest(result)}


def load_fixture():
    payload = json.loads(FIXTURE.read_text())
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    if digest(content) != payload.get("content_sha256"):
        raise ValueError("legacy server fixture hash mismatch")
    if (
        payload.get("format") != "varde-rules-lab-server-legacy-parity"
        or payload.get("source_base") != BASE
        or payload.get("version") != 1
    ):
        raise ValueError("unsupported legacy server fixture")
    return payload


class TestLabServerLegacyParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()
        cls.server_context = isolated_server()
        cls.server = cls.server_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.server_context.__exit__(None, None, None)

    def test_complete_matrix_and_fixed_nonvolatile_environment(self):
        expected = {(rules, size) for rules in RULESETS for size in SIZES}
        self.assertEqual(len(self.fixture["flows"]), 24)
        self.assertEqual({(flow["rules"], flow["n"]) for flow in self.fixture["flows"]}, expected)
        self.assertEqual(len(self.fixture["saves"]), 24 * len(SAVE_KINDS))
        self.assertEqual(
            {(save["rules"], save["n"], save["kind"]) for save in self.fixture["saves"]},
            {(rules, size, kind) for rules, size in expected for kind in SAVE_KINDS},
        )
        for flow in self.fixture["flows"]:
            self.assertEqual([item["phase"] for item in flow["observations"]], list(PHASES))
        for save in self.fixture["saves"]:
            self.assertEqual(set(save["observations"]), set(FORMATS))
        self.assertEqual(self.fixture["normalization"]["excluded_public_fields"], [])
        self.assertEqual(self.fixture["normalization"]["excluded_save_fields"], [])
        self.assertEqual(self.server.MODEL.status(), self.fixture["model_status"])
        self.assertEqual(self.server.TRAINER.status(), self.fixture["trainer_status"])
        self.assertIsNone(self.server.TRAINER.thread)

    def test_legacy_public_views_and_saves_across_every_phase(self):
        for flow in self.fixture["flows"]:
            with self.subTest(rules=flow["rules"], n=flow["n"]):
                self.assertEqual(
                    observe_flow(self.server, flow["rules"], flow["n"]),
                    flow["observations"],
                )

    def test_legacy_configuration_pie_and_explanation_serialization(self):
        self.assertEqual(set(self.fixture["configurations"]), set(CONFIGURATIONS))
        for name, case in self.fixture["configurations"].items():
            with self.subTest(configuration=name):
                self.assertEqual(observe_configuration(self.server, case["request"]), case["expected"])

    def test_old_and_normalized_legacy_saves_load_and_continue_in_both_formats(self):
        for case in self.fixture["saves"]:
            payload = deepcopy(case["payload"])
            self.assertEqual(
                save_payload(self.server, case["rules"], case["n"], case["kind"]),
                payload,
            )
            for format_id in FORMATS:
                with self.subTest(rules=case["rules"], n=case["n"], kind=case["kind"], format=format_id):
                    payload["format"] = format_id
                    self.assertEqual(
                        observe_save(self.server, payload), case["observations"][format_id],
                    )

    def test_existing_catalog_entries_and_profile_catalog_are_unchanged(self):
        catalog = self.server.ruleset_catalog_public()
        original = self.fixture["catalog"]
        old_ids = {item["id"] for item in original["rulesets"]}
        self.assertEqual(
            [item for item in catalog["rulesets"] if item["id"] in old_ids],
            original["rulesets"],
        )
        for key in original.keys() - {"rulesets"}:
            self.assertEqual(catalog[key], original[key])
        self.assertEqual(
            self.server.profiles_public(self.server.MODEL.status()), self.fixture["profiles"],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    arguments, remaining = parser.parse_known_args()
    if arguments.generate:
        payload = generate()
        FIXTURE.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        print(json.dumps({"path": str(FIXTURE), "content_sha256": payload["content_sha256"]}))
    else:
        unittest.main(argv=[sys.argv[0], *remaining])
