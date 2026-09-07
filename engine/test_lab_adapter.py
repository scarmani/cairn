"""Laboratory API-spine contracts; native search remains a separate unit."""

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from actions import RulesAction, legal_actions
from game_factory import new_game
from lab_match import (
    action_from_alias, apply_lab_action, lab_computer_settings, lab_state,
)
from lab_spec import LAB_SPECS
import server
from varde import BLACK, WHITE, Game, Illegal, rulesets_public


def laboratory(rules="junction-y", **body):
    game = new_game(3, rules=rules, experimental=True)
    return game, server.MatchConfig.from_new_game(game, body)


def act(game, match, kind, point=None, orientation=None):
    actor = match.seats[match.lab_state.actor_color].kind
    return apply_lab_action(
        game, match, RulesAction(kind, point, orientation=orientation), actor_kind=actor,
    )


class TestLabMatchAdapter(unittest.TestCase):
    def setUp(self):
        self.model = patch.object(server, "MODEL", Mock(status=lambda: {"games_trained": 0}))
        self.model.start()
        self.addCleanup(self.model.stop)

    def test_all_three_modes_bind_one_game_and_authoritative_seat_identities(self):
        for mode in ("hotseat", "computer", "watch", "computer_vs_computer"):
            game, match = laboratory(mode=mode)
            state = lab_state(game, match)
            self.assertIs(state.game, game)
            self.assertIs(state.end_acceptances, match.end_acceptances)
            self.assertEqual(state.seats, {color: match.seats[color].identity for color in (BLACK, WHITE)})
            self.assertEqual(match.mode, "watch" if mode == "computer_vs_computer" else mode)
            self.assertEqual(game.players, {color: match.seats[color].name for color in (BLACK, WHITE)})

    def test_public_and_snapshot_reads_do_not_reinitialize_the_pending_actor(self):
        game, match = laboratory(players={BLACK: "Ada", WHITE: "Grace"})
        act(game, match, "play", (2, 0))
        act(game, match, "pass")
        act(game, match, "pass")
        act(game, match, "accept")
        state = match.lab_state
        before = state.analysis_key()
        view = server.public_view(game, match)
        self.assertEqual(view["current_player"], match.seats[state.actor_color].name)
        self.assertNotEqual(state.actor_color, game.to_move)
        server.snapshot_payload(game, match)
        server.public_view(game, match)
        self.assertIs(match.lab_state, state)
        self.assertEqual(state.analysis_key(), before)

    def test_computer_settings_never_normalize_to_a_classic_profile(self):
        for mode in ("computer", "watch"):
            game, match = laboratory(mode=mode)
            for seat in match.seats.values():
                self.assertIsNone(seat.profile)
            self.assertIsNone(server.public_view(game, match)["match"]["profile"])
        for difficulty in ("casual", "standard"):
            self.assertEqual(lab_computer_settings(difficulty), (difficulty, None))
        for difficulty in ("advanced", None, "mcts", 1):
            with self.assertRaises(ValueError):
                lab_computer_settings(difficulty)
        for mode in ("hotseat", "computer", "watch"):
            for field in ("profile", "black_profile", "white_profile"):
                for profile in ("balanced", "personal", "mason", ""):
                    with self.subTest(mode=mode, field=field, profile=profile), self.assertRaises(ValueError):
                        laboratory(mode=mode, **{field: profile})

    def test_complete_computer_seats_swap_once_with_difficulty_and_seed(self):
        game, match = laboratory(mode="watch", seed=91, black_difficulty="casual", white_difficulty="standard")
        black, white = match.seats[BLACK], match.seats[WHITE]
        act(game, match, "play", (2, 0))
        act(game, match, "swap")
        self.assertIs(match.seats[BLACK], white)
        self.assertIs(match.seats[WHITE], black)
        self.assertEqual((match.seats[BLACK].difficulty, match.seats[BLACK].seed), ("standard", 92))
        self.assertEqual((match.seats[WHITE].difficulty, match.seats[WHITE].seed), ("casual", 91))
        self.assertEqual(match.lab_state.actor_seat, black.identity)
        self.assertEqual(game.players, {BLACK: white.name, WHITE: black.name})
        before = server.snapshot_payload(game, match)
        with self.assertRaises(Illegal):
            act(game, match, "swap")
        self.assertEqual(server.snapshot_payload(game, match), before)

    def test_pending_human_ending_decision_is_never_skipped_for_computer(self):
        game, match = laboratory(mode="computer", human_color=WHITE)
        act(game, match, "play", (2, 0))
        act(game, match, "pass")
        act(game, match, "pass")
        self.assertEqual(match.lab_state.actor_color, WHITE)
        self.assertIsNone(match.next_computer_color(game))
        self.assertFalse(match.computer_can_act(game))
        before = server.snapshot_payload(game, match)
        with self.assertRaises(Illegal):
            apply_lab_action(game, match, RulesAction("accept"), actor_kind="computer")
        self.assertEqual(server.snapshot_payload(game, match), before)
        act(game, match, "accept")
        self.assertEqual(match.next_computer_color(game), BLACK)
        self.assertTrue(match.computer_can_act(game))
        act(game, match, "resume")
        self.assertFalse(game.finished)
        self.assertEqual(match.end_acceptances, set())

    def test_watch_endings_include_both_seats_and_one_post_resumption_acceptance(self):
        game, match = laboratory(mode="watch")
        act(game, match, "play", (2, 0))
        act(game, match, "pass")
        act(game, match, "pass")
        first_identity = match.lab_state.actor_seat
        act(game, match, "accept")
        self.assertFalse(match.end_decided)
        self.assertEqual(match.end_acceptances, {first_identity})
        self.assertNotEqual(match.lab_state.actor_seat, first_identity)
        self.assertTrue(match.computer_can_act(game))
        act(game, match, "resume")
        act(game, match, "pass")
        act(game, match, "pass")
        final_identity = match.lab_state.actor_seat
        act(game, match, "accept")
        self.assertEqual(match.end_acceptances, {final_identity})
        self.assertTrue(match.end_decided)
        self.assertFalse(match.computer_can_act(game))
        view = server.public_view(game, match)
        self.assertIsNone(view["current_player"])
        self.assertFalse(view["resumption_available"])
        saved = server.snapshot_payload(game, match)
        restored, restored_match = server.load_snapshot(saved)
        self.assertEqual(server.snapshot_payload(restored, restored_match), saved)

    def test_computer_executes_native_legal_action_without_legacy_fallback(self):
        game, match = laboratory(mode="computer", human_color=WHITE, difficulty="casual")
        before = server.snapshot_payload(game, match)
        available = legal_actions(match.lab_state)
        with patch.object(server, "choose_decision") as legacy, patch.object(server, "get_profile") as profile:
            decision = server.apply_computer_action(game, match)
            legacy.assert_not_called()
            profile.assert_not_called()
        self.assertIn(decision.action, available)
        self.assertEqual(decision.action.kind, "play")
        self.assertEqual(game.placements_played, 1)
        self.assertEqual(game.constructions_played, 0)
        self.assertNotEqual(server.snapshot_payload(game, match), before)
        self.assertTrue(decision.to_dict()["provisional"])

    def test_binding_drift_and_legacy_ending_shortcuts_are_rejected(self):
        game, match = laboratory()
        for operation in (lambda: match.clear_end_acceptances(),
                          lambda: match.accept_end(game, BLACK),
                          lambda: setattr(match, "end_decided", True)):
            with self.assertRaises(ValueError):
                operation()
        match.seats[BLACK].name = "Changed outside binding"
        with self.assertRaisesRegex(ValueError, "binding"):
            server.public_view(game, match)

    def test_snapshot_cross_validation_rejects_identity_name_mode_and_acceptance_changes(self):
        game, match = laboratory(mode="watch")
        act(game, match, "play", (2, 0))
        act(game, match, "pass")
        act(game, match, "pass")
        act(game, match, "accept")
        original = server.snapshot_payload(game, match)
        changes = [
            lambda p: p["match"]["seats"][BLACK].update(identity="another"),
            lambda p: p["match"]["seats"][BLACK].update(name="another"),
            lambda p: p["match"].update(mode="computer"),
            lambda p: p["match"].update(end_acceptances=[]),
            lambda p: p["match"].update(end_acceptances=None),
            lambda p: p["match"].update(end_decided=True),
            lambda p: p["match"]["seats"][BLACK].update(profile="balanced"),
            lambda p: p["match"]["seats"][BLACK].update(difficulty="advanced"),
            lambda p: p["match"]["seats"][BLACK].update(seed=True),
            lambda p: p["match"].update(unsupported=True),
            lambda p: p.pop("rules_state"),
            lambda p: p.pop("match"),
        ]
        for change in changes:
            bad = deepcopy(original)
            change(bad)
            with self.assertRaises(ValueError):
                server.load_snapshot(bad)
        self.assertEqual(server.snapshot_payload(game, match), original)

    def test_snapshots_round_trip_all_rules_and_both_legacy_format_identifiers(self):
        for spec in LAB_SPECS:
            game, match = laboratory(spec.id, mode="computer", human_color=BLACK)
            act(game, match, "play", game.board.points[0])
            snapshot = server.snapshot_payload(game, match)
            for format_id in ("cairn-game", "varde-game"):
                restored, restored_match = server.load_snapshot(snapshot | {"format": format_id})
                self.assertEqual(server.snapshot_payload(restored, restored_match), snapshot)
                self.assertIs(restored_match.lab_state.game, restored)
                self.assertIs(restored_match.lab_state.end_acceptances, restored_match.end_acceptances)

    def test_static_controls_are_not_loadable_as_browser_lab_matches(self):
        game = new_game(3, rules="go-static-y", research=True)
        with self.assertRaisesRegex(ValueError, "research-only"):
            server.MatchConfig.from_new_game(game, {})
        with self.assertRaisesRegex(ValueError, "research-only"):
            server.load_snapshot(game.to_dict())

    def test_public_majority_cells_count_edges_not_individual_line_points(self):
        game, match = laboratory("gjerde-majority")
        view = server.public_view(game, match)
        self.assertTrue(all(point["original"] and not point["scoring"] for point in view["points"]))
        self.assertEqual(len(view["cells"]), 19)
        for cell in view["cells"]:
            self.assertEqual(len(cell["edges"]), 6)
            self.assertIsNone(cell["owner"])
            self.assertEqual(cell["counts"], {BLACK: 0, WHITE: 0})
        act(game, match, "play", game.board.points[0])
        view = server.public_view(game, match)
        self.assertTrue(any(cell["counts"][BLACK] for cell in view["cells"]))
        self.assertEqual(view["score"], {BLACK: 0, WHITE: 0})

    def test_points_use_real_distinct_liberties_and_zero_point_center(self):
        game, match = laboratory("junction-six")
        act(game, match, "play", (2, 0))
        act(game, match, "construct", (0, 0), 0)
        act(game, match, "play", (0, 0))
        view = server.public_view(game, match)
        center = next(point for point in view["points"] if point["coord"] == [0, 0])
        self.assertFalse(center["original"])
        self.assertFalse(center["scoring"])
        self.assertFalse(center["sky"])
        self.assertTrue(center["center"])
        self.assertEqual(len(center["neighbors"]), 6)
        self.assertEqual(view["control"], {BLACK: 2, WHITE: 0})
        self.assertEqual(view["original_control"], {BLACK: 1, WHITE: 0})
        group = {(2, 0), (0, 0)}
        liberties = {nb for p in group for nb in game.board.neighbors[p] if not game.state[nb]}
        self.assertEqual(center["group_libs"], len(liberties))

    def test_aliases_are_strict_and_cannot_override_the_route_action(self):
        self.assertEqual(action_from_alias("/api/play", {"point": [2, 0]}), RulesAction("play", (2, 0)))
        self.assertEqual(action_from_alias("/api/pass", {}), RulesAction("pass"))
        for route, body in (("/api/play", {"action": "pass"}), ("/api/play", {"point": [True, 0]}),
                            ("/api/pass", {"point": [2, 0]}), ("/api/unknown", {})):
            with self.assertRaises(ValueError):
                action_from_alias(route, body)

    def test_legacy_match_projection_and_catalog_entries_are_not_reinterpreted(self):
        game = Game(3)
        match = server.MatchConfig.from_new_game(game, {"mode": "computer", "difficulty": "advanced"})
        self.assertIsNone(match.lab_state)
        self.assertEqual(match.profile, "personal")
        view = server.public_view(game, match)
        for field in ("experimental", "accepted", "legal_actions", "construction_sites", "flat"):
            self.assertNotIn(field, view)
        payload = server.snapshot_payload(game, match)
        self.assertEqual(payload["version"], 1)
        self.assertNotIn("rules_state", payload)
        base = rulesets_public()["rulesets"]
        public = server.ruleset_catalog_public()["rulesets"]
        for original, actual in zip(base, public):
            self.assertEqual(original, {key: value for key, value in actual.items()
                                        if key != "native_evaluator_revision"})


if __name__ == "__main__":
    unittest.main()
