"""Independent match/adapter boundary tests; no agent or strength evidence."""

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from actions import RulesAction, legal_actions
from game_factory import new_game
from lab_match import apply_lab_action
from lab_spec import LAB_SPECS
import server
from varde import BLACK, WHITE, Illegal, other


class TestLabServerOwnership(unittest.TestCase):
    def setUp(self):
        model = patch.object(server, "MODEL", Mock(status=lambda: {}))
        model.start()
        self.addCleanup(model.stop)

    def make_match(self, rules="junction-y", **settings):
        game = new_game(3, rules=rules, experimental=True)
        match = server.MatchConfig.from_new_game(game, settings)
        self.assertIs(match.lab_state.game, game)
        self.assertIs(match.end_acceptances, match.lab_state.end_acceptances)
        return game, match

    def act(self, game, match, kind, point=None, *, actor_kind=None):
        if actor_kind is None:
            actor_kind = match.seats[match.lab_state.actor_color].kind
        before_state = match.lab_state
        result = apply_lab_action(
            game, match, RulesAction(kind, point), actor_kind=actor_kind,
        )
        self.assertIs(result, before_state)
        self.assertIs(match.lab_state, before_state)
        self.assertIs(match.lab_state.game, game)
        self.assertIs(match.end_acceptances, match.lab_state.end_acceptances)
        return result

    def ending(self, game, match):
        if game.moves_played == 0:
            self.act(game, match, "play", game.board.points[0])
        self.act(game, match, "pass")
        self.act(game, match, "pass")
        self.assertTrue(game.finished)
        self.assertFalse(match.lab_state.terminal)
        self.assertEqual(match.lab_state.actor_color, game.to_move)

    def round_trip(self, game, match):
        payload = server.snapshot_payload(game, match)
        restored, restored_match = server.load_snapshot(deepcopy(payload))
        self.assertEqual(server.snapshot_payload(restored, restored_match), payload)
        self.assertEqual(restored_match.lab_state.analysis_key(), match.lab_state.analysis_key())
        self.assertIs(restored_match.lab_state.game, restored)
        self.assertIs(restored_match.end_acceptances, restored_match.lab_state.end_acceptances)
        self.assertIsNot(restored, game)
        self.assertIsNot(restored_match.lab_state, match.lab_state)
        return restored, restored_match

    def test_all_seven_games_represent_three_modes_without_profiles(self):
        configurations = (
            {"mode": "hotseat", "players": {BLACK: "Ada", WHITE: "Grace"}},
            {"mode": "computer", "human_color": BLACK, "difficulty": "casual", "seed": 71},
            {"mode": "computer", "human_color": WHITE, "difficulty": "standard", "seed": 73},
            {"mode": "watch", "black_difficulty": "casual", "white_difficulty": "standard", "seed": 79},
        )
        for spec in LAB_SPECS:
            for settings in configurations:
                with self.subTest(rules=spec.id, settings=settings):
                    game, match = self.make_match(spec.id, **settings)
                    view = server.public_view(game, match)
                    self.assertEqual(view["actor_seat"], match.seats[BLACK].identity)
                    self.assertEqual(view["players"], {c: match.seats[c].name for c in (BLACK, WHITE)})
                    self.assertIsNone(view["match"]["profile"])
                    for seat in view["match"]["seats"].values():
                        self.assertIsNone(seat.get("profile"))
                    self.assertEqual(
                        view["match"]["computer_can_act"], match.seats[BLACK].kind == "computer",
                    )
                    self.round_trip(game, match)

    def test_human_and_computer_pie_takeover_swap_complete_seats_once(self):
        for human_color in (BLACK, WHITE):
            with self.subTest(human_color=human_color):
                game, match = self.make_match(
                    mode="computer", human_color=human_color, difficulty="casual", seed=123,
                )
                black, white = match.seats[BLACK], match.seats[WHITE]
                self.act(game, match, "play", game.board.points[0])
                self.assertTrue(game.swap_available)
                self.assertEqual(match.lab_state.actor_seat, white.identity)
                self.act(game, match, "swap")
                self.assertIs(match.seats[BLACK], white)
                self.assertIs(match.seats[WHITE], black)
                self.assertEqual(game.players, {BLACK: white.name, WHITE: black.name})
                self.assertEqual(match.lab_state.seats, {BLACK: white.identity, WHITE: black.identity})
                self.assertEqual(match.human_color, other(human_color))
                self.assertEqual(match.lab_state.actor_seat, black.identity)
                self.assertEqual(match.lab_state.actor_color, WHITE)
                computer = match.seats[match.computer_color]
                self.assertEqual((computer.difficulty, computer.seed, computer.profile), ("casual", 123, None))
                before = server.snapshot_payload(game, match)
                with self.assertRaises(Illegal):
                    self.act(game, match, "swap")
                self.assertEqual(server.snapshot_payload(game, match), before)
                self.round_trip(game, match)

    def test_watch_takeover_keeps_independent_settings_and_seeds(self):
        game, match = self.make_match(
            mode="watch", black_difficulty="casual", white_difficulty="standard", seed=37,
        )
        black, white = match.seats[BLACK], match.seats[WHITE]
        self.act(game, match, "play", game.board.points[0])
        self.act(game, match, "swap")
        self.assertIs(match.seats[BLACK], white)
        self.assertIs(match.seats[WHITE], black)
        self.assertEqual((white.difficulty, white.seed), ("standard", 38))
        self.assertEqual((black.difficulty, black.seed), ("casual", 37))
        self.round_trip(game, match)

    def test_wrong_kind_cannot_place_pass_swap_or_decide_an_ending(self):
        for human_color in (BLACK, WHITE):
            game, match = self.make_match(mode="computer", human_color=human_color)
            phases = (
                (RulesAction("play", game.board.points[0]), RulesAction("pass")),
                (RulesAction("swap"), RulesAction("pass")),
                (RulesAction("accept"), RulesAction("resume")),
            )
            for index, actions in enumerate(phases):
                if index == 1:
                    self.act(game, match, "play", game.board.points[0])
                elif index == 2:
                    self.ending(game, match)
                wrong = "human" if match.seats[match.lab_state.actor_color].kind == "computer" else "computer"
                before = server.snapshot_payload(game, match)
                for action in actions:
                    with self.subTest(human_color=human_color, phase=index, action=action):
                        with self.assertRaises(Illegal):
                            apply_lab_action(game, match, action, actor_kind=wrong)
                        self.assertEqual(server.snapshot_payload(game, match), before)
                if wrong == "human":
                    with self.assertRaises(Illegal):
                        server.assert_human_action(game, match)
                else:
                    server.assert_human_action(game, match)

    def test_first_ending_needs_both_actual_seats_in_all_modes(self):
        for settings in (
            {"mode": "hotseat"}, {"mode": "watch"},
            {"mode": "computer", "human_color": BLACK},
            {"mode": "computer", "human_color": WHITE},
        ):
            with self.subTest(settings=settings):
                game, match = self.make_match(**settings)
                self.ending(game, match)
                first_color = match.lab_state.actor_color
                first_seat = match.lab_state.actor_seat
                self.act(game, match, "accept")
                self.assertEqual(match.end_acceptances, {first_seat})
                self.assertFalse(match.lab_state.terminal)
                self.assertFalse(match.end_decided)
                self.assertEqual(match.lab_state.actor_color, other(first_color))
                view = server.public_view(game, match)
                self.assertEqual(view["match"]["pending_end_deciders"], [other(first_color)])
                self.assertEqual(
                    match.computer_can_act(game), match.seats[other(first_color)].kind == "computer",
                )
                self.act(game, match, "accept")
                self.assertEqual(match.end_acceptances, {seat.identity for seat in match.seats.values()})
                self.assertTrue(match.end_decided)
                self.assertTrue(match.lab_state.terminal)
                view = server.public_view(game, match)
                self.assertTrue(view["accepted"])
                self.assertIsNone(view["actor_color"])
                self.assertIsNone(view["actor_seat"])
                self.assertEqual(view["legal_actions"], [])
                self.assertEqual(view["match"]["pending_end_deciders"], [])
                self.assertFalse(view["match"]["computer_can_act"])
                self.round_trip(game, match)

    def test_save_between_acceptances_continues_without_changing_original(self):
        game, match = self.make_match(mode="watch")
        self.act(game, match, "play", game.board.points[0])
        self.act(game, match, "swap")
        self.ending(game, match)
        first = match.lab_state.actor_seat
        self.act(game, match, "accept")
        before = server.snapshot_payload(game, match)
        for action in ("accept", "resume"):
            restored, restored_match = self.round_trip(game, match)
            self.assertEqual(restored_match.end_acceptances, {first})
            self.assertNotEqual(restored_match.lab_state.actor_seat, first)
            self.act(restored, restored_match, action)
            self.assertEqual(restored_match.lab_state.terminal, action == "accept")
            self.assertEqual(restored.resumption_used, action == "resume")
            self.round_trip(restored, restored_match)
            self.assertEqual(server.snapshot_payload(game, match), before)

    def test_resume_clears_acceptances_and_next_ending_has_exactly_one(self):
        for settings in (
            {"mode": "hotseat"}, {"mode": "watch"},
            {"mode": "computer", "human_color": BLACK},
            {"mode": "computer", "human_color": WHITE},
        ):
            with self.subTest(settings=settings):
                game, match = self.make_match(**settings)
                self.ending(game, match)
                self.act(game, match, "accept")
                self.act(game, match, "resume")
                self.assertEqual(match.end_acceptances, set())
                self.assertFalse(game.finished)
                self.assertTrue(game.resumption_used)
                self.assertIsNone(match.lab_state.end_decider)
                self.ending(game, match)
                self.assertEqual(legal_actions(match.lab_state), (RulesAction("accept"),))
                final_seat = match.lab_state.actor_seat
                self.act(game, match, "accept")
                self.assertTrue(match.lab_state.terminal)
                self.assertEqual(match.end_acceptances, {final_seat})
                payload = server.snapshot_payload(game, match)
                self.assertEqual(payload["match"]["end_acceptances"], [final_seat])
                self.assertEqual(payload["rules_state"]["end_acceptances"], [final_seat])
                self.round_trip(game, match)
                for action in ("accept", "resume", "pass"):
                    with self.assertRaises(Illegal):
                        apply_lab_action(game, match, RulesAction(action), actor_kind="human")
                    self.assertEqual(server.snapshot_payload(game, match), payload)

    def test_snapshot_rejects_disagreement_between_match_and_rules_state(self):
        game, match = self.make_match(mode="watch")
        self.ending(game, match)
        self.act(game, match, "accept")
        payload = server.snapshot_payload(game, match)
        mutations = (
            lambda p: p["match"]["seats"][BLACK].update(identity="forged-seat"),
            lambda p: p["rules_state"]["seats"].update({BLACK: "forged-seat"}),
            lambda p: p["match"]["seats"][BLACK].update(name="Forged name"),
            lambda p: p["match"].update(end_acceptances=[]),
            lambda p: p["match"].update(end_acceptances=list(p["rules_state"]["seats"].values())),
            lambda p: p["match"].update(end_decided=True),
            lambda p: p["match"].update(mode="hotseat"),
            lambda p: p["match"].update(mode="computer"),
            lambda p: p.pop("rules_state"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                bad = deepcopy(payload)
                mutate(bad)
                with self.assertRaises(ValueError):
                    server.load_snapshot(bad)
                self.assertEqual(server.snapshot_payload(game, match), payload)

    def test_explicit_profiles_and_advanced_are_rejected_without_personal_lookup(self):
        with patch.object(server, "get_profile", side_effect=AssertionError("legacy profile lookup")):
            for mode in ("hotseat", "computer", "watch"):
                for key in ("profile", "black_profile", "white_profile"):
                    for profile in ("balanced", "personal", "raider", "unknown"):
                        with self.subTest(mode=mode, key=key, profile=profile):
                            with self.assertRaises(ValueError):
                                self.make_match(mode=mode, **{key: profile})
            for settings in (
                {"mode": "computer", "difficulty": "advanced"},
                {"mode": "watch", "black_difficulty": "advanced"},
                {"mode": "watch", "white_difficulty": "advanced"},
            ):
                with self.subTest(settings=settings), self.assertRaises(ValueError):
                    self.make_match(**settings)

    def test_saved_profiles_cannot_migrate_laboratory_seats_to_personal(self):
        game, match = self.make_match(mode="watch")
        payload = server.snapshot_payload(game, match)
        for color in (BLACK, WHITE):
            for fields in ({"profile": "personal"}, {"profile": "balanced"}, {"difficulty": "advanced"}):
                with self.subTest(color=color, fields=fields):
                    bad = deepcopy(payload)
                    bad["match"]["seats"][color].update(fields)
                    with self.assertRaises(ValueError):
                        server.load_snapshot(bad)
        self.round_trip(game, match)

    def test_api_spine_computer_stage_fails_closed_without_legacy_search(self):
        game, match = self.make_match(mode="computer", human_color=WHITE)
        before = server.snapshot_payload(game, match)
        with patch.object(server, "choose_decision", side_effect=AssertionError("legacy search")), \
                patch.object(server, "get_profile", side_effect=AssertionError("legacy profile")):
            with self.assertRaisesRegex(Illegal, "not yet available"):
                server.apply_computer_action(game, match)
        self.assertEqual(server.snapshot_payload(game, match), before)


if __name__ == "__main__":
    unittest.main()
