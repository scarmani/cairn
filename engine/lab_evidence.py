"""Evidence cards: explicit missingness and provenance, never a beauty score.

This schema does not infer qualification from win rates. Research must supply
hash-linked admission records, and human-only dimensions remain unmeasured until
human observations actually exist.
"""

from copy import deepcopy
import hashlib
import json
import math


EVIDENCE_SCHEMA = 1
EVIDENCE_STATUSES = (
    "verified", "observed", "provisional", "unmeasured", "contradicted",
)
DIMENSIONS = (
    "correctness", "rule_economy", "tactical_structure", "strategic_depth",
    "strategic_variety", "closure", "aesthetic_potential",
)
HUMAN_ONLY = ("readability", "beauty", "replay_desire", "memorable_understanding")
RECIPES = (
    "lab-uct-0.1", "lab-reserved-0.1", "lab-terminal-proof-0.1",
)
ROLLOUT_POLICIES = ("uniform", "light")
DEVELOPMENT_BUDGETS = (64, 256, 1024, 2048)


def canonical_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()


def evidence_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("evidence contains non-finite values")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("evidence keys must be strings")
        for item in value.values():
            _finite_json(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _finite_json(item)
    canonical_bytes(value)


def entry(status="unmeasured", *, value=None, sample_size=0,
          provenance=(), uncertainty="Not measured", scope=None,
          source_kind="computer"):
    if status not in EVIDENCE_STATUSES:
        raise ValueError("unknown evidence status")
    if type(sample_size) is not int or sample_size < 0:
        raise ValueError("sample_size must be a nonnegative integer")
    if not isinstance(uncertainty, str) or not uncertainty.strip():
        raise ValueError("uncertainty must be explicit")
    if status == "unmeasured" and (value is not None or sample_size):
        raise ValueError("missing evidence is null, not a zero rating or a sample")
    if not isinstance(provenance, (tuple, list)) or not all(
        isinstance(source, str) and source.strip() for source in provenance
    ):
        raise ValueError("provenance must contain nonempty source references")
    if status != "unmeasured" and not provenance:
        raise ValueError("reported evidence requires provenance")
    if source_kind not in ("computer", "human-observation", "mechanical-proof", "design"):
        raise ValueError("unknown evidence source kind")
    result = {
        "status": status, "value": deepcopy(value), "sample_size": sample_size,
        "provenance": list(provenance), "uncertainty": uncertainty, "scope": scope,
        "source_kind": source_kind,
    }
    _finite_json(result)
    return result


def empty_card(ruleset, revision, *, source_commit=None, rules_hash=None):
    if not all(isinstance(item, str) and item for item in (ruleset, revision)):
        raise ValueError("ruleset and revision are required")
    return {
        "schema": EVIDENCE_SCHEMA,
        "ruleset": ruleset, "revision": revision,
        "source_commit": source_commit, "rules_hash": rules_hash,
        "dimensions": {name: entry() for name in DIMENSIONS},
        "human_observations": {name: entry() for name in HUMAN_ONLY},
        "mcts_admission": {
            "status": "unmeasured", "recipe": None, "agent_hash": None,
            "development_positions": 0, "holdout_positions": 0,
            "policies": {policy: "unmeasured" for policy in ROLLOUT_POLICIES},
            "manifest_hash": None, "result_hash": None,
        },
        "comparative_games": 0,
        "comparative_headline_allowed": False,
        "shortlist": {"qualified": False, "design_priority": None},
    }


def validate_card(card):
    """Validate interchange shape, including the negative-evidence firewall."""
    _finite_json(card)
    if card.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("unsupported evidence card")
    if not all(isinstance(card.get(k), str) and card[k] for k in ("ruleset", "revision")):
        raise ValueError("missing evidence identity")
    for name, expected in (("dimensions", DIMENSIONS), ("human_observations", HUMAN_ONLY)):
        if set(card.get(name, {})) != set(expected):
            raise ValueError("incomplete evidence dimensions")
        for item in card[name].values():
            if not isinstance(item, dict):
                raise ValueError("malformed evidence entry")
            entry(**item)
            if name == "human_observations" and item["status"] != "unmeasured":
                if item.get("source_kind") != "human-observation" or item["sample_size"] < 1:
                    raise ValueError("human-only dimensions require actual human observations")
    admission = card.get("mcts_admission", {})
    if admission.get("status") not in (
        "unmeasured", "incomplete", "failed", "admitted",
    ):
        raise ValueError("invalid admission status")
    if set(admission.get("policies", {})) != set(ROLLOUT_POLICIES):
        raise ValueError("both rollout policies must be reported")
    if any(value not in ("unmeasured", "incomplete", "failed", "passed")
           for value in admission["policies"].values()):
        raise ValueError("invalid policy admission status")
    for key in ("development_positions", "holdout_positions"):
        if type(admission.get(key)) is not int or admission[key] < 0:
            raise ValueError("corpus counts must be nonnegative integers")
    for key in ("agent_hash", "manifest_hash", "result_hash"):
        digest = admission.get(key)
        if digest is not None and (
            not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("admission hash must be a SHA-256 digest")
    if admission["status"] == "admitted":
        if admission.get("recipe") not in RECIPES or not all(
            admission.get(k) for k in ("agent_hash", "manifest_hash", "result_hash")
        ):
            raise ValueError("admission must be hash-linked to a frozen recipe")
        if any(admission.get(k, 0) < 8 for k in ("development_positions", "holdout_positions")):
            raise ValueError("minimum independent corpus not met")
        if any(value != "passed" for value in admission["policies"].values()):
            raise ValueError("policy-robust admission requires both policies")
    games = card.get("comparative_games")
    if type(games) is not int or games < 0:
        raise ValueError("invalid completed comparative game count")
    if type(card.get("comparative_headline_allowed")) is not bool:
        raise ValueError("headline authorization must be boolean")
    shortlist = card.get("shortlist")
    if not isinstance(shortlist, dict) or type(shortlist.get("qualified")) is not bool:
        raise ValueError("shortlist qualification must be explicit and boolean")
    priority = shortlist.get("design_priority")
    if priority is not None and (type(priority) is not int or priority < 1):
        raise ValueError("provisional design priority must be a positive integer or null")
    if card["comparative_headline_allowed"] or shortlist["qualified"]:
        if admission["status"] != "admitted" or games < 100:
            raise ValueError("qualified comparison requires admission and 100 completed games")
    return deepcopy(card)


def frozen_program():
    """Predeclared search/gate parameters, included in every research manifest."""
    return {
        "schema": 1, "revision": "rules-lab-program-0.1",
        "recipes": list(RECIPES), "policies": list(ROLLOUT_POLICIES),
        "development_budgets": list(DEVELOPMENT_BUDGETS),
        "replicates": 4, "minimum_positions_per_split_per_ruleset": 8,
        "holdout_pooled_floor": 0.8, "holdout_cell_minimum_hits": 3,
        "holdout_monotonic_final_two_rungs": True,
        "required_integrity_failures": 0,
        "deep_optional_budget": 4096, "top_action_stability": 0.85,
        "top_three_jaccard_stability": 0.8,
        "selection": "one-global-recipe-equal-ruleset-weight-then-latency-then-id",
        "schedule": "frozen-registry-round-robin-collective-rungs",
        "backups": "accepted-terminal-only; exact-proofs-counted-separately",
        "post_holdout_tuning": False,
        "comparative_headline_minimum_games": 100,
    }
