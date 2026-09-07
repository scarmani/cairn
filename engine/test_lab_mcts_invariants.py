"""Independent MCTS checks over authored abstract graphs, never Varde games.

The fixtures implement only explicit state tables and legal transitions. They
perform no minimax/proof calculation and import no production rules/evaluator.
"""

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.harness import lab_mcts as mcts  # noqa: E402
from research.harness.lab_terminal_cert import TerminalProvider  # noqa: E402


RECIPES = ("lab-uct-0.1", "lab-reserved-0.1", "lab-terminal-proof-0.1")
POLICIES = ("uniform", "light")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def hashed(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def wire(kind, **values):
    return {"action": kind, **values}


def table_row(name, edges=(), *, color="B", swapped=False, score=None):
    return {"name": name, "edges": list(edges), "color": color, "score": score,
            "seats": {"B": "S2", "W": "S1"} if swapped else {"B": "S1", "W": "S2"}}


@dataclass(frozen=True)
class EventFacts:
    action_kind: str
    extension_action: bool = False
    captured_original: int = 0
    captured_junction: int = 0
    defended_group_count: int = 0
    completed_cells: int = 0


@dataclass(frozen=True)
class ExpansionRow:
    _wire: str
    facts: EventFacts
    _state: str

    @property
    def action(self):
        return json.loads(self._wire)

    @property
    def action_id(self):
        return self._wire

    def successor(self):
        return json.loads(self._state)


class AbstractGraph:
    def __init__(self, *rows, reverse=False):
        self.rows = {row["name"]: deepcopy(row) for row in rows}
        self.root = {"node": "root", "history": ["factory"], "private_marker": [7]}
        self.reverse = reverse
        self.score_calls = []
        self.transition_calls = []

    def actor(self, state):
        row = self.rows[state["node"]]
        if row["score"] is not None:
            return {"seat": None, "color": None}
        return {"seat": row["seats"][row["color"]], "color": row["color"]}

    def legal(self, state):
        actions = [deepcopy(action) for action, _ in self.rows[state["node"]]["edges"]]
        return list(reversed(actions)) if self.reverse else actions

    def transition(self, state, action):
        self.transition_calls.append((state["node"], encoded(action)))
        for expected, target in self.rows[state["node"]]["edges"]:
            if encoded(expected) == encoded(action):
                return {"node": target, "history": state["history"] + [encoded(action)],
                        "private_marker": deepcopy(state["private_marker"])}
        raise ValueError("outside the authored synthetic domain")

    def score(self, state):
        value = self.rows[state["node"]]["score"]
        if value is None:
            raise AssertionError("nonaccepted synthetic state was scored")
        self.score_calls.append(state["node"])
        return deepcopy(value)

    def provider(self, **overrides):
        fields = {
            "provider_id": "independent-mcts-abstract-table-0.1",
            "rules_id": "synthetic-not-a-varde-game", "rules_revision": "0.1",
            "rules_hash": hashed("fixed-table-legal-edges-only"),
            "implementation_hash": hashed(self.rows),
            "fingerprint": hashed, "snapshot": deepcopy,
            "metadata": lambda _state: {"origin": "synthetic-engineering", "full_action_replay": False},
            "actor": self.actor,
            "seats": lambda state: deepcopy(self.rows[state["node"]]["seats"]),
            "accepted": lambda state: self.rows[state["node"]]["score"] is not None,
            "score": self.score, "legal_actions": self.legal, "transition": self.transition,
        }
        fields.update(overrides)
        return TerminalProvider(**fields)

    def expand(self, state, facts=None):
        facts = facts or {}
        return tuple(ExpansionRow(encoded(action), facts.get(encoded(action), EventFacts(action["action"])),
                                  encoded(self.transition(state, action))) for action in self.legal(state))


def terminal_choices(*scores):
    actions = [wire("construct", face=[1, -1], orientation=i) for i in range(len(scores))]
    return AbstractGraph(table_row("root", [(action, f"end-{i}") for i, action in enumerate(actions)]),
                         *(table_row(f"end-{i}", score={"B": score[0], "W": score[1]})
                           for i, score in enumerate(scores)))


class TestLabMCTSIndependentInvariants(unittest.TestCase):
    def search(self, graph, **options):
        before = deepcopy(graph.root)
        defaults = {"recipe": RECIPES[0], "policy": "uniform", "simulations": 32,
                    "seed": 7, "rollout_limit": 100}
        provider = options.pop("provider", graph.provider())
        result = mcts.search(graph.root, provider, **(defaults | options))
        self.assertEqual(graph.root, before)
        data = result.canonical_dict()
        self.assertNotIn("timing", data)
        self.assertFalse(data["admission_record"])
        work = data["work"]
        self.assertEqual(work["requested_iterations"], work["completed_iterations"] +
                         work["aborted_iterations"] + work["unused_iterations"])
        self.assertEqual(work["iterations_started"], work["completed_iterations"] + work["aborted_iterations"])
        self.assertEqual(work["completed_iterations"], work["terminal_simulations"] + work["exact_proof_returns"])
        self.assertEqual(work["terminal_simulations"], work["terminal_backups"])
        self.assertEqual(work["backup_node_updates"], work["terminal_backup_node_updates"] + work["proof_backup_node_updates"])
        self.assertEqual(len(data["rollout_lengths"]), work["terminal_simulations"])
        self.assertLessEqual(work["expansions"], work["completed_iterations"] + work["aborted_iterations"])
        return result

    def test_all_arms_policies_are_deterministic_legal_detached_and_full_wire(self):
        for recipe in RECIPES:
            for policy in POLICIES:
                with self.subTest(recipe=recipe, policy=policy):
                    graph = terminal_choices((0, 3), (0, 3), (0, 3))
                    first = self.search(graph, recipe=recipe, policy=policy)
                    second = self.search(graph, recipe=recipe, policy=policy)
                    self.assertEqual(first.canonical_dict(), second.canonical_dict())
                    self.assertEqual(first.canonical_hash, second.canonical_hash)
                    data = first.to_dict()
                    self.assertEqual(data["status"], "complete")
                    self.assertIn(data["selected_action"], graph.legal(graph.root))
                    self.assertEqual(set(data["selected_action"]), {"action", "face", "orientation"})
                    self.assertEqual(len({row["action_id"] for row in data["root_actions"]}), 3)
                    data["root_actions"].clear()
                    self.assertEqual(len(first.to_dict()["root_actions"]), 3)

    def test_enumeration_order_never_changes_completed_semantic_results(self):
        graph = terminal_choices((0, 2), (0, 2), (0, 2))
        for recipe in RECIPES:
            for policy in POLICIES:
                with self.subTest(recipe=recipe, policy=policy):
                    graph.reverse = False
                    first = self.search(graph, recipe=recipe, policy=policy)
                    graph.reverse = True
                    second = self.search(graph, recipe=recipe, policy=policy)
                    self.assertEqual(first.canonical_dict(), second.canonical_dict())

    def test_takeover_tracks_original_seat_not_original_color(self):
        take = wire("swap")
        keep = wire("play", point=[2, 0])
        graph = AbstractGraph(table_row("root", [(take, "taken"), (keep, "kept")], color="W"),
                              table_row("taken", swapped=True, score={"B": 4, "W": 0}),
                              table_row("kept", score={"B": 4, "W": 0}))
        for recipe in RECIPES:
            for policy in POLICIES:
                with self.subTest(recipe=recipe, policy=policy):
                    result = self.search(graph, recipe=recipe, policy=policy, simulations=64).to_dict()
                    self.assertEqual(result["objective_seat"], "S2")
                    self.assertEqual(result["selected_action"], take)

    def test_same_seat_extension_and_opponent_reply_have_opposite_polarity(self):
        extend, leave = wire("extend", point=[4, 0]), wire("pass")
        bad, good = wire("finish-extension"), wire("play", point=[5, 1])
        for color, expected in (("B", extend), ("W", leave)):
            graph = AbstractGraph(table_row("root", [(extend, "reply"), (leave, "draw")]),
                                  table_row("reply", [(bad, "loss"), (good, "win")], color=color),
                                  table_row("draw", score={"B": 0, "W": 0}),
                                  table_row("loss", score={"B": 0, "W": 1}),
                                  table_row("win", score={"B": 1, "W": 0}))
            for recipe in RECIPES:
                with self.subTest(color=color, recipe=recipe):
                    result = self.search(graph, recipe=recipe, simulations=128).to_dict()
                    self.assertEqual(result["selected_action"], expected)

    def test_acceptance_is_not_terminal_and_resumption_keeps_seat_identity(self):
        accept, resume, play_on = wire("accept"), wire("resume"), wire("play", point=[2, 0])
        graph = AbstractGraph(table_row("root", [(accept, "other-seat"), (resume, "own-turn")]),
                              table_row("other-seat", [(resume, "other-turn")], color="W"),
                              table_row("other-turn", [(play_on, "loss")], color="W"),
                              table_row("own-turn", [(play_on, "win")]),
                              table_row("win", score={"B": 1, "W": 0}),
                              table_row("loss", score={"B": 0, "W": 1}))
        for recipe in RECIPES:
            result = self.search(graph, recipe=recipe, simulations=64).to_dict()
            self.assertEqual(result["selected_action"], resume)
        self.assertTrue(set(graph.score_calls) <= {"win", "loss"})

    def test_successful_rollout_never_proves_its_nonterminal_tree_leaf(self):
        action = wire("play", point=[2, 0])
        graph = AbstractGraph(table_row("root", [(action, "middle")]),
                              table_row("middle", [(wire("accept"), "terminal")], color="W"),
                              table_row("terminal", score={"B": 10, "W": 0}))
        result = self.search(graph, recipe=RECIPES[2], simulations=1).to_dict()
        self.assertEqual(result["work"]["terminal_simulations"], 1)
        self.assertEqual(result["work"]["exact_proof_returns"], 0)
        self.assertEqual(result["root_bounds"], [-1, 1])
        self.assertEqual(result["root_actions"][0]["bounds"], [-1, 1])
        self.assertFalse(result["complete_optimal_action_set"])
        self.assertEqual(result["proven_optimal_action_ids"], [])

    def test_root_exact_win_keeps_unknown_alternatives_and_unused_budget(self):
        graph = terminal_choices((1, 0), (1000, 0), (5, 0))
        result = self.search(graph, recipe=RECIPES[2], simulations=32).to_dict()
        self.assertEqual(result["root_bounds"], [1, 1])
        self.assertEqual(result["work"]["completed_iterations"], 1)
        self.assertEqual(result["work"]["unused_iterations"], 31)
        self.assertEqual(len(result["unresolved_action_ids"]), 2)
        self.assertFalse(result["complete_optimal_action_set"])
        chosen_id = encoded(result["selected_action"])
        self.assertIn(chosen_id, result["proven_optimal_action_ids"])
        for row in result["root_actions"]:
            if row["action_id"] != chosen_id:
                self.assertEqual(row["bounds"], [-1, 1])
                self.assertFalse(row["proven_optimal"])

    def test_equivalent_draws_complete_but_winning_margins_are_not_rewards(self):
        draws = self.search(terminal_choices((0, 0), (9, 9)), recipe=RECIPES[2]).to_dict()
        self.assertEqual(draws["root_bounds"], [0, 0])
        self.assertTrue(draws["complete_optimal_action_set"])
        self.assertEqual(len(draws["proven_optimal_action_ids"]), 2)
        for recipe in RECIPES[:2]:
            result = self.search(terminal_choices((1, 0), (1000, 0)), recipe=recipe).to_dict()
            self.assertTrue(all(row["root_mean"] == 1 for row in result["root_actions"]))
            self.assertEqual(result["root_bounds"], [-1, 1])
            self.assertTrue(all(row["bounds"] == [-1, 1] for row in result["root_actions"]))

    def test_structural_defense_preference_cannot_turn_sacrifice_into_inferiority(self):
        rescue, sacrifice = wire("play", point=[0, 0]), wire("play", point=[2, 0])
        graph = AbstractGraph(table_row("root", [(rescue, "loss"), (sacrifice, "win")]),
                              table_row("loss", score={"B": 0, "W": 1}),
                              table_row("win", score={"B": 1, "W": 0}))
        facts = {encoded(rescue): EventFacts("play", defended_group_count=1)}
        for recipe in RECIPES:
            result = self.search(graph, recipe=recipe, policy="light", simulations=64,
                                 expand=lambda state: graph.expand(state, facts)).to_dict()
            self.assertEqual(result["selected_action"], sacrifice)

    def test_already_accepted_root_has_no_invented_objective_or_iterations(self):
        graph = AbstractGraph(table_row("root", score={"B": 7, "W": 0}))
        for recipe in RECIPES:
            result = self.search(graph, recipe=recipe).to_dict()
            self.assertEqual(result["status"], "already-terminal")
            self.assertIsNone(result["selected_action"])
            self.assertIsNone(result["objective_seat"])
            self.assertEqual(result["work"]["completed_iterations"], 0)
            self.assertEqual(result["work"]["terminal_simulations"], 0)
            self.assertEqual(result["work"]["unused_iterations"], 32)

    def test_total_action_watchdog_never_fabricates_a_terminal_backup(self):
        graph = AbstractGraph(table_row("root", [(wire("pass"), "middle")]),
                              table_row("middle", [(wire("accept"), "end")]),
                              table_row("end", score={"B": 0, "W": 0}))
        failed = self.search(graph, rollout_limit=1, simulations=4).to_dict()
        self.assertEqual(failed["status"], "incomplete")
        self.assertIsNone(failed["selected_action"])
        self.assertEqual(failed["work"]["completed_iterations"], 0)
        self.assertEqual(failed["work"]["aborted_iterations"], 1)
        self.assertEqual(failed["work"]["terminal_backups"], 0)
        boundary = self.search(graph, rollout_limit=2, simulations=1).to_dict()
        self.assertEqual(boundary["status"], "complete")
        self.assertEqual(boundary["work"]["terminal_simulations"], 1)
        self.assertEqual(boundary["work"]["tree_actions"] + boundary["work"]["rollout_actions"], 2)

    def test_entry_cancellation_and_expired_deadline_have_no_selected_action(self):
        graph = terminal_choices((0, 0), (0, 0))
        for options in ({"cancelled": lambda: True}, {"clock": lambda: 10.0, "deadline": 9.0}):
            with self.subTest(options=options):
                result = self.search(graph, **options).to_dict()
                self.assertEqual(result["status"], "incomplete")
                self.assertIsNone(result["selected_action"])
                self.assertEqual(result["work"]["completed_iterations"], 0)
                self.assertEqual(result["work"]["terminal_backups"], 0)

    def test_malformed_configuration_precedes_every_provider_callback(self):
        graph = terminal_choices((0, 0))
        def forbidden(_state):
            raise AssertionError("provider called before malformed configuration rejection")
        provider = graph.provider(fingerprint=forbidden)
        cases = [("simulations", value) for value in (True, 0, -1, 1.0, 4097)]
        cases += [("seed", value) for value in (True, 1.0, "7")]
        cases += [("rollout_limit", value) for value in (True, 0, 2.0)]
        cases += [("recipe", "unknown"), ("policy", "unknown"), ("deadline", float("nan")),
                  ("deadline", float("inf")), ("deadline", True)]
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.search(graph, provider=provider, **{field: value})

    def test_supplied_expander_cannot_forge_a_terminal_successor(self):
        action = wire("play", point=[2, 0])
        graph = AbstractGraph(table_row("root", [(action, "loss")]),
                              table_row("loss", score={"B": 0, "W": 1}),
                              table_row("fabricated-win", score={"B": 1, "W": 0}))
        def forged(state):
            successor = graph.transition(state, action)
            successor["node"] = "fabricated-win"
            return (ExpansionRow(encoded(action), EventFacts("play"), encoded(successor)),)
        with self.assertRaises(mcts.MCTSIntegrityError) as caught:
            self.search(graph, recipe=RECIPES[2], expand=forged)
        self.assertIsNone(caught.exception.partial_result.to_dict()["selected_action"])
        self.assertFalse(caught.exception.partial_result.to_dict()["admission_record"])

    def test_mutating_legal_iterators_and_transition_exceptions_preserve_caller(self):
        graph = terminal_choices((0, 0), (0, 0))
        before = deepcopy(graph.root)
        def mutating_legal(state):
            yield graph.legal(state)[0]
            state["private_marker"].append(99)
            raise RuntimeError("synthetic generator failure after mutation")
        def mutating_transition(state, action):
            state["private_marker"].append(99)
            raise RuntimeError("synthetic transition failure after mutation")
        for override in ({"legal_actions": mutating_legal}, {"transition": mutating_transition}):
            with self.subTest(override=override), self.assertRaises(mcts.MCTSIntegrityError) as caught:
                self.search(graph, provider=graph.provider(**override))
            self.assertEqual(graph.root, before)
            self.assertIsNone(caught.exception.partial_result.to_dict()["selected_action"])

    def test_reserved_exposure_overflows_only_for_mandatory_actions_and_eventually_opens_all(self):
        admin = [wire(kind) for kind in ("swap", "pass", "resume", "accept", "finish-extension")]
        moves = [wire("play", point=[2 * i, 0]) for i in range(40)]
        def make(actions):
            return AbstractGraph(table_row("root", [(action, f"node-{i}") for i, action in enumerate(actions)]),
                                 *(table_row(f"node-{i}", score={"B": 0, "W": 1})
                                   for i in range(len(actions))))
        for recipe in RECIPES[1:]:
            overflow = self.search(make(admin + moves), recipe=recipe, simulations=1).to_dict()
            exposed = {row["action_id"] for row in overflow["root_actions"] if row["exposed"]}
            self.assertTrue({encoded(action) for action in admin} <= exposed)
            self.assertGreaterEqual(len(exposed), 5)
            wide = self.search(make(moves), recipe=recipe, simulations=64).to_dict()
            self.assertEqual(wide["exposure_threshold"], 16)
            self.assertEqual(sum(row["exposed"] for row in wide["root_actions"]), 16)
            self.assertEqual(sum(row["visits"] for row in wide["root_actions"]), 64)
            self.assertTrue(all(row["bounds"] == [-1, 1] for row in wide["root_actions"] if not row["expanded"]))
        final = self.search(make(moves[:9]), recipe=RECIPES[1], simulations=64).to_dict()
        self.assertTrue(all(row["exposed"] and row["expanded"] for row in final["root_actions"]))

    def test_common_seed_prefix_ignores_budget_and_zero_fact_recipe_differences(self):
        graph = terminal_choices((0, 1), (0, 1), (0, 1))
        small = self.search(graph, simulations=8).to_dict()
        large = self.search(graph, simulations=32).to_dict()
        reserved = self.search(graph, simulations=32, recipe=RECIPES[1]).to_dict()
        self.assertEqual(small["iteration_trace"], large["iteration_trace"][:8])
        self.assertEqual(large["iteration_trace"], reserved["iteration_trace"])
        self.assertNotEqual(small["agent_hash"], large["agent_hash"])
        self.assertNotEqual(large["agent_hash"], reserved["agent_hash"])
        choices = {encoded(self.search(graph, seed=seed, simulations=1).to_dict()["selected_action"])
                   for seed in range(12)}
        self.assertGreater(len(choices), 1)

    def test_exact_returns_are_not_counted_as_new_terminal_simulations(self):
        safe, uncertain = wire("pass"), wire("play", point=[2, 0])
        rows = [table_row("root", [(safe, "draw"), (uncertain, "chain-0")]),
                table_row("draw", score={"B": 0, "W": 0})]
        for i in range(40):
            rows.append(table_row(f"chain-{i}", [(wire("play", point=[2 * i, 0]),
                                                  f"chain-{i + 1}" if i < 39 else "loss")],
                                  color="W" if i % 2 == 0 else "B"))
        rows.append(table_row("loss", score={"B": 0, "W": 1}))
        result = self.search(AbstractGraph(*rows), recipe=RECIPES[2], simulations=32).to_dict()
        self.assertGreater(result["work"]["exact_proof_returns"], 0)
        self.assertGreater(result["work"]["terminal_simulations"], 0)
        self.assertLess(result["work"]["terminal_simulations"], result["work"]["completed_iterations"])
        self.assertGreater(result["work"]["proof_backup_node_updates"], 0)
        self.assertEqual(result["root_bounds"], [0, 1])

    def test_full_history_changes_domain_and_is_never_replaced_by_diagram_identity(self):
        graph = terminal_choices((1, 0), (0, 1))
        original_legal = graph.legal
        def historical_domain(state):
            actions = original_legal(state)
            return actions[1:] if state["node"] == "root" and "forbidden-first" in state["history"] else actions
        provider = graph.provider(legal_actions=historical_domain)
        first = self.search(graph, provider=provider, simulations=16).to_dict()
        graph.root["history"].append("forbidden-first")
        second = self.search(graph, provider=provider, simulations=16).to_dict()
        self.assertNotEqual(first["root_fingerprint"], second["root_fingerprint"])
        self.assertEqual(first["selected_action"]["orientation"], 0)
        self.assertEqual(second["selected_action"]["orientation"], 1)
        self.assertEqual(len(second["root_actions"]), 1)

    def test_collision_and_active_cycle_never_become_a_draw_or_proof(self):
        first, second = wire("play", point=[0, 0]), wire("play", point=[2, 0])
        graph = AbstractGraph(table_row("root", [(first, "shared"), (second, "shared")]),
                              table_row("shared", score={"B": 0, "W": 0}))
        node_only = graph.provider(fingerprint=lambda state: hashed(state["node"]))
        with self.assertRaises(mcts.MCTSIntegrityError):
            self.search(graph, provider=node_only, simulations=4)
        cyclic = AbstractGraph(table_row("root", [(first, "root")]))
        provider = cyclic.provider(transition=lambda state, _action: deepcopy(state))
        with self.assertRaises(mcts.MCTSIntegrityError) as caught:
            self.search(cyclic, provider=provider, simulations=4)
        self.assertEqual(caught.exception.work["terminal_backups"], 0)
        self.assertIsNone(caught.exception.partial_result.to_dict()["selected_action"])

    def test_seat_conservation_terminal_score_types_and_duplicate_actions_fail_closed(self):
        graph = terminal_choices((0, 0))
        graph.rows["end-0"]["seats"] = {"B": "S1", "W": "S3"}
        with self.assertRaises(mcts.MCTSIntegrityError):
            self.search(graph, recipe=RECIPES[2])
        for bad in (True, 1.0, float("nan"), float("inf")):
            graph = terminal_choices((0, 0))
            provider = graph.provider(score=lambda _state, bad=bad: {"B": bad, "W": 0})
            with self.subTest(bad=bad), self.assertRaises(mcts.MCTSIntegrityError):
                self.search(graph, provider=provider, recipe=RECIPES[2])
        graph = terminal_choices((0, 0))
        graph.rows["root"]["edges"] *= 2
        with self.assertRaises(mcts.MCTSIntegrityError):
            self.search(graph)

    def test_expansion_domains_facts_and_action_ids_cannot_silently_disagree(self):
        graph = terminal_choices((0, 0), (0, 0))
        def omitted(state):
            return graph.expand(state)[:1]
        def duplicate(state):
            rows = graph.expand(state)
            return rows[:1] * 2
        def bad_facts(state):
            rows = list(graph.expand(state))
            rows[0] = replace(rows[0], facts=EventFacts("construct", captured_original=True))
            return tuple(rows)
        def mismatched_kind(state):
            rows = list(graph.expand(state))
            rows[0] = replace(rows[0], facts=EventFacts("pass"))
            return tuple(rows)
        for expand in (omitted, duplicate, bad_facts, mismatched_kind):
            with self.subTest(expand=expand), self.assertRaises(mcts.MCTSIntegrityError) as caught:
                self.search(graph, expand=expand)
            self.assertIsNone(caught.exception.partial_result.to_dict()["selected_action"])

    def test_cancellation_after_work_retains_counts_without_emitting_a_choice(self):
        graph = terminal_choices((0, 0), (0, 0))
        result = self.search(graph, simulations=32, cancelled=lambda: len(graph.score_calls) >= 2).to_dict()
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["selected_action"])
        self.assertGreater(result["work"]["completed_iterations"], 0)
        self.assertLess(result["work"]["completed_iterations"], 32)

    def test_last_terminal_callback_cannot_cross_stop_boundary_and_emit_a_choice(self):
        for reason in ("cancelled", "deadline"):
            with self.subTest(reason=reason):
                graph = terminal_choices((0, 0))
                timer = [0.0]
                stop = [False]
                def score(state):
                    timer[0] = 2.0
                    stop[0] = True
                    return graph.score(state)
                controls = ({"cancelled": lambda: stop[0]} if reason == "cancelled" else
                            {"deadline": 1.0, "clock": lambda: timer[0]})
                result = self.search(graph, provider=graph.provider(score=score),
                                     simulations=1, **controls).to_dict()
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["reason"], reason)
                self.assertIsNone(result["selected_action"])
                self.assertEqual(result["work"]["terminal_score_evaluations"], 1)

    def test_repeated_full_states_cannot_change_observed_domains_facts_or_successors(self):
        a, b = wire("play", point=[0, 0]), wire("play", point=[2, 0])
        finish, alternate = wire("accept"), wire("pass")
        for contradiction in ("domain", "facts", "successor"):
            with self.subTest(contradiction=contradiction):
                graph = AbstractGraph(table_row("root", [(a, "shared"), (b, "shared")]),
                                      table_row("shared", [(finish, "draw"), (alternate, "draw")]),
                                      table_row("draw", score={"B": 0, "W": 0}),
                                      table_row("win", score={"B": 1, "W": 0}))
                observed = {"domain": 0, "facts": 0, "successor": 0}
                def legal(state):
                    if state["node"] != "shared":
                        return graph.legal(state)
                    observed["domain"] += 1
                    return [alternate if contradiction == "domain" and observed["domain"] > 1 else finish]
                def transition(state, action):
                    if state["node"] == "root":
                        return {"node": "shared", "history": ["canonical-shared"], "private_marker": [7]}
                    observed["successor"] += 1
                    target = "win" if contradiction == "successor" and observed["successor"] > 1 else "draw"
                    return {"node": target, "history": ["canonical-terminal"], "private_marker": [7]}
                def expand(state):
                    actions = graph.legal(state) if state["node"] != "shared" else [finish]
                    if state["node"] == "shared":
                        observed["facts"] += 1
                    count = observed["facts"] if state["node"] == "shared" else 0
                    return tuple(ExpansionRow(encoded(action),
                        EventFacts(action["action"], defended_group_count=count),
                        encoded(transition(state, action))) for action in actions)
                provider = graph.provider(legal_actions=legal, transition=transition)
                options = {"expand": expand} if contradiction == "facts" else {}
                with self.assertRaises(mcts.MCTSIntegrityError) as caught:
                    self.search(graph, provider=provider, simulations=2, **options)
                self.assertIsNone(caught.exception.partial_result.to_dict()["selected_action"])

    def test_repeated_accepted_full_state_cannot_change_score_pair(self):
        graph = terminal_choices((0, 0), (0, 0))
        calls = []
        def transition(_state, _action):
            return {"node": "end-0", "history": ["canonical-terminal"], "private_marker": [7]}
        def score(_state):
            calls.append(1)
            return {"B": len(calls), "W": 0}
        with self.assertRaises(mcts.MCTSIntegrityError) as caught:
            self.search(graph, provider=graph.provider(transition=transition, score=score), simulations=2)
        self.assertIsNone(caught.exception.partial_result.to_dict()["selected_action"])

    def test_cancellation_after_generator_yield_preserves_observed_action_count(self):
        graph = terminal_choices((0, 0))
        stop, yielded = [False], []
        def legal(state):
            for action in graph.legal(state):
                yielded.append(action)
                stop[0] = True
                yield action
        result = self.search(graph, provider=graph.provider(legal_actions=legal),
                             cancelled=lambda: stop[0], simulations=1).to_dict()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reason"], "cancelled")
        self.assertEqual(len(yielded), 1)
        self.assertEqual(result["work"]["actions_enumerated"], len(yielded))
        self.assertEqual(result["work"]["terminal_backups"], 0)


if __name__ == "__main__":
    unittest.main()
