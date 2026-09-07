"""Simulated accounting checks; these tests do not run research games."""

from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.harness.lab_budget import (
    BudgetError,
    BudgetIntegrityError,
    MAX_WINDOWS,
    REPOSITORY,
    ReconciliationRequired,
    ResearchBudget,
    SAFETY_FACTOR,
    WINDOW_SECONDS,
    _seal,
    round_robin_blocks,
)


class Clock:
    def __init__(self, now=10_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _competing_start(arguments):
    path, index = arguments
    ledger = ResearchBudget(path, session_id="shared", clock=Clock())
    try:
        ledger.start_job(str(index), kind="proof", workers=2,
                         projected_seconds=1, measurement="frozen pilot")
        return True
    except BudgetError:
        return False


class TestLabBudget(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "ledger.json"
        self.clock = Clock()
        self.budget = ResearchBudget.create(
            self.path, session_id="first", plan_sha256="a" * 64, clock=self.clock
        )

    def start(self, name="a", **kwargs):
        values = {"kind": "proof", "workers": 1, "projected_seconds": 1,
                  "measurement": "test pilot: 1 unit / second"}
        values.update(kwargs)
        return self.budget.start_job(name, **values)

    def test_creation_and_idle_time_do_not_open_or_charge_research_window(self):
        self.clock.advance(100_000)
        status = self.budget.status()
        self.assertEqual(status["windows_opened"], 0)
        self.assertEqual(status["charged_seconds"], 0)
        self.assertEqual(status["total_remaining_seconds"], 129_600)
        self.assertEqual(status["state"]["plan_sha256"], "a" * 64)

    def test_overlapping_jobs_charge_wall_union_not_worker_sum(self):
        self.start(workers=4)
        self.clock.advance(10)
        self.start("b", kind="calibration", workers=4)
        self.clock.advance(5)
        status = self.budget.finish_job("a", outcome="completed", cpu_seconds=45)
        self.assertEqual(status["charged_seconds"], 15)
        self.assertEqual(status["active_workers"], 4)
        self.clock.advance(5)
        status = self.budget.finish_job("b", outcome="failed", cpu_seconds=30)
        self.assertEqual(status["charged_seconds"], 20)
        self.assertEqual(status["cpu_seconds_reported"], 75)
        self.clock.advance(50)
        self.assertEqual(self.budget.status()["charged_seconds"], 20)

    def test_cancelled_and_failed_work_is_charged_with_unknown_cpu_explicit(self):
        for name, outcome in [("a", "cancelled"), ("b", "failed")]:
            self.start(name, kind="research")
            self.clock.advance(7)
            self.budget.finish_job(name, outcome=outcome)
        status = self.budget.status()
        self.assertEqual(status["charged_seconds"], 14)
        self.assertEqual(status["cpu_reports_missing"], 2)
        with self.assertRaisesRegex(BudgetError, "unique"):
            self.start("a")

    def test_projection_includes_safety_and_exact_boundary_fits(self):
        projection = WINDOW_SECONDS / SAFETY_FACTOR
        admitted = self.start(projected_seconds=projection)
        self.assertEqual(admitted["guarded_seconds"], WINDOW_SECONDS)
        self.assertEqual(admitted["deadline"], self.clock.now + WINDOW_SECONDS)
        self.budget.finish_job("a", outcome="completed")
        with self.assertRaisesRegex(BudgetError, "does not fit"):
            self.start("b", projected_seconds=projection + 0.01)
        self.assertEqual(self.budget.status()["active_jobs"], [])

    def test_three_windows_never_multiply_parallel_wall_allowance(self):
        for index in range(MAX_WINDOWS):
            self.start(str(index), workers=8)
            self.clock.advance(WINDOW_SECONDS)
            status = self.budget.finish_job(str(index), outcome="completed")
            self.assertEqual(status["charged_seconds"], (index + 1) * WINDOW_SECONDS)
            with self.assertRaisesRegex(BudgetError, "does not fit"):
                self.start(f"overflow-{index}")
            if index < MAX_WINDOWS - 1:
                self.budget.advance_window()
        self.assertEqual(status["total_remaining_seconds"], 0)
        with self.assertRaisesRegex(BudgetError, "no next"):
            self.budget.advance_window()

    def test_window_boundary_checkpoint_stops_but_cleanup_remains_possible(self):
        self.start()
        self.clock.advance(WINDOW_SECONDS)
        with self.assertRaisesRegex(BudgetError, "exhausted"):
            self.budget.checkpoint()
        self.budget.finish_job("a", outcome="cancelled")
        self.budget.advance_window()
        self.start("b")

    def test_overrun_is_recorded_not_clipped_and_blocks_dependent_work(self):
        self.start()
        self.clock.advance(WINDOW_SECONDS + 8)
        with self.assertRaises(BudgetError):
            self.budget.checkpoint()
        status = self.budget.finish_job("a", outcome="failed")
        self.assertEqual(status["charged_seconds"], WINDOW_SECONDS + 8)
        self.assertTrue(status["overrun"])
        with self.assertRaisesRegex(BudgetError, "overrun"):
            self.budget.advance_window()

    def test_window_cannot_advance_with_active_jobs(self):
        self.start()
        with self.assertRaisesRegex(BudgetError, "stop and reconcile"):
            self.budget.advance_window()
        self.budget.finish_job("a", outcome="completed")
        self.assertEqual(self.budget.advance_window()["windows_opened"], 2)

    def test_early_boundary_forfeits_unused_window_without_inventing_time(self):
        self.start()
        self.clock.advance(7)
        self.budget.finish_job("a", outcome="completed")
        status = self.budget.advance_window()
        self.assertEqual(status["charged_seconds"], 7)
        self.assertEqual(status["forfeited_seconds"], WINDOW_SECONDS - 7)
        self.assertEqual(status["total_remaining_seconds"], 2 * WINDOW_SECONDS)

    def test_restart_charges_downtime_until_explicit_reconciliation(self):
        self.start()
        self.clock.advance(10)
        self.budget.checkpoint()
        restarted = ResearchBudget(self.path, session_id="second", clock=self.clock)
        self.clock.advance(100)
        self.assertTrue(restarted.status()["requires_reconciliation"])
        with self.assertRaises(ReconciliationRequired):
            restarted.start_job("b", kind="proof", workers=1,
                                projected_seconds=1, measurement="pilot")
        with self.assertRaises(BudgetError):
            restarted.reconcile(stopped_job_ids=[], reason="not enough evidence")
        self.clock.advance(5)
        status = restarted.reconcile(stopped_job_ids=["a"], reason="verified old worker stopped")
        self.assertEqual(status["charged_seconds"], 115)
        self.assertFalse(status["requires_reconciliation"])
        self.assertEqual(status["state"]["jobs"]["a"]["outcome"], "reconciled")
        restarted.start_job("b", kind="research", workers=1,
                            projected_seconds=1, measurement="new fixed block")

    def test_same_coordinator_workers_share_session_and_complete_job(self):
        self.start()
        worker = ResearchBudget(self.path, session_id="first", clock=self.clock)
        self.clock.advance(3)
        self.assertEqual(worker.finish_job("a", outcome="completed")["charged_seconds"], 3)
        resumed = ResearchBudget(self.path, session_id="new-lifetime", clock=self.clock)
        self.assertFalse(resumed.status()["requires_reconciliation"])

    def test_checkpoints_and_shared_worker_reloads_leave_exact_final_accounting(self):
        other_clock = Clock()
        other_path = self.path.with_name("uninterrupted.json")
        uninterrupted = ResearchBudget.create(
            other_path, session_id="first", plan_sha256="a" * 64, clock=other_clock
        )
        self.start()
        uninterrupted.start_job("a", kind="proof", workers=1, projected_seconds=1,
                                measurement="test pilot: 1 unit / second")
        for seconds in [3, 5, 11]:
            self.clock.advance(seconds)
            self.budget.checkpoint()
        self.budget = ResearchBudget(self.path, session_id="first", clock=self.clock)
        self.budget.finish_job("a", outcome="completed", cpu_seconds=15)
        other_clock.advance(19)
        uninterrupted.finish_job("a", outcome="completed", cpu_seconds=15)
        self.assertEqual(self.path.read_bytes(), other_path.read_bytes())

    def test_separate_processes_atomically_enforce_worker_ceiling(self):
        self.budget = ResearchBudget(self.path, session_id="shared", clock=self.clock)
        with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
            results = list(pool.map(_competing_start, [(str(self.path), i) for i in range(12)]))
        self.assertEqual(sum(results), 4)
        self.assertEqual(self.budget.status()["active_workers"], 8)

    def test_failed_request_does_not_erase_active_elapsed_time(self):
        self.start(workers=8)
        self.clock.advance(12)
        with self.assertRaisesRegex(BudgetError, "ceiling"):
            self.start("b")
        self.assertEqual(self.budget.status()["charged_seconds"], 12)

    def test_atomic_replace_failure_keeps_prior_file_and_recovers_elapsed(self):
        self.start()
        before = self.path.read_bytes()
        self.clock.advance(9)
        with patch("research.harness.lab_budget.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.budget.checkpoint()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(set(self.path.parent.iterdir()), {self.path, self.path.with_suffix(".json.lock")})
        self.assertEqual(self.budget.status()["charged_seconds"], 9)

    def test_tampering_truncation_and_changed_limits_fail_closed(self):
        before = self.path.read_text()
        for value in ["{", '{"payload": {}}']:
            self.path.write_text(value)
            with self.assertRaises(BudgetIntegrityError):
                self.budget.status()
        envelope = json.loads(before)
        envelope["payload"]["last_accounted_at"] += 1
        self.path.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(BudgetIntegrityError, "checksum"):
            self.budget.status()
        envelope["payload"]["limits"]["windows"] = 4
        self.path.write_text(json.dumps(_seal(envelope["payload"])))
        with self.assertRaisesRegex(BudgetIntegrityError, "frozen limits"):
            self.budget.status()

    def test_time_backwards_never_rewrites_ledger(self):
        self.start()
        before = self.path.read_bytes()
        self.clock.advance(-1)
        with self.assertRaisesRegex(BudgetIntegrityError, "backwards"):
            self.budget.status()
        self.assertEqual(self.path.read_bytes(), before)

    def test_resealed_but_inconsistent_accounting_is_rejected(self):
        self.start()
        self.clock.advance(4)
        self.budget.finish_job("a", outcome="completed")
        state = json.loads(self.path.read_text())["payload"]
        state["windows"][0]["charged_seconds"] = 0
        self.path.write_text(json.dumps(_seal(state)))
        with self.assertRaisesRegex(BudgetIntegrityError, "union"):
            self.budget.status()

    def test_invalid_inputs_and_existing_ledger_cannot_reset_budget(self):
        with self.assertRaisesRegex(BudgetError, "reset"):
            ResearchBudget.create(self.path, session_id="other", plan_sha256="a" * 64)
        with self.assertRaisesRegex(BudgetError, "outside"):
            ResearchBudget(REPOSITORY / "ledger.json", session_id="bad")
        for kwargs in [{"workers": True}, {"workers": 9}, {"projected_seconds": float("nan")},
                       {"projected_seconds": 0}, {"measurement": ""}, {"kind": "live-game"}]:
            with self.assertRaises(BudgetError):
                self.start(**kwargs)
        self.assertEqual(self.budget.status()["windows_opened"], 0)

    def test_status_snapshot_cannot_mutate_persisted_ledger(self):
        self.start()
        status = self.budget.status()
        status["state"]["jobs"]["a"]["workers"] = 200
        self.assertEqual(self.budget.status()["active_workers"], 1)

    def test_round_robin_is_registry_ordered_balanced_and_resume_stable(self):
        registry = ["old", "new", "static"]
        cells = {"new": ["n1", "n2"], "static": [], "old": ["o1", "o2", "o3"]}
        expected = [("old", "o1"), ("new", "n1"), ("old", "o2"), ("new", "n2"), ("old", "o3")]
        actual = round_robin_blocks(registry, cells)
        self.assertEqual(actual, expected)
        self.assertEqual(actual[:2] + round_robin_blocks(registry, cells)[2:], expected)
        self.assertEqual(round_robin_blocks([], {}), [])
        with self.assertRaises(BudgetError):
            round_robin_blocks(["old", "old"], {"old": []})
        with self.assertRaises(BudgetError):
            round_robin_blocks(registry, {"old": []})


if __name__ == "__main__":
    unittest.main()
