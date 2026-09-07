"""Short authored mechanics only; no terminal proofs, corpus, or policy games."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest.mock import patch

from research.harness.lab_origin import (
    LEGACY_CANDIDATES, PRODUCTION_RULESETS, OriginIntegrityError, OriginRecord,
    bind_origin_provider, create_origin, origin_configuration, runtime_sources,
    verify_origin,
)
from research.harness.lab_terminal_cert import canonical_hash, canonical_json


def play(point):
    return {"action": "play", "point": list(point)}


def admin(kind):
    return {"action": kind}


def opening(rules):
    return play((3, 1) if rules in ("gjerde", "gjerde-go", "line-breath", "gjerde-majority") else (2, 0))


def reseal(value):
    value["record_hash"] = canonical_hash({key: item for key, item in value.items() if key != "record_hash"})
    return value


class TestLabOrigin(unittest.TestCase):
    def record(self, rules="junction-y", actions=None, **kwargs):
        return create_origin(origin_configuration(rules, **kwargs), [opening(rules)] if actions is None else actions)

    def test_all_sixteen_rules_and_four_sizes_replay_from_neutral_factory(self):
        self.assertEqual(len(PRODUCTION_RULESETS), 16)
        covered = set()
        for rules in PRODUCTION_RULESETS:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=rules, n=n):
                    actions = [opening(rules), admin("swap"), admin("pass"), admin("pass"), admin("accept")]
                    record = self.record(rules, actions, n=n, seed=73)
                    result = verify_origin(record)
                    receipt, wire = result.receipt, record.to_dict()
                    self.assertTrue(receipt["full_action_replay"])
                    self.assertTrue(receipt["factory_origin_verified"])
                    self.assertFalse(receipt["admission_record"])
                    self.assertFalse(result.production_root.accepted)
                    self.assertEqual(wire["initial"]["snapshot"]["players"], {"B": "Player 1", "W": "Player 2"})
                    self.assertEqual(wire["actions"][1]["after"]["seats"], {"B": "S2", "W": "S1"})
                    self.assertEqual(receipt["independent_mechanics"], rules not in LEGACY_CANDIDATES)
                    if rules in LEGACY_CANDIDATES:
                        self.assertIsNone(result.independent_root)
                        self.assertIn("shared production", receipt["mechanics_limit"])
                    else:
                        self.assertIsNone(receipt["mechanics_limit"])
                        self.assertEqual(result.production_root.to_dict(), result.independent_root.to_dict())
                    covered.add((rules, n))
        self.assertEqual(len(covered), 64)

    def test_all_distinct_orientations_and_permanent_topology_are_recorded(self):
        for rules, kind, orientations in (("junction-y", "construct", range(2)),
                                           ("junction-six", "construct", range(1)),
                                           ("junction-planted", "plant", range(2)),
                                           ("junction-passage", "construct", range(3))):
            ids = set()
            for orientation in orientations:
                with self.subTest(rules=rules, orientation=orientation):
                    actions = [opening(rules), {"action": kind, "face": [0, 0], "orientation": orientation}]
                    result = verify_origin(self.record(rules, actions))
                    wire = result.record.to_dict()
                    ids.add(wire["actions"][1]["id"])
                    self.assertEqual(result.production_root.game.topology, ((0, 0, orientation),))
                    self.assertEqual(result.production_root.to_dict(), result.independent_root.to_dict())
            self.assertEqual(len(ids), len(orientations))
        actions = [play((2, 0)), {"action": "construct", "face": [0, 0], "orientation": 0},
                   play((-1, 1)), play((0, 0)), play((-1, -1))]
        result = verify_origin(self.record("junction-y", actions))
        self.assertEqual(result.production_root.game.state[(0, 0)], ())
        self.assertEqual(result.production_root.game.topology, ((0, 0, 0),))
        self.assertEqual(result.production_root.to_dict(), result.independent_root.to_dict())

    def test_seed_normalization_is_explicit_and_no_factory_behavior_changes(self):
        for rules in PRODUCTION_RULESETS:
            record = self.record(rules, seed=-73)
            normalization = record.to_dict()["normalization"]
            self.assertEqual(normalization["requested_seed"], -73)
            prebuilt = rules in ("go-static-six", "go-static-y")
            self.assertEqual(normalization["effective_seed"], -73 if prebuilt else 0)
            self.assertEqual(normalization["seed_semantics"], "prebuilt-topology-retains-seed" if prebuilt else "factory-ignores-seed")
            verify_origin(record)

    def test_both_acceptances_and_resumption_are_explicit_not_reconstructed(self):
        prefix = [opening("breath-connection"), admin("pass"), admin("pass")]
        result = verify_origin(self.record("breath-connection", prefix + [admin("accept"), admin("accept")]))
        self.assertTrue(result.production_root.accepted)
        rows = result.record.to_dict()["actions"]
        self.assertNotEqual(rows[-2]["before"]["actor"]["seat"], rows[-1]["before"]["actor"]["seat"])
        for first in ([], [admin("accept")]):
            chain = prefix + first + [admin("resume"), admin("pass"), admin("pass"), admin("accept")]
            verified = verify_origin(self.record("breath-connection", chain))
            self.assertTrue(verified.production_root.accepted)
            self.assertTrue(verified.production_root.game.resumption_used)
        with self.assertRaises(ValueError):
            self.record("breath-connection", prefix + [admin("resume"), admin("pass"), admin("pass"), admin("resume")])
        bad = result.record.to_dict()
        bad["actions"].pop(-2)
        bad["actions"][-1]["index"] -= 1
        with self.assertRaises(ValueError):
            verify_origin(reseal(bad))

    def test_actor_preserving_extension_closure_and_automatic_closure(self):
        prefix = [play((2, 0)), play((1, 1)), play((-8, 0)), play((1, -1))]
        auto = verify_origin(self.record("breath-run", prefix + [{"action": "extend", "point": [4, 0]}]))
        row = auto.record.to_dict()["actions"][-1]
        self.assertNotEqual(row["before"]["actor"], row["after"]["actor"])
        chain = prefix + [play((-8, -2)), play((5, -1)),
                          {"action": "extend", "point": [4, 0]}, admin("finish-extension")]
        result = verify_origin(self.record("breath-run", chain))
        rows = result.record.to_dict()["actions"]
        self.assertEqual(rows[-2]["before"]["actor"], rows[-2]["after"]["actor"])
        self.assertNotEqual(rows[-1]["before"]["actor"], rows[-1]["after"]["actor"])
        bad = result.record.to_dict()
        bad["actions"].pop()
        with self.assertRaises(ValueError):
            verify_origin(reseal(bad))

    def test_configuration_and_action_aliases_fail_strictly(self):
        for name, value in (("n", True), ("n", 3.0), ("topology_seed", False),
                            ("rules_revision", 0.1), ("initial_seats", {"B": "S1", "W": "S1"})):
            config = origin_configuration("junction-y")
            config[name] = value
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                create_origin(config, [])
        for wire in ({"action": "play", "point": [True, 0]},
                     {"action": "construct", "face": [0, 0], "orientation": False},
                     {"action": "play", "point": [2, 0], "extra": 1}):
            with self.assertRaises(ValueError):
                self.record(actions=[wire])
        for invalid in ("unknown", "breath-cap", None, []):
            with self.assertRaises(ValueError):
                origin_configuration(invalid)

    def test_hash_resealed_snapshot_history_actor_and_source_tampering_fail(self):
        original = self.record().to_dict()
        for mutate in (
            lambda p: p["configuration"].update(n=4),
            lambda p: p["initial"]["snapshot"].update(moves_played=True),
            lambda p: p["final"]["snapshot"]["history"].pop(),
            lambda p: p["actions"][0].update(index=False),
            lambda p: p["actions"][0]["after"]["actor"].update(seat="S1"),
            lambda p: p["providers"]["production"].update(implementation_hash="0" * 64),
            lambda p: p["sources"]["hashes"].update({"engine/actions.py": "0" * 64}),
            lambda p: p.update(unapproved=True),
        ):
            bad = deepcopy(original)
            mutate(bad)
            bad["sources"]["bundle_hash"] = canonical_hash(bad["sources"]["hashes"])
            for key in ("initial", "final"):
                bad[key]["stamp"]["snapshot_hash"] = canonical_hash(bad[key]["snapshot"])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                verify_origin(reseal(bad))

    def test_fresh_empty_origin_is_valid_but_imported_snapshot_is_not_configuration(self):
        result = verify_origin(self.record(actions=[]))
        self.assertEqual(result.receipt["action_count"], 0)
        self.assertTrue(result.receipt["full_action_replay"])
        with self.assertRaises(ValueError):
            create_origin(result.production_root.to_dict(), [])

    def test_records_actions_roots_and_receipts_are_detached(self):
        config, actions = origin_configuration("junction-y"), [opening("junction-y")]
        saved_config, saved_actions = deepcopy(config), deepcopy(actions)
        record = create_origin(config, actions)
        result = verify_origin(record)
        self.assertEqual(config, saved_config)
        self.assertEqual(actions, saved_actions)
        with self.assertRaises(FrozenInstanceError):
            record._json = "{}"
        root = result.production_root
        root.game.state[(2, 0)] = ()
        receipt = result.receipt
        receipt["full_action_replay"] = False
        wire = record.to_dict()
        wire["configuration"]["initial_seats"]["B"] = "changed"
        self.assertTrue(result.receipt["full_action_replay"])
        self.assertEqual(result.production_root.game.state[(2, 0)], ("B",))
        self.assertEqual(record.to_dict()["configuration"], saved_config)

    def test_binding_exact_root_and_provider_defaults_remain_separate(self):
        result = verify_origin(self.record())
        root = result.production_root
        before = canonical_json(root.to_dict())
        for independent in (False, True):
            state = result.independent_root if independent else root
            bound = bind_origin_provider(result, state, independent=independent)
            self.assertTrue(bound.metadata(state)["provenance"]["full_action_replay"])
            child = bound.transition(state, admin("pass"))
            self.assertFalse(bound.metadata(child)["provenance"]["full_action_replay"])
            with self.assertRaises(ValueError):
                bind_origin_provider(result, child, independent=independent)
        self.assertEqual(canonical_json(root.to_dict()), before)
        from research.harness.lab_research_adapter import production_provider
        self.assertFalse(production_provider("junction-y").metadata(root)["provenance"]["full_action_replay"])
        bad_receipt = result.receipt
        bad_receipt["action_count"] = 999
        forged = replace(result, _receipt_json=canonical_json(bad_receipt))
        with self.assertRaises(ValueError):
            bind_origin_provider(forged)
        root.game.history.clear()
        with self.assertRaises(ValueError):
            bind_origin_provider(replace(result, _production=root))
        with self.assertRaises(ValueError):
            bind_origin_provider(result.receipt)
        with self.assertRaises(ValueError):
            bind_origin_provider(verify_origin(self.record("classic")), independent=True)

    def test_changed_runtime_bytes_fail_create_verify_and_existing_bound_provider(self):
        result = verify_origin(self.record())
        bound, root = bind_origin_provider(result), result.production_root
        changed = runtime_sources()
        changed["hashes"]["engine/actions.py"] = "0" * 64
        changed["bundle_hash"] = canonical_hash(changed["hashes"])
        with patch("research.harness.lab_origin._actual_sources", return_value=changed):
            for callback in (lambda: self.record(), lambda: verify_origin(result.record),
                             lambda: bind_origin_provider(result), lambda: bound.metadata(root),
                             lambda: bound.transition(root, admin("pass"))):
                with self.assertRaises(OriginIntegrityError):
                    callback()

    def test_canonical_storage_rejects_duplicate_json_and_detached_sources(self):
        record = self.record()
        wire = record.to_dict()
        self.assertEqual(OriginRecord.from_dict(wire).record_hash, record.record_hash)
        with self.assertRaises(ValueError):
            OriginRecord(record._json[:-1] + ',"version":1}')
        with self.assertRaises(ValueError):
            OriginRecord(json.dumps(wire, indent=2))
        sources = runtime_sources()
        sources["hashes"].clear()
        self.assertTrue(runtime_sources()["hashes"])


if __name__ == "__main__":
    unittest.main()
