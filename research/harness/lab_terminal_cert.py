"""Independent accepted-terminal certificate checking, not a proof producer.

Only trusted local provider objects are executable. Certificate data is strict
finite JSON and never names external graph files. In-memory pickle bytes guard
callback input mutation; they are never loaded, hashed into evidence, or treated
as semantic fingerprints. Provider states must be deepcopyable and pickleable.
"""

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import pickle
from typing import Any, Callable


FORMAT = "varde-lab-terminal-certificate"
VERSION = 1
CLAIM_LIMIT = "accepted-terminal WDL within the checked graph; not research admission or strategic strength"
UNRESOLVED_REASONS = frozenset(("not-expanded", "node-limit", "deadline", "cancelled", "watchdog"))
PROVIDER_FIELDS = ("provider_id", "rules_id", "rules_revision", "rules_hash", "implementation_hash")
CALLBACK_FIELDS = ("fingerprint", "snapshot", "metadata", "actor", "seats", "accepted", "score", "legal_actions", "transition")
RESOURCE_FIELDS = frozenset(("nodes", "transition_attempts", "terminal_leaves", "terminal_simulation_backups"))


def _finite_json(value):
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _finite_json(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _finite_json(item)
        return
    raise ValueError("expected detached finite JSON data")


def canonical_json(value):
    try:
        _finite_json(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, OverflowError, RecursionError) as error:
        raise ValueError("invalid finite JSON data") from error


def canonical_hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _copy_json(value):
    return json.loads(canonical_json(value))


def _fields(value, expected, label):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError(f"invalid {label} fields")


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(f"invalid {label}")


def _hash(value, label):
    if type(value) is not str or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"invalid {label} SHA-256")


def action_id(wire):
    if type(wire) is not dict:
        raise ValueError("action wire must be a JSON object")
    _text(wire.get("action"), "action kind")
    return canonical_json(wire)


def _action_id(value):
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid canonical action ID") from error
    if action_id(parsed) != value:
        raise ValueError("action ID is not canonical complete wire JSON")


def _bounds(value):
    if type(value) is not list or len(value) != 2 or any(type(v) is not int or v not in (-1, 0, 1) for v in value) or value[0] > value[1]:
        raise ValueError("invalid WDL bounds")


def _actor(value):
    _fields(value, ("seat", "color"), "actor")
    if value["seat"] is None and value["color"] is None:
        return
    _text(value["seat"], "actor identity")
    if value["color"] not in ("B", "W"):
        raise ValueError("invalid actor color")


def _seats(value):
    _fields(value, ("B", "W"), "seat map")
    for seat in value.values():
        _text(seat, "seat identity")
    if len(set(value.values())) != 2:
        raise ValueError("seat map is not bijective")


def _score(value):
    _fields(value, ("B", "W"), "terminal score")
    if any(type(score) is not int for score in value.values()):
        raise ValueError("terminal scores must be exact integers")


@dataclass(frozen=True)
class TerminalProvider:
    provider_id: str
    rules_id: str
    rules_revision: str
    rules_hash: str
    implementation_hash: str
    fingerprint: Callable[[Any], str]
    snapshot: Callable[[Any], dict]
    metadata: Callable[[Any], dict]
    actor: Callable[[Any], dict]
    seats: Callable[[Any], dict]
    accepted: Callable[[Any], bool]
    score: Callable[[Any], dict]
    legal_actions: Callable[[Any], Any]
    transition: Callable[[Any, dict], Any]

    def __post_init__(self):
        for name in PROVIDER_FIELDS[:3]:
            _text(getattr(self, name), name)
        for name in PROVIDER_FIELDS[3:]:
            _hash(getattr(self, name), name)
        for name in CALLBACK_FIELDS:
            if not callable(getattr(self, name)):
                raise ValueError(f"provider {name} is not callable")

    def identity(self):
        return {name: getattr(self, name) for name in PROVIDER_FIELDS}


def _validate_payload(payload):
    _fields(payload, ("format", "version", "provider", "root", "objective", "root_actions", "graph", "graph_hash", "resources", "claim_limit"), "terminal certificate")
    canonical_json(payload)
    if payload["format"] != FORMAT or type(payload["version"]) is not int or payload["version"] != VERSION or payload["claim_limit"] != CLAIM_LIMIT:
        raise ValueError("unsupported terminal certificate or claim limit")
    _fields(payload["provider"], PROVIDER_FIELDS, "provider identity")
    for name in PROVIDER_FIELDS[:3]:
        _text(payload["provider"][name], name)
    for name in PROVIDER_FIELDS[3:]:
        _hash(payload["provider"][name], name)
    root = payload["root"]
    _fields(root, ("snapshot", "fingerprint", "actor", "metadata"), "certificate root")
    if type(root["snapshot"]) is not dict or type(root["metadata"]) is not dict:
        raise ValueError("root snapshot and metadata must be JSON objects")
    _hash(root["fingerprint"], "root fingerprint")
    _actor(root["actor"])
    _fields(payload["objective"], ("kind", "seat"), "objective")
    if payload["objective"]["kind"] != "accepted-terminal-wdl":
        raise ValueError("certificate objective is not accepted-terminal WDL")
    _text(payload["objective"]["seat"], "objective seat")
    _fields(payload["resources"], RESOURCE_FIELDS, "producer resources")
    if any(type(value) is not int or value < 0 for value in payload["resources"].values()) or payload["resources"]["terminal_simulation_backups"] != 0:
        raise ValueError("invalid producer resources or nonzero simulation backups")
    graph = payload["graph"]
    if type(graph) is not list or not graph:
        raise ValueError("a nonempty inline graph is required")
    _hash(payload["graph_hash"], "graph hash")
    if canonical_hash(graph) != payload["graph_hash"]:
        raise ValueError("terminal graph hash mismatch")
    nodes = {}
    for node in graph:
        _fields(node, ("fingerprint", "actor", "seats", "accepted", "bounds", "kind", "score", "actions", "unresolved_reason"), "graph node")
        fingerprint = node["fingerprint"]
        _hash(fingerprint, "node fingerprint")
        if fingerprint in nodes:
            raise ValueError("duplicate or contradictory node fingerprint")
        nodes[fingerprint] = node
        _actor(node["actor"])
        _seats(node["seats"])
        _bounds(node["bounds"])
        if type(node["accepted"]) is not bool or type(node["actions"]) is not list:
            raise ValueError("invalid node acceptance flag or action domain")
        if node["accepted"]:
            if node["actor"] != {"seat": None, "color": None}:
                raise ValueError("accepted node must have no actor")
        elif node["actor"]["color"] is None or node["actor"]["seat"] != node["seats"][node["actor"]["color"]]:
            raise ValueError("nonterminal actor does not match seat map")
        if node["kind"] == "terminal":
            if not node["accepted"] or node["actions"] or node["unresolved_reason"] is not None:
                raise ValueError("invalid accepted leaf")
            _score(node["score"])
            if node["bounds"][0] != node["bounds"][1]:
                raise ValueError("terminal leaf must claim exact bounds")
        elif node["kind"] == "expanded":
            if node["accepted"] or node["score"] is not None or node["unresolved_reason"] is not None or not node["actions"]:
                raise ValueError("invalid expanded nonterminal")
        elif node["kind"] == "unexpanded":
            if node["accepted"] or node["score"] is not None or node["actions"] or type(node["unresolved_reason"]) is not str or node["unresolved_reason"] not in UNRESOLVED_REASONS or node["bounds"] != [-1, 1]:
                raise ValueError("invalid unresolved nonterminal")
        else:
            raise ValueError("unsupported graph node kind")
        ids = set()
        for edge in node["actions"]:
            _fields(edge, ("id", "action", "child", "unresolved_reason"), "graph edge")
            if action_id(edge["action"]) != edge["id"] or edge["id"] in ids:
                raise ValueError("duplicate or incomplete action ID")
            ids.add(edge["id"])
            if edge["child"] is None:
                if type(edge["unresolved_reason"]) is not str or edge["unresolved_reason"] not in UNRESOLVED_REASONS:
                    raise ValueError("unknown child requires an explicit unresolved reason")
            else:
                _hash(edge["child"], "child fingerprint")
                if edge["unresolved_reason"] is not None:
                    raise ValueError("resolved edge cannot claim an unresolved reason")
    root_id = root["fingerprint"]
    if root_id not in nodes or nodes[root_id]["actor"] != root["actor"]:
        raise ValueError("root node missing or actor mismatched")
    if payload["objective"]["seat"] not in nodes[root_id]["seats"].values():
        raise ValueError("objective identity is not a root seat")
    root_identities = set(nodes[root_id]["seats"].values())
    indegree = dict.fromkeys(nodes, 0)
    for node in nodes.values():
        if set(node["seats"].values()) != root_identities:
            raise ValueError("seat identity set changed inside graph")
        for edge in node["actions"]:
            if edge["child"] is not None:
                if edge["child"] not in nodes:
                    raise ValueError("dangling proof edge")
                indegree[edge["child"]] += 1
    reachable, frontier = set(), [root_id]
    while frontier:
        fingerprint = frontier.pop()
        if fingerprint in reachable:
            continue
        reachable.add(fingerprint)
        frontier.extend(edge["child"] for edge in nodes[fingerprint]["actions"] if edge["child"] is not None)
    if reachable != set(nodes):
        raise ValueError("unreachable proof nodes")
    queue = deque(fingerprint for fingerprint, count in indegree.items() if count == 0)
    order = []
    while queue:
        fingerprint = queue.popleft()
        order.append(fingerprint)
        for edge in nodes[fingerprint]["actions"]:
            if edge["child"] is not None:
                indegree[edge["child"]] -= 1
                if indegree[edge["child"]] == 0:
                    queue.append(edge["child"])
    if len(order) != len(nodes):
        raise ValueError("cyclic claimed proof graph")
    if type(payload["root_actions"]) is not list:
        raise ValueError("root action classification must be a list")
    root_claims = {}
    for row in payload["root_actions"]:
        _fields(row, ("id", "bounds"), "root action bounds")
        _action_id(row["id"])
        _bounds(row["bounds"])
        if row["id"] in root_claims:
            raise ValueError("duplicate root action classification")
        root_claims[row["id"]] = row["bounds"]
    if set(root_claims) != {edge["id"] for edge in nodes[root_id]["actions"]}:
        raise ValueError("root action classification omits or invents alternatives")
    return nodes, order


def seal_certificate(payload):
    """Detach a caller-authored graph and calculate its hash; never solve it."""
    result = _copy_json(payload)
    result["graph_hash"] = canonical_hash(result["graph"])
    return result


@dataclass(frozen=True)
class TerminalCertificate:
    _payload_json: str

    def __post_init__(self):
        payload = json.loads(self._payload_json)
        _validate_payload(payload)
        object.__setattr__(self, "_payload_json", canonical_json(payload))

    @classmethod
    def from_dict(cls, payload):
        return cls(canonical_json(payload))

    def to_dict(self):
        return json.loads(self._payload_json)


class TerminalIntegrityError(RuntimeError):
    """Callback failure, mutation, or contradiction invalidates the check."""

    work = None


@dataclass(frozen=True)
class TerminalCheckReport:
    _payload_json: str

    def to_dict(self):
        return json.loads(self._payload_json)

    def __getattr__(self, name):
        try:
            return self.to_dict()[name]
        except KeyError as error:
            raise AttributeError(name) from error


class _Exhausted(Exception):
    pass


class _Checker:
    def __init__(self, provider, node_limit, cancelled):
        self.provider, self.node_limit, self.cancelled = provider, node_limit, cancelled
        self.work = dict.fromkeys(("nodes_checked", "unknown_successors_checked", "transition_attempts", "legal_action_enumerations", "terminal_scores_checked", "callback_calls", "terminal_simulation_backups"), 0)

    def raw(self, name, callback, state, *args):
        try:
            before = pickle.dumps((state, args), protocol=5)
        except Exception as error:
            raise TerminalIntegrityError("provider state is not structurally guardable") from error
        self.work["callback_calls"] += 1
        try:
            return callback(state, *args)
        except TerminalIntegrityError:
            raise
        except Exception as error:
            raise TerminalIntegrityError(f"{name} callback failed") from error
        finally:
            try:
                unchanged = pickle.dumps((state, args), protocol=5) == before
            except Exception as error:
                raise TerminalIntegrityError(f"{name} corrupted callback inputs") from error
            if not unchanged:
                raise TerminalIntegrityError(f"{name} mutated callback inputs")

    def identity(self, state):
        snapshot = _copy_json(self.raw("snapshot", self.provider.snapshot, state))
        if type(snapshot) is not dict:
            raise TerminalIntegrityError("provider snapshot is not a JSON object")
        fingerprint = self.raw("fingerprint", self.provider.fingerprint, state)
        try:
            _hash(fingerprint, "provider fingerprint")
        except ValueError as error:
            raise TerminalIntegrityError(str(error)) from error
        return snapshot, fingerprint

    def call(self, name, state, *args, callback=None):
        before = self.identity(state)
        try:
            return self.raw(name, callback or getattr(self.provider, name), state, *args)
        finally:
            after = self.identity(state)
            if after[1] != before[1] or canonical_json(after[0]) != canonical_json(before[0]):
                raise TerminalIntegrityError(f"{name} changed complete snapshot or fingerprint")

    def poll(self, state):
        if self.cancelled is not None:
            value = self.call("cancellation", state, callback=lambda _state: self.cancelled())
            if type(value) is not bool:
                raise TerminalIntegrityError("cancellation callback must return bool")
            if value:
                raise _Exhausted("cancelled")
        if self.work["nodes_checked"] + self.work["unknown_successors_checked"] >= self.node_limit:
            raise _Exhausted("node-limit")

    def envelope(self, state, root_identities):
        actor = _copy_json(self.call("actor", state))
        seats = _copy_json(self.call("seats", state))
        accepted = self.call("accepted", state)
        try:
            _actor(actor)
            _seats(seats)
        except ValueError as error:
            raise TerminalIntegrityError("invalid provider actor/seat data") from error
        if type(accepted) is not bool or set(seats.values()) != root_identities:
            raise TerminalIntegrityError("accepted flag or conserved seat identities invalid")
        if accepted:
            if actor != {"seat": None, "color": None}:
                raise TerminalIntegrityError("accepted state still has an actor")
        elif actor["color"] is None or actor["seat"] != seats[actor["color"]]:
            raise TerminalIntegrityError("pending actor does not match seat identities")
        return actor, seats, accepted

    def legal(self, state):
        self.work["legal_action_enumerations"] += 1

        def collect(source):
            # Consume and detach inside the guard, including iterator failures.
            return [_copy_json(action) for action in self.provider.legal_actions(source)]

        actions = self.call("legal_actions", state, callback=collect)
        try:
            result = {action_id(action): action for action in actions}
        except ValueError as error:
            raise TerminalIntegrityError("invalid provider action wire") from error
        if len(result) != len(actions):
            raise TerminalIntegrityError("provider legal actions contain duplicate IDs")
        return result

    def advance(self, state, action):
        self.work["transition_attempts"] += 1
        child = self.call("transition", state, deepcopy(action))
        try:
            return deepcopy(child)
        except Exception as error:
            raise TerminalIntegrityError("successor is not detached/copyable") from error


def check_certificate(certificate, root_state, provider, *, node_limit=10000, cancelled=None):
    """Recompute a supplied proof graph; never produce a graph or run MCTS.

    The configurable node budget charges graph nodes and explicitly unresolved
    successor-envelope checks separately; their sum may not exceed node_limit.
    Unknown successors supply no score or proof leaf even when truly accepted.
    """
    if not isinstance(certificate, TerminalCertificate):
        certificate = TerminalCertificate.from_dict(certificate)
    if not isinstance(provider, TerminalProvider):
        raise ValueError("TerminalProvider is required")
    if type(node_limit) is not int or node_limit < 0 or (cancelled is not None and not callable(cancelled)):
        raise ValueError("invalid checker resource limit or cancellation callback")
    payload = certificate.to_dict()
    nodes, order = _validate_payload(payload)
    checker = _Checker(provider, node_limit, cancelled)
    work = checker.work
    root_id = payload["root"]["fingerprint"]
    objective = payload["objective"]["seat"]
    reason, recomputed = None, {}
    terminal_root = None
    try:
        if provider.identity() != payload["provider"]:
            raise TerminalIntegrityError("provider identity or implementation hash mismatch")
        try:
            root = deepcopy(root_state)
        except Exception as error:
            raise TerminalIntegrityError("root state cannot be independently copied") from error
        snapshot, fingerprint = checker.identity(root)
        if canonical_json(snapshot) != canonical_json(payload["root"]["snapshot"]) or fingerprint != root_id:
            raise TerminalIntegrityError("root snapshot or complete fingerprint mismatch")
        metadata = _copy_json(checker.call("metadata", root))
        if type(metadata) is not dict or canonical_json(metadata) != canonical_json(payload["root"]["metadata"]):
            raise TerminalIntegrityError("provider-derived metadata/provenance mismatch")
        states, snapshots = {root_id: root}, {root_id: snapshot}
        root_identities = set(nodes[root_id]["seats"].values())
        for fingerprint in order:
            state = states[fingerprint]
            checker.poll(state)
            work["nodes_checked"] += 1
            node = nodes[fingerprint]
            current_snapshot, current_fingerprint = checker.identity(state)
            if current_fingerprint != fingerprint or canonical_json(current_snapshot) != canonical_json(snapshots[fingerprint]):
                raise TerminalIntegrityError("reconstructed node identity changed")
            actual_actor, actual_seats, actual_accepted = checker.envelope(state, root_identities)
            if actual_accepted != node["accepted"] or actual_actor != node["actor"] or actual_seats != node["seats"]:
                raise TerminalIntegrityError("actor, seat identity, or accepted-terminal contradiction")
            if fingerprint == root_id:
                terminal_root = actual_accepted
            if node["kind"] == "unexpanded":
                recomputed[fingerprint] = [-1, 1]
                continue
            legal = checker.legal(state)
            if actual_accepted:
                if legal:
                    raise TerminalIntegrityError("accepted state still has legal actions")
                work["terminal_scores_checked"] += 1
                actual_score = _copy_json(checker.call("score", state))
                try:
                    _score(actual_score)
                except ValueError as error:
                    raise TerminalIntegrityError("invalid provider terminal score") from error
                if actual_score != node["score"]:
                    raise TerminalIntegrityError("accepted terminal score mismatch")
                own_color = next(color for color, seat in actual_seats.items() if seat == objective)
                other_color = "W" if own_color == "B" else "B"
                margin = actual_score[own_color] - actual_score[other_color]
                value = (margin > 0) - (margin < 0)
                recomputed[fingerprint] = [value, value]
            else:
                if set(legal) != {edge["id"] for edge in node["actions"]}:
                    raise TerminalIntegrityError("expanded node omits or invents legal actions")
                for edge in sorted(node["actions"], key=lambda edge: edge["id"]):
                    # Even unresolved edges must represent legal real transitions.
                    child = checker.advance(state, legal[edge["id"]])
                    child_snapshot, child_id = checker.identity(child)
                    if child_id in snapshots and canonical_json(snapshots[child_id]) != canonical_json(child_snapshot):
                        raise TerminalIntegrityError("same fingerprint reconstructed contradictory snapshots")
                    snapshots.setdefault(child_id, child_snapshot)
                    if edge["child"] is None:
                        checker.poll(child)
                        work["unknown_successors_checked"] += 1
                        checker.envelope(child, root_identities)
                        continue
                    if child_id != edge["child"]:
                        raise TerminalIntegrityError("transition child fingerprint mismatch")
                    states.setdefault(child_id, child)
        for fingerprint in reversed(order):
            node = nodes[fingerprint]
            if node["kind"] == "expanded":
                bounds = [recomputed[edge["child"]] if edge["child"] is not None else [-1, 1] for edge in node["actions"]]
                aggregate = max if node["actor"]["seat"] == objective else min
                recomputed[fingerprint] = [aggregate(value[0] for value in bounds), aggregate(value[1] for value in bounds)]
            if node["bounds"] != recomputed[fingerprint]:
                raise TerminalIntegrityError("claimed node WDL bounds contradict accepted-terminal minimax")
        action_results = [{"id": edge["id"], "action": edge["action"], "bounds": recomputed[edge["child"]] if edge["child"] is not None else [-1, 1]}
                          for edge in sorted(nodes[root_id]["actions"], key=lambda edge: edge["id"])]
        claims = {row["id"]: row["bounds"] for row in payload["root_actions"]}
        if any(claims[row["id"]] != row["bounds"] for row in action_results):
            raise TerminalIntegrityError("claimed per-action WDL bounds are incorrect")
    except _Exhausted as error:
        reason = str(error)
        action_results = [{"id": row["id"], "action": json.loads(row["id"]), "bounds": [-1, 1]} for row in sorted(payload["root_actions"], key=lambda row: row["id"])]
    except Exception as error:
        if not isinstance(error, TerminalIntegrityError):
            error = TerminalIntegrityError(f"checker/provider integrity failure: {error}")
        error.work = _copy_json(work)
        raise error
    verified = reason is None
    root_bounds = recomputed[root_id] if verified else [-1, 1]
    root_exact = verified and root_bounds[0] == root_bounds[1]
    domain_complete = verified and nodes[root_id]["kind"] == "expanded"
    complete = domain_complete and all(row["bounds"][0] == row["bounds"][1] for row in action_results)
    report = {
        "verified": verified, "status": "verified" if verified else "unknown",
        "certificate_hash": canonical_hash(payload), "root_bounds": root_bounds,
        "root_value": root_bounds[0] if root_exact else None,
        "root_value_exact": root_exact, "root_domain_complete": domain_complete,
        "terminal_root": terminal_root, "decision_classified": complete,
        "complete_optimal_action_set": complete,
        "optimal_action_ids": [row["id"] for row in action_results if row["bounds"][0] == root_bounds[0]] if complete else [],
        "unresolved_action_ids": [row["id"] for row in action_results if row["bounds"][0] != row["bounds"][1]],
        "action_results": action_results, "reason": reason, "work": work,
        "claimed_resources": payload["resources"], "admission_record": False,
        "claim_limit": CLAIM_LIMIT,
    }
    return TerminalCheckReport(canonical_json(report))
