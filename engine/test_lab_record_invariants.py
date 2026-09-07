"""Independent local-record checks; mechanical replay is not human-study evidence."""

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from actions import RulesAction, RulesState, apply_action
from lab_game import LabGame
from lab_spec import LAB_SPECS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.harness.lab_record import replay_lab_record, validate_lab_record_shape
from research.harness.human_study import validate_playtest_record


ROOT = Path(__file__).resolve().parents[1]
SESSION = "11111111-1111-4111-8111-111111111111"
PRIVATE_IDS = {"S1": "private-server-seat-alice", "S2": "private-server-seat-bob"}


def action(kind, point=None, orientation=None):
    return RulesAction(kind, point, orientation=orientation).to_dict()


def after_fields(state):
    game = state.game
    return {
        "to_move": game.to_move, "actor_color": state.actor_color, "actor_seat": state.actor_seat,
        "seats": dict(state.seats), "end_acceptances": sorted(state.end_acceptances),
        "finished": game.finished, "accepted": state.accepted, "resumption_used": game.resumption_used,
        "consecutive_passes": game.consecutive_passes, "swap_available": game.swap_available,
        "moves_played": game.moves_played, "placements_played": game.placements_played,
        "constructions_played": game.constructions_played,
        "topology": [list(row) for row in game.topology],
        "score": game.score(), "original_control": game.original_control_count(),
    }


def public_view(state):
    """Independent projection with deliberately private server seat/name values."""
    game, after = state.game, after_fields(state)
    original = set(getattr(game.board, "original_points", game.board.points))
    centers = set(getattr(game.board, "active_centers", ()))
    return {
        **{key: value for key, value in after.items() if key not in ("seats", "end_acceptances")},
        "n": game.board.n, "rules": game.rules, "rules_revision": "0.1", "experimental": True, "flat": True,
        "actor_seat": PRIVATE_IDS[state.actor_seat] if state.actor_seat else None,
        "points": [{"coord": list(p), "stack": list(game.state[p]), "original": p in original,
                    "scoring": p in original and game.rules != "gjerde-majority", "center": p in centers}
                   for p in game.board.points],
        "capture_waves": [[list(p) for p in wave] for wave in game.last_capture_waves],
        "match": {"mode": "hotseat", "seats": {
            color: {"identity": PRIVATE_IDS[identity], "kind": "human", "name": f"Private name {identity}"}
            for color, identity in state.seats.items()},
            "end_acceptances": sorted(PRIVATE_IDS[identity] for identity in state.end_acceptances)},
    }


def make_record(rules="junction-y", n=3, actions=()):
    """Construct records directly from shared actions, without record-module helpers."""
    state = RulesState(LabGame(n, rules=rules), seats={"B": "S1", "W": "S2"})
    record = {
        "format": "varde-lab-playtest", "version": 2, "source": "browser-local-hotseat",
        "session_id": SESSION, "rules": {"id": rules, "revision": "0.1"}, "board_size": n,
        "catalog_version": 1, "initial_seats": {"B": "S1", "W": "S2"},
        "status": "active", "actions": [], "final_score": None,
    }
    chain = []
    for wire in actions:
        before = public_view(state)
        actor = {"seat": state.actor_seat, "color": state.actor_color}
        state = apply_action(state, RulesAction.from_dict(wire))
        waves = ([[list(p) for p in sorted(wave)] for wave in state.game.last_capture_waves]
                 if wire["action"] in ("play", "plant") else [])
        original = set(getattr(state.game.board, "original_points", state.game.board.points))
        removed = [tuple(p) for wave in waves for p in wave]
        record["actions"].append({
            "index": len(record["actions"]), "action": deepcopy(wire), "actor": actor, "elapsed_ms": 17,
            "captures": {"original": sum(p in original for p in removed),
                         "junction": sum(p not in original for p in removed), "waves": waves},
            "after": after_fields(state),
        })
        chain.append({"action": deepcopy(wire), "before": before, "after": public_view(state), "elapsedMs": 17})
    if state.accepted:
        record.update(status="complete", final_score=state.game.score())
    return record, state, chain


def js_call(operation, payload):
    script = r"""
const fs = require('node:fs');
const api = require(process.argv[1]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
try {
  if (input.operation === 'validate') {
    process.stdout.write(JSON.stringify({ok: true, value: api.validateLabRecordShape(input.payload)}));
  } else if (input.operation === 'create') {
    process.stdout.write(JSON.stringify({ok: true, value: api.createLabRecord(input.payload.view, input.payload.options)}));
  } else if (input.operation === 'append') {
    const before = JSON.stringify(input.payload);
    const value = api.appendLabAction(input.payload.record, input.payload.event);
    process.stdout.write(JSON.stringify({ok: true, value, inputUnchanged: before === JSON.stringify(input.payload)}));
  } else if (input.operation === 'chain') {
    const before = JSON.stringify(input.payload);
    let value = api.createLabRecord(input.payload.view, input.payload.options);
    for (const event of input.payload.events) value = api.appendLabAction(value, event);
    process.stdout.write(JSON.stringify({ok: true, value, inputUnchanged: before === JSON.stringify(input.payload)}));
  } else throw new Error('test operation is unknown');
} catch (error) {
  process.stdout.write(JSON.stringify({ok: false, error: String(error.message)}));
}
"""
    result = subprocess.run(
        [shutil.which("node") or "node", "-e", script, str(ROOT / "web" / "lab-record.js")],
        input=json.dumps({"operation": operation, "payload": payload}), capture_output=True, text=True,
        cwd=ROOT, check=False, timeout=10,
    )
    if result.returncode:
        raise AssertionError(f"JavaScript helper process failed: {result.stderr}")
    return json.loads(result.stdout)


class TestLabRecordInvariants(unittest.TestCase):
    def assert_valid_both(self, record):
        before = deepcopy(record)
        checked = validate_lab_record_shape(record)
        self.assertEqual(checked, record)
        self.assertIsNot(checked, record)
        self.assertEqual(record, before)
        self.assertTrue(js_call("validate", record)["ok"])

    def test_seven_rules_all_sizes_replay_without_a_research_or_human_claim(self):
        for spec in LAB_SPECS:
            for n in (3, 4, 5, 6):
                with self.subTest(rules=spec.id, n=n):
                    initial = LabGame(n, rules=spec.id)
                    original = getattr(initial.board, "original_points", initial.board.points)
                    moves = [action("play", original[0]), action("swap")]
                    if "construct" in spec.supported_actions or "plant" in spec.supported_actions:
                        kind = "plant" if "plant" in spec.supported_actions else "construct"
                        moves.append(action(kind, (1, 0), len(spec.orientation_sets) - 1))
                    record, state, _ = make_record(spec.id, n, moves)
                    before = deepcopy(record)
                    self.assertEqual(validate_lab_record_shape(record), record)
                    report = replay_lab_record(record)
                    self.assertTrue(report.mechanically_verified)
                    self.assertEqual(report.action_count, len(moves))
                    self.assertEqual(report.accepted, state.accepted)
                    self.assertRegex(report.replay_hash, r"^[0-9a-f]{64}$")
                    self.assertEqual(report.to_dict(), replay_lab_record(record).to_dict())
                    self.assertNotIn("actions", report.to_dict())
                    self.assertNotIn("human_study_qualified", report.to_dict())
                    self.assertEqual(record, before)

    def test_browser_helpers_anonymize_pie_and_both_ending_phases(self):
        moves = [action("play", (2, 0)), action("swap"), action("pass"), action("pass"),
                 action("accept"), action("resume"), action("pass"), action("pass"), action("accept")]
        record, state, chain = make_record(actions=moves)
        response = js_call("chain", {"view": chain[0]["before"],
                                    "options": {"sessionId": SESSION, "catalogVersion": 1}, "events": chain})
        self.assertTrue(response["ok"], response)
        self.assertTrue(response["inputUnchanged"])
        self.assertEqual(response["value"], record)
        encoded = json.dumps(response["value"])
        self.assertNotIn("private-", encoded)
        self.assertNotIn("Private name", encoded)
        self.assertEqual(record["actions"][1]["actor"], {"seat": "S2", "color": "W"})
        self.assertEqual(record["actions"][1]["after"]["seats"], {"B": "S2", "W": "S1"})
        self.assertNotEqual(record["actions"][4]["after"]["actor_color"], record["actions"][4]["after"]["to_move"])
        self.assertFalse(record["actions"][4]["after"]["accepted"])
        self.assertEqual(record["actions"][5]["after"]["end_acceptances"], [])
        self.assertTrue(state.accepted)
        self.assertIsNone(record["actions"][-1]["after"]["actor_color"])
        self.assertIsNone(record["actions"][-1]["after"]["actor_seat"])
        self.assert_valid_both(record)
        self.assertTrue(replay_lab_record(record).accepted)

    def test_two_first_ending_acceptances_do_not_pretend_first_acceptance_was_terminal(self):
        record, _, _ = make_record(actions=[action("play", (2, 0)), action("pass"), action("pass"), action("accept")])
        self.assertEqual(record["status"], "active")
        self.assertIsNone(record["final_score"])
        self.assertFalse(replay_lab_record(record).accepted)
        completed, _, _ = make_record(actions=[action("play", (2, 0)), action("pass"), action("pass"),
                                             action("accept"), action("accept")])
        self.assertEqual(completed["status"], "complete")
        self.assertTrue(replay_lab_record(completed).accepted)
        self.assert_valid_both(completed)

    def test_capture_role_and_administrative_rows_are_not_stale(self):
        fixtures = {
            "junction-y": [action("play", (2, 0)), action("construct", (0, 0), 0),
                           action("play", (-1, 1)), action("play", (0, 0)), action("play", (-1, -1))],
            "gjerde-majority": [action("play", (0, 2)), action("play", (3, 1)),
                                action("play", (3, -1)), action("play", (-15, -5)),
                                action("play", (3, 3)), action("play", (-15, -3)), action("play", (6, 0))],
        }
        for rules, moves in fixtures.items():
            with self.subTest(rules=rules):
                record, _, chain = make_record(rules, actions=moves + [action("pass")])
                capture = record["actions"][-2]["captures"]
                self.assertEqual((capture["original"], capture["junction"]), (0, 1) if rules == "junction-y" else (1, 0))
                self.assertEqual(record["actions"][-1]["captures"], {"original": 0, "junction": 0, "waves": []})
                # Even an old/stale public-view wave must not leak into a pass row.
                chain[-1]["after"]["capture_waves"] = deepcopy(capture["waves"])
                response = js_call("chain", {"view": chain[0]["before"],
                                            "options": {"sessionId": SESSION, "catalogVersion": 1}, "events": chain})
                self.assertTrue(response["ok"], response)
                self.assertEqual(response["value"], record)
                self.assertTrue(replay_lab_record(record).mechanically_verified)

    def test_strict_python_and_javascript_reject_identical_malformed_fields(self):
        good, _, _ = make_record(actions=[action("play", (2, 0)), action("construct", (1, 0), 0)])
        mutations = (
            lambda r: r.update(name="Private person"), lambda r: r.update(version=True),
            lambda r: r.update(session_id="not-a-uuid"), lambda r: r.update(board_size=True),
            lambda r: r.update(catalog_version=-1), lambda r: r.update(source="agent-research"),
            lambda r: r["rules"].update(revision="0.2"), lambda r: r["rules"].update(id="go-static-y"),
            lambda r: r["initial_seats"].update(B="private-server-seat"),
            lambda r: r["actions"][0].update(index=1), lambda r: r["actions"][0].update(elapsed_ms=True),
            lambda r: r["actions"][0].update(elapsed_ms=2 ** 53),
            lambda r: r["actions"][0]["action"].update(point=[True, 0]),
            lambda r: r["actions"][1]["action"].update(orientation=True),
            lambda r: r["actions"][1]["action"].update(orientation=2),
            lambda r: r["actions"][0]["actor"].update(seat="S3"),
            lambda r: r["actions"][0]["captures"].update(original=-1),
            lambda r: r["actions"][0]["after"].update(accepted=1),
            lambda r: r["actions"][0]["after"].update(actor_seat=None),
            lambda r: r["actions"][0]["after"]["seats"].update(B="S2"),
            lambda r: r["actions"][0]["after"].update(end_acceptances=["S1", "S1"]),
            lambda r: r["actions"][0]["after"].update(moves_played=1.5),
            lambda r: r["actions"][1]["after"].update(topology=[[1, 0, False]]),
            lambda r: r["actions"][0]["after"]["score"].update(notes="free text"),
            lambda r: r.update(final_score={"B": 54, "W": 0}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                bad = deepcopy(good)
                mutate(bad)
                before = deepcopy(bad)
                with self.assertRaises(ValueError):
                    validate_lab_record_shape(bad)
                self.assertFalse(js_call("validate", bad)["ok"])
                self.assertEqual(bad, before)

    def test_structurally_valid_telemetry_tampering_never_passes_mechanical_replay(self):
        good, _, _ = make_record(actions=[action("play", (2, 0)), action("construct", (1, 0), 0)])
        mutations = (
            lambda r: r["actions"][0]["after"]["score"].update(B=53),
            lambda r: r["actions"][0]["after"]["original_control"].update(B=2),
            lambda r: r["actions"][1]["action"].update(orientation=1),
        )
        for mutate in mutations:
            bad = deepcopy(good)
            mutate(bad)
            self.assertEqual(validate_lab_record_shape(bad), bad)
            self.assertTrue(js_call("validate", bad)["ok"])
            with self.assertRaises(ValueError):
                replay_lab_record(bad)

    def test_malformed_nested_identity_types_report_validation_errors_not_type_crashes(self):
        good, _, _ = make_record(actions=[action("play", (2, 0))])
        mutations = (
            lambda r: r["initial_seats"].update(B=[]),
            lambda r: r["actions"][0]["after"].update(to_move=[]),
            lambda r: r["actions"][0]["after"].update(actor_color={}),
            lambda r: r["actions"][0]["after"]["seats"].update(W=[]),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                bad = deepcopy(good)
                mutate(bad)
                with self.assertRaises(ValueError):
                    validate_lab_record_shape(bad)

    def test_integral_json_number_forms_normalize_identically_without_mutating_input(self):
        good, _, _ = make_record(actions=[action("play", (2, 0)), action("construct", (1, 0), 1)])

        def float_numbers(value):
            if type(value) is int:
                return float(value)
            if isinstance(value, list):
                return [float_numbers(item) for item in value]
            if isinstance(value, dict):
                return {key: float_numbers(item) for key, item in value.items()}
            return value

        alternate = float_numbers(good)
        before = deepcopy(alternate)
        normalized = validate_lab_record_shape(alternate)
        self.assertEqual(normalized, good)
        self.assertIs(type(normalized["version"]), int)
        self.assertIs(type(normalized["actions"][1]["action"]["orientation"]), int)
        self.assertIs(type(normalized["actions"][0]["after"]["score"]["B"]), int)
        self.assertIs(type(normalized["actions"][0]["after"]["accepted"]), bool)
        self.assertEqual(js_call("validate", alternate)["value"], normalized)
        self.assertEqual(replay_lab_record(alternate).replay_hash, replay_lab_record(good).replay_hash)
        self.assertEqual(alternate, before)
        self.assertIs(type(alternate["actions"][1]["action"]["orientation"]), float)
        for value in (float("nan"), float("inf"), 3.25, float(2 ** 53)):
            bad = deepcopy(good)
            bad["board_size"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_lab_record_shape(bad)

    def test_js_start_requires_fresh_hotseat_lab_and_append_is_detached(self):
        record, _, chain = make_record(actions=[action("play", (2, 0))])
        options = {"sessionId": SESSION, "catalogVersion": 1}
        empty, _, _ = make_record()
        self.assertEqual(js_call("create", {"view": chain[0]["before"], "options": options})["value"], empty)
        result = js_call("append", {"record": empty, "event": chain[0]})
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["inputUnchanged"])
        self.assertEqual(result["value"], record)
        for mutate in (
            lambda v: v["match"].update(mode="computer"), lambda v: v.update(moves_played=1),
            lambda v: v.update(rules="classic"), lambda v: v.update(experimental=False),
        ):
            view = deepcopy(chain[0]["before"])
            mutate(view)
            self.assertFalse(js_call("create", {"view": view, "options": options})["ok"])

    def test_v1_record_validator_and_new_replay_dependencies_remain_isolated(self):
        legacy = {
            "format": "varde-human-playtest", "version": 1, "session_id": SESSION,
            "source": "browser-local-hotseat", "rules": {"id": "classic", "revision": "classic-1.3"},
            "board_size": 3, "catalog_version": 1, "native_evaluator_hash": "a" * 64,
            "status": "active", "actions": [], "final_score": None,
            "resumption_used": False, "ended_by_stagnation": False,
        }
        self.assertTrue(validate_playtest_record(legacy))
        with self.assertRaises(ValueError):
            validate_lab_record_shape(legacy)
        modern, _, _ = make_record()
        with self.assertRaises(ValueError):
            validate_playtest_record(modern)
        forbidden = {"server", "learning", "opponent", "lab_opponent", "lab_oracle", "mcts"}
        tree = ast.parse((ROOT / "research" / "harness" / "lab_record.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {name.name.rsplit(".", 1)[-1] for name in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").rsplit(".", 1)[-1]}
            else:
                continue
            self.assertFalse(names & forbidden, names)


if __name__ == "__main__":
    unittest.main()
