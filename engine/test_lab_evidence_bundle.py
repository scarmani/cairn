"""Synthetic interchange tests; no recorded action is replayed or evaluated."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from research.harness import lab_evidence_bundle as evidence  # noqa: E402


def synthetic_inputs():
    """Declared synthetic metadata only; intentionally not authenticated evidence."""
    pins = {key: {"path": path, "sha256": digest} for key, (path, digest) in evidence.INDEX_PINS.items()}
    pins["browser_raw"] = {"path": evidence.BROWSER_RAW, "sha256": "a" * 64}
    for path in ((evidence.BROWSER_AUDIT, evidence.MAJORITY_RECEIPT)
                 + evidence.SELECTED_PATHS + evidence.EXCLUDED_PATHS + evidence.BOOTSTRAP_FILES):
        pins[path] = {"path": path, "sha256": "a" * 64}
    receipt = {"format": "varde-lab-record-replay", "version": 1, "mechanically_verified": True,
               "action_count": 0, "accepted": False, "replay_hash": "b" * 64,
               "claim_limit": "mechanical replay only; not a qualified human study or game-quality finding"}
    selected, excluded = [], []
    for path in evidence.SELECTED_PATHS + evidence.EXCLUDED_PATHS:
        name = path.rsplit("/", 1)[1]
        rules = "gjerde-majority" if name.startswith("majority-four") else next(
            rule for rule in evidence.PRODUCTION_RULESETS if name.startswith(rule + "-")
            and rule not in evidence.LEGACY_CANDIDATES)
        record = {"format": "varde-lab-playtest", "version": 2, "source": "browser-local-hotseat",
                  "session_id": "11111111-1111-4111-8111-111111111111", "rules": {"id": rules, "revision": "0.1"},
                  "board_size": 3, "catalog_version": 1, "initial_seats": {"B": "S1", "W": "S2"},
                  "status": "active", "actions": [], "final_score": None}
        item = {"path": path, "sha256": "a" * 64, "record": record,
                "provenance": {"kind": "engineering-ui-automation", "source_id": path},
                "replay_receipt": deepcopy(receipt)}
        if path in evidence.SELECTED_PATHS:
            selected.append(item)
        else:
            excluded.append(evidence._record_metadata(item) | {"reason": "superseded-matrix-2"})
    ids = [f"bootstrap-{index:03d}-{rules}-n{size}" for index, (size, rules) in enumerate(
        (size, rules) for size in (3, 4) for rules in evidence.PRODUCTION_RULESETS)]
    completed = [{"cell": {"n": 3, "rules_id": rules}, "task_id": ids[index],
                  "independently_certified": False, "result_hash": "c" * 64,
                  "comparison": {"independent_complete": False, "optimal_action_ids": [], "root_bounds": [-1, 1],
                                 "root_class": "partial", "root_domains_equal": False,
                                 "status": "unqualified-shared-mechanics"},
                  "paths": {"independent": None, "production": {
                      "checker_reason": "node-limit", "checker_status": "unknown", "checker_verified": False,
                      "checker_work": dict.fromkeys(("callback_calls", "legal_action_enumerations", "nodes_checked", "terminal_scores_checked",
                                                     "terminal_simulation_backups", "transition_attempts", "unknown_successors_checked"), 0),
                      "producer_reason": "node-limit", "producer_status": "partial",
                      "producer_work": dict.fromkeys(("actions_enumerated", "callback_calls", "legal_action_enumerations", "memo_hits", "nodes",
                                                      "terminal_leaves", "terminal_simulation_backups", "transition_attempts"), 0), "root_width": 2}}}
                 for index, rules in enumerate(evidence.LEGACY_CANDIDATES)]
    inventory = json.loads((REPOSITORY / evidence.INDEX_PINS["corpus"][0]).read_text())["rulesets"]
    return {"format": evidence.INPUT_FORMAT, "version": 1,
            "source": {"commit": "e" * 40, "commit_role": "evidence-parent",
                       "hashes": dict(evidence._LOADED_SOURCES),
                       "hash_scope": "actual-report-tool-and-frozen-dependencies"},
            "pins": pins, "catalog": evidence._catalog(), "candidate_inventory": inventory,
            "bootstrap": {"semantic": {"admission_record": False, "canonical_results_hash": "d" * 64,
                                        "completed": completed, "manifest_hash": "e" * 64,
                                        "not_completed": ids[6:]},
                          "accounting": {"status": "timeout", "reason": "task-timeout", "task_count": 32,
                                         "attempted": 14, "completed": 6, "interrupted": 8, "unstarted": 18,
                                         "independently_certified": 0, "admitted_agents": 0,
                                         "all_cleanup_confirmed": True}},
            "selected_records": selected, "excluded_records": excluded}


def reseal(bundle):
    bundle["bundle_hash"] = evidence.canonical_hash({key: value for key, value in bundle.items() if key != "bundle_hash"})
    return bundle


class EvidenceBundleTests(unittest.TestCase):
    def bundle(self):
        return evidence.build_evidence_bundle(evidence.EvidenceInputs.from_dict(synthetic_inputs())).to_dict()

    def test_all_definitions_missingness_and_separate_coverage(self):
        bundle = self.bundle()
        self.assertEqual([card["ruleset"] for card in bundle["cards"]], list(evidence.PRODUCTION_RULESETS))
        self.assertEqual(len(bundle["record_selection"]["selected"]), 13)
        self.assertEqual(len(bundle["record_selection"]["excluded"]), 12)
        self.assertEqual(bundle["comparative_shortlist"], [])
        for card in bundle["cards"]:
            self.assertEqual(card["comparative_games"], 0)
            self.assertFalse(card["comparative_headline_allowed"])
            self.assertFalse(card["shortlist"]["qualified"])
            self.assertIsNone(card["shortlist"]["design_priority"])
            self.assertEqual(card["mcts_admission"]["status"], "unmeasured")
            for item in card["human_observations"].values():
                self.assertEqual(item["status"], "unmeasured")
                self.assertIsNone(item["value"])

    def test_detached_deterministic_roundtrip_and_render(self):
        raw = synthetic_inputs()
        before = deepcopy(raw)
        inputs = evidence.EvidenceInputs.from_dict(raw)
        first = evidence.build_evidence_bundle(inputs)
        second = evidence.build_evidence_bundle(evidence.EvidenceInputs.from_dict(inputs.to_dict()))
        self.assertEqual(first.canonical_hash, second.canonical_hash)
        self.assertEqual(evidence.render_evidence_markdown(first), evidence.render_evidence_markdown(second))
        self.assertEqual(raw, before)
        output = first.to_dict()
        output["cards"].clear()
        self.assertEqual(len(first.to_dict()["cards"]), 16)

    def test_bundle_pins_are_closed_and_crosslinked(self):
        cases = []
        value = self.bundle()
        value["pins"]["runtime"] = {"path": "/tmp/claim.py", "sha256": "a" * 64}
        cases.append(value)
        value = self.bundle()
        del value["pins"][evidence.SELECTED_PATHS[0]]
        cases.append(value)
        value = self.bundle()
        value["pins"][evidence.SELECTED_PATHS[0]]["sha256"] = "f" * 64
        cases.append(value)
        for value in cases:
            with self.subTest(value=value["pins"].keys()), self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence.validate_evidence_bundle(reseal(value))

    def test_metadata_rejects_aliases_unknown_fields_and_mismatched_rules(self):
        for key, replacement in (("ruleset", "classic"), ("revision", "1.3"), ("board_size", True),
                                 ("action_count", False), ("accepted", 0), ("extra", "claim")):
            value = self.bundle()
            value["record_selection"]["excluded"][0][key] = replacement
            with self.subTest(key=key), self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence.validate_evidence_bundle(reseal(value))

    def test_inventory_counts_reject_boolean_aliases(self):
        value = synthetic_inputs()
        value["candidate_inventory"][0]["certified_counts"]["development"] = False
        with self.assertRaises(evidence.EvidenceBundleIntegrityError):
            evidence.EvidenceInputs.from_dict(value)

    def test_evidence_parent_must_contain_exact_pinned_indices(self):
        completed = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")
        with patch.object(evidence.subprocess, "run", return_value=completed):
            with self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence._source("e" * 40)

    def test_parent_source_authentication_success_and_missing_history(self):
        calls = []

        def git(args, **kwargs):
            calls.append(args)
            if args[1] == "show":
                path = args[2].split(":", 1)[1]
                return subprocess.CompletedProcess(args, 0, stdout=(REPOSITORY / path).read_bytes(), stderr=b"")
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with patch.object(evidence.subprocess, "run", side_effect=git):
            source = evidence._source("e" * 40)
        self.assertEqual(source["commit"], "e" * 40)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(call[2].startswith("e" * 40 + ":") for call in calls[1:]))
        with patch.object(evidence.subprocess, "run", side_effect=subprocess.CalledProcessError(128, ["git", "show"])):
            with self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence._source("e" * 40)

    def test_loaded_report_source_drift_is_not_relabelled_as_parent_evidence(self):
        def read(root, relative):
            if relative == evidence.SOURCE_PATHS[0]:
                return b"changed after import"
            return (root / relative).read_bytes()

        with patch.object(evidence, "_read", side_effect=read), patch.object(evidence.subprocess, "run") as git:
            git.side_effect = lambda args, **_: subprocess.CompletedProcess(
                args, 0, stdout=(REPOSITORY / args[2].split(":", 1)[1]).read_bytes() if args[1] == "show" else b"", stderr=b"")
            with self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence._source("e" * 40)

    def test_record_roles_receipts_and_no_human_or_admission_upgrade(self):
        cases = []
        value = synthetic_inputs()
        value["selected_records"][0]["path"] = evidence.EXCLUDED_PATHS[0]
        cases.append(value)
        value = synthetic_inputs()
        value["excluded_records"][0]["replay_receipt"]["mechanically_verified"] = False
        cases.append(value)
        value = synthetic_inputs()
        value["selected_records"][0]["replay_receipt"]["action_count"] = 1
        cases.append(value)
        value = synthetic_inputs()
        value["selected_records"][0]["provenance"]["kind"] = "human-observation"
        cases.append(value)
        value = synthetic_inputs()
        value["catalog"][0]["revision"] = "0.1"
        cases.append(value)
        for value in cases:
            with self.subTest(value=value["selected_records"][0]["path"]), self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence.validate_evidence_inputs(value)
        for field, replacement in (("comparative_games", 100), ("comparative_headline_allowed", True)):
            value = self.bundle()
            value["cards"][0][field] = replacement
            with self.subTest(field=field), self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence.validate_evidence_bundle(reseal(value))

    def test_bootstrap_rows_cannot_change_identity_or_imply_terminal_proofs(self):
        for section, field, replacement in ((None, "task_id", "bootstrap-006-line-breath-n3"),
                                             ("paths", "independent", {}),
                                             ("comparison", "root_class", "solved"),
                                             ("comparison", "root_domains_equal", True)):
            value = synthetic_inputs()
            row = value["bootstrap"]["semantic"]["completed"][0]
            (row if section is None else row[section])[field] = replacement
            with self.subTest(field=field), self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence.validate_evidence_inputs(value)

    def test_missing_or_changed_input_pins_fail_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence._read_pinned(temp, "absent.json", "a" * 64)
            path = Path(temp) / "record.json"
            path.write_bytes(b"{}")
            with self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence._read_pinned(temp, "record.json", "a" * 64)
            self.assertEqual(evidence._read_pinned(temp, "record.json", hashlib.sha256(b"{}").hexdigest()), {})

    def test_path_containment_and_strict_json(self):
        for path in ("../outside", "/tmp/outside", "a/../outside", "./inside", "a\\b", "a//b"):
            with self.subTest(path=path), self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence._path(path)
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'not-json'):
            with self.subTest(data=data), self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence._parse(data)

    def test_symlinks_cannot_escape_explicit_input_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            root.mkdir()
            outside = Path(temp) / "outside.json"
            outside.write_bytes(b"{}")
            (root / "alias.json").symlink_to(outside)
            with self.assertRaises(evidence.EvidenceBundleIntegrityError):
                evidence._read(root, "alias.json")

    def test_malformed_nested_json_reports_integrity_error_not_type_crash(self):
        paths = (("candidate_inventory", 0, "sizes"), ("bootstrap", "semantic", "completed"),
                 ("selected_records", 0, "provenance"), ("excluded_records", 0, "ruleset"))
        for path in paths:
            for replacement in (None, [], True):
                value = synthetic_inputs()
                target = value
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = replacement
                with self.subTest(path=path, replacement=replacement), self.assertRaises(evidence.EvidenceBundleIntegrityError):
                    evidence.validate_evidence_inputs(value)

    def test_public_shape_api_never_authenticates_or_replays(self):
        value = synthetic_inputs()
        with patch.object(evidence, "_read", side_effect=AssertionError("no external read")), \
                patch.object(evidence.subprocess, "run", side_effect=AssertionError("no subprocess")):
            inputs = evidence.EvidenceInputs.from_dict(value)
            bundle = evidence.build_evidence_bundle(inputs)
            self.assertEqual(bundle.to_dict()["comparative_shortlist"], [])


if __name__ == "__main__":
    unittest.main()
