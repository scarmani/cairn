"""Bounded accepted-terminal proof production, independent of checker search.

This module does not launch research, import game mechanics, or check its own
proofs. Only public certificate/schema helpers are shared with the independent
checker. Trusted provider states must be deepcopyable and in-memory pickleable;
guard bytes never enter canonical evidence and are never deserialized.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import pickle
import time

from research.harness.lab_terminal_cert import (
    CLAIM_LIMIT, FORMAT, TerminalCertificate, TerminalProvider, action_id,
    canonical_json, seal_certificate,
)
import json


PRODUCER_REVISION = "0.1"
PRODUCER_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
ADMINISTRATIVE = frozenset(("swap", "pass", "finish-extension", "resume", "accept"))
PROVENANCE_LIMIT = "Provider-reported provenance only; this producer does not attest origin, reachability, or complete historical actions."


class ProducerIntegrityError(RuntimeError):
    """A provider contradiction or mutation prevents any certifiable result."""

    work = None
    telemetry = None


def _detached(value):
    return json.loads(canonical_json(value))


def _sha(value):
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _exact_time(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("clock/deadline must be finite numeric values")
    return value


@dataclass(frozen=True)
class ProofProductionResult:
    _payload_json: str

    @property
    def certificate(self):
        payload = self.to_dict()["certificate"]
        return TerminalCertificate.from_dict(payload) if payload is not None else None

    @property
    def telemetry(self):
        return self.to_dict()["telemetry"]

    @property
    def timing(self):
        return self.to_dict()["timing"]

    def to_dict(self):
        return json.loads(self._payload_json)

    def canonical_dict(self):
        result = self.to_dict()
        del result["timing"]
        return result


class _Production:
    def __init__(self, provider, node_limit, cancelled, deadline, clock):
        self.provider, self.node_limit = provider, node_limit
        self.cancelled, self.deadline, self.clock = cancelled, deadline, clock
        self.work = dict.fromkeys(("nodes", "transition_attempts", "legal_action_enumerations", "actions_enumerated", "memo_hits", "terminal_leaves", "terminal_simulation_backups", "callback_calls"), 0)
        self.nodes, self.snapshots, self.active = {}, {}, set()
        self.stop_reason = None
        self.objective = None
        self.root_actor = None
        self.root_id = None
        self.root_metadata = None
        self.root_snapshot = None
        self.identities = None
        self.terminal_convention = None
        self.provider_full_action_replay = False

    def raw(self, name, callback, source, *args):
        try:
            before = pickle.dumps((source, args), protocol=5)
        except Exception as error:
            raise ProducerIntegrityError("provider input cannot be structurally guarded") from error
        self.work["callback_calls"] += 1
        try:
            return callback(source, *args)
        except ProducerIntegrityError:
            raise
        except Exception as error:
            raise ProducerIntegrityError(f"{name} callback failed") from error
        finally:
            try:
                unchanged = pickle.dumps((source, args), protocol=5) == before
            except Exception as error:
                raise ProducerIntegrityError(f"{name} corrupted its input") from error
            if not unchanged:
                raise ProducerIntegrityError(f"{name} mutated its input")

    def identity(self, source):
        snapshot = _detached(self.raw("snapshot", self.provider.snapshot, source))
        fingerprint = self.raw("fingerprint", self.provider.fingerprint, source)
        if type(snapshot) is not dict or not _sha(fingerprint):
            raise ProducerIntegrityError("invalid complete snapshot or fingerprint")
        return snapshot, fingerprint

    def call(self, name, source, *args, callback=None):
        before, fingerprint = self.identity(source)
        try:
            return self.raw(name, callback or getattr(self.provider, name), source, *args)
        finally:
            after, next_fingerprint = self.identity(source)
            if next_fingerprint != fingerprint or canonical_json(after) != canonical_json(before):
                raise ProducerIntegrityError(f"{name} changed complete input identity")

    def stop(self, source):
        if self.stop_reason is not None:
            return self.stop_reason
        if self.cancelled is not None:
            value = self.raw("cancellation", lambda _source: self.cancelled(), source)
            if type(value) is not bool:
                raise ProducerIntegrityError("cancellation must return an exact Boolean")
            if value:
                self.stop_reason = "cancelled"
        if self.stop_reason is None and self.deadline is not None:
            now = _exact_time(self.clock())
            if now >= self.deadline:
                self.stop_reason = "deadline"
        if self.stop_reason is None and self.work["nodes"] >= self.node_limit:
            self.stop_reason = "node-limit"
        return self.stop_reason

    def envelope(self, source):
        actor = _detached(self.call("actor", source))
        seats = _detached(self.call("seats", source))
        accepted = self.call("accepted", source)
        if type(seats) is not dict or set(seats) != {"B", "W"} or any(type(value) is not str or not value.strip() for value in seats.values()) or len(set(seats.values())) != 2:
            raise ProducerIntegrityError("invalid bijective seat identities")
        if self.identities is not None and set(seats.values()) != self.identities:
            raise ProducerIntegrityError("original seat identities changed")
        if type(actor) is not dict or set(actor) != {"seat", "color"} or type(accepted) is not bool:
            raise ProducerIntegrityError("invalid actor or accepted flag")
        if accepted:
            if actor != {"seat": None, "color": None}:
                raise ProducerIntegrityError("accepted state has an actor")
        elif type(actor["seat"]) is not str or actor["color"] not in ("B", "W") or seats[actor["color"]] != actor["seat"]:
            raise ProducerIntegrityError("pending actor does not match conserved seat map")
        return actor, seats, accepted

    def legal(self, source):
        self.work["legal_action_enumerations"] += 1

        def collect(state):
            result = []
            for action in self.provider.legal_actions(state):
                self.work["actions_enumerated"] += 1
                result.append(_detached(action))
            return result

        result = self.call("legal_actions", source, callback=collect)
        actions = {}
        for wire in result:
            identity = action_id(wire)
            if identity in actions:
                raise ProducerIntegrityError("duplicate complete legal action ID")
            actions[identity] = wire
        return [(identity, actions[identity]) for identity in sorted(actions)]

    def enter(self, source, *, root=False):
        snapshot, fingerprint = self.identity(source)
        if fingerprint in self.snapshots:
            if canonical_json(snapshot) != canonical_json(self.snapshots[fingerprint]):
                raise ProducerIntegrityError("contradictory complete fingerprint snapshots")
            if fingerprint in self.active:
                raise ProducerIntegrityError("repeated active ancestor is not a terminal result")
            self.work["memo_hits"] += 1
            return fingerprint, None
        # Caller polls before attempting a successor, so this is a newly
        # inspected state within the hard budget, including accepted leaves.
        if self.work["nodes"] >= self.node_limit:
            raise ProducerIntegrityError("producer exceeded its hard node budget")
        self.work["nodes"] += 1
        actor, seats, accepted = self.envelope(source)
        if root:
            self.identities = set(seats.values())
            self.root_actor = actor
            self.objective = {"kind": "accepted-terminal-wdl", "seat": seats["B"] if accepted else actor["seat"]}
            self.terminal_convention = "Black seat at the accepted root" if accepted else None
            metadata = _detached(self.call("metadata", source))
            if type(metadata) is not dict:
                raise ProducerIntegrityError("provider metadata must be a JSON object")
            provenance = metadata.get("provenance", {})
            if type(provenance) is not dict or type(provenance.get("full_action_replay", False)) is not bool:
                raise ProducerIntegrityError("provider full-action provenance must be an exact Boolean")
            self.provider_full_action_replay = provenance.get("full_action_replay", False)
            self.root_metadata, self.root_snapshot, self.root_id = metadata, snapshot, fingerprint
        legal = self.legal(source)
        if accepted and legal:
            raise ProducerIntegrityError("accepted state still has legal actions")
        if not accepted and not legal:
            raise ProducerIntegrityError("nonaccepted state has an empty legal domain")
        node = {"fingerprint": fingerprint, "actor": actor, "seats": seats, "accepted": accepted,
                "bounds": [-1, 1], "kind": "terminal" if accepted else "expanded", "score": None,
                "actions": [], "unresolved_reason": None}
        if accepted:
            actual_score = _detached(self.call("score", source))
            if type(actual_score) is not dict or set(actual_score) != {"B", "W"} or any(type(value) is not int for value in actual_score.values()):
                raise ProducerIntegrityError("accepted score must contain exact B/W integers")
            own = next(color for color, seat in seats.items() if seat == self.objective["seat"])
            other = "W" if own == "B" else "B"
            margin = actual_score[own] - actual_score[other]
            value = 1 if margin > 0 else -1 if margin < 0 else 0
            node.update(score=actual_score, bounds=[value, value])
            self.work["terminal_leaves"] += 1
        else:
            node["actions"] = [{"id": identity, "action": wire, "child": None, "unresolved_reason": "not-expanded"}
                               for identity, wire in legal]
        self.nodes[fingerprint], self.snapshots[fingerprint] = node, snapshot
        if accepted:
            return fingerprint, None
        self.active.add(fingerprint)
        return fingerprint, {"source": source, "fingerprint": fingerprint, "next": 0}

    def traverse(self, root):
        if self.stop(root):
            return
        _, frame = self.enter(root, root=True)
        frames = [frame] if frame is not None else []
        while frames:
            frame = frames[-1]
            node = self.nodes[frame["fingerprint"]]
            edges = node["actions"]
            if frame["next"] < len(edges) and self.stop(frame["source"]) is None:
                edge = edges[frame["next"]]
                frame["next"] += 1
                self.work["transition_attempts"] += 1
                child = self.call("transition", frame["source"], deepcopy(edge["action"]))
                try:
                    child = deepcopy(child)
                except Exception as error:
                    raise ProducerIntegrityError("successor cannot be independently copied") from error
                child_id, next_frame = self.enter(child)
                edge.update(child=child_id, unresolved_reason=None)
                if next_frame is not None:
                    frames.append(next_frame)
                continue
            for edge in edges[frame["next"]:]:
                edge["unresolved_reason"] = self.stop_reason or "not-expanded"
            lower, upper = [], []
            for edge in edges:
                bounds = self.nodes[edge["child"]]["bounds"] if edge["child"] is not None else [-1, 1]
                lower.append(bounds[0])
                upper.append(bounds[1])
            if node["actor"]["seat"] == self.objective["seat"]:
                node["bounds"] = [max(lower), max(upper)]
            else:
                node["bounds"] = [min(lower), min(upper)]
            self.active.remove(frame["fingerprint"])
            frames.pop()

    def output(self, elapsed):
        certificate = None
        results = []
        root = self.nodes.get(self.root_id)
        complete, domain_complete, exact = False, False, False
        root_class, root_bounds, root_value = "partial", None, None
        if root is not None:
            root_bounds = root["bounds"]
            exact = root_bounds[0] == root_bounds[1]
            root_value = root_bounds[0] if exact else None
            domain_complete = root["kind"] == "expanded"
            results = [{"id": edge["id"], "action": edge["action"],
                        "bounds": self.nodes[edge["child"]]["bounds"] if edge["child"] is not None else [-1, 1]}
                       for edge in root["actions"]]
            complete = domain_complete and all(row["bounds"][0] == row["bounds"][1] for row in results)
            if root["accepted"]:
                root_class = "terminal"
            elif complete:
                if len(results) == 1 and results[0]["action"]["action"] in ADMINISTRATIVE:
                    root_class = "forced-administrative"
                elif len({row["bounds"][0] for row in results}) == 1:
                    root_class = "all-actions-equivalent"
                else:
                    root_class = "discriminating"
            payload = {"format": FORMAT, "version": 1, "provider": self.provider.identity(),
                       "root": {"snapshot": self.root_snapshot, "fingerprint": self.root_id, "actor": self.root_actor, "metadata": self.root_metadata},
                       "objective": self.objective,
                       "root_actions": [{"id": row["id"], "bounds": row["bounds"]} for row in results],
                       "graph": [self.nodes[key] for key in sorted(self.nodes)], "graph_hash": "0" * 64,
                       "resources": {key: self.work[key] for key in ("nodes", "transition_attempts", "terminal_leaves", "terminal_simulation_backups")},
                       "claim_limit": CLAIM_LIMIT}
            certificate = TerminalCertificate.from_dict(seal_certificate(payload)).to_dict()
        telemetry = {
            "status": "complete" if root_class != "partial" else "partial", "reason": self.stop_reason,
            "root_class": root_class, "root_actor": self.root_actor, "objective": self.objective,
            "terminal_root_convention": self.terminal_convention,
            "root_domain_complete": domain_complete, "complete_root": complete,
            "root_bounds": root_bounds, "root_value": root_value, "root_value_exact": exact,
            "action_results": results,
            "optimal_action_ids": [row["id"] for row in results if row["bounds"][0] == root_value] if complete else [],
            "unresolved_action_ids": [row["id"] for row in results if row["bounds"][0] != row["bounds"][1]],
            "work": self.work, "provider": self.provider.identity(),
            "producer_revision": PRODUCER_REVISION, "producer_hash": PRODUCER_HASH,
            "provenance": {"provider_reported_full_action_replay": self.provider_full_action_replay,
                           "verified_by_producer": False, "verification_limit": PROVENANCE_LIMIT},
            "admission_record": False,
        }
        return ProofProductionResult(canonical_json({"format": "varde-lab-proof-production", "version": 1,
                                                    "certificate": certificate, "telemetry": telemetry,
                                                    "timing": {"elapsed_seconds": elapsed}}))


def produce_certificate(root_state, provider, *, node_limit=10000, cancelled=None, deadline=None, clock=time.monotonic):
    """Produce one bounded certificate; a separate checker must verify it.

    Deadline/cancellation are cooperative between bounded provider operations,
    not process supervision. Terminal roots use the current Black seat as the
    deterministic objective and never supply a decision/admission record.
    """
    if not isinstance(provider, TerminalProvider):
        raise ValueError("a canonical TerminalProvider is required")
    if type(node_limit) is not int or not 1 <= node_limit <= 10000:
        raise ValueError("node_limit must be an exact integer from 1 through 10000")
    if cancelled is not None and not callable(cancelled):
        raise ValueError("cancelled must be callable")
    if not callable(clock):
        raise ValueError("clock must be callable")
    if deadline is not None:
        _exact_time(deadline)
    runner = _Production(provider, node_limit, cancelled, deadline, clock)
    try:
        started = _exact_time(clock())
        root = deepcopy(root_state)
        runner.traverse(root)
        elapsed = max(0.0, _exact_time(clock()) - started)
        return runner.output(elapsed)
    except Exception as error:
        if not isinstance(error, ProducerIntegrityError):
            error = ProducerIntegrityError(f"producer integrity failure: {error}")
        error.work = _detached(runner.work)
        error.telemetry = {"status": "integrity-error", "work": _detached(runner.work),
                           "provider": provider.identity(), "admission_record": False}
        raise error
