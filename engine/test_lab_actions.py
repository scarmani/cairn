"""Product-only checks for single-resolution laboratory transitions."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from actions import RulesAction, RulesState, apply_action, legal_actions
from lab_actions import TransitionCache, legal_transitions
from lab_game import LabGame
from varde import Game, Illegal


class TestLabTransitions(unittest.TestCase):
    def test_first_expansion_matches_shared_actions_without_mutating_parent(self):
        state = RulesState(LabGame(3, rules="junction-planted"))
        before = state.to_dict()
        cache = TransitionCache()
        transitions = legal_transitions(state, cache=cache)
        self.assertEqual(tuple(item.action for item in transitions), legal_actions(state))
        self.assertEqual(cache.legal_transition_count, 54)
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(legal_transitions(state, cache=cache), transitions)
        self.assertEqual(cache.legal_transition_count, 54)
        self.assertEqual(cache.cache_hits, 1)

    def test_returned_successor_mutations_cannot_corrupt_cached_replay(self):
        state = RulesState(LabGame(3, rules="junction-six"))
        apply_action(state, RulesAction("play", state.game.board.points[0]), copy=False)
        cache = TransitionCache()
        transition = next(item for item in legal_transitions(state, cache=cache)
                          if item.action.kind == "construct")
        saved = transition.successor().to_dict()
        child = transition.successor()
        child.game.action_journal[0]["point"][0] += 1000
        child.game.history.clear()
        child.end_acceptances.add("invented")
        child.seats["B"] = "invented"
        self.assertEqual(transition.successor().to_dict(), saved)
        self.assertEqual(RulesState.from_dict(saved).to_dict(), saved)
        again = legal_transitions(state, cache=cache)
        self.assertEqual(next(item for item in again if item.action == transition.action).successor().to_dict(), saved)

    def test_no_legacy_prescan_and_one_resolution_per_generated_placement(self):
        import lab_game

        state = RulesState(LabGame(3, rules="breath-connection"))
        cache = TransitionCache()
        with patch.object(LabGame, "legal_placements", side_effect=AssertionError("pre-scan")), \
                patch.object(LabGame, "construction_actions", side_effect=AssertionError("pre-scan")), \
                patch.object(lab_game, "resolve", wraps=lab_game.resolve) as resolve:
            first = legal_transitions(state, cache=cache)
            self.assertEqual(resolve.call_count, 54)
            for transition in first:
                transition.successor()
            legal_transitions(state, cache=cache)
            self.assertEqual(resolve.call_count, 54)
        self.assertEqual(cache.transition_attempts, 54)

    def test_lru_is_bounded_and_eviction_does_not_invalidate_returned_transitions(self):
        states = [RulesState(LabGame(3, rules=rules)) for rules in (
            "line-breath", "breath-connection", "junction-y",
        )]
        cache = TransitionCache(max_batches=1)
        first = legal_transitions(states[0], cache=cache)
        preserved = first[0].successor().to_dict()
        for state in states[1:]:
            legal_transitions(state, cache=cache)
            self.assertEqual(len(cache._batches), 1)
        self.assertEqual(first[0].successor().to_dict(), preserved)
        self.assertEqual(cache.cache_hits, 0)
        legal_transitions(states[0], cache=cache)
        self.assertEqual(cache.cache_hits, 0)

    def test_actual_reachable_ko_is_not_bypassed(self):
        state = RulesState(LabGame(3, rules="go-honeycomb"))
        for point in ((-8, 0), (-7, 1), (-8, -2), (-8, 2), (-5, -1), (-5, 1)):
            apply_action(state, RulesAction("play", point), copy=False)
        apply_action(state, RulesAction("pass"), copy=False)
        apply_action(state, RulesAction("play", (-7, -1)), copy=False)
        forbidden = RulesAction("play", (-8, 0))
        before = deepcopy(state.to_dict())
        with self.assertRaisesRegex(Illegal, "repetition"):
            apply_action(state, forbidden, validate=False)
        self.assertNotIn(forbidden, [item.action for item in legal_transitions(state)])
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(RulesState.from_dict(before).to_dict(), before)

    def test_rejects_legacy_games_and_invalid_capacity(self):
        with self.assertRaises(ValueError):
            legal_transitions(RulesState(Game(3)))
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                TransitionCache(value)


if __name__ == "__main__":
    unittest.main()
