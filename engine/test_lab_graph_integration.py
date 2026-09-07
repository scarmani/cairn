"""Graph game/factory/save integration; no strategic or optimal-action labels."""

from copy import deepcopy
import pickle
import unittest

from actions import RulesAction, RulesState, apply_action, legal_actions
from game_factory import load_game, new_game
from lab_graph import seeded_static_topology
from varde import BLACK, WHITE, Illegal


EMPTY_JUNCTIONS = ("junction-y", "junction-six")
CONTROLS = ("go-honeycomb", "go-static-y", "go-static-six")


class TestLabGraphIntegration(unittest.TestCase):
    def test_explicit_factory_selection_all_sizes_and_static_opening(self):
        for rules in EMPTY_JUNCTIONS + CONTROLS:
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    game = new_game(n, rules=rules, experimental=True, research=rules in CONTROLS, seed=37)
                    self.assertEqual(game.rules, rules)
                    self.assertEqual(len(game.board.original_points), 6 * n * n)
                    self.assertEqual(set(game.legal_placements()), set(game.board.original_points))
                    self.assertEqual(game.construction_actions(), ())
                    self.assertEqual(game.score(), {BLACK: 0, WHITE: 0})
                    self.assertEqual(game.constructions_played, 0)
                    if rules == "go-static-y":
                        self.assertEqual(game.board.topology, seeded_static_topology(n, "y", 37))
                        self.assertEqual(len(game.board.active_centers), len(game.board.faces))
                    elif rules == "go-static-six":
                        self.assertEqual(game.board.topology, seeded_static_topology(n, "six", 37))
                    else:
                        self.assertEqual(game.board.topology, ())
                    for point in game.board.active_centers:
                        with self.assertRaises(Illegal):
                            game.play(point)
                    self.assertEqual(load_game(game.to_dict()).to_dict(), game.to_dict())

    def test_construction_is_an_atomic_turn_and_resets_passes(self):
        for rules in EMPTY_JUNCTIONS:
            game = new_game(3, rules=rules, experimental=True)
            before = game.to_dict()
            with self.assertRaises(Illegal):
                game.construct((0, 0), 0)
            self.assertEqual(game.to_dict(), before)
            game.play((2, 0))
            game.play_pass()
            self.assertEqual(game.consecutive_passes, 1)
            game.construct((0, 0), 0)
            self.assertEqual(game.to_move, WHITE)
            self.assertEqual(game.moves_played, 3)
            self.assertEqual(game.placements_played, 1)
            self.assertEqual(game.constructions_played, 1)
            self.assertEqual(game.consecutive_passes, 0)
            self.assertEqual(game.quiet_moves, 0)
            self.assertFalse(game.swap_available)
            self.assertEqual(game.state[(0, 0)], ())
            self.assertEqual(game.topology, ((0, 0, 0),))
            self.assertEqual(game.action_journal[-1], {"action": "construct", "face": [0, 0], "orientation": 0})

    def test_failed_build_cannot_mutate_graph_history_or_counters(self):
        for rules in EMPTY_JUNCTIONS:
            game = new_game(3, rules=rules, experimental=True)
            game.play((2, 0))
            game.construct((0, 0), 0)
            before, board = game.to_dict(), game.board
            for face, orientation in (((0, 0), 0), ((0, 0), 1), ((99, 0), 0), ((True, 0), 0), ((1, 0), True), ((1, 0), 9)):
                with self.subTest(rules=rules, face=face, orientation=orientation):
                    with self.assertRaises(Illegal):
                        game.construct(face, orientation)
                    self.assertIs(game.board, board)
                    self.assertEqual(game.to_dict(), before)

    def test_graph_snapshots_and_historical_widths_round_trip(self):
        for rules in EMPTY_JUNCTIONS:
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    game = new_game(n, rules=rules, experimental=True)
                    game.play((2, 0))
                    game.construct((0, 0), 0)
                    game.construct((1, -1), 1 if rules == "junction-y" else 0)
                    game.play((0, 0))
                    payload = game.to_dict()
                    self.assertEqual({len(record["stacks"]) for record in payload["history"]}, {6*n*n, 6*n*n+1, 6*n*n+2})
                    for format_id in ("varde-game", "cairn-game"):
                        restored = load_game(payload | {"format": format_id})
                        self.assertEqual(restored.to_dict(), payload)
                        self.assertEqual(restored.repetition_key(), game.repetition_key())
                        self.assertEqual(restored.legal_placements(), game.legal_placements())
                        self.assertEqual(restored.construction_actions(), game.construction_actions())
                    copied = pickle.loads(pickle.dumps(game))
                    self.assertEqual(copied.to_dict(), payload)
                    self.assertIs(copied.board, game.board)

    def test_graph_history_and_initial_topology_tampering_is_rejected(self):
        game = new_game(3, rules="junction-y", experimental=True)
        game.play((2, 0))
        game.construct((0, 0), 0)
        game.construct((1, -1), 1)
        original = game.to_dict()
        altered = []
        bad = deepcopy(original)
        bad["history"].pop(0)
        altered.append(bad)
        bad = deepcopy(original)
        bad["topology"] = [[0, 0, 1], [1, -1, 1]]
        altered.append(bad)
        bad = deepcopy(original)
        bad["initial_topology"] = [[0, 0, 0]]
        altered.append(bad)
        bad = deepcopy(original)
        next(record for record in bad["history"] if record["topology"])["topology"].append([2, 0, 0])
        altered.append(bad)
        bad = deepcopy(original)
        bad["journal"][1]["orientation"] = 1
        altered.append(bad)
        for payload in altered:
            with self.assertRaises(ValueError):
                load_game(payload)
        for seed in (True, "37", None, 37.0):
            with self.assertRaises(ValueError):
                new_game(3, rules="go-static-y", research=True, seed=seed)
        static = new_game(3, rules="go-static-y", research=True, seed=37).to_dict()
        static["topology_seed"] = 38
        with self.assertRaises(ValueError):
            load_game(static)

    def test_zero_point_center_does_not_add_occupied_area(self):
        for rules in ("go-static-y", "go-static-six"):
            game = new_game(3, rules=rules, research=True)
            game.play((2, 0))
            self.assertEqual(game.score(), {BLACK: 54, WHITE: 0})
            game.play((0, 0))
            self.assertEqual(game.control_count(), {BLACK: 1, WHITE: 1})
            self.assertEqual(game.score(), {BLACK: 1, WHITE: 0})

    def test_shared_actions_pie_and_both_ending_decisions_after_construction(self):
        for rules in EMPTY_JUNCTIONS:
            original = RulesState.from_game(new_game(3, rules=rules, experimental=True))
            first = apply_action(original, RulesAction("play", (2, 0)))
            swapped = apply_action(first, RulesAction("swap"))
            action = RulesAction("construct", (0, 0), orientation=0)
            self.assertIn(action, legal_actions(swapped))
            built = apply_action(swapped, action)
            self.assertEqual(original.game.topology, ())
            self.assertEqual(swapped.game.topology, ())
            self.assertEqual(built.seats, {BLACK: "seat-white", WHITE: "seat-black"})
            self.assertNotEqual(built.analysis_key(), swapped.analysis_key())
            built = apply_action(built, RulesAction("pass"))
            built = apply_action(built, RulesAction("pass"))
            first_accepts = apply_action(built, RulesAction("accept"))
            restored = RulesState.from_dict(first_accepts.to_dict())
            self.assertFalse(restored.terminal)
            self.assertEqual(restored.analysis_key(), first_accepts.analysis_key())
            resumed = apply_action(restored, RulesAction("resume"))
            self.assertEqual(resumed.game.topology, ((0, 0, 0),))
            resumed = apply_action(resumed, RulesAction("pass"))
            resumed = apply_action(resumed, RulesAction("pass"))
            self.assertTrue(apply_action(resumed, RulesAction("accept")).terminal)

    def test_fixed_scoring_version_two_shape_is_preserved(self):
        for rules in ("line-breath", "gjerde-majority", "breath-connection"):
            payload = new_game(3, rules=rules, experimental=True).to_dict()
            self.assertNotIn("topology_seed", payload)
            self.assertNotIn("initial_topology", payload)
            self.assertEqual(load_game(payload).to_dict(), payload)


if __name__ == "__main__":
    unittest.main()
