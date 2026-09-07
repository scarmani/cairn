"""Independent producer/checker round trips over tiny abstract state graphs.

These fixtures are synthetic engineering cases, not Varde positions, tactical
admission, reachability certificates, or actual-game proof searches.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.harness.lab_proof_producer import (  # noqa: E402
    ProducerIntegrityError, produce_certificate,
)
from research.harness.lab_terminal_cert import (  # noqa: E402
    TerminalProvider, check_certificate,
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def hashed(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def wire(kind, **fields):
    return {"action": kind, **fields}


def row(name, edges=(), *, color="B", swapped=False, score=None):
    return {
        "name": name, "edges": tuple(edges), "color": color,
        "seats": {"B": "S2", "W": "S1"} if swapped else {"B": "S1", "W": "S2"},
        "score": score,
    }


class AbstractTree:
    """Hand-authored transition table, with no search or value propagation."""

    def __init__(self, *rows):
        self.rows = {item["name"]: item for item in rows}
        self.states = {name: {"position": name, "history": [name], "marker": 1}
                       for name in self.rows}
        self.root = self.states["root"]
        self.score_calls = []
        self.transition_calls = []
        self.meta = {"origin": "independent-synthetic-engineering-fixture"}

    def actor(self, state):
        item = self.rows[state["position"]]
        return {"seat": None, "color": None} if item["score"] is not None else {
            "seat": item["seats"][item["color"]], "color": item["color"],
        }

    def legal(self, state):
        return [deepcopy(action) for action, _target in self.rows[state["position"]]["edges"]]

    def advance(self, state, action):
        self.transition_calls.append((state["position"], encoded(action)))
        for expected, target in self.rows[state["position"]]["edges"]:
            if encoded(expected) == encoded(action):
                return deepcopy(self.states[target])
        raise ValueError("not in synthetic legal domain")

    def score(self, state):
        result = self.rows[state["position"]]["score"]
        if result is None:
            raise AssertionError("a nonaccepted synthetic state was scored")
        self.score_calls.append(state["position"])
        return deepcopy(result)

    def provider(self, **overrides):
        fields = {
            "provider_id": "independent-producer-synthetic-table",
            "rules_id": "synthetic-not-a-game", "rules_revision": "0.1",
            "rules_hash": hashed("abstract directed graph"),
            "implementation_hash": hashed("independent explicit table v1"),
            "fingerprint": hashed, "snapshot": deepcopy,
            "metadata": lambda _state: deepcopy(self.meta),
            "actor": self.actor,
            "seats": lambda state: deepcopy(self.rows[state["position"]]["seats"]),
            "accepted": lambda state: self.rows[state["position"]]["score"] is not None,
            "score": self.score, "legal_actions": self.legal, "transition": self.advance,
        }
        fields.update(overrides)
        return TerminalProvider(**fields)


def alternatives(*scores):
    edges = tuple((wire("construct", face=[1, -1], orientation=i), f"leaf-{i}")
                  for i in range(len(scores)))
    return AbstractTree(row("root", edges), *(
        row(f"leaf-{i}", score={"B": score[0], "W": score[1]})
        for i, score in enumerate(scores)
    ))


class TestLabProofProducerInvariants(unittest.TestCase):
    def roundtrip(self, tree, **kwargs):
        before = deepcopy(tree.root)
        provider = tree.provider()
        result = produce_certificate(tree.root, provider, **kwargs)
        self.assertEqual(tree.root, before)
        self.assertIsNotNone(result.certificate)
        checked = check_certificate(result.certificate, tree.root, provider).to_dict()
        self.assertTrue(checked["verified"])
        telemetry = result.telemetry
        self.assertFalse(telemetry["admission_record"])
        self.assertFalse(checked["admission_record"])
        self.assertEqual(telemetry["work"]["terminal_simulation_backups"], 0)
        self.assertEqual(checked["work"]["terminal_simulation_backups"], 0)
        self.assertEqual(telemetry["root_bounds"], checked["root_bounds"])
        self.assertEqual(telemetry["root_value"], checked["root_value"])
        self.assertEqual(telemetry["complete_root"], checked["complete_optimal_action_set"])
        self.assertEqual(telemetry["optimal_action_ids"], checked["optimal_action_ids"])
        self.assertEqual(telemetry["unresolved_action_ids"], checked["unresolved_action_ids"])
        return result, checked

    def test_all_complete_root_classes_and_forced_substantive_distinction(self):
        cases = (
            (AbstractTree(row("root", score={"B": 2, "W": 0})), "terminal"),
            (AbstractTree(row("root", ((wire("accept"), "end"),)),
                          row("end", score={"B": 0, "W": 0})), "forced-administrative"),
            (alternatives((2, 0)), "all-actions-equivalent"),
            (alternatives((2, 0), (100, 0)), "all-actions-equivalent"),
            (alternatives((2, 0), (0, 2), (0, 0)), "discriminating"),
        )
        for tree, label in cases:
            with self.subTest(label=label, root_width=len(tree.legal(tree.root))):
                result, checked = self.roundtrip(tree)
                self.assertEqual(result.telemetry["root_class"], label)
                if label == "terminal":
                    self.assertTrue(checked["terminal_root"])
                    self.assertFalse(checked["decision_classified"])
                    self.assertIsNotNone(result.telemetry["terminal_root_convention"])
                else:
                    self.assertTrue(checked["decision_classified"])

    def test_every_administrative_kind_is_classified_without_pruning(self):
        for kind in ("swap", "pass", "finish-extension", "resume", "accept"):
            with self.subTest(kind=kind):
                tree = AbstractTree(row("root", ((wire(kind), "end"),)),
                                    row("end", score={"B": 0, "W": 0}))
                result, _checked = self.roundtrip(tree)
                self.assertEqual(result.telemetry["root_class"], "forced-administrative")
        for kind in ("play", "construct", "plant", "extend"):
            with self.subTest(kind=kind):
                tree = AbstractTree(row("root", ((wire(kind), "end"),)),
                                    row("end", score={"B": 0, "W": 0}))
                result, _checked = self.roundtrip(tree)
                self.assertEqual(result.telemetry["root_class"], "all-actions-equivalent")

    def test_equivalent_oriented_wins_and_legitimate_sacrifice_all_remain_optimal(self):
        rescue = wire("play", point=[0, 0], label="local-rescue")
        sacrifice = wire("play", point=[1, 0], label="local-sacrifice")
        lose = wire("play", point=[2, 0])
        tree = AbstractTree(row("root", ((rescue, "narrow"), (sacrifice, "large"), (lose, "loss"))),
                            row("narrow", score={"B": 1, "W": 0}),
                            row("large", score={"B": 100, "W": 0}),
                            row("loss", score={"B": 0, "W": 1}))
        _result, checked = self.roundtrip(tree)
        self.assertEqual(set(checked["optimal_action_ids"]), {encoded(rescue), encoded(sacrifice)})
        oriented, _checked = self.roundtrip(alternatives((2, 0), (100, 0)))
        self.assertEqual(len(oriented.telemetry["optimal_action_ids"]), 2)
        self.assertEqual({item["action"]["orientation"]
                          for item in oriented.telemetry["action_results"]}, {0, 1})

    def test_same_seat_after_takeover_maximizes_and_opposite_seat_minimizes(self):
        swap, draw = wire("swap"), wire("pass")
        tree = AbstractTree(
            row("root", ((swap, "same"), (draw, "draw"))),
            row("same", ((wire("extend"), "win"), (wire("finish-extension"), "loss")),
                color="W", swapped=True),
            row("win", swapped=True, score={"B": 0, "W": 3}),
            row("loss", swapped=True, score={"B": 3, "W": 0}),
            row("draw", score={"B": 1, "W": 1}),
        )
        result, checked = self.roundtrip(tree)
        self.assertEqual(checked["optimal_action_ids"], [encoded(swap)])
        self.assertEqual(result.telemetry["root_actor"], {"seat": "S1", "color": "B"})
        self.assertEqual(result.certificate.to_dict()["objective"]["seat"], "S1")
        tree.rows["same"]["color"] = "B"  # Same graph, now S2 controls the reply.
        _result, checked = self.roundtrip(tree)
        self.assertEqual(checked["optimal_action_ids"], [encoded(draw)])

    def test_white_root_objective_is_not_hard_coded_to_black(self):
        tree = alternatives((2, 0), (0, 2))
        tree.rows["root"]["color"] = "W"
        result, checked = self.roundtrip(tree)
        self.assertEqual(result.certificate.to_dict()["objective"]["seat"], "S2")
        self.assertEqual(checked["optimal_action_ids"], [encoded(wire(
            "construct", face=[1, -1], orientation=1))])

    def test_partial_exact_root_does_not_label_unknown_alternative(self):
        result, checked = self.roundtrip(alternatives((2, 0), (0, 2)), node_limit=2)
        self.assertEqual(result.telemetry["status"], "partial")
        self.assertEqual(result.telemetry["reason"], "node-limit")
        self.assertEqual(result.telemetry["root_class"], "partial")
        self.assertTrue(checked["root_value_exact"])
        self.assertEqual(checked["root_value"], 1)
        self.assertFalse(checked["complete_optimal_action_set"])
        self.assertEqual(checked["optimal_action_ids"], [])
        self.assertEqual(len(checked["unresolved_action_ids"]), 1)
        self.assertEqual(len(result.certificate.to_dict()["root_actions"]), 2)
        self.assertEqual(result.telemetry["work"]["nodes"], 2)

    def test_root_only_budget_preserves_complete_unknown_domain_without_scoring(self):
        tree = alternatives((2, 0), (0, 2), (1, 1))
        result = produce_certificate(tree.root, tree.provider(), node_limit=1)
        self.assertEqual(tree.score_calls, [])
        self.assertEqual(tree.transition_calls, [])
        self.assertEqual(result.telemetry["work"]["nodes"], 1)
        self.assertEqual(result.telemetry["work"]["actions_enumerated"], 3)
        self.assertTrue(result.telemetry["root_domain_complete"])
        self.assertFalse(result.telemetry["complete_root"])
        self.assertEqual(result.telemetry["root_bounds"], [-1, 1])
        self.assertEqual(len(result.telemetry["unresolved_action_ids"]), 3)
        self.assertTrue(check_certificate(result.certificate, tree.root, tree.provider()).verified)
        self.assertEqual(tree.score_calls, [])  # Checker does not score unknown accepted successors.

    def test_terminal_root_convention_tracks_current_black_identity_after_takeover(self):
        tree = AbstractTree(row("root", swapped=True, score={"B": 0, "W": 1}))
        result, checked = self.roundtrip(tree)
        self.assertEqual(result.certificate.to_dict()["objective"]["seat"], "S2")
        self.assertEqual(result.telemetry["terminal_root_convention"], "Black seat at the accepted root")
        self.assertEqual(checked["root_value"], -1)
        self.assertFalse(checked["decision_classified"])
        self.assertEqual(result.telemetry["action_results"], [])

    def test_terminal_with_actions_and_pending_null_actor_are_not_accepted(self):
        terminal = AbstractTree(row("root", ((wire("pass"), "root"),), score={"B": 0, "W": 0}))
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(terminal.root, terminal.provider())
        tree = alternatives((2, 0))
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(tree.root, tree.provider(actor=lambda _state: {"seat": None, "color": None}))

    def test_shared_dag_is_reused_but_history_is_part_of_memo_identity(self):
        tree = AbstractTree(row("root", ((wire("accept"), "shared"), (wire("pass"), "shared"))),
                            row("shared", score={"B": 0, "W": 0}))
        result, _checked = self.roundtrip(tree)
        self.assertEqual(result.telemetry["work"]["nodes"], 2)
        self.assertEqual(result.telemetry["work"]["transition_attempts"], 2)
        self.assertEqual(result.telemetry["work"]["memo_hits"], 1)
        self.assertEqual(len(result.certificate.to_dict()["graph"]), 2)
        distinct = alternatives((2, 0), (0, 2))
        distinct.states["leaf-0"]["board"] = distinct.states["leaf-1"]["board"] = []
        result, checked = self.roundtrip(distinct)
        self.assertEqual(result.telemetry["work"]["memo_hits"], 0)
        self.assertEqual(len(checked["optimal_action_ids"]), 1)

    def test_active_ancestor_cycles_and_snapshot_hash_collisions_are_integrity_errors(self):
        cycle = AbstractTree(row("root", ((wire("pass"), "root"),)))
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(cycle.root, cycle.provider())
        tree = alternatives((2, 0), (0, 2))
        provider = tree.provider(fingerprint=lambda state: hashed(
            "root" if state["position"] == "root" else "collision"))
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(tree.root, provider)

    def test_type_exact_snapshot_alias_collision_is_not_a_memo_hit(self):
        tree = alternatives((2, 0), (2, 0))
        tree.states["leaf-1"]["marker"] = True
        provider = tree.provider(
            snapshot=lambda state: {"root": state["position"] == "root", "marker": state["marker"]},
            fingerprint=lambda state: hashed(state["position"] == "root"),
        )
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(tree.root, provider)

    def test_long_chain_uses_explicit_stack_and_strict_node_ceiling(self):
        count = 1100
        tree = AbstractTree(
            row("root", ((wire("pass"), "n0"),)),
            *(row(f"n{i}", ((wire("pass"), f"n{i + 1}"),), color="W" if i % 2 else "B")
              for i in range(count)),
            row(f"n{count}", score={"B": 0, "W": 0}),
        )
        result, _checked = self.roundtrip(tree, node_limit=count + 2)
        self.assertEqual(result.telemetry["work"]["nodes"], count + 2)
        partial, _checked = self.roundtrip(tree, node_limit=1000)
        self.assertEqual(partial.telemetry["work"]["nodes"], 1000)
        self.assertEqual(partial.telemetry["root_class"], "partial")

    def test_entry_stops_have_no_fabricated_root_and_midway_stops_roundtrip(self):
        for options, reason in (({"cancelled": lambda: True}, "cancelled"),
                                ({"deadline": 1.0, "clock": lambda: 2.0}, "deadline")):
            with self.subTest(reason=reason):
                tree = alternatives((2, 0), (0, 2))
                result = produce_certificate(tree.root, tree.provider(), **options)
                self.assertIsNone(result.certificate)
                self.assertEqual(result.telemetry["status"], "partial")
                self.assertEqual(result.telemetry["reason"], reason)
                self.assertEqual(result.telemetry["work"]["nodes"], 0)
                self.assertFalse(tree.transition_calls)
                self.assertFalse(tree.score_calls)
        for mode in ("cancelled", "deadline"):
            with self.subTest(mode=mode):
                tree = alternatives((2, 0), (0, 2))
                options = {"cancelled": lambda: bool(tree.score_calls)} if mode == "cancelled" else {
                    "deadline": 1.0, "clock": lambda: 2.0 if tree.score_calls else 0.0,
                }
                result, _checked = self.roundtrip(tree, **options)
                self.assertEqual(result.telemetry["reason"], mode)
                self.assertEqual(result.telemetry["root_class"], "partial")

    def test_bad_limits_clocks_flags_and_provenance_fail_closed(self):
        tree = alternatives((2, 0))
        for limit in (0, -1, True, 2.0, 10001):
            with self.subTest(limit=limit), self.assertRaises((ValueError, TypeError)):
                produce_certificate(tree.root, tree.provider(), node_limit=limit)
        for value in (True, float("nan"), float("inf"), "1"):
            with self.subTest(deadline=value), self.assertRaises((ValueError, TypeError)):
                produce_certificate(tree.root, tree.provider(), deadline=value)
        with self.assertRaises((ValueError, ProducerIntegrityError)):
            produce_certificate(tree.root, tree.provider(), cancelled=lambda: 1)
        for value in (1, "true", None, []):
            tree.meta = {"provenance": {"full_action_replay": value}}
            with self.subTest(provenance=value), self.assertRaises((ValueError, ProducerIntegrityError)):
                produce_certificate(tree.root, tree.provider())

    def test_provenance_is_provider_reported_never_upgraded_to_verification(self):
        for metadata, reported in (({}, False), ({"provenance": {"full_action_replay": True}}, True),
                                   ({"provenance": {"full_action_replay": False}}, False)):
            with self.subTest(reported=reported):
                tree = alternatives((2, 0))
                tree.meta = metadata
                result, _checked = self.roundtrip(tree)
                provenance = result.telemetry["provenance"]
                self.assertIs(provenance["provider_reported_full_action_replay"], reported)
                self.assertIs(provenance["verified_by_producer"], False)
                self.assertTrue(provenance["verification_limit"])

    def test_invalid_acceptance_identity_score_domain_and_nonfinite_callbacks(self):
        cases = (
            {"accepted": lambda _state: 1},
            {"actor": lambda _state: {"seat": ["S1"], "color": "B"}},
            {"metadata": lambda _state: {"broken": float("nan")}},
            {"legal_actions": lambda _state: []},
            {"legal_actions": lambda _state: [wire("pass"), wire("pass")]},
            {"score": lambda _state: {"B": True, "W": 0}},
            {"score": lambda _state: {"B": 1.0, "W": 0}},
        )
        for overrides in cases:
            with self.subTest(callback=next(iter(overrides))):
                tree = alternatives((2, 0))
                before = deepcopy(tree.root)
                with self.assertRaises((ValueError, ProducerIntegrityError)):
                    produce_certificate(tree.root, tree.provider(**overrides))
                self.assertEqual(tree.root, before)
        tree = alternatives((2, 0))
        tree.rows["leaf-0"]["seats"]["W"] = "S3"
        with self.assertRaises(ProducerIntegrityError):
            produce_certificate(tree.root, tree.provider())

    def test_callback_mutation_and_partial_generator_failures_preserve_input_and_counts(self):
        tree = alternatives((2, 0), (0, 2))
        before = deepcopy(tree.root)

        def bad_transition(state, action):
            state["history"].append("corruption")
            action["orientation"] = 99
            raise RuntimeError("synthetic failing callback")

        with self.assertRaises(ProducerIntegrityError) as caught:
            produce_certificate(tree.root, tree.provider(transition=bad_transition))
        self.assertEqual(tree.root, before)
        self.assertEqual(caught.exception.work["transition_attempts"], 1)

        def broken_domain(_state):
            yield wire("pass")
            yield wire("accept")
            raise RuntimeError("synthetic partial enumeration")

        with self.assertRaises(ProducerIntegrityError) as caught:
            produce_certificate(tree.root, tree.provider(legal_actions=broken_domain))
        self.assertEqual(caught.exception.work["actions_enumerated"], 2)
        self.assertEqual(tree.root, before)

    def test_canonical_outputs_are_detached_ordered_and_timing_independent(self):
        tree = alternatives((2, 0), (0, 2), (1, 1))
        one = produce_certificate(tree.root, tree.provider(), clock=lambda: 0.0)
        tree.rows["root"]["edges"] = tuple(reversed(tree.rows["root"]["edges"]))
        two = produce_certificate(tree.root, tree.provider(), clock=lambda: 99.0)
        self.assertEqual(encoded(one.canonical_dict()), encoded(two.canonical_dict()))
        before = one.canonical_dict()
        exposed = one.to_dict()
        exposed["telemetry"]["action_results"][0]["bounds"][0] = -999
        exposed["certificate"]["root"]["snapshot"]["marker"] = "changed"
        telemetry = one.telemetry
        telemetry["work"]["nodes"] = -999
        self.assertEqual(one.canonical_dict(), before)
        self.assertNotIn("timing", one.canonical_dict())


if __name__ == "__main__":
    unittest.main()
