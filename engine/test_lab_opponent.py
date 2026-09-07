"""Provisional native-agent policy checks, not strategic admission evidence."""

from dataclasses import FrozenInstanceError
import math
import unittest
from unittest.mock import patch

from actions import RulesAction, RulesState, apply_action, legal_actions
from lab_actions import legal_transitions
from lab_game import LabGame
from lab_opponent import (
    LAB_NATIVE_HASH, LAB_NATIVE_RECIPE, LAB_NATIVE_WEIGHTS,
    LabDecision, choose_lab_decision, evaluate_state, lab_features, lab_native_public,
)
from varde import Illegal


def opened(rules="breath-connection"):
    state = RulesState(LabGame(3, rules=rules))
    apply_action(state, RulesAction("play", state.game.board.points[0]), copy=False)
    return state


def end_by_passes(state):
    apply_action(state, RulesAction("pass"), copy=False)
    apply_action(state, RulesAction("pass"), copy=False)
    return state


class TestLabNativeOpponent(unittest.TestCase):
    def test_metadata_is_detached_weights_and_decisions_are_immutable(self):
        decision = LabDecision(RulesAction("construct", (0, 0), orientation=0))
        payload = decision.to_dict()
        self.assertEqual(payload["recipe"], LAB_NATIVE_RECIPE)
        self.assertEqual(payload["agent_hash"], LAB_NATIVE_HASH)
        self.assertEqual(payload["face"], [0, 0])
        self.assertNotIn("score", payload)
        self.assertNotIn("weights", payload)
        self.assertEqual(len(LAB_NATIVE_HASH), 64)
        payload["face"][0] = 99
        self.assertEqual(decision.action.point, (0, 0))
        metadata = lab_native_public()
        metadata["difficulties"].clear()
        self.assertEqual(lab_native_public()["difficulties"], ["casual", "standard"])
        with self.assertRaises(TypeError):
            LAB_NATIVE_WEIGHTS["occupied_objective"] = 2.0
        with self.assertRaises(FrozenInstanceError):
            decision.nodes = 22

    def test_difficulties_are_legal_deterministic_and_leave_save_untouched(self):
        for difficulty in ("casual", "standard"):
            for rules in ("line-breath", "junction-passage", "junction-planted"):
                with self.subTest(difficulty=difficulty, rules=rules):
                    state = opened(rules)
                    before = state.to_dict()
                    first = choose_lab_decision(state, difficulty, 821)
                    second = choose_lab_decision(RulesState.from_dict(before), difficulty, 821)
                    self.assertIn(first.action, legal_actions(state))
                    self.assertNotEqual(first.action.kind, "pass")
                    self.assertEqual(first.action, second.action)
                    self.assertEqual(first.reason_code, second.reason_code)
                    self.assertEqual(first.nodes, second.nodes)
                    self.assertEqual(state.to_dict(), before)
                    self.assertGreater(first.nodes, 0)
                    self.assertGreaterEqual(first.transition_attempts, first.nodes)

    def test_first_ending_both_seats_accept_and_loaded_intermediate_continues(self):
        state = opened()
        apply_action(state, RulesAction("play", state.game.board.points[-1]), copy=False)
        end_by_passes(state)
        self.assertEqual(state.game.score(), {"B": 0, "W": 0})
        first = choose_lab_decision(state, seed=15)
        self.assertEqual(first.action.kind, "accept")
        apply_action(state, first.action, copy=False)
        self.assertFalse(state.terminal)
        self.assertEqual(len(state.end_acceptances), 1)
        restored = RulesState.from_dict(state.to_dict())
        second = choose_lab_decision(restored, seed=15)
        self.assertEqual(second.action.kind, "accept")
        apply_action(restored, second.action, copy=False)
        self.assertTrue(restored.terminal)
        self.assertEqual(len(restored.end_acceptances), 2)
        with self.assertRaises(Illegal):
            choose_lab_decision(restored)

    def test_losing_actor_resumes_once_then_accepts_the_second_ending(self):
        state = end_by_passes(opened())
        self.assertEqual(state.actor_color, "W")
        self.assertLess(state.game.score()["W"], state.game.score()["B"])
        decision = choose_lab_decision(state)
        self.assertEqual(decision.action.kind, "resume")
        apply_action(state, decision.action, copy=False)
        self.assertFalse(state.game.finished)
        self.assertTrue(state.game.resumption_used)
        end_by_passes(state)
        self.assertEqual(choose_lab_decision(state).action.kind, "accept")
        apply_action(state, RulesAction("accept"), copy=False)
        self.assertTrue(state.terminal)
        self.assertEqual(len(state.end_acceptances), 1)

    def test_pending_end_is_not_an_accepted_terminal_score(self):
        state = end_by_passes(opened())
        pending = evaluate_state(state, "seat-black")
        self.assertLess(abs(pending), 10)
        apply_action(state, RulesAction("accept"), copy=False)
        apply_action(state, RulesAction("accept"), copy=False)
        margin = state.game.score()["B"] - state.game.score()["W"]
        self.assertEqual(evaluate_state(state, "seat-black"), 10 + margin / 54)
        self.assertEqual(evaluate_state(state, "seat-white"), -10 - margin / 54)

    def test_standard_scans_pass_and_takeover_from_original_identity(self):
        import lab_opponent

        state = RulesState(LabGame(3, rules="junction-y"))
        seen = []
        real_evaluate = evaluate_state

        def observe(child, seat):
            seen.append((seat, child.color_for_seat(seat), child.game.consecutive_passes,
                         child.game.swap_decided))
            return real_evaluate(child, seat)

        with patch.object(lab_opponent, "evaluate_state", side_effect=observe):
            choose_lab_decision(state, "standard", seed=31)
        self.assertTrue(all(seat == "seat-black" for seat, *_ in seen))
        self.assertTrue(any(color == "W" and swapped for _, color, _, swapped in seen))
        self.assertTrue(any(passes == 1 for _, _, passes, _ in seen))

    def test_white_takeover_changes_color_but_not_evaluation_identity(self):
        state = opened("junction-six")
        perspective = state.actor_seat
        swapped = apply_action(state, RulesAction("swap"))
        self.assertEqual(perspective, "seat-white")
        self.assertEqual(swapped.color_for_seat(perspective), "B")
        self.assertEqual(swapped.actor_seat, "seat-black")
        expected = sum(value * LAB_NATIVE_WEIGHTS[name]
                       for name, value in lab_features(swapped.game, "B").items())
        self.assertEqual(evaluate_state(swapped, perspective), expected)
        self.assertEqual(evaluate_state(state, perspective), -expected)

    def test_standard_node_count_includes_all_replies_not_only_candidate_roots(self):
        state = RulesState(LabGame(3, rules="go-honeycomb"))
        decision = choose_lab_decision(state, "standard", seed=31)
        roots = legal_transitions(state)
        # Every original opening is legal. Each searched opening has 53 ordinary
        # replies plus legal pass and takeover; no pre-scan adds phantom nodes.
        self.assertEqual(len(roots), 54)
        self.assertEqual(decision.nodes, 54 + 10 * 55)
        self.assertEqual(decision.transition_attempts, decision.nodes)

    def test_invalid_difficulty_seed_and_input_are_rejected(self):
        state = opened()
        for difficulty in ("advanced", "personal", None):
            with self.subTest(difficulty=difficulty), self.assertRaises(ValueError):
                choose_lab_decision(state, difficulty)
        for seed in (True, "1", 1.0):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                choose_lab_decision(state, seed=seed)
        with self.assertRaises(ValueError):
            choose_lab_decision(state.game)
        self.assertTrue(all(math.isfinite(value) for value in lab_features(state.game, "B").values()))

    def test_unused_early_area_score_is_not_computed_but_group_tax_remains(self):
        for rules in ("line-breath", "breath-connection", "junction-y", "go-static-six"):
            state = opened(rules)
            with self.subTest(rules=rules), patch.object(LabGame, "score", side_effect=AssertionError("unused area flood")):
                features = lab_features(state.game, "B")
            self.assertEqual(features["late_empty_area"], 0)
            original = getattr(state.game.board, "original_points", state.game.board.points)
            self.assertEqual(features["occupied_objective"], 1 / len(original))
            self.assertEqual(features["connection_group_tax"], 1 / 54 if rules == "breath-connection" else 0)

    def test_late_area_recovers_actual_group_adjusted_score_exactly(self):
        # Constructed feature-only position, not reachable game evidence.
        game = LabGame(3, rules="breath-connection")
        game.state = {point: ("B",) for point in game.board.points}
        game.state[game.board.points[0]] = ()
        with patch.object(game, "score", wraps=game.score) as score:
            features = lab_features(game, "B")
        self.assertEqual(score.call_count, 1)
        self.assertEqual(features["occupied_objective"], 53 / 54)
        self.assertEqual(features["connection_group_tax"], 1 / 54)
        self.assertEqual(features["late_empty_area"], 1 / 54)


if __name__ == "__main__":
    unittest.main()
