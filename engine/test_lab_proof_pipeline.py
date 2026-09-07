"""Synthetic producer/checker/task integration; no real games or research jobs."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.harness.lab_fixed_tasks import FixedTaskManifest, run_fixed_tasks
from research.harness.lab_proof_producer import produce_certificate
from research.harness.lab_terminal_cert import (
    TerminalProvider, action_id, canonical_hash, canonical_json, check_certificate,
)


def synthetic_task(node_limit=30, *, broken=False):
    return {"node_limit": node_limit, "broken": broken,
            "nodes": {
                "root": {"actor": "first", "seats": {"B": "first", "W": "second"},
                         "choices": [{"wire": {"action": "construct", "point": [1, 2], "orientation": 1}, "target": "takeover"},
                                     {"wire": {"action": "construct", "point": [1, 2], "orientation": 0}, "target": "draw"}]},
                "takeover": {"actor": "first", "seats": {"B": "second", "W": "first"},
                             "choices": [{"wire": {"action": "accept"}, "target": "win"}]},
                "win": {"actor": None, "seats": {"B": "second", "W": "first"}, "score": {"B": 0, "W": 2}},
                "draw": {"actor": None, "seats": {"B": "first", "W": "second"}, "score": {"B": 1, "W": 1}},
            }}


def evaluate_synthetic(task):
    """Trusted test callback; independent checking remains separately counted."""
    payload = task["payload"]
    states = {name: dict(deepcopy(row), name=name) for name, row in payload["nodes"].items()}

    def actor(state):
        seat = state["actor"]
        return {"seat": seat, "color": next((color for color, owner in state["seats"].items()
                                              if owner == seat), None)}

    def advance(state, wire):
        if payload["broken"]:
            raise RuntimeError("synthetic provider failure")
        target = next(row["target"] for row in state.get("choices", [])
                      if action_id(row["wire"]) == action_id(wire))
        return deepcopy(states[target])

    provider = TerminalProvider(
        provider_id="synthetic-pipeline-v1", rules_id="synthetic-pipeline", rules_revision="0.1",
        rules_hash="a" * 64, implementation_hash="b" * 64,
        fingerprint=canonical_hash, snapshot=deepcopy,
        metadata=lambda state: {"provenance": {"full_action_replay": False}, "synthetic": True},
        actor=actor, seats=lambda state: deepcopy(state["seats"]),
        accepted=lambda state: "score" in state,
        score=lambda state: deepcopy(state["score"]),
        legal_actions=lambda state: [deepcopy(row["wire"]) for row in state.get("choices", [])],
        transition=advance,
    )
    root = states["root"]
    before = canonical_json(root)
    produced = produce_certificate(root, provider, node_limit=payload["node_limit"])
    checked = check_certificate(produced.certificate, root, provider).to_dict()
    if canonical_json(root) != before:
        raise RuntimeError("root mutated")
    return {"production": produced.canonical_dict(), "verification": checked}


def synthetic_manifest(*, broken=False):
    return FixedTaskManifest.create(
        source={"commit": "b554a82f49076ed6c0abc7700f0067932dbd6a2a", "hashes": {"fixture": "c" * 64}},
        configuration={"synthetic": True, "real_game_proofs": False},
        tasks=[{"id": "complete", "payload": synthetic_task(broken=broken)},
               {"id": "limited", "payload": synthetic_task(1)}],
    )


class TestLabProofPipeline(unittest.TestCase):
    def test_checked_proofs_resume_with_byte_equivalent_semantic_results(self):
        manifest = synthetic_manifest()
        calls = []

        def callback(task):
            calls.append(task["id"])
            return evaluate_synthetic(task)

        with TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "resume.json"
            partial = run_fixed_tasks(manifest, callback, checkpoint_path=checkpoint,
                                     cancelled=lambda: bool(calls))
            self.assertEqual(calls, ["complete"])
            self.assertFalse(partial.to_dict()["complete"])
            resumed = run_fixed_tasks(manifest, callback, checkpoint_path=checkpoint)
            uninterrupted = run_fixed_tasks(manifest, evaluate_synthetic,
                                            checkpoint_path=Path(directory) / "whole.json")
            self.assertEqual(calls, ["complete", "limited"])
            self.assertEqual(resumed.canonical_results_hash, uninterrupted.canonical_results_hash)
            self.assertEqual(canonical_json(resumed.to_dict()["completed"]),
                             canonical_json(uninterrupted.to_dict()["completed"]))

            complete, limited = [row["result"] for row in resumed.to_dict()["completed"]]
            self.assertEqual(complete["production"]["telemetry"]["root_class"], "discriminating")
            self.assertEqual(complete["verification"]["optimal_action_ids"],
                             [action_id({"action": "construct", "point": [1, 2], "orientation": 1})])
            self.assertTrue(limited["verification"]["verified"])
            self.assertFalse(limited["verification"]["complete_optimal_action_set"])
            self.assertEqual(limited["production"]["telemetry"]["reason"], "node-limit")
            for result in (complete, limited):
                self.assertNotIn("timing", result["production"])
                self.assertFalse(result["verification"]["admission_record"])
                self.assertFalse(result["production"]["telemetry"]["admission_record"])
                self.assertEqual(result["production"]["telemetry"]["work"]["terminal_simulation_backups"], 0)
                self.assertEqual(result["verification"]["work"]["terminal_simulation_backups"], 0)
                self.assertFalse(result["production"]["telemetry"]["provenance"]["verified_by_producer"])

    def test_provider_failure_blocks_pipeline_without_scored_result_or_retry(self):
        manifest = synthetic_manifest(broken=True)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "failure.json"
            failed = run_fixed_tasks(manifest, evaluate_synthetic, checkpoint_path=path)
            self.assertEqual(failed.to_dict()["status"], "blocked")
            self.assertEqual(failed.to_dict()["completed"], [])
            retried = run_fixed_tasks(manifest, lambda _: self.fail("failure auto-retried"), checkpoint_path=path)
            self.assertEqual(failed.to_dict(), retried.to_dict())


if __name__ == "__main__":
    unittest.main()
