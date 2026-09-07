"""Native lab integration contracts, not comparative search evidence."""

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from actions import RulesAction, apply_action, legal_actions
from game_factory import new_game
from lab_match import apply_lab_action
from lab_opponent import LabDecision, lab_native_public
from lab_spec import LAB_SPECS
import server
from varde import BLACK, WHITE, Illegal


class TestLabNativeServer(unittest.TestCase):
    def setUp(self):
        self.model = Mock(status=lambda: {"games_trained": 0})
        model = patch.object(server, "MODEL", self.model)
        model.start()
        self.addCleanup(model.stop)

    def match(self, rules="junction-y", **settings):
        game = new_game(3, rules=rules, experimental=True)
        settings.setdefault("mode", "watch")
        settings.setdefault("black_difficulty", "casual")
        settings.setdefault("white_difficulty", "casual")
        return game, server.MatchConfig.from_new_game(game, settings)

    def act(self, game, match, action):
        kind = match.seats[match.lab_state.actor_color].kind
        return apply_lab_action(game, match, action, actor_kind=kind)

    def opening(self, game, match):
        self.act(game, match, RulesAction("play", game.board.points[0]))

    def continuation(self, game, match):
        payload = server.snapshot_payload(game, match)
        restored, restored_match = server.load_snapshot(deepcopy(payload))
        self.assertEqual(server.snapshot_payload(restored, restored_match), payload)
        return restored, restored_match

    def test_real_casual_opening_is_legal_for_all_seven_without_classic_or_personal(self):
        with patch.object(server, "choose_decision", side_effect=AssertionError("legacy search")), \
                patch.object(server, "get_profile", side_effect=AssertionError("legacy profile")):
            for spec in LAB_SPECS:
                with self.subTest(rules=spec.id):
                    game, match = self.match(spec.id, seed=31)
                    actions = legal_actions(match.lab_state)
                    bound = match.lab_state
                    decision = server.apply_computer_action(game, match, model=object())
                    self.assertIsInstance(decision, LabDecision)
                    self.assertIn(decision.action, actions)
                    self.assertEqual(decision.action.kind, "play")
                    self.assertEqual(game.placements_played, 1)
                    self.assertEqual(game.constructions_played, 0)
                    self.assertIs(match.lab_state, bound)
                    self.assertEqual(len(game.action_journal), 1)
                    self.continuation(game, match)
        self.assertEqual(self.model.mock_calls, [])

    def test_human_turn_and_hotseat_fail_before_native_analysis(self):
        for settings in ({"mode": "hotseat"}, {"mode": "computer", "human_color": BLACK}):
            game, match = self.match(**settings)
            before = server.snapshot_payload(game, match)
            with patch.object(server, "choose_lab_decision") as choose:
                with self.assertRaises(Illegal):
                    server.apply_computer_action(game, match)
                choose.assert_not_called()
            self.assertEqual(server.snapshot_payload(game, match), before)

    def test_human_white_receives_takeover_after_real_computer_opening(self):
        game, match = self.match(mode="computer", human_color=WHITE, difficulty="casual", seed=41)
        original_computer = match.seats[BLACK]
        server.apply_computer_action(game, match)
        self.assertTrue(game.swap_available)
        self.assertEqual(match.lab_state.actor_seat, "human")
        self.assertFalse(match.computer_can_act(game))
        self.act(game, match, RulesAction("swap"))
        self.assertIs(match.seats[WHITE], original_computer)
        self.assertTrue(match.computer_can_act(game))
        available = legal_actions(match.lab_state)
        decision = server.apply_computer_action(game, match)
        self.assertIn(decision.action, available)
        self.assertEqual(match.lab_state.actor_seat, "human")
        self.continuation(game, match)

    def test_typed_takeover_keeps_complete_independent_seats_and_settings(self):
        game, match = self.match(black_difficulty="casual", white_difficulty="standard", seed=47)
        black, white = match.seats[BLACK], match.seats[WHITE]
        self.opening(game, match)
        original = match.lab_state
        before = original.to_dict()
        decision = LabDecision(RulesAction("swap"), reason_code="swap", reason_text="Take over.")

        def choose(analyzed, *, difficulty, seed):
            self.assertIsNot(analyzed, original)
            self.assertIsNot(analyzed.game, game)
            self.assertEqual(analyzed.to_dict(), before)
            self.assertEqual((difficulty, seed), ("standard", 48))
            return decision

        with patch.object(server, "choose_lab_decision", side_effect=choose), \
                patch.object(server, "apply_lab_action", wraps=apply_lab_action) as commit:
            self.assertIs(server.apply_computer_action(game, match), decision)
            commit.assert_called_once_with(game, match, decision.action, actor_kind="computer")
        self.assertIs(match.seats[BLACK], white)
        self.assertIs(match.seats[WHITE], black)
        self.assertEqual(match.lab_state.actor_seat, black.identity)
        self.assertEqual((black.difficulty, black.seed), ("casual", 47))
        self.assertEqual((white.difficulty, white.seed), ("standard", 48))
        self.assertEqual(game.action_journal[-1], {"action": "swap"})
        self.continuation(game, match)
        move = next(action for action in legal_actions(match.lab_state) if action.kind == "play")
        with patch.object(server, "choose_lab_decision", return_value=LabDecision(move)) as choose:
            server.apply_computer_action(game, match)
            self.assertEqual(choose.call_args.kwargs, {"difficulty": "casual", "seed": 47})

    def test_computer_takeover_of_human_black_returns_turn_to_same_human_identity(self):
        game, match = self.match(mode="computer", human_color=BLACK, difficulty="standard", seed=53)
        human, computer = match.seats[BLACK], match.seats[WHITE]
        self.opening(game, match)
        with patch.object(server, "choose_lab_decision", return_value=LabDecision(RulesAction("swap"))) as choose:
            server.apply_computer_action(game, match)
            self.assertEqual(choose.call_args.kwargs, {"difficulty": "standard", "seed": 53})
        self.assertIs(match.seats[BLACK], computer)
        self.assertIs(match.seats[WHITE], human)
        self.assertEqual(match.human_color, WHITE)
        self.assertEqual(match.lab_state.actor_seat, human.identity)
        self.assertFalse(match.computer_can_act(game))
        self.continuation(game, match)

    def test_structured_construct_and_plant_commit_only_one_final_transition(self):
        for rules, kind, orientation in (("junction-y", "construct", 1), ("junction-planted", "plant", 1),
                                         ("junction-passage", "construct", 2), ("junction-six", "construct", 0)):
            with self.subTest(rules=rules):
                game, match = self.match(rules)
                self.opening(game, match)
                action = RulesAction(kind, (1, 0), orientation=orientation)
                self.assertIn(action, legal_actions(match.lab_state))
                expected = apply_action(match.lab_state, action)
                before_length = len(game.action_journal)
                decision = LabDecision(action, reason_code=kind, reason_text="Change connectivity.")
                with patch.object(server, "choose_lab_decision", return_value=decision), \
                        patch.object(server, "apply_lab_action", wraps=apply_lab_action) as commit:
                    server.apply_computer_action(game, match)
                    commit.assert_called_once_with(game, match, action, actor_kind="computer")
                self.assertEqual(match.lab_state.to_dict(), expected.to_dict())
                self.assertEqual(len(game.action_journal), before_length + 1)
                self.assertEqual(game.action_journal[-1], action.to_dict())
                self.assertEqual(game.constructions_played, 1)
                self.assertEqual(game.placements_played, 2 if kind == "plant" else 1)
                self.continuation(game, match)

    def test_winning_computer_accepts_then_losing_computer_can_resume_across_load(self):
        game, match = self.match()
        self.opening(game, match)
        self.act(game, match, RulesAction("construct", (1, 0), orientation=0))
        self.act(game, match, RulesAction("pass"))
        self.act(game, match, RulesAction("pass"))
        self.assertEqual(match.lab_state.actor_color, BLACK)
        self.assertGreater(game.score()[BLACK], game.score()[WHITE])
        first = match.lab_state.actor_seat
        self.assertEqual(server.apply_computer_action(game, match).action.kind, "accept")
        self.assertEqual(match.end_acceptances, {first})
        self.assertFalse(match.lab_state.terminal)
        game, match = self.continuation(game, match)
        self.assertEqual(match.lab_state.actor_color, WHITE)
        self.assertEqual(server.apply_computer_action(game, match).action.kind, "resume")
        self.assertFalse(game.finished)
        self.assertTrue(game.resumption_used)
        self.assertEqual(match.end_acceptances, set())
        self.act(game, match, RulesAction("pass"))
        self.act(game, match, RulesAction("pass"))
        self.assertEqual(server.apply_computer_action(game, match).action.kind, "accept")
        self.assertTrue(match.lab_state.terminal)
        before = server.snapshot_payload(game, match)
        with patch.object(server, "choose_lab_decision") as choose:
            with self.assertRaises(Illegal):
                server.apply_computer_action(game, match)
            choose.assert_not_called()
        self.assertEqual(server.snapshot_payload(game, match), before)
        self.continuation(game, match)

    def test_tied_ending_has_two_real_computer_acceptances(self):
        game, match = self.match("breath-connection")
        self.opening(game, match)
        point = next(action.point for action in legal_actions(match.lab_state) if action.kind == "play")
        self.act(game, match, RulesAction("play", point))
        self.act(game, match, RulesAction("pass"))
        self.act(game, match, RulesAction("pass"))
        self.assertEqual(game.score()[BLACK], game.score()[WHITE])
        self.assertEqual(server.apply_computer_action(game, match).action.kind, "accept")
        self.assertFalse(match.lab_state.terminal)
        self.assertEqual(server.apply_computer_action(game, match).action.kind, "accept")
        self.assertTrue(match.lab_state.terminal)
        self.assertEqual(match.end_acceptances, {seat.identity for seat in match.seats.values()})

    def test_human_ending_decision_is_not_skipped_by_native_agent(self):
        game, match = self.match(mode="computer", human_color=WHITE, difficulty="casual")
        self.opening(game, match)
        self.act(game, match, RulesAction("pass"))
        self.act(game, match, RulesAction("pass"))
        before = server.snapshot_payload(game, match)
        with patch.object(server, "choose_lab_decision") as choose:
            with self.assertRaises(Illegal):
                server.apply_computer_action(game, match)
            choose.assert_not_called()
        self.assertEqual(server.snapshot_payload(game, match), before)
        self.act(game, match, RulesAction("accept"))
        self.assertEqual(server.apply_computer_action(game, match).action.kind, "accept")
        self.assertTrue(match.lab_state.terminal)

    def test_real_standard_save_continuation_has_identical_semantics(self):
        game, match = self.match("junction-planted", black_difficulty="standard", white_difficulty="standard", seed=61)
        self.opening(game, match)
        self.act(game, match, RulesAction("plant", (1, 0), orientation=1))
        restored, restored_match = self.continuation(game, match)
        first = server.apply_computer_action(game, match).to_dict()
        second = server.apply_computer_action(restored, restored_match).to_dict()
        first.pop("elapsed_ms")
        second.pop("elapsed_ms")
        self.assertEqual(first, second)
        self.assertEqual(server.snapshot_payload(game, match), server.snapshot_payload(restored, restored_match))

    def test_invalid_or_mutating_analysis_never_replaces_live_state(self):
        game, match = self.match()
        self.opening(game, match)
        state = match.lab_state
        before = server.snapshot_payload(game, match)
        legal = next(action for action in legal_actions(state) if action.kind == "play")

        def mutate_position(analyzed, **_):
            apply_action(analyzed, legal, copy=False)
            return LabDecision(legal)

        def mutate_journal(analyzed, **_):
            analyzed.game.action_journal[0]["point"][0] += 100
            return LabDecision(legal)

        def mutate_history(analyzed, **_):
            analyzed.game.history.clear()
            return LabDecision(legal)

        def mutate_seat(analyzed, **_):
            analyzed.seats[BLACK] = "wrong identity"
            return LabDecision(legal)

        attempts = (
            {"return_value": object()},
            {"return_value": LabDecision("play")},
            {"return_value": LabDecision(RulesAction("play", (999, 999)))},
            {"side_effect": mutate_position}, {"side_effect": mutate_journal},
            {"side_effect": mutate_history}, {"side_effect": mutate_seat},
        )
        for attempt in attempts:
            with self.subTest(attempt=attempt), patch.object(server, "choose_lab_decision", **attempt):
                with self.assertRaises(Illegal):
                    server.apply_computer_action(game, match)
            self.assertIs(match.lab_state, state)
            self.assertIs(match.lab_state.game, game)
            self.assertEqual(server.snapshot_payload(game, match), before)
        with patch.object(server, "choose_lab_decision", side_effect=RuntimeError("analysis failed")):
            with self.assertRaisesRegex(RuntimeError, "analysis failed"):
                server.apply_computer_action(game, match)
        self.assertEqual(server.snapshot_payload(game, match), before)

    def test_explanations_and_provisional_metadata_do_not_expose_weights(self):
        for explain in (False, True):
            game, match = self.match(explain=explain)
            self.opening(game, match)
            decision = LabDecision(
                RulesAction("construct", (1, 0), orientation=1),
                reason_code="construct", reason_text="Open new connection choices.", nodes=7,
            )
            with patch.object(server, "choose_lab_decision", return_value=decision):
                server.apply_computer_action(game, match)
            with patch.object(server, "get_profile", side_effect=AssertionError("legacy label")):
                view = server.public_view(game, match, decision)
            public = view["computer_decision"]
            self.assertEqual(public["action"], "construct")
            self.assertEqual(public["face"], [1, 0])
            self.assertEqual(public["orientation"], 1)
            self.assertEqual(public["reason_code"], "construct")
            self.assertEqual(public["reason_text"], decision.reason_text if explain else "")
            self.assertTrue(public["provisional"])
            self.assertFalse({"score", "weights", "profile"} & set(public))
            self.assertEqual(view["native_opponent"], lab_native_public())
            self.assertEqual(view["native_opponent"]["status"], "provisional")
            self.assertEqual(view["mcts_admission"], {"status": "unmeasured", "comparative_games": 0})
            restored, restored_match = self.continuation(game, match)
            self.assertIsNone(server.public_view(restored, restored_match)["computer_decision"])
        for entry in server.ruleset_catalog_public()["rulesets"]:
            if entry.get("experimental"):
                self.assertEqual(entry["native_evaluator_revision"], "lab-native-objective-v1")
                self.assertEqual(entry["native_opponent"], lab_native_public())
                self.assertEqual(entry["analysis_status"], "unmeasured")


if __name__ == "__main__":
    unittest.main()
