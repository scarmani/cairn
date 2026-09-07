"""Implementation-level graph transition and clone isolation contracts."""

from copy import deepcopy
import unittest

from lab_game import LabGame
from varde import BLACK, WHITE, Illegal


class TestLabConstructionSnapshots(unittest.TestCase):
    def test_planted_junction_is_one_atomic_occupied_transition(self):
        game = LabGame(3, rules="junction-planted")
        game.play((2, 0))
        before = game.to_dict()
        board, stones, captured = game.try_plant((0, 0), 0)
        self.assertEqual(game.to_dict(), before)
        self.assertEqual(stones[(0, 0)], (WHITE,))
        self.assertEqual(captured, 0)
        final_key = game.repetition_key(stones, BLACK, board=board)
        self.assertEqual(game.plant((0, 0), 0), 0)
        self.assertEqual((game.moves_played, game.placements_played, game.constructions_played), (2, 2, 1))
        self.assertEqual(game.repetition_key(), final_key)
        self.assertEqual(game.to_move, BLACK)
        self.assertEqual(game.action_journal[-1], {"action": "plant", "face": [0, 0], "orientation": 0})
        topology_history = [key for key in game.history if key[3] == ((0, 0, 0),)]
        self.assertEqual(topology_history, [final_key])
        self.assertEqual(LabGame.from_dict(game.to_dict()).to_dict(), game.to_dict())

    def test_planted_legal_actions_never_offer_empty_construction(self):
        game = LabGame(3, rules="junction-planted")
        self.assertEqual(game.construction_actions(), ())
        with self.assertRaises(Illegal):
            game.plant((0, 0), 0)
        game.play((2, 0))
        before = game.to_dict()
        with self.assertRaisesRegex(Illegal, "empty construction is unavailable"):
            game.construct((0, 0), 0)
        self.assertEqual(game.to_dict(), before)
        actions = game.construction_actions()
        self.assertEqual(len(actions), 2 * len(game.board.faces))
        self.assertEqual({action.kind for action in actions}, {"plant"})
        self.assertEqual(game.to_dict(), before)

    def test_orientation_specific_plant_suicide_filters_actions_without_mutation(self):
        game = LabGame(3, rules="junction-planted")
        game.play((2, 0))
        # Legal replay: White passes while Black fills the odd three corners.
        for point in (game.board.faces[(0, 0)][i] for i in (1, 3, 5)):
            game.play_pass()
            game.play(point)
        self.assertEqual(game.to_move, WHITE)
        before, board = game.to_dict(), game.board
        with self.assertRaisesRegex(Illegal, "suicide"):
            game.plant((0, 0), 1)
        self.assertIs(game.board, board)
        self.assertEqual(game.to_dict(), before)
        local = {action.orientation for action in game.construction_actions() if action.point == (0, 0)}
        self.assertEqual(local, {0})
        self.assertEqual(game.plant((0, 0), 0), 0)
        self.assertEqual(LabGame.from_dict(game.to_dict()).to_dict(), game.to_dict())

    def test_passage_three_orientations_use_off_center_face_coordinates(self):
        for n in range(3, 7):
            for orientation in range(3):
                with self.subTest(n=n, orientation=orientation):
                    game = LabGame(n, rules="junction-passage")
                    game.play((2, 0))
                    face = (1, 0)
                    corners = game.board.faces[face]
                    board, stones = game.try_construct(face, orientation)
                    self.assertEqual(board.centers[face], (3, 1))
                    self.assertEqual(
                        set(board.neighbors[(3, 1)]),
                        {corners[orientation], corners[orientation + 3]},
                    )
                    self.assertEqual(stones[(3, 1)], ())
                    self.assertEqual(game.construct(face, orientation), 0)
                    self.assertEqual((game.moves_played, game.placements_played, game.constructions_played), (2, 1, 1))
                    self.assertEqual(LabGame.from_dict(game.to_dict()).to_dict(), game.to_dict())

    def test_new_actions_cannot_be_reinterpreted_between_planted_and_empty_games(self):
        planted = LabGame(3, rules="junction-planted")
        planted.play((2, 0))
        planted.plant((0, 0), 0)
        bad = planted.to_dict()
        bad["journal"][-1]["action"] = "construct"
        with self.assertRaisesRegex(ValueError, "empty construction is unavailable"):
            LabGame.from_dict(bad)
        for rules in ("junction-y", "junction-six", "junction-passage", "go-static-y", "breath-connection"):
            game = LabGame(3, rules=rules)
            game.play((2, 0))
            before = game.to_dict()
            with self.assertRaisesRegex(Illegal, "planted construction is unavailable"):
                game.plant((0, 0), 0)
            self.assertEqual(game.to_dict(), before)

    def test_planted_pass_reset_counters_and_journal_replay_all_sizes(self):
        for n in range(3, 7):
            game = LabGame(n, rules="junction-planted")
            game.play((2, 0))
            game.play_pass()
            game.plant((1, 0), 1)
            self.assertEqual((game.moves_played, game.placements_played, game.constructions_played), (3, 2, 1))
            self.assertEqual((game.consecutive_passes, game.quiet_moves), (0, 0))
            payload = game.to_dict()
            for format_id in ("varde-game", "cairn-game"):
                self.assertEqual(LabGame.from_dict(payload | {"format": format_id}).to_dict(), payload)
            for field in ("moves_played", "placements_played", "constructions_played"):
                bad = deepcopy(payload)
                bad[field] += 1
                with self.assertRaisesRegex(ValueError, "journal"):
                    LabGame.from_dict(bad)

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
