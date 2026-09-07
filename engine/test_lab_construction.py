"""Implementation-level graph transition and clone isolation contracts."""

from copy import deepcopy
import unittest

from lab_game import LabGame
from varde import BLACK, WHITE, Illegal


class TestLabConstructionSnapshots(unittest.TestCase):
    def test_trial_topology_key_and_commit_match_without_mutating_parent(self):
        for rules in ("junction-y", "junction-six"):
            game = LabGame(3, rules=rules)
            game.play((2, 0))
            before, original_board = game.to_dict(), game.board
            candidate_board, candidate_stones = game.try_construct((0, 0), 0)
            candidate_key = game.repetition_key(candidate_stones, BLACK, board=candidate_board)
            self.assertEqual(game.to_dict(), before)
            self.assertIs(game.board, original_board)
            self.assertNotIn((0, 0), original_board.points)
            self.assertEqual(candidate_stones[(0, 0)], ())
            self.assertNotEqual(candidate_key, game.repetition_key())
            self.assertEqual(game.construct((0, 0), 0), 0)
            self.assertIs(game.board, candidate_board)
            self.assertEqual(game.state, candidate_stones)
            self.assertEqual(game.repetition_key(), candidate_key)

    def test_clone_shares_only_immutable_geometry_and_history_members(self):
        game = LabGame(3, rules="junction-y")
        game.play((2, 0))
        game.construct((0, 0), 1)
        before = game.to_dict()
        clone = game.clone()
        self.assertIs(clone.board, game.board)
        self.assertIsNot(clone.history, game.history)
        self.assertIsNot(clone.state, game.state)
        for point in game.state:
            self.assertIs(clone.state[point], game.state[point])
        for key in game.history:
            self.assertTrue(any(key is copied_key for copied_key in clone.history))
        clone.action_journal[-1]["face"][0] = 999
        clone.state[(0, 0)] = (WHITE,)
        clone.players[BLACK] = "Changed"
        clone.history.clear()
        self.assertEqual(game.to_dict(), before)

    def test_total_and_original_occupancy_are_distinct_from_area(self):
        game = LabGame(3, rules="junction-six")
        game.play((2, 0))
        game.construct((0, 0), 0)
        game.play((0, 0))
        self.assertEqual(game.control_count(), {BLACK: 2, WHITE: 0})
        self.assertEqual(game.original_control_count(), {BLACK: 1, WHITE: 0})
        self.assertEqual(game.score(), {BLACK: 54, WHITE: 0})

    def test_alternate_y_orientations_have_different_candidate_keys(self):
        game = LabGame(3, rules="junction-y")
        game.play((2, 0))
        keys = []
        for orientation in (0, 1):
            board, state = game.try_construct((0, 0), orientation)
            keys.append(game.repetition_key(state, BLACK, board=board))
        self.assertNotEqual(*keys)
        self.assertEqual(game.topology, ())

    def test_history_cannot_invent_future_topology_or_reuse_current_width(self):
        game = LabGame(3, rules="junction-y")
        game.play((2, 0))
        game.construct((0, 0), 0)
        payload = game.to_dict()
        bad = deepcopy(payload)
        old = next(record for record in bad["history"] if record["topology"] == [])
        old["stacks"].append([])
        with self.assertRaisesRegex(ValueError, "stone array"):
            LabGame.from_dict(bad)
        bad = deepcopy(payload)
        old = next(record for record in bad["history"] if record["topology"] == [])
        old["topology"] = [[1, 0, 0]]
        old["stacks"].append([])
        with self.assertRaisesRegex(ValueError, "future junction"):
            LabGame.from_dict(bad)

    def test_constructed_repetition_rejection_is_atomic_mechanical_only(self):
        game = LabGame(3, rules="junction-six")
        game.play((2, 0))
        board, stones = game.try_construct((0, 0), 0)
        # Synthetic key only tests enforcement; journal certification must reject
        # this invented history, and it is never a research fixture or evidence.
        game.history.add(game.repetition_key(stones, BLACK, board=board))
        before = game.to_dict()
        with self.assertRaisesRegex(Illegal, "repetition"):
            game.construct((0, 0), 0)
        self.assertEqual(game.to_dict(), before)
        self.assertFalse(any(action.point == (0, 0) for action in game.construction_actions()))
        with self.assertRaises(ValueError):
            LabGame.from_dict(before)


if __name__ == "__main__":
    unittest.main()
