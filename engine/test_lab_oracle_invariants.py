"""Independent mechanical and synthetic-tree checks, never admission evidence.

No corpus search or game-optimal certificate is produced by these unit tests.
Direct state replacements below are explicitly constructed invariant fixtures.
"""

import ast
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from actions import RulesAction, RulesState, apply_action, legal_actions
from lab_game import LabGame
from lab_spec import EXPERIMENT_SPECS
import lab_graph
import varde

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.harness import lab_oracle as oracle
from research.harness.lab_local_proof import (
    Actor, LocalProofSpec, ProofIntegrityError, ProofProvider, QuantifierStep,
    Truth, classify_local,
)


def wire(kind, point=None, orientation=None):
    return RulesAction(kind, point, orientation=orientation).to_dict()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class TestIndependentLabOracle(unittest.TestCase):
    def pair(self, rules, n=3, seed=23):
        return RulesState(LabGame(n, rules=rules, seed=seed)), oracle.new_state(rules, n, seed=seed)

    def advance(self, product, independent, action):
        before = independent.to_dict()
        product = apply_action(product, RulesAction.from_dict(action))
        result = oracle.transition(independent, action)
        self.assertEqual(independent.to_dict(), before)
        self.assertEqual(result.state.to_dict(), product.to_dict())
        self.assertEqual(oracle.score(result.state), product.game.score())
        return product, result.state

    def assert_geometry(self, product, independent):
        actual, expected = oracle.geometry(independent), product.game.board
        self.assertEqual(tuple(actual.points), tuple(expected.points))
        self.assertEqual(set(actual.original_points), set(getattr(expected, "original_points", expected.points)))
        self.assertEqual(set(actual.active_centers), set(getattr(expected, "active_centers", ())))
        self.assertEqual({p: set(n) for p, n in actual.neighbors.items()},
                         {p: set(n) for p, n in expected.neighbors.items()})
        if hasattr(expected, "faces"):
            self.assertEqual(dict(actual.faces), dict(expected.faces))
            self.assertEqual(dict(actual.centers), dict(expected.centers))
        if hasattr(expected, "cell_edges"):
            self.assertEqual({f: set(e) for f, e in actual.cell_edges.items()},
                             {f: set(e) for f, e in expected.cell_edges.items()})
        with self.assertRaises(TypeError):
            actual.neighbors[actual.points[0]] = ()

    def test_all_ten_rules_and_sizes_match_geometry_actions_and_short_journals(self):
        for spec in EXPERIMENT_SPECS:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=spec.id, n=n):
                    product, independent = self.pair(spec.id, n)
                    self.assertEqual(independent.to_dict(), product.to_dict())
                    self.assert_geometry(product, independent)
                    self.assertEqual(
                        {json.dumps(a.to_dict(), sort_keys=True) for a in oracle.legal_actions(independent)},
                        {json.dumps(a.to_dict(), sort_keys=True) for a in legal_actions(product)},
                    )
                    original = getattr(product.game.board, "original_points", product.game.board.points)
                    for action in (wire("play", original[0]), wire("swap"), wire("play", original[-1])):
                        product, independent = self.advance(product, independent, action)
                    if "construct" in spec.supported_actions or "plant" in spec.supported_actions:
                        kind = "plant" if "plant" in spec.supported_actions else "construct"
                        action = wire(kind, (1, 0), len(spec.orientation_sets) - 1)
                        product, independent = self.advance(product, independent, action)
                        self.assert_geometry(product, independent)
                    self.assertEqual(
                        {json.dumps(a.to_dict(), sort_keys=True) for a in oracle.legal_actions(independent)},
                        {json.dumps(a.to_dict(), sort_keys=True) for a in legal_actions(product)},
                    )
                    payload = product.to_dict()
                    restored = oracle.load_snapshot(payload)
                    self.assertEqual(restored.state.to_dict(), payload)
                    self.assertTrue(restored.mechanical_journal_verified)
                    self.assertTrue(restored.current_envelope_verified)
                    self.assertFalse(restored.full_action_replay)

    def test_empty_hub_is_one_distinct_liberty_and_occupation_merges_groups(self):
        state = oracle.new_state("junction-y")
        self.assertNotIn((0, 0), oracle.geometry(state).points)
        for action in (wire("play", (2, 0)), wire("construct", (0, 0), 0),
                       wire("play", (-1, 1)), wire("play", (8, 0))):
            state = oracle.transition(state, action).state
        before_groups = oracle.groups(state, "B")
        self.assertEqual(len(before_groups), 2)
        self.assertTrue(all((0, 0) in oracle.liberties(state, group) for group in before_groups))
        merged = oracle.transition(state, wire("play", (0, 0))).state
        self.assertEqual(oracle.groups(merged, "B"), (frozenset({(2, 0), (-1, 1), (0, 0)}),))
        self.assertNotIn((0, 0), oracle.liberties(merged, (0, 0)))
        path = oracle.new_state("junction-y")
        for point in ((2, 0), (-8, -2), (1, 1), (-8, 0), (-1, 1), (-8, 2)):
            path = oracle.transition(path, wire("play", point)).state
        before_liberties = oracle.liberties(path, (2, 0))
        built = oracle.transition(path, wire("construct", (0, 0), 0)).state
        self.assertEqual(oracle.liberties(built, (2, 0)), before_liberties | {(0, 0)})

    def test_hub_capture_reopens_permanent_topology_and_allows_reoccupation(self):
        sequences = {
            "junction-y": (wire("play", (2, 0)), wire("construct", (0, 0), 0),
                           wire("play", (-1, 1)), wire("play", (0, 0)), wire("play", (-1, -1))),
            "junction-planted": (wire("play", (2, 0)), wire("plant", (0, 0), 0),
                                 wire("play", (-1, 1)), wire("play", (8, 0)), wire("play", (-1, -1))),
            "junction-passage": (wire("play", (2, 0)), wire("construct", (0, 0), 0),
                                 wire("play", (8, 0)), wire("play", (0, 0)), wire("play", (-2, 0))),
        }
        for rules, actions in sequences.items():
            with self.subTest(rules=rules):
                product, independent = self.pair(rules)
                for action in actions[:-1]:
                    product, independent = self.advance(product, independent, action)
                captured = oracle.transition(independent, actions[-1])
                self.assertEqual((captured.captured_original, captured.captured_junction), (0, 1))
                self.assertEqual(captured.captured_points, frozenset({(0, 0)}))
                product, independent = self.advance(product, independent, actions[-1])
                self.assertIsNone(independent.at((0, 0)))
                self.assertIn((0, 0), oracle.geometry(independent).active_centers)
                topology = independent.topology
                for action in (wire("pass"), wire("play", (0, 0))):
                    product, independent = self.advance(product, independent, action)
                self.assertEqual(independent.topology, topology)
                self.assertEqual(independent.at((0, 0)), "B")

    def test_plant_does_not_capture_existing_atari_and_suicide_is_atomic(self):
        product, state = self.pair("junction-planted")
        for point in ((1, 1), (2, 0), (1, -1), (8, 0)):
            product, state = self.advance(product, state, wire("play", point))
        self.assertEqual(oracle.liberties(state, (2, 0)), frozenset({(4, 0)}))
        result = oracle.transition(state, wire("plant", (0, 0), 1))
        self.assertEqual(result.captured_total, 0)
        self.assertEqual(result.state.at((2, 0)), "W")
        self.assertEqual(oracle.liberties(result.state, (2, 0)), frozenset({(4, 0)}))
        before_keys = set(state.history)
        added = set(result.state.history) - before_keys
        self.assertEqual(added, {result.state.repetition_key()})
        self.assertEqual(len(result.state.journal), len(state.journal) + 1)
        suicide = oracle.new_state("junction-planted")
        for point in ((-8, -2), (2, 0), (-8, 0), (-1, 1), (-8, 2), (-1, -1)):
            suicide = oracle.transition(suicide, wire("play", point)).state
        before = suicide.to_dict()
        with self.assertRaises(oracle.OracleIllegal):
            oracle.transition(suicide, wire("plant", (0, 0), 0))
        self.assertEqual(suicide.to_dict(), before)
        self.assertEqual(oracle.transition(suicide, wire("plant", (0, 0), 1)).captured_total, 0)

    def test_reachable_ko_and_pass_history_are_independently_enforced(self):
        product, state = self.pair("go-honeycomb")
        for point in ((-8, 0), (-7, 1), (-8, -2), (-8, 2), (-5, -1), (-5, 1)):
            product, state = self.advance(product, state, wire("play", point))
        product, state = self.advance(product, state, wire("pass"))
        self.assertIn(state.repetition_key(), state.history)
        product, state = self.advance(product, state, wire("play", (-7, -1)))
        before = state.to_dict()
        with self.assertRaises(oracle.OracleIllegal):
            oracle.transition(state, wire("play", (-8, 0)))
        self.assertNotIn(oracle.OracleAction("play", (-8, 0)), oracle.legal_actions(state))
        self.assertEqual(state.to_dict(), before)

    def test_topology_and_final_planted_occupancy_both_participate_in_superko(self):
        # Injected forbidden keys test the repetition mechanism, not reachability.
        state = oracle.new_state("junction-planted")
        state = oracle.transition(state, wire("play", (8, 0))).state
        action = wire("plant", (1, 0), 0)
        next_state = oracle.transition(state, action).state
        forbidden = replace(state, history=state.history | {next_state.repetition_key()})
        before = forbidden.to_dict()
        with self.assertRaises(oracle.OracleIllegal):
            oracle.transition(forbidden, action)
        self.assertEqual(forbidden.to_dict(), before)
        center = oracle.geometry(next_state).centers[(1, 0)]
        empty_intermediate = replace(next_state, stones=tuple(
            None if point == center else next_state.at(point) for point in oracle.geometry(next_state).points))
        only_empty_forbidden = replace(state, history=state.history | {empty_intermediate.repetition_key()})
        self.assertEqual(oracle.transition(only_empty_forbidden, action).state.stones, next_state.stones)
        alternate = oracle.transition(state, wire("plant", (1, 0), 1)).state
        self.assertNotEqual(next_state.repetition_key(), alternate.repetition_key())
        other_topology_forbidden = replace(state, history=state.history | {alternate.repetition_key()})
        self.assertEqual(oracle.transition(other_topology_forbidden, action).state.stones, next_state.stones)

    def test_import_and_full_action_replay_keep_distinct_seat_provenance(self):
        initial = oracle.new_state("junction-six")
        actions = [wire("play", (2, 0)), wire("swap"), wire("pass"), wire("pass"), wire("accept")]
        full = oracle.replay(initial, actions)
        self.assertTrue(full.full_action_replay)
        self.assertFalse(full.state.terminal)
        self.assertEqual(len(full.state.end_acceptances), 1)
        payload = full.state.to_dict()
        for format_id in ("varde-game", "cairn-game"):
            saved = deepcopy(payload)
            saved["format"] = format_id
            before = deepcopy(saved)
            imported = oracle.load_snapshot(saved)
            self.assertEqual(imported.state.to_dict(), payload)
            self.assertTrue(imported.mechanical_journal_verified)
            self.assertTrue(imported.current_envelope_verified)
            self.assertFalse(imported.full_action_replay)
            self.assertEqual(saved, before)
        actions += [wire("resume"), wire("pass"), wire("pass"), wire("accept")]
        resumed = oracle.replay(initial, actions)
        self.assertTrue(resumed.full_action_replay)
        self.assertTrue(resumed.state.terminal)
        self.assertTrue(resumed.state.resumption_used)
        self.assertEqual(len(resumed.state.end_acceptances), 1)
        self.assertFalse(oracle.load_snapshot(resumed.state.to_dict()).full_action_replay)
        game_only = deepcopy(payload)
        game_only.pop("rules_state")
        imported = oracle.load_snapshot(game_only)
        self.assertTrue(imported.mechanical_journal_verified)
        self.assertFalse(imported.current_envelope_verified)
        self.assertFalse(imported.full_action_replay)

    def test_replaying_an_imported_continuation_does_not_restore_missing_historical_seat_actions(self):
        initial = oracle.new_state("junction-six")
        complete = oracle.replay(initial, (
            wire("play", (2, 0)), wire("pass"), wire("pass"), wire("accept"),
        ))
        imported = oracle.load_snapshot(complete.state.to_dict())
        self.assertFalse(imported.full_action_replay)
        continued = oracle.replay(imported.state, (wire("resume"), wire("pass")))
        self.assertFalse(continued.mechanical_journal_verified)
        self.assertFalse(continued.full_action_replay)
        self.assertTrue(continued.assumptions)

    def test_strict_import_rejects_missing_history_wrong_width_and_forged_endings(self):
        product, state = self.pair("junction-y")
        for action in (wire("play", (2, 0)), wire("construct", (1, 0), 1), wire("pass"), wire("pass")):
            product, state = self.advance(product, state, action)
        payload = product.to_dict()
        mutations = (
            lambda p: p["history"].pop(0),
            lambda p: p["history"].append(deepcopy(p["history"][0])),
            lambda p: p["history"][0]["stacks"].append([]),
            lambda p: p.update(topology=[]),
            lambda p: p["topology"].append([1, 0, 0]),
            lambda p: p.update(moves_played=True),
            lambda p: p.update(rules_revision="future"),
            lambda p: p["journal"][1].update(orientation=True),
            lambda p: p["rules_state"].update(accepted=True, end_decider=None),
            lambda p: p["rules_state"].update(end_acceptances=["invented"]),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                bad = deepcopy(payload)
                mutate(bad)
                before = deepcopy(bad)
                with self.assertRaises(ValueError):
                    oracle.load_snapshot(bad)
                self.assertEqual(bad, before)

    def test_objective_scores_use_original_area_majority_and_group_tax(self):
        # These arbitrary occupancy replacements test scoring only, not reachability.
        for rules in ("junction-y", "junction-six", "junction-passage"):
            state = oracle.new_state(rules)
            state = oracle.transition(state, wire("play", (8, 0))).state
            state = oracle.transition(state, wire("construct", (0, 0), 0)).state
            board = oracle.geometry(state)
            state = replace(state, stones=tuple("B" for _ in board.points))
            self.assertEqual(oracle.score(state), {"B": 54, "W": 0})
            empty_hub = replace(state, stones=tuple(None if p == (0, 0) else "B" for p in board.points))
            self.assertEqual(oracle.score(empty_hub), {"B": 54, "W": 0})
        state = oracle.new_state("gjerde-majority")
        board = oracle.geometry(state)
        edges = tuple(board.cell_edges[(0, 0)])
        for count, expected in ((3, 0), (4, 1), (5, 1), (6, 1)):
            changed = replace(state, stones=tuple("B" if p in edges[:count] else None for p in board.points))
            self.assertEqual(oracle.score(changed), {"B": expected, "W": 0})
        state = oracle.new_state("breath-connection")
        board = oracle.geometry(state)
        separated = replace(state, stones=tuple("B" if p in {(2, 0), (-1, 1)} else "W" if p == (8, 0) else None
                                                for p in board.points))
        self.assertEqual(oracle.score(separated), {"B": 0, "W": 0})
        self.assertEqual(oracle.score(oracle.new_state("line-breath")), {"B": 0, "W": 0})

    def test_breath_checks_the_placed_group_before_enemy_capture(self):
        # Deliberately constructed last-liberty fixture; no reachability claim.
        for rules in ("line-breath", "gjerde-majority", "breath-connection", "go-honeycomb"):
            with self.subTest(rules=rules):
                state = oracle.new_state(rules)
                board = oracle.geometry(state)
                point = board.original_points[0]
                state = replace(state, stones=tuple(None if p == point else "W" for p in board.points))
                before = state.to_dict()
                if rules == "go-honeycomb":
                    result = oracle.transition(state, wire("play", point))
                    self.assertEqual(result.captured_total, len(board.points) - 1)
                    self.assertEqual(result.state.at(point), "B")
                else:
                    with self.assertRaises(oracle.OracleIllegal):
                        oracle.transition(state, wire("play", point))
                self.assertEqual(state.to_dict(), before)

    def test_color_and_spatial_scoring_group_liberty_symmetry_including_static_y(self):
        # Mechanical invariant transforms preserve stored Y orientations, not seed recipes.
        for spec in EXPERIMENT_SPECS:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=spec.id, n=n):
                    state = oracle.new_state(spec.id, n, seed=29)
                    board = oracle.geometry(state)
                    state = replace(state, stones=tuple(
                        "B" if i % 7 == 0 else "W" if i % 11 == 0 else None
                        for i in range(len(board.points))))
                    reversed_state = replace(state, stones=tuple(
                        "W" if stone == "B" else "B" if stone == "W" else None for stone in state.stones))
                    score = oracle.score(state)
                    self.assertEqual(oracle.score(reversed_state), {"B": score["W"], "W": score["B"]})
                    for color, inverse in (("B", "W"), ("W", "B")):
                        self.assertEqual(oracle.groups(state, color), oracle.groups(reversed_state, inverse))
                        for group in oracle.groups(state, color):
                            self.assertEqual(oracle.liberties(state, group), oracle.liberties(reversed_state, group))
                    # Reflect y then rotate 60 degrees: an exact honeycomb dihedral image.
                    def point_image(point):
                        x, y = point
                        return (x + 3 * y) // 2, (x - y) // 2

                    topology = []
                    for q, r, orientation in state.topology:
                        indices = {(1 - index) % 6 for index in spec.orientation_sets[orientation]}
                        mapped = next(i for i, option in enumerate(spec.orientation_sets) if set(option) == indices)
                        topology.append((q + r, -r, mapped))
                    target = replace(state, topology=tuple(sorted(topology)))
                    target_board = oracle.geometry(target)
                    stones = {point_image(p): state.at(p) for p in board.points}
                    target = replace(target, stones=tuple(stones[p] for p in target_board.points))
                    self.assertEqual(oracle.score(target), score)
                    for color in ("B", "W"):
                        expected = {frozenset(point_image(p) for p in group) for group in oracle.groups(state, color)}
                        self.assertEqual(set(oracle.groups(target, color)), expected)
                        for group in oracle.groups(state, color):
                            image = frozenset(point_image(p) for p in group)
                            self.assertEqual(oracle.liberties(target, image),
                                             frozenset(point_image(p) for p in oracle.liberties(state, group)))

    def test_strict_action_parser_rejects_unknowns_booleans_and_extra_fields(self):
        malformed = (
            {"action": "extend"}, {"action": "play", "point": [True, 0]},
            {"action": "play", "point": [2.0, 0]}, {"action": "pass", "orientation": 0},
            {"action": "construct", "face": [0, 0], "orientation": True},
            {"action": "plant", "face": [0, 0]}, {"action": "play", "point": [2, 0], "extra": 1},
        )
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(ValueError):
                oracle.OracleAction.from_dict(data)
        action = oracle.OracleAction.from_dict(wire("construct", (1, 0), 1))
        detached = action.to_dict()
        detached["face"][0] = 999
        self.assertEqual(action.point, (1, 0))
        with self.assertRaises((AttributeError, TypeError)):
            action.orientation = 0

    def test_warm_geometry_cache_cannot_accept_boolean_or_float_topology_aliases(self):
        state = oracle.new_state("junction-y")
        state = oracle.transition(state, wire("play", (8, 0))).state
        state = oracle.transition(state, wire("construct", (1, 0), 0)).state
        oracle.geometry(state)
        # Python considers these tuples equal as cache keys; schema types must
        # be validated before a cached canonical board can be returned.
        for topology in (((True, 0, 0),), ((1.0, 0, 0),), ((1, 0, False),)):
            for field in ("topology", "initial_topology"):
                with self.subTest(field=field, topology=topology), self.assertRaises(ValueError):
                    replace(state, **{field: topology})

    def test_oracle_calls_work_when_production_builders_parser_and_rules_are_disabled(self):
        product, _ = self.pair("junction-planted")
        for action in (wire("play", (2, 0)), wire("plant", (1, 0), 1)):
            product = apply_action(product, RulesAction.from_dict(action))
        payload = product.to_dict()
        expected_score = product.game.score()
        with ExitStack() as stack:
            for target, name in (
                (varde, "Board"), (varde, "KagomeBoard"), (varde, "groups_of"),
                (varde, "resolve"), (varde, "score_cells"), (lab_graph, "graph_board"),
                (lab_graph, "initial_graph_board"), (LabGame, "score"),
                (LabGame, "from_dict"), (RulesAction, "from_dict"),
            ):
                stack.enter_context(patch.object(target, name, side_effect=AssertionError("production dependency")))
            imported = oracle.load_snapshot(payload)
            self.assertEqual(oracle.score(imported.state), expected_score)
            actions = oracle.legal_actions(imported.state)
            self.assertTrue(actions)
            self.assertIsInstance(oracle.transition(imported.state, actions[0]).state, oracle.OracleState)
        forbidden = {"varde", "cairn", "actions", "lab_graph", "lab_game", "game_factory",
                     "opponent", "lab_opponent", "mcts", "server"}
        for path in Path(oracle.__file__).parent.glob("lab_oracle*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = {item.name.split(".")[0] for item in node.names}
                elif isinstance(node, ast.ImportFrom):
                    imported = {(node.module or "").split(".")[0]}
                else:
                    continue
                self.assertFalse(imported & forbidden, (path, imported))


@dataclass(frozen=True)
class TreeState:
    node: str


@dataclass(frozen=True)
class TreeAction:
    kind: str
    orientation: int


class TestIndependentLocalProof(unittest.TestCase):
    def provider(self, edges, actors=None):
        actors = actors or {}
        return ProofProvider(
            provider_hash=digest("synthetic-only-provider"),
            legal_actions=lambda state: tuple(edges.get(state.node, {})),
            transition=lambda state, action: TreeState(edges[state.node][action]),
            fingerprint=lambda state: digest({"node": state.node}),
            actor=lambda state: Actor(actors.get(state.node, "first"), "B"),
            action_data=lambda action: {"action": action.kind, "orientation": action.orientation},
        )

    def spec(self, schedule=(), mode="at-horizon"):
        return LocalProofSpec(
            goal_id="synthetic-predicate", rules_id="synthetic", rules_revision="test-1",
            scope="Mechanical synthetic tree only; not a game position or admission evidence.",
            schedule=schedule, evaluation_mode=mode,
        )

    def classify(self, edges, statuses, *, schedule=(), mode="at-horizon", actors=None, **kwargs):
        return classify_local(
            TreeState("root"), self.spec(schedule, mode), provider=self.provider(edges, actors),
            predicate=lambda state, _context: statuses.get(state.node, Truth.UNRESOLVED),
            predicate_hash=digest("synthetic-predicate-v1"), **kwargs,
        )

    def test_equivalent_oriented_root_actions_are_all_retained(self):
        first, second, unknown = (TreeAction("construct", i) for i in range(3))
        result = self.classify({"root": {first: "win", second: "win", unknown: "open"}},
                               {"win": Truth.SATISFIED})
        self.assertEqual(len(result.proven_actions), 2)
        self.assertEqual(len(result.unknown_actions), 1)
        self.assertEqual(len(result.disproven_actions), 0)
        self.assertEqual(len(result.action_results), 3)
        self.assertEqual({a.data["orientation"] for a in result.proven_actions}, {0, 1})
        self.assertFalse(hasattr(result, "optimal_actions"))
        self.assertEqual(result.cache_hits, 0)

    def test_exists_and_forall_are_distinct_and_unknown_is_not_disproof(self):
        root, yes, maybe = TreeAction("play", 0), TreeAction("play", 1), TreeAction("play", 2)
        edges = {"root": {root: "branch"}, "branch": {yes: "yes", maybe: "open"}}
        statuses = {"yes": Truth.SATISFIED}
        exists = self.classify(edges, statuses, schedule=(QuantifierStep("exists"),))
        forall = self.classify(edges, statuses, schedule=(QuantifierStep("forall"),))
        self.assertEqual(len(exists.proven_actions), 1)
        self.assertEqual(len(forall.unknown_actions), 1)
        self.assertEqual(len(forall.disproven_actions), 0)

    def test_closure_precedes_actor_mismatch_and_horizon_is_not_guessed(self):
        action = TreeAction("play", 0)
        edges = {"root": {action: "closed"}}
        schedule = (QuantifierStep("exists", actor="root-seat"),)
        actors = {"root": "first", "closed": "second"}
        closed = self.classify(edges, {"closed": Truth.SATISFIED}, schedule=schedule,
                               mode="closure", actors=actors)
        self.assertEqual(len(closed.proven_actions), 1)
        unclosed = self.classify(edges, {}, schedule=schedule, mode="closure", actors=actors)
        self.assertEqual(len(unclosed.unknown_actions), 1)
        horizon = self.classify(edges, {})
        self.assertEqual(len(horizon.unknown_actions), 1)

    def test_budget_and_cancellation_preserve_every_unvisited_root_action(self):
        actions = tuple(TreeAction("construct", i) for i in range(3))
        edges = {"root": {action: "yes" for action in actions}}
        for kwargs in ({"node_limit": 1}, {"cancelled": lambda: True}):
            with self.subTest(kwargs=tuple(kwargs)):
                result = self.classify(edges, {"yes": Truth.SATISFIED}, **kwargs)
                self.assertEqual(len(result.unknown_actions), 3)
                self.assertEqual(len(result.action_results), 3)
                self.assertEqual(result.transition_attempts, 0)
                self.assertEqual(result.cache_hits, 0)

    def test_duplicate_legal_actions_bad_predicates_and_failed_transitions_are_integrity_errors(self):
        action = TreeAction("play", 0)
        provider = self.provider({"root": {action: "yes"}})
        calls = (
            {"provider": replace(provider, legal_actions=lambda _s: (action, action))},
            {"predicate": lambda _s, _c: True},
            {"provider": replace(provider, transition=lambda _s, _a: (_ for _ in ()).throw(ValueError("bad edge")))},
        )
        for changes in calls:
            arguments = {"provider": provider, "predicate": lambda _s, _c: Truth.SATISFIED,
                         "predicate_hash": digest("synthetic-predicate-v1")}
            arguments.update(changes)
            with self.subTest(changes=tuple(changes)), self.assertRaises(ProofIntegrityError):
                classify_local(TreeState("root"), self.spec(), **arguments)

    def test_mutating_callbacks_fail_closed_and_leave_caller_state_untouched(self):
        source = {"node": "root", "history": ["initial"]}
        action = {"action": "play", "orientation": 0}
        provider = ProofProvider(
            provider_hash=digest("mutable-synthetic-provider"),
            legal_actions=lambda _state: (deepcopy(action),),
            transition=lambda _state, _action: {"node": "child", "history": ["initial", "child"]},
            fingerprint=digest, actor=lambda _state: Actor("first", "B"),
            action_data=lambda item: deepcopy(item),
        )

        def mutate_state(state):
            state["history"].append("corrupted")

        def bad_legal(state):
            mutate_state(state)
            return (deepcopy(action),)

        def bad_transition(state, _action):
            mutate_state(state)
            return {"node": "child", "history": []}

        def bad_predicate(state, _context):
            mutate_state(state)
            return Truth.SATISFIED

        def bad_action_data(item):
            item["orientation"] = 1
            return item

        cases = (
            {"provider": replace(provider, legal_actions=bad_legal)},
            {"provider": replace(provider, transition=bad_transition)},
            {"provider": replace(provider, action_data=bad_action_data)},
            {"predicate": bad_predicate},
        )
        for changes in cases:
            with self.subTest(changes=tuple(changes)):
                before = deepcopy(source)
                arguments = {"provider": provider, "predicate": lambda _s, _c: Truth.SATISFIED,
                             "predicate_hash": digest("synthetic-predicate-v1")}
                arguments.update(changes)
                with self.assertRaises(ProofIntegrityError):
                    classify_local(source, self.spec(), **arguments)
                self.assertEqual(source, before)
                self.assertEqual(action, {"action": "play", "orientation": 0})

    def test_restricted_empty_domains_require_explicit_vacuity(self):
        action = TreeAction("play", 0)
        edges = {"root": {action: "branch"}, "branch": {action: "child"}}
        for quantifier in ("exists", "forall"):
            for convention in ("unknown", "vacuous"):
                with self.subTest(quantifier=quantifier, convention=convention):
                    step = QuantifierStep(quantifier, action_kinds=("construct",), empty_domain=convention)
                    result = self.classify(edges, {}, schedule=(step,))
                    expected = "unknown" if convention == "unknown" else (
                        "proven" if quantifier == "forall" else "disproven")
                    self.assertEqual(result.action_results[0].status, expected)
                    self.assertEqual(result.transition_attempts, 1)


if __name__ == "__main__":
    unittest.main()
