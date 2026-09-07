"""Synthetic manifests and short authored origin fixtures; no proof/search run."""

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.harness import lab_proof_jobs as jobs
from research.harness.lab_corpus import CorpusManifest, compile_corpus
from research.harness.lab_corpus_candidates import trusted_sources
from research.harness.lab_fixed_tasks import FixedTaskManifest
from research.harness.lab_origin import origin_configuration
from research.harness.lab_terminal_cert import canonical_hash, canonical_json


def indexed(identifier, *, rules="classic", n=3, split="development", disposition="candidate"):
    return {"id": identifier, "rules_id": rules, "n": n, "split": split, "disposition": disposition}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def reseal_task(task):
    task["payload"]["row_hash"] = canonical_hash(task["payload"]["row"]) if task["payload"]["row"] is not None else None
    task["payload_hash"] = canonical_hash(task["payload"])
    return task


class TestLabProofJobSelectors(unittest.TestCase):
    def test_bootstrap_exact_32_slots_fixed_size_rule_order_and_missing(self):
        rows = [indexed("z"), indexed("a"), indexed("not-selected", split="holdout"),
                indexed("n4", rules="junction-y", n=4),
                indexed("excluded", split=None, disposition="single-action")]
        before = deepcopy(rows)
        result = jobs.select_bootstrap_rows(rows)
        self.assertEqual(len(result), 32)
        self.assertEqual(result[0], {"slot": 0, "rules_id": "classic", "n": 3, "candidate_id": "a"})
        self.assertEqual([(r["n"], r["rules_id"]) for r in result],
                         [(n, rules) for n in (3, 4) for rules in jobs.PRODUCTION_RULESETS])
        self.assertEqual(sum(r["candidate_id"] is not None for r in result), 2)
        self.assertEqual(result, jobs.select_bootstrap_rows(list(reversed(rows))))
        result[0]["candidate_id"] = "detached"
        self.assertEqual(rows, before)
        self.assertEqual(jobs.select_bootstrap_rows(rows)[0]["candidate_id"], "a")

    def test_full_order_round_robins_rules_collectively_across_sizes_splits(self):
        rows = [indexed("classic4", n=4), indexed("classic3h", split="holdout"), indexed("classic3d"),
                indexed("rosette3", rules="rosette"), indexed("rosette4", rules="rosette", n=4),
                indexed("breath3", rules="breath")]
        self.assertEqual(jobs.select_certification_rows(rows),
                         ("classic3d", "rosette3", "breath3", "classic3h", "rosette4", "classic4"))
        self.assertEqual(jobs.select_certification_rows(rows), jobs.select_certification_rows(rows[::-1]))
        self.assertEqual(jobs.select_certification_rows([]), ())

    def test_full_order_interleaves_unequal_four_subcells_before_later_ordinals(self):
        rows = []
        cells = ((3, "development"), (3, "holdout"), (4, "development"), (4, "holdout"))
        for rules in ("classic", "rosette"):
            for cell, ((n, split), count) in enumerate(zip(cells, (3, 1, 2, 1))):
                for ordinal in range(count):
                    rows.append(indexed(f"{rules}-cell{cell}-id{ordinal}", rules=rules, n=n, split=split))
        before = deepcopy(rows)
        result = jobs.select_certification_rows(rows[::-1])
        self.assertEqual(len(result), len(rows))
        self.assertEqual(set(result), {row["id"] for row in rows})
        self.assertEqual(result[:8], tuple(f"{rules}-cell{cell}-id0" for cell in range(4)
                                          for rules in ("classic", "rosette")))
        self.assertEqual(result[8:], tuple(f"{rules}-cell{cell}-id{ordinal}"
                                          for cell, ordinal in ((0, 1), (2, 1), (0, 2))
                                          for rules in ("classic", "rosette")))
        by_id = {row["id"]: row for row in rows}
        for rules in ("classic", "rosette"):
            own = [by_id[name] for name in result if by_id[name]["rules_id"] == rules]
            self.assertEqual([(row["n"], row["split"]) for row in own[:4]], list(cells))
        self.assertEqual(rows, before)

    def test_selectors_reject_malformed_aliases_duplicates_and_cell_overflow(self):
        bad_rows = [[indexed("a"), indexed("a")], [indexed("a", n=True)], [indexed("a", n=3.0)],
                    [indexed("a", n=5)], [indexed("a", rules=[])], [indexed("a", rules="breath-cap")],
                    [indexed("a", split={})], [indexed("a", disposition=[])],
                    [indexed("a", split="development", disposition="duplicate")],
                    [indexed(str(i)) for i in range(17)], [indexed("a") | {"command": "ignored?"}]]
        for function in (jobs.select_bootstrap_rows, jobs.select_certification_rows):
            for rows in bad_rows:
                with self.subTest(function=function.__name__, rows=rows):
                    with self.assertRaises(jobs.ProofJobIntegrityError):
                        function(rows)


class TestLabProofJobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Four explicitly authored single-placement fixtures. No policies,
        # game generation, proof producer/checker, or research ledger involved.
        definitions = []
        for name, rules, n, point in (("classic-a", "classic", 3, [2, 0]),
                                     ("classic-b", "classic", 3, [-8, 0]),
                                     ("junction-n4", "junction-y", 4, [2, 0]),
                                     ("breath-n4", "breath", 4, [2, 0])):
            definitions.append({"id": name, "configuration": origin_configuration(rules, n),
                                "actions": [{"action": "play", "point": point}],
                                "template_id": name, "family": "synthetic-mechanical-opening"})
        cls.small = compile_corpus(definitions, source_parent="1" * 40, trusted_sources=trusted_sources())
        cls.index = cls.small.compact_index()
        cls.raw = (canonical_json(cls.small.to_dict()) + "\n").encode()
        cls.source = {"commit": "2" * 40, "hashes": {label: "3" * 64 for label in jobs.SOURCE_PATHS}}

    @contextmanager
    def fixture(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(jobs, "RAW_SHA256", digest(self.raw)))
            stack.enter_context(patch.object(jobs, "MANIFEST_HASH", self.small.manifest_hash))
            stack.enter_context(patch.object(jobs, "_compact_index", return_value=deepcopy(self.index)))
            stack.enter_context(patch.object(jobs, "validate_committed_source", return_value=deepcopy(self.source)))
            stack.enter_context(patch.object(jobs, "verify_runtime_source"))
            yield jobs.AuthenticatedCorpus(self.raw)

    def test_loader_uses_structure_only_never_full_recompile_or_replay(self):
        with self.fixture(), TemporaryDirectory() as directory:
            path = Path(directory) / "frozen.json"
            path.write_bytes(self.raw)
            with patch.object(CorpusManifest, "from_dict", side_effect=AssertionError("no replay loader")), \
                    patch("research.harness.lab_corpus.compile_corpus", side_effect=AssertionError("no recompile")), \
                    patch("research.harness.lab_origin.verify_origin", side_effect=AssertionError("no replay")):
                value = jobs.load_frozen_corpus(path)
                self.assertEqual(value.to_dict(), self.small.to_dict())
            detached = value.rows
            detached[0]["certified"] = True
            self.assertFalse(value.rows[0]["certified"])
            self.assertEqual(value.identity["manifest_hash"], self.small.manifest_hash)
            with self.assertRaises(FrozenInstanceError):
                value._raw_bytes = b"replacement"

    def test_raw_physical_semantic_and_compact_pins_each_fail_closed(self):
        with self.fixture():
            with self.assertRaises(jobs.ProofJobIntegrityError):
                jobs.AuthenticatedCorpus(self.raw + b" ")
            with patch.object(jobs, "MANIFEST_HASH", "0" * 64):
                with self.assertRaisesRegex(jobs.ProofJobIntegrityError, "semantic"):
                    jobs.AuthenticatedCorpus(self.raw)
            wrong = deepcopy(self.index)
            wrong["candidates"][0]["legal_action_count"] += 1
            with patch.object(jobs, "_compact_index", return_value=wrong):
                with self.assertRaisesRegex(jobs.ProofJobIntegrityError, "correspondence"):
                    jobs.AuthenticatedCorpus(self.raw)

    def test_malformed_pinned_json_does_not_skip_strict_schema(self):
        malformed = [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'[]', b'null']
        wrong = self.small.to_dict()
        wrong["candidates"][0]["certified"] = True
        malformed.append(canonical_json(wrong).encode())
        for data in malformed:
            with self.subTest(data=data[:40]), patch.object(jobs, "RAW_SHA256", digest(data)):
                with self.assertRaises(jobs.ProofJobIntegrityError):
                    jobs.AuthenticatedCorpus(data)

    def test_real_compact_pin_authenticates_without_any_origin_action(self):
        with patch("research.harness.lab_origin.verify_origin", side_effect=AssertionError("no replay")):
            value = jobs._compact_index()
        self.assertEqual(len(value["candidates"]), 512)
        self.assertEqual(value["raw_manifest_hash"], jobs.MANIFEST_HASH)
        with patch.object(jobs, "_read", return_value=b"tampered"):
            with self.assertRaisesRegex(jobs.ProofJobIntegrityError, "physical"):
                jobs._compact_index()

    def test_bootstrap_manifest_complete_deterministic_detached_and_uncertified(self):
        with self.fixture() as corpus:
            first = jobs.build_bootstrap_manifest(corpus)
            second = jobs.build_bootstrap_manifest(corpus)
            self.assertEqual(first.to_dict(), second.to_dict())
            wire = first.to_dict()
            self.assertEqual(len(wire["tasks"]), 32)
            self.assertEqual(wire["configuration"]["execution"], jobs.BOOTSTRAP_EXECUTION)
            self.assertEqual(wire["configuration"]["limits"], {"producer_nodes": 32, "checker_nodes": 128})
            self.assertNotIn("measured", wire["configuration"]["execution"]["projection_kind"])
            self.assertIsNotNone(jobs.validate_proof_manifest(wire))
            for task in wire["tasks"]:
                payload = jobs.validate_proof_task(task)
                self.assertNotIn("legal_actions", payload)
                if payload["row"] is not None:
                    self.assertEqual(payload["row"]["split"], "development")
                    self.assertFalse(payload["row"]["certified"])
                    payload["row"]["certified"] = True
                    self.assertFalse(task["payload"]["row"]["certified"])
                else:
                    self.assertIsNone(payload["row_hash"])

    def test_certification_manifest_keeps_every_candidate_both_splits(self):
        with self.fixture() as corpus:
            result = jobs.build_certification_manifest(corpus, producer_nodes=64, checker_nodes=256).to_dict()
            expected = jobs.select_certification_rows(self.index["candidates"])
            self.assertEqual(tuple(t["payload"]["row"]["id"] for t in result["tasks"]), expected)
            self.assertEqual({t["payload"]["row"]["split"] for t in result["tasks"]}, {"development", "holdout"})
            self.assertIsNone(result["configuration"]["execution"])
            self.assertEqual(result["configuration"]["limits"], {"producer_nodes": 64, "checker_nodes": 256})
            self.assertEqual(result["configuration"]["order"], "rules-round-robin-four-subcell-ordinal-id")
            old_config = deepcopy(result["configuration"])
            old_config["order"] = "rules-round-robin-size-split-id"
            old = FixedTaskManifest.create(source=result["source"], configuration=old_config,
                                           tasks=[{"id": task["id"], "payload": task["payload"]} for task in result["tasks"]])
            with self.assertRaisesRegex(jobs.ProofJobIntegrityError, "configuration"):
                jobs.validate_proof_manifest(old)

    def test_builder_requires_authenticated_wrapper_and_strict_node_caps(self):
        for value in (self.small, self.small.to_dict(), self.index, None):
            with self.assertRaises(jobs.ProofJobIntegrityError):
                jobs.build_bootstrap_manifest(value)
        with self.fixture() as corpus:
            for count in (True, 3.0, 0, -1, 10001, "32", [], float("inf")):
                for key in ("producer_nodes", "checker_nodes"):
                    with self.subTest(key=key, count=count), self.assertRaises(jobs.ProofJobIntegrityError):
                        jobs.build_certification_manifest(corpus, **{key: count})

    def test_task_row_and_identity_tamper_rejected_even_with_resealed_envelope(self):
        with self.fixture() as corpus:
            wire = jobs.build_bootstrap_manifest(corpus).to_dict()
            good = next(t for t in wire["tasks"] if t["payload"]["row"] is not None)
            changes = [lambda p: p.update(slot=True), lambda p: p.update(stage=[]),
                       lambda p: p["cell"].update(rules_id=[]), lambda p: p["cell"].update(n=3.0),
                       lambda p: p["corpus"].update(raw_sha256="0" * 64),
                       lambda p: p["source"]["hashes"].update({"/tmp/execute.py": "a" * 64}),
                       lambda p: p["limits"].update(producer_nodes=33),
                       lambda p: p["row"].update(certified=True),
                       lambda p: p["row"].update(legal_action_count=2),
                       lambda p: p["row"]["definition"].update(family="altered"),
                       lambda p: p["row"]["origin_receipt"].update(full_action_replay=False),
                       lambda p: p["row"]["origin"]["final"]["stamp"].update(actor={}),
                       lambda p: p["row"].update(origin=None), lambda p: p.update(command="do not execute")]
            for change in changes:
                bad = deepcopy(good)
                change(bad["payload"])
                reseal_task(bad)
                with self.subTest(change=change), self.assertRaises(jobs.ProofJobIntegrityError):
                    jobs.validate_proof_task(bad)
            bad = deepcopy(good)
            bad["payload_hash"] = "a" * 64
            with self.assertRaises(jobs.ProofJobIntegrityError):
                jobs.validate_proof_task(bad)

    def test_missing_slots_cannot_receive_substitutes(self):
        with self.fixture() as corpus:
            wire = jobs.build_bootstrap_manifest(corpus).to_dict()
            missing = deepcopy(next(t for t in wire["tasks"] if t["payload"]["row"] is None))
            present = next(t for t in wire["tasks"] if t["payload"]["row"] is not None)
            missing["payload"]["row"] = deepcopy(present["payload"]["row"])
            reseal_task(missing)
            with self.assertRaisesRegex(jobs.ProofJobIntegrityError, "substitute"):
                jobs.validate_proof_task(missing)

    def test_manifest_reordering_omission_and_config_changes_rejected_when_resealed(self):
        with self.fixture() as corpus:
            good = jobs.build_bootstrap_manifest(corpus).to_dict()
            for alteration in ("reorder", "omit", "extra", "configuration", "source"):
                wire = deepcopy(good)
                if alteration == "reorder":
                    wire["tasks"][0], wire["tasks"][1] = wire["tasks"][1], wire["tasks"][0]
                elif alteration == "omit":
                    wire["tasks"].pop()
                elif alteration == "extra":
                    wire["tasks"].append(wire["tasks"][0])
                elif alteration == "configuration":
                    wire["configuration"]["execution"]["workers"] = 9
                else:
                    wire["source"]["commit"] = "4" * 40
                tasks = [{"id": row["id"], "payload": row["payload"]} for row in wire["tasks"]]
                with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                    resealed = FixedTaskManifest.create(source=wire["source"], configuration=wire["configuration"], tasks=tasks)
                    jobs.validate_proof_manifest(resealed)


class TestLabProofJobSources(unittest.TestCase):
    def test_source_mapping_is_closed_and_contains_no_runtime_artifact_paths(self):
        paths = jobs.authoritative_sources()
        self.assertEqual(set(paths), set(jobs.SOURCE_PATHS))
        for label, path in paths.items():
            self.assertFalse(Path(label).is_absolute())
            self.assertEqual(path, jobs.REPOSITORY / label)
        self.assertIn("research/harness/lab_proof_task.py", paths)
        self.assertIn("research/harness/lab_research_cli.py", paths)
        source = {"commit": "1" * 40, "hashes": {k: "a" * 64 for k in paths}}
        source["hashes"]["/tmp/manifest-import.py"] = "b" * 64
        with patch.object(jobs, "_read", side_effect=AssertionError("no supplied path reads")):
            with self.assertRaises(jobs.ProofJobIntegrityError):
                jobs.verify_runtime_source(source)

    def test_runtime_hashes_reject_drift_missing_and_loaded_byte_changes(self):
        fake = {label: "a" * 64 for label in jobs.SOURCE_PATHS}
        source = {"commit": "1" * 40, "hashes": fake}
        with patch.object(jobs, "runtime_source_hashes", return_value=fake):
            self.assertIsNone(jobs.verify_runtime_source(source))
            bad = deepcopy(source)
            bad["hashes"][jobs.SOURCE_PATHS[0]] = "b" * 64
            with self.assertRaises(jobs.ProofJobIntegrityError):
                jobs.verify_runtime_source(bad)
        with patch.object(jobs, "_read", return_value=b"changed"):
            with self.assertRaisesRegex(jobs.ProofJobIntegrityError, "since import"):
                jobs.runtime_source_hashes()
        with patch.object(jobs, "_read", side_effect=jobs.ProofJobIntegrityError("missing")):
            with self.assertRaises(jobs.ProofJobIntegrityError):
                jobs.runtime_source_hashes()

    def test_commit_validation_binds_fixed_paths_allows_unchanged_ancestor(self):
        contents = {label: ("synthetic:" + label).encode() for label in jobs.SOURCE_PATHS}
        hashes = {label: digest(data) for label, data in contents.items()}
        calls = []
        def git(*args):
            calls.append(args)
            if args == ("rev-parse", "HEAD"):
                return b"2" * 40 + b"\n"
            if args[:2] == ("merge-base", "--is-ancestor"):
                return b""
            commit, label = args[1].split(":", 1)
            self.assertIn(commit, ("1" * 40, "2" * 40))
            self.assertIn(label, jobs.SOURCE_PATHS)
            return contents[label]
        with patch.object(jobs, "runtime_source_hashes", return_value=hashes), patch.object(jobs, "_git", side_effect=git):
            fresh = jobs.validate_committed_source()
            self.assertEqual(fresh["commit"], "2" * 40)
            ancestor = {"commit": "1" * 40, "hashes": hashes}
            self.assertEqual(jobs.validate_committed_source(ancestor), ancestor)
        self.assertEqual(sum(c[0] == "show" for c in calls), 2 * len(jobs.SOURCE_PATHS))

    def test_commit_missing_blob_uncommitted_changes_and_false_hashes_fail(self):
        hashes = {label: digest(b"expected") for label in jobs.SOURCE_PATHS}
        def git(*args):
            if args == ("rev-parse", "HEAD"):
                return b"1" * 40
            if args[0] == "merge-base":
                return b""
            return b"different committed source"
        with patch.object(jobs, "runtime_source_hashes", return_value=hashes), patch.object(jobs, "_git", side_effect=git):
            with self.assertRaisesRegex(jobs.ProofJobIntegrityError, "committed source mismatch"):
                jobs.validate_committed_source()
        with patch.object(jobs, "runtime_source_hashes", return_value=hashes), \
                patch.object(jobs, "_git", side_effect=jobs.ProofJobIntegrityError("missing commit/blob")):
            with self.assertRaises(jobs.ProofJobIntegrityError):
                jobs.validate_committed_source()

    def test_bad_hash_types_and_executable_commit_text_are_never_git_arguments(self):
        fake = {label: "a" * 64 for label in jobs.SOURCE_PATHS}
        for commit in (True, [], "$(touch /tmp/no)", "--help", "f" * 39):
            source = {"commit": commit, "hashes": fake}
            with patch.object(jobs, "runtime_source_hashes", return_value=fake), \
                    patch.object(jobs, "_git", return_value=b"1" * 40) as git:
                with self.assertRaises(jobs.ProofJobIntegrityError):
                    jobs.validate_committed_source(source)
                self.assertEqual(git.call_args_list, [unittest.mock.call("rev-parse", "HEAD")])


if __name__ == "__main__":
    unittest.main()
