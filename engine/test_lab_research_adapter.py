"""Mechanical adapters only: no proof checker, search, or research cohort."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest.mock import patch

from actions import RulesAction, RulesState, apply_action, legal_actions
from game_factory import new_game
from lab_spec import EXPERIMENT_SPECS
from varde import Illegal

from research.harness import lab_oracle as oracle
from research.harness.lab_research_adapter import (
    LEGACY_CANDIDATES, PRODUCTION_RULESETS, AdapterIntegrityError, ResearchAdapter,
    canonical_action_id, independent_provider, production_provider,
)


def fresh(rules, *, n=3, seed=0):
    return RulesState(new_game(n, rules=rules, experimental=True, research=True, seed=seed))


class TestLabResearchAdapter(unittest.TestCase):
    def test_all_sixteen_production_domains_and_transitions_are_complete_and_detached(self):
        self.assertEqual(LEGACY_CANDIDATES, ("classic", "rosette", "breath", "breath-run", "gjerde", "gjerde-go"))
        self.assertEqual(len(PRODUCTION_RULESETS), 16)
        for rules in PRODUCTION_RULESETS:
            with self.subTest(rules=rules):
                state = fresh(rules)
                before = state.to_dict()
                provider = production_provider(rules)
                self.assertEqual(provider.snapshot(state), before)
                domain = provider.legal_actions(state)
                self.assertEqual(domain, tuple(action.to_dict() for action in legal_actions(state)))
                self.assertEqual(len({canonical_action_id(action) for action in domain}), len(domain))
                child = provider.transition(state, domain[0])
                expected = apply_action(state, RulesAction.from_dict(domain[0]))
                self.assertEqual(child.to_dict(), expected.to_dict())
                self.assertEqual(state.to_dict(), before)
                child.game.history.clear()
                child.seats["B"] = "changed"
                domain[0]["point"][0] += 1000
                self.assertEqual(state.to_dict(), before)
                self.assertEqual(len(provider.fingerprint(state)), 64)
                json.dumps(provider.snapshot(state), allow_nan=False)
                json.dumps(provider.metadata(state), allow_nan=False)

    def test_independent_mechanics_cover_ten_and_explicitly_reject_legacy(self):
        for spec in EXPERIMENT_SPECS:
            with self.subTest(rules=spec.id):
                production = fresh(spec.id, seed=17)
                independent = oracle.new_state(spec.id, seed=getattr(production.game, "topology_seed", 0))
                prod, ref = production_provider(spec.id), independent_provider(spec.id)
                self.assertEqual(prod.rules_hash, ref.rules_hash)
                self.assertNotEqual(prod.implementation_hash, ref.implementation_hash)
                self.assertEqual(prod.legal_actions(production), ref.legal_actions(independent))
                action = prod.legal_actions(production)[0]
                production = prod.transition(production, action)
                independent = ref.transition(independent, action)
                self.assertEqual(prod.snapshot(production), ref.snapshot(independent))
                self.assertEqual(ref.metadata(independent)["provenance"]["mechanics"], "independent-laboratory-oracle")
        for rules in LEGACY_CANDIDATES:
            with self.subTest(rules=rules), self.assertRaisesRegex(ValueError, "legacy.*unsupported"):
                independent_provider(rules)
        for rules in ("breath-cap", "breath-rescue", "not-a-ruleset", None, []):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                production_provider(rules)

    def test_full_json_action_ids_include_all_orientations_and_ignore_key_order(self):
        action = {"action": "construct", "face": [1, 0], "orientation": 0}
        self.assertEqual(canonical_action_id(action), '{"action":"construct","face":[1,0],"orientation":0}')
        self.assertEqual(canonical_action_id(dict(reversed(tuple(action.items())))), canonical_action_id(action))
        self.assertNotEqual(canonical_action_id(action), canonical_action_id(action | {"orientation": 1}))
        for bad in (None, [], {"action": "play", "point": [float("nan"), 0]}, {"action": "play", "point": [float("inf"), 0]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                canonical_action_id(bad)
        for rules, kind, count in (("junction-y", "construct", 2), ("junction-six", "construct", 1),
                                   ("junction-planted", "plant", 2), ("junction-passage", "construct", 3)):
            state = apply_action(fresh(rules), RulesAction("play", (2, 0)))
            provider = production_provider(rules)
            oriented = [wire for wire in provider.legal_actions(state)
                        if wire["action"] == kind and wire["face"] == [0, 0]]
            self.assertEqual({wire["orientation"] for wire in oriented}, set(range(count)))
            self.assertEqual(len({provider.fingerprint(provider.transition(state, wire)) for wire in oriented}), count)

    def test_score_is_accepted_only_and_pie_ending_actors_are_actual_seats(self):
        for factory, make_state in ((production_provider, fresh), (independent_provider, oracle.new_state)):
            state = make_state("junction-y")
            provider = factory("junction-y")
            with self.assertRaisesRegex(ValueError, "accepted"):
                provider.score(state)
            original_seats = provider.seats(state)
            state = provider.transition(state, {"action": "play", "point": [2, 0]})
            state = provider.transition(state, {"action": "swap"})
            self.assertEqual(provider.actor(state), {"seat": original_seats["B"], "color": "W"})
            for kind in ("pass", "pass"):
                state = provider.transition(state, {"action": kind})
            first = provider.actor(state)["seat"]
            state = provider.transition(state, {"action": "accept"})
            self.assertFalse(provider.accepted(state))
            self.assertNotEqual(provider.actor(state)["seat"], first)
            with self.assertRaisesRegex(ValueError, "accepted"):
                provider.score(state)
            state = provider.transition(state, {"action": "resume"})
            for kind in ("pass", "pass", "accept"):
                state = provider.transition(state, {"action": kind})
            self.assertTrue(provider.accepted(state))
            self.assertEqual(provider.actor(state), {"seat": None, "color": None})
            self.assertEqual(provider.legal_actions(state), ())
            self.assertEqual(set(provider.score(state)), {"B", "W"})
        state = fresh("classic")
        with patch.object(state.game, "score", side_effect=AssertionError("must not evaluate")):
            with self.assertRaisesRegex(ValueError, "accepted"):
                production_provider("classic").score(state)

    def test_unattested_snapshots_never_claim_full_action_replay(self):
        for rules in PRODUCTION_RULESETS:
            state = fresh(rules)
            provider = production_provider(rules)
            metadata = provider.metadata(state)
            self.assertFalse(metadata["provenance"]["full_action_replay"])
            self.assertEqual(metadata["provenance"]["origin"], "unattested-state-snapshot")
            self.assertFalse(metadata["provenance"]["historical_seat_acceptances_recorded"])
            metadata["provenance"]["full_action_replay"] = True
            self.assertFalse(provider.metadata(state)["provenance"]["full_action_replay"])
        initial = oracle.new_state("junction-y")
        verified = oracle.replay(initial, ({"action": "play", "point": [2, 0]},))
        self.assertTrue(verified.full_action_replay)
        # Passing only the resulting state loses that external replay evidence.
        self.assertFalse(independent_provider("junction-y").metadata(verified.state)["provenance"]["full_action_replay"])

    def test_analysis_key_uses_full_forbidden_history_not_legacy_compatibility_key(self):
        state = apply_action(fresh("classic"), RulesAction("play", (2, 0)))
        changed = state.clone()
        changed.game.history.remove(next(key for key in changed.game.history
                                         if key != (changed.game.to_move, tuple(changed.game.state[p] for p in changed.game.board.points))))
        self.assertEqual(state.key(), changed.key())
        adapter = ResearchAdapter("classic")
        self.assertNotEqual(adapter.analysis_key(state), adapter.analysis_key(changed))
        self.assertNotEqual(adapter.fingerprint(state), adapter.fingerprint(changed))
        # This altered history is only an identity counterexample, never a game
        # fixture used for a transition, proof or reachability assertion.

    def test_fingerprint_includes_replay_prefix_initial_topology_and_seed(self):
        first, second = fresh("go-static-six", seed=1), fresh("go-static-six", seed=2)
        self.assertEqual(first.analysis_key(), second.analysis_key())
        adapter = ResearchAdapter("go-static-six")
        self.assertNotEqual(adapter.fingerprint(first), adapter.fingerprint(second))
        for state in (first, second):
            child = adapter.transition(state, {"action": "play", "point": [2, 0]})
            self.assertEqual(child.game.topology_seed, state.game.topology_seed)
            self.assertEqual(RulesState.from_dict(child.to_dict()).to_dict(), child.to_dict())
        self.assertEqual(adapter.counters.resolved_transitions, 2)
        first = apply_action(fresh("junction-y"), RulesAction("play", (2, 0)))
        adapter = ResearchAdapter("junction-y")
        for field in ("action_journal", "initial_topology", "topology_seed", "last_capture_waves"):
            changed = first.clone()
            if field == "action_journal":
                changed.game.action_journal.append({"action": "pass"})
            elif field == "initial_topology":
                changed.game.initial_topology = ((0, 0, 0),)
            elif field == "topology_seed":
                changed.game.topology_seed = 19
            else:
                changed.game.last_capture_waves = [[(2, 0)]]
            self.assertEqual(first.analysis_key(), changed.analysis_key())
            self.assertNotEqual(adapter.fingerprint(first), adapter.fingerprint(changed))
        # Modified replay metadata is never advanced or labeled as valid history.

    def test_reachable_superko_is_respected_and_failures_are_not_cached(self):
        state = fresh("go-honeycomb")
        for point in ((-8, 0), (-7, 1), (-8, -2), (-8, 2), (-5, -1), (-5, 1)):
            apply_action(state, RulesAction("play", point), copy=False)
        apply_action(state, RulesAction("pass"), copy=False)
        apply_action(state, RulesAction("play", (-7, -1)), copy=False)
        before = state.to_dict()
        adapter = ResearchAdapter("go-honeycomb")
        forbidden = {"action": "play", "point": [-8, 0]}
        self.assertNotIn(forbidden, adapter.legal_actions(state))
        for _ in range(2):
            with self.assertRaises(Illegal):
                adapter.transition(state, forbidden)
        self.assertEqual(adapter.counters.transition_attempts, 2)
        self.assertEqual(adapter.counters.resolved_transitions, 0)
        self.assertEqual(adapter.counters.cache_hits, 0)
        self.assertEqual(state.to_dict(), before)

    def test_bounded_cache_returns_caller_owned_results_and_immutable_counters(self):
        adapter = ResearchAdapter("junction-y", max_transitions=1)
        state = fresh("junction-y")
        action = {"action": "play", "point": [2, 0]}
        before, wire_before = state.to_dict(), deepcopy(action)
        first = adapter.transition(state, action)
        saved = first.to_dict()
        first.game.history.clear()
        first.game.action_journal[0]["point"][0] = 9000
        first.seats["B"] = "changed"
        second = adapter.transition(state, action)
        self.assertEqual(second.to_dict(), saved)
        self.assertEqual((adapter.counters.transition_attempts, adapter.counters.resolved_transitions,
                          adapter.counters.cache_hits), (1, 1, 1))
        counter = adapter.counters
        with self.assertRaises(FrozenInstanceError):
            counter.cache_hits = 99
        data = counter.to_dict()
        data["cache_hits"] = 99
        self.assertEqual(adapter.counters.cache_hits, 1)
        adapter.transition(second, {"action": "pass"})
        self.assertEqual(adapter.cached_transition_count, 1)
        self.assertEqual(first.game.action_journal[0]["point"][0], 9000)
        self.assertEqual(adapter.transition(state, action).to_dict(), saved)
        self.assertEqual(adapter.counters.resolved_transitions, 3)
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(action, wire_before)
        separate = ResearchAdapter("junction-y")
        self.assertEqual(separate.cached_transition_count, 0)
        self.assertEqual(separate.counters.cache_hits, 0)

    def test_provider_type_rules_guards_and_readonly_descriptor(self):
        provider = production_provider("classic")
        with self.assertRaises(FrozenInstanceError):
            provider.rules_id = "breath"
        for callback in (provider.snapshot, provider.metadata, provider.fingerprint, provider.actor,
                         provider.seats, provider.accepted, provider.legal_actions):
            for wrong in (fresh("breath"), oracle.new_state("junction-y"), {}):
                with self.subTest(callback=callback, wrong=type(wrong)), self.assertRaises(ValueError):
                    callback(wrong)
        for maximum in (0, -1, True, 2.5, "2"):
            with self.assertRaises(ValueError):
                ResearchAdapter("classic", max_transitions=maximum)

    def test_adapter_detects_input_mutation_even_when_callback_fails(self):
        state = fresh("junction-y")
        before = state.to_dict()
        adapter = ResearchAdapter("junction-y")
        def corrupt(source, _action):
            source.game.history.clear()
            raise ValueError("bad provider")
        adapter.provider = replace(adapter.provider, transition=corrupt)
        with self.assertRaisesRegex(AdapterIntegrityError, "mutat"):
            adapter.transition(state, {"action": "play", "point": [2, 0]})
        self.assertEqual(adapter.counters.resolved_transitions, 0)
        self.assertEqual(adapter.cached_transition_count, 0)
        self.assertEqual(state.to_dict(), before)

    def test_generator_failures_and_duplicate_domains_are_guarded_and_detached(self):
        state = fresh("junction-y")
        before = state.to_dict()
        adapter = ResearchAdapter("junction-y")
        def corrupt(source):
            yield {"action": "play", "point": [2, 0]}
            source.game.history.clear()
            raise ValueError("late generator failure")
        adapter.provider = replace(adapter.provider, legal_actions=corrupt)
        with self.assertRaisesRegex(AdapterIntegrityError, "mutat"):
            adapter.legal_actions(state)
        self.assertEqual(state.to_dict(), before)
        adapter.provider = replace(adapter.provider, legal_actions=lambda _: (
            {"action": "construct", "face": [0, 0], "orientation": 0},
            {"orientation": 0, "face": [0, 0], "action": "construct"},
        ))
        with self.assertRaisesRegex(AdapterIntegrityError, "duplicate"):
            adapter.legal_actions(state)
        self.assertEqual(state.to_dict(), before)

    def test_forged_accepted_flags_and_ending_envelopes_are_rejected(self):
        production = fresh("junction-y")
        production.accepted = True
        independent = replace(oracle.new_state("junction-y"), accepted=True)
        for provider, state in ((production_provider("junction-y"), production),
                                (independent_provider("junction-y"), independent)):
            for callback in (provider.accepted, provider.score, provider.snapshot, provider.actor):
                with self.subTest(provider=provider.provider_id, callback=callback), self.assertRaises(ValueError):
                    callback(state)
        state = fresh("classic")
        for action in (RulesAction("play", (2, 0)), RulesAction("pass"), RulesAction("pass")):
            apply_action(state, action, copy=False)
        provider = production_provider("classic")
        corruptions = [
            lambda value: setattr(value, "accepted", True),
            lambda value: setattr(value, "end_decider", None),
            lambda value: value.end_acceptances.add(value.seats["B"]),
            lambda value: setattr(value.game, "consecutive_passes", 0),
        ]
        for corrupt in corruptions:
            invalid = state.clone()
            corrupt(invalid)
            with self.assertRaises(ValueError):
                provider.accepted(invalid)

    def test_legacy_mutable_geometry_cannot_escape_provider_or_cache_ownership(self):
        for rules in ("classic", "gjerde", "line-breath"):
            state = fresh(rules)
            adapter = ResearchAdapter(rules)
            point = state.game.board.points[0]
            neighbors = state.game.board.neighbors[point]
            wire = {"action": "play", "point": list(point)}
            returned = adapter.transition(state, wire)
            original_fingerprint = adapter.fingerprint(returned)
            returned.game.board.neighbors[point] = ()
            self.assertNotEqual(adapter.fingerprint(returned), original_fingerprint)
            self.assertEqual(state.game.board.neighbors[point], neighbors)
            self.assertEqual(adapter.transition(state, wire).game.board.neighbors[point], neighbors)
            provider_result = adapter.provider.transition(state, wire)
            provider_result.game.board.neighbors[point] = ()
            self.assertEqual(state.game.board.neighbors[point], neighbors)


if __name__ == "__main__":
    unittest.main()
