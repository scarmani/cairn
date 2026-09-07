"""Independent adapter checks only; no game proof, search or admission run."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from actions import RulesAction, RulesState, apply_action
from game_factory import new_game
from lab_spec import EXPERIMENT_SPECS
from varde import Illegal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.harness import lab_oracle as oracle  # noqa: E402
from research.harness.lab_research_adapter import (  # noqa: E402
    ResearchAdapter, canonical_action_id, independent_provider, production_provider,
)


def wire(kind, point=None, orientation=None):
    return RulesAction(kind, point, orientation=orientation).to_dict()


class TestIndependentResearchAdapters(unittest.TestCase):
    def test_canonical_provider_type_imports_from_external_working_directory(self):
        harness = str(Path(__file__).resolve().parents[1] / "research" / "harness")
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import lab_research_adapter as adapter; "
            "from research.harness.lab_terminal_cert import TerminalProvider; "
            "assert isinstance(adapter.production_provider('classic'), TerminalProvider); "
            "assert isinstance(adapter.independent_provider('junction-y'), TerminalProvider)"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-c", script, harness], cwd=directory,
                                    text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_both_providers_represent_takeover_and_both_ending_seats(self):
        for spec in EXPERIMENT_SPECS:
            with self.subTest(rules=spec.id):
                state = RulesState(new_game(3, spec.id, research=True))
                other = oracle.new_state(spec.id)
                production = production_provider(spec.id)
                independent = independent_provider(spec.id)
                opening = getattr(state.game.board, "original_points", state.game.board.points)[0]
                actions = (wire("play", opening), wire("swap"), wire("pass"),
                           wire("pass"), wire("accept"), wire("resume"),
                           wire("pass"), wire("pass"), wire("accept"))
                for index, action in enumerate(actions):
                    before = deepcopy(state.to_dict())
                    oracle_before = deepcopy(other.to_dict())
                    self.assertFalse(production.accepted(state))
                    self.assertFalse(independent.accepted(other))
                    with self.assertRaises(ValueError):
                        production.score(state)
                    with self.assertRaises(ValueError):
                        independent.score(other)
                    self.assertEqual(production.actor(state), independent.actor(other))
                    self.assertEqual(production.seats(state), independent.seats(other))
                    self.assertEqual(
                        {canonical_action_id(a) for a in production.legal_actions(state)},
                        {canonical_action_id(a) for a in independent.legal_actions(other)},
                    )
                    child = production.transition(state, action)
                    oracle_child = independent.transition(other, action)
                    self.assertEqual(state.to_dict(), before)
                    self.assertEqual(other.to_dict(), oracle_before)
                    self.assertEqual(child.to_dict(), oracle_child.to_dict())
                    if index == 4:
                        self.assertTrue(child.game.finished)
                        self.assertFalse(child.accepted)
                        self.assertEqual(child.actor_seat, "seat-white")
                    if index == 5:
                        self.assertFalse(child.game.finished)
                        self.assertEqual(child.game.to_move, state.game.to_move)
                    state, other = child, oracle_child
                self.assertTrue(production.accepted(state))
                self.assertTrue(independent.accepted(other))
                self.assertEqual(production.actor(state), {"seat": None, "color": None})
                self.assertEqual(production.score(state), independent.score(other))
                self.assertEqual(tuple(production.legal_actions(state)), ())
                self.assertEqual(tuple(independent.legal_actions(other)), ())

    def test_oriented_cache_results_cannot_be_mutated_through_returned_states(self):
        cases = (("junction-y", "construct", 2), ("junction-six", "construct", 1),
                 ("junction-planted", "plant", 2), ("junction-passage", "construct", 3))
        for rules, kind, orientations in cases:
            with self.subTest(rules=rules):
                state = RulesState(new_game(3, rules, experimental=True))
                state = apply_action(state, RulesAction("play", (2, 0)))
                adapter = ResearchAdapter(rules, max_transitions=8)
                before = deepcopy(state.to_dict())
                expected_ids = set()
                for orientation in range(orientations):
                    action = wire(kind, (0, 0), orientation)
                    expected_ids.add(canonical_action_id(action))
                    result = adapter.transition(state, action)
                    expected = deepcopy(result.to_dict())
                    result.game.state[(2, 0)] = ()
                    result.seats["B"] = "caller-corruption"
                    action["orientation"] = 999
                    repeated = adapter.transition(state, wire(kind, (0, 0), orientation))
                    self.assertEqual(repeated.to_dict(), expected)
                    self.assertIsNot(repeated, result)
                    self.assertEqual(state.to_dict(), before)
                self.assertEqual(len(expected_ids), orientations)
                first_domain = adapter.legal_actions(state)
                first_domain[0]["caller-field"] = True
                self.assertTrue(all("caller-field" not in a for a in adapter.legal_actions(state)))
                self.assertEqual(state.to_dict(), before)

    def test_reachable_ko_is_not_reintroduced_by_uncached_or_cached_adapters(self):
        rules = "go-honeycomb"
        state = RulesState(new_game(3, rules, research=True))
        independent = oracle.new_state(rules)
        prod = production_provider(rules)
        reference = independent_provider(rules)
        adapter = ResearchAdapter(rules)
        actions = [wire("play", point) for point in
                   ((-8, 0), (-7, 1), (-8, -2), (-8, 2), (-5, -1), (-5, 1))]
        actions.extend((wire("pass"), wire("play", (-7, -1))))
        for action in actions:
            cached = adapter.transition(state, action)
            state = prod.transition(state, action)
            independent = reference.transition(independent, action)
            self.assertEqual(cached.to_dict(), state.to_dict())
            self.assertEqual(state.to_dict(), independent.to_dict())
        recapture = wire("play", (-8, 0))
        before = deepcopy(state.to_dict())
        oracle_before = deepcopy(independent.to_dict())
        for provider, source in ((prod, state), (reference, independent)):
            self.assertNotIn(canonical_action_id(recapture),
                             {canonical_action_id(a) for a in provider.legal_actions(source)})
            with self.assertRaises((ValueError, Illegal)):
                provider.transition(source, recapture)
        with self.assertRaises((ValueError, Illegal)):
            adapter.transition(state, recapture)
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(independent.to_dict(), oracle_before)

    def test_real_legacy_histories_distinguish_identical_current_boards(self):
        # Both action trails are actually replayed, not invented forbidden keys.
        for rules in ("classic", "rosette", "breath", "breath-run"):
            with self.subTest(rules=rules):
                trails = (((-8, -2), (8, 0), (-8, 0), (8, 2)),
                          ((-8, 0), (8, 2), (-8, -2), (8, 0)))
                positions = []
                for trail in trails:
                    state = RulesState(new_game(3, rules))
                    for point in trail:
                        state = apply_action(state, RulesAction("play", point))
                    positions.append(state)
                left, right = positions
                self.assertEqual(left.game.state, right.game.state)
                self.assertEqual(left.key(), right.key())
                self.assertNotEqual(left.game.history, right.game.history)
                adapter = ResearchAdapter(rules)
                self.assertNotEqual(adapter.analysis_key(left), adapter.analysis_key(right))
                self.assertNotEqual(adapter.fingerprint(left), adapter.fingerprint(right))
                self.assertEqual(adapter.transition(left, wire("pass")).game.history,
                                 apply_action(left, RulesAction("pass")).game.history)
                self.assertEqual(adapter.transition(right, wire("pass")).game.history,
                                 apply_action(right, RulesAction("pass")).game.history)


if __name__ == "__main__":
    unittest.main()
