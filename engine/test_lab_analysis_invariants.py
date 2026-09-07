"""Independent Batch6 analysis checks on short authored mechanical records.

No policy games, search, proof work, holdout positions, or human observations
are generated here. Existing independently authored record/geometry fixtures are
reused without altering their source or bypassing legal-action validation.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_lab_junctions import capture_sequence, transform_sequence  # noqa: E402
from test_lab_record_invariants import action, make_record  # noqa: E402
from research.harness import lab_evidence_bundle as evidence  # noqa: E402
from research.harness import lab_record_analysis as analysis  # noqa: E402


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def wires(sequence):
    return [action(row[0], row[1], row[2] if len(row) == 3 else None)
            for row in sequence]


def synthetic_evidence_inputs():
    """Interchange-only fixture, never an authenticated historical artifact.

    Empty mechanically valid records and synthetic receipt/source hashes test
    shape and consistency. The corpus inventory is packaged metadata only;
    neither its positions nor any external record is replayed here.
    """
    catalog = evidence._catalog()
    index_path = Path(__file__).resolve().parents[1] / evidence.INDEX_PINS["corpus"][0]
    inventory = json.loads(index_path.read_text())["rulesets"]
    selected = []
    for path in evidence.SELECTED_PATHS:
        name = Path(path).name
        rules = ("gjerde-majority" if "majority" in name else
                 max((spec["id"] for spec in catalog if name.startswith(spec["id"] + "-")), key=len))
        record, _, _ = make_record(rules=rules)
        receipt = {"format": "varde-lab-record-replay", "version": 1,
                   "mechanically_verified": True, "action_count": 0,
                   "accepted": False, "replay_hash": digest({"synthetic": path}),
                   "claim_limit": "mechanical replay only; not a qualified human study or game-quality finding"}
        selected.append({"path": path, "record": record, "sha256": digest(record),
                         "provenance": {"kind": "engineering-ui-automation", "source_id": path},
                         "replay_receipt": receipt})
    excluded = []
    for path, source in zip(evidence.EXCLUDED_PATHS, selected):
        excluded.append({"path": path, "sha256": source["sha256"],
                         "provenance": {"kind": "engineering-ui-automation", "source_id": path},
                         "replay_receipt": deepcopy(source["replay_receipt"]),
                         "ruleset": source["record"]["rules"]["id"], "revision": "0.1",
                         "board_size": 3, "action_count": 0, "accepted": False,
                         "reason": "superseded-matrix-2"})
    pins = {key: {"path": path, "sha256": sha} for key, (path, sha) in evidence.INDEX_PINS.items()}
    pins["browser_raw"] = {"path": evidence.BROWSER_RAW, "sha256": "a" * 64}
    for path in (evidence.BROWSER_AUDIT, evidence.MAJORITY_RECEIPT) + evidence.BOOTSTRAP_FILES:
        pins[path] = {"path": path, "sha256": "a" * 64}
    pins.update({row["path"]: {"path": row["path"], "sha256": row["sha256"]}
                 for row in selected + excluded})
    tasks = [(rules, n) for n in (3, 4) for rules in evidence.PRODUCTION_RULESETS]
    task_ids = [f"bootstrap-{i:03d}-{rules}-n{n}" for i, (rules, n) in enumerate(tasks)]
    checker_work = ("callback_calls", "legal_action_enumerations", "nodes_checked", "terminal_scores_checked",
                    "terminal_simulation_backups", "transition_attempts", "unknown_successors_checked")
    producer_work = ("actions_enumerated", "callback_calls", "legal_action_enumerations", "memo_hits", "nodes",
                     "terminal_leaves", "terminal_simulation_backups", "transition_attempts")
    completed = [{"cell": {"rules_id": rules, "n": n}, "task_id": task_ids[i],
                  "independently_certified": False, "result_hash": "c" * 64,
                  "comparison": {"status": "unqualified-shared-mechanics", "independent_complete": False,
                                 "root_domains_equal": False, "root_bounds": [-1, 1],
                                 "root_class": "partial", "optimal_action_ids": []},
                  "paths": {"independent": None, "production": {
                      "producer_status": "partial", "producer_reason": "node-limit",
                      "producer_work": dict.fromkeys(producer_work, 0),
                      "checker_status": "unknown", "checker_reason": "node-limit", "checker_verified": False,
                      "checker_work": dict.fromkeys(checker_work, 0), "root_width": 2}}}
                 for i, (rules, n) in enumerate(tasks[:6])]
    return {"format": evidence.INPUT_FORMAT, "version": 1,
            "source": {"commit": "a" * 40, "commit_role": "evidence-parent",
                       "hashes": dict.fromkeys(evidence.SOURCE_PATHS, "b" * 64),
                       "hash_scope": "actual-report-tool-and-frozen-dependencies"},
            "pins": pins, "catalog": catalog, "candidate_inventory": inventory,
            "selected_records": selected, "excluded_records": excluded,
            "bootstrap": {"accounting": {
                "status": "timeout", "reason": "task-timeout", "task_count": 32,
                "attempted": 14, "completed": 6, "interrupted": 8, "unstarted": 18,
                "independently_certified": 0, "admitted_agents": 0, "all_cleanup_confirmed": True,
            }, "semantic": {
                "admission_record": False, "canonical_results_hash": "c" * 64,
                "manifest_hash": "d" * 64,
                "completed": completed, "not_completed": task_ids[6:],
            }}}


def reseal_bundle(value):
    value["bundle_hash"] = digest({key: row for key, row in value.items() if key != "bundle_hash"})
    return value


class TestLabEvidenceAnalysisIndependent(unittest.TestCase):
    def setUp(self):
        self.inputs = synthetic_evidence_inputs()
        self.bundle = evidence.build_evidence_bundle(
            evidence.EvidenceInputs.from_dict(self.inputs)).to_dict()

    def test_synthetic_interchange_preserves_all_missingness_without_authentication(self):
        before = deepcopy(self.inputs)
        checked = evidence.validate_evidence_inputs(self.inputs)
        self.assertEqual(self.inputs, before)
        self.assertEqual(len(self.bundle["cards"]), 16)
        self.assertEqual(self.bundle["comparative_shortlist"], [])
        self.assertEqual(self.bundle["record_selection"]["audited"], 25)
        self.assertEqual(len(self.bundle["record_selection"]["selected"]), 13)
        self.assertEqual(len(self.bundle["record_selection"]["excluded"]), 12)
        for card in self.bundle["cards"]:
            self.assertEqual(card["comparative_games"], 0)
            self.assertFalse(card["comparative_headline_allowed"])
            self.assertFalse(card["shortlist"]["qualified"])
            self.assertIsNone(card["shortlist"]["design_priority"])
            for field in card["human_observations"].values():
                self.assertEqual(field["status"], "unmeasured")
                self.assertIsNone(field["value"])
        checked["catalog"].clear()
        self.assertEqual(self.inputs, before)

    def test_resealed_bundle_cannot_replace_or_malform_pinned_index(self):
        for replacement in ("not-a-hash", "0" * 64):
            changed = deepcopy(self.bundle)
            changed["pins"]["corpus"]["sha256"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                evidence.validate_evidence_bundle(reseal_bundle(changed))

    def test_resealed_bundle_cannot_relabel_script_as_legacy_evidence(self):
        changed = deepcopy(self.bundle)
        changed["record_selection"]["selected"][0]["ruleset"] = "classic"
        changed["record_selection"]["selected"][0]["revision"] = "1.3"
        # Recomputed aggregate counts cannot legitimize changed record identity.
        selected, excluded = (changed["record_selection"][key] for key in ("selected", "excluded"))
        changed["script_coverage"] = evidence._script_coverage(selected, excluded)
        with self.assertRaises(ValueError):
            evidence.validate_evidence_bundle(reseal_bundle(changed))

    def test_resealed_bundle_checks_record_receipt_and_nested_field_types(self):
        for alteration in ("receipt", "board_size", "extra"):
            changed = deepcopy(self.bundle)
            item = changed["record_selection"]["selected"][0]
            if alteration == "receipt":
                item["replay_receipt"]["accepted"] = True
            elif alteration == "board_size":
                item["board_size"] = True
            else:
                item["human_sample"] = True
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                evidence.validate_evidence_bundle(reseal_bundle(changed))

    def test_input_provenance_and_certified_counts_are_strict_not_bool_aliases(self):
        for alteration in ("human", "count", "receipt"):
            changed = deepcopy(self.inputs)
            if alteration == "human":
                changed["selected_records"][0]["provenance"]["kind"] = "human-observation"
            elif alteration == "count":
                changed["candidate_inventory"][0]["certified_counts"]["development"] = False
            else:
                changed["excluded_records"][0]["replay_receipt"]["mechanically_verified"] = False
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                evidence.validate_evidence_inputs(changed)

    def test_resealed_bundle_cannot_add_human_rating_or_admission(self):
        for alteration in ("human", "shortlist", "games", "admission"):
            changed = deepcopy(self.bundle)
            card = changed["cards"][0]
            if alteration == "human":
                card["human_observations"]["beauty"]["value"] = 6
            elif alteration == "shortlist":
                card["shortlist"]["qualified"] = True
            elif alteration == "games":
                card["comparative_games"] = 100
            else:
                card["mcts_admission"]["status"] = "admitted"
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                evidence.validate_evidence_bundle(reseal_bundle(changed))

    def test_partial_bootstrap_cannot_embed_independent_or_verified_proof_claims(self):
        for alteration in ("independent", "checker"):
            changed = deepcopy(self.bundle)
            completed = changed["bootstrap"]["semantic"]["completed"][0]
            if alteration == "independent":
                completed["comparison"]["independent_complete"] = True
            else:
                completed["paths"]["production"]["checker_verified"] = True
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                evidence.validate_evidence_bundle(reseal_bundle(changed))


class TestLabRecordAnalysisIndependent(unittest.TestCase):
    def analyze(self, record, source_id="synthetic/authored-record.json"):
        before = deepcopy(record)
        result = analysis.analyze_record(record,
            provenance={"kind": "engineering-ui-automation", "source_id": source_id},
            source_sha256=digest(record)).to_dict()
        self.assertEqual(record, before)
        self.assertEqual(result["replay_passes"], 2)
        return result

    def test_empty_record_is_an_unfinished_mechanical_observation(self):
        record, _, _ = make_record()
        result = self.analyze(record)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["counters"], {
            "rules_actions": 0, "placements": 0, "constructions": 0,
            "passes": 0, "swaps": 0, "acceptances": 0, "resumptions": 0,
        })
        self.assertEqual(result["actions"], [])
        self.assertEqual(len(result["frames"]), 1)
        self.assertEqual(result["frames"][0]["action_index"], -1)

    def test_planted_contact_uses_actual_new_spokes_and_pre_action_colors(self):
        # Off-center face(1,0), with alternating corner sets {0,2,4}/{1,3,5}.
        # The black stone at corner0 and white stone at corner1 are each close
        # to the hub geometrically, but only one is connected per orientation.
        for orientation, expected in ((0, (True, False)), (1, (False, True))):
            with self.subTest(orientation=orientation):
                record, _, _ = make_record("junction-planted", actions=[
                    action("play", (5, 1)), action("play", (4, 2)),
                    action("plant", (1, 0), orientation),
                ])
                result = self.analyze(record)
                planted = result["actions"][-1]
                self.assertEqual(planted["coordinate"], [3, 1])
                self.assertEqual(planted["action"], action("plant", (1, 0), orientation))
                self.assertEqual((planted["friendly_contact"], planted["enemy_contact"]), expected)
                self.assertEqual(result["counters"]["rules_actions"], 3)
                self.assertEqual(result["counters"]["placements"], 3)
                self.assertEqual(result["counters"]["constructions"], 1)

    def test_two_friendly_incident_edges_still_count_one_contact_placement(self):
        record, _, _ = make_record("junction-planted", actions=[
            action("play", (5, 1)), action("play", (-8, -2)),
            action("play", (2, 2)), action("play", (-8, 0)),
            action("plant", (1, 0), 0),
        ])
        result = self.analyze(record)
        planted = result["actions"][-1]
        self.assertIs(planted["friendly_contact"], True)
        self.assertIs(planted["enemy_contact"], False)
        rows = [row for row in result["heatmaps"]
                if row["kind"] == "friendly-contact" and row["point"] == [3, 1]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 1)

    def test_empty_construction_is_not_a_placement_or_contact(self):
        for orientation, expected_friend in ((0, True), (1, False)):
            with self.subTest(orientation=orientation):
                record, _, _ = make_record("junction-y", actions=[
                    action("play", (5, 1)), action("construct", (1, 0), orientation),
                    action("play", (3, 1)),
                ])
                result = self.analyze(record)
                built, occupied = result["actions"][1:]
                self.assertEqual(built["coordinate"], [3, 1])
                self.assertFalse(built["friendly_contact"])
                self.assertFalse(built["enemy_contact"])
                self.assertIs(occupied["friendly_contact"], expected_friend)
                self.assertEqual(result["counters"]["placements"], 2)
                self.assertEqual(result["counters"]["constructions"], 1)

    def test_center_capture_counts_hub_and_preserves_topology_in_frames(self):
        record, _, _ = make_record("junction-y", actions=wires(capture_sequence("junction-y")))
        result = self.analyze(record)
        last = result["actions"][-1]
        self.assertEqual(last["captures"], {"original": 0, "junction": 1, "waves": [[[0, 0]]]})
        last_projection = result["frames"][-1]["projection"]
        self.assertIn([0, 0], last_projection["current_graph"]["points"])
        self.assertNotIn([0, 0], last_projection["current_graph"]["original_points"])
        self.assertNotIn([0, 0], last_projection["current_graph"]["scoring_points"])
        self.assertEqual(len(last_projection["current_graph"]["topology"]), 1)
        rows = [row for row in result["heatmaps"] if row["kind"] == "capture-junction"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["point"], [0, 0])
        self.assertEqual(rows[0]["count"], 1)

    def test_pie_and_both_ending_phases_preserve_original_seats_and_action_counts(self):
        recorded = [action("play", (2, 0)), action("swap"),
                    action("pass"), action("pass"), action("accept"),
                    action("resume"), action("pass"), action("pass"), action("accept")]
        record, _, _ = make_record(actions=recorded)
        result = self.analyze(record)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["counters"], {
            "rules_actions": 9, "placements": 1, "constructions": 0,
            "passes": 4, "swaps": 1, "acceptances": 2, "resumptions": 1,
        })
        self.assertEqual(result["actions"][1]["actor"], {"color": "W", "seat": "S2"})
        self.assertEqual(result["actions"][2]["actor"], {"color": "W", "seat": "S1"})
        # A first acceptance did not end the game; the other seat could resume.
        self.assertFalse(result["frames"][5]["projection"]["phase"]["accepted"])
        self.assertTrue(result["frames"][-1]["projection"]["phase"]["accepted"])

    def test_spatial_canonicalization_keeps_transformed_orientation_equivalent(self):
        sequence = (("play", (5, 1)), ("construct", (1, 0), 0), ("play", (3, 1)))
        keys = set()
        for turns, reflected in ((0, False), (1, False), (3, True), (5, True)):
            with self.subTest(turns=turns, reflected=reflected):
                transformed = transform_sequence("junction-y", sequence, turns, reflected)
                record, _, _ = make_record("junction-y", actions=wires(transformed))
                result = self.analyze(record)
                projection = result["frames"][-1]["projection"]
                before = deepcopy(projection)
                canonicalized = analysis.canonical_diagram(projection)
                self.assertEqual(projection, before)
                self.assertEqual(canonicalized["key"], result["frames"][-1]["spatial_key"])
                keys.add(canonicalized["key"])
        self.assertEqual(len(keys), 1)

    def test_spatially_equal_scripts_remain_distinct_traces_with_atlas_links(self):
        entries = []
        for label, point in (("left", (-2, 0)), ("right", (2, 0))):
            record, _, _ = make_record(actions=[action("play", point)])
            entries.append({"record": record,
                            "provenance": {"kind": "engineering-ui-automation",
                                           "source_id": f"synthetic/{label}.json"},
                            "source_sha256": digest(record)})
        before = deepcopy(entries)
        result = analysis.analyze_records(entries).to_dict()
        self.assertEqual(entries, before)
        self.assertEqual(result["distinct_traces"], 2)
        self.assertEqual(result["duplicate_records"], [])
        self.assertEqual(len({row["trace_hash"] for row in result["records"]}), 2)
        self.assertEqual(result["strata"][0]["counters"]["placements"], 2)
        self.assertEqual(len(result["atlas"]), 2)  # Initial and rotated-opening classes.
        for diagram in result["atlas"]:
            self.assertEqual(diagram["occurrences"], 2)
            self.assertEqual({row["source_id"] for row in diagram["members"]},
                             {"synthetic/left.json", "synthetic/right.json"})
        self.assertEqual(result["scope"]["admitted_games"], 0)
        self.assertEqual(result["scope"]["human_observations"], 0)
        self.assertIsNone(result["scope"]["strategic_depth"])
        self.assertIsNone(result["scope"]["beauty"])

    def test_malformed_record_and_human_or_path_provenance_fail_closed(self):
        record, _, _ = make_record(actions=[action("play", (2, 0))])
        for alteration in ("orientation", "capture", "score", "actor"):
            changed = deepcopy(record)
            row = changed["actions"][0]
            if alteration == "orientation":
                row["action"]["orientation"] = 0
            elif alteration == "capture":
                row["captures"]["junction"] = 1
            elif alteration == "score":
                row["after"]["score"]["B"] += 1
            else:
                row["actor"]["seat"] = "S2"
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                self.analyze(changed)
        for provenance in ({"kind": "human-observation", "source_id": "record.json"},
                           {"kind": "engineering-ui-automation", "source_id": "../outside.json"},
                           {"kind": "engineering-ui-automation", "source_id": "/tmp/record.json"}):
            with self.subTest(provenance=provenance), self.assertRaises(ValueError):
                analysis.analyze_record(record, provenance=provenance, source_sha256=digest(record))


if __name__ == "__main__":
    unittest.main()
