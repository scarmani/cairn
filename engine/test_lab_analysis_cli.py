"""Offline report presentation/publication tests, not research measurements."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lab_evidence import empty_card, entry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.harness.lab_analysis_cli import (  # noqa: E402
    _publish_text, artifact_manifest, exclusive_output, render_card, render_heatmap,
    render_html, generate_report,
)


class TestLabAnalysisCLI(unittest.TestCase):
    def test_card_missingness_and_no_mutation(self):
        card = empty_card("junction-y", "0.1")
        before = deepcopy(card)
        result = render_card(card)
        self.assertEqual(card, before)
        self.assertIn("No comparative qualification", result)
        self.assertIn("MCTS: unmeasured", result)
        self.assertIn("Human readability, beauty", result)
        self.assertEqual(result.count("<details>"), 7)
        self.assertNotIn("rating: 0", result)

    def test_data_is_escaped_not_executable(self):
        card = empty_card('x\"><img src=x onerror=alert(1)>', "0.1")
        card["dimensions"]["correctness"] = entry(
            "provisional", value="</div><script>alert(1)</script>",
            provenance=["<svg onload=alert(2)>"], uncertainty='"<&', scope="test-only")
        rendered = render_card(card)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("<svg onload", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_rejects_invalid_evidence(self):
        card = empty_card("junction-y", "0.1")
        card["comparative_headline_allowed"] = True
        with self.assertRaises(ValueError):
            render_card(card)

    def test_text_publication_immutable_and_no_temporary_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            _publish_text(path, "héllo")
            self.assertEqual(path.read_text(), "héllo")
            with self.assertRaises(FileExistsError):
                _publish_text(path, "overwrite")
            self.assertEqual(path.read_text(), "héllo")
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["report.html"])

    def test_output_is_exclusive_external_and_symlink_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            # macOS tempfile paths may begin with the system /var symlink.
            root = Path(tmp).resolve()
            target = exclusive_output(root / "a")
            self.assertTrue(target.is_dir())
            with self.assertRaises(FileExistsError):
                exclusive_output(target)
            (root / "link").symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                exclusive_output(root / "link" / "other")
        with self.assertRaises(ValueError):
            exclusive_output(ROOT / "never-create-report-here")
        self.assertFalse((ROOT / "never-create-report-here").exists())

    def test_manifest_is_deterministic_and_paths_are_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _publish_text(root / "a.html", "same")
            report = artifact_manifest(root, metadata={"claim": "engineering-only"})
            self.assertEqual(report, artifact_manifest(root, metadata={"claim": "engineering-only"}))
            self.assertEqual(report["files"], [{"path": "a.html", "bytes": 4,
                                               "sha256": hashlib.sha256(b"same").hexdigest()}])
            self.assertNotIn(tmp, json.dumps(report))
            (root / "link").symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                artifact_manifest(root, metadata={})

    def test_raw_heatmap_does_not_rotate_or_hide_missing_observations(self):
        row = {"base_projection": {"current_graph": {
            "points": [[-2, 0], [2, 0]], "edges": [[[-2, 0], [2, 0]]]}},
            "heatmaps": [{"kind": "construction", "point": [0, 0], "seat": "S1", "color": "B", "count": 2},
                         {"kind": "construction", "point": [0, 0], "seat": "S2", "color": "W", "count": 1}]}
        before = deepcopy(row)
        svg = render_heatmap(row, "construction")
        self.assertIn('cx="200.000" cy="200.000"', svg)
        self.assertIn("3 executed actions", svg)
        self.assertIn("scripted coverage, both colors", svg)
        self.assertEqual(row, before)
        self.assertIn("No event in these scripts", render_heatmap(row, "enemy-contact"))
        row["heatmaps"][0]["count"] = True
        with self.assertRaises(ValueError):
            render_heatmap(row, "construction")

    def test_report_text_state_and_human_claim_firewall(self):
        bundle = {"cards": [empty_card("junction-y", "0.1")],
                  "record_selection": {"selected": [], "excluded": [], "audited": 0},
                  "source": {"commit": "a" * 40}, "bundle_hash": "b" * 64}
        analysis = {"distinct_traces": 0, "atlas": [], "strata": [], "analysis_hash": "c" * 64}
        html = render_html(bundle, analysis)
        self.assertIn("0 final UI scripts", html)
        self.assertIn("render_game_to_text", html)
        self.assertIn("offline-evidence-report", html)
        self.assertIn(".evidence-card[data-ruleset]", html)
        self.assertIn('"admitted_games": 0', html)
        bundle["cards"][0]["human_observations"]["beauty"] = entry(
            "observed", value=5, sample_size=1, provenance=["fictional"],
            source_kind="human-observation", uncertainty="test input")
        with self.assertRaises(ValueError):
            render_html(bundle, analysis)

    def test_publication_pipeline_is_byte_stable_across_output_roots(self):
        # Isolate publication from file authentication, tested by the bundle suite.
        # Empty records produce no new actions; no unavailable external data needed.
        from research.harness import lab_evidence_bundle as evidence
        bundle = {"cards": [empty_card("junction-y", "0.1")],
                  "record_selection": {"selected": [], "excluded": [], "audited": 0},
                  "source": {"commit": "a" * 40}, "bundle_hash": "b" * 64}
        inputs = SimpleNamespace(to_dict=lambda: {"selected_records": []})
        wrapped = SimpleNamespace(to_dict=lambda: deepcopy(bundle))
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(evidence, "load_evidence_inputs", return_value=inputs), \
                patch.object(evidence, "build_evidence_bundle", return_value=wrapped), \
                patch.object(evidence, "validate_evidence_bundle", side_effect=lambda value: value), \
                patch.object(evidence, "render_evidence_markdown", return_value="Synthetic publication test\n"):
            root = Path(tmp).resolve()
            first = generate_report(root, root / "one", "a" * 40)
            second = generate_report(root, root / "two", "a" * 40)
            self.assertEqual(first, second)
            files = sorted(p.relative_to(root / "one") for p in (root / "one").rglob("*") if p.is_file())
            self.assertEqual(len(files), 5)
            for name in files:
                self.assertEqual((root / "one" / name).read_bytes(), (root / "two" / name).read_bytes())
            with self.assertRaises(FileExistsError):
                generate_report(root, root / "one", "a" * 40)

    def test_input_failure_creates_no_output(self):
        from research.harness import lab_evidence_bundle as evidence
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(evidence, "load_evidence_inputs", side_effect=ValueError("tampered")):
            target = Path(tmp).resolve() / "never-created"
            with self.assertRaisesRegex(ValueError, "tampered"):
                generate_report(tmp, target, "a" * 40)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
