"""Golden legacy regression gate for the experimental Rules Laboratory."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from actions import RulesState, apply_action
from varde import BLACK, WHITE, Game, Illegal
from research.harness.lab_compatibility import (
    BASE, RULESETS, SIZES, action_from_dict, file_digest, load_fixture,
    observe_case, replay, ROOT, state_observation,
)


class TestLabLegacyCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()

    def test_matrix_covers_six_candidates_four_sizes_and_both_difficulties(self):
        self.assertEqual(self.fixture["source_base"], BASE)
        for rules in RULESETS:
            for size in SIZES:
                for position in ("fresh", "seeded-six"):
                    case_id = f"{rules}-n{size}-{position}"
                    case = next(c for c in self.fixture["cases"] if c["id"] == case_id)
                    self.assertEqual(
                        {decision["difficulty"] for decision in case["decisions"]},
                        {"casual", "standard"},
                    )
                    self.assertNotIn("elapsed_ms", json.dumps(case))

    def test_seeded_decision_and_state_parity_including_administrative_actions(self):
        for case in self.fixture["cases"]:
            with self.subTest(case=case["id"]):
                actual = observe_case(case)
                self.assertEqual(actual["state"], case["state"])
                self.assertEqual(actual["decisions"], case["decisions"])

    def test_superko_is_reachable_without_fabricated_history(self):
        case = next(c for c in self.fixture["cases"] if c["id"].endswith("reachable-ko"))
        state = replay(case["rules"], case["n"], case["setup_actions"])
        self.assertEqual(state.game.moves_played, 8)
        self.assertEqual(len(state.game.history), 9)
        with self.assertRaisesRegex(Illegal, "repetition"):
            apply_action(state, action_from_dict(case["rejected_action"]), validate=False)

    def test_pie_swaps_complete_identity_and_resumption_remains_once_only(self):
        for rules in RULESETS:
            prefix = f"{rules}-n3-"
            cases = {c["id"][len(prefix):]: c for c in self.fixture["cases"] if c["id"].startswith(prefix)}
            self.assertEqual(cases["pie-taken"]["state"]["seats"], {
                BLACK: "seat-white", WHITE: "seat-black",
            })
            self.assertFalse(cases["first-acceptance"]["state"]["terminal"])
            self.assertTrue(cases["both-accept"]["state"]["terminal"])
            self.assertTrue(cases["final-acceptance"]["state"]["terminal"])
            ending = cases["second-ending"]
            state = replay(rules, 3, ending["setup_actions"])
            with self.assertRaises(Illegal):
                apply_action(state, action_from_dict({"action": "resume"}))

    def test_version_one_save_formats_and_replay_keep_full_history(self):
        self.assertEqual(
            {(s["payload"]["rules"], s["payload"]["n"]) for s in self.fixture["saves"]},
            {(rules, size) for rules in RULESETS for size in SIZES},
        )
        self.assertEqual(len(self.fixture["saves"]), len(RULESETS) * len(SIZES))
        self.assertEqual(
            {s["payload"]["format"] for s in self.fixture["saves"]},
            {"varde-game", "cairn-game"},
        )
        for example in self.fixture["saves"]:
            with self.subTest(save=example["id"]):
                payload = example["payload"]
                self.assertEqual(payload["version"], 1)
                original = replay(payload["rules"], payload["n"], example["setup_actions"])
                for format_id in ("varde-game", "cairn-game"):
                    with self.subTest(format=format_id):
                        restored = Game.from_dict(dict(payload, format=format_id))
                        self.assertEqual(restored.to_dict(), original.game.to_dict())
                        self.assertEqual(restored.history, original.game.history)
                        state = RulesState.from_game(restored)
                        for action in example["continuation"]:
                            apply_action(state, action_from_dict(action), copy=False)
                        self.assertEqual(state_observation(state), example["final"])

    def test_historical_manifests_results_and_golden_fixture_are_byte_preserved(self):
        protected = self.fixture["protections"]["historical_sha256"]
        self.assertGreaterEqual(len(protected), 16)
        for path, expected in protected.items():
            with self.subTest(path=path):
                self.assertEqual(file_digest(ROOT / path), expected)
        # Source hashes establish the initial provenance, not an implementation
        # freeze: legitimate factory wiring may change source but not behavior.
        self.assertIn("engine/varde.py", self.fixture["protections"]["generation_source_sha256"])

    def test_fixture_tampering_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            payload = dict(self.fixture, source_base="changed")
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_fixture(path)


if __name__ == "__main__":
    unittest.main()
