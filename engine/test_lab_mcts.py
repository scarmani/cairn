"""Generic synthetic trees only; never run MCTS on an actual game state."""

from copy import deepcopy
from dataclasses import dataclass, replace
import unittest
from unittest.mock import patch

from research.harness.lab_mcts import MCTSIntegrityError, RECIPES, search
from research.harness.lab_terminal_cert import TerminalProvider, action_id, canonical_hash


def node(name, choices=(), *, seat="S1", color="B", seats=None, score=None, history=()):
    return {"name": name, "choices": [{"wire": wire, "target": target} for wire, target in choices],
            "actor": {"seat": seat, "color": color} if score is None else {"seat": None, "color": None},
            "seats": seats or {"B": "S1", "W": "S2"}, "accepted": score is not None,
            "score": score, "history": list(history), "marker": 1}


def provider(nodes, *, reverse=False):
    table = {row["name"]: deepcopy(row) for row in nodes}
    def actions(state):
        wires = [deepcopy(row["wire"]) for row in state["choices"]]
        return list(reversed(wires)) if reverse else wires
    def transition(state, wire):
        target = next(row["target"] for row in state["choices"] if row["wire"] == wire)
        return deepcopy(table[target])
    return TerminalProvider("synthetic-mcts", "synthetic", "0.1", "a" * 64, "b" * 64,
        canonical_hash, deepcopy, lambda _state: {"synthetic": True},
        lambda state: deepcopy(state["actor"]), lambda state: deepcopy(state["seats"]),
        lambda state: state["accepted"], lambda state: deepcopy(state["score"]), actions, transition)


@dataclass(frozen=True)
class Facts:
    action_kind: str
    extension_action: bool = False
    captured_original: int = 0
    captured_junction: int = 0
    defended_group_count: int = 0
    completed_cells: int = 0


@dataclass(frozen=True)
class Row:
    _action: dict
    facts: Facts
    _state: dict

    @property
    def action(self):
        return deepcopy(self._action)

    @property
    def action_id(self):
        return action_id(self._action)

    def successor(self):
        return deepcopy(self._state)


def expansion(source, fact_overrides=None):
    def expand(state):
        return tuple(Row(wire, (fact_overrides or {}).get(action_id(wire), Facts(wire["action"])),
                         source.transition(state, wire)) for wire in source.legal_actions(state))
    return expand


class TestLabMCTS(unittest.TestCase):
    def run_search(self, nodes, **options):
        p = provider(nodes)
        defaults = {"recipe": "lab-uct-0.1", "policy": "uniform", "simulations": 32,
                    "seed": 19, "rollout_limit": 16}
        defaults.update(options)
        return search(nodes[0], p, **defaults)

    def assert_counts(self, result):
        work = result.canonical_dict()["work"]
        self.assertEqual(work["requested_iterations"], work["completed_iterations"] + work["aborted_iterations"] + work["unused_iterations"])
        self.assertEqual(work["completed_iterations"], work["terminal_simulations"] + work["exact_proof_returns"])
        self.assertEqual(work["terminal_simulations"], work["terminal_backups"])
        self.assertEqual(work["backup_node_updates"], work["terminal_backup_node_updates"] + work["proof_backup_node_updates"])
        self.assertLessEqual(work["expansions"], work["iterations_started"])

    def test_three_recipes_two_policies_legal_deterministic_detached_and_counted(self):
        nodes = [node("root", (({"action": "sacrifice"}, "win"), ({"action": "defend"}, "draw"))),
                 node("win", score={"B": 2, "W": 1}), node("draw", score={"B": 7, "W": 7})]
        before = deepcopy(nodes)
        for recipe in RECIPES:
            for policy in ("uniform", "light"):
                with self.subTest(recipe=recipe, policy=policy):
                    a = self.run_search(nodes, recipe=recipe, policy=policy)
                    b = self.run_search(nodes, recipe=recipe, policy=policy)
                    self.assertEqual(a.canonical_dict(), b.canonical_dict())
                    self.assertEqual(a.canonical_hash, b.canonical_hash)
                    self.assertEqual(a.to_dict()["selected_action"], {"action": "sacrifice"})
                    self.assertEqual(a.to_dict()["status"], "complete")
                    self.assert_counts(a)
                    changed = a.to_dict()
                    changed["work"]["terminal_backups"] = -1
                    self.assertNotEqual(a.to_dict(), changed)
        self.assertEqual(nodes, before)

    def test_original_seat_survives_takeover_and_same_seat_turns(self):
        nodes = [node("root", (({"action": "continue"}, "same"), ({"action": "attack"}, "opponent"))),
                 node("same", (({"action": "swap"}, "win"), ({"action": "mistake"}, "loss"))),
                 node("opponent", (({"action": "cooperate"}, "win"), ({"action": "refute"}, "loss")), seat="S2", color="W"),
                 node("win", seats={"B": "S2", "W": "S1"}, score={"B": 0, "W": 3}),
                 node("loss", score={"B": 0, "W": 3})]
        for recipe in RECIPES:
            with self.subTest(recipe=recipe):
                result = self.run_search(nodes, recipe=recipe, simulations=128).to_dict()
                self.assertEqual(result["objective_seat"], "S1")
                self.assertEqual(result["selected_action"], {"action": "continue"})

    def test_equivalent_winning_margins_and_orientations(self):
        a = {"action": "plant", "face": [0, 0], "orientation": 0}
        b = dict(a, orientation=1)
        nodes = [node("root", ((a, "a"), (b, "b"))), node("a", score={"B": 2, "W": 1}), node("b", score={"B": 1000, "W": 0})]
        result = self.run_search(nodes, simulations=16).to_dict()
        self.assertEqual({row["action_id"] for row in result["root_actions"]}, {action_id(a), action_id(b)})
        self.assertEqual({row["root_mean"] for row in result["root_actions"]}, {1.0})
        self.assertEqual({row["visits"] for row in result["root_actions"]}, {8})
        self.assertIn(result["selected_action"], (a, b))

    def test_enumeration_order_and_requested_budget_preserve_common_prefixes(self):
        nodes = [node("root", tuple(({"action": f"choice-{i}"}, f"leaf-{i}") for i in range(5)))]
        nodes += [node(f"leaf-{i}", score={"B": i % 3, "W": 1}) for i in range(5)]
        options = dict(recipe="lab-uct-0.1", policy="uniform", seed=6, rollout_limit=5)
        a = search(nodes[0], provider(nodes), simulations=16, **options)
        b = search(nodes[0], provider(nodes, reverse=True), simulations=16, **options)
        c = search(nodes[0], provider(nodes), simulations=64, **options)
        self.assertEqual(a.canonical_dict(), b.canonical_dict())
        self.assertEqual(a.to_dict()["iteration_trace"], c.to_dict()["iteration_trace"][:16])
        self.assertNotEqual(a.to_dict()["agent_hash"], c.to_dict()["agent_hash"])

    def test_uniform_and_light_use_complete_domain_and_facts_only_as_preferences(self):
        nodes = [node("root", (({"action": "enter"}, "rollout"),)),
                 node("rollout", (({"action": "capture"}, "win"), ({"action": "pass"}, "loss")), seat="S2", color="W"),
                 node("win", score={"B": 2, "W": 0}), node("loss", score={"B": 0, "W": 2})]
        p = provider(nodes)
        facts = {action_id({"action": "capture"}): Facts("capture", captured_original=1)}
        outcomes = {policy: [] for policy in ("uniform", "light")}
        for seed in range(40):
            for policy in outcomes:
                result = search(nodes[0], p, recipe="lab-uct-0.1", policy=policy, simulations=1,
                                seed=seed, rollout_limit=4, expand=expansion(p, facts))
                outcomes[policy].append(result.to_dict()["iteration_trace"][0]["root_seat_wdl"])
        self.assertEqual(set(outcomes["uniform"]), {-1, 1})
        self.assertGreater(outcomes["light"].count(1), outcomes["uniform"].count(1))
        # Positive probability is an algorithm branch property, not something
        # that a finite seed sample must happen to exhibit. Force only the
        # exploration coin; keep actual uniform semantic action hashes intact.
        from research.harness.lab_mcts import _Search
        original = _Search.semantic
        def force_exploration(self, label, *args, **kwargs):
            return "0" * 64 if label == "light-explore" else original(self, label, *args, **kwargs)
        explored = []
        with patch.object(_Search, "semantic", force_exploration):
            for seed in range(40):
                result = search(nodes[0], p, recipe="lab-uct-0.1", policy="light", simulations=1,
                                seed=seed, rollout_limit=4, expand=expansion(p, facts))
                explored.append(result.to_dict()["iteration_trace"][0]["root_seat_wdl"])
        self.assertEqual(explored, outcomes["uniform"])

    def test_reserved_exposure_schedule_admin_overflow_and_eventual_expansion(self):
        choices = tuple(({"action": f"move-{i}"}, "draw") for i in range(40))
        nodes = [node("root", choices), node("draw", score={"B": 0, "W": 0})]
        for budget, exposed in ((4, 4), (16, 8), (64, 16), (400, 40)):
            with self.subTest(budget=budget):
                result = self.run_search(nodes, recipe="lab-reserved-0.1", simulations=budget).to_dict()
                self.assertEqual(result["exposure_threshold"], exposed)
                self.assertEqual(sum(row["exposed"] for row in result["root_actions"]), exposed)
        admin = tuple(({"action": kind}, "draw") for kind in ("swap", "pass", "resume", "accept", "finish-extension"))
        extra = [node("root", admin + choices), nodes[1]]
        result = self.run_search(extra, recipe="lab-reserved-0.1", simulations=1).to_dict()
        exposed = {row["action"]["action"] for row in result["root_actions"] if row["exposed"]}
        self.assertTrue({wire["action"] for wire, _ in admin} <= exposed)
        self.assertEqual(len(exposed), 5)

    def test_control_reserved_common_trace_when_all_actions_exposed_and_same_tier(self):
        nodes = [node("root", (({"action": "pass"}, "draw"), ({"action": "swap"}, "draw"))), node("draw", score={"B": 0, "W": 0})]
        a = self.run_search(nodes, recipe="lab-uct-0.1").to_dict()
        b = self.run_search(nodes, recipe="lab-reserved-0.1").to_dict()
        self.assertEqual(a["iteration_trace"], b["iteration_trace"])
        self.assertEqual(a["selected_action"], b["selected_action"])
        self.assertNotEqual(a["agent_hash"], b["agent_hash"])

    def test_rollout_terminal_never_proves_nonterminal_tree_leaf(self):
        nodes = [node("root", (({"action": "enter"}, "middle"),)),
                 node("middle", (({"action": "accept"}, "win"),)), node("win", score={"B": 1, "W": 0})]
        result = self.run_search(nodes, recipe="lab-terminal-proof-0.1", simulations=1).to_dict()
        self.assertEqual(result["root_bounds"], [-1, 1])
        self.assertEqual(result["root_actions"][0]["bounds"], [-1, 1])
        self.assertEqual(result["work"]["proof_propagations"], 0)
        self.assertEqual(result["work"]["terminal_simulations"], 1)
        self.assertEqual(result["work"]["rollout_actions"], 1)

    def test_extremal_root_proof_stops_but_retains_unknown_alternatives(self):
        nodes = [node("root", tuple(({"action": f"choice-{i}"}, "win") for i in range(20))), node("win", score={"B": 1, "W": 0})]
        result = self.run_search(nodes, recipe="lab-terminal-proof-0.1", simulations=64)
        data = result.to_dict()
        self.assertEqual(data["reason"], "root-proven")
        self.assertEqual(data["root_bounds"], [1, 1])
        self.assertEqual(data["work"]["completed_iterations"], 1)
        self.assertEqual(data["work"]["unused_iterations"], 63)
        self.assertEqual(len(data["proven_optimal_action_ids"]), 1)
        self.assertEqual(len(data["unresolved_action_ids"]), 19)
        self.assertFalse(data["complete_optimal_action_set"])
        self.assert_counts(result)

    def test_exact_returns_are_not_simulations_and_complete_equivalent_draw_sets(self):
        nodes = [node("root", tuple(({"action": f"choice-{i}"}, "draw") for i in range(12))), node("draw", score={"B": 4, "W": 4})]
        result = self.run_search(nodes, recipe="lab-terminal-proof-0.1", simulations=128)
        data = result.to_dict()
        self.assertEqual(data["root_bounds"], [0, 0])
        self.assertTrue(data["complete_optimal_action_set"])
        self.assertEqual(len(data["proven_optimal_action_ids"]), 12)
        self.assertGreater(data["work"]["exact_proof_returns"], 0)
        self.assertEqual(data["work"]["terminal_simulations"], 12)
        self.assert_counts(result)

    def test_accepted_root_no_invented_objective_action_or_iterations(self):
        result = self.run_search([node("terminal", score={"B": 10, "W": 0})])
        data = result.to_dict()
        self.assertEqual(data["status"], "already-terminal")
        self.assertIsNone(data["objective_seat"])
        self.assertIsNone(data["selected_action"])
        self.assertIsNone(data["root_bounds"])
        self.assertEqual(data["work"]["terminal_simulations"], 0)
        self.assertEqual(data["work"]["completed_iterations"], 0)
        self.assertEqual(data["work"]["terminal_score_evaluations"], 1)
        self.assert_counts(result)

    def test_watchdog_counts_tree_and_rollout_and_accepts_exact_boundary(self):
        nodes = [node("root", (({"action": "construct"}, "middle"),)),
                 node("middle", (({"action": "accept"}, "done"),)), node("done", score={"B": 1, "W": 0})]
        incomplete = self.run_search(nodes, rollout_limit=1).to_dict()
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertEqual(incomplete["reason"], "watchdog")
        self.assertEqual(incomplete["work"]["tree_actions"], 1)
        self.assertEqual(incomplete["work"]["rollout_actions"], 0)
        self.assertIsNone(incomplete["selected_action"])
        complete = self.run_search(nodes, rollout_limit=2)
        self.assertEqual(complete.to_dict()["status"], "complete")
        self.assertTrue(all(row["tree_actions"] + row["rollout_actions"] == 2 for row in complete.to_dict()["iteration_trace"]))
        self.assert_counts(complete)

    def test_cancel_deadline_preserve_partial_counts_without_action(self):
        nodes = [node("root", (({"action": "accept"}, "done"),)), node("done", score={"B": 0, "W": 0})]
        for options in ({"cancelled": lambda: True}, {"deadline": 0, "clock": lambda: 0}):
            result = self.run_search(nodes, **options)
            self.assertEqual(result.to_dict()["status"], "incomplete")
            self.assertIsNone(result.to_dict()["selected_action"])
            self.assert_counts(result)
        calls = 0
        def cancel_later():
            nonlocal calls
            calls += 1
            return calls > 20
        result = self.run_search(nodes, cancelled=cancel_later)
        self.assertEqual(result.to_dict()["status"], "incomplete")
        self.assertGreater(result.to_dict()["work"]["completed_iterations"], 0)
        self.assertIsNone(result.to_dict()["selected_action"])
        self.assert_counts(result)

    def test_invalid_configuration_precedes_callbacks(self):
        nodes = [node("root", (({"action": "accept"}, "done"),)), node("done", score={"B": 0, "W": 0})]
        p = replace(provider(nodes), snapshot=lambda _state: self.fail("configuration must fail first"))
        options = dict(recipe="lab-uct-0.1", policy="uniform", simulations=4, seed=1, rollout_limit=4)
        for field, value in (("simulations", True), ("simulations", 4097), ("simulations", 1.0), ("seed", True),
                             ("rollout_limit", 0), ("recipe", []), ("policy", {}), ("deadline", float("nan"))):
            with self.subTest(field=field), self.assertRaises(ValueError):
                search(nodes[0], p, **(options | {field: value}))

    def test_mutations_generator_exceptions_and_invalid_terminal_scores_fail(self):
        nodes = [node("root", (({"action": "accept"}, "done"),)), node("done", score={"B": 1, "W": 0})]
        p = provider(nodes)
        before = deepcopy(nodes[0])
        def bad_actor(state):
            state["marker"] = True
            return state["actor"]
        def bad_generator(state):
            yield state["choices"][0]["wire"]
            state["marker"] += 1
            raise RuntimeError("late invalid iterator")
        def bad_action(_state, wire):
            wire["orientation"] = 99
            raise RuntimeError("mutated input wire")
        for changed in (replace(p, actor=bad_actor), replace(p, legal_actions=bad_generator),
                        replace(p, transition=bad_action), replace(p, score=lambda _s: {"B": True, "W": 0}),
                        replace(p, accepted=lambda _s: 1)):
            with self.subTest(changed=changed), self.assertRaises(MCTSIntegrityError) as caught:
                search(nodes[0], changed, recipe="lab-uct-0.1", policy="uniform", simulations=4, seed=1, rollout_limit=4)
            self.assertIsNone(caught.exception.telemetry["selected_action"])
            self.assertEqual(nodes[0], before)

    def test_collisions_cycles_changed_seats_and_nonterminal_empty_domain_fail(self):
        cycle = [node("root", (({"action": "repeat"}, "root"),))]
        for nodes in (cycle, [node("root")], [node("root", (({"action": "x"}, "wrong"),)),
                    node("wrong", seats={"B": "replacement", "W": "S2"}, score={"B": 1, "W": 0})]):
            with self.subTest(nodes=nodes), self.assertRaises(MCTSIntegrityError):
                self.run_search(nodes)
        nodes = [node("root", (({"action": "x"}, "done"),)), node("done", score={"B": 1, "W": 0})]
        p = replace(provider(nodes), fingerprint=lambda _state: "c" * 64)
        with self.assertRaises(MCTSIntegrityError):
            search(nodes[0], p, recipe="lab-uct-0.1", policy="uniform", simulations=4, seed=1, rollout_limit=4)

    def test_expander_cannot_substitute_successors_or_hide_legal_actions(self):
        nodes = [node("root", (({"action": "one"}, "loss"), ({"action": "two"}, "loss"))),
                 node("loss", score={"B": 0, "W": 2}), node("forged", score={"B": 9, "W": 0})]
        p = provider(nodes)
        def forged(state):
            return tuple(Row(wire, Facts(wire["action"]), nodes[-1]) for wire in p.legal_actions(state))
        def partial(state):
            return expansion(p)(state)[:1]
        for expand in (forged, partial):
            with self.subTest(expand=expand), self.assertRaises(MCTSIntegrityError) as caught:
                search(nodes[0], p, recipe="lab-uct-0.1", policy="uniform", simulations=4, seed=1, rollout_limit=4, expand=expand)
            self.assertEqual(caught.exception.work["terminal_backups"], 0)

    def test_terminal_rollout_means_do_not_merge_distinct_tree_edges(self):
        nodes = [node("root", (({"action": "one"}, "same"), ({"action": "two"}, "same"))), node("same", score={"B": 0, "W": 0})]
        result = self.run_search(nodes, simulations=8).to_dict()
        self.assertEqual([row["visits"] for row in result["root_actions"]], [4, 4])
        self.assertEqual(result["work"]["tree_nodes"], 3)
        self.assertEqual(result["work"]["terminal_simulations"], 8)
        self.assertTrue(all(row["bounds"] == [-1, 1] for row in result["root_actions"]))

    def test_machine_timing_never_enters_canonical_result(self):
        nodes = [node("root", (({"action": "accept"}, "done"),)), node("done", score={"B": 1, "W": 0})]
        first = iter((0, 3))
        second = iter((0, 8))
        a = self.run_search(nodes, clock=lambda: next(first))
        b = self.run_search(nodes, clock=lambda: next(second))
        self.assertEqual(a.canonical_dict(), b.canonical_dict())
        self.assertNotEqual(a.timing, b.timing)
        self.assertNotIn("timing", a.canonical_dict())

    def test_last_terminal_callback_cannot_bypass_deadline_or_cancellation(self):
        nodes = [node("root", (({"action": "accept"}, "done"),)), node("done", score={"B": 1, "W": 0})]
        options = dict(recipe="lab-uct-0.1", policy="uniform", simulations=1, seed=1, rollout_limit=3)
        for mode in ("deadline", "cancel"):
            flag = [False]
            def late_score(state):
                flag[0] = True
                return deepcopy(state["score"])
            p = replace(provider(nodes), score=late_score)
            controls = {"deadline": 1, "clock": lambda: 2 if flag[0] else 0} if mode == "deadline" else {"cancelled": lambda: flag[0]}
            with self.subTest(mode=mode):
                result = search(nodes[0], p, **options, **controls)
                self.assertEqual(result.to_dict()["status"], "incomplete")
                self.assertIsNone(result.to_dict()["selected_action"])
                self.assertEqual(result.to_dict()["work"]["completed_iterations"], 1)
                self.assert_counts(result)

    def test_interruption_exit_still_checks_source_identity(self):
        nodes = [node("root", (({"action": "accept"}, "done"),)), node("done", score={"B": 1, "W": 0})]
        with patch("research.harness.lab_mcts._check_sources", side_effect=MCTSIntegrityError("synthetic source drift")):
            with self.assertRaises(MCTSIntegrityError) as caught:
                self.run_search(nodes, cancelled=lambda: True)
        self.assertEqual(caught.exception.telemetry["status"], "integrity-failure")
        self.assertIsNone(caught.exception.telemetry["selected_action"])

    def test_terminal_score_contradiction_is_not_hidden_by_identical_fingerprint(self):
        nodes = [node("root", (({"action": "one"}, "same"), ({"action": "two"}, "same"))), node("same", score={"B": 1, "W": 0})]
        calls = [0]
        def contradiction(_state):
            calls[0] += 1
            return {"B": calls[0], "W": 0}
        with self.assertRaisesRegex(MCTSIntegrityError, "contradictory accepted") as caught:
            search(nodes[0], replace(provider(nodes), score=contradiction), recipe="lab-uct-0.1",
                   policy="uniform", simulations=4, seed=1, rollout_limit=3)
        self.assertEqual(caught.exception.work["terminal_backups"], 1)
        self.assertIsNone(caught.exception.telemetry["selected_action"])

    def test_invalid_clock_after_cancellation_still_preserves_integrity_telemetry(self):
        nodes = [node("root", (({"action": "accept"}, "done"),)), node("done", score={"B": 1, "W": 0})]
        values = iter((0, float("nan")))
        with self.assertRaises(MCTSIntegrityError) as caught:
            self.run_search(nodes, cancelled=lambda: True, clock=lambda: next(values))
        self.assertEqual(caught.exception.telemetry["status"], "integrity-failure")
        self.assertEqual(caught.exception.work["completed_iterations"], 0)
        self.assertIsNone(caught.exception.telemetry["selected_action"])

    def test_final_clock_detects_deadline_crossed_during_exit_source_check(self):
        from research.harness import lab_mcts
        nodes = [node("root", (({"action": "accept"}, "done"),)), node("done", score={"B": 1, "W": 0})]
        source_checks = [0]
        original = lab_mcts._check_sources
        def checked_exit():
            original()
            source_checks[0] += 1
        with patch.object(lab_mcts, "_check_sources", checked_exit):
            result = self.run_search(nodes, simulations=1, deadline=1,
                                     clock=lambda: 2 if source_checks[0] >= 2 else 0)
        data = result.to_dict()
        self.assertEqual(data["status"], "incomplete")
        self.assertEqual(data["reason"], "deadline")
        self.assertIsNone(data["selected_action"])
        self.assertEqual(data["work"]["completed_iterations"], 1)
        self.assert_counts(result)


if __name__ == "__main__":
    unittest.main()
