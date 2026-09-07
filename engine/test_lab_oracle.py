"""Mechanical oracle tests; no proof searches or research corpus generation."""

from dataclasses import FrozenInstanceError, replace
import unittest

from research.harness.lab_oracle import (
    OracleAction, geometry, load_snapshot, new_state, replay, score, transition,
)
from research.harness.lab_oracle_geometry import RULES


class TestLabOracle(unittest.TestCase):
    def test_empty_board_and_original_opening_geometry(self):
        for rules, spec in RULES.items():
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    state = new_state(rules, n, seed=19)
                    expected = 9 * n * n - 3 * n if spec.lines else 6 * n * n
                    self.assertEqual(len(geometry(state).original_points), expected)
                    self.assertEqual(score(state), {"B": 0, "W": 0})

    def test_action_parser_has_one_strict_immutable_representation(self):
        raw = {"action": "plant", "face": [0, 0], "orientation": 1}
        action = OracleAction.from_dict(raw)
        raw["face"][0] = 9
        self.assertEqual(action.point, (0, 0))
        wire = action.to_dict()
        wire["face"][0] = 8
        self.assertEqual(action.point, (0, 0))
        with self.assertRaises(FrozenInstanceError):
            action.orientation = 0
        bad = (
            {"action": "play", "point": [True, 0]},
            {"action": "play", "point": (0, 0)},
            {"action": "construct", "face": [0, 0], "orientation": True},
            {"action": "construct", "point": [0, 0], "orientation": 0},
            {"action": "pass", "point": [0, 0]},
            {"action": "unknown"},
        )
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                OracleAction.from_dict(value)

    def test_geometry_and_state_snapshots_have_no_mutable_aliases(self):
        state = new_state("junction-y")
        board = geometry(state)
        point = board.original_points[0]
        with self.assertRaises(TypeError):
            board.neighbors[point] = ()
        with self.assertRaises(FrozenInstanceError):
            state.moves_played = 1
        child = transition(state, OracleAction("play", point)).state
        self.assertIsNone(state.at(point))
        self.assertEqual(child.at(point), "B")
        wire = child.to_dict()
        wire["stacks"][board.index[point]][0] = "W"
        wire["journal"][0]["point"][0] += 99
        wire["history"].clear()
        self.assertEqual(child.at(point), "B")
        self.assertEqual(child.journal[0].point, point)
        self.assertEqual(len(child.history), 2)
        self.assertIs(geometry(state), geometry(child))

    def test_analysis_identity_includes_forbidden_history_and_seat_phase(self):
        state = new_state("junction-six")
        child = transition(state, OracleAction("play", geometry(state).original_points[0])).state
        # Constructed key comparison only; no fabricated history is used as
        # admissible evidence or to hide a legal action in a research position.
        altered = replace(child, history=frozenset((child.repetition_key(),)))
        self.assertEqual(altered.repetition_key(), child.repetition_key())
        self.assertNotEqual(altered.analysis_key(), child.analysis_key())
        takeover = transition(child, OracleAction("swap")).state
        self.assertEqual(takeover.repetition_key(), child.repetition_key())
        self.assertNotEqual(takeover.analysis_key(), child.analysis_key())

    def test_state_rejects_noncanonical_or_mutable_topology(self):
        state = new_state("go-static-y", seed=31)
        with self.assertRaises(ValueError):
            replace(state, topology=state.topology[::-1])
        with self.assertRaises(ValueError):
            replace(state, topology=list(state.topology))
        for rules in ("classic", "breath", "junction-unknown"):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                new_state(rules)

    def test_acceptance_wire_order_is_not_historical_order(self):
        state = new_state("go-honeycomb", seats=("z-original-black", "a-original-white"))
        result = replay(state, (
            OracleAction("play", geometry(state).original_points[0]),
            OracleAction("pass"), OracleAction("pass"),
            OracleAction("accept"), OracleAction("accept"),
        ))
        payload = result.state.to_dict()
        payload["rules_state"]["end_acceptances"].reverse()
        before = payload["rules_state"]["end_acceptances"][:]
        imported = load_snapshot(payload)
        self.assertTrue(imported.state.terminal)
        self.assertFalse(imported.full_action_replay)
        self.assertEqual(imported.state, result.state)
        self.assertEqual(payload["rules_state"]["end_acceptances"], before)


if __name__ == "__main__":
    unittest.main()
