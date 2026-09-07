"""Mechanical transitions/facts only; no actual-game MCTS or terminal proofs."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import pickle
import unittest
from unittest.mock import patch

from actions import RulesAction, RulesState, apply_action, legal_actions
from game_factory import new_game
from lab_game import LabGame
from research.harness.lab_research_adapter import PRODUCTION_RULESETS, production_provider
from research.harness.lab_search_adapter import (
    SearchAdapterIntegrityError, SearchFacts, SearchTransition, SearchTransitionCache,
)
from research.harness.lab_terminal_cert import canonical_json
from varde import has_sky


def position(rules, n=3):
    return RulesState(new_game(n, rules, experimental=True, research=True, seed=17))


def prepared(rules):
    state = position(rules)
    state.game.moves_played = 8
    state.game.swap_decided = True
    return state


def row_for(state, action):
    return next(row for row in SearchTransitionCache(state.game.rules).expand(state) if row.action == action)


class TestLabSearchAdapter(unittest.TestCase):
    def test_all_sixteen_rules_all_sizes_every_transition_matches_frozen_provider(self):
        checked = set()
        for rules in PRODUCTION_RULESETS:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=rules, n=n):
                    state = position(rules, n)
                    saved = pickle.dumps(state, protocol=5)
                    cache, reference = SearchTransitionCache(rules), production_provider(rules)
                    rows = cache.expand(state)
                    self.assertEqual(tuple(row.action for row in rows), reference.legal_actions(state))
                    for row in rows:
                        expected = reference.transition(state, row.action)
                        actual = row.successor()
                        self.assertEqual(reference.snapshot(actual), reference.snapshot(expected))
                        self.assertEqual(reference.fingerprint(actual), reference.fingerprint(expected))
                    self.assertEqual(pickle.dumps(state, protocol=5), saved)
                    checked.add((rules, n))
        self.assertEqual(len(checked), 64)

    def test_each_lab_candidate_resolves_once_and_common_provider_reuses_batch(self):
        state = position("junction-planted")
        cache = SearchTransitionCache("junction-planted")
        with patch.object(LabGame, "legal_placements", side_effect=AssertionError("pre-scan")), \
                patch.object(LabGame, "construction_actions", side_effect=AssertionError("pre-scan")):
            rows = cache.expand(state)
            count = cache.counters.lab_candidate_attempts
            self.assertEqual(count, 54)
            self.assertEqual(len(cache.provider.legal_actions(state)), 54)
            for row in rows:
                self.assertEqual(cache.provider.transition(state, row.action).to_dict(), row.successor().to_dict())
            self.assertEqual(cache.counters.lab_candidate_attempts, count)
            self.assertEqual(cache.counters.batches_resolved, 1)
            self.assertEqual(cache.counters.fact_passes, 54)
            self.assertEqual(cache.counters.successors_returned, 108)

    def test_legacy_domain_enumerates_once_then_only_members_are_applied(self):
        import actions
        state = position("classic")
        cache = SearchTransitionCache("classic")
        with patch("research.harness.lab_search_adapter.legal_actions", wraps=legal_actions) as enumerate_domain, \
                patch.object(actions, "legal_actions", side_effect=AssertionError("nested validation")):
            rows = cache.expand(state)
            for row in rows:
                cache.transition(state, row.action)
            self.assertEqual(enumerate_domain.call_count, 1)
        self.assertEqual(cache.counters.legacy_domain_enumerations, 1)
        self.assertEqual(cache.counters.legacy_candidate_applications, len(rows))
        self.assertEqual(cache.counters.legacy_actions_enumerated, len(rows))
        with self.assertRaises(SearchAdapterIntegrityError):
            cache.transition(state, {"action": "play", "point": [1000, 1000]})
        self.assertEqual(cache.counters.legacy_candidate_applications, len(rows))

    def test_constructed_classic_cover_is_not_a_capture(self):
        state = prepared("classic")
        target = (2, 0)
        state.game.state[target] = ("W",)
        for neighbor in state.game.board.neighbors[target]:
            state.game.state[neighbor] = ("B",)
        row = row_for(state, {"action": "play", "point": list(target)})
        self.assertEqual(row.successor().game.state[target], ("W", "B"))
        self.assertEqual(row.facts.captured_enemy_stones, 0)

    def test_constructed_capture_and_reachable_hub_capture_are_separate(self):
        state = prepared("breath")
        target = (2, 0)
        neighbors = state.game.board.neighbors[target]
        state.game.state[target] = ("W",)
        for neighbor in neighbors[:2]:
            state.game.state[neighbor] = ("B",)
        row = row_for(state, {"action": "play", "point": list(neighbors[2])})
        self.assertEqual((row.facts.captured_original, row.facts.captured_junction), (1, 0))
        state = position("junction-y")
        for action in (RulesAction("play", (2, 0)), RulesAction("construct", (0, 0), orientation=0),
                       RulesAction("play", (-1, 1)), RulesAction("play", (0, 0))):
            apply_action(state, action, copy=False)
        row = row_for(state, {"action": "play", "point": [-1, -1]})
        self.assertEqual((row.facts.captured_original, row.facts.captured_junction), (0, 1))
        self.assertEqual(row.successor().game.topology, ((0, 0, 0),))

    def test_sole_liberty_defense_and_strict_sky_exclusion(self):
        state = prepared("breath")
        for point, color in (((2, 0), "B"), ((1, 1), "W"), ((1, -1), "W")):
            state.game.state[point] = (color,)
        defended = row_for(state, {"action": "play", "point": [4, 0]})
        self.assertEqual(defended.facts.defended_group_count, 1)
        sky = prepared("classic")
        for point, stack in { (2, 0): ("B",), (4, 0): ("B", "B"),
                             (1, 1): ("W", "W"), (1, -1): ("W", "W"),
                             (5, -1): ("W", "W") }.items():
            sky.game.state[point] = stack
        self.assertTrue(has_sky(sky.game.board, sky.game.state, (2, 0), None))
        self.assertEqual(row_for(sky, {"action": "play", "point": [5, 1]}).facts.defended_group_count, 0)

    def test_sky_creation_defends_old_group_without_a_second_ordinary_liberty(self):
        state = prepared("classic")
        for point in ((2, 0), (4, 0), (5, 1)):
            state.game.state[point] = ("B",)
        for point in ((1, 1), (1, -1), (5, -1), (4, 2)):
            state.game.state[point] = ("W", "W")
        self.assertFalse(has_sky(state.game.board, state.game.state, (2, 0), None))
        row = row_for(state, {"action": "play", "point": [4, 0]})
        child = row.successor()
        self.assertTrue(has_sky(child.game.board, child.game.state, (2, 0), (4, 0)))
        self.assertEqual(row.facts.defended_group_count, 1)

    def test_cell_completion_is_net_objective_gain_and_line_breath_is_zero(self):
        for rules, occupied in (("gjerde", 5), ("gjerde-go", 5), ("gjerde-majority", 3), ("line-breath", 5)):
            with self.subTest(rules=rules):
                state = prepared(rules)
                edges = state.game.board.cell_edges[(0, 0)]
                for edge in edges[:occupied]:
                    state.game.state[edge] = ("B",)
                action = {"action": "play", "point": list(edges[occupied])}
                row = row_for(state, action)
                expected = 0 if rules == "line-breath" else max(0, row.successor().game.score()["B"] - state.game.score()["B"])
                self.assertEqual(row.facts.completed_cells, expected)
                if rules != "line-breath":
                    self.assertEqual(expected, 1)

    def test_administration_and_actual_extension_flags(self):
        state = position("breath-run")
        apply_action(state, RulesAction("play", (2, 0)), copy=False)
        swap = row_for(state, {"action": "swap"})
        self.assertEqual(swap.facts, SearchFacts("swap"))
        state = position("breath-run")
        for point in ((2, 0), (1, 1), (-8, 0), (1, -1), (-8, -2), (5, -1)):
            apply_action(state, RulesAction("play", point), copy=False)
        extend = row_for(state, {"action": "extend", "point": [4, 0]})
        self.assertTrue(extend.facts.extension_action)
        extended = extend.successor()
        finish = row_for(extended, {"action": "finish-extension"})
        self.assertEqual(finish.facts, SearchFacts("finish-extension", True))
        state = position("junction-y")
        for action in (RulesAction("play", (2, 0)), RulesAction("pass"), RulesAction("pass")):
            apply_action(state, action, copy=False)
        for row in SearchTransitionCache("junction-y").expand(state):
            self.assertEqual(row.facts, SearchFacts(row.action["action"]))

    def test_full_history_real_ko_and_exact_oriented_membership(self):
        state = position("go-honeycomb")
        for point in ((-8, 0), (-7, 1), (-8, -2), (-8, 2), (-5, -1), (-5, 1)):
            apply_action(state, RulesAction("play", point), copy=False)
        apply_action(state, RulesAction("pass"), copy=False)
        apply_action(state, RulesAction("play", (-7, -1)), copy=False)
        cache = SearchTransitionCache("go-honeycomb")
        self.assertNotIn({"action": "play", "point": [-8, 0]}, cache.legal_actions(state))
        without_history = deepcopy(state)
        without_history.game.history.clear()  # constructed cache-key distinction, never origin evidence
        self.assertIn({"action": "play", "point": [-8, 0]}, cache.legal_actions(without_history))
        self.assertEqual(cache.counters.batches_resolved, 2)
        state = position("junction-passage")
        apply_action(state, RulesAction("play", (2, 0)), copy=False)
        cache = SearchTransitionCache("junction-passage")
        rows = [row for row in cache.expand(state) if row.action.get("face") == [0, 0]]
        self.assertEqual({row.action["orientation"] for row in rows}, {0, 1, 2})
        self.assertEqual(len({row.action_id for row in rows}), 3)

    def test_copies_isolate_legacy_geometry_journals_and_returned_wires(self):
        for rules in ("classic", "junction-y"):
            state, cache = position(rules), SearchTransitionCache(rules, 1)
            row = cache.expand(state)[0]
            original = row.successor()
            returned = row.successor()
            returned.game.history.clear()
            returned.seats["B"] = "changed"
            if rules == "classic":
                returned.game.board.neighbors[returned.game.board.points[0]] = []
            else:
                returned.game.action_journal[0]["point"][0] = 999
            wire = row.action
            wire["point"][0] = 999
            self.assertEqual(pickle.dumps(row.successor()), pickle.dumps(original))
            self.assertEqual(cache.expand(state)[0].action, row.action)
            cache.expand(original)
            self.assertEqual(cache.cached_batches, 1)
            self.assertEqual(row.successor().to_dict(), original.to_dict())

    def test_identity_and_domain_failure_cannot_mutate_caller_or_publish_batch(self):
        for callback in ("fingerprint", "snapshot", "metadata"):
            state, cache = position("classic"), SearchTransitionCache("classic")
            saved = pickle.dumps(state)
            def mutate(value):
                value.game.state[(2, 0)] = ("W",)
                raise RuntimeError("injected failure")
            if callback == "metadata":
                # Base fingerprint invokes its frozen closure metadata; replace
                # fingerprint with an explicit failing metadata path for this guard.
                cache._base = replace(cache._base, fingerprint=mutate)
            else:
                cache._base = replace(cache._base, **{callback: mutate})
            with self.assertRaises(SearchAdapterIntegrityError):
                cache.expand(state)
            self.assertEqual(pickle.dumps(state), saved)
            self.assertEqual(cache.cached_batches, 0)
        state, cache = position("classic"), SearchTransitionCache("classic")
        def corrupt_domain(source):
            yield RulesAction("play", (2, 0))
            source.game.history.clear()
            raise RuntimeError("iterator failed")
        before = pickle.dumps(state)
        with patch("research.harness.lab_search_adapter.legal_actions", corrupt_domain), self.assertRaises(SearchAdapterIntegrityError):
            cache.expand(state)
        self.assertEqual(pickle.dumps(state), before)
        self.assertEqual(cache.cached_batches, 0)
        self.assertEqual(cache.counters.legacy_actions_enumerated, 1)
        self.assertEqual(cache.counters.legacy_candidate_applications, 0)

    def test_fingerprint_collision_and_source_staleness_fail_closed(self):
        cache, state = SearchTransitionCache("classic"), position("classic")
        original = cache._base.fingerprint(state)
        cache._base = replace(cache._base, fingerprint=lambda _: original)
        cache.expand(state)
        altered = deepcopy(state)
        altered.game.players["B"] = "different"
        with self.assertRaises(SearchAdapterIntegrityError):
            cache.expand(altered)
        import research.harness.lab_search_adapter as module
        changed = module._actual_sources()
        changed["engine/actions.py"] = "0" * 64
        with patch.object(module, "_actual_sources", return_value=changed):
            for callback in (cache.identity, lambda: cache.provider, lambda: SearchTransitionCache("classic")):
                with self.assertRaises(SearchAdapterIntegrityError):
                    callback()

    def test_cache_and_facts_strictness_and_identity_capacity(self):
        for value in (0, -1, True, 2.0):
            with self.assertRaises(ValueError):
                SearchTransitionCache("classic", value)
        with self.assertRaises(ValueError):
            SearchTransitionCache("unknown")
        for kwargs in ({"captured_original": True}, {"completed_cells": -1}, {"extension_action": 1}):
            with self.assertRaises(ValueError):
                SearchFacts("play", **kwargs)
        facts = SearchFacts("play")
        with self.assertRaises(FrozenInstanceError):
            facts.captured_original = 1
        self.assertNotEqual(SearchTransitionCache("classic", 1).identity(), SearchTransitionCache("classic", 2).identity())
        cache = SearchTransitionCache("classic", 2)
        with self.assertRaises(AttributeError):
            cache.max_batches = 99
        cache._max_batches = 99  # malicious private drift cannot keep claiming the old configuration
        with self.assertRaises(SearchAdapterIntegrityError):
            cache.identity()
        transition = SearchTransition({"action": "play", "point": [2, 0]}, facts, {"nested": []})
        child = transition.successor()
        child["nested"].append(1)
        self.assertEqual(transition.successor(), {"nested": []})
        self.assertEqual(canonical_json(transition.action), transition.action_id)


if __name__ == "__main__":
    unittest.main()
