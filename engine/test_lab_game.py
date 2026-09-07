"""Mechanical contracts, not strategic evidence or generated game certificates."""

from copy import deepcopy
import unittest
from unittest.mock import call, patch

from actions import RulesAction
from lab_game import LabGame, SCORING_RULESETS
from varde import BLACK, WHITE, Game, Illegal, resolve


class TestLabScoring(unittest.TestCase):
    def test_empty_boards_score_zero_across_all_supported_sizes(self):
        for rules in SCORING_RULESETS:
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    game = LabGame(n, rules=rules)
                    self.assertEqual(game.score(), {BLACK: 0, WHITE: 0})

    def test_line_area_counts_lines_not_cells_and_neutral_mixed_regions(self):
        game = LabGame(3, rules="line-breath")
        first, last = game.board.points[0], game.board.points[-1]
        game.state[first] = (BLACK,)
        self.assertEqual(game.score(), {BLACK: len(game.board.points), WHITE: 0})
        self.assertNotEqual(len(game.board.points), len(game.board.cells))
        game.state[last] = (WHITE,)
        self.assertEqual(game.score(), {BLACK: 1, WHITE: 1})

    def test_line_area_single_color_pocket_counts_one_empty_line(self):
        game = LabGame(3, rules="line-breath")
        pocket = sorted(game.board.deep)[0]
        surrounding = game.board.neighbors[pocket]
        game.state = {point: (WHITE,) for point in game.board.points}
        game.state[pocket] = ()
        for point in surrounding:
            game.state[point] = (BLACK,)
        black = len(surrounding) + 1
        self.assertEqual(game.score(), {BLACK: black, WHITE: len(game.board.points) - black})

    def test_majority_requires_at_least_four_not_three_or_exactly_four(self):
        for n in range(3, 7):
            for count in range(7):
                with self.subTest(n=n, controlled_edges=count):
                    game = LabGame(n, rules="gjerde-majority")
                    edges = game.board.cell_edges[(0, 0)]
                    for point in edges[:count]:
                        game.state[point] = (BLACK,)
                    self.assertEqual(game.score(), {BLACK: int(count >= 4), WHITE: 0})

    def test_majority_mixed_boundaries_and_two_separate_cells(self):
        game = LabGame(3, rules="gjerde-majority")
        first = game.board.cell_edges[game.board.cells[0]]
        last = game.board.cell_edges[game.board.cells[-1]]
        for point in first[:4]:
            game.state[point] = (BLACK,)
        for point in last[:4]:
            game.state[point] = (WHITE,)
        self.assertEqual(game.score(), {BLACK: 1, WHITE: 1})
        game = LabGame(3, rules="gjerde-majority")
        edges = game.board.cell_edges[(0, 0)]
        for index, point in enumerate(edges):
            game.state[point] = (BLACK if index < 3 else WHITE,)
        self.assertEqual(game.score(), {BLACK: 0, WHITE: 0})

    def test_majority_shared_edge_can_contribute_to_both_adjacent_cells(self):
        game = LabGame(3, rules="gjerde-majority")
        first = set(game.board.cell_edges[(0, 0)])
        second = set(game.board.cell_edges[(1, 0)])
        shared = first & second
        self.assertEqual(len(shared), 1)
        for edges in (first, second):
            for point in shared | set(sorted(edges - shared)[:3]):
                game.state[point] = (BLACK,)
        self.assertEqual(game.score(), {BLACK: 2, WHITE: 0})

    def test_group_tax_counts_components_not_stones(self):
        game = LabGame(3, rules="breath-connection")
        first, last = game.board.points[0], game.board.points[-1]
        game.state[first] = (BLACK,)
        self.assertEqual(game.score()[BLACK], len(game.board.points) - 1)
        game.state[last] = (BLACK,)
        self.assertEqual(game.score()[BLACK], len(game.board.points) - 2)
        game.state[last] = ()
        game.state[game.board.neighbors[first][0]] = (BLACK,)
        self.assertEqual(game.score()[BLACK], len(game.board.points) - 1)
        game.state = {point: () for point in game.board.points}
        game.state[first], game.state[last] = (BLACK,), (WHITE,)
        self.assertEqual(game.score(), {BLACK: 0, WHITE: 0})

    def test_scoring_is_exactly_color_symmetric_and_nonmutating(self):
        for rules in SCORING_RULESETS:
            game = LabGame(3, rules=rules)
            for _ in range(7):
                game.play(game.legal_placements()[0])
            before = game.to_dict()
            score = game.score()
            other_game = game.clone()
            other_game.state = {
                point: tuple(WHITE if c == BLACK else BLACK for c in stack)
                for point, stack in game.state.items()
            }
            self.assertEqual(other_game.score(), {BLACK: score[WHITE], WHITE: score[BLACK]})
            self.assertEqual(game.to_dict(), before)


class TestLabTransitions(unittest.TestCase):
    def test_constructors_reject_unsupported_or_ambiguous_inputs(self):
        for rules in ("classic", "breath", "junction-unknown", "unknown", None):
            with self.assertRaises(ValueError):
                LabGame(3, rules=rules)
        for n in (True, 3.0, "3", 2, 7):
            with self.assertRaises(ValueError):
                LabGame(n)

    def test_flat_placement_and_breath_before_capture_for_all_three_variants(self):
        for rules in SCORING_RULESETS:
            with self.subTest(rules=rules):
                game = LabGame(3, rules=rules)
                point = game.board.points[0]
                game.play(point)
                with self.assertRaisesRegex(Illegal, "stack"):
                    game.play(point)
                # Constructed local invariant: White has one remaining liberty.
                # This is not exported as a reachable journal certificate.
                game = LabGame(3, rules=rules)
                game.state = {p: (WHITE,) for p in game.board.points}
                game.state[point] = ()
                with self.assertRaisesRegex(Illegal, "suicide"):
                    game.try_play(point)
                _state, captured = resolve(
                    game.board, game.state, point, BLACK, set(), rules="gjerde-go",
                )
                self.assertEqual(captured, len(game.board.points) - 1)

    def test_invalid_points_fail_without_mutation(self):
        game = LabGame(3)
        before = game.to_dict()
        for point in ((999, 999), (True, 0), (1.0, 1), "bad", None):
            with self.assertRaises(Illegal):
                game.play(point)
            self.assertEqual(game.to_dict(), before)

    def test_legal_capture_uses_flat_waves_and_keeps_trial_nonmutating(self):
        for rules in SCORING_RULESETS:
            with self.subTest(rules=rules):
                game = LabGame(3, rules=rules)
                victim = sorted(game.board.deep)[0]
                capture = game.board.neighbors[victim][0]
                game.state[victim] = (WHITE,)
                for neighbor in game.board.neighbors[victim]:
                    if neighbor != capture:
                        game.state[neighbor] = (BLACK,)
                before = deepcopy(game.state)
                trial, count = game.try_play(capture)
                self.assertEqual(count, 1)
                self.assertEqual(trial[victim], ())
                self.assertEqual(game.state, before)
                self.assertEqual(game.play(capture), 1)
                self.assertEqual(game.state, trial)
                self.assertEqual(game.last_capture_waves, [(victim,)])

    def test_try_play_legal_enumeration_and_clone_are_isolated(self):
        for rules in SCORING_RULESETS:
            game = LabGame(3, rules=rules)
            before = game.to_dict()
            choices = game.legal_placements()
            state, captured = game.try_play(choices[0])
            self.assertEqual(captured, 0)
            self.assertEqual(game.to_dict(), before)
            clone = game.clone()
            self.assertIsInstance(clone, LabGame)
            self.assertIs(clone.board, game.board)
            clone.play(choices[0])
            self.assertEqual(clone.state, state)
            self.assertEqual(game.to_dict(), before)
            clone2 = clone.clone()
            clone2.action_journal[0]["point"][0] = 999
            clone2.players[BLACK] = "Changed"
            clone2.history.clear()
            self.assertNotEqual(clone2.action_journal, clone.action_journal)
            self.assertNotEqual(clone2.players, clone.players)
            self.assertTrue(clone.history)

    def test_repetition_signature_separates_rules_history_and_next_color(self):
        first = LabGame(3, rules="line-breath")
        second = LabGame(3, rules="gjerde-majority")
        self.assertNotEqual(first.repetition_key(), second.repetition_key())
        self.assertNotEqual(first.repetition_key(), first.repetition_key(to_move=WHITE))
        point = first.legal_placements()[0]
        state, _ = first.try_play(point)
        key = first.repetition_key(state, WHITE)
        self.assertEqual(key[:4], ("line-breath", "0.1", 3, ()))
        # Synthetic forbidden-key test is explicitly mechanical, not evidence.
        first.history.add(key)
        before = first.to_dict()
        with self.assertRaisesRegex(Illegal, "repetition"):
            first.play(point)
        self.assertNotIn(point, first.legal_placements())
        self.assertEqual(first.to_dict(), before)
        with self.assertRaisesRegex(ValueError, "journal"):
            LabGame.from_dict(before)

    def test_pie_passes_and_once_only_resumption_all_sizes(self):
        for rules in SCORING_RULESETS:
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    game = LabGame(n, rules=rules)
                    with self.assertRaises(Illegal):
                        game.play_pass()
                    game.play(game.board.points[0])
                    state = dict(game.state)
                    key = game.repetition_key()
                    game.take_over()
                    self.assertEqual(game.state, state)
                    self.assertEqual(game.repetition_key(), key)
                    self.assertEqual(game.players[BLACK], "Player 2")
                    self.assertEqual(game.to_move, WHITE)
                    game.play_pass()
                    game.play_pass()
                    self.assertTrue(game.finished)
                    self.assertFalse(game.no_progress_end)
                    self.assertEqual(game.moves_played, 3)
                    self.assertEqual(game.placements_played, 1)
                    self.assertEqual(game.constructions_played, 0)
                    game.demand_resumption()
                    self.assertFalse(game.finished)
                    game.play_pass()
                    game.play_pass()
                    self.assertTrue(game.finished)
                    with self.assertRaises(Illegal):
                        game.demand_resumption()
                    restored = LabGame.from_dict(game.to_dict())
                    self.assertEqual(restored.to_dict(), game.to_dict())

    def test_old_quiet_counter_cannot_end_new_flat_game(self):
        game = LabGame(3)
        game.play(game.board.points[0])
        game.quiet_moves = 100  # constructed legacy-counter boundary test
        game.play_pass()
        self.assertFalse(game.finished)
        self.assertFalse(game.no_progress_end)


class TestLabSaveReplay(unittest.TestCase):
    def example(self, rules="breath-connection", n=3):
        game = LabGame(n, rules=rules)
        game.players = {BLACK: "A human", WHITE: "Provisional computer"}
        game.play(game.board.points[0])
        game.take_over()
        for _ in range(3):
            game.play(game.legal_placements()[0])
        return game

    def test_version_two_roundtrip_both_formats_and_all_sizes(self):
        for rules in SCORING_RULESETS:
            for n in range(3, 7):
                original = self.example(rules, n)
                for format_id in ("varde-game", "cairn-game"):
                    with self.subTest(rules=rules, n=n, format=format_id):
                        payload = original.to_dict()
                        self.assertEqual(payload["version"], 2)
                        payload["format"] = format_id
                        restored = LabGame.from_dict(payload)
                        self.assertEqual(restored.to_dict(), original.to_dict())
                        self.assertEqual(restored.history, original.history)
                        self.assertEqual(restored.legal_placements(), original.legal_placements())
                        point = original.legal_placements()[0]
                        clone = original.clone()
                        clone.play(point)
                        restored.play(point)
                        self.assertEqual(restored.to_dict(), clone.to_dict())

    def test_outer_seat_state_is_preserved_for_adapter_not_consumed_as_game_actions(self):
        game = self.example()
        payload = game.to_dict()
        payload.update(match={"opaque": "match-owned"}, rules_state={"opaque": "adapter-owned"})
        before = deepcopy(payload)
        self.assertEqual(LabGame.from_dict(payload).to_dict(), game.to_dict())
        self.assertEqual(payload, before)

    def test_schema_and_counter_tampering_rejected(self):
        game = self.example()
        mutations = {
            "version": True, "rules_revision": "0.2", "n": True,
            "placements_played": True, "moves_played": 4.0,
            "constructions_played": 1, "finished": 1, "no_progress_end": True,
            "extension_used": True, "extension_points": [[0, 0]],
            "topology": [[0, 0, 0]], "to_move": "X",
            "players": {BLACK: "Black"}, "initial_players": [],
            "consecutive_passes": -1, "quiet_moves": float("nan"),
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                payload = game.to_dict()
                payload[field] = value
                with self.assertRaises(ValueError):
                    LabGame.from_dict(payload)
        for field in ("journal", "history", "rules_revision"):
            payload = game.to_dict()
            del payload[field]
            with self.assertRaises(ValueError):
                LabGame.from_dict(payload)

    def test_full_history_is_replayed_not_silently_repaired(self):
        game = self.example()
        for mutation in ("omit", "duplicate", "alter", "foreign", "journal", "stone"):
            with self.subTest(mutation=mutation):
                payload = game.to_dict()
                if mutation == "omit":
                    payload["history"].pop(0)
                elif mutation == "duplicate":
                    payload["history"].append(deepcopy(payload["history"][0]))
                elif mutation == "alter":
                    payload["history"][0]["to_move"] = WHITE
                elif mutation == "foreign":
                    payload["history"][0]["rules"] = "line-breath"
                elif mutation == "journal":
                    payload["journal"].pop()
                else:
                    payload["stacks"][0] = [BLACK, WHITE]
                with self.assertRaises(ValueError):
                    LabGame.from_dict(payload)

    def test_invalid_journal_actions_and_extra_action_fields_are_rejected(self):
        events = [
            {"action": "pass"}, {"action": "resume"}, {"action": "accept"},
            {"action": "extend", "point": [0, 0]}, {"action": "finish-extension"},
            {"action": "construct", "face": [0, 0], "orientation": 0},
            {"action": "plant", "face": [0, 0], "orientation": 0},
            {"action": "play", "point": [True, 0]},
            {"action": "play", "point": [0, 0], "orientation": 0},
        ]
        for event in events:
            with self.subTest(event=event):
                payload = LabGame(3).to_dict()
                payload["journal"] = [event]
                with self.assertRaises(ValueError):
                    LabGame.from_dict(payload)

    def test_journal_replay_uses_the_shared_structured_action_parser(self):
        game = self.example()
        payload = game.to_dict()
        with patch("actions.RulesAction.from_dict", wraps=RulesAction.from_dict) as parser:
            restored = LabGame.from_dict(payload)
        self.assertEqual(parser.call_args_list, [call(event) for event in payload["journal"]])
        self.assertEqual(restored.to_dict(), game.to_dict())

    def test_legacy_loader_stays_version_one_and_new_rules_are_not_legacy_registered(self):
        legacy = Game(3)
        self.assertEqual(legacy.to_dict()["version"], 1)
        self.assertEqual(Game.from_dict(legacy.to_dict()).to_dict(), legacy.to_dict())
        with self.assertRaises(ValueError):
            Game.from_dict(LabGame(3).to_dict())
        with self.assertRaises(ValueError):
            Game(3, rules="line-breath")


if __name__ == "__main__":
    unittest.main()
