"""Integration boundaries for laboratory games, not strategic evidence."""

import copy
import unittest

from actions import RulesAction, RulesState, apply_action, legal_actions
from game_factory import load_game, new_game
from varde import BLACK, WHITE, Game, Illegal


SCORING_RULES = ("line-breath", "gjerde-majority", "breath-connection")
LEGACY_RULES = ("classic", "rosette", "breath", "breath-run", "gjerde", "gjerde-go")


class TestLabFactory(unittest.TestCase):
    def test_legacy_constructor_and_loader_remain_exact(self):
        for rules in LEGACY_RULES:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=rules, n=n):
                    original = Game(n, rules=rules)
                    made = new_game(n, rules=rules)
                    self.assertIs(type(made), Game)
                    self.assertEqual(made.to_dict(), original.to_dict())
                    for format_id in ("varde-game", "cairn-game"):
                        payload = original.to_dict() | {"format": format_id}
                        self.assertEqual(load_game(payload).to_dict(), original.to_dict())

    def test_laboratory_requires_explicit_opt_in(self):
        for rules in SCORING_RULES:
            with self.assertRaisesRegex(ValueError, "experimental"):
                new_game(3, rules=rules)
            made = new_game(3, rules=rules, experimental=True)
            self.assertEqual(made.rules, rules)
            self.assertEqual(made.to_dict()["version"], 2)
            self.assertEqual(load_game(made.to_dict()).to_dict(), made.to_dict())
        for rules in ("unknown", "breath-cap", "breath-extend"):
            with self.assertRaises(ValueError):
                new_game(3, rules=rules)
        with self.assertRaisesRegex(ValueError, "research"):
            new_game(3, rules="go-static-y", experimental=True)
        # Archived legacy saves remain loadable, without reopening public games.
        self.assertEqual(load_game(Game(3, rules="breath-cap").to_dict()).rules, "breath-cap")

    def test_bad_headers_and_sizes_fail_explicitly(self):
        for n in (True, False, 2, 7, 3.0, "3"):
            with self.assertRaises(ValueError):
                new_game(n, rules="breath-connection", experimental=True)
        for payload in (None, [], {}, {"version": 3}, {"version": True}):
            with self.assertRaises(ValueError):
                load_game(payload)

    def test_complete_analysis_key_separates_history_without_changing_legacy_key(self):
        for rules in ("breath", "breath-connection"):
            game = new_game(3, rules=rules, experimental=rules in SCORING_RULES)
            state = RulesState.from_game(game)
            state = apply_action(state, legal_actions(state)[0])
            altered = state.clone()
            # Mechanical cache test only: remove an actual earlier position, do
            # not export it as reachable evidence or conceal a legal alternative.
            earlier = next(item for item in altered.game.history if item != (
                altered.game.repetition_key() if hasattr(altered.game, "repetition_key")
                else (altered.game.to_move, tuple(altered.game.state[p] for p in altered.game.board.points))
            ))
            altered.game.history.remove(earlier)
            self.assertNotEqual(state.analysis_key(), altered.analysis_key())
            if rules == "breath":
                self.assertEqual(state.key(), altered.key())
            else:
                self.assertEqual(state.game.repetition_key(), altered.game.repetition_key())
                self.assertNotEqual(state.key(), altered.key())
            other_seats = state.clone()
            other_seats.seats[BLACK] = "another-seat"
            self.assertNotEqual(state.analysis_key(), other_seats.analysis_key())
            self.assertEqual(state.analysis_key(), state.clone().analysis_key())

    def test_structured_action_round_trips_and_rejects_ambiguous_payloads(self):
        for action in (
            RulesAction("play", (2, 0)), RulesAction("pass"), RulesAction("swap"),
            RulesAction("construct", (0, 0), orientation=1),
            RulesAction("plant", (1, -1), orientation=0),
        ):
            self.assertEqual(RulesAction.from_dict(action.to_dict()), action)
        self.assertEqual(repr(RulesAction("play", (2, 0))), "RulesAction(kind='play', point=(2, 0))")
        self.assertEqual(RulesAction("play", (2, 0)).sort_key(), (2, (2, 0)))
        invalid = (
            {}, {"action": "play", "point": [True, 0]},
            {"action": "pass", "point": [2, 0]},
            {"action": "construct", "face": [0, 0]},
            {"action": "plant", "face": [0, 0], "orientation": True},
            {"action": "construct", "point": [0, 0], "orientation": 0},
            {"action": "play", "point": [2, 0], "orientation": 0},
            {"action": "pass", "extra": 1},
        )
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                RulesAction.from_dict(payload)

    def test_seat_envelope_preserves_takeover_and_between_acceptances(self):
        for rules in ("classic",) + SCORING_RULES:
            state = RulesState.from_game(new_game(3, rules=rules, experimental=True))
            state = apply_action(state, legal_actions(state)[0])
            state = apply_action(state, RulesAction("swap"))
            self.assertEqual(state.seats[BLACK], "seat-white")
            state = apply_action(state, RulesAction("pass"))
            state = apply_action(state, RulesAction("pass"))
            state = apply_action(state, RulesAction("accept"))
            payload = state.to_dict()
            restored = RulesState.from_dict(payload)
            self.assertFalse(restored.terminal)
            self.assertEqual(restored.analysis_key(), state.analysis_key())
            resumed = apply_action(restored, RulesAction("resume"))
            self.assertEqual(resumed.end_acceptances, set())
            self.assertTrue(resumed.game.resumption_used)
            resumed = apply_action(resumed, RulesAction("pass"))
            resumed = apply_action(resumed, RulesAction("pass"))
            ended = apply_action(resumed, RulesAction("accept"))
            self.assertTrue(RulesState.from_dict(ended.to_dict()).terminal)
            with self.assertRaises(Illegal):
                apply_action(ended, RulesAction("resume"))

    def test_invalid_seat_envelope_cannot_fabricate_terminal_state(self):
        state = RulesState.from_game(new_game(3))
        payload = state.to_dict()
        for update in (
            {"accepted": True}, {"accepted": 1}, {"end_acceptances": ["intruder"]},
            {"end_decider": WHITE}, {"seats": {BLACK: "same", WHITE: "same"}},
        ):
            bad = copy.deepcopy(payload)
            bad["rules_state"].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                RulesState.from_dict(bad)

    def test_ending_envelope_requires_the_actual_acceptance_sequence(self):
        state = RulesState.from_game(new_game(3))
        state = apply_action(state, legal_actions(state)[0])
        state = apply_action(state, RulesAction("pass"))
        state = apply_action(state, RulesAction("pass"))
        other_color = WHITE if state.game.to_move == BLACK else BLACK
        bad = state.to_dict()
        bad["rules_state"]["end_decider"] = other_color
        with self.assertRaises(ValueError):
            RulesState.from_dict(bad)
        bad["rules_state"]["end_decider"] = state.game.to_move
        bad["rules_state"]["end_acceptances"] = [state.seats[other_color]]
        with self.assertRaises(ValueError):
            RulesState.from_dict(bad)
        resumed = apply_action(state, RulesAction("resume"))
        resumed = apply_action(resumed, RulesAction("pass"))
        resumed = apply_action(resumed, RulesAction("pass"))
        ended = apply_action(resumed, RulesAction("accept"))
        bad = ended.to_dict()
        bad["rules_state"]["end_acceptances"] = list(ended.seats.values())
        with self.assertRaises(ValueError):
            RulesState.from_dict(bad)
        bad["rules_state"]["end_acceptances"] = [ended.seats[other_color]]
        with self.assertRaises(ValueError):
            RulesState.from_dict(bad)

    def test_construction_actions_are_deeply_immutable(self):
        for kind in ("construct", "plant"):
            with self.assertRaises(ValueError):
                RulesAction(kind, [0, 0], orientation=0)
            self.assertIsInstance(hash(RulesAction(kind, (0, 0), orientation=0)), int)


if __name__ == "__main__":
    unittest.main()
