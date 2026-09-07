"""Generic terminal-only research MCTS; no game/evaluator/proof imports.

The three frozen recipes share statistics and random streams. Exact tree proofs
are distinct from terminal simulations; a rollout never proves its tree leaf.
This module launches no actual research. Providers/expanders are trusted local
callbacks with guarded, detached state and complete-history fingerprints.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import pickle
import time
from types import MappingProxyType

from research.harness.lab_terminal_cert import TerminalProvider, action_id, canonical_hash, canonical_json


FORMAT = "varde-lab-mcts-result"
VERSION = 1
ADMINISTRATIVE = frozenset(("swap", "pass", "resume", "accept", "finish-extension"))
FACT_FIELDS = ("action_kind", "extension_action", "captured_original", "captured_junction",
               "defended_group_count", "completed_cells")
CORE_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_SOURCE_FILES = (Path(__file__).resolve(), Path(__file__).with_name("lab_terminal_cert.py").resolve())
_SOURCE_BASELINE = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in _SOURCE_FILES)


@dataclass(frozen=True)
class Recipe:
    id: str
    reserved: bool
    terminal_proof: bool

    def to_dict(self):
        return {"id": self.id, "reserved": self.reserved, "terminal_proof": self.terminal_proof,
                "exploration": "sqrt(2)", "reward": "original-root-seat-terminal-wdl",
                "expansion": "ceil(2*sqrt(visits))+administrative" if self.reserved else "all-legal",
                "rng": "semantic-sha256-common-streams-0.1", "core_hash": CORE_HASH}


RECIPES = MappingProxyType({recipe.id: recipe for recipe in (
    Recipe("lab-uct-0.1", False, False), Recipe("lab-reserved-0.1", True, False),
    Recipe("lab-terminal-proof-0.1", True, True),
)})


@dataclass(frozen=True)
class SearchResult:
    _canonical_json: str
    _timing_json: str

    def canonical_dict(self):
        return json.loads(self._canonical_json)

    @property
    def canonical_hash(self):
        return canonical_hash(self.canonical_dict())

    @property
    def timing(self):
        return json.loads(self._timing_json)

    def to_dict(self):
        return self.canonical_dict() | {"timing": self.timing}


class MCTSIntegrityError(RuntimeError):
    """No decision is admissible after a provider or source contradiction."""

    partial_result = None

    @property
    def telemetry(self):
        return self.partial_result.canonical_dict() if self.partial_result else None

    @property
    def work(self):
        return self.telemetry["work"] if self.partial_result else None


class _Interrupted(Exception):
    def __init__(self, reason):
        self.reason = reason


def _copy(value):
    return json.loads(canonical_json(value))


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _finite_time(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _check_sources():
    if tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in _SOURCE_FILES) != _SOURCE_BASELINE:
        raise MCTSIntegrityError("loaded core/helper source bytes changed")


@dataclass(frozen=True)
class _Facts:
    action_kind: str
    extension_action: bool = False
    captured_original: int = 0
    captured_junction: int = 0
    defended_group_count: int = 0
    completed_cells: int = 0

    def vector(self):
        return (int(self.extension_action), self.captured_original + self.captured_junction,
                self.defended_group_count, self.completed_cells)


@dataclass(frozen=True)
class _Move:
    wire_json: str
    facts: _Facts

    @property
    def action(self):
        return json.loads(self.wire_json)


@dataclass
class _Node:
    state: object
    fingerprint: str
    actor: dict
    seats: dict
    accepted: bool
    domain: dict | None = None
    children: dict = field(default_factory=dict)
    visits: int = 0
    total: float = 0.0
    bounds: tuple = (-1, 1)
    terminal_value: int | None = None


class _Search:
    def __init__(self, provider, recipe, policy, simulations, seed, rollout_limit,
                 expand, cancelled, deadline, clock):
        self.provider, self.recipe, self.policy = provider, recipe, policy
        self.simulations, self.seed, self.rollout_limit = simulations, seed, rollout_limit
        self.expand, self.cancelled, self.deadline, self.clock = expand, cancelled, deadline, clock
        self.root = None
        self.root_fingerprint = None
        self.objective = None
        self.seat_set = None
        self.seen = {}
        self.score_observations = {}
        self.legal_observations = {}
        self.fact_observations = {}
        self.transition_observations = {}
        self.trace, self.rollout_lengths = [], []
        self.started_at = self.last_clock = None
        names = ("requested_iterations", "iterations_started", "completed_iterations", "aborted_iterations",
                 "unused_iterations", "terminal_simulations", "terminal_backups", "exact_proof_returns",
                 "proof_propagations", "backup_node_updates", "terminal_backup_node_updates",
                 "proof_backup_node_updates", "tree_nodes", "expansions", "legal_action_enumerations",
                 "actions_enumerated", "transition_requests", "expansion_batches", "successor_calls",
                 "callback_calls", "tree_actions", "rollout_actions", "terminal_score_evaluations")
        self.work = dict.fromkeys(names, 0)
        self.work["requested_iterations"] = simulations
        self.work["unused_iterations"] = simulations

    def now(self):
        value = self.clock()
        if not _finite_time(value) or self.last_clock is not None and value < self.last_clock:
            raise MCTSIntegrityError("clock must be finite and nondecreasing")
        self.last_clock = value
        return value

    def stop(self, source=None):
        if self.cancelled is not None:
            value = self.raw("cancellation", lambda _source: self.cancelled(), source)
            if type(value) is not bool:
                raise MCTSIntegrityError("cancellation must return an exact Boolean")
            if value:
                raise _Interrupted("cancelled")
        if self.deadline is not None and self.now() >= self.deadline:
            raise _Interrupted("deadline")

    def raw(self, name, callback, source, *args):
        try:
            before = pickle.dumps((source, args), protocol=5)
        except Exception as error:
            raise MCTSIntegrityError("callback input cannot be guarded") from error
        self.work["callback_calls"] += 1
        try:
            return callback(source, *args)
        except (_Interrupted, MCTSIntegrityError):
            raise
        except Exception as error:
            raise MCTSIntegrityError(f"{name} callback failed: {type(error).__name__}") from error
        finally:
            try:
                unchanged = pickle.dumps((source, args), protocol=5) == before
            except Exception as error:
                raise MCTSIntegrityError(f"{name} corrupted its input") from error
            if not unchanged:
                raise MCTSIntegrityError(f"{name} mutated its input")

    def describe(self, source):
        snapshot = _copy(self.raw("snapshot", self.provider.snapshot, source))
        metadata = _copy(self.raw("metadata", self.provider.metadata, source))
        fingerprint = self.raw("fingerprint", self.provider.fingerprint, source)
        actor = _copy(self.raw("actor", self.provider.actor, source))
        seats = _copy(self.raw("seats", self.provider.seats, source))
        accepted = self.raw("accepted", self.provider.accepted, source)
        if type(snapshot) is not dict or type(metadata) is not dict or not _sha(fingerprint):
            raise MCTSIntegrityError("invalid complete state fingerprint/snapshot/metadata")
        if (type(seats) is not dict or set(seats) != {"B", "W"}
                or any(type(seat) is not str or not seat for seat in seats.values())
                or len(set(seats.values())) != 2):
            raise MCTSIntegrityError("invalid bijective seat map")
        if self.seat_set is not None and set(seats.values()) != self.seat_set:
            raise MCTSIntegrityError("original seat identities changed")
        if type(actor) is not dict or set(actor) != {"seat", "color"} or type(accepted) is not bool:
            raise MCTSIntegrityError("invalid actor or accepted schema")
        if accepted:
            if actor != {"seat": None, "color": None}:
                raise MCTSIntegrityError("accepted state has an acting seat")
        elif (type(actor["color"]) is not str or actor["color"] not in seats
              or type(actor["seat"]) is not str or seats[actor["color"]] != actor["seat"]):
            raise MCTSIntegrityError("acting seat contradicts its color")
        guard = canonical_hash({"snapshot": snapshot, "metadata": metadata, "actor": actor,
                                "seats": seats, "accepted": accepted})
        if fingerprint in self.seen and self.seen[fingerprint] != guard:
            raise MCTSIntegrityError("full fingerprint collision or unstable provider state")
        self.seen[fingerprint] = guard
        return fingerprint, actor, seats, accepted

    def call(self, name, callback, source, *args):
        before = self.describe(source)
        try:
            return self.raw(name, callback, source, *args)
        finally:
            if self.describe(source) != before:
                raise MCTSIntegrityError(f"{name} changed the complete input identity")

    def node(self, source, *, tree=False):
        clone = deepcopy(source)
        before = self.describe(source)
        after = self.describe(clone)
        if before != after:
            raise MCTSIntegrityError("detaching a state changed its full identity")
        if tree:
            self.work["tree_nodes"] += 1
        return _Node(clone, *after)

    def legal(self, source):
        self.work["legal_action_enumerations"] += 1
        def materialize(state):
            result, seen = [], set()
            for wire in self.provider.legal_actions(state):
                self.work["actions_enumerated"] += 1
                self.stop(state)
                detached = _copy(wire)
                identifier = action_id(detached)
                if identifier in seen:
                    raise MCTSIntegrityError("duplicate legal action wire")
                seen.add(identifier)
                result.append(detached)
            return result
        result = self.call("legal_actions", materialize, source)
        fingerprint = self.describe(source)[0]
        observed = tuple(sorted(action_id(wire) for wire in result))
        if fingerprint in self.legal_observations and self.legal_observations[fingerprint] != observed:
            raise MCTSIntegrityError("legal domain changed at the same full state")
        self.legal_observations[fingerprint] = observed
        return result

    def read_row(self, row):
        wire = _copy(row.action)
        identifier = action_id(wire)
        if type(row.action_id) is not str or row.action_id != identifier or not callable(row.successor):
            raise MCTSIntegrityError("invalid full expansion action identity or successor")
        values = {name: getattr(row.facts, name) for name in FACT_FIELDS}
        if (values["action_kind"] != wire["action"] or type(values["action_kind"]) is not str
                or type(values["extension_action"]) is not bool
                or any(type(values[name]) is not int or values[name] < 0 for name in FACT_FIELDS[2:])):
            raise MCTSIntegrityError("invalid frozen structural facts")
        return identifier, _Move(identifier, _Facts(**values))

    def batch(self, node):
        self.stop(node.state)
        self.work["expansion_batches"] += 1
        rows = None
        if self.expand is not None:
            def materialize(source):
                result = self.expand(source)
                if type(result) is not tuple:
                    raise MCTSIntegrityError("expander must return the complete immutable tuple")
                return result
            rows = self.call("expand", materialize, node.state)
        legal = self.legal(node.state)
        domain = {action_id(wire): _Move(action_id(wire), _Facts(wire["action"])) for wire in legal}
        originals = {}
        if rows is not None:
            supplied = {}
            for row in rows:
                self.stop(node.state)
                identifier, move = self.call("expansion_row", lambda _s: self.read_row(row), node.state)
                if identifier in supplied:
                    raise MCTSIntegrityError("duplicate expansion row")
                supplied[identifier], originals[identifier] = move, row
            if set(domain) != set(supplied):
                raise MCTSIntegrityError("expansion domain differs from complete legal actions")
            domain = supplied
        if node.accepted and domain or not node.accepted and not domain:
            raise MCTSIntegrityError("legal domain contradicts accepted terminal status")
        if node.domain is not None and domain != node.domain:
            raise MCTSIntegrityError("legal actions/facts changed at the same full state")
        observed = canonical_hash([{ "action_id": key,
            "facts": {name: getattr(move.facts, name) for name in FACT_FIELDS}}
            for key, move in sorted(domain.items())])
        if node.fingerprint in self.fact_observations and self.fact_observations[node.fingerprint] != observed:
            raise MCTSIntegrityError("structural facts changed at the same full state")
        self.fact_observations[node.fingerprint] = observed
        node.domain = domain
        return originals

    def advance(self, node, identifier, originals):
        self.stop(node.state)
        wire = node.domain[identifier].action
        self.work["transition_requests"] += 1
        authority = self.call("transition", self.provider.transition, node.state, _copy(wire))
        resolved = self.node(authority)
        transition_key = (node.fingerprint, identifier)
        if transition_key in self.transition_observations and self.transition_observations[transition_key] != resolved.fingerprint:
            raise MCTSIntegrityError("authoritative successor changed for the same full state/action")
        self.transition_observations[transition_key] = resolved.fingerprint
        if identifier in originals:
            # Each use is compared with the authoritative transition, which is
            # a cache hit in the production adapter, not a new rules scan.
            row = originals[identifier]
            before = self.read_row(row)
            self.work["successor_calls"] += 1
            try:
                candidate = self.call("successor", lambda _s: row.successor(), node.state)
            finally:
                if self.read_row(row) != before:
                    raise MCTSIntegrityError("successor callback mutated its expansion row")
            candidate_info = self.describe(candidate)
            if candidate_info != (resolved.fingerprint, resolved.actor, resolved.seats, resolved.accepted):
                raise MCTSIntegrityError("expanded successor contradicts authoritative transition")
        return resolved

    def semantic(self, label, node, identifier="", iteration=None, depth=None):
        return canonical_hash({"stream": label, "root": self.root_fingerprint,
            "node": node.fingerprint, "seed": self.seed, "action": identifier,
            "iteration": iteration, "depth": depth})

    def tier(self, move):
        if move.facts.action_kind in ADMINISTRATIVE:
            return 0
        vector = move.facts.vector()
        return next((index + 1 for index, value in enumerate(vector) if value > 0), 5)

    def exposed(self, node):
        if node.domain is None:
            return (), 0
        order = sorted(node.domain, key=lambda key: (
            self.tier(node.domain[key]) if self.recipe.reserved else 0,
            self.semantic("expansion-order", node, key)))
        if not self.recipe.reserved:
            return tuple(order), len(order)
        threshold = min(len(order), max(1, math.ceil(2 * math.sqrt(node.visits))))
        mandatory = [key for key in order if node.domain[key].facts.action_kind in ADMINISTRATIVE]
        allowed = set(mandatory)
        for key in order:
            if len(allowed) >= threshold:
                break
            allowed.add(key)
        return tuple(key for key in order if key in allowed), threshold

    def choose_tree(self, node, iteration):
        exposed, _threshold = self.exposed(node)
        for key in exposed:
            if key not in node.children:
                return key, True
        maximize = node.actor["seat"] == self.objective
        def rating(key):
            child = node.children[key]
            if not child.visits:
                return float("inf")
            mean = child.total / child.visits
            exploitation = mean if maximize else 1 - mean
            return exploitation + math.sqrt(2 * math.log(max(1, node.visits)) / child.visits)
        chosen = min(exposed, key=lambda key: (-rating(key), self.semantic("uct-tie", node, key, iteration)))
        return chosen, False

    def choose_rollout(self, node, iteration, depth):
        identifiers = tuple(node.domain)
        uniform = self.policy == "uniform"
        if not uniform:
            uniform = int(self.semantic("light-explore", node, iteration=iteration, depth=depth), 16) % 10 == 0
        if uniform:
            return min(identifiers, key=lambda key: self.semantic("rollout-uniform", node, key, iteration, depth))
        best = max(move.facts.vector() for move in node.domain.values())
        return min((key for key in identifiers if node.domain[key].facts.vector() == best),
                   key=lambda key: self.semantic("rollout-light", node, key, iteration, depth))

    def terminal(self, node):
        if not node.accepted:
            raise MCTSIntegrityError("attempt to score a nonaccepted state")
        if node.terminal_value is None:
            if self.legal(node.state):
                raise MCTSIntegrityError("accepted state has legal actions")
            self.work["terminal_score_evaluations"] += 1
            score = _copy(self.call("score", self.provider.score, node.state))
            if type(score) is not dict or set(score) != {"B", "W"} or any(type(value) is not int for value in score.values()):
                raise MCTSIntegrityError("accepted score must be two exact integers")
            previous = self.score_observations.get(node.fingerprint)
            if previous is not None and previous != score:
                raise MCTSIntegrityError("contradictory accepted scores at the same full state")
            self.score_observations[node.fingerprint] = dict(score)
            if self.objective is None:
                return None
            color = next(color for color, seat in node.seats.items() if seat == self.objective)
            margin = score[color] - score["W" if color == "B" else "B"]
            node.terminal_value = (margin > 0) - (margin < 0)
        return node.terminal_value

    def rollout(self, node, iteration, depth, active):
        length = 0
        while True:
            self.stop(node.state)
            if node.accepted:
                return self.terminal(node), length, node.fingerprint
            if depth >= self.rollout_limit:
                raise _Interrupted("watchdog")
            rows = self.batch(node)
            key = self.choose_rollout(node, iteration, depth)
            node = self.advance(node, key, rows)
            depth += 1
            length += 1
            self.work["rollout_actions"] += 1
            if node.fingerprint in active:
                raise MCTSIntegrityError("repeated active full state during rollout")
            active.add(node.fingerprint)

    def propagate(self, path):
        if not self.recipe.terminal_proof:
            return
        for node in reversed(path):
            before = node.bounds
            if node.accepted and node.terminal_value is not None:
                node.bounds = (node.terminal_value, node.terminal_value)
            elif node.domain:
                bounds = [node.children[key].bounds if key in node.children else (-1, 1) for key in node.domain]
                operation = max if node.actor["seat"] == self.objective else min
                node.bounds = (operation(pair[0] for pair in bounds), operation(pair[1] for pair in bounds))
            if node.bounds != before:
                self.work["proof_propagations"] += 1

    def iteration(self, index):
        node = self.root
        path, active = [node], {node.fingerprint}
        depth, root_action = 0, None
        outcome, rollout_length, final_id = None, 0, None
        while True:
            self.stop(node.state)
            if self.recipe.terminal_proof and node.bounds[0] == node.bounds[1]:
                value, outcome = node.bounds[0], "proof"
                break
            if node.accepted:
                value, outcome, final_id = self.terminal(node), "terminal", node.fingerprint
                break
            if depth >= self.rollout_limit:
                raise _Interrupted("watchdog")
            rows = self.batch(node) if node.domain is None else None
            key, expand = self.choose_tree(node, index)
            if root_action is None:
                root_action = key
            if expand:
                if rows is None:
                    rows = self.batch(node)
                child = self.advance(node, key, rows)
                self.work["tree_nodes"] += 1
                self.work["expansions"] += 1
                node.children[key] = child
            else:
                child = node.children[key]
            node = child
            depth += 1
            self.work["tree_actions"] += 1
            if node.fingerprint in active:
                raise MCTSIntegrityError("repeated active full state in selected tree path")
            active.add(node.fingerprint)
            path.append(node)
            if expand:
                if node.accepted:
                    value, outcome, final_id = self.terminal(node), "terminal", node.fingerprint
                else:
                    value, rollout_length, final_id = self.rollout(node, index, depth, active)
                    outcome = "terminal"
                break
        reward = (value + 1) / 2
        for visited in path:
            visited.visits += 1
            visited.total += reward
        self.work["backup_node_updates"] += len(path)
        if outcome == "terminal":
            self.work["terminal_simulations"] += 1
            self.work["terminal_backups"] += 1
            self.work["terminal_backup_node_updates"] += len(path)
            self.rollout_lengths.append(rollout_length)
        else:
            self.work["exact_proof_returns"] += 1
            self.work["proof_backup_node_updates"] += len(path)
        self.propagate(path)
        self.work["completed_iterations"] += 1
        self.trace.append({"iteration": index, "outcome": outcome, "root_action_id": root_action,
            "tree_actions": depth, "rollout_actions": rollout_length, "root_seat_wdl": value,
            "terminal_fingerprint": final_id})

    def result(self, status, reason):
        configuration = {"policy": self.policy, "simulations": self.simulations, "seed": self.seed,
                         "rollout_limit": self.rollout_limit, "expanded_facts": self.expand is not None}
        recipe = self.recipe.to_dict()
        identity = {"provider": self.provider.identity(), "recipe": recipe, "configuration": configuration,
                    "root_fingerprint": self.root_fingerprint}
        actions, selected = [], None
        exposed, threshold = self.exposed(self.root) if self.root else ((), 0)
        root_exact = bool(self.root and self.recipe.terminal_proof and self.root.bounds[0] == self.root.bounds[1])
        for key, move in sorted((self.root.domain or {}).items()) if self.root else ():
            child = self.root.children.get(key)
            bounds = child.bounds if child else (-1, 1)
            actions.append({"action": move.action, "action_id": key, "visits": child.visits if child else 0,
                "root_mean": child.total / child.visits if child and child.visits else None,
                "bounds": list(bounds), "exposed": key in exposed, "expanded": child is not None,
                "proven_optimal": root_exact and bounds == self.root.bounds})
        proven = [row["action_id"] for row in actions if row["proven_optimal"]]
        if status == "complete":
            eligible = [row for row in actions if row["action_id"] in proven] if root_exact else [row for row in actions if row["visits"]]
            if not eligible:
                raise MCTSIntegrityError("completed search has no justified root decision")
            chosen = min(eligible, key=lambda row: (-row["visits"], -row["root_mean"],
                         self.semantic("final-tie", self.root, row["action_id"])))
            selected = chosen["action"]
        self.work["aborted_iterations"] = self.work["iterations_started"] - self.work["completed_iterations"]
        self.work["unused_iterations"] = self.simulations - self.work["iterations_started"]
        payload = {"format": FORMAT, "version": VERSION, "status": status, "reason": reason,
            "selected_action": selected, "objective_seat": self.objective,
            "root_fingerprint": self.root_fingerprint,
            "root_bounds": list(self.root.bounds) if self.root and self.objective else None,
            "root_actions": actions, "exposure_threshold": threshold,
            "complete_optimal_action_set": bool(actions) and root_exact and all(row["bounds"][0] == row["bounds"][1] for row in actions),
            "proven_optimal_action_ids": proven,
            "unresolved_action_ids": [row["action_id"] for row in actions if row["bounds"][0] != row["bounds"][1]],
            "configuration": configuration, "recipe": recipe, "provider": self.provider.identity(),
            "core_hash": CORE_HASH, "agent_hash": canonical_hash(identity), "work": self.work,
            "rollout_lengths": self.rollout_lengths, "iteration_trace": self.trace,
            "admission_record": False, "adapter_work": "reported separately by the source-bound caller"}
        finished = self.now()
        if status in ("complete", "already-terminal") and self.deadline is not None and finished >= self.deadline:
            payload.update(status="incomplete", reason="deadline", selected_action=None)
        timing = {"elapsed_seconds": finished - self.started_at if self.started_at is not None else None}
        return SearchResult(canonical_json(payload), canonical_json(timing))


def search(root, provider, *, recipe, policy, simulations, seed, rollout_limit,
           expand=None, cancelled=None, deadline=None, clock=time.monotonic):
    """Fixed-work synthetic/research search; this API never launches a job."""
    if (type(simulations) is not int or not 1 <= simulations <= 4096
            or type(seed) is not int or type(rollout_limit) is not int or rollout_limit < 1
            or type(recipe) is not str or recipe not in RECIPES
            or type(policy) is not str or policy not in ("uniform", "light")
            or deadline is not None and not _finite_time(deadline)
            or expand is not None and not callable(expand)
            or cancelled is not None and not callable(cancelled) or not callable(clock)):
        raise ValueError("invalid frozen MCTS configuration")
    if not isinstance(provider, TerminalProvider):
        raise ValueError("frozen TerminalProvider required")
    engine = _Search(provider, RECIPES[recipe], policy, simulations, seed, rollout_limit,
                     expand, cancelled, deadline, clock)
    original = None

    def failed(cause):
        error = cause if isinstance(cause, MCTSIntegrityError) else MCTSIntegrityError(f"search integrity failure: {type(cause).__name__}")
        try:
            error.partial_result = engine.result("integrity-failure", "integrity-failure")
        except Exception:
            # Invalid late clocks cannot erase already observed canonical work.
            engine.clock = lambda: engine.last_clock if engine.last_clock is not None else 0
            error.partial_result = engine.result("integrity-failure", "integrity-failure")
        return error

    try:
        engine.started_at = engine.now()
        engine.stop()
        _check_sources()
        original = pickle.dumps(root, protocol=5)
        engine.root = engine.node(deepcopy(root), tree=True)
        engine.root_fingerprint = engine.root.fingerprint
        engine.seat_set = set(engine.root.seats.values())
        if engine.root.accepted:
            engine.terminal(engine.root)
            status, reason = "already-terminal", "accepted-root"
        else:
            engine.objective = engine.root.actor["seat"]
            status, reason = "complete", "budget-completed"
            for index in range(simulations):
                engine.stop(engine.root.state)
                engine.work["iterations_started"] += 1
                engine.iteration(index)
                if engine.recipe.terminal_proof and engine.root.bounds[0] == engine.root.bounds[1]:
                    reason = "root-proven"
                    break
        engine.stop(engine.root.state)
        _check_sources()
        if pickle.dumps(root, protocol=5) != original:
            raise MCTSIntegrityError("caller root changed during search")
        return engine.result(status, reason)
    except _Interrupted as stopped:
        try:
            _check_sources()
            if original is not None and pickle.dumps(root, protocol=5) != original:
                raise MCTSIntegrityError("caller root changed before interruption")
            return engine.result("incomplete", stopped.reason)
        except Exception as cause:
            raise failed(cause) from cause
    except Exception as cause:
        try:
            _check_sources()
        except Exception as source_error:
            raise failed(source_error) from cause
        error = failed(cause)
        if error is cause:
            raise
        raise error from cause
