"""Explicit local proof-job controls; import never launches research.

Run with ``python -m research.harness.lab_research_cli --help``. The first
bootstrap is a frozen hard reservation, not an estimate learned from game data.
Certification manifests may be prepared, but their measured execution cohort
must be frozen separately. This CLI never runs an unqualified match or MCTS arm.
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from research.harness.lab_budget import ResearchBudget  # noqa: E402
from research.harness.lab_supervisor import (  # noqa: E402
    Reconciliation, TrustedWorker, load_supervisor_checkpoint, run_supervised,
)
from research.harness.lab_terminal_cert import canonical_json  # noqa: E402

PLAN_SHA256 = "71517f521ca4da1ab17acc817381e52f3f05e872700ece6ec96c9ae0a59dec6c"
ARTIFACT_ENV = "VARDE_LAB_ARTIFACT_ROOT"
TERM_GRACE = 0.05
KILL_GRACE = 0.05
REAP_TIMEOUT = 1.0
BOOTSTRAP_MEASUREMENT = (
    "Frozen 5D/5F bootstrap hard reservation: 32 fixed development slots, "
    "32 producer/128 checker nodes per mechanics path, 8 workers, 20s whole "
    "task, 120s cohort including cleanup; not measured game throughput."
)


class ResearchCLIError(ValueError):
    """A local run request failed before admissible evidence could be reported."""


def _external(value):
    path = Path(value).expanduser().resolve()
    if path == REPOSITORY or REPOSITORY in path.parents:
        raise ResearchCLIError("research output and ledgers must be outside the repository")
    return path


def _read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ResearchCLIError("duplicate JSON object key")
            result[key] = value
        return result

    value = json.loads(Path(path).read_text(), object_pairs_hook=unique)
    canonical_json(value)
    return value


def _worker():
    from research.harness.lab_proof_jobs import authoritative_sources

    return TrustedWorker("research.harness.lab_proof_task", "run_proof_task",
                         authoritative_sources())


def _manifest(path):
    from research.harness.lab_proof_jobs import (
        validate_committed_source, validate_proof_manifest, verify_runtime_source,
    )

    result = validate_proof_manifest(_read_json(path))
    source = result.to_dict()["source"]
    validate_committed_source(source)
    verify_runtime_source(source)
    return result


def _reconciliation(path):
    if path is None:
        return None
    value = _read_json(path)
    fields = {"attempt_nonces", "job_ids", "reason", "externally_confirmed_stopped"}
    if type(value) is not dict or set(value) != fields:
        raise ResearchCLIError("explicit complete reconciliation receipt required")
    if type(value["attempt_nonces"]) is not list or type(value["job_ids"]) is not list:
        raise ResearchCLIError("reconciliation identities must be lists")
    return Reconciliation(tuple(value["attempt_nonces"]), tuple(value["job_ids"]),
                          value["reason"], value["externally_confirmed_stopped"])


@contextmanager
def _run_context(artifact_root):
    """Trusted parent-owned environment and bounded cancellation, restored always."""
    old_root = os.environ.get(ARTIFACT_ENV)
    previous = {}
    interrupted = False

    def stop(_signum, _frame):
        nonlocal interrupted
        interrupted = True

    try:
        os.environ[ARTIFACT_ENV] = str(artifact_root)
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, stop)
        yield lambda: interrupted
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if old_root is None:
            os.environ.pop(ARTIFACT_ENV, None)
        else:
            os.environ[ARTIFACT_ENV] = old_root


def _audit_completed(manifest, worker, output_dir, store, *, required=False):
    from research.harness.lab_proof_task import audit_result

    checkpoint = output_dir / "supervisor-checkpoint.json"
    if not checkpoint.exists():
        if required:
            raise ResearchCLIError("no supervisor checkpoint exists to audit")
        return {"checkpoint_present": False, "completed_artifacts_audited": 0,
                "independently_certified": 0, "admission_record": False}
    state = load_supervisor_checkpoint(manifest, worker, output_dir)
    by_id = {task["id"]: task for task in manifest.to_dict()["tasks"]}
    count = 0
    for row in state["completed"]:
        audit_result(row["result"], store, task=by_id[row["task_id"]])
        count += int(row["result"].get("independently_certified") is True)
    return {"checkpoint_present": True,
            "completed_artifacts_audited": len(state["completed"]),
            "independently_certified": count,
            "attempts": len(state["attempts"]),
            "cohort_states": [{"id": row["id"], "status": row["status"],
                               "cleanup_confirmed": row["cleanup_confirmed"]}
                              for row in state["cohorts"]],
            "admission_record": False}


def prepare(args):
    from research.harness.lab_proof_jobs import (
        build_bootstrap_manifest, build_certification_manifest, load_frozen_corpus,
    )
    from research.harness.lab_proof_task import publish_json

    directory = _external(args.output_dir)
    corpus = load_frozen_corpus(args.corpus)
    builder = (build_bootstrap_manifest if args.stage == "bootstrap"
               else build_certification_manifest)
    manifest = builder(corpus)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    publish_json(path, manifest.to_dict())
    return {"status": "prepared", "manifest": str(path),
            "manifest_hash": manifest.manifest_hash,
            "task_count": len(manifest.to_dict()["tasks"]),
            "stage": args.stage, "research_launched": False,
            "source_commit_verified": True, "admission_record": False}


def initialize_budget(args):
    ledger = ResearchBudget.create(_external(args.ledger), session_id=args.session,
                                   plan_sha256=PLAN_SHA256)
    return {"status": "initialized", "ledger": str(ledger.path),
            "budget": ledger.status(), "research_launched": False}


def budget_status(args):
    path = _external(args.ledger)
    if not path.is_file():
        raise ResearchCLIError("explicit research ledger does not exist")
    ledger = ResearchBudget(path, session_id=args.session)
    result = ledger.status()
    if result["state"]["plan_sha256"] != PLAN_SHA256:
        raise ResearchCLIError("ledger belongs to a different frozen plan")
    return {"status": "accounting", "ledger": str(path), "budget": result}


def audit(args):
    from research.harness.lab_proof_task import ArtifactStore

    manifest = _manifest(args.manifest)
    directory = _external(args.output_dir)
    return {"status": "audited", "manifest_hash": manifest.manifest_hash,
            "source_commit_verified": True,
            "artifacts": _audit_completed(manifest, _worker(), directory,
                                           ArtifactStore(directory / "artifacts"), required=True),
            "admission_record": False}


def run(args):
    from research.harness.lab_proof_jobs import verify_runtime_source
    from research.harness.lab_proof_task import ArtifactStore

    manifest = _manifest(args.manifest)
    frozen = manifest.to_dict()
    execution = frozen["configuration"]["execution"]
    if frozen["configuration"]["stage"] != "bootstrap" or execution is None:
        raise ResearchCLIError("certification execution requires a separately frozen measured cohort")
    directory = _external(args.output_dir)
    checkpoint_exists = (directory / "supervisor-checkpoint.json").exists()
    if checkpoint_exists and not args.resume:
        raise ResearchCLIError("existing checkpoint requires explicit --resume")
    if args.resume and not checkpoint_exists:
        raise ResearchCLIError("cannot resume an absent checkpoint")
    reconciliation = _reconciliation(args.reconcile_json)
    if reconciliation is not None and not args.resume:
        raise ResearchCLIError("reconciliation is valid only with --resume")
    worker = _worker()
    store = ArtifactStore(directory / "artifacts")
    prior_audit = _audit_completed(manifest, worker, directory, store)
    accounting = budget_status(args)
    ledger = ResearchBudget(accounting["ledger"], session_id=args.session)
    if accounting["budget"]["overrun"]:
        raise ResearchCLIError("prior budget overrun blocks all dependent launches")
    if accounting["budget"]["requires_reconciliation"] and reconciliation is None:
        raise ResearchCLIError("foreign active research lease requires explicit reconciliation")
    try:
        with _run_context(store.root) as cancelled:
            result = run_supervised(
                manifest, worker, output_dir=directory, budget=ledger,
                job_id=args.job, kind="proof",
                projected_seconds=execution["cohort_timeout"], measurement=BOOTSTRAP_MEASUREMENT,
                workers=execution["workers"], task_timeout=execution["task_timeout"],
                cohort_timeout=execution["cohort_timeout"], cancelled=cancelled,
                reconcile=reconciliation, term_grace=TERM_GRACE,
                kill_grace=KILL_GRACE, reap_timeout=REAP_TIMEOUT,
            )
        final_audit = _audit_completed(manifest, worker, directory, store, required=True)
        operational = result.to_dict()
        response = {"status": operational["status"], "run": operational,
                    "prior_artifact_audit": prior_audit, "artifact_audit": final_audit,
                    "source_commit_verified": True, "research_bootstrap_run": True,
                    "budget": ledger.status(), "admission_record": False}
        store.put_operational({"kind": "coordinator-report", "job_id": args.job,
                               "manifest_hash": manifest.manifest_hash, "report": response})
        return response
    finally:
        verify_runtime_source(frozen["source"])


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    prepared = sub.add_parser("prepare", help="Authenticate frozen bytes and write an immutable job manifest only")
    prepared.add_argument("--stage", choices=("bootstrap", "certification"), default="bootstrap")
    prepared.add_argument("--corpus", required=True)
    prepared.add_argument("--output-dir", required=True)
    prepared.set_defaults(callback=prepare)
    initialize = sub.add_parser("init-budget", help="Create an explicit ledger; never reset an existing one")
    initialize.add_argument("--ledger", required=True)
    initialize.add_argument("--session", required=True)
    initialize.set_defaults(callback=initialize_budget)
    status = sub.add_parser("status", help="Read and conservatively reconcile elapsed active accounting")
    status.add_argument("--ledger", required=True)
    status.add_argument("--session", required=True)
    status.set_defaults(callback=budget_status)
    audited = sub.add_parser("audit", help="Verify completed checkpoint artifacts without running proofs")
    audited.add_argument("--manifest", required=True)
    audited.add_argument("--output-dir", required=True)
    audited.set_defaults(callback=audit)
    executed = sub.add_parser("run", help="Run only the frozen bootstrap through the bounded supervisor")
    executed.add_argument("--manifest", required=True)
    executed.add_argument("--output-dir", required=True)
    executed.add_argument("--ledger", required=True)
    executed.add_argument("--session", required=True)
    executed.add_argument("--job", required=True)
    executed.add_argument("--resume", action="store_true")
    executed.add_argument("--reconcile-json")
    executed.set_defaults(callback=run)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        value = args.callback(args)
    except (ValueError, OSError, RuntimeError) as error:
        print(canonical_json({"status": "blocked", "error": type(error).__name__,
                              "message": str(error), "admission_record": False}))
        return 2
    print(canonical_json(value))
    return 0 if value["status"] in ("prepared", "initialized", "accounting", "audited", "complete") else 3


if __name__ == "__main__":
    raise SystemExit(main())
