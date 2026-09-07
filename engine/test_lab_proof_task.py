"""Synthetic proof orchestration only; no real-game proof/search or budget jobs."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.harness import lab_proof_task as task_module
from research.harness.lab_proof_producer import produce_certificate
from research.harness.lab_terminal_cert import TerminalProvider, canonical_hash


def synthetic(prefix="p", *, second_score=0, extra=False):
    actions = [{"action": "plant", "face": [0, 0], "orientation": index} for index in range(2 + int(extra))]
    nodes = {"root": {"name": "root", "actor": {"seat": "S1", "color": "B"},
                      "seats": {"B": "S1", "W": "S2"}, "accepted": False,
                      "score": None, "actions": actions}}
    for index in range(len(actions)):
        nodes[str(index)] = {"name": str(index), "actor": {"seat": None, "color": None},
                            "seats": {"B": "S1", "W": "S2"}, "accepted": True,
                            "score": {"B": 1 if index == 0 else second_score, "W": 0}, "actions": []}
    provider = TerminalProvider(
        provider_id="synthetic-" + prefix, rules_id="synthetic", rules_revision="0.1",
        rules_hash="a" * 64, implementation_hash=canonical_hash(prefix),
        fingerprint=lambda state: canonical_hash({"provider": prefix, "state": state}),
        snapshot=deepcopy, metadata=lambda _: {"provenance": {"full_action_replay": False}, "synthetic": True},
        actor=lambda s: deepcopy(s["actor"]), seats=lambda s: deepcopy(s["seats"]),
        accepted=lambda s: s["accepted"], score=lambda s: deepcopy(s["score"]),
        legal_actions=lambda s: deepcopy(s["actions"]),
        transition=lambda _s, wire: deepcopy(nodes[str(wire["orientation"])]),
    )
    return deepcopy(nodes["root"]), provider


class TestLabProofTask(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="varde-synthetic-proof-")
        self.addCleanup(self.temp.cleanup)
        self.store = task_module.ArtifactStore(self.temp.name)

    def run_paths(self, **options):
        root, provider = synthetic()
        independent_root, independent = synthetic("i")
        return task_module.execute_paths(root, provider, independent_root=independent_root,
                                         independent_provider=independent, store=self.store, **options)

    def test_separate_provider_certificate_identities_and_checked_work(self):
        calls = []
        original = task_module.check_certificate

        def checked(certificate, root, provider, **kwargs):
            calls.append(provider.provider_id)
            self.assertEqual(certificate.to_dict()["provider"], provider.identity())
            return original(certificate, root, provider, **kwargs)

        with patch.object(task_module, "check_certificate", side_effect=checked):
            result = self.run_paths()
        self.assertEqual(calls, ["synthetic-p", "synthetic-i"])
        self.assertTrue(result["comparison"]["independent_complete"])
        self.assertFalse(result["independently_certified"])
        self.assertFalse(result["admission_record"])
        self.assertIsNone(result["origin"])
        for path in result["paths"].values():
            production = self.store.read_json(path["producer"])
            report = self.store.read_json(path["checker"])
            self.assertEqual(production["telemetry"]["work"]["nodes"], 3)
            self.assertEqual(report["work"]["nodes_checked"], 3)
            self.assertNotIn("timing", production)
            self.assertEqual(report["work"]["terminal_simulation_backups"], 0)

    def test_cancellation_and_checker_limits_are_unknown_not_certificates(self):
        result = self.run_paths(cancelled=lambda: True)
        self.assertFalse(result["comparison"]["independent_complete"])
        for path in result["paths"].values():
            self.assertIsNone(path["checker"])
            self.assertIsNone(self.store.read_json(path["producer"])["certificate"])
        for limits in ({"producer_nodes": 2}, {"checker_nodes": 1}):
            with self.subTest(limits=limits):
                result = self.run_paths(**limits)
                self.assertFalse(result["comparison"]["independent_complete"])
                self.assertFalse(result["independently_certified"])
                self.assertEqual(result["comparison"]["root_class"], "partial")

    def test_both_paths_share_one_absolute_deadline(self):
        deadlines = []

        def producing(root, provider, **kwargs):
            deadlines.append(kwargs["deadline"])
            return produce_certificate(root, provider, **kwargs)

        with patch.object(task_module, "produce_certificate", side_effect=producing):
            result = self.run_paths(deadline=100, clock=lambda: 0)
        self.assertEqual(deadlines, [100, 100])
        self.assertTrue(result["comparison"]["independent_complete"])

    def test_invalid_clocks_and_deadlines_never_become_zero_elapsed(self):
        for value in (True, float("nan"), float("inf"), "0"):
            with self.subTest(value=value, kind="deadline"), self.assertRaises(ValueError):
                self.run_paths(deadline=value)
            with self.subTest(value=value, kind="clock"), self.assertRaises(ValueError):
                self.run_paths(clock=lambda value=value: value)

    def test_timing_does_not_enter_any_canonical_reference_or_result(self):
        first = self.run_paths(clock=lambda: 0)
        ticks = iter(range(1000))
        second = self.run_paths(clock=lambda: next(ticks))
        self.assertEqual(first, second)
        files = sorted((Path(self.temp.name) / "operational").glob("*.json"))
        self.assertEqual(len(files), 2)
        values = [json.loads(path.read_bytes()) for path in files]
        self.assertNotEqual(values[0], values[1])
        self.assertNotIn("operational", json.dumps(first))

    def test_independent_disagreement_and_legal_domain_divergence_stop(self):
        root, provider = synthetic()
        for options in ({"second_score": -1}, {"extra": True}):
            other_root, other = synthetic("i", **options)
            with self.subTest(options=options), self.assertRaises(task_module.ProofTaskIntegrityError):
                task_module.execute_paths(root, provider, independent_root=other_root,
                                           independent_provider=other, store=self.store)

    def test_provider_mutation_and_iterator_failure_do_not_mutate_caller(self):
        root, provider = synthetic()
        before = deepcopy(root)

        def mutated(state):
            state["name"] = "corrupt"
            raise RuntimeError("callback failed")

        def iterator(state):
            yield state["actions"][0]
            state["name"] = "corrupt"
            raise RuntimeError("enumeration failed")

        for changed in (replace(provider, actor=mutated), replace(provider, legal_actions=iterator)):
            with self.subTest(provider=changed), self.assertRaises(task_module.ProofTaskIntegrityError):
                task_module.execute_paths(root, changed, store=self.store)
            self.assertEqual(root, before)

    def test_artifact_collision_symlink_missing_and_corruption_fail_closed(self):
        reference = self.store.put_json({"proof": [1, 2]})
        self.assertEqual(hashlib.sha256(self.store.read(reference)).hexdigest(), reference["sha256"])
        path = self.store.root / reference["content_id"]
        path.write_bytes(b"corrupt")
        with self.assertRaises(task_module.ProofTaskIntegrityError):
            self.store.put_json({"proof": [1, 2]})
        path.unlink()
        with self.assertRaises(task_module.ProofTaskIntegrityError):
            self.store.audit(reference)
        outside = self.store.root / "outside.json"
        outside.write_bytes(b"{}")
        path.symlink_to(outside)
        with self.assertRaises(task_module.ProofTaskIntegrityError):
            self.store.audit(reference)
        self.assertEqual(outside.read_bytes(), b"{}")

    def test_manifest_writer_is_immutable_and_has_no_temporary_residue(self):
        path = self.store.root / "manifest.json"
        task_module.publish_json(path, {"source": "synthetic"})
        task_module.publish_json(path, {"source": "synthetic"})
        with self.assertRaises(task_module.ProofTaskIntegrityError):
            task_module.publish_json(path, {"source": "changed"})
        self.assertFalse(list(self.store.root.glob(".proof-*.tmp")))

    def test_audit_rejects_transplanted_checker_or_unearned_origin_promotion(self):
        result = self.run_paths()
        for kind in ("checker", "promotion", "flag-alias", "comparison", "path-flag-alias"):
            altered = deepcopy(result)
            if kind == "checker":
                altered["paths"]["independent"]["checker"] = altered["paths"]["production"]["checker"]
            elif kind == "promotion":
                altered["independently_certified"] = True
            elif kind == "flag-alias":
                altered["independently_certified"] = 0
            elif kind == "path-flag-alias":
                for path in altered["paths"].values():
                    path["root_accepted"] = 0
            else:
                altered["comparison"]["root_bounds"] = [True, True]
            altered.pop("result_hash")
            altered["result_hash"] = canonical_hash(altered)
            with self.subTest(kind=kind), self.assertRaises(task_module.ProofTaskIntegrityError):
                task_module.audit_result(altered, self.store)

    def test_audit_missing_artifacts_does_not_rerun_proofs(self):
        result = self.run_paths()
        reference = result["paths"]["production"]["producer"]
        (self.store.root / reference["content_id"]).unlink()
        with patch.object(task_module, "produce_certificate") as produce, \
                patch.object(task_module, "check_certificate") as check, \
                self.assertRaises(ValueError):
            task_module.audit_result(result, self.store)
        produce.assert_not_called()
        check.assert_not_called()

    def test_expected_task_audit_rejects_transplant_without_proof_rerun(self):
        from research.harness import lab_proof_jobs as jobs
        payload = {"row": None, "row_hash": None, "source": {"synthetic": True}}
        task = {"id": "synthetic-missing", "payload": payload, "payload_hash": canonical_hash(payload)}
        with patch.object(jobs, "verify_runtime_source"), \
                patch.object(jobs, "validate_proof_task", return_value=deepcopy(payload)), \
                patch.dict("os.environ", {task_module.ARTIFACT_ENV: self.temp.name}):
            result = task_module.run_proof_task(task)
            self.assertEqual(task_module.audit_result(result, self.store, task=task), result)
            for changed in ({"id": "other-slot"}, {"payload_hash": "a" * 64}):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    task_module.audit_result(result, self.store, task=task | changed)

    def test_source_exit_guard_runs_for_missing_success_and_every_failure(self):
        from research.harness import lab_proof_jobs as jobs
        payload = {"row": None, "row_hash": None, "source": {"synthetic": True}}
        task = {"id": "synthetic-missing", "payload": payload, "payload_hash": canonical_hash(payload)}
        with patch.object(jobs, "verify_runtime_source") as guard, \
                patch.object(jobs, "validate_proof_task", return_value=deepcopy(payload)), \
                patch.dict("os.environ", {task_module.ARTIFACT_ENV: self.temp.name}):
            result = task_module.run_proof_task(task)
        self.assertEqual(guard.call_count, 2)
        self.assertEqual(result["comparison"]["status"], "missing")
        self.assertFalse(result["independently_certified"])
        for error in (ValueError("malformed task"), RuntimeError("validation failed")):
            with self.subTest(error=error), patch.object(jobs, "verify_runtime_source") as guard, \
                    patch.object(jobs, "validate_proof_task", side_effect=error), self.assertRaises(type(error)):
                task_module.run_proof_task(task)
            self.assertEqual(guard.call_count, 2)
        with patch.object(jobs, "verify_runtime_source", side_effect=[None, ValueError("exit drift")]), \
                patch.object(jobs, "validate_proof_task", return_value=deepcopy(payload)), \
                patch.dict("os.environ", {task_module.ARTIFACT_ENV: self.temp.name}), self.assertRaisesRegex(ValueError, "exit drift"):
            task_module.run_proof_task(task)

    def test_fresh_origin_failure_never_reaches_proof_and_checks_exit_sources(self):
        from research.harness import lab_proof_jobs as jobs
        payload = {"row": {"origin": {"synthetic": True}, "origin_hash": "a" * 64},
                   "row_hash": "b" * 64, "source": {"synthetic": True}}
        task = {"id": "synthetic-rejected", "payload": payload, "payload_hash": canonical_hash(payload)}
        with patch.object(jobs, "verify_runtime_source") as guard, \
                patch.object(jobs, "validate_proof_task", return_value=deepcopy(payload)), \
                patch.object(task_module, "verify_origin", side_effect=ValueError("origin rejected")), \
                patch.object(task_module, "produce_certificate") as produce, \
                patch.dict("os.environ", {task_module.ARTIFACT_ENV: self.temp.name}), self.assertRaisesRegex(ValueError, "origin rejected"):
            task_module.run_proof_task(task)
        self.assertEqual(guard.call_count, 2)
        produce.assert_not_called()


if __name__ == "__main__":
    unittest.main()
