"""Bounded authored Toy origins only, never the full pool or proof search."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.harness.lab_corpus import CorpusIntegrityError, CorpusManifest, compile_corpus
from research.harness.lab_origin import origin_configuration
from research.harness.lab_terminal_cert import canonical_hash


PARENT = "47f5a87d7c8a672e06c8398b9333889fd44a7e75"


def candidate(identifier, actions=None, *, rules="junction-y", template="opening", family="contact"):
    return {"id": identifier, "configuration": origin_configuration(rules),
            "actions": [{"action": "play", "point": [2, 0]}] if actions is None else actions,
            "template_id": template, "family": family}


def reseal(wire):
    wire["manifest_hash"] = canonical_hash({k: v for k, v in wire.items() if k != "manifest_hash"})
    return wire


class TestLabCorpus(unittest.TestCase):
    def compile(self, definitions, **kwargs):
        return compile_corpus(definitions, source_parent=PARENT, **kwargs)

    def test_duplicate_ids_and_malformed_definitions_fail_before_replay(self):
        bad = candidate("bad")
        bad["configuration"]["n"] = True
        values = [[candidate("same"), candidate("same")], [candidate("good"), bad]]
        named = candidate("named")
        named["configuration"]["initial_seats"]["B"] = "A personal name"
        values += [[candidate("good"), named], [candidate(f"many-{i}") for i in range(17)],
                   [candidate(f"overflow-{i}") for i in range(513)]]
        for definitions in values:
            with patch("research.harness.lab_corpus.create_origin", side_effect=AssertionError("must prevalidate")):
                with self.assertRaises(ValueError):
                    self.compile(definitions)

    def test_all_rules_have_explicit_missing_and_uncertified_status(self):
        corpus = self.compile([])
        wire = corpus.to_dict()
        self.assertEqual(len(wire["rulesets"]), 16)
        self.assertEqual(wire["candidates"], [])
        self.assertFalse(wire["admission_record"])
        for row in wire["rulesets"]:
            self.assertEqual(row["certified_counts"], {"development": 0, "holdout": 0})
            self.assertEqual(row["admission_status"], "incomplete")
            self.assertEqual(set(row["sizes"]), {"3", "4"})

    def test_structural_dispositions_do_not_infer_action_values(self):
        opening = [{"action": "play", "point": [2, 0]}]
        ending = opening + [{"action": "pass"}, {"action": "pass"}]
        rows = [candidate("eligible"), candidate("invalid", [{"action": "pass"}]),
                candidate("single", ending + [{"action": "accept"}]),
                candidate("terminal", ending + [{"action": "accept"}, {"action": "accept"}])]
        # One first-ending acceptance still leaves accept/resume: use the once-
        # resumed ending to obtain a genuinely single-action root.
        rows[2]["actions"] = ending + [{"action": "resume"}, {"action": "pass"}, {"action": "pass"}]
        result = self.compile(rows).to_dict()
        statuses = {r["id"]: r["disposition"] for r in result["candidates"]}
        self.assertEqual(statuses, {"eligible": "candidate", "invalid": "invalid-origin",
                                   "single": "single-action", "terminal": "accepted-terminal"})
        for row in result["candidates"]:
            self.assertEqual(row["equivalence"], "unknown")
            self.assertFalse(row["certified"])
            if row["disposition"] != "candidate":
                self.assertIsNone(row["split"])

    def test_history_insensitive_dedup_chooses_lexical_id(self):
        a = candidate("a")
        z = candidate("z", a["actions"] + [{"action": "pass"}, {"action": "pass"}, {"action": "resume"}])
        # The resumption phase differs, so this pair must not collapse. Identical
        # authored origins with distinct template IDs do collapse without outcome.
        b = candidate("b", template="another-intention")
        rows = {r["id"]: r for r in self.compile([z, b, a]).to_dict()["candidates"]}
        self.assertEqual(rows["b"]["disposition"], "duplicate")
        self.assertEqual(rows["b"]["representative_id"], "a")
        self.assertEqual(rows["b"]["spatial_key"], rows["a"]["spatial_key"])
        self.assertNotEqual(rows["z"]["spatial_key"], rows["a"]["spatial_key"])

    def test_split_order_regeneration_and_load_are_deterministic(self):
        definitions = [candidate("center"), candidate("edge", [{"action": "play", "point": [-8, 0]}]),
                       candidate("contact", [{"action": "play", "point": [2, 0]}, {"action": "play", "point": [1, 1]}])]
        first, second = self.compile(definitions), self.compile(list(reversed(definitions)))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(CorpusManifest.from_dict(first.to_dict()).to_dict(), first.to_dict())
        splits = {"development": set(), "holdout": set()}
        for row in first.to_dict()["candidates"]:
            if row["split"]:
                splits[row["split"]].add(row["spatial_key"])
        self.assertTrue(splits["development"])
        self.assertTrue(splits["holdout"])
        self.assertFalse(splits["development"] & splits["holdout"])

    def test_compact_index_has_hash_links_but_no_raw_origins_or_results(self):
        corpus = self.compile([candidate("one")])
        compact = corpus.compact_index()
        self.assertEqual(compact["raw_manifest_hash"], corpus.manifest_hash)
        row = compact["candidates"][0]
        self.assertNotIn("origin", row)
        self.assertNotIn("actions", row)
        self.assertIsInstance(row["origin_hash"], str)
        def walk(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertNotIn(key, {"wdl", "winning", "optimal_action_ids", "score", "outcome"})
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(compact)

    def test_unknown_fields_type_aliases_and_resealed_split_tamper_reject(self):
        original = self.compile([candidate("one")]).to_dict()
        for mutation in (lambda p: p.update(version=True), lambda p: p.update(extra=1),
                         lambda p: p["candidates"][0].update(split="holdout"),
                         lambda p: p["candidates"][0].update(certified=True),
                         lambda p: p["candidates"][0].update(legal_action_count=True)):
            bad = deepcopy(original)
            mutation(bad)
            with self.assertRaises(ValueError):
                CorpusManifest.from_dict(reseal(bad))

    def test_optional_author_binding_reads_only_trusted_local_paths(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "author.json"
            # Authored fixture text is created by the test only; no execution.
            path.write_text("short authored table\n")
            sources = {"test-author": path}
            corpus = self.compile([candidate("one")], trusted_sources=sources)
            self.assertEqual(CorpusManifest.from_dict(corpus.to_dict(), trusted_sources=sources).manifest_hash, corpus.manifest_hash)
            with self.assertRaises(ValueError):
                CorpusManifest.from_dict(corpus.to_dict())
            path.write_text("changed authored table\n")
            with self.assertRaises(ValueError):
                CorpusManifest.from_dict(corpus.to_dict(), trusted_sources=sources)

    def test_only_ordinary_authored_illegality_is_a_nonfatal_candidate(self):
        with patch("research.harness.lab_corpus.create_origin", side_effect=RuntimeError("oracle contradiction")):
            with self.assertRaises(RuntimeError):
                self.compile([candidate("one")])
        with patch("research.harness.lab_corpus.symmetry_key", side_effect=ValueError("bad projection")):
            with self.assertRaises(ValueError):
                self.compile([candidate("one")])

    def test_manifest_and_returned_data_are_detached(self):
        definitions = [candidate("one")]
        saved = deepcopy(definitions)
        corpus = self.compile(definitions)
        self.assertEqual(definitions, saved)
        with self.assertRaises(FrozenInstanceError):
            corpus._json = "{}"
        wire = corpus.to_dict()
        wire["candidates"][0]["definition"]["actions"].clear()
        compact = corpus.compact_index()
        compact["candidates"].clear()
        self.assertEqual(corpus.to_dict()["candidates"][0]["definition"], saved[0])
        self.assertEqual(len(corpus.compact_index()["candidates"]), 1)

    def test_fixed_pool_sizes_parent_and_source_names_are_strict(self):
        definition = candidate("one")
        definition["configuration"]["n"] = 5
        with self.assertRaises(CorpusIntegrityError):
            self.compile([definition])
        for parent in ("HEAD", "a" * 39, True):
            with self.assertRaises(ValueError):
                compile_corpus([], source_parent=parent)
        with self.assertRaises(ValueError):
            self.compile([], trusted_sources={"research/harness/lab_corpus.py": __file__})


if __name__ == "__main__":
    unittest.main()
