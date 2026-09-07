"""Independent proof-job invariants over authored synthetic finite graphs only.

No fixture below instantiates a Varde game or performs actual-game proof work.
Provider implementations are deliberately distinct while their action semantics
are identical, so cross-mechanics comparisons cannot rely on equal fingerprints.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.harness import lab_proof_task as task_module  # noqa: E402
from research.harness import lab_proof_jobs as jobs  # noqa: E402
from research.harness.lab_proof_producer import produce_certificate  # noqa: E402
from research.harness.lab_terminal_cert import check_certificate  # noqa: E402
from research.harness.lab_terminal_cert import TerminalProvider  # noqa: E402


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def action(orientation):
    return {"action": "construct", "face": [1, -1], "orientation": orientation}


class SyntheticMechanics:
    """Explicit one-step graphs; no evaluator, minimax, or game-rule imports."""

    def __init__(self, identity, scores=((1, 0), (0, 1)), *, root_color="B", swap=False):
        self.identity = identity
        self.scores = tuple(scores)
        self.root_color = root_color
        self.swap = swap
        self.root = {"node": "root", "trail": [], "implementation": identity}
        self.events = []

    def seats(self, state):
        if state["node"] != "root" and self.swap:
            return {"B": "S2", "W": "S1"}
        return {"B": "S1", "W": "S2"}

    def legal(self, state):
        self.events.append(("legal", state["node"]))
        return [action(index) for index in range(len(self.scores))] if state["node"] == "root" else []

    def transition(self, state, wire):
        self.events.append(("transition", state["node"], canonical(wire)))
        if state["node"] != "root" or wire not in self.legal(state):
            raise ValueError("invalid authored synthetic edge")
        return {"node": str(wire["orientation"]), "trail": [deepcopy(wire)],
                "implementation": self.identity}

    def score(self, state):
        self.events.append(("score", state["node"]))
        if state["node"] == "root":
            raise AssertionError("synthetic nonterminal scoring is forbidden")
        black, white = self.scores[int(state["node"])]
        return {"B": black, "W": white}

    def provider(self):
        def actor(state):
            if state["node"] != "root":
                return {"color": None, "seat": None}
            return {"color": self.root_color, "seat": self.seats(state)[self.root_color]}
        return TerminalProvider(
            provider_id=f"independent-proof-job-fixture-{self.identity}",
            rules_id="synthetic-proof-job", rules_revision="0.1",
            rules_hash=digest("explicit-authored-graph"), implementation_hash=digest(self.identity),
            fingerprint=digest, snapshot=deepcopy,
            metadata=lambda _state: {"provenance": {"full_action_replay": False},
                                    "scope": "synthetic-engineering-only"},
            actor=actor, seats=self.seats,
            accepted=lambda state: state["node"] != "root", score=self.score,
            legal_actions=self.legal, transition=self.transition,
        )


class TestLabProofJobIndependentInvariants(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def execute(self, production=None, independent=None, **options):
        production = production or SyntheticMechanics("production")
        independent = independent or SyntheticMechanics("independent")
        before = deepcopy((production.root, independent.root))
        result = task_module.execute_paths(
            production.root, production.provider(),
            independent_root=independent.root, independent_provider=independent.provider(),
            store=task_module.ArtifactStore(self.directory),
            **({"producer_nodes": 32, "checker_nodes": 128} | options),
        )
        self.assertEqual((production.root, independent.root), before)
        self.assertFalse(result["independently_certified"])
        return result

    def report(self, mechanics, *, node_limit=32, checker_limit=128):
        provider = mechanics.provider()
        produced = produce_certificate(mechanics.root, provider, node_limit=node_limit)
        return check_certificate(produced.certificate, mechanics.root, provider,
                                 node_limit=checker_limit).to_dict()

    def test_complete_disjoint_implementation_paths_agree_without_origin_promotion(self):
        production, independent = SyntheticMechanics("production"), SyntheticMechanics("independent")
        self.assertNotEqual(production.provider().fingerprint(production.root),
                            independent.provider().fingerprint(independent.root))
        result = self.execute(production, independent)
        comparison = result["comparison"]
        self.assertEqual(comparison["status"], "independent-complete")
        self.assertTrue(comparison["independent_complete"])
        self.assertEqual(comparison["root_class"], "discriminating")
        self.assertEqual(comparison["optimal_action_ids"], [canonical(action(0))])

    def test_equivalent_win_margins_remain_complete_equal_action_sets(self):
        result = self.execute(SyntheticMechanics("production", ((1, 0), (900, 0))),
                              SyntheticMechanics("independent", ((20, 0), (2, 0))))
        comparison = result["comparison"]
        self.assertTrue(comparison["independent_complete"])
        self.assertEqual(comparison["root_class"], "all-actions-equivalent")
        self.assertEqual(set(comparison["optimal_action_ids"]), {canonical(action(0)), canonical(action(1))})

    def test_original_white_seat_becomes_black_and_retains_objective(self):
        result = self.execute(SyntheticMechanics("production", root_color="W", swap=True),
                              SyntheticMechanics("independent", root_color="W", swap=True))
        self.assertEqual(result["comparison"]["optimal_action_ids"], [canonical(action(0))])
        self.assertTrue(result["comparison"]["independent_complete"])

    def test_every_checker_receives_its_own_mechanics_certificate(self):
        checked = []
        def check(certificate, root, provider, **options):
            checked.append((certificate.to_dict()["provider"], provider.identity()))
            self.assertEqual(certificate.to_dict()["provider"], provider.identity())
            return check_certificate(certificate, root, provider, **options)
        with patch.object(task_module, "check_certificate", check):
            self.execute()
        self.assertEqual(len(checked), 2)
        self.assertNotEqual(checked[0][0], checked[1][0])

    def test_partial_production_or_checker_exhaustion_never_becomes_complete(self):
        for options in ({"producer_nodes": 1}, {"checker_nodes": 1}):
            with self.subTest(options=options):
                result = self.execute(**options)
                self.assertFalse(result["comparison"]["independent_complete"])
                self.assertEqual(result["comparison"]["status"], "independent-partial")

    def test_checker_cancelled_before_root_envelope_remains_unknown(self):
        stop = [False]
        def produce(root, provider, **options):
            result = produce_certificate(root, provider, **options)
            stop[0] = True
            return result
        with patch.object(task_module, "produce_certificate", produce):
            result = self.execute(cancelled=lambda: stop[0])
        self.assertFalse(result["comparison"]["independent_complete"])
        self.assertEqual(result["comparison"]["status"], "independent-partial")

    def test_final_clock_callback_cannot_mutate_original_root_without_detection(self):
        production, independent = SyntheticMechanics("production"), SyntheticMechanics("independent")
        mutated = [False]
        def clock():
            if sum(event[0] == "score" for event in independent.events) >= 4 and not mutated[0]:
                production.root["trail"].append("outside-clone mutation")
                mutated[0] = True
            return 0.0
        with self.assertRaises(task_module.ProofTaskIntegrityError):
            task_module.execute_paths(production.root, production.provider(),
                independent_root=independent.root, independent_provider=independent.provider(),
                store=task_module.ArtifactStore(self.directory), producer_nodes=32,
                checker_nodes=128, clock=clock)
        self.assertTrue(mutated[0])

    def test_missing_independent_mechanics_stays_unqualified_despite_exact_result(self):
        mechanics = SyntheticMechanics("production")
        result = task_module.execute_paths(mechanics.root, mechanics.provider(),
                                          store=task_module.ArtifactStore(self.directory),
                                          producer_nodes=32, checker_nodes=128)
        self.assertEqual(result["comparison"]["status"], "unqualified-shared-mechanics")
        self.assertFalse(result["comparison"]["independent_complete"])
        self.assertFalse(result["independently_certified"])

    def test_accepted_and_single_choice_roots_never_fill_independent_quota(self):
        for accepted in (False, True):
            with self.subTest(accepted=accepted):
                production = SyntheticMechanics("production", ((0, 0),))
                independent = SyntheticMechanics("independent", ((0, 0),))
                if accepted:
                    production.root["node"] = "0"
                    independent.root["node"] = "0"
                result = self.execute(production, independent)
                self.assertFalse(result["comparison"]["independent_complete"])
                if accepted:
                    self.assertEqual(result["comparison"]["root_class"], "terminal")
                else:
                    self.assertEqual(result["comparison"]["root_class"], "all-actions-equivalent")

    def test_checked_wdl_or_complete_action_domain_disagreement_is_integrity_failure(self):
        variants = (
            (SyntheticMechanics("production", ((1, 0), (1, 0))),
             SyntheticMechanics("independent", ((0, 1), (0, 1)))),
            (SyntheticMechanics("production"),
             SyntheticMechanics("independent", ((1, 0), (0, 1), (0, 0)))),
        )
        for production, independent in variants:
            with self.subTest(independent=independent.scores), self.assertRaises(task_module.ProofTaskIntegrityError):
                self.execute(production, independent)

    def test_one_partial_report_is_unknown_not_a_fabricated_disagreement(self):
        production, independent = SyntheticMechanics("production"), SyntheticMechanics("independent")
        first = self.report(production)
        second = self.report(independent, node_limit=1)
        result = task_module.compare_reports(first, second,
            production_domain=production.legal(production.root),
            independent_domain=independent.legal(independent.root),
            objective={"kind": "accepted-terminal-wdl", "seat": "S1"})
        self.assertEqual(result["status"], "independent-partial")
        self.assertFalse(result["independent_complete"])

    def test_comparison_rejects_type_aliases_and_dropped_action_orientation(self):
        production, independent = SyntheticMechanics("production"), SyntheticMechanics("independent")
        first, second = self.report(production), self.report(independent)
        options = {"production_domain": production.legal(production.root),
                   "independent_domain": independent.legal(independent.root),
                   "objective": {"kind": "accepted-terminal-wdl", "seat": "S1"}}
        for change in ("verified", "bounds", "orientation"):
            altered = deepcopy(second)
            if change == "verified":
                altered["verified"] = 1
            elif change == "bounds":
                altered["root_bounds"] = [True, True]
            else:
                altered["action_results"][0]["action"].pop("orientation")
            with self.subTest(change=change), self.assertRaises(ValueError):
                task_module.compare_reports(first, altered, **options)

    def test_equal_but_contradictory_complete_reports_cannot_choose_a_proven_loss(self):
        production, independent = SyntheticMechanics("production"), SyntheticMechanics("independent")
        first, second = self.report(production), self.report(independent)
        for report in (first, second):
            report["root_bounds"] = [-1, -1]
            report["root_value"] = -1
            report["optimal_action_ids"] = [canonical(action(1))]
        with self.assertRaises(ValueError):
            task_module.compare_reports(first, second,
                production_domain=production.legal(production.root),
                independent_domain=independent.legal(independent.root),
                objective={"kind": "accepted-terminal-wdl", "seat": "S1"})

    def test_invalid_limits_and_incomplete_provider_pair_are_rejected(self):
        for options in ({"producer_nodes": True}, {"checker_nodes": 1.0},
                        {"producer_nodes": 10001}, {"checker_nodes": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.execute(**options)
        mechanics = SyntheticMechanics("production")
        with self.assertRaises(ValueError):
            task_module.execute_paths(mechanics.root, mechanics.provider(),
                independent_root=deepcopy(mechanics.root),
                store=task_module.ArtifactStore(self.directory))

    def test_resealed_matching_reports_cannot_invert_unchanged_certificate_actions(self):
        result = self.execute()
        store = task_module.ArtifactStore(self.directory)
        changed = deepcopy(result)
        for path in changed["paths"].values():
            report = store.read_json(path["checker"])
            for row in report["action_results"]:
                row["bounds"] = [-value for value in row["bounds"]]
            report["optimal_action_ids"] = [canonical(action(1))]
            # Root remains an exact win, but the report now attributes that win
            # to the certificate's exact losing move. Both reports still agree.
            path["checker"] = store.put_json(report)
        changed["comparison"]["optimal_action_ids"] = [canonical(action(1))]
        changed.pop("result_hash")
        changed["result_hash"] = digest(changed)
        with patch.object(task_module, "produce_certificate") as produce, \
                patch.object(task_module, "check_certificate") as check, \
                self.assertRaises(task_module.ProofTaskIntegrityError):
            task_module.audit_result(changed, store)
        produce.assert_not_called()
        check.assert_not_called()

    def test_artifact_roundtrip_is_content_addressed_detached_and_hash_exact(self):
        store = task_module.ArtifactStore(self.directory)
        value = {"scope": "synthetic", "nested": [1, {"orientation": 1}]}
        original = deepcopy(value)
        ref = store.put_json(value)
        self.assertEqual(set(ref), {"content_id", "bytes", "sha256"})
        self.assertEqual(ref, store.put_json(deepcopy(value)))
        data = store.read(ref)
        self.assertEqual(len(data), ref["bytes"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), ref["sha256"])
        value["nested"].clear()
        returned = store.read_json(ref)
        self.assertEqual(returned, original)
        returned["nested"].clear()
        self.assertEqual(store.read_json(ref), original)
        store.audit(ref)

    def test_artifact_references_reject_traversal_type_aliases_corruption_and_missing(self):
        store = task_module.ArtifactStore(self.directory)
        ref = store.put_json({"safe": True})
        for changed in ({"content_id": "../outside.json"}, {"content_id": str(self.directory / "absolute.json")},
                        {"bytes": True}, {"bytes": float(ref["bytes"])}, {"sha256": "0" * 64}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                store.audit(ref | changed)
        filename = self.directory / ref["content_id"]
        filename.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            store.audit(ref)
        filename.unlink()
        with self.assertRaises(ValueError):
            store.audit(ref)

    def test_artifact_store_cannot_follow_external_symlink_or_use_repository_root(self):
        store = task_module.ArtifactStore(self.directory)
        ref = store.put_json({"safe": True})
        filename = self.directory / ref["content_id"]
        contents = filename.read_bytes()
        filename.unlink()
        with TemporaryDirectory() as external:
            escaped = Path(external) / "same-bytes.json"
            escaped.write_bytes(contents)
            filename.symlink_to(escaped)
            with self.assertRaises(ValueError):
                store.audit(ref)
        with self.assertRaises(ValueError):
            task_module.ArtifactStore(Path(__file__).resolve().parents[1])

    def test_rejected_repository_store_must_not_attempt_directory_creation(self):
        forbidden = Path(__file__).resolve().parents[1] / "never-create-proof-test-artifacts"
        with patch.object(Path, "mkdir", side_effect=AssertionError("write attempted before validation")):
            with self.assertRaises(ValueError):
                task_module.ArtifactStore(forbidden)

    def test_nonfinite_artifacts_and_mismatching_existing_content_fail_closed(self):
        store = task_module.ArtifactStore(self.directory)
        for value in (float("nan"), float("inf"), {"x": float("-inf")}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                store.put_json(value)
        value = {"safe": True}
        ref = store.put_json(value)
        (self.directory / ref["content_id"]).write_bytes(b"other")
        with self.assertRaises(ValueError):
            store.put_json(value)


class TestLabProofJobSelectionInvariants(unittest.TestCase):
    def row(self, identifier, *, rules="classic", n=3, split="development", disposition="candidate"):
        return {"id": identifier, "rules_id": rules, "n": n, "split": split, "disposition": disposition}

    def test_bootstrap_preserves_all_cells_fixed_order_missing_slots_and_lexical_choice(self):
        rows = [self.row("z"), self.row("a"), self.row("0-holdout", split="holdout"),
                self.row("0-excluded", split=None, disposition="single-action")]
        before = deepcopy(rows)
        selected = jobs.select_bootstrap_rows(rows)
        self.assertEqual(selected, jobs.select_bootstrap_rows(list(reversed(rows))))
        self.assertEqual(rows, before)
        self.assertEqual(len(selected), 32)
        order = ("classic", "rosette", "breath", "breath-run", "gjerde", "gjerde-go",
                 "line-breath", "gjerde-majority", "breath-connection", "junction-y", "junction-six",
                 "junction-planted", "junction-passage", "go-honeycomb", "go-static-six", "go-static-y")
        self.assertEqual([(row["rules_id"], row["n"]) for row in selected],
                         [(rules, n) for n in (3, 4) for rules in order])
        self.assertEqual([row["slot"] for row in selected], list(range(32)))
        self.assertEqual(selected[0]["candidate_id"], "a")
        self.assertEqual(sum(row["candidate_id"] is None for row in selected), 31)

    def test_certification_round_robin_does_not_exhaust_one_ruleset_first(self):
        rows = [self.row("a"), self.row("b", split="holdout"), self.row("c", n=4),
                self.row("d", rules="breath"), self.row("e", rules="breath", n=4)]
        self.assertEqual(jobs.select_certification_rows(rows), ("a", "d", "b", "e", "c"))
        self.assertEqual(jobs.select_certification_rows(rows), jobs.select_certification_rows(list(reversed(rows))))

    def test_selector_rejects_type_aliases_duplicate_ids_and_untrusted_extra_fields(self):
        for rows in ([self.row("a", n=True)], [self.row("a", n=3.0)],
                     [self.row("a"), self.row("a")], [self.row("a", rules="../../import")],
                     [self.row("a") | {"command": "do-not-execute"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                jobs.select_bootstrap_rows(rows)
        with self.assertRaises(ValueError):
            jobs.build_bootstrap_manifest({"candidates": []})

    def missing_task(self):
        source = {"commit": "1" * 40, "hashes": {name: "a" * 64 for name in jobs.SOURCE_PATHS}}
        payload = {"format": "varde-lab-proof-task", "version": 1, "stage": "bootstrap", "slot": 0,
                   "cell": {"rules_id": "classic", "n": 3}, "corpus": jobs.corpus_identity(),
                   "source": source, "row": None, "row_hash": None,
                   "limits": {"producer_nodes": 32, "checker_nodes": 128}}
        return {"id": "bootstrap-000-classic-n3", "payload": payload, "payload_hash": digest(payload)}

    def test_task_schema_remains_strict_even_after_attacker_reseals_payload_hash(self):
        task = self.missing_task()
        with patch.object(jobs, "_compact_index", return_value={"candidates": []}):
            self.assertEqual(jobs.validate_proof_task(task), task["payload"])
            for field, value in (("version", True), ("slot", False), ("stage", "holdout"),
                                 ("limits", {"producer_nodes": 32.0, "checker_nodes": 128}),
                                 ("corpus", jobs.corpus_identity() | {"raw_sha256": "0" * 64})):
                changed = deepcopy(task)
                changed["payload"][field] = value
                changed["payload_hash"] = digest(changed["payload"])
                with self.subTest(field=field), self.assertRaises(ValueError):
                    jobs.validate_proof_task(changed)

    def test_runtime_source_validation_rejects_actual_drift_not_just_mismatching_declarations(self):
        source = self.missing_task()["payload"]["source"]
        observed = deepcopy(source["hashes"])
        observed[next(iter(observed))] = "b" * 64
        with patch.object(jobs, "runtime_source_hashes", return_value=observed):
            with self.assertRaises(ValueError):
                jobs.verify_runtime_source(source)


if __name__ == "__main__":
    unittest.main()
