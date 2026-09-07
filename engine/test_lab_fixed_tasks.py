"""Synthetic callbacks only; no worker, proof, or research budget jobs."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.harness.lab_fixed_tasks import (
    FixedTaskIntegrityError, FixedTaskManifest, load_checkpoint, run_fixed_tasks,
)
from research.harness.lab_terminal_cert import canonical_hash, canonical_json


class Clock:
    def __init__(self, value=10):
        self.value = value

    def __call__(self):
        return self.value


def manifest(ids=("b", "a", "c")):
    return FixedTaskManifest.create(
        source={"commit": "a" * 40, "hashes": {"synthetic-fixture": "b" * 64}},
        configuration={"policy": "synthetic", "budgets": [1, 2]},
        tasks=[{"id": identifier, "payload": {"number": index}} for index, identifier in enumerate(ids)],
    )


def successful(task):
    return {"answer": task["payload"]["number"] * 2, "not_research": True}


class TestLabFixedTasks(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "checkpoint.json"
        self.clock = Clock()
        self.manifest = manifest()

    def run_tasks(self, callback=successful, **kwargs):
        return run_fixed_tasks(self.manifest, callback, checkpoint_path=self.path, clock=self.clock, **kwargs)

    def read_raw(self):
        return json.loads(self.path.read_text())

    def test_strict_manifest_hashes_and_detached_inputs(self):
        wire = self.manifest.to_dict()
        restored = FixedTaskManifest.from_dict(wire)
        self.assertEqual(restored.to_dict(), wire)
        wire["tasks"][0]["payload"]["number"] = 99
        self.assertNotEqual(restored.to_dict(), wire)
        self.assertEqual(restored.manifest_hash, self.manifest.manifest_hash)
        with self.assertRaises(FrozenInstanceError):
            restored.manifest_hash = "bad"
        bad_values = []
        for field in ("source_hash", "configuration_hash", "manifest_hash"):
            bad = self.manifest.to_dict()
            bad[field] = "0" * 64
            bad_values.append(bad)
        bad = self.manifest.to_dict()
        bad["tasks"][0]["payload_hash"] = "0" * 64
        bad_values.append(bad)
        for mutation in (lambda p: p.update(extra=True), lambda p: p.update(version=True),
                         lambda p: p["tasks"].append(deepcopy(p["tasks"][0])),
                         lambda p: p["source"].update(extra=True),
                         lambda p: p["tasks"][0].update(extra=True)):
            bad = self.manifest.to_dict()
            mutation(bad)
            bad_values.append(bad)
        for bad in bad_values:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                FixedTaskManifest.from_dict(bad)
        with self.assertRaises(ValueError):
            manifest(())
        with self.assertRaises(ValueError):
            manifest(("same", "same"))

    def test_manifest_rejects_nonfinite_and_malformed_source_payloads(self):
        for value in (float("nan"), float("inf"), object(), {1: "not a JSON key"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                FixedTaskManifest.create(source={"commit": "a" * 40, "hashes": {"fixture": "b" * 64}},
                                         configuration={}, tasks=[{"id": "task", "payload": value}])
        for source in ({}, {"commit": "branch-name", "hashes": {}},
                       {"commit": "a" * 40, "hashes": {}},
                       {"commit": "a" * 40, "hashes": {"fixture": "not-a-hash"}}):
            with self.assertRaises(ValueError):
                FixedTaskManifest.create(source=source, configuration={}, tasks=[{"id": "a", "payload": None}])

    def test_fixed_order_and_checkpoint_resumption_are_canonical(self):
        executed = []
        def callback(task):
            executed.append(task["id"])
            self.clock.value += 2
            return successful(task)
        partial = self.run_tasks(callback, deadline=12)
        self.assertEqual(executed, ["b"])
        self.assertEqual(partial.to_dict()["reason"], "deadline")
        self.assertFalse(partial.to_dict()["complete"])
        resumed = self.run_tasks(callback)
        self.assertEqual(executed, ["b", "a", "c"])
        self.assertTrue(resumed.to_dict()["complete"])
        other = Path(self.temporary.name) / "other.json"
        uninterrupted = run_fixed_tasks(self.manifest, successful, checkpoint_path=other, clock=Clock(900))
        self.assertEqual(resumed.canonical_results_hash, uninterrupted.canonical_results_hash)
        self.assertEqual(canonical_json(resumed.to_dict()["completed"]), canonical_json(uninterrupted.to_dict()["completed"]))
        self.assertNotEqual(resumed.to_dict()["attempts"], uninterrupted.to_dict()["attempts"])
        self.run_tasks(lambda _: self.fail("completed task executed twice"))

    def test_cancellation_before_next_task_is_explicit_and_resumable(self):
        calls = []
        def callback(task):
            calls.append(task["id"])
            return successful(task)
        result = self.run_tasks(callback, cancelled=lambda: bool(calls))
        self.assertEqual(calls, ["b"])
        data = result.to_dict()
        self.assertEqual(data["reason"], "cancelled")
        self.assertEqual(data["remaining_ids"], ["a", "c"])
        self.assertEqual(data["attempts"][-1]["status"], "cancelled")
        self.assertFalse(data["attempts"][-1]["started"])
        self.assertTrue(self.run_tasks(callback).to_dict()["complete"])
        self.assertEqual(calls, ["b", "a", "c"])

    def test_deadline_is_between_tasks_not_a_running_callback_stop(self):
        calls = []
        def slow(task):
            calls.append(task["id"])
            self.clock.value += 50
            return successful(task)
        result = self.run_tasks(slow, deadline=11).to_dict()
        self.assertEqual(calls, ["b"])
        self.assertEqual(result["completed"][0]["result"], successful(self.manifest.to_dict()["tasks"][0]))
        self.assertEqual(result["attempts"][0]["elapsed_seconds"], 50)
        self.assertEqual(result["reason"], "deadline")
        self.assertFalse(result["hard_deadline_enforced"])

    def test_initial_deadline_or_cancellation_never_completes_empty_output(self):
        result = self.run_tasks(lambda _: self.fail("must not start"), deadline=10).to_dict()
        self.assertEqual(result["completed"], [])
        self.assertFalse(result["complete"])
        self.assertEqual(result["attempts"][0]["status"], "deadline")

    def test_callback_failure_and_input_mutation_are_persisted_and_never_retried(self):
        for name, callback in (("exception", lambda _: (_ for _ in ()).throw(RuntimeError("synthetic failure"))),
                               ("mutation", lambda task: task["payload"].update(number=77)),
                               ("nonfinite", lambda _: {"result": float("nan")})):
            with self.subTest(case=name):
                path = Path(self.temporary.name) / f"{name}.json"
                result = run_fixed_tasks(self.manifest, callback, checkpoint_path=path, clock=self.clock)
                data = result.to_dict()
                self.assertEqual(data["status"], "blocked")
                self.assertEqual(data["completed"], [])
                self.assertTrue(data["attempts"][-1]["started"])
                rerun = run_fixed_tasks(self.manifest, lambda _: self.fail("fault auto-retried"),
                                        checkpoint_path=path, clock=self.clock)
                self.assertEqual(rerun.to_dict(), data)
                self.assertEqual(self.manifest.to_dict()["tasks"][0]["payload"], {"number": 0})

    def test_callback_mutation_wins_over_an_exception_and_result_alias_is_detached(self):
        def corrupt(task):
            task["payload"]["number"] = 99
            raise RuntimeError("secondary failure")
        result = self.run_tasks(corrupt).to_dict()
        self.assertEqual(result["reason"], "integrity-failure")
        path = Path(self.temporary.name) / "detached.json"
        retained = []
        def callback(task):
            value = {"id": task["id"], "nested": []}
            retained.append(value)
            return value
        result = run_fixed_tasks(self.manifest, callback, checkpoint_path=path, clock=self.clock)
        expected = result.to_dict()
        retained[0]["nested"].append("outside mutation")
        returned = result.to_dict()
        returned["completed"][0]["result"]["nested"].append("report mutation")
        self.assertEqual(result.to_dict(), expected)
        self.assertEqual(load_checkpoint(self.manifest, path)["completed"], expected["completed"])

    def test_tampered_and_incompatible_checkpoints_reject_before_callback(self):
        self.run_tasks()
        original = self.read_raw()
        for change in (lambda p: p["completed"][0]["result"].update(answer=999),
                       lambda p: p.update(extra=True),
                       lambda p: p.update(version=True),
                       lambda p: p["completed"].reverse(),
                       lambda p: p["attempts"].pop(),
                       lambda p: p["attempts"][0].update(elapsed_seconds=-1)):
            envelope = deepcopy(original)
            change(envelope["payload"])
            # A valid outer checksum alone cannot conceal invalid inner fields.
            envelope["sha256"] = canonical_hash(envelope["payload"])
            self.path.write_text(canonical_json(envelope))
            with self.assertRaises(ValueError):
                self.run_tasks(lambda _: self.fail("tampered checkpoint executed"))
        self.path.write_text(canonical_json(original | {"sha256": "0" * 64}))
        with self.assertRaises(FixedTaskIntegrityError):
            load_checkpoint(self.manifest, self.path)
        self.path.write_text(canonical_json(original))
        with self.assertRaises(ValueError):
            run_fixed_tasks(manifest(("different",)), successful, checkpoint_path=self.path)

    def test_interrupted_running_attempt_blocks_without_duplicate_execution(self):
        seen_running = []
        def callback(task):
            seen_running.append(load_checkpoint(self.manifest, self.path))
            return successful(task)
        self.run_tasks(callback)
        interrupted = seen_running[0]
        self.assertEqual(interrupted["attempts"][0]["status"], "running")
        self.path.write_text(canonical_json({"payload": interrupted, "sha256": canonical_hash(interrupted)}))
        result = self.run_tasks(lambda _: self.fail("unknown attempt retried")).to_dict()
        self.assertEqual(result["reason"], "unreconciled-attempt")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["completed"], [])

    def test_atomic_write_failure_never_starts_unrecorded_callback(self):
        with patch("research.harness.lab_fixed_tasks.os.replace", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(ValueError):
                self.run_tasks(lambda _: self.fail("undurable callback started"))
        self.assertFalse(self.path.exists())
        self.assertFalse(list(self.path.parent.glob("*.tmp")))
        self.run_tasks(deadline=10)
        saved = self.path.read_bytes()
        with patch("research.harness.lab_fixed_tasks.os.replace", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(ValueError):
                self.run_tasks(lambda _: self.fail("undurable callback started"))
        self.assertEqual(self.path.read_bytes(), saved)

    def test_invalid_clock_control_and_repository_output_fail_closed(self):
        from research.harness.lab_fixed_tasks import REPOSITORY

        with self.assertRaises(ValueError):
            run_fixed_tasks(self.manifest, successful, checkpoint_path=REPOSITORY / "forbidden-test-checkpoint.json")
        for value in (True, -1, float("nan"), float("inf"), "12", 2**1024):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_tasks(deadline=value)
        for value in (True, -1, float("nan"), "now"):
            path = Path(self.temporary.name) / f"clock-{repr(value)}.json"
            result = run_fixed_tasks(self.manifest, lambda _: self.fail("bad clock started"),
                                     checkpoint_path=path, clock=lambda: value).to_dict()
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["attempts"][0]["started"])
        path = Path(self.temporary.name) / "bad-cancel.json"
        result = run_fixed_tasks(self.manifest, lambda _: self.fail("bad cancellation started"),
                                 checkpoint_path=path, cancelled=lambda: "yes").to_dict()
        self.assertEqual(result["reason"], "integrity-failure")

    def test_backwards_clock_after_callback_does_not_complete_the_task(self):
        def callback(task):
            self.clock.value -= 1
            return successful(task)
        result = self.run_tasks(callback).to_dict()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["completed"], [])
        self.assertEqual(result["reason"], "integrity-failure")
        self.assertIsNone(result["attempts"][0]["elapsed_seconds"])

    def test_post_callback_write_failure_preserves_ambiguous_running_attempt(self):
        original_replace = os.replace
        replaces, executions = [], []
        def fail_completion(source, target):
            replaces.append(target)
            if len(replaces) == 3:
                raise OSError("result persistence failed")
            return original_replace(source, target)
        def callback(task):
            executions.append(task["id"])
            return successful(task)
        with patch("research.harness.lab_fixed_tasks.os.replace", side_effect=fail_completion):
            with self.assertRaises(FixedTaskIntegrityError):
                self.run_tasks(callback)
        self.assertEqual(executions, ["b"])
        self.assertEqual(load_checkpoint(self.manifest, self.path)["attempts"][-1]["status"], "running")
        self.assertEqual(self.run_tasks(lambda _: self.fail("ambiguous task replayed")).to_dict()["reason"],
                         "unreconciled-attempt")

    def test_reentrant_runner_is_rejected_without_a_second_callback(self):
        def callback(task):
            with self.assertRaisesRegex(FixedTaskIntegrityError, "already owned"):
                self.run_tasks(lambda _: self.fail("nested owner executed"))
            return successful(task)
        self.assertTrue(self.run_tasks(callback).to_dict()["complete"])

    def test_duplicate_json_keys_are_rejected_even_with_a_valid_payload_checksum(self):
        self.run_tasks()
        original = self.read_raw()
        self.path.write_text('{"payload":' + canonical_json(original["payload"]) +
                             ',"sha256":"' + original["sha256"] + '","sha256":"' + original["sha256"] + '"}')
        with self.assertRaisesRegex(FixedTaskIntegrityError, "duplicate"):
            load_checkpoint(self.manifest, self.path)

    def test_manifest_path_and_command_strings_remain_inert_data(self):
        inert = FixedTaskManifest.create(
            source={"commit": "c" * 40, "hashes": {"/nonexistent/source-is-a-label": "d" * 64}},
            configuration={"script": "never execute this"},
            tasks=[{"id": "inert", "payload": {"path": "/nonexistent/payload-is-not-loaded", "command": "exit 99"}}],
        )
        result = run_fixed_tasks(inert, lambda task: {"echo": task["payload"]},
                                 checkpoint_path=self.path, clock=self.clock).to_dict()
        self.assertTrue(result["complete"])
        self.assertEqual(result["completed"][0]["result"]["echo"]["command"], "exit 99")


if __name__ == "__main__":
    unittest.main()
