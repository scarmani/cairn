"""Synthetic accepted-terminal graphs only; no game proofs or corpus search."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import unittest

from research.harness.lab_terminal_cert import (
    CLAIM_LIMIT, FORMAT, TerminalCertificate, TerminalIntegrityError,
    TerminalProvider, action_id, canonical_hash, check_certificate, seal_certificate,
)


def state(name, *, actor="S1", color="B", seats=None, score=None, choices=()):
    return {"name": name, "marker": 1, "accepted": score is not None,
            "actor": {"seat": actor, "color": color} if score is None else {"seat": None, "color": None},
            "seats": seats or {"B": "S1", "W": "S2"}, "score": score,
            "choices": [{"wire": wire, "next": target} for wire, target in choices]}


def fixture(states, bounds, *, objective="S1", unknown=(), unexpanded=()):
    """Serialize explicitly authored synthetic nodes/bounds, not solve a game."""
    by_name = {item["name"]: item for item in states}

    def advance(source, wire):
        target = next(item["next"] for item in source["choices"] if action_id(item["wire"]) == action_id(wire))
        return deepcopy(by_name[target])

    provider = TerminalProvider(
        provider_id="synthetic-tree-v1", rules_id="synthetic", rules_revision="0.1",
        rules_hash="a" * 64, implementation_hash="b" * 64,
        fingerprint=canonical_hash, snapshot=deepcopy,
        metadata=lambda _state: {"synthetic": True, "full_action_replay": False},
        actor=lambda source: deepcopy(source["actor"]), seats=lambda source: deepcopy(source["seats"]),
        accepted=lambda source: source["accepted"], score=lambda source: deepcopy(source["score"]),
        legal_actions=lambda source: [deepcopy(row["wire"]) for row in source["choices"]],
        transition=advance,
    )
    graph = []
    for item in states:
        kind = "terminal" if item["accepted"] else "unexpanded" if item["name"] in unexpanded else "expanded"
        edges = []
        if kind == "expanded":
            for row in item["choices"]:
                unresolved = (item["name"], action_id(row["wire"])) in unknown
                edges.append({"id": action_id(row["wire"]), "action": deepcopy(row["wire"]),
                              "child": None if unresolved else canonical_hash(by_name[row["next"]]),
                              "unresolved_reason": "not-expanded" if unresolved else None})
        graph.append({"fingerprint": canonical_hash(item), "actor": deepcopy(item["actor"]),
                      "seats": deepcopy(item["seats"]), "accepted": item["accepted"],
                      "bounds": list(bounds[item["name"]]), "kind": kind, "score": deepcopy(item["score"]),
                      "actions": edges, "unresolved_reason": "not-expanded" if kind == "unexpanded" else None})
    root = states[0]
    by_hash = {node["fingerprint"]: node for node in graph}
    payload = {"format": FORMAT, "version": 1, "provider": provider.identity(),
               "root": {"snapshot": deepcopy(root), "fingerprint": canonical_hash(root),
                        "actor": deepcopy(root["actor"]), "metadata": provider.metadata(root)},
               "objective": {"kind": "accepted-terminal-wdl", "seat": objective},
               "root_actions": [{"id": edge["id"], "bounds": by_hash[edge["child"]]["bounds"] if edge["child"] else [-1, 1]}
                                for edge in graph[0]["actions"]],
               "graph": graph, "graph_hash": "0" * 64,
               "resources": {"nodes": 900, "transition_attempts": 800, "terminal_leaves": 700, "terminal_simulation_backups": 0},
               "claim_limit": CLAIM_LIMIT}
    return provider, root, seal_certificate(payload)


def small_tree():
    states = [state("root", choices=(({"action": "sacrifice"}, "win"), ({"action": "safe"}, "draw"))),
              state("win", score={"B": 2, "W": 1}), state("draw", score={"B": 5, "W": 5})]
    return fixture(states, {"root": [1, 1], "win": [1, 1], "draw": [0, 0]})


class TestTerminalCertificate(unittest.TestCase):
    def test_equivalent_wins_keep_all_actions_despite_score_margins(self):
        provider, root, payload = fixture([
            state("root", choices=(({"action": "small"}, "small"), ({"action": "large"}, "large"))),
            state("small", score={"B": 2, "W": 1}), state("large", score={"B": 80, "W": 0}),
        ], {"root": [1, 1], "small": [1, 1], "large": [1, 1]})
        before = deepcopy((payload, root))
        certificate = TerminalCertificate.from_dict(payload)
        payload["root"]["snapshot"]["marker"] = 999
        result = check_certificate(certificate, root, provider)
        self.assertTrue(result.verified)
        self.assertTrue(result.complete_optimal_action_set)
        self.assertEqual(result.optimal_action_ids, sorted(action_id({"action": kind}) for kind in ("small", "large")))
        self.assertFalse(result.admission_record)
        self.assertEqual(root, before[1])
        detached = certificate.to_dict()
        detached["graph"].clear()
        self.assertEqual(len(certificate.to_dict()["graph"]), 3)
        report = result.to_dict()
        report["work"]["nodes_checked"] = 0
        self.assertEqual(result.work["nodes_checked"], 3)
        self.assertEqual(result.claimed_resources["nodes"], 900)
        self.assertEqual(result.work["terminal_simulation_backups"], 0)
        with self.assertRaises(FrozenInstanceError):
            provider.provider_id = "changed"

    def test_same_seat_turns_and_opponent_root_use_identity_not_depth(self):
        provider, root, payload = fixture([
            state("root", actor="S2", color="W", choices=(({"action": "continue"}, "same"), ({"action": "draw"}, "draw"))),
            state("same", actor="S2", color="W", choices=(({"action": "win"}, "win"), ({"action": "loss"}, "loss"))),
            state("win", score={"B": 8, "W": 0}), state("loss", score={"B": 0, "W": 8}),
            state("draw", score={"B": 4, "W": 4}),
        ], {"root": [-1, -1], "same": [-1, -1], "win": [1, 1], "loss": [-1, -1], "draw": [0, 0]})
        result = check_certificate(payload, root, provider)
        self.assertEqual(result.root_value, -1)
        self.assertEqual(result.optimal_action_ids, [action_id({"action": "continue"})])
        payload["graph"][1]["bounds"] = [1, 1]
        with self.assertRaises(TerminalIntegrityError):
            check_certificate(seal_certificate(payload), root, provider)

    def test_terminal_score_uses_post_takeover_color_mapping(self):
        provider, root, payload = fixture([
            state("root", choices=(({"action": "swap"}, "swapped"), ({"action": "remain"}, "draw"))),
            state("swapped", seats={"B": "S2", "W": "S1"}, score={"B": 0, "W": 2}),
            state("draw", score={"B": 0, "W": 0}),
        ], {"root": [1, 1], "swapped": [1, 1], "draw": [0, 0]})
        self.assertEqual(check_certificate(payload, root, provider).optimal_action_ids, [action_id({"action": "swap"})])

    def test_exact_root_is_not_complete_classification_with_unknown_alternative(self):
        provider, root, payload = small_tree()
        payload["graph"][0]["actions"][1].update(child=None, unresolved_reason="watchdog")
        payload["graph"] = payload["graph"][:2]
        payload["root_actions"][1]["bounds"] = [-1, 1]
        result = check_certificate(seal_certificate(payload), root, provider)
        self.assertTrue(result.verified)
        self.assertTrue(result.root_value_exact)
        self.assertEqual(result.root_value, 1)
        self.assertFalse(result.decision_classified)
        self.assertFalse(result.complete_optimal_action_set)
        self.assertEqual(result.optimal_action_ids, [])
        self.assertEqual(result.unresolved_action_ids, [action_id({"action": "safe"})])
        self.assertEqual(result.work["transition_attempts"], 2)
        self.assertEqual(result.work["unknown_successors_checked"], 1)
        self.assertEqual(result.work["terminal_scores_checked"], 1)
        exhausted = check_certificate(seal_certificate(payload), root, provider, node_limit=2)
        self.assertEqual(exhausted.status, "unknown")
        self.assertEqual(exhausted.work["nodes_checked"] + exhausted.work["unknown_successors_checked"], 2)
        self.assertFalse(exhausted.decision_classified)

    def test_terminal_and_unexpanded_roots_are_not_decisions(self):
        provider, root, payload = fixture([state("done", score={"B": 3, "W": 4})], {"done": [-1, -1]})
        result = check_certificate(payload, root, provider)
        self.assertTrue(result.terminal_root)
        self.assertEqual(result.root_value, -1)
        self.assertFalse(result.decision_classified)
        provider, root, payload = fixture([state("pending")], {"pending": [-1, 1]}, unexpanded=("pending",))
        result = check_certificate(payload, root, provider)
        self.assertTrue(result.verified)
        self.assertFalse(result.root_domain_complete)
        self.assertIsNone(result.root_value)

    def test_resource_exhaustion_is_unknown_and_preserves_actual_work(self):
        provider, root, payload = small_tree()
        for limit in (0, 1, 2):
            with self.subTest(limit=limit):
                result = check_certificate(payload, root, provider, node_limit=limit)
                self.assertFalse(result.verified)
                self.assertEqual(result.status, "unknown")
                self.assertEqual(result.reason, "node-limit")
                self.assertEqual(result.work["nodes_checked"], limit)
                self.assertIsNone(result.root_value)
                self.assertEqual(result.optimal_action_ids, [])
        result = check_certificate(payload, root, provider, cancelled=lambda: True)
        self.assertEqual(result.reason, "cancelled")
        self.assertEqual(result.work["nodes_checked"], 0)
        with self.assertRaises(ValueError):
            check_certificate(payload, root, provider, node_limit=True)

    def test_orientations_are_distinct_complete_action_ids(self):
        a = {"action": "construct", "face": [0, 0], "orientation": 0}
        b = dict(a, orientation=1)
        provider, root, payload = fixture([
            state("root", choices=((a, "win"), (b, "draw"))),
            state("win", score={"B": 2, "W": 1}), state("draw", score={"B": 1, "W": 1}),
        ], {"root": [1, 1], "win": [1, 1], "draw": [0, 0]})
        self.assertNotEqual(action_id(a), action_id(b))
        self.assertEqual(check_certificate(payload, root, provider).optimal_action_ids, [action_id(a)])
        payload["graph"][0]["actions"][1]["id"] = action_id(a)
        with self.assertRaises(ValueError):
            TerminalCertificate.from_dict(seal_certificate(payload))

    def test_bad_schema_hashes_resources_and_operational_reasons(self):
        _, _, original = small_tree()
        mutations = (
            lambda p: p.update(version=True),
            lambda p: p.update(format="varde-lab-local-proof"),
            lambda p: p.update(graph_hash="0" * 64),
            lambda p: p["resources"].update(terminal_simulation_backups=1),
            lambda p: p["resources"].update(nodes=False),
            lambda p: p["resources"].update(elapsed_ms=5),
            lambda p: p["graph"][0]["bounds"].__setitem__(0, True),
        )
        for mutate in mutations:
            payload = deepcopy(original)
            mutate(payload)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                TerminalCertificate.from_dict(payload)
        for reason in ([], {}, 0, False, None):
            payload = deepcopy(original)
            payload["graph"][0]["actions"][1].update(child=None, unresolved_reason=reason)
            payload["graph"] = payload["graph"][:2]
            payload["root_actions"][1]["bounds"] = [-1, 1]
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                TerminalCertificate.from_dict(seal_certificate(payload))
            payload = deepcopy(original)
            payload["graph"] = [payload["graph"][0]]
            payload["graph"][0].update(kind="unexpanded", actions=[], bounds=[-1, 1], unresolved_reason=reason)
            payload["root_actions"] = []
            with self.subTest(node_reason=reason), self.assertRaises(ValueError):
                TerminalCertificate.from_dict(seal_certificate(payload))

    def test_finite_json_comparison_preserves_boolean_integer_float_types(self):
        provider, root, original = small_tree()
        for value in (True, 1.0):
            payload = deepcopy(original)
            payload["root"]["snapshot"]["marker"] = value
            with self.subTest(snapshot=value), self.assertRaises(TerminalIntegrityError):
                check_certificate(payload, root, provider)
        payload = deepcopy(original)
        payload["root"]["metadata"]["full_action_replay"] = 0
        with self.assertRaises(TerminalIntegrityError):
            check_certificate(payload, root, provider)

    def test_callback_mutation_and_partial_iterator_failure_leave_root_untouched(self):
        provider, root, payload = small_tree()
        before = deepcopy(root)

        def mutating(source):
            source["marker"] += 1
            return source["actor"]

        def failed_iterator(source):
            yield source["choices"][0]["wire"]
            source["marker"] += 1
            raise RuntimeError("late iterator failure")

        def mutating_transition(source, action):
            action["injected"] = True
            raise RuntimeError("transition failure")

        for changed in (replace(provider, actor=mutating),
                        replace(provider, legal_actions=failed_iterator),
                        replace(provider, transition=mutating_transition),
                        replace(provider, snapshot=mutating)):
            with self.subTest(provider=changed), self.assertRaises(TerminalIntegrityError) as raised:
                check_certificate(payload, root, changed)
            self.assertEqual(root, before)
            self.assertGreater(raised.exception.work["callback_calls"], 0)

    def test_false_terminal_score_or_missing_action_is_not_a_certificate(self):
        provider, root, payload = small_tree()
        with self.assertRaises(TerminalIntegrityError):
            check_certificate(payload, root, replace(provider, accepted=lambda _state: True))
        wrong_score = replace(provider, score=lambda _state: {"B": 99, "W": 0})
        with self.assertRaises(TerminalIntegrityError):
            check_certificate(payload, root, wrong_score)
        missing_action = replace(provider, legal_actions=lambda source: provider.legal_actions(source)[:1])
        with self.assertRaises(TerminalIntegrityError):
            check_certificate(payload, root, missing_action)


if __name__ == "__main__":
    unittest.main()
