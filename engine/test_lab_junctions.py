"""Independent mechanical fixtures for Y and six-spoke junction games.

Short replay fixtures use real legal transitions, without policy search. Explicit
constructed scoring/color cases are local invariants, not reachable-game evidence
or game-optimal certificates. No playouts, calibration, or research runs occur.
"""

import unittest

from lab_game import LabGame
from varde import BLACK, WHITE, Illegal


FACE = (0, 0)
CENTER = (0, 0)
CORNERS = ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))
FILLERS = ((-8, -2), (-8, 0), (-8, 2), (8, -2), (8, 0), (8, 2), (-7, -3))
JUNCTION_RULES = ("junction-y", "junction-six")
CHOICES = {"junction-y": ((0, 2, 4), (1, 3, 5)), "junction-six": ((0, 1, 2, 3, 4, 5),)}


def component_and_liberties(game, point):
    """Independent graph walk; does not import production group/capture code."""
    color = game.state[point]
    if not color:
        raise ValueError("group fixture requires an occupied point")
    group, liberties = {point}, set()
    pending = [point]
    while pending:
        current = pending.pop()
        for neighbor in game.board.neighbors[current]:
            if not game.state[neighbor]:
                liberties.add(neighbor)
            elif game.state[neighbor] == color and neighbor not in group:
                group.add(neighbor)
                pending.append(neighbor)
    return group, liberties


def replay(rules, actions, n=3):
    game = LabGame(n, rules=rules)
    for action in actions:
        if action[0] == "play":
            game.play(action[1])
        elif action[0] == "construct":
            game.construct(action[1], action[2])
        else:
            raise AssertionError("unrecognized mechanical fixture action")
    return game


def capture_sequence(rules):
    if rules == "junction-y":
        return (
            ("play", CORNERS[0]), ("construct", FACE, 0),
            ("play", CORNERS[2]), ("play", CENTER), ("play", CORNERS[4]),
        )
    return (
        ("play", CORNERS[0]), ("construct", FACE, 0),
        ("play", CORNERS[1]), ("play", FILLERS[0]),
        ("play", CORNERS[2]), ("play", FILLERS[1]),
        ("play", CORNERS[3]), ("play", FILLERS[2]),
        ("play", CORNERS[4]), ("play", CENTER), ("play", CORNERS[5]),
    )


def transform_point(point, turns, reflect):
    x, y = point
    if reflect:
        y = -y
    for _ in range(turns):
        x, y = (x - 3 * y) // 2, (x + y) // 2
    return (x, y)


def transform_face(face, turns, reflect):
    q, r = face
    if reflect:
        r = -q - r
    for _ in range(turns):
        q, r = -r, q + r
    return (q, r)


def transform_sequence(rules, actions, turns, reflect):
    result = []
    for action in actions:
        if action[0] == "play":
            result.append(("play", transform_point(action[1], turns, reflect)))
        else:
            selected = tuple(sorted(
                ((-i if reflect else i) + turns) % 6
                for i in CHOICES[rules][action[2]]
            ))
            result.append(("construct", transform_face(action[1], turns, reflect),
                           CHOICES[rules].index(selected)))
    return tuple(result)


class TestLabJunctionMechanics(unittest.TestCase):
    def assert_round_trip(self, game):
        snapshot = game.to_dict()
        restored = LabGame.from_dict(snapshot)
        self.assertEqual(restored.to_dict(), snapshot)
        self.assertEqual(restored.history, game.history)
        self.assertEqual(restored.board, game.board)
        self.assertEqual(restored.state, game.state)
        self.assertEqual(game.to_dict(), snapshot)
        return restored

    def test_inactive_centers_and_original_opening_all_sizes(self):
        for rules in JUNCTION_RULES:
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    game = LabGame(n, rules=rules)
                    before = game.to_dict()
                    self.assertEqual(len(game.board.original_points), 6 * n * n)
                    self.assertEqual(len(game.board.faces), 3 * n * (n - 1) + 1)
                    self.assertEqual(game.board.faces[FACE], CORNERS)
                    self.assertNotIn(CENTER, game.state)
                    self.assertNotIn(CENTER, game.board.neighbors)
                    self.assertEqual(tuple(game.construction_actions()), ())
                    with self.assertRaises(Illegal):
                        game.play(CENTER)
                    with self.assertRaises(Illegal):
                        game.construct(FACE, 0)
                    self.assertEqual(game.to_dict(), before)
                    game.play(CORNERS[0])
                    self.assertTrue(game.swap_available)
                    self.assertEqual(len(game.construction_actions()), len(game.board.faces) * len(CHOICES[rules]))
                    game.construct(FACE, 0)
                    self.assertFalse(game.swap_available)
                    self.assertEqual(game.to_move, BLACK)
                    self.assertEqual(game.placements_played, 1)
                    self.assertEqual(game.constructions_played, 1)
                    self.assertEqual(game.moves_played, 2)
                    self.assertEqual(game.state[CENTER], ())
                    self.assertNotIn(CENTER, game.board.scoring_points)
                    self.assert_round_trip(game)

    def test_added_liberty_and_y_orientation_have_exact_effects(self):
        sequence = (("play", CORNERS[0]), ("play", CORNERS[1]),
                    ("play", (8, 0)), ("play", CORNERS[5]))
        for rules in JUNCTION_RULES:
            for orientation in range(len(CHOICES[rules])):
                with self.subTest(rules=rules, orientation=orientation):
                    game = replay(rules, sequence)
                    parent = game.clone()
                    old_board = game.board
                    self.assertEqual(component_and_liberties(game, CORNERS[0]),
                                     ({CORNERS[0]}, {(4, 0)}))
                    before = game.to_dict()
                    game.construct(FACE, orientation)
                    expected = {(4, 0)}
                    if 0 in CHOICES[rules][orientation]:
                        expected.add(CENTER)
                    self.assertEqual(component_and_liberties(game, CORNERS[0]),
                                     ({CORNERS[0]}, expected))
                    self.assertEqual(parent.to_dict(), before)
                    self.assertIs(parent.board, old_board)
                    self.assertIsNot(game.board, old_board)
                    self.assertNotIn(CENTER, old_board.points)
                    self.assert_round_trip(game)

    def test_shared_empty_junction_counts_once_for_a_connected_group(self):
        sequence = (("play", CORNERS[0]), ("play", FILLERS[0]),
                    ("play", CORNERS[1]), ("play", FILLERS[1]),
                    ("play", CORNERS[2]), ("play", FILLERS[2]))
        expected_group = {CORNERS[0], CORNERS[1], CORNERS[2]}
        before_liberties = {CORNERS[5], (4, 0), (2, 2), CORNERS[3], (-2, 2)}
        for rules in JUNCTION_RULES:
            with self.subTest(rules=rules):
                game = replay(rules, sequence)
                self.assertEqual(component_and_liberties(game, CORNERS[0]),
                                 (expected_group, before_liberties))
                game.construct(FACE, 0)
                self.assertEqual(component_and_liberties(game, CORNERS[0]),
                                 (expected_group, before_liberties | {CENTER}))
                self.assertEqual(game.state[CENTER], ())
                self.assert_round_trip(game)

    def test_empty_center_does_not_merge_but_occupation_does(self):
        sequence = (("play", CORNERS[0]), ("construct", FACE, 0),
                    ("play", CORNERS[2]), ("play", FILLERS[0]))
        for rules in JUNCTION_RULES:
            with self.subTest(rules=rules):
                game = replay(rules, sequence)
                self.assertEqual(component_and_liberties(game, CORNERS[0])[0], {CORNERS[0]})
                self.assertEqual(component_and_liberties(game, CORNERS[2])[0], {CORNERS[2]})
                self.assertIn(CENTER, component_and_liberties(game, CORNERS[0])[1])
                self.assertIn(CENTER, component_and_liberties(game, CORNERS[2])[1])
                self.assertEqual(game.play(CENTER), 0)
                self.assertEqual(component_and_liberties(game, CENTER)[0],
                                 {CORNERS[0], CORNERS[2], CENTER})
                self.assert_round_trip(game)

    def test_capture_reopens_junction_without_removing_graph(self):
        for rules in JUNCTION_RULES:
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    sequence = capture_sequence(rules)
                    game = replay(rules, sequence[:-1], n=n)
                    final_point = sequence[-1][1]
                    self.assertEqual(game.state[CENTER], (WHITE,))
                    self.assertEqual(component_and_liberties(game, CENTER),
                                     ({CENTER}, {final_point}))
                    board = game.board
                    snapshot = game.to_dict()
                    restored = self.assert_round_trip(game)
                    trial, captured = game.try_play(final_point)
                    self.assertEqual(captured, 1)
                    self.assertEqual(trial[CENTER], ())
                    self.assertEqual(game.to_dict(), snapshot)
                    self.assertEqual(game.play(final_point), 1)
                    self.assertEqual(restored.play(final_point), 1)
                    self.assertIs(game.board, board)
                    self.assertEqual(game.state[CENTER], ())
                    self.assertEqual(game.last_capture_waves, [(CENTER,)])
                    self.assertEqual(game.topology, ((0, 0, 0),))
                    self.assertIn(CENTER, component_and_liberties(game, final_point)[1])
                    self.assertNotIn(CENTER, game.board.scoring_points)
                    self.assertEqual(restored.to_dict(), game.to_dict())
                    self.assert_round_trip(game)

    def test_ordinary_center_suicide_is_rejected_without_mutation(self):
        for rules in JUNCTION_RULES:
            sequence = [("play", FILLERS[0]), ("construct", FACE, 0)]
            for i, corner_index in enumerate(CHOICES[rules][0]):
                sequence.extend((("play", FILLERS[i + 1]), ("play", CORNERS[corner_index])))
            game = replay(rules, sequence)
            self.assertEqual(game.to_move, BLACK)
            self.assertEqual(game.state[CENTER], ())
            for point in game.board.neighbors[CENTER]:
                self.assertEqual(game.state[point], (WHITE,))
                self.assertTrue(component_and_liberties(game, point)[1] - {CENTER})
            before = game.to_dict()
            with self.assertRaisesRegex(Illegal, "suicide"):
                game.try_play(CENTER)
            with self.assertRaisesRegex(Illegal, "suicide"):
                game.play(CENTER)
            self.assertEqual(game.to_dict(), before)
            self.assertNotIn(CENTER, game.legal_placements())
            self.assert_round_trip(game)

    def test_legal_capture_replays_under_all_rotations_and_reflections(self):
        for rules in JUNCTION_RULES:
            original = replay(rules, capture_sequence(rules))
            for turns in range(6):
                for reflect in (False, True):
                    with self.subTest(rules=rules, turns=turns, reflect=reflect):
                        actions = transform_sequence(rules, capture_sequence(rules), turns, reflect)
                        game = replay(rules, actions)
                        expected_state = {transform_point(p, turns, reflect): stack
                                          for p, stack in original.state.items()}
                        self.assertEqual(game.state, expected_state)
                        self.assertEqual(game.score(), original.score())
                        self.assertEqual(game.last_capture_waves, [(CENTER,)])
                        self.assert_round_trip(game)

    def test_color_reversed_capture_is_reachable_with_an_extra_distant_opening(self):
        # A leading Black placement flips every subsequent actor. This is a real
        # legal replay, not a fabricated White-to-move initial state. The extra
        # original point is excluded only from the color-equivalence assertion.
        distant_opening = (8, 0)
        for rules in JUNCTION_RULES:
            ordinary = replay(rules, capture_sequence(rules))
            reversed_game = replay(rules, (("play", distant_opening),) + capture_sequence(rules))
            self.assertEqual(ordinary.state[distant_opening], ())
            self.assertEqual(reversed_game.state[distant_opening], (BLACK,))
            for point in ordinary.board.points:
                if point == distant_opening:
                    continue
                expected = tuple(WHITE if color == BLACK else BLACK for color in ordinary.state[point])
                self.assertEqual(reversed_game.state[point], expected)
            self.assertEqual(reversed_game.last_capture_waves, [(CENTER,)])
            self.assert_round_trip(reversed_game)

    def test_constructed_original_only_area_changes_through_a_zero_point_hub(self):
        # Constructed local scoring invariant, not journal-certified reachable
        # game evidence. Every scored area expectation is explicit and independent
        # of the production scorer. No analysis/proof search is performed.
        for rules in JUNCTION_RULES:
            for invert_colors in (False, True):
                with self.subTest(rules=rules, invert_colors=invert_colors):
                    game = LabGame(3, rules=rules)
                    owner = WHITE if invert_colors else BLACK
                    other = BLACK if invert_colors else WHITE
                    game.state = {point: (other,) for point in game.board.original_points}
                    for point in (CORNERS[1], CORNERS[5], (4, 0)):
                        game.state[point] = (owner,)
                    for point in (CORNERS[0], CORNERS[2]):
                        game.state[point] = ()
                    self.assertEqual(game.score(), {owner: 4, other: 49})
                    game.board = game.board.with_junction(FACE, 0)
                    game.topology = game.board.topology
                    game.state[CENTER] = ()
                    self.assertEqual(game.score(), {owner: 3, other: 49})
                    game.state[CENTER] = (owner,)
                    before = game.to_dict()
                    self.assertEqual(game.score(), {owner: 4, other: 49})
                    self.assertEqual(game.to_dict(), before)
                    self.assertEqual(len(game.board.scoring_points), 54)
                    with self.assertRaises(ValueError):
                        LabGame.from_dict(before)


if __name__ == "__main__":
    unittest.main()
