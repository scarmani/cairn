"""Synthetic proof production only: no actual game states or corpus searches."""

from copy import deepcopy
from dataclasses import replace
import unittest

from research.harness.lab_proof_producer import ProducerIntegrityError, produce_certificate
from research.harness.lab_terminal_cert import TerminalProvider, action_id, canonical_hash, check_certificate


def node(name, *, choices=(), actor="S1", color="B", score=None, seats=None):
    return {"name": name, "marker": 1, "accepted": score is not None,
            "actor": {"seat": actor, "color": color} if score is None else {"seat": None, "color": None},
            "seats": seats or {"B": "S1", "W": "S2"}, "score": score,
            "choices": [{"action": wire, "target": target} for wire, target in choices]}


def provider_for(nodes):
    table = {state["name"]: state for state in nodes}

    def advance(state, wire):
        name = next(row["target"] for row in state["choices"] if row["action"] == wire)
        return deepcopy(table[name])

    return TerminalProvider(
        provider_id="synthetic-proof-tree", rules_id="synthetic", rules_revision="0.1",
        rules_hash="a" * 64, implementation_hash="b" * 64,
        fingerprint=canonical_hash, snapshot=deepcopy,
        metadata=lambda _state: {"provenance": {"full_action_replay": False}, "synthetic": True},
        actor=lambda state: deepcopy(state["actor"]), seats=lambda state: deepcopy(state["seats"]),
        accepted=lambda state: state["accepted"], score=lambda state: deepcopy(state["score"]),
        legal_actions=lambda state: [deepcopy(row["action"]) for row in state["choices"]], transition=advance,
    )


def tree():
    states = [node("root", choices=(({"action": "sacrifice"}, "win"), ({"action": "rescue"}, "draw"))),
              node("win", score={"B": 2, "W": 1}), node("draw", score={"B": 5, "W": 5})]
    return states[0], provider_for(states)


class TestLabProofProducer(unittest.TestCase):
    def checked(self, states, **kwargs):
        provider = provider_for(states)
        result = produce_certificate(states[0], provider, **kwargs)
        verified = check_certificate(result.certificate, states[0], provider)
        self.assertTrue(verified.verified)
        self.assertFalse(result.telemetry["admission_record"])
        self.assertEqual(result.telemetry["work"]["terminal_simulation_backups"], 0)
        return result, verified

    def test_all_five_root_classes_roundtrip_independent_checker(self):
        terminal = node("done", score={"B": 2, "W": 1})
        cases = (
            ("terminal", [terminal], {}),
            ("forced-administrative", [node("root", choices=(({"action": "accept"}, "done"),)), terminal], {}),
            ("all-actions-equivalent", [node("root", choices=(({"action": "a"}, "done"), ({"action": "b"}, "done"))), terminal], {}),
            ("discriminating", [node("root", choices=(({"action": "a"}, "done"), ({"action": "b"}, "loss"))), terminal, node("loss", score={"B": 1, "W": 2})], {}),
            ("partial", [node("root", choices=(({"action": "a"}, "done"),)), terminal], {"node_limit": 1}),
        )
        for expected, states, kwargs in cases:
            with self.subTest(expected=expected):
                result, _ = self.checked(states, **kwargs)
                self.assertEqual(result.telemetry["root_class"], expected)

    def test_same_seat_opponent_reply_and_takeover_use_identity(self):
        states = [node("root", choices=(({"action": "continue"}, "same"), ({"action": "attack"}, "opponent"))),
                  node("same", choices=(({"action": "swap"}, "win"), ({"action": "bad"}, "loss"))),
                  node("opponent", actor="S2", color="W", choices=(({"action": "good"}, "win"), ({"action": "refute"}, "loss"))),
                  node("win", seats={"B": "S2", "W": "S1"}, score={"B": 1, "W": 3}),
                  node("loss", score={"B": 1, "W": 3})]
        result, report = self.checked(states)
        self.assertEqual(result.telemetry["optimal_action_ids"], [action_id({"action": "continue"})])
        self.assertEqual(report.root_value, 1)
        self.assertGreater(result.telemetry["work"]["memo_hits"], 0)
        self.assertEqual(result.telemetry["work"]["nodes"], 5)

    def test_equivalent_wins_and_orientations_are_never_margin_ranked(self):
        a = {"action": "plant", "face": [0, 0], "orientation": 0}
        b = dict(a, orientation=1)
        result, report = self.checked([
            node("root", choices=((b, "narrow"), (a, "wide"))),
            node("narrow", score={"B": 2, "W": 1}), node("wide", score={"B": 20, "W": 0}),
        ])
        self.assertEqual(result.telemetry["root_class"], "all-actions-equivalent")
        self.assertEqual(result.telemetry["optimal_action_ids"], sorted((action_id(a), action_id(b))))
        self.assertEqual(report.optimal_action_ids, result.telemetry["optimal_action_ids"])

    def test_exact_root_value_does_not_hide_unresolved_alternative(self):
        result, report = self.checked([
            node("root", choices=(({"action": "a-win"}, "win"), ({"action": "z-other"}, "other"))),
            node("win", score={"B": 2, "W": 1}), node("other", score={"B": 1, "W": 1}),
        ], node_limit=2)
        self.assertEqual(result.telemetry["root_bounds"], [1, 1])
        self.assertFalse(result.telemetry["complete_root"])
        self.assertEqual(result.telemetry["root_class"], "partial")
        self.assertEqual(result.telemetry["optimal_action_ids"], [])
        self.assertEqual(result.telemetry["unresolved_action_ids"], [action_id({"action": "z-other"})])
        self.assertTrue(report.root_value_exact)
        self.assertFalse(report.decision_classified)

    def test_entry_stop_has_no_fabricated_certificate(self):
        root, provider = tree()
        for options in ({"cancelled": lambda: True}, {"deadline": 0, "clock": lambda: 0}):
            with self.subTest(options=options):
                result = produce_certificate(root, provider, **options)
                self.assertIsNone(result.certificate)
                self.assertEqual(result.telemetry["root_class"], "partial")
                self.assertEqual(result.telemetry["work"]["nodes"], 0)
                self.assertIsNone(result.telemetry["objective"])

    def test_hard_node_limits_and_strict_provider_provenance(self):
        root, provider = tree()
        for limit in (0, True, 1.0, 10001, -1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                produce_certificate(root, provider, node_limit=limit)
        for value in (0, 1, "false", None, [], {}):
            with self.subTest(value=value), self.assertRaises(ProducerIntegrityError):
                produce_certificate(root, replace(provider, metadata=lambda _s, value=value: {"provenance": {"full_action_replay": value}}))
        result = produce_certificate(root, replace(provider, metadata=lambda _s: {"provenance": {"full_action_replay": True}}))
        self.assertTrue(result.telemetry["provenance"]["provider_reported_full_action_replay"])
        self.assertFalse(result.telemetry["provenance"]["verified_by_producer"])

    def test_nonaccepted_empty_domain_and_false_terminal_score_fail(self):
        pending = node("pending")
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(pending, provider_for([pending]))
        root, provider = tree()
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(root, replace(provider, score=lambda _s: {"B": True, "W": 0}))
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(root, replace(provider, accepted=lambda _s: 1))

    def test_cycles_and_colliding_fingerprints_are_integrity_failures(self):
        cyclic = node("cycle", choices=(({"action": "again"}, "cycle"),))
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(cyclic, provider_for([cyclic]))
        root, provider = tree()
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(root, replace(provider, fingerprint=lambda _s: "c" * 64))

    def test_callback_mutation_iterator_failure_and_root_isolation(self):
        root, provider = tree()
        before = deepcopy(root)

        def bad_actor(source):
            source["marker"] = True
            return source["actor"]

        def broken_iterator(source):
            yield source["choices"][0]["action"]
            source["marker"] += 1
            raise RuntimeError("late enumeration failure")

        def bad_wire(source, action):
            action["orientation"] = 99
            raise RuntimeError("bad transition")

        for changed in (replace(provider, actor=bad_actor), replace(provider, legal_actions=broken_iterator), replace(provider, transition=bad_wire)):
            with self.subTest(provider=changed), self.assertRaises(ProducerIntegrityError) as raised:
                produce_certificate(root, changed)
            self.assertEqual(root, before)
            self.assertGreater(raised.exception.work["callback_calls"], 0)

    def test_deterministic_detached_canonical_results_exclude_timing(self):
        root, provider = tree()
        ticks = iter((0, 7))
        first = produce_certificate(root, provider, clock=lambda: next(ticks))
        ticks = iter((0, 19))
        second = produce_certificate(root, provider, clock=lambda: next(ticks))
        self.assertNotEqual(first.timing, second.timing)
        self.assertEqual(first.canonical_dict(), second.canonical_dict())
        self.assertNotIn("timing", first.canonical_dict())
        telemetry = first.telemetry
        telemetry["work"]["nodes"] = 0
        self.assertEqual(first.telemetry["work"]["nodes"], 3)
        self.assertEqual(first.telemetry["producer_hash"], second.telemetry["producer_hash"])

    def test_explicit_stack_survives_more_than_python_recursion_depth(self):
        length = 1100
        states = [node(str(index), choices=(({"action": "pass"}, str(index + 1)),)) for index in range(length)]
        states.append(node(str(length), score={"B": 1, "W": 0}))
        result, report = self.checked(states, node_limit=length + 1)
        self.assertEqual(result.telemetry["root_class"], "forced-administrative")
        self.assertEqual(result.telemetry["work"]["nodes"], length + 1)
        self.assertEqual(report.root_value, 1)


if __name__ == "__main__":
    unittest.main()
