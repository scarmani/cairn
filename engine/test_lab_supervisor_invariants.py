"""Independent disposable process/budget checks; never run game research."""

import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from research.harness.lab_budget import ResearchBudget
from research.harness.lab_fixed_tasks import FixedTaskManifest
from research.harness import lab_supervisor as supervisor
from research.harness.lab_supervisor import TrustedWorker, run_supervised


def synthetic_callback(task):
    """Trusted test callback: finite data or an intentional synthetic fault."""
    payload = task["payload"]
    mode = payload.get("mode", "ordinary")
    if mode == "mutate":
        task["payload"]["number"] = 900
        return {"answer": 900}
    if mode == "raise":
        raise RuntimeError("independent synthetic failure; not a game result")
    if mode == "partial-output":
        # Bypass redirected Python stdout deliberately to simulate a broken
        # worker protocol write. The supervisor must not block on readline.
        os.write(1, b'{"event":"result","nonce":')
    if mode in ("wait", "partial-output"):
        # Deliberately uncooperative with cooperative cancellation; the process
        # supervisor, not this function, must interrupt the bounded test.
        while True:
            time.sleep(0.02)
    time.sleep(payload.get("delay", 0))
    return {"answer": payload["number"] ** 2, "synthetic": True}


class TestLabSupervisorInvariants(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = {"independent-test-callback": Path(__file__).resolve()}
        self.worker = TrustedWorker(module="engine.test_lab_supervisor_invariants",
                                    function="synthetic_callback", sources=self.sources)

    def manifest(self, payloads):
        return FixedTaskManifest.create(
            source={"commit": "86392fa6d4410286ff7a5da0f7c7f3af5d021b9d",
                    "hashes": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for name, path in self.sources.items()}},
            configuration={"synthetic": True, "real_game_proof": False},
            tasks=[{"id": f"fixed-{index}", "payload": payload}
                   for index, payload in enumerate(payloads)],
        )

    def budget(self, name):
        return ResearchBudget.create(self.root / f"{name}-budget.json", session_id=name,
                                     plan_sha256="0" * 64)

    def run_block(self, manifest, name, *, workers=1, **options):
        budget = self.budget(name)
        options = {"task_timeout": 2, "cohort_timeout": 8, "reap_timeout": 0.1} | options
        result = run_supervised(
            manifest, self.worker, output_dir=self.root / name, budget=budget,
            job_id=name, kind="calibration", projected_seconds=options["cohort_timeout"],
            measurement="Synthetic engineering hard reservation; no game-throughput claim.",
            workers=workers, **options,
        )
        return result, budget.status()

    def test_identical_canonical_results_across_one_two_eight_workers(self):
        manifest = self.manifest([{"number": i, "delay": 0.12 if i == 0 else 0.005}
                                  for i in range(8)])
        hashes = []
        for workers in (1, 2, 8):
            with self.subTest(workers=workers):
                # Correctness equivalence, not a process-startup speed gate.
                # Eight workers reserve4.85s cleanup; the default8s cohort left
                # only3.15s for hosted-runner imports, protocol and result handling.
                result, accounting = self.run_block(manifest, f"workers-{workers}", workers=workers,
                                                    task_timeout=10, cohort_timeout=30)
                hashes.append(result.canonical_results_hash)
                self.assertEqual(result.to_dict()["status"], "complete", result.to_dict())
                self.assertEqual(result.to_dict()["remaining_ids"], [])
                self.assertEqual(len(result.to_dict()["completed"]), 8)
                self.assertFalse(accounting["active_jobs"])
                self.assertEqual(accounting["active_workers"], 0)
                self.assertGreater(accounting["charged_seconds"], 0)
                self.assertFalse(accounting["overrun"])
        self.assertEqual(len(set(hashes)), 1)

    def test_cancel_before_dispatch_leaves_no_active_budget_job(self):
        manifest = self.manifest([{"number": 7}])
        result, accounting = self.run_block(manifest, "cancel-entry", cancelled=lambda: True)
        self.assertEqual(result.to_dict()["status"], "cancelled")
        self.assertEqual(result.to_dict()["completed"], [])
        self.assertFalse(accounting["active_jobs"])
        self.assertEqual(accounting["active_workers"], 0)
        self.assertIsInstance(result.canonical_results_hash, str)

    def test_failed_callback_and_input_mutation_never_leave_active_workers(self):
        for mode in ("raise", "mutate"):
            with self.subTest(mode=mode):
                manifest = self.manifest([{"number": 7, "mode": mode}])
                result, accounting = self.run_block(manifest, f"fault-{mode}")
                self.assertEqual(result.to_dict()["status"], "blocked")
                self.assertEqual(result.to_dict()["completed"], [])
                self.assertFalse(accounting["active_jobs"])
                self.assertEqual(accounting["active_workers"], 0)
                self.assertGreater(accounting["charged_seconds"], 0)
                self.assertIsInstance(result.to_dict(), dict)

    def test_partial_protocol_output_cannot_disable_worker_timeout(self):
        manifest = self.manifest([{"number": 7, "mode": "partial-output"}])
        started = time.monotonic()
        result, accounting = self.run_block(manifest, "partial-protocol", task_timeout=0.3)
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(result.to_dict()["status"], "timeout")
        self.assertEqual(result.to_dict()["completed"], [])
        self.assertFalse(accounting["active_jobs"])

    def test_nonreading_worker_cannot_block_large_outbound_request(self):
        manifest = self.manifest([{"number": 7, "padding": "x" * (1024 * 1024)}])
        real_popen = subprocess.Popen

        def nonreader(command, **kwargs):
            if command == [sys.executable, "-m", "research.harness.lab_worker"]:
                command = [sys.executable, "-c", "import time\nwhile True: time.sleep(.01)"]
            return real_popen(command, **kwargs)

        started = time.monotonic()
        with patch("research.harness.lab_supervisor.subprocess.Popen", side_effect=nonreader):
            result, accounting = self.run_block(manifest, "nonreader", task_timeout=0.3)
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(result.to_dict()["status"], "timeout")
        self.assertEqual(result.to_dict()["completed"], [])
        self.assertFalse(accounting["active_jobs"])

    def test_runtime_source_tamper_rejects_before_budget_or_callback(self):
        manifest = self.manifest([{"number": 7}])
        altered = manifest.to_dict()
        altered["source"]["hashes"]["independent-test-callback"] = "0" * 64
        # Build a fully self-consistent declaration: comparing hashes in JSON
        # with each other is insufficient; authoritative bytes must be checked.
        forged = FixedTaskManifest.create(source=altered["source"],
                                          configuration=altered["configuration"],
                                          tasks=[{"id": row["id"], "payload": row["payload"]}
                                                 for row in altered["tasks"]])
        budget = self.budget("source-tamper")
        with self.assertRaises(ValueError):
            run_supervised(forged, self.worker, output_dir=self.root / "source-tamper",
                           budget=budget, job_id="source-tamper", kind="calibration",
                           projected_seconds=4, measurement="Synthetic invalid-source test.",
                           task_timeout=2, cohort_timeout=4)
        self.assertEqual(budget.status()["windows_opened"], 0)

    def test_invalid_worker_allocations_cannot_open_a_window(self):
        manifest = self.manifest([{"number": 7}])
        for index, workers in enumerate((0, 9, True, 1.0)):
            budget = self.budget(f"bad-workers-{index}")
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                run_supervised(manifest, self.worker, output_dir=self.root / f"bad-{index}",
                               budget=budget, job_id=f"bad-{index}", kind="calibration",
                               projected_seconds=4, measurement="Synthetic invalid allocation.",
                               workers=workers, task_timeout=2, cohort_timeout=4)
            self.assertEqual(budget.status()["windows_opened"], 0)

    def test_recorded_callback_failure_never_automatically_retries(self):
        manifest = self.manifest([{"number": 7, "mode": "raise"}])
        budget = self.budget("no-retry")
        options = {"output_dir": self.root / "no-retry", "budget": budget,
                   "kind": "calibration", "projected_seconds": 4,
                   "measurement": "Synthetic callback-fault persistence test.",
                   "task_timeout": 2, "cohort_timeout": 4}
        failed = run_supervised(manifest, self.worker, job_id="first", **options)
        jobs = budget.status()["state"]["jobs"]
        resumed = run_supervised(manifest, self.worker, job_id="do-not-start", **options)
        self.assertEqual(failed.to_dict()["status"], "blocked")
        self.assertEqual(resumed.to_dict()["status"], "blocked")
        self.assertEqual(resumed.to_dict()["completed"], [])
        self.assertEqual(budget.status()["state"]["jobs"], jobs)

    def test_final_budget_failure_is_not_masked_by_complete_payloads(self):
        manifest = self.manifest([{"number": 7}])
        budget = self.budget("final-overrun")
        options = {"output_dir": self.root / "final-overrun", "budget": budget,
                   "kind": "calibration", "projected_seconds": 4,
                   "measurement": "Synthetic final-accounting failure injection.",
                   "task_timeout": 2, "cohort_timeout": 4}
        original_finish = budget.finish_job

        def injected_overrun(*args, **kwargs):
            accounting = original_finish(*args, **kwargs)
            self.assertFalse(accounting["active_jobs"])
            return accounting | {"overrun": True}

        with patch.object(budget, "finish_job", side_effect=injected_overrun):
            result = run_supervised(manifest, self.worker, job_id="first", **options).to_dict()
        self.assertEqual(len(result["completed"]), 1)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["complete"])
        self.assertEqual(result["reason"], "integrity-failure")
        self.assertFalse(budget.status()["active_jobs"])
        jobs = budget.status()["state"]["jobs"]
        resumed = run_supervised(manifest, self.worker, job_id="do-not-retry", **options).to_dict()
        self.assertEqual(resumed["status"], "blocked")
        self.assertFalse(resumed["complete"])
        self.assertEqual(resumed["completed"], result["completed"])
        self.assertEqual(budget.status()["state"]["jobs"], jobs)

    def test_explicit_cap_overrun_after_cleanup_is_not_a_completed_cohort(self):
        manifest = self.manifest([{"number": 7}])
        original_cleanup = supervisor._cleanup
        original_clock = time.monotonic
        jump = [0]

        def controlled_clock():
            return original_clock() + jump[0]

        def delayed_cleanup(items, *args):
            original_cleanup(items, *args)
            if items:
                # Simulate an OS cleanup stall without actually sleeping or
                # changing the disposable ledger's independent wall clock.
                jump[0] += 20

        with patch.object(supervisor, "_cleanup", side_effect=delayed_cleanup), \
                patch.object(supervisor.time, "monotonic", side_effect=controlled_clock):
            result, accounting = self.run_block(manifest, "explicit-cap")
        result = result.to_dict()
        self.assertEqual(len(result["completed"]), 1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "integrity-failure")
        self.assertEqual(result["cohorts"][0]["status"], "failed")
        self.assertIn("deadline overrun", result["cohorts"][0]["error"]["message"])
        self.assertFalse(accounting["active_jobs"])


if __name__ == "__main__":
    unittest.main()
