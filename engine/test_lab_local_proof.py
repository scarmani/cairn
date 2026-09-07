"""Synthetic local-proof trees only: no game certification or research cohort."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "harness"))

from lab_local_proof import (  # noqa: E402
    Actor, CLAIM_LIMIT, LocalProofSpec, ProofIntegrityError, ProofProvider,
    QuantifierStep, Truth, classify_local,
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def vertex(name, *, seat="A", color="B", truth="unresolved", children=(), history=()):
    return {"name": name, "seat": seat, "color": color, "truth": truth,
            "children": list(children), "history": list(history)}


def edge(child, kind="play", **fields):
    return {"action": {"action": kind, "label": child["name"], **fields}, "child": child}


def provider(**overrides):
    def transition(state, action):
        return deepcopy(next(item["child"] for item in state["children"] if item["action"] == action))

    callbacks = dict(
        provider_hash=digest("synthetic-provider"),
        legal_actions=lambda state: tuple(item["action"] for item in state["children"]),
        transition=transition,
        fingerprint=digest,
        actor=lambda state: Actor(state["seat"], state["color"]),
        action_data=lambda action: action,
    )
    callbacks.update(overrides)
    return ProofProvider(**callbacks)


def specification(**overrides):
    fields = dict(goal_id="synthetic-property", rules_id="synthetic", rules_revision="0.1",
                  scope="Synthetic tree truth at the declared horizon; not a game fixture.")
    fields.update(overrides)
    return LocalProofSpec(**fields)


def evaluate(state, _context):
    return Truth(state["truth"])


def prove(state, spec=None, **kwargs):
    options = dict(provider=provider(), predicate=evaluate, predicate_hash=digest("synthetic-predicate"))
    options.update(kwargs)
    return classify_local(state, spec or specification(), **options)


def labels(records):
    return tuple(record.data["label"] for record in records)


class TestLabLocalProof(unittest.TestCase):
    def test_leaf_truth_partitions_every_root_and_all_equivalent_oriented_actions(self):
        root = vertex("root", children=(
            edge(vertex("win", truth="satisfied"), "construct", face=[1, 0], orientation=0),
            edge(vertex("win", truth="satisfied"), "construct", face=[1, 0], orientation=1),
            edge(vertex("lose", truth="violated")), edge(vertex("pending")),
        ))
        before = deepcopy(root)
        result = prove(root)
        self.assertEqual(len(result.action_results), 4)
        self.assertEqual(len(result.proven_actions), 2)
        self.assertEqual({record.data["orientation"] for record in result.proven_actions}, {0, 1})
        self.assertNotEqual(result.proven_actions[0].id, result.proven_actions[1].id)
        self.assertEqual(labels(result.disproven_actions), ("lose",))
        self.assertEqual(labels(result.unknown_actions), ("pending",))
        self.assertEqual((result.nodes, result.transition_attempts, result.cache_hits), (5, 4, 0))
        self.assertEqual(root, before)
        payload = result.to_dict()
        self.assertEqual(payload["claim_limit"], CLAIM_LIMIT)
        self.assertEqual(payload["horizon"], 1)
        self.assertEqual(payload["root_action_enumerations"], 1)
        self.assertNotIn("optimal_actions", payload)
        self.assertNotIn("terminal_backup", payload)

    def test_quantifiers_use_three_valued_logic_with_no_unknown_as_false(self):
        cases = (
            (("satisfied", "unresolved"), "proven", "unknown"),
            (("violated", "unresolved"), "unknown", "disproven"),
            (("satisfied", "violated"), "proven", "disproven"),
            (("satisfied", "satisfied"), "proven", "proven"),
            (("violated", "violated"), "disproven", "disproven"),
            (("unresolved", "unresolved"), "unknown", "unknown"),
        )
        for truths, existential, universal in cases:
            middle = vertex("middle", children=tuple(edge(vertex(str(index), truth=truth)) for index, truth in enumerate(truths)))
            root = vertex("root", children=(edge(middle),))
            for quantifier, expected in (("exists", existential), ("forall", universal)):
                with self.subTest(truths=truths, quantifier=quantifier):
                    result = prove(root, specification(schedule=(QuantifierStep(quantifier),)))
                    self.assertEqual(result.action_results[0].status, expected)

    def test_nested_schedule_starts_after_root_and_records_witness_and_counterexample(self):
        good = vertex("good", seat="A", children=(edge(vertex("yes", truth="satisfied")),))
        bad = vertex("bad", seat="A", children=(edge(vertex("no", truth="violated")),))
        root = vertex("root", children=(edge(vertex("reply", seat="Z", color="W", children=(edge(good), edge(bad)))),))
        spec = specification(schedule=(QuantifierStep("forall", actor="other-seat"), QuantifierStep("exists", actor="root-seat")))
        result = prove(root, spec)
        self.assertEqual(result.action_results[0].status, "disproven")
        self.assertTrue(any(trace.ply == 1 and trace.actor == Actor("Z", "W") for trace in result.traces))
        self.assertTrue(any(trace.event == "horizon" and trace.status == "disproven" and trace.ply == 3 for trace in result.traces))
        self.assertTrue(all(len(trace.state_hash) == 64 for trace in result.traces))
        self.assertTrue(all(trace.root_action_id == result.action_results[0].action.id for trace in result.traces))
        winner = prove(root, replace(spec, schedule=(QuantifierStep("exists"), QuantifierStep("exists"))))
        self.assertEqual(winner.action_results[0].status, "proven")
        self.assertTrue(any(trace.event == "horizon" and trace.status == "proven" for trace in winner.traces))

    def test_closure_is_checked_before_actor_mismatch(self):
        root = vertex("root", children=(edge(vertex("closed", seat="Z", color="W", truth="satisfied")),))
        step = QuantifierStep("exists", actor="root-seat")
        closure = prove(root, specification(schedule=(step,), evaluation_mode="closure"))
        self.assertEqual(closure.action_results[0].status, "proven")
        self.assertTrue(any(trace.event == "closure" and trace.actor.seat == "Z" for trace in closure.traces))
        horizon = prove(root, specification(schedule=(step,)))
        self.assertEqual(horizon.action_results[0].status, "unknown")
        self.assertTrue(any(trace.event == "actor-mismatch" for trace in horizon.traces))

    def test_unresolved_closure_continues_while_same_actor_retains_turn(self):
        leaf = vertex("closed", seat="Z", color="W", truth="satisfied")
        root = vertex("root", children=(edge(vertex("continue", children=(edge(leaf, "finish"),))),))
        result = prove(root, specification(schedule=(QuantifierStep("exists", actor="root-seat"),), evaluation_mode="closure"))
        self.assertEqual(result.action_results[0].status, "proven")
        self.assertEqual(result.transition_attempts, 2)

    def test_full_domains_include_administration_and_restrictions_are_explicit(self):
        middle = vertex("middle", children=(edge(vertex("yes", truth="satisfied"), "play"),
                                             edge(vertex("no", truth="violated"), "resume")))
        root = vertex("root", children=(edge(middle),))
        unrestricted = prove(root, specification(schedule=(QuantifierStep("forall"),)))
        self.assertEqual(unrestricted.action_results[0].status, "disproven")
        restricted = prove(root, specification(schedule=(QuantifierStep("forall", action_kinds=("play",)),)))
        self.assertEqual(restricted.action_results[0].status, "proven")
        self.assertEqual(restricted.to_dict()["spec"]["schedule"][0]["action_kinds"], ["play"])
        root_actions = vertex("root", children=tuple(edge(vertex(kind, truth="satisfied"), kind) for kind in (
            "pass", "swap", "construct", "plant", "accept", "resume")))
        self.assertEqual(len(prove(root_actions).proven_actions), 6)

    def test_empty_domain_default_unknown_and_explicit_vacuity(self):
        root = vertex("root", children=(edge(vertex("empty")),))
        for quantifier in ("exists", "forall"):
            result = prove(root, specification(schedule=(QuantifierStep(quantifier),)))
            self.assertEqual(result.action_results[0].status, "unknown")
            vacuous = prove(root, specification(schedule=(QuantifierStep(quantifier, empty_domain="vacuous"),)))
            self.assertEqual(vacuous.action_results[0].status, "proven" if quantifier == "forall" else "disproven")
            self.assertEqual(vacuous.to_dict()["spec"]["schedule"][0]["empty_domain"], "vacuous")

    def test_shared_node_ceiling_root_enumeration_and_exact_completion(self):
        root = vertex("root", children=tuple(edge(vertex(str(index), truth="satisfied")) for index in range(4)))
        for limit, expected_proven in ((1, 0), (3, 2), (5, 4)):
            result = prove(root, node_limit=limit)
            self.assertEqual(len(result.proven_actions), expected_proven)
            self.assertEqual(len(result.unknown_actions), 4 - expected_proven)
            self.assertEqual(result.nodes, limit)
            self.assertEqual(result.transition_attempts, limit - 1)
            self.assertEqual(result.action_enumerations, 1)
            self.assertEqual(result.actions_enumerated, 4)
            self.assertEqual(result.limit_reached, limit < 5)
        middle = vertex("middle", children=tuple(edge(vertex(str(index), truth="violated")) for index in range(3)))
        exhausted = prove(vertex("root", children=(edge(middle),)), specification(schedule=(QuantifierStep("exists"),)), node_limit=3)
        self.assertEqual(exhausted.action_results[0].status, "unknown")
        self.assertEqual(exhausted.nodes, 3)
        self.assertEqual(exhausted.transition_attempts, 2)

    def test_cancellation_keeps_complete_root_partition_and_stops_new_transitions(self):
        root = vertex("root", children=tuple(edge(vertex(str(index), truth="satisfied")) for index in range(3)))
        before = deepcopy(root)
        result = prove(root, cancelled=lambda: True)
        self.assertTrue(result.cancelled)
        self.assertEqual((result.nodes, result.transition_attempts), (1, 0))
        self.assertEqual(len(result.unknown_actions), 3)
        self.assertEqual(result.action_enumerations, 1)
        attempts = []
        original = provider()

        def transition(state, action):
            attempts.append(action)
            return original.transition(state, action)

        result = prove(root, provider=replace(original, transition=transition), cancelled=lambda: len(attempts) >= 1)
        self.assertEqual(len(result.proven_actions), 1)
        self.assertEqual(len(result.unknown_actions), 2)
        self.assertEqual(result.transition_attempts, 1)
        self.assertTrue(result.cancelled)
        self.assertEqual(root, before)
        empty = prove(vertex("empty", seat=None, color=None), cancelled=lambda: True)
        self.assertTrue(empty.cancelled)
        self.assertEqual(empty.action_results, ())
        self.assertEqual((empty.nodes, empty.action_enumerations, empty.transition_attempts), (1, 1, 0))

    def test_provider_order_does_not_change_canonical_result_or_budget_assignment(self):
        root = vertex("root", children=tuple(edge(vertex(str(index), truth="satisfied")) for index in range(5)))
        standard = provider()
        reverse = replace(standard, legal_actions=lambda state: reversed(standard.legal_actions(state)))
        self.assertEqual(prove(root, node_limit=3).to_dict(), prove(root, provider=reverse, node_limit=3).to_dict())

    def test_no_memoization_keeps_root_action_and_path_context_independent(self):
        shared = vertex("same")
        root = vertex("root", children=(edge(shared, "construct", orientation=0), edge(shared, "construct", orientation=1)))

        def root_dependent(_state, context):
            return Truth.SATISFIED if context.root_action.data["orientation"] == 1 else Truth.VIOLATED

        result = prove(root, predicate=root_dependent)
        self.assertEqual(len(result.proven_actions), 1)
        self.assertEqual(result.proven_actions[0].data["orientation"], 1)
        self.assertEqual(result.cache_hits, 0)
        changed = deepcopy(root)
        changed["history"].append("forbidden-position")
        self.assertNotEqual(prove(root).input_hash, prove(changed).input_hash)

    def test_duplicate_legal_actions_fail_even_when_success_would_short_circuit(self):
        duplicate = edge(vertex("yes", truth="satisfied"))
        for root in (vertex("root", children=(duplicate, duplicate)),
                     vertex("root", children=(edge(vertex("middle", children=(duplicate, duplicate))),))):
            with self.assertRaisesRegex(ProofIntegrityError, "duplicate legal action"):
                prove(root, specification(schedule=(QuantifierStep("exists"),)))

    def test_provider_failures_and_invalid_outputs_return_no_certificate(self):
        root = vertex("root", children=(edge(vertex("leaf")),))

        def fail(*_):
            raise ValueError("declared-legal action unexpectedly failed")

        providers = (
            provider(transition=fail), provider(legal_actions=fail),
            provider(actor=lambda _: ("A", "B")), provider(fingerprint=lambda _: "incomplete"),
            provider(action_data=lambda _: {"action": "play", "weight": float("nan")}),
            provider(action_data=lambda _: {"missing_kind": "play"}),
        )
        for item in providers:
            with self.subTest(provider=item), self.assertRaises(ProofIntegrityError):
                prove(root, provider=item)
        for predicate in (lambda *_: True, lambda *_: None, lambda *_: "proven", fail):
            with self.assertRaises(ProofIntegrityError):
                prove(root, predicate=predicate)
        with self.assertRaises(ProofIntegrityError):
            prove(root, cancelled=lambda: 1)
        with self.assertRaises(ProofIntegrityError) as caught:
            prove(root, provider=provider(transition=fail))
        self.assertEqual(caught.exception.counters["transition_attempts"], 1)
        self.assertEqual(caught.exception.counters["nodes"], 1)
        self.assertEqual(caught.exception.counters["action_enumerations"], 1)
        with self.assertRaises(TypeError):
            caught.exception.counters["nodes"] = 0

    def test_failed_partial_enumeration_preserves_yielded_action_accounting(self):
        def partial_failure(_state):
            yield {"action": "first"}
            yield {"action": "second"}
            raise ValueError("provider failed after two yields")

        with self.assertRaises(ProofIntegrityError) as caught:
            prove(vertex("root"), provider=provider(legal_actions=partial_failure))
        self.assertEqual(caught.exception.counters["action_enumerations"], 1)
        self.assertEqual(caught.exception.counters["actions_enumerated"], 2)
        self.assertEqual(caught.exception.counters["transition_attempts"], 0)

    def test_mutating_callbacks_fail_and_caller_state_is_preserved(self):
        root = vertex("root", children=(edge(vertex("leaf", truth="satisfied")),))
        original = provider()

        def mutation(callback):
            def wrapped(state, *args):
                state["history"].append("bad mutation")
                return callback(state, *args)
            return wrapped

        callbacks = ("legal_actions", "transition", "fingerprint", "actor")
        for field_name in callbacks:
            before = deepcopy(root)
            bad = replace(original, **{field_name: mutation(getattr(original, field_name))})
            with self.subTest(callback=field_name), self.assertRaises(ProofIntegrityError):
                prove(root, provider=bad)
            self.assertEqual(root, before)
        before = deepcopy(root)
        with self.assertRaises(ProofIntegrityError):
            prove(root, predicate=mutation(evaluate))
        self.assertEqual(root, before)

        def bad_action(action):
            action["orientation"] = 999
            return action

        with self.assertRaises(ProofIntegrityError):
            prove(root, provider=replace(original, action_data=bad_action))
        self.assertEqual(root, before)

        def mutating_generator(state):
            for action in original.legal_actions(state):
                yield action
                state["history"].append("mutation during iteration")

        with self.assertRaises(ProofIntegrityError):
            prove(root, provider=replace(original, legal_actions=mutating_generator))
        self.assertEqual(root, before)

        def mutating_context(_state, context):
            object.__setattr__(context, "ply", 99)
            return Truth.SATISFIED

        with self.assertRaisesRegex(ProofIntegrityError, "context"):
            prove(root, predicate=mutating_context)

    def test_same_immutable_state_can_recur_with_finite_horizon_without_memoization(self):
        cycle = ProofProvider(
            provider_hash=digest("synthetic-cycle"), legal_actions=lambda _: ("stay",),
            transition=lambda state, _: state, fingerprint=digest,
            actor=lambda _: Actor("A", "B"), action_data=lambda _: {"action": "stay"},
        )
        spec = specification(schedule=(QuantifierStep("exists"),) * 3)
        result = prove(("constant",), spec, provider=cycle, predicate=lambda *_: Truth.UNRESOLVED)
        self.assertEqual(result.action_results[0].status, "unknown")
        self.assertEqual((result.nodes, result.transition_attempts, result.cache_hits), (5, 4, 0))
        limited = prove(("constant",), spec, provider=cycle, predicate=lambda *_: Truth.UNRESOLVED, node_limit=3)
        self.assertTrue(limited.limit_reached)
        self.assertEqual((limited.nodes, limited.transition_attempts), (3, 2))

    def test_declared_deep_horizon_is_not_limited_by_python_recursion(self):
        cycle = ProofProvider(
            provider_hash=digest("synthetic-deep-cycle"), legal_actions=lambda _: ("stay",),
            transition=lambda state, _: state, fingerprint=digest,
            actor=lambda _: Actor("A", "B"), action_data=lambda _: {"action": "stay"},
        )
        spec = specification(schedule=(QuantifierStep("exists"),) * 1100)
        result = prove(("constant",), spec, provider=cycle, predicate=lambda *_: Truth.UNRESOLVED, node_limit=2000)
        self.assertEqual(result.action_results[0].status, "unknown")
        self.assertEqual((result.nodes, result.transition_attempts), (1102, 1101))
        self.assertFalse(result.limit_reached)
        limited = prove(("constant",), spec, provider=cycle, predicate=lambda *_: Truth.UNRESOLVED, node_limit=1000)
        self.assertEqual(limited.action_results[0].status, "unknown")
        self.assertEqual((limited.nodes, limited.transition_attempts), (1000, 999))
        self.assertTrue(limited.limit_reached)

    def test_metadata_results_and_wire_payloads_are_detached_and_immutable(self):
        parameters = {"anchors": [[1, 2]], "nested": {"a": "b"}}
        spec = specification(parameters=parameters)
        parameters["anchors"][0][0] = 99
        self.assertEqual(spec.parameters["anchors"], ((1, 2),))
        with self.assertRaises(TypeError):
            spec.parameters["nested"]["a"] = "c"
        with self.assertRaises(FrozenInstanceError):
            spec.goal_id = "another"
        root = vertex("root", children=(edge(vertex("yes", truth="satisfied"), "construct", face=[1, 0], orientation=1),))
        result = prove(root, spec)
        with self.assertRaises(TypeError):
            result.proven_actions[0].data["orientation"] = 2
        payload = result.to_dict()
        payload["proven_actions"][0]["data"]["face"][0] = 999
        self.assertEqual(result.proven_actions[0].data["face"], (1, 0))
        self.assertEqual(json.loads(json.dumps(result.to_dict())), result.to_dict())

    def test_declared_source_hash_is_distinct_from_rules_descriptor_hash(self):
        root = vertex("root", children=(edge(vertex("leaf")),))
        absent = prove(root).to_dict()["hashes"]
        self.assertIsNone(absent["rules"])
        self.assertEqual(len(absent["rules_descriptor"]), 64)
        declared = digest("caller-declared synthetic rules source")
        present = prove(root, specification(rules_hash=declared)).to_dict()["hashes"]
        self.assertEqual(present["rules"], declared)
        self.assertEqual(present["rules_descriptor"], absent["rules_descriptor"])
        self.assertNotEqual(present["rules"], present["rules_descriptor"])
        self.assertNotEqual(present["spec"], absent["spec"])
        with self.assertRaises(ValueError):
            specification(rules_hash="not-a-hash")

    def test_invalid_metadata_and_limits_are_rejected_before_provider_work(self):
        for fields in ({"parameters": {"bad": float("inf")}}, {"evaluation_mode": "heuristic"},
                       {"schedule": ["forall"]}, {"goal_id": ""}, {"scope": ""}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                specification(**fields)
        for fields in ({"quantifier": "maybe"}, {"quantifier": "forall", "actor": "black"},
                       {"quantifier": "exists", "empty_domain": "guess"},
                       {"quantifier": "exists", "action_kinds": ()},
                       {"quantifier": "exists", "action_kinds": ("play", "play")}):
            with self.assertRaises(ValueError):
                QuantifierStep(**fields)
        for limit in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                prove(vertex("root"), node_limit=limit)
        with self.assertRaises(ValueError):
            prove(vertex("root"), predicate_hash="invalid")


if __name__ == "__main__":
    unittest.main()
