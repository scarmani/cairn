"""Proof artifact/process integration on a fixed synthetic graph only."""

from dataclasses import replace
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from engine.test_lab_mcts_workers import synthetic_provider
from research.harness.lab_budget import ResearchBudget
from research.harness.lab_fixed_tasks import FixedTaskManifest
from research.harness.lab_research_cli import ARTIFACT_ENV, _run_context
from research.harness.lab_supervisor import Reconciliation, TrustedWorker, run_supervised
from research.harness.lab_terminal_cert import canonical_json

ROOT = Path(__file__).resolve().parents[1]


def synthetic_proof_callback(task):
    """Only synthetic nodes can enter this callback, never an actual game."""
    from research.harness.lab_proof_task import ArtifactStore, execute_paths

    payload = task["payload"]
    if payload.get("delay"):
        time.sleep(payload["delay"])
    first = synthetic_provider()
    second = replace(first, provider_id="second-synthetic-mechanics-0.1",
                     implementation_hash="e" * 64)
    store = ArtifactStore(os.environ[ARTIFACT_ENV])
    result = execute_paths(
        {"node": "root", "history": []}, first,
        independent_root={"node": "root", "history": []}, independent_provider=second,
        store=store, producer_nodes=payload["producer_nodes"], checker_nodes=128,
    )
    store.audit_result(result)
    return result


class TestLabProofJobWorkers(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.sources = {str(path.relative_to(ROOT)): path for path in (
            Path(__file__).resolve(), ROOT / "engine/test_lab_mcts_workers.py",
            ROOT / "research/harness/lab_proof_task.py",
            ROOT / "research/harness/lab_proof_jobs.py",
            ROOT / "research/harness/lab_proof_producer.py",
            ROOT / "research/harness/lab_terminal_cert.py",
        )}
        self.worker = TrustedWorker("engine.test_lab_proof_job_workers", "synthetic_proof_callback", self.sources)

    def manifest(self):
        return FixedTaskManifest.create(
            source={"commit": "7f882f27edd11a7e2192b18f62c911f7de6e2b04",
                    "hashes": {label: hashlib.sha256(path.read_bytes()).hexdigest()
                               for label, path in self.sources.items()}},
            configuration={"synthetic": True, "actual_game_proofs": False},
            tasks=[{"id": f"synthetic-{index}", "payload": {
                "producer_nodes": 32 if index % 2 == 0 else 1,
                "delay": .05 if index == 0 else 0,
            }} for index in range(8)],
        )

    def execute(self, manifest, name, *, workers=1, ledger=None, cancelled=None, reconcile=None):
        from research.harness.lab_proof_task import ArtifactStore

        if ledger is None:
            ledger = ResearchBudget.create(self.path / f"{name}-budget.json",
                                           session_id=name, plan_sha256="0" * 64)
        directory = self.path / name
        store = ArtifactStore(directory / "artifacts")
        with _run_context(store.root):
            result = run_supervised(
                manifest, self.worker, output_dir=directory, budget=ledger,
                job_id=f"{name}-{len(ledger.status()['state']['jobs'])}", kind="proof",
                projected_seconds=40, measurement="Disposable synthetic proof artifact integration, not game throughput",
                workers=workers, task_timeout=15, cohort_timeout=40, cancelled=cancelled,
                reconcile=reconcile, reap_timeout=.1,
            )
        for row in result.to_dict()["completed"]:
            store.audit_result(row["result"])
        status = ledger.status()
        self.assertEqual(status["active_jobs"], [])
        self.assertEqual(status["active_workers"], 0)
        self.assertFalse(status["overrun"])
        return result, ledger, store

    def test_canonical_results_and_proofs_equal_across_one_two_eight_workers(self):
        manifest = self.manifest()
        results, artifacts = [], []
        for workers in (1, 2, 8):
            result, _, store = self.execute(manifest, f"workers-{workers}", workers=workers)
            payload = result.to_dict()
            self.assertTrue(payload["complete"], payload)
            self.assertEqual(len(payload["completed"]), 8)
            self.assertEqual(payload["remaining_ids"], [])
            for row in payload["completed"]:
                self.assertFalse(row["result"]["independently_certified"])
                self.assertFalse(row["result"]["admission_record"])
            results.append(result.canonical_results_hash)
            artifacts.append({str(path.relative_to(store.root)): path.read_bytes()
                              for path in (store.root / "sha256").rglob("*.json")})
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(artifacts[0], artifacts[1])
        self.assertEqual(artifacts[1], artifacts[2])

    def test_cancelled_cohort_requires_explicit_reconciliation_and_resumes_exactly(self):
        manifest = self.manifest()
        first, ledger, _ = self.execute(manifest, "resume", cancelled=lambda: True)
        data = first.to_dict()
        self.assertEqual(data["status"], "cancelled")
        self.assertFalse(data["complete"])
        self.assertEqual(data["completed"], [])
        blocked, _, _ = self.execute(manifest, "resume", ledger=ledger)
        self.assertEqual(blocked.to_dict()["status"], "blocked")
        self.assertEqual(blocked.to_dict()["reason"], "reconciliation-required")
        receipt = Reconciliation(tuple(row["nonce"] for row in data["attempts"]),
                                 tuple(row["id"] for row in data["cohorts"]),
                                 "Synthetic zero-entry cancellation; owned cleanup confirmed")
        resumed, _, _ = self.execute(manifest, "resume", workers=2, ledger=ledger, reconcile=receipt)
        direct, _, _ = self.execute(manifest, "direct", workers=1)
        self.assertTrue(resumed.to_dict()["complete"], resumed.to_dict())
        self.assertEqual(resumed.canonical_results_hash, direct.canonical_results_hash)
        self.assertEqual(canonical_json(resumed.to_dict()["completed"]),
                         canonical_json(direct.to_dict()["completed"]))


if __name__ == "__main__":
    unittest.main()
