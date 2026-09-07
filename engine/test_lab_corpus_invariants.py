"""Independent structural corpus tests, not certification or policy evidence.

Small authored action lists exercise geometry, provenance and inert manifests.
No full candidate table, game search, proof producer or worker is executed here.
"""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "engine"))

from research.harness import lab_corpus as corpus  # noqa: E402
from research.harness import lab_origin as origin  # noqa: E402
from research.harness import lab_symmetry as symmetry  # noqa: E402
from research.harness.lab_research_adapter import (  # noqa: E402
    LEGACY_CANDIDATES, PRODUCTION_RULESETS, production_provider,
)
from research.harness.lab_terminal_cert import canonical_hash, canonical_json  # noqa: E402


PARENT = "47f5a87d7c8a672e06c8398b9333889fd44a7e75"
KAGOME = {"gjerde", "gjerde-go", "line-breath", "gjerde-majority"}
CORNERS = ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))
SPOKES = {
    "junction-y": ((0, 2, 4), (1, 3, 5)),
    "junction-six": ((0, 1, 2, 3, 4, 5),),
    "junction-planted": ((0, 2, 4), (1, 3, 5)),
    "junction-passage": ((0, 3), (1, 4), (2, 5)),
}


def point_map(point, operation):
    """Independent repeated linear map, not production symmetry helpers."""
    x, y = point
    if operation >= 6:
        y = -y
    for _ in range(operation % 6):
        if (x - 3 * y) % 2 or (x + y) % 2:
            raise ValueError("nonintegral honeycomb coordinate")
        x, y = (x - 3 * y) // 2, (x + y) // 2
    return x, y


def map_action(action, operation, rules):
    result = deepcopy(action)
    if "point" in action:
        result["point"] = list(point_map(action["point"], operation))
    if "face" in action:
        q, r = action["face"]
        x, y = point_map((3 * q, 2 * r + q), operation)
        assert x % 3 == 0 and (y - x // 3) % 2 == 0
        result["face"] = [x // 3, (y - x // 3) // 2]
        mapped = {point_map(CORNERS[i], operation)
                  for i in SPOKES[rules][action["orientation"]]}
        result["orientation"] = next(i for i, indices in enumerate(SPOKES[rules])
                                     if {CORNERS[j] for j in indices} == mapped)
    return result


def play(x, y):
    return {"action": "play", "point": [x, y]}


def root(rules="junction-y", actions=(), n=3, seed=0):
    record = origin.create_origin(origin.origin_configuration(rules, n, seed=seed), list(actions))
    return origin.verify_origin(record).production_root


def candidate(identifier, actions=(), *, rules="junction-y", n=3):
    return {"id": identifier, "configuration": origin.origin_configuration(rules, n),
            "actions": list(actions), "template_id": "synthetic-invariant",
            "family": "mechanical-only"}


class TestLabCorpusSymmetryInvariants(unittest.TestCase):
    def test_independent_coordinate_maps_and_dihedral_group_closure(self):
        points = CORNERS + ((0, 0), (3, 1), (-6, 4), (9, -3))
        for operation in range(12):
            for point in points:
                self.assertEqual(symmetry.transform_coordinate(point, operation), point_map(point, operation))
        signatures = {tuple(point_map(point, op) for point in points) for op in range(12)}
        self.assertEqual(len(signatures), 12)
        for first in range(12):
            for second in range(12):
                composed = tuple(symmetry.transform_coordinate(
                    symmetry.transform_coordinate(point, first), second) for point in points)
                self.assertIn(composed, signatures)
        for bad in (True, 1.0, -1, 12, "0", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                symmetry.transform_coordinate((2, 0), bad)
        for bad in ((True, 0), (2.0, 0), (2,), (2, 0, 0), "20"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                symmetry.transform_coordinate(bad, 1)

    def test_all_definitions_sizes_project_detached_geometry_without_replaying_history(self):
        for rules in PRODUCTION_RULESETS:
            for n in range(3, 7):
                with self.subTest(rules=rules, n=n):
                    state = root(rules, [play(3, 1) if rules in KAGOME else play(2, 0)], n=n, seed=17)
                    before = state.to_dict()
                    projected = symmetry.diagram_projection(state)
                    self.assertEqual(projected["rules_id"], rules)
                    self.assertEqual(projected["board_size"], n)
                    self.assertNotIn("history", projected)
                    self.assertNotIn("journal", projected)
                    transformed = symmetry.transform_projection(projected, 7)
                    self.assertEqual(symmetry.symmetry_key(projected), symmetry.symmetry_key(transformed))
                    projected["stones"].clear()
                    self.assertEqual(state.to_dict(), before)
                    self.assertTrue(symmetry.diagram_projection(state)["stones"])

    def test_rotated_reflected_legal_replays_map_actual_oriented_spokes(self):
        for rules, variants in SPOKES.items():
            for orientation in range(len(variants)):
                kind = "plant" if rules == "junction-planted" else "construct"
                actions = [play(2, 0), {"action": kind, "face": [1, 0], "orientation": orientation}]
                if kind == "construct":
                    actions.append(play(3, 1))
                state = root(rules, actions)
                before = state.to_dict()
                projection = symmetry.diagram_projection(state)
                for operation in range(12):
                    with self.subTest(rules=rules, orientation=orientation, operation=operation):
                        moved = root(rules, [map_action(action, operation, rules) for action in actions])
                        expected = symmetry.diagram_projection(moved)
                        self.assertEqual(symmetry.transform_projection(projection, operation), expected)
                self.assertEqual(state.to_dict(), before)

    def test_same_diagram_distinct_forbidden_histories_remain_only_conservative_duplicates(self):
        first = [play(2, 0), play(1, 1), play(-2, 0), play(-1, -1)]
        second = [play(-2, 0), play(-1, -1), play(2, 0), play(1, 1)]
        left, right = root(actions=first), root(actions=second)
        provider = production_provider("junction-y")
        self.assertNotEqual(left.analysis_key(), right.analysis_key())
        self.assertNotEqual(provider.fingerprint(left), provider.fingerprint(right))
        self.assertEqual(symmetry.diagram_projection(left), symmetry.diagram_projection(right))
        self.assertEqual(symmetry.symmetry_key(left), symmetry.symmetry_key(right))

    def test_initial_static_edges_count_but_ignored_seed_labels_do_not(self):
        self.assertEqual(symmetry.symmetry_key(root(seed=1)), symmetry.symmetry_key(root(seed=999)))
        first, second = root("go-static-y", seed=1), root("go-static-y", seed=2)
        self.assertNotEqual(symmetry.diagram_projection(first)["initial_graph"],
                            symmetry.diagram_projection(second)["initial_graph"])
        self.assertNotEqual(symmetry.symmetry_key(first), symmetry.symmetry_key(second))
        dynamic = root(actions=[play(2, 0), {"action": "construct", "face": [1, 0], "orientation": 0}])
        projection = symmetry.diagram_projection(dynamic)
        self.assertNotEqual(projection["current_graph"], projection["initial_graph"])
        wrong_initial = deepcopy(projection)
        wrong_initial["initial_graph"] = deepcopy(projection["current_graph"])
        self.assertNotEqual(symmetry.symmetry_key(projection), symmetry.symmetry_key(wrong_initial))

    def test_extension_coordinates_and_quiet_phase_survive_projection(self):
        actions = [play(*point) for point in ((2, 0), (1, 1), (-8, 0), (1, -1), (-8, -2), (5, -1))]
        actions.append({"action": "extend", "point": [4, 0]})
        state = root("breath-run", actions)
        projection = symmetry.diagram_projection(state)
        self.assertEqual(projection["phase"]["extension_points"], [[4, 0]])
        self.assertTrue(projection["phase"]["extension_used"])
        for operation in range(12):
            moved = root("breath-run", [map_action(action, operation, "breath-run") for action in actions])
            self.assertEqual(symmetry.transform_projection(projection, operation),
                             symmetry.diagram_projection(moved))
        # A diagram helper is not a reachability verifier. This constructed
        # projection tests only that a termination-relevant counter is retained.
        different_quiet_phase = deepcopy(projection)
        different_quiet_phase["phase"]["quiet_moves"] += 1
        self.assertNotEqual(symmetry.symmetry_key(projection), symmetry.symmetry_key(different_quiet_phase))

    def test_actor_pie_acceptances_resumption_and_no_color_interchange(self):
        opening = [play(2, 0)]
        ordinary = root(actions=opening)
        pie = root(actions=opening + [{"action": "swap"}])
        self.assertNotEqual(symmetry.symmetry_key(ordinary), symmetry.symmetry_key(pie))
        ending_actions = opening + [{"action": kind} for kind in ("pass", "pass")]
        first = root(actions=ending_actions)
        second = root(actions=ending_actions + [{"action": "accept"}])
        self.assertNotEqual(first.actor_seat, second.actor_seat)
        self.assertNotEqual(symmetry.symmetry_key(first), symmetry.symmetry_key(second))
        accepted = root(actions=ending_actions + [{"action": "accept"}] * 2)
        self.assertTrue(symmetry.diagram_projection(accepted)["phase"]["accepted"])
        resumed = root(actions=ending_actions + [{"action": "resume"}])
        self.assertTrue(symmetry.diagram_projection(resumed)["phase"]["resumption_used"])
        self.assertNotEqual(symmetry.symmetry_key(ordinary), symmetry.symmetry_key(resumed))
        color_reversed = symmetry.diagram_projection(ordinary)
        for row in color_reversed["stones"]:
            row["column"] = ["W" if color == "B" else "B" for color in row["column"]]
        self.assertNotEqual(symmetry.symmetry_key(ordinary), symmetry.symmetry_key(color_reversed))

    def test_actual_spoke_topology_and_geometry_types_are_validated(self):
        state = root(actions=[play(2, 0), {"action": "construct", "face": [1, 0], "orientation": 0}])
        projection = symmetry.diagram_projection(state)
        bad = deepcopy(projection)
        bad["current_graph"]["topology"][0]["neighbors"].pop()
        with self.assertRaises(ValueError):
            symmetry.symmetry_key(bad)
        bad = deepcopy(projection)
        bad["current_graph"]["scoring_points"].append([3, 1])
        with self.assertRaises(ValueError):
            symmetry.symmetry_key(bad)
        bad = deepcopy(projection)
        bad["current_graph"]["points"][0][0] = float(bad["current_graph"]["points"][0][0])
        with self.assertRaises(ValueError):
            symmetry.symmetry_key(bad)
        for field, value in (("version", True), ("board_size", 3.0), ("rules_revision", "unknown")):
            bad = deepcopy(projection)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                symmetry.symmetry_key(bad)


class TestLabCorpusManifestInvariants(unittest.TestCase):
    def compile(self, definitions):
        before = deepcopy(definitions)
        result = corpus.compile_corpus(definitions, source_parent=PARENT)
        self.assertEqual(definitions, before)
        return result

    def test_all_malformed_definitions_are_rejected_before_any_origin_execution(self):
        good = candidate("valid-prefix", [play(2, 0)])
        bad_values = []
        for field, value in (("id", True), ("template_id", []), ("family", None),
                             ("actions", {}), ("configuration", "file:///tmp/never-read")):
            bad = candidate("bad")
            bad[field] = value
            bad_values.append(bad)
        for field, value in (("n", True), ("n", 3.0), ("n", 5),
                             ("rules_revision", "not-real"), ("rules_id", "__import__('os')"),
                             ("topology_seed", float("nan"))):
            bad = candidate("bad")
            bad["configuration"][field] = value
            bad_values.append(bad)
        for action in ({"action": "construct", "face": [1, 0]},
                       {"action": "construct", "face": [1, 0], "orientation": True},
                       {"action": "play", "point": [2.0, 0]},
                       {"action": "pass", "command": "never-run"}):
            bad_values.append(candidate("bad", [action]))
        for bad in bad_values:
            with self.subTest(bad=repr(bad)), patch.object(corpus, "create_origin") as create:
                with self.assertRaises(ValueError):
                    self.compile([good, bad])
                create.assert_not_called()

    def test_duplicate_ids_and_nonfinite_source_metadata_are_pre_execution_errors(self):
        with patch.object(corpus, "create_origin") as create:
            with self.assertRaises(ValueError):
                self.compile([candidate("duplicate"), candidate("duplicate")])
            for source_parent in (True, 47, "0" * 39, "0" * 41, "g" * 40, float("inf")):
                with self.subTest(source_parent=source_parent), self.assertRaises(ValueError):
                    corpus.compile_corpus([candidate("one")], source_parent=source_parent)
            create.assert_not_called()

    def test_manifest_is_detached_reproducible_and_runtime_tamper_checked(self):
        definitions = [candidate("one", [play(2, 0)]), candidate("two", [play(-2, 0)])]
        first = self.compile(definitions)
        second = self.compile(list(reversed(definitions)))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.manifest_hash, second.manifest_hash)
        payload = first.to_dict()
        loaded = corpus.CorpusManifest.from_dict(payload)
        self.assertEqual(loaded.to_dict(), payload)
        payload["version"] = True
        with self.assertRaises(ValueError):
            corpus.CorpusManifest.from_dict(payload)
        self.assertEqual(type(first.to_dict()["version"]), int)
        payload = first.to_dict()
        payload["unexpected_outcome"] = 1
        with self.assertRaises(ValueError):
            corpus.CorpusManifest.from_dict(payload)
        self.assertNotIn("unexpected_outcome", first.to_dict())
        self.assertNotIn("timing", canonical_json(first.to_dict()))

    def test_lexical_dedup_and_salted_alternating_splits_are_disjoint(self):
        definitions = [candidate("z-duplicate", [play(2, 0)]),
                       candidate("a-representative", [play(-2, 0)]),
                       candidate("rim", [play(-8, 0)]),
                       candidate("contact", [play(2, 0), play(1, 1)]),
                       candidate("history-a", [play(2, 0), play(1, 1), play(-2, 0), play(-1, -1)]),
                       candidate("history-z", [play(-2, 0), play(-1, -1), play(2, 0), play(1, 1)])]
        manifest = self.compile(definitions)
        rows = {row["id"]: row for row in manifest.to_dict()["candidates"]}
        self.assertEqual(rows["z-duplicate"]["disposition"], "duplicate")
        self.assertEqual(rows["z-duplicate"]["representative_id"], "a-representative")
        self.assertIsNone(rows["z-duplicate"]["split"])
        self.assertEqual(rows["history-z"]["representative_id"], "history-a")
        self.assertNotEqual(rows["history-z"]["root_fingerprint"], rows["history-a"]["root_fingerprint"])
        self.assertEqual(rows["history-z"]["spatial_key"], rows["history-a"]["spatial_key"])
        eligible = [row for row in rows.values() if row["disposition"] == "candidate"]
        ordered = sorted(eligible, key=lambda row: (canonical_hash({
            "salt": "varde-rules-lab-corpus-split-0.1", "rules": "junction-y", "n": 3,
            "spatial_key": row["spatial_key"]}), row["spatial_key"]))
        self.assertEqual([row["split"] for row in ordered],
                         ["development" if index % 2 == 0 else "holdout" for index in range(len(ordered))])
        development = {row["spatial_key"] for row in rows.values() if row["split"] == "development"}
        holdout = {row["spatial_key"] for row in rows.values() if row["split"] == "holdout"}
        self.assertTrue(development)
        self.assertTrue(holdout)
        self.assertFalse(development & holdout)
        self.assertEqual(manifest.to_dict(), self.compile(list(reversed(definitions))).to_dict())

    def test_structural_rejections_are_preserved_without_action_value_inference(self):
        endings = [play(2, 0)] + [{"action": kind} for kind in ("pass", "pass")]
        definitions = [candidate("terminal", endings + [{"action": "accept"}] * 2),
                       candidate("single", endings + [{"action": kind} for kind in ("resume", "pass", "pass")]),
                       candidate("invalid", [play(9998, 0)]),
                       candidate("legal", [play(2, 0)])]
        value = self.compile(definitions).to_dict()
        rows = {row["id"]: row for row in value["candidates"]}
        expected = {"terminal": "accepted-terminal", "single": "single-action",
                    "invalid": "invalid-origin", "legal": "candidate"}
        self.assertEqual({key: row["disposition"] for key, row in rows.items()}, expected)
        self.assertEqual(rows["terminal"]["legal_action_count"], 0)
        self.assertEqual(rows["single"]["legal_action_count"], 1)
        self.assertIsNone(rows["invalid"]["origin_hash"])
        self.assertIsNone(rows["invalid"]["root_fingerprint"])
        for identifier, row in rows.items():
            self.assertEqual(row["equivalence"], "unknown")
            self.assertIs(row["certified"], False)
            if identifier != "legal":
                self.assertIsNone(row["split"])
                self.assertTrue(row["reason"])
        forbidden = {"wdl", "outcome", "winning", "score", "root_value", "optimal_action_ids", "action_values"}
        def check_keys(item):
            if isinstance(item, dict):
                self.assertFalse(forbidden & set(item))
                for child in item.values():
                    check_keys(child)
            elif isinstance(item, list):
                for child in item:
                    check_keys(child)
        check_keys(value)

    def test_missing_rules_and_legacy_independence_remain_explicitly_unqualified(self):
        manifest = self.compile([candidate("one", [play(2, 0)])])
        value = manifest.to_dict()
        self.assertEqual([row["rules_id"] for row in value["rulesets"]], list(PRODUCTION_RULESETS))
        for row in value["rulesets"]:
            self.assertEqual(set(row["sizes"]), {"3", "4"})
            self.assertEqual(row["certified_counts"], {"development": 0, "holdout": 0})
            self.assertEqual(row["required_certified_per_split"], 8)
            self.assertEqual(row["admission_status"], "incomplete")
            self.assertEqual(row["sizes"]["4"]["proposed"], 0)
            independent = row["rules_id"] not in LEGACY_CANDIDATES
            self.assertIs(row["independent_mechanics"], independent)
            self.assertIs(row["dual_mechanical_origin_available"], independent)
            if not independent:
                self.assertEqual(row["independence_status"], "unqualified-shared-mechanics")
                self.assertTrue(row["mechanics_limit"])
        index = manifest.compact_index()
        self.assertEqual(index["raw_manifest_hash"], manifest.manifest_hash)
        self.assertEqual(index["rulesets"], value["rulesets"])
        self.assertIs(index["admission_record"], False)
        index["rulesets"].clear()
        self.assertEqual(len(manifest.compact_index()["rulesets"]), 16)

    def test_self_resealed_split_source_and_qualification_tamper_is_rejected(self):
        manifest = self.compile([candidate("one", [play(2, 0)])])
        original = manifest.to_dict()
        changed = deepcopy(original)
        changed["candidates"][0]["split"] = "holdout"
        rule = next(row for row in changed["rulesets"] if row["rules_id"] == "junction-y")
        rule["sizes"]["3"]["structural_counts"] = {"development": 0, "holdout": 1}
        mutations = [changed]
        for key, value in (("equivalence", "all-actions-equivalent"), ("certified", True),
                           ("legal_action_count", True), ("origin_hash", "0" * 64)):
            changed = deepcopy(original)
            changed["candidates"][0][key] = value
            mutations.append(changed)
        changed = deepcopy(original)
        changed["sources"]["hashes"]["research/harness/lab_corpus.py"] = "0" * 64
        changed["sources"]["source_hash"] = canonical_hash({
            key: item for key, item in changed["sources"].items() if key != "source_hash"})
        mutations.append(changed)
        for changed in mutations:
            changed["manifest_hash"] = canonical_hash({key: item for key, item in changed.items() if key != "manifest_hash"})
            with self.subTest(changed=changed["candidates"][0]), self.assertRaises(ValueError):
                corpus.CorpusManifest.from_dict(changed)

    def test_manifest_labels_are_inert_and_oracle_integrity_failure_is_not_invalid_origin(self):
        literal = "__import__('os').system('not-an-executed-command')"
        definition = candidate(literal, [play(2, 0)])
        definition["template_id"] = "/tmp/not-a-module-or-template-file"
        definition["family"] = "$(not-a-command)"
        with patch("os.system", side_effect=AssertionError("command executed")), \
                patch("subprocess.Popen", side_effect=AssertionError("process launched")):
            row = self.compile([definition]).to_dict()["candidates"][0]
        self.assertEqual(row["id"], literal)
        self.assertEqual(row["definition"], definition)
        with patch.object(corpus, "verify_origin", side_effect=origin.OriginIntegrityError("Synthetic oracle mismatch")):
            with self.assertRaisesRegex(ValueError, "oracle mismatch"):
                self.compile([candidate("valid", [play(2, 0)])])


if __name__ == "__main__":
    unittest.main()
