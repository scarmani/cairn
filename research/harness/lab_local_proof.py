"""Generic bounded local proofs; no game mechanics, search agent or memoization.

Providers supply complete legal domains and pure, deepcopyable/equality-comparable
state/action objects. A complete fingerprint includes every legality-relevant
field and history. This runner does not infer or detect tactical obligations.
"""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable


ORACLE_FORMAT = "varde-lab-local-proof"
ORACLE_VERSION = 1
CLAIM_LIMIT = "local predicate and declared horizon only; not optimal play"
DEFAULT_NODE_LIMIT = 10_000
STATUSES = frozenset(("proven", "disproven", "unknown"))


class ProofIntegrityError(RuntimeError):
    """An invalid provider/predicate prevents any certifiable result."""

    counters = None


class Truth(Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNRESOLVED = "unresolved"


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _hash(value, label):
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError(f"{label} must be a lowercase SHA-256 hash")
    return value


def _freeze(value):
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return MappingProxyType({key: _freeze(value[key]) for key in sorted(value)})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise ValueError("metadata must be finite JSON data")


def _thaw(value):
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _canonical(value):
    return json.dumps(_thaw(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Actor:
    seat: str | None
    color: str | None

    def __post_init__(self):
        if (self.seat is None) != (self.color is None):
            raise ValueError("actor seat and color must both be present or absent")
        if self.seat is not None:
            _text(self.seat, "actor seat")
            _text(self.color, "actor color")

    def to_dict(self):
        return {"seat": self.seat, "color": self.color}


@dataclass(frozen=True)
class QuantifierStep:
    quantifier: str
    actor: str = "any"
    action_kinds: tuple[str, ...] | None = None
    empty_domain: str = "unknown"

    def __post_init__(self):
        if self.quantifier not in ("exists", "forall"):
            raise ValueError("quantifier must be exists or forall")
        if self.actor not in ("any", "root-seat", "other-seat"):
            raise ValueError("invalid actor constraint")
        if self.empty_domain not in ("unknown", "vacuous"):
            raise ValueError("empty domain must be unknown or explicitly vacuous")
        if self.action_kinds is not None:
            if not isinstance(self.action_kinds, (tuple, list)) or not self.action_kinds:
                raise ValueError("restricted action kinds must be a nonempty sequence")
            kinds = tuple(_text(kind, "action kind") for kind in self.action_kinds)
            if len(set(kinds)) != len(kinds):
                raise ValueError("duplicate restricted action kinds")
            object.__setattr__(self, "action_kinds", tuple(sorted(kinds)))

    def to_dict(self):
        return {"quantifier": self.quantifier, "actor": self.actor,
                "action_kinds": list(self.action_kinds) if self.action_kinds is not None else None,
                "empty_domain": self.empty_domain}


@dataclass(frozen=True)
class LocalProofSpec:
    goal_id: str
    rules_id: str
    rules_revision: str
    scope: str
    schedule: tuple[QuantifierStep, ...] = ()
    parameters: Mapping = field(default_factory=dict)
    evaluation_mode: str = "at-horizon"
    rules_hash: str | None = None

    def __post_init__(self):
        for name in ("goal_id", "rules_id", "rules_revision", "scope"):
            _text(getattr(self, name), name)
        if not isinstance(self.schedule, (tuple, list)) or any(
                not isinstance(step, QuantifierStep) for step in self.schedule):
            raise ValueError("schedule must contain explicit QuantifierStep values")
        object.__setattr__(self, "schedule", tuple(self.schedule))
        if not isinstance(self.parameters, Mapping):
            raise ValueError("parameters must be a JSON object")
        object.__setattr__(self, "parameters", _freeze(self.parameters))
        if self.evaluation_mode not in ("at-horizon", "closure"):
            raise ValueError("invalid predicate evaluation mode")
        if self.rules_hash is not None:
            _hash(self.rules_hash, "rules hash")

    def to_dict(self):
        return {"goal_id": self.goal_id, "rules_id": self.rules_id,
                "rules_revision": self.rules_revision, "rules_hash": self.rules_hash,
                "scope": self.scope, "schedule": [step.to_dict() for step in self.schedule],
                "parameters": _thaw(self.parameters), "evaluation_mode": self.evaluation_mode}


@dataclass(frozen=True)
class ProofProvider:
    provider_hash: str
    legal_actions: Callable[[Any], Any]
    transition: Callable[[Any, Any], Any]
    fingerprint: Callable[[Any], str]
    actor: Callable[[Any], Actor]
    action_data: Callable[[Any], Mapping]

    def __post_init__(self):
        _hash(self.provider_hash, "provider hash")
        for name in ("legal_actions", "transition", "fingerprint", "actor", "action_data"):
            if not callable(getattr(self, name)):
                raise ValueError(f"provider {name} must be callable")


@dataclass(frozen=True)
class ActionRecord:
    id: str
    data: Mapping

    def __post_init__(self):
        if not isinstance(self.data, Mapping):
            raise ValueError("action wire data must be an object")
        data = _freeze(self.data)
        _text(data.get("action"), "action kind")
        if self.id != _canonical(data):
            raise ValueError("action ID must preserve complete canonical wire data")
        object.__setattr__(self, "data", data)

    def to_dict(self):
        return {"id": self.id, "data": _thaw(self.data)}


@dataclass(frozen=True)
class ProofContext:
    spec: LocalProofSpec
    root_actor: Actor
    root_fingerprint: str
    root_action: ActionRecord
    ply: int


@dataclass(frozen=True)
class ProofTrace:
    root_action_id: str | None
    ply: int
    actor: Actor
    state_hash: str
    event: str
    action_id: str | None = None
    status: str | None = None
    quantifier: str | None = None

    def to_dict(self):
        return {"root_action_id": self.root_action_id, "ply": self.ply,
                "actor": self.actor.to_dict(), "state_hash": self.state_hash,
                "event": self.event, "action_id": self.action_id,
                "status": self.status, "quantifier": self.quantifier}


@dataclass(frozen=True)
class ActionResult:
    action: ActionRecord
    status: str

    def __post_init__(self):
        if not isinstance(self.action, ActionRecord) or self.status not in STATUSES:
            raise ValueError("invalid action proof result")

    def to_dict(self):
        return {"action": self.action.to_dict(), "status": self.status}


@dataclass(frozen=True)
class LocalCertificate:
    spec: LocalProofSpec
    input_hash: str
    provider_hash: str
    predicate_hash: str
    root_actor: Actor
    action_results: tuple[ActionResult, ...]
    nodes: int
    node_limit: int
    transition_attempts: int
    action_enumerations: int
    actions_enumerated: int
    cancelled: bool
    limit_reached: bool
    traces: tuple[ProofTrace, ...]
    cache_hits: int = 0

    @property
    def proven_actions(self):
        return tuple(result.action for result in self.action_results if result.status == "proven")

    @property
    def disproven_actions(self):
        return tuple(result.action for result in self.action_results if result.status == "disproven")

    @property
    def unknown_actions(self):
        return tuple(result.action for result in self.action_results if result.status == "unknown")

    def to_dict(self):
        return {
            "format": ORACLE_FORMAT, "version": ORACLE_VERSION,
            "claim_limit": CLAIM_LIMIT, "spec": self.spec.to_dict(),
            "source_hash_provenance": "caller-declared rules/provider/predicate hashes; not independently verified",
            "hashes": {"input": self.input_hash, "spec": _digest(self.spec.to_dict()),
                       "rules": self.spec.rules_hash,
                       "rules_descriptor": _digest({"id": self.spec.rules_id, "revision": self.spec.rules_revision}),
                       "provider": self.provider_hash, "predicate": self.predicate_hash,
                       "oracle": ORACLE_HASH},
            "horizon": 1 + len(self.spec.schedule),
            "root_actor": self.root_actor.to_dict(),
            "action_results": [result.to_dict() for result in self.action_results],
            "proven_actions": [action.to_dict() for action in self.proven_actions],
            "disproven_actions": [action.to_dict() for action in self.disproven_actions],
            "unknown_actions": [action.to_dict() for action in self.unknown_actions],
            "nodes": self.nodes, "node_limit": self.node_limit,
            "transition_attempts": self.transition_attempts,
            "action_enumerations": self.action_enumerations,
            "root_action_enumerations": 1, "actions_enumerated": self.actions_enumerated,
            "cache_hits": self.cache_hits, "cancelled": self.cancelled,
            "limit_reached": self.limit_reached,
            "traces": [trace.to_dict() for trace in self.traces],
        }


def _copy(value, label):
    try:
        return deepcopy(value)
    except Exception as exc:
        raise ProofIntegrityError(f"{label} is not independently copyable") from exc


def _unchanged(value, before, label):
    try:
        equal = value == before
        if type(equal) is not bool or not equal:
            raise ProofIntegrityError(f"{label} mutated its input")
    except ProofIntegrityError:
        raise
    except Exception as exc:
        raise ProofIntegrityError(f"{label} cannot establish input equality") from exc


@dataclass
class _Frame:
    state: Any
    context: ProofContext
    index: int
    entered: bool = False
    step: QuantifierStep | None = None
    domain: tuple = ()
    next_action: int = 0
    statuses: list = field(default_factory=list)


class _Runner:
    def __init__(self, spec, provider, predicate, predicate_hash, node_limit, cancelled):
        self.spec, self.provider, self.predicate = spec, provider, predicate
        self.predicate_hash, self.node_limit = predicate_hash, node_limit
        self.cancel_callback = cancelled
        self.nodes = self.transition_attempts = self.action_enumerations = self.actions_enumerated = 0
        self.cancelled = self.limit_reached = False
        self.traces = []

    def fingerprint(self, state):
        before = _copy(state, "fingerprint state")
        try:
            value = self.provider.fingerprint(state)
            _hash(value, "state fingerprint")
        except Exception as exc:
            raise ProofIntegrityError("invalid or failed state fingerprint") from exc
        finally:
            _unchanged(state, before, "fingerprint callback")
        return value

    def call(self, label, callback, *args, states=(), actions=()):
        objects = tuple(states) + tuple(actions)
        copies = [_copy(value, label) for value in objects]
        hashes = [self.fingerprint(state) for state in states]
        try:
            return callback(*args)
        except ProofIntegrityError:
            raise
        except Exception as exc:
            raise ProofIntegrityError(f"{label} failed") from exc
        finally:
            for value, before in zip(objects, copies):
                _unchanged(value, before, label)
            for state, before in zip(states, hashes):
                if self.fingerprint(state) != before:
                    raise ProofIntegrityError(f"{label} changed the complete state fingerprint")

    def actor(self, state):
        actor = self.call("actor callback", self.provider.actor, state, states=(state,))
        if not isinstance(actor, Actor):
            raise ProofIntegrityError("actor callback must return Actor")
        return actor

    def enumerate(self, state):
        self.action_enumerations += 1

        def collect():
            actions = []
            for action in self.provider.legal_actions(state):
                self.actions_enumerated += 1
                actions.append(action)
            return tuple(actions)

        actions = self.call("legal-action enumeration", collect, states=(state,))
        records, seen = [], set()
        for action in actions:
            raw = self.call("action-data callback", self.provider.action_data, action, states=(state,), actions=(action,))
            try:
                record = ActionRecord(_canonical(raw), raw)
            except Exception as exc:
                raise ProofIntegrityError("invalid legal action wire data") from exc
            if record.id in seen:
                raise ProofIntegrityError("duplicate legal action")
            seen.add(record.id)
            records.append((action, record))
        # Provider iteration order must not affect which root gets scarce work.
        return tuple(sorted(records, key=lambda item: item[1].id))

    def poll_cancellation(self, state):
        if not self.cancelled:
            result = self.call("cancellation callback", self.cancel_callback, states=(state,))
            if type(result) is not bool:
                raise ProofIntegrityError("cancellation callback must return bool")
            self.cancelled = result

    def stopped(self, state):
        self.poll_cancellation(state)
        if self.cancelled:
            return "cancelled"
        if self.nodes >= self.node_limit:
            self.limit_reached = True
            return "node-limit"
        return None

    def trace(self, state, context, event, *, action=None, status=None, quantifier=None, ply=None):
        self.traces.append(ProofTrace(
            context.root_action.id if context else None,
            ply if ply is not None else context.ply if context else 0,
            self.actor(state), self.fingerprint(state), event,
            action.id if action else None, status, quantifier,
        ))

    def advance(self, state, action):
        self.transition_attempts += 1
        child = self.call("declared-legal transition", self.provider.transition,
                          state, action, states=(state,), actions=(action,))
        # An immutable provider may legitimately return the same value/object;
        # the source guards above and detached copy below still isolate traversal.
        child = _copy(child, "transition successor")
        self.nodes += 1
        self.fingerprint(child)
        self.actor(child)
        return child

    def truth(self, state, context):
        def context_data():
            return {"spec": context.spec.to_dict(), "root_actor": context.root_actor.to_dict(),
                    "root_fingerprint": context.root_fingerprint,
                    "root_action": context.root_action.to_dict(), "ply": context.ply}

        before = _digest(context_data())
        try:
            result = self.call("predicate callback", self.predicate, state, context, states=(state,))
        finally:
            if _digest(context_data()) != before:
                raise ProofIntegrityError("predicate callback mutated its context")
        if not isinstance(result, Truth):
            raise ProofIntegrityError("predicate callback must return a tri-state Truth")
        return {Truth.SATISFIED: "proven", Truth.VIOLATED: "disproven", Truth.UNRESOLVED: "unknown"}[result]

    def evaluate(self, state, context, index):
        # Explicit DFS keeps Python's recursion ceiling out of proof semantics.
        frames = [_Frame(state, context, index)]
        completed = None
        while frames:
            frame = frames[-1]
            state, context, index = frame.state, frame.context, frame.index
            if completed is not None:
                frame.statuses.append(completed)
                completed = None
            if not frame.entered:
                frame.entered = True
                if self.spec.evaluation_mode == "closure" or index >= len(self.spec.schedule):
                    status = self.truth(state, context)
                    if status != "unknown" or index >= len(self.spec.schedule):
                        self.trace(state, context, "closure" if self.spec.evaluation_mode == "closure" else "horizon", status=status)
                        frames.pop()
                        completed = status
                        continue
                step = self.spec.schedule[index]
                actor = self.actor(state)
                if (step.actor == "root-seat" and actor.seat != context.root_actor.seat
                        or step.actor == "other-seat" and (actor.seat is None or actor.seat == context.root_actor.seat)):
                    self.trace(state, context, "actor-mismatch", status="unknown", quantifier=step.quantifier)
                    frames.pop()
                    completed = "unknown"
                    continue
                reason = self.stopped(state)
                if reason:
                    self.trace(state, context, reason, status="unknown", quantifier=step.quantifier)
                    frames.pop()
                    completed = "unknown"
                    continue
                actions = self.enumerate(state)
                frame.step = step
                frame.domain = tuple(item for item in actions if step.action_kinds is None or item[1].data["action"] in step.action_kinds)
                if not frame.domain:
                    status = "unknown" if step.empty_domain == "unknown" else "proven" if step.quantifier == "forall" else "disproven"
                    self.trace(state, context, "empty-domain", status=status, quantifier=step.quantifier)
                    frames.pop()
                    completed = status
                    continue
            step, statuses = frame.step, frame.statuses
            decided = (step.quantifier == "exists" and "proven" in statuses
                       or step.quantifier == "forall" and "disproven" in statuses)
            if decided or frame.next_action >= len(frame.domain):
                if step.quantifier == "exists":
                    status = "proven" if "proven" in statuses else "disproven" if all(item == "disproven" for item in statuses) else "unknown"
                else:
                    status = "disproven" if "disproven" in statuses else "proven" if all(item == "proven" for item in statuses) else "unknown"
                self.trace(state, context, "quantified-result", status=status, quantifier=step.quantifier)
                frames.pop()
                completed = status
                continue
            action, record = frame.domain[frame.next_action]
            frame.next_action += 1
            reason = self.stopped(state)
            if reason:
                self.trace(state, context, reason, action=record, status="unknown", quantifier=step.quantifier)
                statuses.append("unknown")
                continue
            self.trace(state, context, "transition", action=record, quantifier=step.quantifier)
            child = self.advance(state, action)
            next_context = ProofContext(context.spec, context.root_actor, context.root_fingerprint,
                                        context.root_action, context.ply + 1)
            frames.append(_Frame(child, next_context, index + 1))
        return completed

    def counters(self):
        return MappingProxyType({
            "nodes": self.nodes, "node_limit": self.node_limit,
            "transition_attempts": self.transition_attempts,
            "action_enumerations": self.action_enumerations,
            "actions_enumerated": self.actions_enumerated, "cache_hits": 0,
            "cancelled": self.cancelled, "limit_reached": self.limit_reached,
        })


def classify_local(state, spec, *, provider, predicate, predicate_hash,
                   node_limit=DEFAULT_NODE_LIMIT, cancelled=lambda: False):
    """Classify every root action; local success is never a game-result value.

    The root counts as one entered state. Root enumeration always completes,
    even if already cancelled or node_limit=1, so all unresolved roots remain
    visible. Every attempted transition is counted; no transition starts after
    exhaustion. Schedule steps begin after the independently classified root
    action. Predicate/provider implementation hashes are caller declarations.
    """
    if not isinstance(spec, LocalProofSpec) or not isinstance(provider, ProofProvider):
        raise ValueError("explicit LocalProofSpec and ProofProvider are required")
    if not callable(predicate) or not callable(cancelled):
        raise ValueError("predicate and cancellation callbacks must be callable")
    _hash(predicate_hash, "predicate hash")
    if type(node_limit) is not int or node_limit < 1:
        raise ValueError("node limit must be a positive integer")
    runner = _Runner(spec, provider, predicate, predicate_hash, node_limit, cancelled)
    original = _copy(state, "root state")
    # Analyze another copy: a bad callback cannot modify the caller's game.
    root = _copy(state, "root state")
    try:
        runner.nodes = 1
        input_hash, root_actor = runner.fingerprint(root), runner.actor(root)
        runner.poll_cancellation(root)
        records = runner.enumerate(root)
        results = []
        for action, record in records:
            context = ProofContext(spec, root_actor, input_hash, record, 0)
            reason = runner.stopped(root)
            if reason:
                runner.trace(root, context, reason, action=record, status="unknown")
                status = "unknown"
            else:
                runner.trace(root, context, "root-transition", action=record)
                child = runner.advance(root, action)
                child_context = ProofContext(spec, root_actor, input_hash, record, 1)
                status = runner.evaluate(child, child_context, 0)
            results.append(ActionResult(record, status))
        if runner.fingerprint(root) != input_hash:
            raise ProofIntegrityError("proof traversal changed the root fingerprint")
        return LocalCertificate(
            spec, input_hash, provider.provider_hash, predicate_hash, root_actor,
            tuple(results), runner.nodes, node_limit, runner.transition_attempts,
            runner.action_enumerations, runner.actions_enumerated,
            runner.cancelled, runner.limit_reached, tuple(runner.traces),
        )
    except ProofIntegrityError as exc:
        exc.counters = runner.counters()
        raise
    finally:
        try:
            _unchanged(state, original, "proof runner")
        except ProofIntegrityError as exc:
            exc.counters = runner.counters()
            raise


ORACLE_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
