"""MCTS orchestration on small synthetic graphs, never real game research."""

from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from research.harness.lab_budget import ResearchBudget
from research.harness.lab_fixed_tasks import FixedTaskManifest, run_fixed_tasks
from research.harness.lab_supervisor import Reconciliation, TrustedWorker, run_supervised
from research.harness.lab_terminal_cert import (
    TerminalProvider, action_id, canonical_hash, canonical_json,
)


RECIPES = ("lab-uct-0.1", "lab-reserved-0.1", "lab-terminal-proof-0.1")
POLICIES = ("uniform", "light")
ROOT = Path(__file__).resolve().parents[1]


def synthetic_provider():
    """Independent finite graph with oriented alternatives and conserved seats."""
    ordinary = {"B": "first", "W": "second"}
    swapped = {"B": "second", "W": "first"}
    graph = {
        "root": {"actor": "B", "seats": ordinary, "edges": [
            ({"action": "construct", "face": [0, 0], "orientation": 0}, "a"),
            ({"action": "construct", "face": [0, 0], "orientation": 1}, "b"),
            ({"action": "swap"}, "s"),
        ]},
        "a": {"actor": "W", "seats": ordinary, "edges": [
            ({"action": "play", "point": [1, 0]}, "win"),
            ({"action": "pass"}, "loss"),
        ]},
        "b": {"actor": "W", "seats": ordinary, "edges": [
            ({"action": "pass"}, "draw"),
        ]},
        "s": {"actor": "W", "seats": swapped, "edges": [
            ({"action": "play", "point": [2, 0]}, "swapped-win"),
            ({"action": "pass"}, "swapped-loss"),
        ]},
        "win": {"seats": ordinary, "score": {"B": 3, "W": 0}},
        "loss": {"seats": ordinary, "score": {"B": 0, "W": 3}},
        "draw": {"seats": ordinary, "score": {"B": 2, "W": 2}},
        "swapped-win": {"seats": swapped, "score": {"B": 0, "W": 3}},
        "swapped-loss": {"seats": swapped, "score": {"B": 3, "W": 0}},
    }
    # JSON-normalize tuples in the authored synthetic edge table.
    identity_graph = {
        name: row | {"edges": [[wire, target] for wire, target in row.get("edges", [])]}
        for name, row in graph.items()
    }
    graph_hash = canonical_hash(identity_graph)

    def actor(state):
        row = graph[state["node"]]
        color = row.get("actor")
        return {"color": color, "seat": row["seats"][color] if color else None}

    def legal(state):
        return [deepcopy(wire) for wire, _ in graph[state["node"]].get("edges", [])]

    def transition(state, wire):
        for candidate, target in graph[state["node"]].get("edges", []):
            if action_id(candidate) == action_id(wire):
                return {"node": target, "history": state["history"] + [state["node"]]}
        raise ValueError("illegal synthetic action")

    return TerminalProvider(
        provider_id="synthetic-mcts-worker-0.1", rules_id="synthetic-only",
        rules_revision="0.1", rules_hash=graph_hash,
        implementation_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        fingerprint=lambda state: canonical_hash({"graph": graph_hash, "state": state}),
        snapshot=lambda state: deepcopy(state),
        metadata=lambda state: {"origin": "synthetic", "full_history_verified": False},
        actor=actor,
        seats=lambda state: deepcopy(graph[state["node"]]["seats"]),
        accepted=lambda state: "score" in graph[state["node"]],
        score=lambda state: deepcopy(graph[state["node"]]["score"]),
        legal_actions=legal, transition=transition,
    )


def synthetic_search_callback(task):
    """Trusted callback; this function cannot instantiate a production game."""
    from research.harness.lab_mcts import search

    payload = task["payload"]
    time.sleep(payload.get("delay", 0))
    provider = synthetic_provider()
    if payload.get("fault") == "mutation":
        def mutate(state):
            state["history"].append("illegal callback mutation")
            raise ValueError("synthetic secondary callback exception")
        provider = replace(provider, legal_actions=mutate)
    result = search(
        {"node": "root", "history": []}, provider,
        recipe=payload["recipe"], policy=payload["policy"],
        simulations=16, seed=payload["seed"], rollout_limit=16,
        cancelled=(lambda: True) if payload.get("cancel_search") else None,
    )
    return {"synthetic": True, "search": result.canonical_dict()}


class TestLabMCTSWorkers(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.sources = {
            "synthetic-worker": Path(__file__).resolve(),
            "mcts": ROOT / "research/harness/lab_mcts.py",
            "terminal-provider": ROOT / "research/harness/lab_terminal_cert.py",
            "worker-protocol": ROOT / "research/harness/lab_worker.py",
            "supervisor": ROOT / "research/harness/lab_supervisor.py",
            "fixed-tasks": ROOT / "research/harness/lab_fixed_tasks.py",
            "budget": ROOT / "research/harness/lab_budget.py",
        }
        self.worker = TrustedWorker(module="engine.test_lab_mcts_workers",
                                    function="synthetic_search_callback", sources=self.sources)

    def manifest(self, *, fault=None, cancel_search=False):
        tasks = [
            {"id": f"synthetic-{index:02d}", "payload": {
                "recipe": recipe, "policy": policy, "seed": index,
                "delay": 0.08 if index == 0 else 0,
                "fault": fault, "cancel_search": cancel_search,
            }}
            for index, (recipe, policy) in enumerate(
                [(recipe, policy) for _replicate in range(2)
                 for recipe in RECIPES for policy in POLICIES]
            )
        ]
        return FixedTaskManifest.create(
            source={"commit": "136312eda4d201b5883a80c87a6b608bd8668035",
                    "hashes": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for name, path in self.sources.items()}},
            configuration={"synthetic": True, "real_game_search": False,
                           "recipes": list(RECIPES), "policies": list(POLICIES)},
            tasks=tasks,
        )

    def supervised(self, manifest, name, *, workers=1, budget=None, cancelled=None, reconcile=None):
        if budget is None:
            budget = ResearchBudget.create(self.path / f"{name}-budget.json",
                                           session_id=name, plan_sha256="0" * 64)
        result = run_supervised(
            manifest, self.worker, output_dir=self.path / name, budget=budget,
            job_id=f"{name}-{len(budget.status()['state']['jobs'])}", kind="calibration",
            projected_seconds=40,
            measurement="Disposable synthetic MCTS engineering; no game throughput claim.",
            workers=workers, task_timeout=15, cohort_timeout=40, reap_timeout=0.1,
            cancelled=cancelled, reconcile=reconcile,
        )
        accounting = budget.status()
        self.assertFalse(accounting["active_jobs"])
        self.assertEqual(accounting["active_workers"], 0)
        self.assertFalse(accounting["overrun"])
        return result, budget

    def test_completed_canonical_results_match_one_two_eight_workers(self):
        manifest = self.manifest()
        results = []
        for workers in (1, 2, 8):
            result, _ = self.supervised(manifest, f"workers-{workers}", workers=workers)
            data = result.to_dict()
            self.assertTrue(data["complete"], data)
            self.assertEqual(len(data["completed"]), 12)
            self.assertEqual(data["remaining_ids"], [])
            for row in data["completed"]:
                search = row["result"]["search"]
                self.assertNotIn("timing", search)
                self.assertEqual(search["status"], "complete")
                self.assertIsNotNone(search["selected_action"])
                self.assertFalse(search["admission_record"])
                work = search["work"]
                self.assertEqual(work["completed_iterations"],
                                 work["terminal_simulations"] + work["exact_proof_returns"])
            results.append(result.canonical_results_hash)
        self.assertEqual(len(set(results)), 1)

    def test_cancelled_fixed_checkpoint_resumes_to_same_semantic_results(self):
        manifest = self.manifest()
        calls = []

        def callback(task):
            calls.append(task["id"])
            return synthetic_search_callback(task)

        path = self.path / "partial.json"
        partial = run_fixed_tasks(manifest, callback, checkpoint_path=path,
                                  cancelled=lambda: len(calls) == 2)
        self.assertEqual(partial.to_dict()["reason"], "cancelled")
        self.assertEqual(len(partial.to_dict()["completed"]), 2)
        resumed = run_fixed_tasks(manifest, callback, checkpoint_path=path)
        direct = run_fixed_tasks(manifest, synthetic_search_callback,
                                 checkpoint_path=self.path / "direct.json")
        self.assertTrue(resumed.to_dict()["complete"])
        self.assertEqual(len(calls), 12)
        self.assertEqual(resumed.canonical_results_hash, direct.canonical_results_hash)
        self.assertEqual(canonical_json(resumed.to_dict()["completed"]),
                         canonical_json(direct.to_dict()["completed"]))

    def test_supervisor_cancel_before_entry_is_resumable_without_duplicate_search(self):
        manifest = self.manifest()
        first, budget = self.supervised(manifest, "resume", cancelled=lambda: True)
        self.assertEqual(first.to_dict()["status"], "cancelled")
        self.assertEqual(first.to_dict()["completed"], [])
        blocked, _ = self.supervised(manifest, "resume", workers=2, budget=budget)
        self.assertEqual(blocked.to_dict()["reason"], "reconciliation-required")
        self.assertEqual(blocked.to_dict()["completed"], [])
        receipt = Reconciliation(
            attempt_nonces=(), job_ids=(first.to_dict()["cohorts"][0]["id"],),
            reason="Synthetic pre-entry cancellation: no worker started; closed ledger confirmed.",
        )
        resumed, _ = self.supervised(manifest, "resume", workers=2, budget=budget,
                                     reconcile=receipt)
        direct, _ = self.supervised(manifest, "direct", workers=1)
        self.assertTrue(resumed.to_dict()["complete"], resumed.to_dict())
        self.assertEqual(resumed.canonical_results_hash, direct.canonical_results_hash)

    def test_recipe_tamper_is_not_hidden_by_recomputed_manifest_envelope(self):
        original = self.manifest().to_dict()
        payload = deepcopy(original["tasks"][0]["payload"])
        payload["recipe"] = "lab-unknown-0.1"
        forged = FixedTaskManifest.create(
            source=original["source"], configuration=original["configuration"],
            tasks=[{"id": "forged-recipe", "payload": payload}],
        )
        result, budget = self.supervised(forged, "bad-recipe")
        self.assertEqual(result.to_dict()["status"], "blocked")
        self.assertEqual(result.to_dict()["completed"], [])
        before = budget.status()["state"]["jobs"]
        repeated, _ = self.supervised(forged, "bad-recipe", budget=budget)
        self.assertEqual(repeated.to_dict()["status"], "blocked")
        self.assertEqual(budget.status()["state"]["jobs"], before)

    def test_completed_task_is_not_confused_with_an_admitted_search(self):
        # The coordinator completed its callback; the cancelled search did not
        # complete any decision. Production admission must inspect that status.
        result, _ = self.supervised(self.manifest(cancel_search=True), "cancel-search", workers=2)
        self.assertTrue(result.to_dict()["complete"], result.to_dict())
        for row in result.to_dict()["completed"]:
            search = row["result"]["search"]
            self.assertEqual(search["status"], "incomplete")
            self.assertIsNone(search["selected_action"])
            self.assertFalse(search["admission_record"])
            self.assertEqual(search["work"]["completed_iterations"], 0)

    def test_manifest_internal_tamper_is_rejected(self):
        original = self.manifest().to_dict()
        original["tasks"][0]["payload"]["policy"] = "light"
        with self.assertRaises(ValueError):
            FixedTaskManifest.from_dict(original)

    def test_core_source_tamper_rejects_before_opening_disposable_window(self):
        original = self.manifest().to_dict()
        original["source"]["hashes"]["mcts"] = "0" * 64
        forged = FixedTaskManifest.create(
            source=original["source"], configuration=original["configuration"],
            tasks=[{"id": row["id"], "payload": row["payload"]}
                   for row in original["tasks"]],
        )
        budget = ResearchBudget.create(self.path / "tamper-budget.json",
                                       session_id="tamper", plan_sha256="0" * 64)
        with self.assertRaises(ValueError):
            self.supervised(forged, "tamper", budget=budget)
        self.assertEqual(budget.status()["windows_opened"], 0)

    def test_callback_mutation_blocks_and_cannot_be_retried(self):
        manifest = self.manifest(fault="mutation")
        result, budget = self.supervised(manifest, "mutation")
        self.assertEqual(result.to_dict()["status"], "blocked")
        self.assertEqual(result.to_dict()["completed"], [])
        before = budget.status()["state"]["jobs"]
        repeated, _ = self.supervised(manifest, "mutation", budget=budget)
        self.assertEqual(repeated.to_dict()["status"], "blocked")
        self.assertEqual(budget.status()["state"]["jobs"], before)


if __name__ == "__main__":
    unittest.main()
