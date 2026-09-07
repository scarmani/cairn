"""Authored-table engineering only; no complete corpus compilation or proof."""

from collections import Counter
import unittest

from research.harness.lab_corpus_candidates import (
    LINE_RULES, LINE_POINTS, VERTEX_POINTS, PRODUCTION_RULESETS, authored_candidates, definitions_hash,
)
from research.harness.lab_origin import create_origin, verify_origin
from research.harness.lab_terminal_cert import canonical_hash


class TestLabCorpusCandidates(unittest.TestCase):
    def test_fixed_complete_detached_table_without_replay(self):
        definitions = authored_candidates()
        self.assertEqual(len(definitions), 512)
        self.assertEqual(len({row["id"] for row in definitions}), 512)
        counts = Counter((row["configuration"]["rules_id"], row["configuration"]["n"]) for row in definitions)
        self.assertEqual(set(counts), {(rules, n) for rules in PRODUCTION_RULESETS for n in (3, 4)})
        self.assertEqual(set(counts.values()), {16})
        self.assertEqual(definitions_hash(), canonical_hash(definitions))
        definitions[0]["actions"][0]["point"][0] = 99
        self.assertNotEqual(definitions_hash(), canonical_hash(definitions))
        self.assertLessEqual(max(len(row["actions"]) for row in definitions), 11)

    def test_complete_orientation_wires_and_original_openings(self):
        seen = {}
        for row in authored_candidates():
            rules = row["configuration"]["rules_id"]
            points = LINE_POINTS if rules in LINE_RULES else VERTEX_POINTS
            index = 4 if row["template_id"] in ("05-rim-pair", "07-distributed", "10-resumed") else 0
            self.assertEqual(row["actions"][0], {"action": "play", "point": list(points[index])})
            for action in row["actions"]:
                if action["action"] in ("construct", "plant"):
                    self.assertEqual(set(action), {"action", "face", "orientation"})
                    seen.setdefault(rules, set()).add(action["orientation"])
        self.assertEqual(seen, {"junction-y": {0, 1}, "junction-six": {0},
                               "junction-planted": {0, 1}, "junction-passage": {0, 1, 2}})

    def test_selected_preexisting_mechanical_chains_are_transcribed_exactly(self):
        wanted = {"junction-y-n3-15-hub-reopened", "breath-run-n3-14-rescue-open",
                  "breath-run-n3-15-rescue-finished", "junction-passage-n3-14-passage-two"}
        for row in authored_candidates():
            if row["id"] in wanted:
                with self.subTest(id=row["id"]):
                    root = verify_origin(create_origin(row["configuration"], row["actions"])).production_root
                    if row["id"].endswith("hub-reopened"):
                        self.assertEqual(root.game.state[(0, 0)], ())
                        self.assertEqual(root.game.topology, ((0, 0, 0),))
                    if row["id"].endswith("rescue-open"):
                        self.assertTrue(root.game.extension_only_turn)
                    if row["id"].endswith("rescue-finished"):
                        self.assertFalse(root.game.extension_only_turn)
        self.assertEqual(len(wanted), 4)
