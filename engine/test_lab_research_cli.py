"""Local orchestration tests; disposable ledgers and no actual-game searches."""

import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from research.harness import lab_research_cli as cli
from research.harness.lab_budget import ResearchBudget
from research.harness.lab_terminal_cert import canonical_json


class TestLabResearchCLI(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def budget_args(self):
        return argparse.Namespace(ledger=str(self.root / "budget.json"), session="synthetic-only")

    def run_args(self, **changes):
        values = dict(manifest="unused-mocked.json", output_dir=str(self.root / "results"),
                      ledger=str(self.root / "budget.json"), session="synthetic-only",
                      job="synthetic-job", resume=False, reconcile_json=None)
        return argparse.Namespace(**(values | changes))

    @staticmethod
    def manifest(stage="bootstrap"):
        return Mock(to_dict=lambda: {
            "source": {"commit": "a" * 40, "hashes": {}},
            "configuration": {"stage": stage, "execution": {
                "workers": 8, "task_timeout": 20, "cohort_timeout": 120,
                "reserved_capacity": 156, "projection_kind": "declared-hard-reservation"}},
            "tasks": [],
        }, manifest_hash="b" * 64)

    def test_help_and_import_from_other_directory_launch_nothing(self):
        result = subprocess.run([sys.executable, str(Path(cli.__file__).resolve()), "--help"],
                                cwd=self.root, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("init-budget", result.stdout)
        self.assertIn("audit", result.stdout)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_budget_creation_is_explicit_and_never_resets(self):
        args = self.budget_args()
        first = cli.initialize_budget(args)
        self.assertEqual(first["budget"]["charged_seconds"], 0)
        self.assertEqual(first["budget"]["windows_opened"], 0)
        self.assertFalse(first["research_launched"])
        before = Path(args.ledger).read_bytes()
        with self.assertRaises(ValueError):
            cli.initialize_budget(args)
        self.assertEqual(Path(args.ledger).read_bytes(), before)
        status = cli.budget_status(args)["budget"]
        self.assertEqual(status["state"]["plan_sha256"], cli.PLAN_SHA256)
        self.assertEqual(status["active_jobs"], [])

    def test_prepare_creates_external_parent_and_publishes_only_manifest(self):
        from research.harness import lab_proof_jobs

        directory = self.root / "new-cohort"
        manifest = self.manifest()
        args = argparse.Namespace(output_dir=str(directory), corpus="mocked-frozen.json", stage="bootstrap")
        with patch.object(lab_proof_jobs, "load_frozen_corpus", return_value=object()), \
                patch.object(lab_proof_jobs, "build_bootstrap_manifest", return_value=manifest), \
                patch.object(cli, "run_supervised") as supervised:
            first = cli.prepare(args)
            again = cli.prepare(args)
        self.assertEqual(first, again)
        self.assertEqual(list(directory.iterdir()), [directory / "manifest.json"])
        self.assertEqual(json.loads((directory / "manifest.json").read_text()), manifest.to_dict())
        self.assertFalse(first["research_launched"])
        supervised.assert_not_called()

    def test_missing_and_wrong_plan_ledgers_fail_closed(self):
        args = self.budget_args()
        with self.assertRaisesRegex(ValueError, "does not exist"):
            cli.budget_status(args)
        ResearchBudget.create(args.ledger, session_id=args.session, plan_sha256="e" * 64)
        with self.assertRaisesRegex(ValueError, "different frozen plan"):
            cli.budget_status(args)

    def test_repository_outputs_rejected(self):
        for path in (cli.REPOSITORY, cli.REPOSITORY / "ignored-run"):
            with self.assertRaisesRegex(ValueError, "outside"):
                cli._external(path)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for index, content in enumerate(('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}')):
            path = self.root / f"invalid-{index}.json"
            path.write_text(content)  # Deliberately malformed synthetic input.
            with self.assertRaises(ValueError):
                cli._read_json(path)

    def test_reconciliation_is_exact_explicit_data(self):
        self.assertIsNone(cli._reconciliation(None))
        path = self.root / "reconcile.json"
        value = {"attempt_nonces": ["a" * 32], "job_ids": ["job"],
                 "reason": "Owned synthetic workers confirmed stopped", "externally_confirmed_stopped": False}
        path.write_text(canonical_json(value))
        receipt = cli._reconciliation(path)
        self.assertEqual(receipt.attempt_nonces, ("a" * 32,))
        for changed in (value | {"extra": 1}, value | {"job_ids": "job"},
                        value | {"externally_confirmed_stopped": 1}):
            path.write_text(canonical_json(changed))
            with self.assertRaises(ValueError):
                cli._reconciliation(path)

    def test_context_restores_environment_and_signal_handlers_after_error(self):
        before = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        with patch.dict(os.environ, {cli.ARTIFACT_ENV: "prior-trusted-root"}):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                with cli._run_context(self.root) as cancelled:
                    self.assertEqual(os.environ[cli.ARTIFACT_ENV], str(self.root))
                    self.assertFalse(cancelled())
                    signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
                    self.assertTrue(cancelled())
                    raise RuntimeError("synthetic failure")
            self.assertEqual(os.environ[cli.ARTIFACT_ENV], "prior-trusted-root")
        for number, handler in before.items():
            self.assertEqual(signal.getsignal(number), handler)

    def test_context_removes_new_environment_value(self):
        with patch.dict(os.environ, {}, clear=True):
            with cli._run_context(self.root):
                self.assertIn(cli.ARTIFACT_ENV, os.environ)
            self.assertNotIn(cli.ARTIFACT_ENV, os.environ)

    def test_certification_cannot_run_without_measured_cohort(self):
        with patch.object(cli, "_manifest", return_value=self.manifest("certification")), \
                patch.object(cli, "run_supervised") as supervised:
            with self.assertRaisesRegex(ValueError, "separately frozen measured cohort"):
                cli.run(self.run_args())
        supervised.assert_not_called()

    def test_explicit_resume_is_required_and_must_exist(self):
        with patch.object(cli, "_manifest", return_value=self.manifest()), \
                patch.object(cli, "run_supervised") as supervised:
            with self.assertRaisesRegex(ValueError, "absent checkpoint"):
                cli.run(self.run_args(resume=True))
            directory = self.root / "results"
            directory.mkdir()
            (directory / "supervisor-checkpoint.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "explicit --resume"):
                cli.run(self.run_args())
        supervised.assert_not_called()

    def test_bad_completed_artifact_blocks_before_budget_or_dispatch(self):
        with patch.object(cli, "_manifest", return_value=self.manifest()), \
                patch.object(cli, "_worker", return_value=Mock()), \
                patch.object(cli, "_audit_completed", side_effect=ValueError("corrupt artifact")), \
                patch.object(cli, "budget_status") as budget, \
                patch.object(cli, "run_supervised") as supervised:
            with self.assertRaisesRegex(ValueError, "corrupt artifact"):
                cli.run(self.run_args())
        budget.assert_not_called()
        supervised.assert_not_called()

    def test_run_uses_frozen_limits_and_never_elevates_supervisor_claims(self):
        from research.harness import lab_proof_jobs
        from research.harness import lab_proof_task

        cli.initialize_budget(self.budget_args())
        manifest = self.manifest()
        store = Mock(root=self.root / "results" / "artifacts")
        run_result = Mock(to_dict=lambda: {"status": "timeout", "complete": False,
                                          "source_commit_verified": False, "admission_record": False})
        with patch.object(cli, "_manifest", return_value=manifest), \
                patch.object(cli, "_worker", return_value=Mock()), \
                patch.object(cli, "_audit_completed", return_value={"completed_artifacts_audited": 0}), \
                patch.object(lab_proof_task, "ArtifactStore", return_value=store), \
                patch.object(lab_proof_jobs, "verify_runtime_source") as verify, \
                patch.object(cli, "run_supervised", return_value=run_result) as supervised:
            response = cli.run(self.run_args())
        kwargs = supervised.call_args.kwargs
        self.assertEqual((kwargs["workers"], kwargs["task_timeout"], kwargs["cohort_timeout"]), (8, 20, 120))
        self.assertEqual(kwargs["projected_seconds"], 120)
        self.assertEqual((kwargs["term_grace"], kwargs["kill_grace"], kwargs["reap_timeout"]), (.05, .05, 1))
        self.assertIsNone(kwargs["reconcile"])
        self.assertEqual(response["status"], "timeout")
        self.assertFalse(response["run"]["source_commit_verified"])
        self.assertFalse(response["admission_record"])
        self.assertTrue(response["source_commit_verified"])
        verify.assert_called_once_with(manifest.to_dict()["source"])
        store.put_operational.assert_called_once()

    def test_supervisor_exception_still_checks_sources_and_restores_context(self):
        from research.harness import lab_proof_jobs
        from research.harness import lab_proof_task

        cli.initialize_budget(self.budget_args())
        with patch.object(cli, "_manifest", return_value=self.manifest()), \
                patch.object(cli, "_worker", return_value=Mock()), \
                patch.object(cli, "_audit_completed", return_value={}), \
                patch.object(lab_proof_task, "ArtifactStore", return_value=Mock(root=self.root)), \
                patch.object(lab_proof_jobs, "verify_runtime_source") as verify, \
                patch.object(cli, "run_supervised", side_effect=RuntimeError("synthetic supervisor failure")), \
                patch.dict(os.environ, {cli.ARTIFACT_ENV: "old"}):
            with self.assertRaisesRegex(RuntimeError, "supervisor failure"):
                cli.run(self.run_args())
            self.assertEqual(os.environ[cli.ARTIFACT_ENV], "old")
        verify.assert_called_once()

    def test_cli_reports_failure_as_json_without_false_success(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = cli.main(["status", "--ledger", str(self.root / "missing"), "--session", "test"])
        self.assertEqual(code, 2)
        value = json.loads(stream.getvalue())
        self.assertEqual(value["status"], "blocked")
        self.assertFalse(value["admission_record"])


if __name__ == "__main__":
    unittest.main()
