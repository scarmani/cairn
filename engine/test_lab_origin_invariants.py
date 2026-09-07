"""Independent full-origin mechanics checks, never actual-game proof search.

Every action list is a short explicitly authored mechanical sequence. No policy
rollouts, terminal proof production, corpus selection or research budget is used.
"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "engine"))

from research.harness import lab_origin as origin  # noqa: E402
from research.harness.lab_research_adapter import (  # noqa: E402
    LEGACY_CANDIDATES, PRODUCTION_RULESETS, production_provider,
)
from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402


KAGOME = {"gjerde", "gjerde-go", "line-breath", "gjerde-majority"}


def play(x, y):
    return {"action": "play", "point": [x, y]}


def kinds(*names):
    return [{"action": name} for name in names]


def reseal(payload):
    result = deepcopy(payload)
    result["record_hash"] = canonical_hash({key: item for key, item in result.items()
                                             if key != "record_hash"})
    return result


def first_hash_change(value):
    """Corrupt one declared source digest without supplying any external path."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str) and len(item) == 64 and all(c in "0123456789abcdef" for c in item):
                value[key] = "0" * 64 if item != "0" * 64 else "1" * 64
                return True
            if first_hash_change(item):
                return True
    elif isinstance(value, list):
        return any(first_hash_change(item) for item in value)
    return False


class TestLabOriginInvariants(unittest.TestCase):
    def make(self, rules="junction-y", actions=None, **configuration):
        config = origin.origin_configuration(rules, **configuration)
        actions = [play(2, 0)] if actions is None else actions
        before_config, before_actions = deepcopy(config), deepcopy(actions)
        record = origin.create_origin(config, actions)
        verified = origin.verify_origin(record)
        self.assertEqual(config, before_config)
        self.assertEqual(actions, before_actions)
        self.assertEqual(verified.production_root.to_dict(), record.to_dict()["final"]["snapshot"])
        if verified.independent_root is not None:
            self.assertEqual(verified.independent_root.to_dict(), verified.production_root.to_dict())
        return record, verified

    def test_all_sixteen_definitions_four_sizes_have_fresh_replay_without_independence_inflation(self):
        self.assertEqual(len(PRODUCTION_RULESETS), 16)
        for rules in PRODUCTION_RULESETS:
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    opening = play(3, 1) if rules in KAGOME else play(2, 0)
                    record, verified = self.make(rules, [opening], n=n, seed=17)
                    self.assertEqual(record.to_dict()["configuration"]["n"], n)
                    self.assertEqual(len(record.to_dict()["actions"]), 1)
                    expected = rules not in LEGACY_CANDIDATES
                    self.assertIs(verified.receipt["independent_mechanics"], expected)
                    self.assertEqual(verified.independent_root is not None, expected)
                    self.assertFalse(verified.receipt["admission_record"])

    def test_every_construction_orientation_is_an_explicit_full_action(self):
        for rules, kind, count in (("junction-y", "construct", 2),
                                   ("junction-six", "construct", 1),
                                   ("junction-planted", "plant", 2),
                                   ("junction-passage", "construct", 3)):
            hashes = []
            for orientation in range(count):
                with self.subTest(rules=rules, orientation=orientation):
                    action = {"action": kind, "face": [1, 0], "orientation": orientation}
                    record, verified = self.make(rules, [play(2, 0), action])
                    self.assertEqual(record.to_dict()["actions"][1]["action"], action)
                    self.assertIn((1, 0, orientation), verified.production_root.game.board.topology)
                    hashes.append(record.record_hash)
            self.assertEqual(len(set(hashes)), count)

    def test_captured_junction_retains_topology_and_full_legal_history(self):
        actions = [play(2, 0), {"action": "construct", "face": [0, 0], "orientation": 0},
                   play(-1, 1), play(0, 0), play(-1, -1)]
        record, verified = self.make(actions=actions)
        root = verified.production_root
        self.assertEqual(root.game.state[(0, 0)], ())
        self.assertIn((0, 0, 0), root.game.board.topology)
        self.assertEqual(len(record.to_dict()["actions"]), 5)
        self.assertGreater(len(root.game.history), 1)

    def test_same_seat_extension_and_explicit_closure_are_not_invented(self):
        opening = [play(*point) for point in ((2, 0), (1, 1), (-8, 0), (1, -1), (-8, -2), (5, -1))]
        extension = {"action": "extend", "point": [4, 0]}
        record, opened = self.make("breath-run", opening + [extension])
        root = opened.production_root
        self.assertTrue(root.game.extension_only_turn)
        self.assertEqual(root.actor_seat, "S1")
        self.assertEqual(record.to_dict()["actions"][-1]["before"]["actor"],
                         record.to_dict()["actions"][-1]["after"]["actor"])
        closed_record, closed = self.make("breath-run", opening + [extension, {"action": "finish-extension"}])
        self.assertFalse(closed.production_root.game.extension_only_turn)
        self.assertEqual(closed.production_root.actor_seat, "S2")
        bad = closed_record.to_dict()
        bad["actions"].pop()
        with self.assertRaises(ValueError):
            origin.verify_origin(reseal(bad))
        automatic, ended = self.make("breath-run", opening[:4] + [extension])
        self.assertFalse(ended.production_root.game.extension_only_turn)
        self.assertEqual(ended.production_root.actor_seat, "S2")
        self.assertNotIn("finish-extension", [row["action"]["action"] for row in automatic.to_dict()["actions"]])

    def test_pie_swaps_complete_identities_and_every_ending_action_is_recorded(self):
        for seats in ({"B": "S1", "W": "S2"}, {"B": "S2", "W": "S1"}):
            with self.subTest(seats=seats):
                actions = [play(2, 0)] + kinds("swap", "pass", "pass", "accept")
                partial_record, partial = self.make(actions=actions, seats=seats)
                self.assertFalse(partial.production_root.accepted)
                self.assertEqual(partial.production_root.seats, {"B": seats["W"], "W": seats["B"]})
                ended_record, ended = self.make(actions=actions + kinds("accept"), seats=seats)
                self.assertTrue(ended.production_root.accepted)
                self.assertEqual(len(ended_record.to_dict()["actions"]), 6)
                self.assertNotEqual(partial_record.record_hash, ended_record.record_hash)
                resumed_record, resumed = self.make(actions=actions + kinds("resume", "pass", "pass", "accept"), seats=seats)
                self.assertTrue(resumed.production_root.accepted)
                self.assertTrue(resumed.production_root.game.resumption_used)
                self.assertEqual(len(resumed_record.to_dict()["actions"]), 9)
                self.assertIs(resumed.receipt["independent_mechanics"], True)
                bad = ended_record.to_dict()
                bad["actions"].pop()
                with self.assertRaises(ValueError):
                    origin.verify_origin(reseal(bad))

    def test_bound_metadata_is_root_exact_and_does_not_change_default_provider(self):
        _record, verified = self.make()
        root = verified.production_root
        before = root.to_dict()
        bound = origin.bind_origin_provider(verified, root)
        self.assertTrue(bound.metadata(root)["provenance"]["full_action_replay"])
        self.assertFalse(production_provider("junction-y").metadata(root)["provenance"]["full_action_replay"])
        child = bound.transition(root, {"action": "pass"})
        self.assertFalse(bound.metadata(child)["provenance"]["full_action_replay"])
        with self.assertRaises(ValueError):
            origin.bind_origin_provider(verified, child)
        self.assertEqual(root.to_dict(), before)
        independent = origin.bind_origin_provider(verified, independent=True)
        self.assertTrue(independent.metadata(verified.independent_root)["provenance"]["full_action_replay"])
        _legacy_record, legacy = self.make("classic")
        with self.assertRaises(ValueError):
            origin.bind_origin_provider(legacy, independent=True)

    def test_bound_descriptor_identifies_wrapper_code_without_becoming_position_specific(self):
        _record, first = self.make()
        _other_record, second = self.make(actions=[play(2, 0), play(-2, 0)])
        base = production_provider("junction-y")
        first_provider = origin.bind_origin_provider(first)
        second_provider = origin.bind_origin_provider(second)
        self.assertNotEqual(first_provider.provider_id, base.provider_id)
        self.assertNotEqual(first_provider.implementation_hash, base.implementation_hash)
        self.assertEqual(first_provider.rules_hash, base.rules_hash)
        self.assertEqual(first_provider.rules_id, base.rules_id)
        self.assertEqual(first_provider.identity(), second_provider.identity())
        self.assertNotEqual(first_provider.metadata(first.production_root),
                            second_provider.metadata(second.production_root))

    def test_imported_suffix_or_wrong_history_cannot_gain_a_bound_origin(self):
        from actions import RulesState

        record, verified = self.make(actions=[play(2, 0), play(-2, 0)])
        altered = verified.production_root
        altered.game.history.remove(next(iter(altered.game.history)))
        with self.assertRaises(ValueError):
            origin.bind_origin_provider(verified, altered)
        # A complete origin may survive an exact serialization round trip; an
        # imported root alone still cannot manufacture a VerifiedOrigin receipt.
        restored = RulesState.from_dict(record.to_dict()["final"]["snapshot"])
        self.assertTrue(origin.bind_origin_provider(verified, restored).metadata(restored)["provenance"]["full_action_replay"])
        with self.assertRaises(ValueError):
            origin.bind_origin_provider(restored)
        suffix = record.to_dict()
        suffix["actions"] = suffix["actions"][1:]
        suffix["actions"][0]["index"] = 0
        with self.assertRaises(ValueError):
            origin.verify_origin(reseal(suffix))

    def test_authored_ko_history_survives_replay_and_forbidden_recapture_is_rejected(self):
        actions = [play(*point) for point in ((-8, 0), (-7, 1), (-8, -2), (-8, 2), (-5, -1), (-5, 1))]
        actions += kinds("pass") + [play(-7, -1)]
        _record, verified = self.make("go-honeycomb", actions)
        root = verified.production_root
        forbidden = play(-8, 0)
        self.assertNotIn(forbidden, production_provider("go-honeycomb").legal_actions(root))
        with self.assertRaises(ValueError):
            self.make("go-honeycomb", actions + [forbidden])

    def test_detached_records_receipts_and_roots_cannot_mutate_verified_state(self):
        record, verified = self.make()
        expected_record, expected_receipt = record.to_dict(), verified.receipt
        mutated = record.to_dict()
        mutated["actions"][0]["action"]["point"][0] = 999
        receipt = verified.receipt
        receipt["independent_mechanics"] = False
        root = verified.production_root
        root.game.history.clear()
        self.assertEqual(record.to_dict(), expected_record)
        self.assertEqual(verified.receipt, expected_receipt)
        self.assertGreater(len(verified.production_root.game.history), 0)
        self.assertTrue(origin.bind_origin_provider(verified).metadata(verified.production_root)["provenance"]["full_action_replay"])

    def test_forged_verified_receipts_and_internal_roots_are_replayed_not_trusted(self):
        _record, verified = self.make()
        for field, value in (("full_action_replay", False), ("version", True),
                             ("root_fingerprint", "0" * 64), ("admission_record", True)):
            forged_receipt = verified.receipt
            forged_receipt[field] = value
            forged_receipt["receipt_hash"] = canonical_hash({key: item for key, item in forged_receipt.items()
                                                              if key != "receipt_hash"})
            forged = replace(verified, _receipt_json=canonical_json(forged_receipt))
            with self.subTest(field=field), self.assertRaises(ValueError):
                origin.bind_origin_provider(forged)
        altered = verified.production_root
        altered.seats = {"B": "S2", "W": "S1"}
        with self.assertRaises(ValueError):
            origin.bind_origin_provider(replace(verified, _production=altered))

    def test_seed_normalization_is_explicit_and_only_prebuilt_topology_retains_it(self):
        for rules, effective in (("classic", 0), ("junction-y", 0), ("go-honeycomb", 0),
                                 ("go-static-six", 17), ("go-static-y", 17)):
            with self.subTest(rules=rules):
                record, verified = self.make(rules, [], seed=17)
                normalization = record.to_dict()["normalization"]
                self.assertEqual(normalization["requested_seed"], 17)
                self.assertEqual(normalization["effective_seed"], effective)
                self.assertEqual(normalization["players"], {"B": "Player 1", "W": "Player 2"})
                self.assertEqual(verified.receipt["action_count"], 0)
                self.assertTrue(verified.receipt["factory_origin_verified"])
                self.assertTrue(verified.receipt["full_action_replay"])
                if rules in LEGACY_CANDIDATES:
                    self.assertTrue(verified.receipt["mechanics_limit"])
                    self.assertFalse(verified.receipt["independent_mechanics"])

    def test_self_resealed_tampering_still_fails_independent_replay(self):
        record, _verified = self.make(actions=[play(2, 0), play(-2, 0)])
        mutations = (
            lambda p: p.update(extra=True),
            lambda p: p["configuration"].update(rules_revision="wrong"),
            lambda p: p["actions"][0].update(index=True),
            lambda p: p["actions"][0].update(index=0.0),
            lambda p: p["actions"][0]["action"]["point"].__setitem__(0, 2.0),
            lambda p: p["actions"][0]["after"].update(accepted=0),
            lambda p: p["actions"].reverse(),
            lambda p: p["actions"].append(deepcopy(p["actions"][-1])),
            lambda p: p["final"]["stamp"].update(history_hash="0" * 64),
            lambda p: p["final"]["snapshot"].update(version=True),
            lambda p: p["initial"]["stamp"].update(actor={"seat": "S2", "color": "B"}),
        )
        for number, mutation in enumerate(mutations):
            bad = record.to_dict()
            mutation(bad)
            with self.subTest(number=number), self.assertRaises(ValueError):
                origin.verify_origin(reseal(bad))

    def test_wrong_oriented_actions_and_invalid_configuration_types_are_rejected(self):
        for options in ({"n": True}, {"n": 3.0}, {"seed": True}, {"seed": 1.0},
                        {"seats": {"B": "S1", "W": "S1"}},
                        {"seats": {"B": ["S1"], "W": "S2"}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                origin.origin_configuration("junction-y", **options)
        for orientation in (True, 0.0, -1, 2):
            with self.subTest(orientation=orientation), self.assertRaises(ValueError):
                self.make(actions=[play(2, 0), {"action": "construct", "face": [0, 0], "orientation": orientation}])

    def test_source_declarations_cannot_replace_authoritative_runtime_validation(self):
        record, verified = self.make()
        bad = record.to_dict()
        self.assertTrue(first_hash_change(bad["sources"]))
        with self.assertRaises(ValueError):
            origin.verify_origin(reseal(bad))
        original = Path.read_bytes
        origin_path = Path(origin.__file__).resolve()

        def stale(path):
            contents = original(path)
            return contents + b"\n# synthetic stale bytes\n" if path.resolve() == origin_path else contents

        with patch.object(Path, "read_bytes", stale):
            with self.assertRaises(ValueError):
                origin.verify_origin(record)
            with self.assertRaises(ValueError):
                origin.bind_origin_provider(verified)
        bound = origin.bind_origin_provider(verified)
        with patch.object(Path, "read_bytes", stale):
            with self.assertRaises(ValueError):
                bound.metadata(verified.production_root)
            with self.assertRaises(ValueError):
                bound.transition(verified.production_root, {"action": "pass"})


if __name__ == "__main__":
    unittest.main()
