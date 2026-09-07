"""Read-only analysis of short authored records; no policy or proof research."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from engine.test_lab_record import fixture
from research.harness.lab_terminal_cert import canonical_hash
from research.harness import lab_record_analysis as analysis


def provenance(source="tests/script.json"):
    return {"kind": "engineering-ui-automation", "source_id": source}


def entry(record, source="tests/script.json"):
    return {"record": record, "provenance": provenance(source), "source_sha256": canonical_hash(record)}


class TestLabRecordAnalysis(unittest.TestCase):
    def analyze(self, record):
        return analysis.analyze_record(record, provenance=provenance(), source_sha256=canonical_hash(record)).to_dict()

    def test_placement_construction_and_plant_counters_are_separate(self):
        for rules, kind in (("junction-y", "construct"), ("junction-planted", "plant")):
            record, _ = fixture(rules, ({"action": "play", "point": [2, 0]},
                                        {"action": kind, "face": [1, 0], "orientation": 1}))
            before = deepcopy(record)
            result = self.analyze(record)
            self.assertEqual(record, before)
            self.assertEqual(result["replay_passes"], 2)
            self.assertEqual(result["counters"]["rules_actions"], 2)
            self.assertEqual(result["counters"]["constructions"], 1)
            self.assertEqual(result["counters"]["placements"], 2 if kind == "plant" else 1)
            self.assertEqual(result["actions"][1]["coordinate"], [3, 1])
            self.assertEqual(result["actions"][1]["action"]["orientation"], 1)

    def test_replay_required_and_mutated_telemetry_fails_before_frames(self):
        record, _ = fixture(wires=({"action": "play", "point": [2, 0]},))
        with patch.object(analysis, "replay_lab_record", wraps=analysis.replay_lab_record) as replay:
            self.analyze(record)
        self.assertEqual(replay.call_count, 1)
        record["actions"][0]["after"]["score"]["B"] += 1
        with self.assertRaises(ValueError):
            self.analyze(record)

    def test_objective_score_and_original_control_are_distinct_provisional_observations(self):
        for rules, point in (("gjerde-majority", [3, 1]), ("breath-connection", [2, 0])):
            record, _ = fixture(rules, ({"action": "play", "point": point},))
            result = self.analyze(record)
            observation = result["actions"][0]
            with self.subTest(rules=rules):
                self.assertEqual(observation["current_objective_score"], record["actions"][0]["after"]["score"])
                self.assertEqual(observation["original_control"], {"B": 1, "W": 0})
                self.assertNotEqual(observation["current_objective_score"], observation["original_control"])
                self.assertEqual(observation["objective_score_status"], "provisional-position")
                self.assertIsNone(result["final_score"])
        complete, _ = fixture(wires=({"action": "play", "point": [2, 0]}, {"action": "pass"},
                                     {"action": "pass"}, {"action": "accept"}, {"action": "accept"}))
        result = self.analyze(complete)
        self.assertEqual(result["actions"][-1]["objective_score_status"], "accepted-terminal")
        self.assertEqual(result["actions"][-1]["current_objective_score"], result["final_score"])

    def test_strict_provenance_rejects_human_admission_and_path_authority(self):
        record, _ = fixture()
        for value in ({"kind": "human-observation", "source_id": "x"},
                      provenance() | {"admitted": True}, provenance("../outside.json"),
                      provenance("/absolute.json"), provenance("")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                analysis.analyze_record(record, provenance=value, source_sha256="a" * 64)
        for digest in (True, "0" * 63, "A" * 64):
            with self.assertRaises(ValueError):
                analysis.analyze_record(record, provenance=provenance(), source_sha256=digest)

    def test_dedup_ignores_session_timing_but_retains_source_accounting(self):
        record, _ = fixture(wires=({"action": "play", "point": [2, 0]},))
        repeated = deepcopy(record)
        repeated["session_id"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        repeated["actions"][0]["elapsed_ms"] = 999
        values = [entry(record, "matrix-2/a.json"), entry(repeated, "matrix-3/a.json")]
        result = analysis.analyze_records(values).to_dict()
        self.assertEqual(result["input_records"], 2)
        self.assertEqual(result["distinct_traces"], 1)
        self.assertEqual(len(result["duplicate_records"]), 1)
        self.assertEqual(result["strata"][0]["counters"]["rules_actions"], 1)
        self.assertEqual(result, analysis.analyze_records(list(reversed(values))).to_dict())

    def test_unobserved_coverage_is_missing_and_qualification_never_inferred(self):
        empty = analysis.analyze_records([]).to_dict()
        self.assertEqual(len(empty["coverage"]), 16)
        self.assertEqual(empty["strata"], [])
        self.assertTrue(all(row["observation"] is None for row in empty["coverage"]))
        self.assertEqual(empty["scope"]["admitted_games"], 0)
        self.assertEqual(empty["scope"]["human_observations"], 0)
        self.assertIsNone(empty["scope"]["strategic_depth"])
        self.assertIsNone(empty["scope"]["beauty"])

    def test_svg_uses_actual_edges_scoring_points_hubs_and_escapes_annotation(self):
        record, _ = fixture("junction-passage", ({"action": "play", "point": [2, 0]},
                                                 {"action": "construct", "face": [1, 0], "orientation": 2}))
        report = self.analyze(record)
        projection = report["frames"][-1]["projection"]
        before = deepcopy(projection)
        svg = analysis.render_diagram(projection, annotation="<script>not executable</script>")
        root = ElementTree.fromstring(svg)
        ns = {"s": "http://www.w3.org/2000/svg"}
        self.assertEqual(len(root.findall(".//s:line[@class='graph-edge']", ns)), len(projection["current_graph"]["edges"]))
        self.assertEqual(len(root.findall(".//s:g[@class='junction']", ns)), 1)
        self.assertIn("zero-point", svg)
        self.assertNotIn("<script>", svg)
        self.assertEqual(projection, before)
        self.assertEqual(svg, analysis.render_diagram(projection, "<script>not executable</script>"))

    def test_same_projection_d6_class_has_deterministic_detached_representative(self):
        from research.harness.lab_symmetry import transform_projection
        record, _ = fixture(wires=({"action": "play", "point": [2, 0]},))
        projection = self.analyze(record)["frames"][-1]["projection"]
        first = analysis.canonical_diagram(projection)
        second = analysis.canonical_diagram(transform_projection(projection, 3))
        self.assertEqual(first["key"], second["key"])
        self.assertEqual(first["projection"], second["projection"])
        first["projection"]["stones"].clear()
        self.assertTrue(analysis.canonical_diagram(projection)["projection"]["stones"])

    def test_cell_legend_distinguishes_fences_majority_and_line_area(self):
        from actions import RulesState
        from game_factory import new_game
        from research.harness.lab_symmetry import diagram_projection
        for rules in ("gjerde", "gjerde-go", "gjerde-majority", "line-breath"):
            state = RulesState(new_game(3, rules=rules, experimental=True))
            svg = analysis.render_diagram(diagram_projection(state))
            with self.subTest(rules=rules):
                if rules in ("gjerde", "gjerde-go"):
                    self.assertIn("fenced regions", svg)
                elif rules == "gjerde-majority":
                    self.assertIn("scores one cell", svg)
                else:
                    self.assertIn("Cell outlines do not add score", svg)

    def test_analysis_records_are_immutable_and_do_not_import_agents(self):
        record, _ = fixture()
        result = analysis.analyze_record(record, provenance=provenance(), source_sha256=canonical_hash(record))
        detached = result.to_dict()
        detached["frames"].clear()
        self.assertEqual(len(result.to_dict()["frames"]), 1)
        source = Path(analysis.__file__).read_text()
        self.assertNotIn("choose_lab_decision", source)
        self.assertNotIn("produce_certificate", source)
        self.assertNotIn("check_certificate", source)


if __name__ == "__main__":
    unittest.main()
