"""Real short synthetic processes with disposable ledgers; no research jobs."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from research.harness.lab_budget import ResearchBudget
from research.harness.lab_fixed_tasks import FixedTaskManifest
from research.harness.lab_supervisor import (
    GROUP_SNAPSHOT_TIMEOUT, Reconciliation, SupervisorIntegrityError, TrustedWorker,
    cleanup_reservation, load_supervisor_checkpoint, run_supervised,
)
from research.harness.lab_terminal_cert import canonical_hash, canonical_json


class TestLabSupervisor(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.worker = TrustedWorker("lab_supervisor_test_helpers", "synthetic_callback",
                                    {"callback": Path(__file__).with_name("lab_supervisor_test_helpers.py")})
        self.ledger = ResearchBudget.create(self.root / "budget.json", session_id="synthetic-owner", plan_sha256="a" * 64)
        self.counter = 0

    def manifest(self, payloads):
        return FixedTaskManifest.create(source={"commit": "b" * 40, "hashes": self.worker.source_hashes()},
            configuration={"test_only": True}, tasks=[{"id": f"task-{index}", "payload": payload} for index, payload in enumerate(payloads)])

    def run_tasks(self, manifest, **kwargs):
        self.counter += 1
        values = dict(output_dir=self.root / "output", budget=self.ledger, job_id=f"synthetic-{self.counter}",
                      kind="calibration", projected_seconds=2, measurement="synthetic engineering hard reservation; not game throughput",
                      workers=1, task_timeout=1, cohort_timeout=10, term_grace=.02, kill_grace=.02, reap_timeout=.3)
        values.update(kwargs)
        return run_supervised(manifest, self.worker, **values)

    def assert_stopped(self, report):
        self.assertTrue(all(a["cleanup_confirmed"] for a in report["attempts"]))
        self.assertTrue(all(c["ledger_closed"] for c in report["cohorts"]))
        self.assertEqual(self.ledger.status()["active_jobs"], [])
        for attempt in report["attempts"]:
            if attempt["pid"]:
                with self.assertRaises(ProcessLookupError):
                    os.kill(attempt["pid"], 0)

    def test_one_two_eight_workers_have_identical_canonical_results(self):
        manifest = self.manifest([{"value": i, "delay": (7 - i) * .004} for i in range(8)])
        reports = [self.run_tasks(manifest, workers=count, output_dir=self.root / f"workers-{count}").to_dict()
                   for count in (1, 2, 8)]
        self.assertEqual(len({r["canonical_results_hash"] for r in reports}), 1)
        for result in reports:
            self.assertTrue(result["complete"])
            self.assertEqual([row["task_id"] for row in result["completed"]], [f"task-{i}" for i in range(8)])
            self.assertTrue(all(a["cpu_seconds"] is not None for a in result["attempts"]))
            self.assert_stopped(result)
        self.assertEqual(self.ledger.status()["cpu_reports_missing"], 3)

    def test_out_of_order_completions_survive_explicit_cancel_resume(self):
        marker = self.root / "running.pid"
        manifest = self.manifest([{"value": 0, "delay": .2, "pid_file": str(marker)}, {"value": 1}, {"value": 2}])
        def cancel():
            checkpoint = self.root / "output" / "supervisor-checkpoint.json"
            return checkpoint.exists() and bool(json.loads(checkpoint.read_text())["payload"]["completed"])
        first = self.run_tasks(manifest, workers=2, cancelled=cancel).to_dict()
        self.assertEqual(first["status"], "cancelled")
        self.assertEqual(first["completed"][0]["task_id"], "task-1")
        self.assert_stopped(first)
        self.assertEqual(self.run_tasks(manifest).to_dict()["reason"], "reconciliation-required")
        pending = tuple(a["nonce"] for a in first["attempts"] if a["status"] != "completed")
        receipt = Reconciliation(pending, (first["cohorts"][0]["id"],), "Synthetic stopped workers confirmed")
        final = self.run_tasks(manifest, reconcile=receipt).to_dict()
        self.assertTrue(final["complete"])
        self.assertEqual(sum(a["task_id"] == "task-1" for a in final["attempts"]), 1)
        self.assertEqual(final["attempts"][0]["status"], "cancelled")
        self.assert_stopped(final)

    def test_uncooperative_worker_and_same_group_descendant_are_killed_and_reaped(self):
        child_file = self.root / "child.pid"
        manifest = self.manifest([{"mode": "descendant", "child_file": str(child_file)}])
        result = self.run_tasks(manifest, task_timeout=.3).to_dict()
        self.assertEqual(result["status"], "timeout")
        self.assertFalse(result["complete"])
        self.assertEqual(result["completed"], [])
        self.assert_stopped(result)
        child = int(child_file.read_text())
        expires = time.monotonic() + 1
        while time.monotonic() < expires:
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(.01)
        else:
            self.fail("owned same-group child remained after cleanup")
        self.assertGreater(self.ledger.status()["charged_seconds"], .2)

    def test_worker_faults_never_score_or_retry(self):
        for mode in ("error", "mutate", "nan", "exit"):
            with self.subTest(mode=mode):
                manifest = self.manifest([{"mode": mode}])
                output = self.root / mode
                result = self.run_tasks(manifest, output_dir=output).to_dict()
                self.assertFalse(result["complete"])
                self.assertEqual(result["completed"], [])
                self.assertEqual(result["status"], "blocked")
                self.assert_stopped(result)
                again = self.run_tasks(manifest, output_dir=output).to_dict()
                self.assertEqual(again["attempts"], result["attempts"])

    def test_source_mismatch_and_manifest_tamper_prevent_launch(self):
        manifest = self.manifest([{"value": 1}])
        source = self.root / "declared.txt"
        source.write_text("before")
        self.worker = TrustedWorker(self.worker.module, self.worker.function,
                                    {"callback": Path(__file__).with_name("lab_supervisor_test_helpers.py"), "data": source})
        manifest = self.manifest([{"value": 1}])
        source.write_text("after")
        with self.assertRaisesRegex(SupervisorIntegrityError, "source"):
            self.run_tasks(manifest)
        self.assertEqual(self.ledger.status()["state"]["jobs"], {})
        source.write_text("before")
        self.run_tasks(manifest)
        checkpoint = self.root / "output" / "supervisor-checkpoint.json"
        envelope = json.loads(checkpoint.read_text())
        envelope["payload"]["completed"][0]["result"]["value"] = 99
        envelope["sha256"] = canonical_hash(envelope["payload"])
        checkpoint.write_text(canonical_json(envelope))
        with self.assertRaises(SupervisorIntegrityError):
            self.run_tasks(manifest)

    def test_source_change_or_control_exception_cleans_before_ledger_finish(self):
        source = self.root / "dependency.txt"
        source.write_text("original")
        self.worker = TrustedWorker(self.worker.module, self.worker.function,
                                    {"callback": Path(__file__).with_name("lab_supervisor_test_helpers.py"), "dependency": source})
        manifest = self.manifest([{"mode": "source", "source_file": str(source)}])
        result = self.run_tasks(manifest).to_dict()
        self.assertEqual(result["reason"], "integrity-failure")
        self.assertFalse(result["complete"])
        self.assert_stopped(result)
        source.write_text("original")
        marker = self.root / "started.pid"
        manifest = self.manifest([{"mode": "hang", "pid_file": str(marker)}])
        def broken_control():
            if marker.exists():
                raise RuntimeError("synthetic coordinator control fault")
            return False
        result = self.run_tasks(manifest, output_dir=self.root / "control", cancelled=broken_control).to_dict()
        self.assertEqual(result["status"], "blocked")
        self.assert_stopped(result)

    def test_invalid_workers_projection_and_cleanup_cap_never_launch(self):
        manifest = self.manifest([{}])
        for kwargs in ({"workers": 0}, {"workers": 9}, {"workers": True}, {"projected_seconds": -1},
                       {"projected_seconds": 200000}, {"cohort_timeout": .01}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.run_tasks(manifest, **kwargs)
        self.assertEqual(self.ledger.status()["state"]["jobs"], {})

    def test_selector_failure_closes_zero_worker_reservation_and_stays_failed(self):
        manifest = self.manifest([{}])
        with patch("research.harness.lab_supervisor.selectors.DefaultSelector", side_effect=RuntimeError("selector fault")):
            result = self.run_tasks(manifest).to_dict()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["attempts"], [])
        self.assert_stopped(result)
        self.assertEqual(self.run_tasks(manifest).to_dict()["status"], "blocked")

    def test_detached_results_and_read_only_checkpoint(self):
        manifest = self.manifest([{"value": 8}])
        result = self.run_tasks(manifest)
        original = result.to_dict()
        mutated = result.to_dict()
        mutated["completed"][0]["result"]["value"] = -1
        loaded = load_supervisor_checkpoint(manifest, self.worker, self.root / "output")
        loaded["completed"].clear()
        self.assertEqual(result.to_dict(), original)
        self.assertEqual(load_supervisor_checkpoint(manifest, self.worker, self.root / "output")["completed"], original["completed"])

    def test_cleanup_reservation_covers_each_serial_exit_and_snapshot(self):
        for workers in (1, 2, 8):
            expected = workers * (.02 + .03 + .04 + 2 * GROUP_SNAPSHOT_TIMEOUT) + .05
            self.assertEqual(cleanup_reservation(workers, .02, .03, .04), expected)
        manifest = self.manifest([{}])
        with self.assertRaisesRegex(ValueError, "reserve"):
            self.run_tasks(manifest, workers=8, cohort_timeout=cleanup_reservation(8, .02, .02, .3))
        self.assertEqual(self.ledger.status()["state"]["jobs"], {})

    def test_completed_checkpoint_rejects_impossible_phases_and_nested_types(self):
        manifest = self.manifest([{}])
        self.run_tasks(manifest)
        checkpoint = self.root / "output" / "supervisor-checkpoint.json"
        original = json.loads(checkpoint.read_text())
        changes = [
            ("attempts", "pid", None), ("attempts", "started_at", None),
            ("attempts", "cpu_seconds", None), ("attempts", "task_id", []),
            ("attempts", "cohort_id", {}), ("attempts", "status", []),
            ("cohorts", "ended_at", None), ("cohorts", "charged_after", None),
            ("cohorts", "status", []), ("cohorts", "ledger_closed", False),
        ]
        for collection, field, value in changes:
            with self.subTest(collection=collection, field=field):
                altered = deepcopy(original)
                altered["payload"][collection][0][field] = value
                if field == "pid":
                    altered["payload"][collection][0]["pgid"] = None
                altered["sha256"] = canonical_hash(altered["payload"])
                checkpoint.write_text(canonical_json(altered))
                with self.assertRaises(SupervisorIntegrityError):
                    load_supervisor_checkpoint(manifest, self.worker, self.root / "output")
        checkpoint.write_text(canonical_json(original))

    def test_framework_loaded_bytes_cannot_be_relabelled_by_new_manifest(self):
        manifest = self.manifest([{}])
        from research.harness import lab_supervisor
        actual = lab_supervisor._digest
        def altered(path):
            if Path(path).name == "lab_fixed_tasks.py":
                return "f" * 64
            return actual(path)
        with patch.object(lab_supervisor, "_digest", side_effect=altered):
            with self.assertRaisesRegex(SupervisorIntegrityError, "loaded"):
                self.run_tasks(manifest)
        self.assertEqual(self.ledger.status()["windows_opened"], 0)

    def test_zero_attempt_crash_lease_requires_explicit_reconciliation(self):
        manifest = self.manifest([{}])
        initial = self.run_tasks(manifest, cancelled=lambda: True).to_dict()
        self.assertEqual(initial["attempts"], [])
        # Simulate only the persisted zero-attempt crash boundary. No process
        # was ever started; the foreign lease still requires explicit receipt.
        self.ledger.start_job("crash", kind="calibration", workers=1,
                              projected_seconds=1, measurement="Synthetic interrupted reservation")
        checkpoint = self.root / "output" / "supervisor-checkpoint.json"
        envelope = json.loads(checkpoint.read_text())
        cohort = envelope["payload"]["cohorts"][0]
        cohort.update(id="crash", status="active", ledger_closed=False,
                      cleanup_confirmed=False, ended_at=None, charged_after=None)
        envelope["sha256"] = canonical_hash(envelope["payload"])
        checkpoint.write_text(canonical_json(envelope))
        self.ledger = ResearchBudget(self.ledger.path, session_id="synthetic-restarted-owner")
        blocked = self.run_tasks(manifest).to_dict()
        self.assertEqual(blocked["status"], "blocked")
        with self.assertRaisesRegex(SupervisorIntegrityError, "external"):
            self.run_tasks(manifest, reconcile=Reconciliation((), ("crash",), "No synthetic worker started"))
        final = self.run_tasks(manifest, reconcile=Reconciliation((), ("crash",),
                               "Synthetic zero-attempt origin confirms no process started", True)).to_dict()
        self.assertTrue(final["complete"])
        self.assertEqual(len(final["attempts"]), 1)
        self.assertEqual(final["cohorts"][0]["status"], "active")
        self.assertEqual(self.ledger.status()["active_jobs"], [])

    def test_persistence_failure_with_live_worker_cleans_and_retains_negative(self):
        manifest = self.manifest([{"mode": "hang"}])
        from research.harness import lab_supervisor
        original = lab_supervisor._atomic
        failed = False
        def fail_once(path, envelope):
            nonlocal failed
            attempts = envelope["payload"]["attempts"]
            if not failed and any(a["status"] == "running" for a in attempts):
                failed = True
                raise OSError("Synthetic durable-start write failure")
            return original(path, envelope)
        with patch.object(lab_supervisor, "_atomic", side_effect=fail_once):
            result = self.run_tasks(manifest).to_dict()
        self.assertTrue(failed)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["completed"], [])
        self.assert_stopped(result)
        self.assertEqual(self.run_tasks(manifest).to_dict()["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
