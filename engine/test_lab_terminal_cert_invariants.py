"""Independent synthetic terminal-certificate checks; no game proof search.

Every graph and bound below is a small hand-specified abstract fixture. These
are engineering tests, never a corpus or evidence of optimal Varde decisions.
"""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.harness.lab_terminal_cert import (  # noqa: E402
    CLAIM_LIMIT, TerminalCertificate, TerminalIntegrityError, TerminalProvider, check_certificate,
    seal_certificate,
)


SEATS = {"B": "S1", "W": "S2"}
SWAPPED = {"B": "S2", "W": "S1"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def action(kind, **fields):
    return {"action": kind, **fields}


def node(name, *, edges=(), bounds=(-1, 1), color="B", seats=None,
         score=None, reason=None):
    return {
        "name": name, "edges": tuple(edges), "bounds": list(bounds),
        "color": color, "seats": dict(seats or SEATS), "score": score,
        "reason": reason,
    }


class SyntheticWorld:
    """Explicit abstract state table, independent of the checker's traversal."""

    def __init__(self, *nodes, root="root"):
        self.nodes = {item["name"]: item for item in nodes}
        self.states = {
            name: {"node": name, "history": ["synthetic-origin"], "marker": 1}
            for name in self.nodes
        }
        self.root = self.states[root]
        self.origin = {"kind": "synthetic-unit-test", "full_action_replay": False, "seed": 7}
        self.score_calls = []

    def actor(self, state):
        item = self.nodes[state["node"]]
        if item["score"] is not None:
            return {"seat": None, "color": None}
        return {"seat": item["seats"][item["color"]], "color": item["color"]}

    def accepted(self, state):
        return self.nodes[state["node"]]["score"] is not None

    def score(self, state):
        if not self.accepted(state):
            raise AssertionError("nonterminal score callback was queried")
        self.score_calls.append(state["node"])
        return deepcopy(self.nodes[state["node"]]["score"])

    def legal(self, state):
        return [deepcopy(wire) for wire, _child in self.nodes[state["node"]]["edges"]]

    def advance(self, state, wire):
        destination = next(
            child for expected, child in self.nodes[state["node"]]["edges"]
            if canonical(expected) == canonical(wire)
        )
        return deepcopy(self.states[destination])

    def provider(self, **overrides):
        fields = dict(
            provider_id="independent-synthetic-table",
            rules_id="synthetic", rules_revision="0.1",
            rules_hash=digest("synthetic-rules"),
            implementation_hash=digest("independent-synthetic-table-v1"),
            fingerprint=digest, snapshot=deepcopy,
            metadata=lambda _state: deepcopy(self.origin),
            actor=self.actor,
            seats=lambda state: deepcopy(self.nodes[state["node"]]["seats"]),
            accepted=self.accepted, score=self.score, legal_actions=self.legal,
            transition=self.advance,
        )
        fields.update(overrides)
        return TerminalProvider(**fields)

    def payload(self):
        """Serialize hand-declared synthetic bounds; does not solve a graph."""
        graph = []
        for name, item in self.nodes.items():
            is_terminal = item["score"] is not None
            kind = "terminal" if is_terminal else "unexpanded" if item["reason"] else "expanded"
            edges = []
            for wire, destination in item["edges"]:
                edges.append({
                    "id": canonical(wire), "action": deepcopy(wire),
                    "child": digest(self.states[destination]), "unresolved_reason": None,
                })
            graph.append({
                "fingerprint": digest(self.states[name]), "actor": self.actor(self.states[name]),
                "seats": deepcopy(item["seats"]), "accepted": is_terminal,
                "bounds": list(item["bounds"]), "kind": kind,
                "score": deepcopy(item["score"]), "actions": edges,
                "unresolved_reason": item["reason"],
            })
        root = self.nodes[self.root["node"]]
        payload = {
            "format": "varde-lab-terminal-certificate", "version": 1,
            "provider": {
                "provider_id": "independent-synthetic-table", "rules_id": "synthetic",
                "rules_revision": "0.1", "rules_hash": digest("synthetic-rules"),
                "implementation_hash": digest("independent-synthetic-table-v1"),
            },
            "root": {
                "snapshot": deepcopy(self.root), "fingerprint": digest(self.root),
                "actor": self.actor(self.root), "metadata": deepcopy(self.origin),
            },
            "objective": {"kind": "accepted-terminal-wdl", "seat": "S1"},
            "root_actions": [
                {"id": canonical(wire), "bounds": list(self.nodes[child]["bounds"])}
                for wire, child in root["edges"]
            ],
            "graph": graph,
            "resources": {
                "nodes": 0, "transition_attempts": 0, "terminal_leaves": 0,
                "terminal_simulation_backups": 0,
            },
            "claim_limit": CLAIM_LIMIT,
        }
        return seal_certificate(payload)

    def check(self, payload=None, provider=None, **kwargs):
        cert = TerminalCertificate.from_dict(payload or self.payload())
        return check_certificate(cert, self.root, provider or self.provider(), **kwargs)


def two_wins():
    return SyntheticWorld(
        node("root", edges=((action("construct", face=[1, 0], orientation=0), "small"),
                            (action("construct", face=[1, 0], orientation=1), "large")),
             bounds=(1, 1)),
        node("small", bounds=(1, 1), score={"B": 2, "W": 1}),
        node("large", bounds=(1, 1), score={"B": 100, "W": 0}),
    )


class TestLabTerminalCertInvariants(unittest.TestCase):
    def test_equivalent_wins_preserve_orientation_and_ignore_margin(self):
        world = two_wins()
        before = deepcopy(world.root)
        result = world.check().to_dict()
        self.assertTrue(result["verified"])
        self.assertTrue(result["complete_optimal_action_set"])
        self.assertEqual(set(result["optimal_action_ids"]), {
            canonical(action("construct", face=[1, 0], orientation=0)),
            canonical(action("construct", face=[1, 0], orientation=1)),
        })
        self.assertEqual(result["root_value"], 1)
        self.assertFalse(result["admission_record"])
        self.assertEqual(result["work"]["terminal_simulation_backups"], 0)
        self.assertEqual(result["claimed_resources"]["nodes"], 0)
        self.assertGreater(result["work"]["nodes_checked"], 0)
        self.assertEqual(world.root, before)

    def test_exact_root_does_not_classify_unknown_alternative(self):
        world = SyntheticWorld(
            node("root", edges=((action("play", point=[0, 0]), "win"),
                                (action("pass"), "unknown")), bounds=(1, 1)),
            node("win", bounds=(1, 1), score={"B": 1, "W": 0}),
            node("unknown", color="W", reason="node-limit"),
        )
        result = world.check().to_dict()
        self.assertTrue(result["verified"])
        self.assertTrue(result["root_value_exact"])
        self.assertEqual(result["root_value"], 1)
        self.assertFalse(result["decision_classified"])
        self.assertFalse(result["complete_optimal_action_set"])
        self.assertFalse(result["optimal_action_ids"])
        self.assertEqual(result["unresolved_action_ids"], [canonical(action("pass"))])

    def test_same_seat_after_color_takeover_maximizes_for_original_identity(self):
        world = SyntheticWorld(
            node("root", edges=((action("swap"), "same-seat"), (action("pass"), "draw")),
                 bounds=(1, 1)),
            node("same-seat", color="W", seats=SWAPPED,
                 edges=((action("play", point=[0, 0]), "win-white"),
                        (action("play", point=[1, 0]), "lose-white")), bounds=(1, 1)),
            node("win-white", seats=SWAPPED, bounds=(1, 1), score={"B": 0, "W": 1}),
            node("lose-white", seats=SWAPPED, bounds=(-1, -1), score={"B": 100, "W": 0}),
            node("draw", bounds=(0, 0), score={"B": 2, "W": 2}),
        )
        result = world.check().to_dict()
        self.assertEqual(result["optimal_action_ids"], [canonical(action("swap"))])
        self.assertEqual(result["root_value"], 1)

    def test_opponent_acceptance_resumption_choice_uses_minimizing_polarity(self):
        world = SyntheticWorld(
            node("root", edges=((action("accept"), "opponent"),
                                (action("resume"), "draw")), bounds=(0, 0)),
            node("opponent", color="W",
                 edges=((action("accept"), "win"), (action("resume"), "loss")),
                 bounds=(-1, -1)),
            node("win", bounds=(1, 1), score={"B": 2, "W": 0}),
            node("loss", bounds=(-1, -1), score={"B": 0, "W": 2}),
            node("draw", bounds=(0, 0), score={"B": 0, "W": 0}),
        )
        result = world.check().to_dict()
        self.assertEqual(result["optimal_action_ids"], [canonical(action("resume"))])
        self.assertNotIn("opponent", world.score_calls)

    def test_terminal_root_has_no_decision_or_corpus_claim(self):
        world = SyntheticWorld(node("root", bounds=(0, 0), score={"B": 0, "W": 0}))
        result = world.check().to_dict()
        self.assertTrue(result["verified"])
        self.assertTrue(result["terminal_root"])
        self.assertFalse(result["decision_classified"])
        self.assertFalse(result["admission_record"])
        self.assertFalse(result["optimal_action_ids"])

    def test_opponent_root_never_selects_maximum_for_other_seats_objective(self):
        world = SyntheticWorld(
            node("root", color="W", bounds=(-1, -1),
                 edges=((action("play", point=[0, 0]), "win"),
                        (action("play", point=[1, 0]), "loss"))),
            node("win", bounds=(1, 1), score={"B": 1, "W": 0}),
            node("loss", bounds=(-1, -1), score={"B": 0, "W": 1}),
        )
        result = world.check().to_dict()
        self.assertEqual(result["root_value"], -1)
        self.assertEqual(result["optimal_action_ids"], [canonical(action("play", point=[1, 0]))])

    def test_bijective_successor_cannot_replace_an_original_seat(self):
        world = two_wins()
        world.nodes["large"]["seats"] = {"B": "S1", "W": "S3"}
        with self.assertRaises(ValueError):
            world.check()
        world = two_wins()
        provider = world.provider()
        changed = replace(provider, seats=lambda state: (
            {"B": "S1", "W": "S3"} if state["node"] == "large" else provider.seats(state)
        ))
        with self.assertRaises(TerminalIntegrityError):
            world.check(provider=changed)

    def test_equal_repeated_state_is_valid_but_fingerprint_alias_is_rejected(self):
        world = two_wins()
        wires = [wire for wire, _child in world.nodes["root"]["edges"]]
        world.nodes["root"]["edges"] = tuple((wire, "small") for wire in wires)
        del world.nodes["large"]
        result = world.check().to_dict()
        self.assertTrue(result["complete_optimal_action_set"])
        self.assertEqual(len(result["optimal_action_ids"]), 2)

        world = two_wins()
        bad = world.payload()
        small_hash = digest(world.states["small"])
        bad["graph"][0]["actions"][1]["child"] = small_hash
        bad["graph"].pop()
        provider = replace(
            world.provider(),
            fingerprint=lambda state: small_hash if state["node"] == "large" else digest(state),
        )
        with self.assertRaises(TerminalIntegrityError):
            world.check(seal_certificate(bad), provider=provider)

    def test_unknown_edge_still_rejects_replacement_of_original_identity(self):
        world = SyntheticWorld(
            node("root", edges=((action("pass"), "pending"),)),
            node("pending", color="W", reason="not-expanded"),
        )
        payload = world.payload()
        payload["graph"][0]["actions"][0].update(child=None, unresolved_reason="node-limit")
        payload["graph"].pop()
        provider = world.provider()
        changed = replace(provider, seats=lambda state: (
            {"B": "S1", "W": "S3"} if state["node"] == "pending" else provider.seats(state)
        ))
        with self.assertRaises(TerminalIntegrityError):
            world.check(seal_certificate(payload), provider=changed)

    def test_unknown_terminal_successor_consumes_budget_but_never_supplies_a_value(self):
        world = SyntheticWorld(
            node("root", edges=((action("pass"), "win"),)),
            node("win", bounds=(1, 1), score={"B": 1, "W": 0}),
        )
        payload = world.payload()
        payload["graph"][0]["actions"][0].update(child=None, unresolved_reason="watchdog")
        payload["graph"].pop()
        payload["root_actions"][0]["bounds"] = [-1, 1]
        payload = seal_certificate(payload)
        limited = world.check(payload, node_limit=1).to_dict()
        self.assertFalse(limited["verified"])
        self.assertFalse(limited["decision_classified"])
        complete_check = world.check(payload, node_limit=2).to_dict()
        self.assertTrue(complete_check["verified"])
        self.assertEqual(complete_check["root_bounds"], [-1, 1])
        self.assertFalse(complete_check["complete_optimal_action_set"])
        self.assertEqual(complete_check["work"]["nodes_checked"], 1)
        self.assertEqual(complete_check["work"]["unknown_successors_checked"], 1)
        self.assertEqual(complete_check["work"]["terminal_scores_checked"], 0)
        self.assertEqual(complete_check["work"]["terminal_simulation_backups"], 0)
        self.assertEqual(world.score_calls, [])

    def test_cycles_dangling_edges_and_unreachable_nodes_fail_schema(self):
        world = two_wins()
        for kind in ("cycle", "dangling", "unreachable"):
            bad = world.payload()
            if kind == "cycle":
                bad["graph"][0]["actions"][0]["child"] = bad["root"]["fingerprint"]
                bad["graph"].pop(1)
            elif kind == "dangling":
                bad["graph"][0]["actions"][0]["child"] = digest("nonexistent")
            else:
                extra = deepcopy(bad["graph"][1])
                extra["fingerprint"] = digest("unreachable")
                bad["graph"].append(extra)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                TerminalCertificate.from_dict(seal_certificate(bad))

    def test_resource_and_cancellation_exhaustion_never_emit_decision_labels(self):
        world = two_wins()
        for options in ({"node_limit": 1}, {"cancelled": lambda: True}):
            with self.subTest(options=tuple(options)):
                result = world.check(**options).to_dict()
                self.assertFalse(result["verified"])
                self.assertEqual(result["status"], "unknown")
                self.assertFalse(result["decision_classified"])
                self.assertFalse(result["complete_optimal_action_set"])
                self.assertFalse(result["optimal_action_ids"])
                self.assertFalse(result["admission_record"])
                self.assertEqual(result["work"]["terminal_simulation_backups"], 0)

    def test_certificate_and_report_outputs_are_detached(self):
        world = two_wins()
        payload = world.payload()
        cert = TerminalCertificate.from_dict(payload)
        expected = cert.to_dict()
        payload["root"]["snapshot"]["history"].append("external mutation")
        exported = cert.to_dict()
        exported["graph"][0]["actions"][0]["action"]["orientation"] = 99
        self.assertEqual(cert.to_dict(), expected)
        report = check_certificate(cert, world.root, world.provider())
        report_before = report.to_dict()
        result = report.to_dict()
        result["work"]["nodes_checked"] = 999999
        result["optimal_action_ids"].clear()
        self.assertEqual(report.to_dict(), report_before)

    def test_bool_and_float_aliases_are_not_integer_certificate_fields(self):
        world = two_wins()
        for field, alias in (("version", True), ("version", 1.0),
                             ("bounds", True), ("bounds", 1.0),
                             ("score", True), ("score", 2.0),
                             ("resources", False), ("resources", 0.0)):
            with self.subTest(field=field, alias=alias):
                bad = world.payload()
                if field == "version":
                    bad[field] = alias
                elif field == "bounds":
                    bad["graph"][0]["bounds"][0] = alias
                elif field == "score":
                    bad["graph"][1]["score"]["B"] = alias
                else:
                    bad[field]["nodes"] = alias
                with self.assertRaises(ValueError):
                    TerminalCertificate.from_dict(seal_certificate(bad))

    def test_unresolved_reason_malformed_containers_raise_schema_value_error(self):
        world = SyntheticWorld(
            node("root", edges=((action("pass"), "pending"),)),
            node("pending", color="W", reason="not-expanded"),
        )
        for location in ("node", "edge"):
            for malformed in ([], {}, ["node-limit"], {"reason": "cancelled"}):
                bad = world.payload()
                if location == "node":
                    bad["graph"][1]["unresolved_reason"] = malformed
                else:
                    bad["graph"][0]["actions"][0]["child"] = None
                    bad["graph"][0]["actions"][0]["unresolved_reason"] = malformed
                    bad["graph"].pop()
                with self.subTest(location=location, malformed=malformed), self.assertRaises(ValueError):
                    TerminalCertificate.from_dict(seal_certificate(bad))

    def test_nonzero_simulation_claim_and_local_claim_limit_are_rejected(self):
        for field in ("terminal_simulation_backups", "claim_limit"):
            bad = two_wins().payload()
            if field == "claim_limit":
                bad[field] = "local predicate and declared horizon only; not optimal play"
            else:
                bad["resources"][field] = 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                TerminalCertificate.from_dict(seal_certificate(bad))

    def test_missing_and_duplicate_oriented_domains_are_not_accepted(self):
        world = two_wins()
        for operation in ("missing", "duplicate", "wrong-id"):
            bad = world.payload()
            if operation == "missing":
                bad["graph"][0]["actions"].pop()
                bad["root_actions"].pop()
                bad["graph"].pop()
            elif operation == "duplicate":
                bad["graph"][0]["actions"][1] = deepcopy(bad["graph"][0]["actions"][0])
            else:
                bad["graph"][0]["actions"][1]["id"] = bad["graph"][0]["actions"][0]["id"]
            with self.subTest(operation=operation), self.assertRaises((ValueError, TerminalIntegrityError)):
                world.check(seal_certificate(bad))

    def test_snapshot_metadata_and_root_actor_tampering_are_rejected(self):
        world = two_wins()
        for tamper in ("snapshot", "metadata", "actor", "objective"):
            bad = world.payload()
            if tamper == "snapshot":
                bad["root"]["snapshot"]["marker"] = True
            elif tamper == "metadata":
                bad["root"]["metadata"]["full_action_replay"] = True
            elif tamper == "actor":
                bad["root"]["actor"] = {"seat": "S2", "color": "W"}
            else:
                bad["objective"]["seat"] = "unknown-seat"
            with self.subTest(tamper=tamper), self.assertRaises((ValueError, TerminalIntegrityError)):
                world.check(seal_certificate(bad))

    def test_false_terminal_score_and_polarity_claims_are_rejected(self):
        world = two_wins()
        for tamper in ("leaf-score", "root-value", "false-terminal"):
            bad = world.payload()
            if tamper == "leaf-score":
                bad["graph"][1]["score"] = {"B": 1, "W": 2}
                bad["graph"][1]["bounds"] = [-1, -1]
                bad["root_actions"][0]["bounds"] = [-1, -1]
            elif tamper == "root-value":
                bad["graph"][0]["bounds"] = [0, 0]
            else:
                bad["graph"] = [dict(
                    bad["graph"][0], accepted=True, kind="terminal", actions=[],
                    actor={"seat": None, "color": None}, score={"B": 1, "W": 0},
                )]
                bad["root"]["actor"] = {"seat": None, "color": None}
                bad["root_actions"] = []
            with self.subTest(tamper=tamper), self.assertRaises((ValueError, TerminalIntegrityError)):
                world.check(seal_certificate(bad))

    def test_mutating_transition_and_failed_callback_preserve_caller(self):
        world = two_wins()
        original = deepcopy(world.root)
        for fail in (False, True):
            def mutate(state, wire):
                state["history"].append("forbidden mutation")
                wire["orientation"] = 9
                if fail:
                    raise RuntimeError("synthetic provider failure")
                return deepcopy(world.states["small"])

            with self.subTest(fail=fail), self.assertRaises(TerminalIntegrityError):
                world.check(provider=replace(world.provider(), transition=mutate))
            self.assertEqual(world.root, original)


if __name__ == "__main__":
    unittest.main()
