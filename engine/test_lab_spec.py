"""Specification tests only: no laboratory game behavior is implemented here."""

from dataclasses import FrozenInstanceError, replace
import importlib
import json
import math
import unittest

import lab_spec
from lab_spec import (
    ALLOWED_SIZES, BASE_ACTIONS, CONSTRUCT_ACTIONS, EXPERIMENT_REGISTRY,
    EXPERIMENT_SPECS, HEX_CORNER_OFFSETS, LAB_CATALOG_VERSION, LAB_REGISTRY,
    LAB_SPECS, PASSAGE_ORIENTATIONS, PLANTED_ACTIONS, SIX_ORIENTATIONS,
    STATIC_CONTROL_REGISTRY, STATIC_CONTROL_SPECS, STATIC_Y_SEED_RECIPE,
    Y_ORIENTATIONS, get_experiment_spec, get_lab_spec, lab_specs_public,
)
import varde


LAB_IDS = (
    "line-breath", "gjerde-majority", "breath-connection", "junction-y",
    "junction-six", "junction-planted", "junction-passage",
)
CONTROL_IDS = ("go-honeycomb", "go-static-six", "go-static-y")


class TestLabSpecifications(unittest.TestCase):
    def test_frozen_ids_revisions_order_sizes_and_evidence(self):
        self.assertEqual(LAB_CATALOG_VERSION, 1)
        self.assertEqual(tuple(LAB_REGISTRY), LAB_IDS)
        self.assertEqual(tuple(STATIC_CONTROL_REGISTRY), CONTROL_IDS)
        self.assertEqual(tuple(EXPERIMENT_REGISTRY), LAB_IDS + CONTROL_IDS)
        self.assertEqual(len({spec.evaluation_id for spec in EXPERIMENT_SPECS}), 10)
        for spec in EXPERIMENT_SPECS:
            with self.subTest(rules=spec.id):
                self.assertEqual(spec.revision, "0.1")
                self.assertEqual(spec.evaluation_id, f"{spec.id}-0.1")
                self.assertEqual(spec.allowed_sizes, (3, 4, 5, 6))
                self.assertEqual(spec.admission_status, "unmeasured")
                self.assertFalse(spec.public_new_game)
                self.assertTrue(spec.description)
                self.assertTrue(spec.hypothesis)
                self.assertEqual(len(spec.rule_concepts), len(set(spec.rule_concepts)))

    def test_scoring_variants_match_the_frozen_rules(self):
        expected = {
            "line-breath": ("kagome-lines", "line-area", None, 0),
            "gjerde-majority": ("kagome-lines", "cell-majority", 4, 0),
            "breath-connection": ("honeycomb-vertices", "area-minus-groups", None, 1),
        }
        for rules, values in expected.items():
            spec = get_lab_spec(rules)
            self.assertEqual(
                (spec.geometry, spec.scoring, spec.majority_threshold, spec.group_penalty),
                values,
            )
            self.assertEqual(spec.resolution, "breath-first")
            self.assertEqual(spec.construction, "none")
            self.assertEqual(spec.supported_actions, BASE_ACTIONS)
            self.assertEqual(spec.orientation_sets, ())
        self.assertIn("at least four", get_lab_spec("gjerde-majority").description)

    def test_junction_mechanics_and_static_controls_are_separate(self):
        expected = {
            "junction-y": ("empty-y", Y_ORIENTATIONS, CONSTRUCT_ACTIONS),
            "junction-six": ("empty-six", SIX_ORIENTATIONS, CONSTRUCT_ACTIONS),
            "junction-planted": ("planted-y", Y_ORIENTATIONS, PLANTED_ACTIONS),
            "junction-passage": ("empty-passage", PASSAGE_ORIENTATIONS, CONSTRUCT_ACTIONS),
        }
        for rules, values in expected.items():
            spec = get_lab_spec(rules)
            self.assertEqual((spec.construction, spec.orientation_sets, spec.supported_actions), values)
            self.assertEqual(spec.resolution, "capture-first")
            self.assertEqual(spec.scoring, "original-vertex-area")
            self.assertEqual(spec.experimental_availability, "experimental-lab")
            self.assertNotIn("extend", spec.supported_actions)
        for spec in STATIC_CONTROL_SPECS:
            self.assertEqual(spec.supported_actions, BASE_ACTIONS)
            self.assertEqual(spec.experimental_availability, "research-only")
            self.assertEqual(spec.resolution, "capture-first")
            self.assertEqual(spec.scoring, "original-vertex-area")
        self.assertEqual(get_experiment_spec("go-static-six").construction, "prebuilt-six")
        self.assertEqual(get_experiment_spec("go-static-y").construction, "prebuilt-y")
        self.assertEqual(get_experiment_spec("go-static-y").topology_seed_recipe, STATIC_Y_SEED_RECIPE)
        self.assertEqual(get_experiment_spec("go-honeycomb").construction, "none")

    def test_corner_indexing_and_exact_orientation_constants(self):
        self.assertEqual(HEX_CORNER_OFFSETS, tuple(varde.CORNERS))
        self.assertEqual(Y_ORIENTATIONS, ((0, 2, 4), (1, 3, 5)))
        self.assertEqual(PASSAGE_ORIENTATIONS, ((0, 3), (1, 4), (2, 5)))
        self.assertEqual(SIX_ORIENTATIONS, ((0, 1, 2, 3, 4, 5),))
        for choices in (Y_ORIENTATIONS, PASSAGE_ORIENTATIONS, SIX_ORIENTATIONS):
            for orientation in choices:
                self.assertEqual(len(set(orientation)), len(orientation))
            with self.assertRaises(TypeError):
                choices[0][0] = 7
        for turn in range(6):
            for direction in (-1, 1):
                for choices in (Y_ORIENTATIONS, PASSAGE_ORIENTATIONS, SIX_ORIENTATIONS):
                    transformed = {
                        tuple(sorted((direction * i + turn) % 6 for i in orientation))
                        for orientation in choices
                    }
                    self.assertEqual(transformed, set(choices))

    def test_catalog_and_nested_fields_are_immutable(self):
        for registry in (LAB_REGISTRY, STATIC_CONTROL_REGISTRY, EXPERIMENT_REGISTRY):
            with self.assertRaises(TypeError):
                registry["new"] = LAB_SPECS[0]
        with self.assertRaises(FrozenInstanceError):
            LAB_SPECS[0].revision = "0.2"
        with self.assertRaises(TypeError):
            LAB_SPECS[0].supported_actions[0] = "extend"
        with self.assertRaises(TypeError):
            replace(LAB_SPECS[0], rule_concepts=["mutable"])
        with self.assertRaises(TypeError):
            replace(get_lab_spec("junction-y"), orientation_sets=([0, 2, 4],))

    def test_invalid_ids_and_metadata_fail_explicitly(self):
        for invalid in ("unknown", "classic", "junction-Y", "", None, [], 3):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    get_lab_spec(invalid)
                with self.assertRaises(ValueError):
                    get_experiment_spec(invalid)
        for rules in CONTROL_IDS:
            with self.assertRaises(ValueError):
                get_lab_spec(rules)
        for changes in (
            {"revision": "0.2"}, {"admission_status": "passed"},
            {"allowed_sizes": (3, 4, 5, 6, 7)}, {"allowed_sizes": list(ALLOWED_SIZES)},
            {"majority_threshold": 5}, {"majority_threshold": 4.0},
            {"group_penalty": float("nan")},
            {"orientation_sets": ((0, 0, 2),)}, {"orientation_sets": ((0, 2, 6),)},
            {"orientation_sets": ((False, 2, 4),)},
            {"experimental_availability": "ordinary-public"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    replace(LAB_SPECS[0], **changes)

    def test_public_metadata_is_detached_finite_json(self):
        payload = lab_specs_public()
        self.assertEqual(payload["version"], LAB_CATALOG_VERSION)
        self.assertEqual(tuple(item["id"] for item in payload["rulesets"]), LAB_IDS)
        all_metadata = [spec.public_dict() for spec in EXPERIMENT_SPECS]
        json.dumps(all_metadata, allow_nan=False)

        def check(value):
            if isinstance(value, dict):
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
            elif isinstance(value, (int, float)):
                self.assertTrue(math.isfinite(value))

        check(all_metadata)
        payload["rulesets"][0]["allowed_sizes"].append(9)
        payload["rulesets"][3]["orientation_sets"][0][0] = 5
        self.assertEqual(LAB_SPECS[0].allowed_sizes, ALLOWED_SIZES)
        self.assertEqual(get_lab_spec("junction-y").orientation_sets, Y_ORIENTATIONS)

    def test_import_and_metadata_do_not_change_legacy_registry_or_games(self):
        registry_before = varde.rulesets_public()
        ids_before = varde.RULESETS
        game_before = varde.Game(3, rules="breath").to_dict()
        importlib.reload(lab_spec)
        lab_spec.lab_specs_public()
        self.assertEqual(varde.rulesets_public(), registry_before)
        self.assertEqual(varde.RULESETS, ids_before)
        self.assertEqual(varde.Game(3, rules="breath").to_dict(), game_before)
        self.assertFalse(set(EXPERIMENT_REGISTRY) & set(varde.RULESET_REGISTRY))
        for rules in LAB_IDS + CONTROL_IDS:
            with self.assertRaises(ValueError):
                varde.Game(3, rules=rules)


if __name__ == "__main__":
    unittest.main()
