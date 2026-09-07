"""Independent importer provenance and isolation; no research proof searches."""

import ast
from copy import deepcopy
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from actions import RulesAction, RulesState, apply_action
from game_factory import new_game
from lab_spec import EXPERIMENT_SPECS
import lab_game
import lab_graph
import varde


def mechanical_sequence(spec):
    """Short legal interface exercise, not a sampled or certified research game."""
    actions = [{"action": "play", "point": [2, 0]}, {"action": "swap"}]
    if "construct" in spec.supported_actions:
        actions.append({"action": "construct", "face": [0, 0], "orientation": 0})
    elif "plant" in spec.supported_actions:
        actions.append({"action": "plant", "face": [0, 0], "orientation": 0})
    return actions


class TestLabOracleProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = importlib.import_module("research.harness.lab_oracle")

    def short_game(self, spec, n=3):
        state = RulesState(new_game(n, rules=spec.id, experimental=True, research=True, seed=73))
        actions = mechanical_sequence(spec)
        # The canonical line geometry label is checked against actual metadata,
        # with a legal original point selected before any transition is applied.
        if spec.id in ("line-breath", "gjerde-majority"):
            actions[0]["point"] = list(state.game.board.points[0])
        for action in actions:
            apply_action(state, RulesAction.from_dict(action), copy=False)
        return state, actions

    def test_snapshot_replay_matches_all_definitions_and_reports_limited_provenance(self):
        for spec in EXPERIMENT_SPECS:
            for n in (3, 6):
                with self.subTest(rules=spec.id, n=n):
                    state, _actions = self.short_game(spec, n)
                    payload = state.to_dict()
                    before = deepcopy(payload)
                    imported = self.oracle.load_snapshot(payload)
                    self.assertEqual(imported.state.to_dict(), payload)
                    self.assertTrue(imported.mechanical_journal_verified)
                    self.assertTrue(imported.current_envelope_verified)
                    self.assertFalse(imported.full_action_replay)
                    self.assertTrue(imported.assumptions)
                    self.assertEqual(len(imported.input_sha256), 64)
                    self.assertEqual(payload, before)
                    payload["journal"].clear()
                    payload["stacks"][0].append("W")
                    self.assertEqual(imported.state.to_dict(), before)

    def test_complete_seat_replay_and_snapshot_import_are_not_conflated(self):
        for rules in ("junction-y", "junction-planted", "junction-passage"):
            spec = next(item for item in EXPERIMENT_SPECS if item.id == rules)
            state, actions = self.short_game(spec)
            suffix = ["pass", "pass", "accept", "resume", "pass", "pass", "accept"]
            for kind in suffix:
                wire = {"action": kind}
                apply_action(state, RulesAction.from_dict(wire), copy=False)
                actions.append(wire)
            # The public factory uses the seed only for prebuilt controls.
            # Replay the actual initial metadata, not an unused request value.
            initial = self.oracle.new_state(rules, 3, seed=state.game.topology_seed)
            checked = self.oracle.replay(initial, actions)
            self.assertTrue(checked.full_action_replay)
            self.assertEqual(len(checked.actor_trace), len(actions))
            self.assertTrue(checked.state.terminal)
            self.assertEqual(checked.state.to_dict(), state.to_dict())
            imported = self.oracle.load_snapshot(state.to_dict())
            self.assertFalse(imported.full_action_replay)
            self.assertTrue(imported.current_envelope_verified)
            self.assertTrue(imported.assumptions)
            self.assertEqual(imported.state.to_dict(), checked.state.to_dict())

    def test_aliases_are_versioned_and_never_change_input(self):
        state, _actions = self.short_game(next(s for s in EXPERIMENT_SPECS if s.id == "junction-y"))
        canonical = state.to_dict()
        for identifier in ("varde-game", "cairn-game"):
            payload = deepcopy(canonical)
            payload["format"] = identifier
            before = deepcopy(payload)
            self.assertEqual(self.oracle.load_snapshot(payload).state.to_dict(), canonical)
            self.assertEqual(payload, before)
        for key, value in (("format", "unknown-game"), ("version", 1),
                           ("version", True), ("rules_revision", "99.0")):
            payload = deepcopy(canonical)
            payload[key] = value
            with self.assertRaises(ValueError):
                self.oracle.load_snapshot(payload)

    def test_missing_extra_duplicate_or_changed_history_is_not_repaired(self):
        state, _actions = self.short_game(next(s for s in EXPERIMENT_SPECS if s.id == "junction-passage"))
        source = state.to_dict()
        mutations = []
        missing = deepcopy(source)
        missing["history"].pop(0)
        mutations.append(missing)
        duplicate = deepcopy(source)
        duplicate["history"].append(deepcopy(duplicate["history"][0]))
        mutations.append(duplicate)
        future = deepcopy(source)
        future["history"][0]["topology"] = [[0, 0, 0], [1, 0, 0]]
        mutations.append(future)
        changed = deepcopy(source)
        changed["history"][-1]["to_move"] = "B" if changed["history"][-1]["to_move"] == "W" else "W"
        mutations.append(changed)
        for index, payload in enumerate(mutations):
            with self.subTest(mutation=index):
                before = deepcopy(payload)
                with self.assertRaises(ValueError):
                    self.oracle.load_snapshot(payload)
                self.assertEqual(payload, before)

    def test_integer_boolean_journal_and_envelope_tampering_fail_closed(self):
        state, _actions = self.short_game(next(s for s in EXPERIMENT_SPECS if s.id == "junction-planted"))
        source = state.to_dict()
        for field in ("n", "moves_played", "placements_played", "constructions_played",
                      "consecutive_passes", "quiet_moves", "topology_seed"):
            # Seeds may be any integer; a negative seed is not malformed.
            values = (True, "3", 3.0) if field == "topology_seed" else (True, -1, "3", 3.0)
            for value in values:
                payload = deepcopy(source)
                payload[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.oracle.load_snapshot(payload)
        mutations = []
        wrong_journal = deepcopy(source)
        wrong_journal["journal"][-1]["orientation"] = 1
        mutations.append(wrong_journal)
        unexpected = deepcopy(source)
        unexpected["invented_flag"] = False
        mutations.append(unexpected)
        accepted = deepcopy(source)
        accepted["rules_state"]["accepted"] = True
        mutations.append(accepted)
        repeated_seat = deepcopy(source)
        repeated_seat["rules_state"]["seats"]["W"] = repeated_seat["rules_state"]["seats"]["B"]
        mutations.append(repeated_seat)
        for payload in mutations:
            with self.assertRaises(ValueError):
                self.oracle.load_snapshot(payload)

    def test_no_production_imports_or_runtime_capture_geometry_dependency(self):
        module_path = Path(self.oracle.__file__)
        paths = [module_path]
        geometry_path = module_path.with_name("lab_oracle_geometry.py")
        if geometry_path.exists():
            paths.append(geometry_path)
        for path in paths:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    for name in names:
                        allowed = name.split(".")[0] in sys.stdlib_module_names or name in (
                            "research.harness.lab_oracle_geometry", "lab_oracle_geometry",
                        )
                        self.assertTrue(allowed, f"non-independent import {name} in {path.name}")
        with patch.object(varde, "resolve", side_effect=AssertionError("production resolution")), \
                patch.object(varde, "groups_of", side_effect=AssertionError("production groups")), \
                patch.object(varde.Board, "__init__", side_effect=AssertionError("production board")), \
                patch.object(lab_graph, "graph_board", side_effect=AssertionError("production graph")), \
                patch.object(lab_game.LabGame, "from_dict", side_effect=AssertionError("production loader")), \
                patch.object(lab_game.LabGame, "score", side_effect=AssertionError("production score")):
            state = self.oracle.new_state("junction-y", 3)
            first = self.oracle.transition(state, {"action": "play", "point": [2, 0]}).state
            built = self.oracle.transition(first, {"action": "construct", "face": [0, 0], "orientation": 0}).state
            self.assertEqual(built.at((0, 0)), None)
            self.assertEqual(self.oracle.score(built), {"B": 54, "W": 0})
            self.assertEqual(self.oracle.load_snapshot(built.to_dict()).state.to_dict(), built.to_dict())


if __name__ == "__main__":
    unittest.main()
