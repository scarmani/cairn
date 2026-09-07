import unittest

from lab_evidence import (
    DIMENSIONS, empty_card, entry, evidence_hash, frozen_program, validate_card,
)


class TestLaboratoryEvidence(unittest.TestCase):
    def test_missing_is_null_not_zero(self):
        card = validate_card(empty_card("junction-y", "0.1"))
        self.assertEqual(set(card["dimensions"]), set(DIMENSIONS))
        self.assertIsNone(card["dimensions"]["strategic_depth"]["value"])
        with self.assertRaises(ValueError):
            entry(value=0)
        with self.assertRaises(ValueError):
            entry(sample_size=1)

    def test_provenance_finiteness_and_uncertainty(self):
        with self.assertRaises(ValueError):
            entry("verified", value=True)
        with self.assertRaises(ValueError):
            entry("observed", value=float("nan"), provenance=["test"])
        with self.assertRaises(ValueError):
            entry(uncertainty="")
        value = entry("provisional", value="connection motif", provenance=["fixture.json#abc"],
                      uncertainty="Computer-derived hypothesis; no human observations", scope="local")
        self.assertEqual(value["status"], "provisional")

    def test_no_accidental_headline(self):
        card = empty_card("line-breath", "0.1")
        card["comparative_games"] = 1000
        card["comparative_headline_allowed"] = True
        with self.assertRaises(ValueError):
            validate_card(card)

    def test_qualification_requires_two_policies_and_corpora(self):
        card = empty_card("breath-connection", "0.1")
        a = card["mcts_admission"]
        a.update(status="admitted", recipe="lab-uct-0.1", agent_hash="a" * 64,
                 manifest_hash="b" * 64, result_hash="c" * 64,
                 development_positions=8, holdout_positions=8)
        with self.assertRaises(ValueError):
            validate_card(card)
        a["policies"] = {"uniform": "passed", "light": "passed"}
        self.assertEqual(validate_card(card)["mcts_admission"]["status"], "admitted")
        a["holdout_positions"] = 7
        with self.assertRaises(ValueError):
            validate_card(card)

    def test_real_human_observation_and_valid_qualified_comparison(self):
        card = empty_card("junction-y", "0.1")
        card["human_observations"]["beauty"] = entry(
            "observed", value=5, sample_size=12, provenance=["human-study.json#participants"],
            source_kind="human-observation", uncertainty="Small voluntary sample",
        )
        self.assertEqual(validate_card(card)["human_observations"]["beauty"]["value"], 5)
        a = card["mcts_admission"]
        a.update(status="admitted", recipe="lab-uct-0.1", agent_hash="a" * 64,
                 manifest_hash="b" * 64, result_hash="c" * 64,
                 development_positions=8, holdout_positions=8,
                 policies={"uniform": "passed", "light": "passed"})
        card["comparative_games"] = 100
        card["comparative_headline_allowed"] = True
        card["shortlist"]["qualified"] = True
        self.assertTrue(validate_card(card)["shortlist"]["qualified"])

    def test_no_mutation_and_recipe_hash_frozen(self):
        card = empty_card("junction-six", "0.1")
        copy = validate_card(card)
        copy["dimensions"]["correctness"]["value"] = "different"
        self.assertIsNone(card["dimensions"]["correctness"]["value"])
        recipe = frozen_program()
        first = evidence_hash(recipe)
        self.assertEqual(first, evidence_hash(frozen_program()))
        recipe["replicates"] = 3
        self.assertNotEqual(first, evidence_hash(recipe))

    def test_human_rating_cannot_be_filled_by_machine_records(self):
        card = empty_card("junction-y", "0.1")
        card["human_observations"]["beauty"] = entry(
            "observed", value=7, provenance=["machine-rollouts.json"],
            uncertainty="No human observations",
        )
        with self.assertRaises(ValueError):
            validate_card(card)

    def test_shortlist_needs_admitted_comparative_evidence(self):
        card = empty_card("junction-y", "0.1")
        card["shortlist"]["qualified"] = True
        with self.assertRaises(ValueError):
            validate_card(card)

    def test_malformed_gate_metadata_cannot_authorize_claims(self):
        for bad_field, bad_value in (("agent_hash", 1), ("manifest_hash", "x"),
                                     ("development_positions", 8.5),
                                     ("holdout_positions", True)):
            card = empty_card("junction-y", "0.1")
            a = card["mcts_admission"]
            a.update(status="admitted", recipe="lab-uct-0.1", agent_hash="a" * 64,
                     manifest_hash="b" * 64, result_hash="c" * 64,
                     development_positions=8, holdout_positions=8,
                     policies={"uniform": "passed", "light": "passed"})
            card["comparative_games"] = 100
            card["comparative_headline_allowed"] = True
            a[bad_field] = bad_value
            with self.subTest(field=bad_field), self.assertRaises(ValueError):
                validate_card(card)
        card = empty_card("junction-y", "0.1")
        card["comparative_headline_allowed"] = 0
        with self.assertRaises(ValueError):
            validate_card(card)


if __name__ == "__main__":
    unittest.main()
