"""Independent native-agent mechanics, not admission or strategic evidence.

Feature-only positions and forbidden-history injections are explicitly constructed
invariants. They are not claimed reachable or exported as research certificates.
"""

from collections import Counter
from copy import deepcopy
from dataclasses import FrozenInstanceError
import math
import unittest
from unittest.mock import patch

from actions import RulesAction, RulesState, apply_action, legal_actions
from game_factory import new_game
from lab_actions import TransitionCache, legal_transitions
from lab_game import LabGame
from lab_graph import GraphBoard, graph_board
from lab_opponent import (
    LAB_NATIVE_WEIGHTS, choose_lab_decision, evaluate_state, lab_features,
    lab_native_public,
)
from lab_spec import EXPERIMENT_SPECS, LAB_SPECS
import server
from varde import BLACK, WHITE, other


def position(rules, n=3, *, seed=17, opening=True):
    game = new_game(n, rules=rules, experimental=True, research=True, seed=seed)
    state = RulesState(game)
    if opening:
        originals = getattr(game.board, "original_points", game.board.points)
        apply_action(state, RulesAction("play", originals[0]), copy=False)
        apply_action(state, RulesAction("play", originals[-1]), copy=False)
    return state


def deterministic_fields(decision):
    fields = decision.to_dict()
    fields.pop("elapsed_ms", None)
    return fields


def spatial_image(game, spec, turns, reflected):
    """Transform a mechanical feature fixture, not a seed-generated new setup."""
    def point_image(point):
        x, y = point
        if reflected:
            y = -y
        for _ in range(turns):
            x, y = (x - 3 * y) // 2, (x + y) // 2
        return x, y

    def face_image(face):
        q, r = face
        if reflected:
            r = -q - r
        for _ in range(turns):
            q, r = -r, q + r
        return q, r

    target = game.clone()
    if isinstance(game.board, GraphBoard):
        topology = []
        for q, r, orientation in game.topology:
            indices = {
                ((-index if reflected else index) + turns) % 6
                for index in spec.orientation_sets[orientation]
            }
            mapped = next(i for i, option in enumerate(spec.orientation_sets) if set(option) == indices)
            topology.append((*face_image((q, r)), mapped))
        target.board = graph_board(game.board.n, game.board.spoke_family, topology)
        target.topology = target.board.topology
    transformed = {point_image(point): stack for point, stack in game.state.items()}
    target.state = {point: transformed[point] for point in target.board.points}
    return target


class TestLabNativeInvariants(unittest.TestCase):
    def test_every_ruleset_and_difficulty_is_legal_deterministic_and_nonmutating(self):
        for spec in EXPERIMENT_SPECS:
            state = position(spec.id)
            before = state.to_dict()
            allowed = set(legal_actions(state))
            for difficulty in ("casual", "standard"):
                with self.subTest(rules=spec.id, difficulty=difficulty):
                    first = choose_lab_decision(state, difficulty=difficulty, seed=419)
                    second = choose_lab_decision(state.clone(), difficulty=difficulty, seed=419)
                    self.assertIn(first.action, allowed)
                    self.assertEqual(first.action, second.action)
                    self.assertEqual(deterministic_fields(first), deterministic_fields(second))
                    self.assertTrue(first.to_dict()["provisional"])
                    self.assertNotIn("score", first.to_dict())
                    self.assertNotIn("weights", first.to_dict())
                    self.assertEqual(state.to_dict(), before)
                    with self.assertRaises((FrozenInstanceError, AttributeError)):
                        first.action = RulesAction("pass")

    def test_transition_sets_match_real_adapter_on_every_size_and_ruleset(self):
        for spec in EXPERIMENT_SPECS:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=spec.id, n=n):
                    state = position(spec.id, n)
                    before = state.to_dict()
                    transitions = legal_transitions(state)
                    self.assertEqual({t.action for t in transitions}, set(legal_actions(state)))
                    self.assertEqual(len(transitions), len({t.action for t in transitions}))
                    self.assertEqual(state.to_dict(), before)

    def test_features_are_finite_bounded_and_exactly_color_symmetric_on_all_sizes(self):
        for spec in EXPERIMENT_SPECS:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=spec.id, n=n):
                    state = position(spec.id, n)
                    originals = getattr(state.game.board, "original_points", state.game.board.points)
                    apply_action(state, RulesAction("play", originals[len(originals) // 2]), copy=False)
                    before = state.to_dict()
                    black = lab_features(state.game, BLACK)
                    white = lab_features(state.game, WHITE)
                    self.assertEqual(set(black), set(LAB_NATIVE_WEIGHTS) - {"capture_transition"})
                    reversed_game = state.game.clone()
                    reversed_game.state = {
                        p: tuple(other(color) for color in stack)
                        for p, stack in state.game.state.items()
                    }
                    flipped = lab_features(reversed_game, BLACK)
                    for name, value in black.items():
                        self.assertTrue(math.isfinite(value), name)
                        self.assertLessEqual(abs(value), 1, name)
                        self.assertEqual(value, -white[name], name)
                        self.assertEqual(flipped[name], white[name], name)
                    self.assertEqual(state.to_dict(), before)

    def test_group_tax_rewards_connection_without_a_per_group_liberty_reward(self):
        state = position("breath-connection", opening=False)
        game = state.game
        points = len(game.board.points)
        game.state[(2, 0)] = (BLACK,)
        game.state[(-1, 1)] = (BLACK,)
        disconnected = lab_features(game, BLACK)
        value = evaluate_state(state, state.seats[BLACK])
        self.assertEqual(disconnected["occupied_objective"], 2 / points)
        self.assertEqual(disconnected["connection_group_tax"], 2 / points)
        self.assertEqual(disconnected["liberty_health"], 2 / points)
        self.assertEqual(disconnected["late_empty_area"], 0)
        game.state[(-1, 1)] = ()
        game.state[(1, 1)] = (BLACK,)
        connected = lab_features(game, BLACK)
        self.assertEqual(connected["connection_group_tax"], 1 / points)
        self.assertEqual(connected["liberty_health"], disconnected["liberty_health"])
        self.assertAlmostEqual(evaluate_state(state, state.seats[BLACK]) - value, 1 / points)

    def test_feature_values_respect_rotations_and_reflections_of_stored_topology(self):
        for spec in EXPERIMENT_SPECS:
            state = position(spec.id)
            originals = getattr(state.game.board, "original_points", state.game.board.points)
            apply_action(state, RulesAction("play", originals[len(originals) // 2]), copy=False)
            if "construct" in spec.supported_actions or "plant" in spec.supported_actions:
                kind = "plant" if "plant" in spec.supported_actions else "construct"
                apply_action(state, RulesAction(kind, (1, 0), orientation=0), copy=False)
            expected = lab_features(state.game, BLACK)
            before = state.to_dict()
            for turns in range(6):
                for reflected in (False, True):
                    with self.subTest(rules=spec.id, turns=turns, reflected=reflected):
                        transformed = spatial_image(state.game, spec, turns, reflected)
                        self.assertEqual(lab_features(transformed, BLACK), expected)
            self.assertEqual(state.to_dict(), before)

    def test_majority_uses_cells_and_keeps_line_control_separate(self):
        state = position("gjerde-majority", opening=False)
        game = state.game
        edges = game.board.cell_edges[(0, 0)]
        cells, points = len(game.board.cells), len(game.board.points)
        for edge in edges[:3]:
            game.state[edge] = (BLACK,)
        three = lab_features(game, BLACK)
        self.assertEqual(three["majority_owned"], 0)
        self.assertEqual(three["majority_three_edges"], 1 / cells)
        self.assertEqual(three["majority_line_control"], 3 / points)
        self.assertEqual(three["occupied_objective"], 0)
        self.assertEqual(three["late_empty_area"], 0)
        game.state[edges[3]] = (BLACK,)
        four = lab_features(game, BLACK)
        self.assertEqual(four["majority_owned"], 1 / cells)
        self.assertEqual(four["majority_line_control"], 4 / points)
        self.assertEqual(game.score(), {BLACK: 1, WHITE: 0})

    def test_zero_point_hub_has_no_occupied_or_liberty_health_mass(self):
        for rules, action in (("junction-y", "construct"), ("junction-planted", "plant")):
            with self.subTest(rules=rules):
                state = position(rules)
                before = lab_features(state.game, BLACK)
                apply_action(state, RulesAction(action, (0, 0), orientation=0), copy=False)
                if action == "construct":
                    apply_action(state, RulesAction("play", (0, 0)), copy=False)
                after = lab_features(state.game, BLACK)
                self.assertTrue(state.game.state[(0, 0)])
                self.assertEqual(after["occupied_objective"], before["occupied_objective"])
                self.assertEqual(after["liberty_health"], before["liberty_health"])
                self.assertEqual(after["vulnerable_mass"], before["vulnerable_mass"])

    def test_capture_facts_distinguish_hub_from_original_stone(self):
        state = position("junction-y", opening=False)
        for action in (
            RulesAction("play", (2, 0)),
            RulesAction("construct", (0, 0), orientation=0),
            RulesAction("play", (-1, 1)),
            RulesAction("play", (0, 0)),
        ):
            apply_action(state, action, copy=False)
        transitions = legal_transitions(state)
        capture = next(t for t in transitions if t.action == RulesAction("play", (-1, -1)))
        self.assertEqual(capture.facts.captured_total, 1)
        self.assertEqual(capture.facts.captured_original, 0)
        self.assertEqual(capture.facts.captured_junction, 1)
        successor = capture.successor()
        self.assertEqual(successor.game.state[(0, 0)], ())
        self.assertEqual(successor.game.topology, state.game.topology)
        self.assertEqual(successor.game.original_control_count()[BLACK], 3)

    def test_sole_liberty_defense_changes_vulnerable_original_mass(self):
        state = position("go-honeycomb", opening=False)
        for point in ((2, 0), (1, 1), (8, 0), (1, -1)):
            apply_action(state, RulesAction("play", point), copy=False)
        points = len(state.game.board.points)
        self.assertEqual(lab_features(state.game, BLACK)["vulnerable_mass"], 1 / points)
        defense = next(t for t in legal_transitions(state) if t.action == RulesAction("play", (4, 0)))
        saved = defense.successor()
        self.assertEqual(saved.game.state[(2, 0)], (BLACK,))
        self.assertEqual(lab_features(saved.game, BLACK)["vulnerable_mass"], 0)

    def test_terminal_evaluation_requires_acceptance_not_just_two_passes(self):
        for rules in ("breath-connection", "gjerde-majority", "junction-six"):
            with self.subTest(rules=rules):
                state = position(rules, opening=False)
                apply_action(state, RulesAction("play", state.game.board.points[0]), copy=False)
                black, white = state.seats[BLACK], state.seats[WHITE]
                apply_action(state, RulesAction("pass"), copy=False)
                apply_action(state, RulesAction("pass"), copy=False)
                pending = evaluate_state(state, black)
                self.assertFalse(state.terminal)
                self.assertLess(abs(pending), 10)
                apply_action(state, RulesAction("accept"), copy=False)
                self.assertEqual(evaluate_state(state, black), pending)
                apply_action(state, RulesAction("accept"), copy=False)
                denominator = len(state.game.board.cells) if rules == "gjerde-majority" else len(state.game.board.points)
                margin = state.game.score()[BLACK] - state.game.score()[WHITE]
                expected = (10 if margin > 0 else -10 if margin < 0 else 0) + margin / denominator
                self.assertTrue(state.terminal)
                self.assertEqual(evaluate_state(state, black), expected)
                self.assertEqual(evaluate_state(state, white), -expected)

    def test_pie_evaluation_tracks_each_original_seat_not_fixed_color(self):
        for spec in EXPERIMENT_SPECS:
            with self.subTest(rules=spec.id):
                state = position(spec.id, opening=False)
                black, white = state.seats[BLACK], state.seats[WHITE]
                apply_action(state, RulesAction("play", state.game.board.points[0]), copy=False)
                values = {seat: evaluate_state(state, seat) for seat in (black, white)}
                swapped = apply_action(state, RulesAction("swap"))
                self.assertEqual(swapped.actor_seat, black)
                self.assertEqual(swapped.actor_color, WHITE)
                self.assertEqual(evaluate_state(swapped, black), values[white])
                self.assertEqual(evaluate_state(swapped, white), values[black])
                for root in (state, swapped):
                    before = root.to_dict()
                    original_seat = root.actor_seat
                    perspectives = []

                    def observed(candidate, perspective_seat):
                        perspectives.append(perspective_seat)
                        return evaluate_state(candidate, perspective_seat)

                    with patch("lab_opponent.evaluate_state", side_effect=observed):
                        decision = choose_lab_decision(root, difficulty="standard", seed=29)
                    self.assertIn(decision.action, legal_actions(root))
                    self.assertTrue(perspectives)
                    self.assertEqual(set(perspectives), {original_seat})
                    self.assertEqual(root.to_dict(), before)

    def test_saved_seat_seed_reproduces_decisions_before_and_after_takeover(self):
        for spec in LAB_SPECS:
            with self.subTest(rules=spec.id):
                game = new_game(3, rules=spec.id, experimental=True)
                match = server.MatchConfig.from_new_game(game, {
                    "mode": "watch", "black_difficulty": "casual",
                    "white_difficulty": "standard", "seed": 311,
                })
                from lab_match import apply_lab_action

                apply_lab_action(game, match, RulesAction("play", game.board.points[0]), actor_kind="computer")
                for swap in (False, True):
                    if swap:
                        apply_lab_action(game, match, RulesAction("swap"), actor_kind="computer")
                    payload = server.snapshot_payload(game, match)
                    restored_game, restored_match = server.load_snapshot(deepcopy(payload))
                    seat = match.seats[match.lab_state.actor_color]
                    restored_seat = restored_match.seats[restored_match.lab_state.actor_color]
                    first = choose_lab_decision(match.lab_state, difficulty=seat.difficulty, seed=seat.seed)
                    second = choose_lab_decision(
                        restored_match.lab_state,
                        difficulty=restored_seat.difficulty, seed=restored_seat.seed,
                    )
                    self.assertEqual(deterministic_fields(first), deterministic_fields(second))
                    self.assertEqual(server.snapshot_payload(game, match), payload)
                    self.assertEqual(server.snapshot_payload(restored_game, restored_match), payload)

    def test_cache_returns_isolated_successors_and_respects_forbidden_history(self):
        state = position("junction-y")
        before = state.to_dict()
        cache = TransitionCache(max_batches=2)
        transitions = legal_transitions(state, cache=cache)
        item = next(t for t in transitions if t.action.kind == "play")
        expected = item.successor().to_dict()
        polluted = item.successor()
        polluted.game.history.clear()
        polluted.game.action_journal[0]["point"][0] = 999
        polluted.seats[BLACK] = "polluted-seat"
        self.assertEqual(item.successor().to_dict(), expected)
        self.assertEqual(state.to_dict(), before)
        restricted = state.clone()
        restricted.game.history.add(item.successor().game.repetition_key())
        self.assertNotIn(item.action, {t.action for t in legal_transitions(restricted, cache=cache)})
        self.assertIn(item.action, {t.action for t in legal_transitions(state, cache=cache)})
        self.assertEqual(state.to_dict(), before)

    def test_cache_separates_journal_and_seed_even_when_analysis_keys_match(self):
        original = position("go-honeycomb", seed=11)
        seed_changed = position("go-honeycomb", seed=12)
        journal_changed = original.clone()
        journal_changed.game.action_journal.reverse()
        self.assertEqual(original.analysis_key(), seed_changed.analysis_key())
        self.assertEqual(original.analysis_key(), journal_changed.analysis_key())
        cache = TransitionCache(max_batches=2)
        for state in (original, seed_changed, journal_changed, original):
            result = legal_transitions(state, cache=cache)[0].successor()
            self.assertEqual(result.game.topology_seed, state.game.topology_seed)
            self.assertEqual(result.game.action_journal[:-1], state.game.action_journal)

    def test_candidates_resolve_once_without_preliminary_legal_move_scans(self):
        state = position("junction-planted")
        expected = set(legal_actions(state))
        cache = TransitionCache(max_batches=2)
        calls = Counter()
        original_play = LabGame._resolve_placement
        original_plant = LabGame._resolve_plant

        def play(game, point, **kwargs):
            calls[("play", point)] += 1
            return original_play(game, point, **kwargs)

        def plant(game, face, orientation, **kwargs):
            calls[("plant", face, orientation)] += 1
            return original_plant(game, face, orientation, **kwargs)

        with patch.object(LabGame, "legal_placements", side_effect=AssertionError("preliminary placement scan")), \
                patch.object(LabGame, "construction_actions", side_effect=AssertionError("preliminary construction scan")), \
                patch.object(LabGame, "_resolve_placement", new=play), \
                patch.object(LabGame, "_resolve_plant", new=plant):
            first = legal_transitions(state, cache=cache)
            second = legal_transitions(state, cache=cache)
        self.assertEqual({t.action for t in first}, expected)
        self.assertEqual({t.action for t in second}, expected)
        self.assertTrue(calls)
        self.assertTrue(all(count == 1 for count in calls.values()), calls)

    def test_public_recipe_is_provisional_and_weights_cannot_be_mutated(self):
        public = lab_native_public()
        self.assertTrue(public["provisional"])
        self.assertEqual(public["difficulties"], ["casual", "standard"])
        self.assertEqual(len(public["agent_hash"]), 64)
        int(public["agent_hash"], 16)
        self.assertNotIn("weights", public)
        with self.assertRaises(TypeError):
            LAB_NATIVE_WEIGHTS["occupied_objective"] = 999

    def test_decision_identifies_its_frozen_recipe_as_well_as_source_hash(self):
        decision = choose_lab_decision(position("junction-six"), difficulty="casual", seed=7)
        public = decision.to_dict()
        self.assertEqual(public["recipe"], "lab-native-objective-v1")
        self.assertEqual(public["recipe"], lab_native_public()["recipe"])
        self.assertEqual(public["agent_hash"], lab_native_public()["agent_hash"])


if __name__ == "__main__":
    unittest.main()
