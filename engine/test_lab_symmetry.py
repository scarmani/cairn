"""Spatial diagram checks on authored mechanics only; no search or proof."""

from copy import deepcopy
import unittest

from actions import RulesAction, RulesState, apply_action
from game_factory import new_game
from lab_spec import HEX_CORNER_OFFSETS, PASSAGE_ORIENTATIONS, Y_ORIENTATIONS
from research.harness.lab_symmetry import (
    D6, RULESETS, diagram_projection, symmetry_key, transform_coordinate, transform_projection,
)
from research.harness.lab_terminal_cert import canonical_json


def fresh(rules, n=3, seed=7):
    return RulesState(new_game(n, rules, research=True, seed=seed), seats={"B": "S1", "W": "S2"})


def play(state, point):
    return apply_action(state, RulesAction("play", point))


class TestLabSymmetry(unittest.TestCase):
    def test_exact_rotation_reflection_and_group_closure(self):
        self.assertEqual(transform_coordinate((2, 0), 1), (1, 1))
        self.assertEqual(transform_coordinate((1, 1), 6), (1, -1))
        basis = ((8, 2), (-5, 1))
        maps = {tuple(transform_coordinate(point, s) for point in basis) for s in D6}
        self.assertEqual(len(maps), 12)
        for a in D6:
            for b in D6:
                self.assertIn(tuple(transform_coordinate(transform_coordinate(p, a), b) for p in basis), maps)
        point = (5, -3)
        for _ in range(6):
            point = transform_coordinate(point, 1)
        self.assertEqual(point, (5, -3))
        self.assertEqual(transform_coordinate(transform_coordinate(point, 6), 6), point)

    def test_coordinate_types_and_exact_divisibility(self):
        for point in ([True, 1], [1.0, 1], [1, 0], [1], {"x": 1}, [0, 0, 0], "00"):
            with self.subTest(point=point), self.assertRaises(ValueError):
                transform_coordinate(point, 0)
        for symmetry in (True, 1.0, -1, 12, [], "1"):
            with self.subTest(symmetry=symmetry), self.assertRaises(ValueError):
                transform_coordinate((0, 0), symmetry)

    def test_all_sixteen_rules_four_sizes_geometry_and_detachment(self):
        self.assertEqual(len(RULESETS), 16)
        for rules in RULESETS:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=rules, n=n):
                    state = fresh(rules, n)
                    original = getattr(state.game.board, "original_points", state.game.board.points)[0]
                    state = play(state, original)
                    before, analysis = state.to_dict(), state.analysis_key()
                    projected = diagram_projection(state)
                    self.assertEqual(projected["board_size"], n)
                    self.assertEqual(projected["phase"]["opening_phase"], "pie-window")
                    self.assertEqual(len(projected["current_graph"]["points"]), len(state.game.board.points))
                    self.assertEqual(transform_projection(projected, 0), projected)
                    self.assertEqual(symmetry_key(projected), symmetry_key(transform_projection(projected, 7)))
                    self.assertEqual(state.to_dict(), before)
                    self.assertEqual(state.analysis_key(), analysis)
                    projected["stones"][0]["column"].append("W")
                    projected["current_graph"]["points"].clear()
                    self.assertEqual(state.to_dict(), before)

    def test_rotated_authored_dynamic_construction_replays_match_projection(self):
        for rules in ("junction-y", "junction-six", "junction-passage", "junction-planted"):
            orientations = PASSAGE_ORIENTATIONS if rules == "junction-passage" else Y_ORIENTATIONS
            if rules == "junction-six":
                orientations = (tuple(range(6)),)
            for orientation in range(len(orientations)):
                for symmetry in D6:
                    with self.subTest(rules=rules, orientation=orientation, symmetry=symmetry):
                        kind = "plant" if rules == "junction-planted" else "construct"
                        state = play(fresh(rules), (2, 0))
                        state = apply_action(state, RulesAction(kind, (0, 0), orientation))
                        transformed_spokes = {transform_coordinate(HEX_CORNER_OFFSETS[i], symmetry) for i in orientations[orientation]}
                        candidates = [{HEX_CORNER_OFFSETS[i] for i in choice} for choice in orientations]
                        new_orientation = candidates.index(transformed_spokes)
                        rotated = play(fresh(rules), transform_coordinate((2, 0), symmetry))
                        rotated = apply_action(rotated, RulesAction(kind, (0, 0), new_orientation))
                        expected = transform_projection(diagram_projection(state), symmetry)
                        self.assertEqual(expected, diagram_projection(rotated))
                        center = next(row for row in expected["current_graph"]["topology"] if row["center"] == [0, 0])
                        self.assertEqual(set(map(tuple, center["neighbors"])), transformed_spokes)

    def test_scoring_cells_originals_and_zero_point_hubs_are_explicit(self):
        for rules in ("gjerde", "gjerde-go", "gjerde-majority", "line-breath"):
            graph = diagram_projection(fresh(rules))["current_graph"]
            self.assertEqual(len(graph["cells"]), 19)
            self.assertTrue(all(len(row["boundary"]) == 6 for row in graph["cells"]))
            self.assertEqual(bool(graph["scoring_points"]), rules == "line-breath")
        state = play(fresh("junction-y"), (2, 0))
        state = apply_action(state, RulesAction("construct", (0, 0), 0))
        state = play(state, (0, 0))
        graph = diagram_projection(state)["current_graph"]
        self.assertIn([0, 0], graph["points"])
        self.assertNotIn([0, 0], graph["original_points"])
        self.assertNotIn([0, 0], graph["scoring_points"])

    def test_fixed_initial_topology_is_not_confused_with_constructed_geometry(self):
        first, second = fresh("go-static-six", seed=1), fresh("go-static-six", seed=2)
        self.assertEqual(symmetry_key(first), symmetry_key(second))
        a, b = fresh("go-static-y", seed=1), fresh("go-static-y", seed=2)
        self.assertNotEqual(symmetry_key(a), symmetry_key(b))
        projection = diagram_projection(a)
        self.assertEqual(projection["initial_graph"], projection["current_graph"])
        self.assertTrue(projection["initial_graph"]["topology"])
        self.assertEqual(symmetry_key(projection), symmetry_key(transform_projection(projection, 3)))

    def test_authored_reordered_origins_deduplicate_despite_distinct_real_history(self):
        # Both four-action histories are mechanically replayed, never edited or
        # manufactured. Independent placements commute spatially but leave
        # different actual forbidden-position histories and journals.
        state, reordered = fresh("junction-y"), fresh("junction-y")
        for point in ((2, 0), (-2, 0), (5, 1), (-5, 1)):
            state = play(state, point)
        for point in ((5, 1), (-5, 1), (2, 0), (-2, 0)):
            reordered = play(reordered, point)
        self.assertNotEqual(state.analysis_key(), reordered.analysis_key())
        self.assertNotEqual(state.game.history, reordered.game.history)
        self.assertEqual(diagram_projection(state), diagram_projection(reordered))
        self.assertEqual(symmetry_key(state), symmetry_key(reordered))
        projected = diagram_projection(reordered)
        self.assertNotIn("history", projected)
        self.assertNotIn("journal", projected)
        self.assertNotIn("moves_played", projected["phase"])
        # Presentation names and the seed label are explicitly omitted.
        copied = state.clone()
        copied.game.players = {"B": "not a seat", "W": "another display name"}
        self.assertEqual(symmetry_key(state), symmetry_key(copied))

    def test_endings_takeover_and_extension_point_phases_are_preserved(self):
        state = play(fresh("breath-run"), (2, 0))
        swapped = apply_action(state, RulesAction("swap"))
        self.assertNotEqual(symmetry_key(state), symmetry_key(swapped))
        ended = apply_action(apply_action(swapped, RulesAction("pass")), RulesAction("pass"))
        resumed = apply_action(ended, RulesAction("resume"))
        self.assertNotEqual(symmetry_key(ended), symmetry_key(resumed))
        self.assertTrue(diagram_projection(resumed)["phase"]["resumption_used"])
        one = apply_action(ended, RulesAction("accept"))
        two = apply_action(one, RulesAction("accept"))
        self.assertEqual(len({symmetry_key(s) for s in (ended, one, two)}), 3)
        self.assertIsNone(diagram_projection(two)["phase"]["actor_color"])
        projection = diagram_projection(swapped)
        projection["phase"]["extension_used"] = True
        projection["phase"]["extension_points"] = [[2, 0], [1, 1]]
        transformed = transform_projection(projection, 1)
        self.assertEqual(transformed["phase"]["extension_points"], [[1, 1], [-1, 1]])
        altered = deepcopy(projection)
        altered["phase"]["quiet_moves"] += 1
        self.assertNotEqual(symmetry_key(projection), symmetry_key(altered))

    def test_different_shapes_and_rules_are_not_collapsed(self):
        state = play(fresh("classic"), (2, 0))
        first = diagram_projection(state)
        second = deepcopy(first)
        next(row for row in second["stones"] if row["point"] == [2, 0])["column"].append("W")
        self.assertNotEqual(symmetry_key(first), symmetry_key(second))
        self.assertNotEqual(symmetry_key(fresh("breath")), symmetry_key(fresh("classic")))

    def test_strict_projection_schema_rejects_aliases_duplicates_and_bad_spokes(self):
        state = play(fresh("junction-y"), (2, 0))
        state = apply_action(state, RulesAction("construct", (0, 0), 0))
        value = diagram_projection(state)
        cases = []
        for field, invalid in (("version", True), ("board_size", 3.0), ("rules_id", [])):
            altered = deepcopy(value)
            altered[field] = invalid
            cases.append(altered)
        for field, invalid in (("to_move", []), ("actor_color", {}), ("seats", {"B": [], "W": "S2"}),
                               ("accepted", 1), ("consecutive_passes", True)):
            altered = deepcopy(value)
            altered["phase"][field] = invalid
            cases.append(altered)
        altered = deepcopy(value)
        altered["current_graph"]["edges"].append(altered["current_graph"]["edges"][0])
        cases.append(altered)
        altered = deepcopy(value)
        altered["current_graph"]["topology"][0]["neighbors"].pop()
        cases.append(altered)
        altered = deepcopy(value)
        altered["stones"][0]["column"] = [float("nan")]
        cases.append(altered)
        altered = deepcopy(value)
        altered["stones"][0]["point"] = tuple(altered["stones"][0]["point"])
        cases.append(altered)
        original = canonical_json(value)
        for index, altered in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                symmetry_key(altered)
        self.assertEqual(canonical_json(value), original)

    def test_malformed_production_identity_is_rejected_without_mutation(self):
        for field, invalid in (("seats", {"B": [], "W": "S2"}), ("end_decider", [])):
            state = fresh("junction-y")
            setattr(state, field, invalid)
            with self.subTest(field=field), self.assertRaises(ValueError):
                diagram_projection(state)
            self.assertEqual(getattr(state, field), invalid)


if __name__ == "__main__":
    unittest.main()
