"""Short mechanical record fixtures and Python/JavaScript schema parity."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from actions import RulesAction, RulesState, apply_action
from game_factory import new_game

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "harness"))
import lab_record  # noqa: E402


SESSION = "12345678-1234-4234-8234-123456789abc"


def fixture(rules="junction-y", wires=(), n=3):
    game = new_game(n, rules=rules, experimental=True)
    game.players = {"B": "S1", "W": "S2"}
    state = RulesState(game, seats={"B": "S1", "W": "S2"})
    record = {"format": lab_record.FORMAT, "version": 2, "source": "browser-local-hotseat",
              "session_id": SESSION, "rules": {"id": rules, "revision": "0.1"}, "board_size": n,
              "catalog_version": 1, "initial_seats": {"B": "S1", "W": "S2"},
              "status": "active", "actions": [], "final_score": None}
    for wire in wires:
        action = RulesAction.from_dict(wire)
        before = state
        actor = {"seat": state.actor_seat, "color": state.actor_color}
        state = apply_action(state, action)
        record["actions"].append({"index": len(record["actions"]), "action": deepcopy(wire),
                                  "actor": actor, "elapsed_ms": 13,
                                  "captures": lab_record._capture_projection(before, state, action),
                                  "after": lab_record._projection(state)})
    if state.accepted:
        record.update(status="complete", final_score=state.game.score())
    return record, state


def validate_js(records):
    result = subprocess.run(
        ["node", "-e", "const fs=require('node:fs'); const api=require(process.argv[1]);"
         "const inputs=JSON.parse(fs.readFileSync(0,'utf8'));"
         "process.stdout.write(JSON.stringify(inputs.map(x=>{try{return {ok:true,value:api.validateLabRecordShape(x)}}"
         "catch(e){return {ok:false,error:e.message}}})));", str(ROOT / "web" / "lab-record.js")],
        input=json.dumps(records), text=True, capture_output=True, check=True, timeout=10,
    )
    return json.loads(result.stdout)


class TestLabRecord(unittest.TestCase):
    def test_all_construction_orientations_preserve_atomic_counters_and_replay(self):
        records = []
        for rules, (kind, count) in lab_record.CONSTRUCTION.items():
            for orientation in range(count):
                record, state = fixture(rules, (
                    {"action": "play", "point": [2, 0]},
                    {"action": kind, "face": [1, 0], "orientation": orientation},
                ))
                self.assertEqual(record["actions"][-1]["after"]["constructions_played"], 1)
                self.assertEqual(record["actions"][-1]["after"]["placements_played"], 2 if kind == "plant" else 1)
                self.assertEqual(state.game.topology, ((1, 0, orientation),))
                self.assertTrue(lab_record.replay_lab_record(record).mechanically_verified)
                records.append(record)
        self.assertTrue(all(result["ok"] for result in validate_js(records)))

    def test_accepted_terminal_and_pending_ending_are_distinct(self):
        wires = [{"action": "play", "point": [2, 0]}, {"action": "pass"}, {"action": "pass"},
                 {"action": "accept"}, {"action": "accept"}]
        for size in (3, 4, 5, 6):
            pending, _ = fixture(wires=wires[:4], n=size)
            complete, _ = fixture(wires=wires, n=size)
            self.assertFalse(lab_record.replay_lab_record(pending).accepted)
            self.assertTrue(lab_record.replay_lab_record(complete).accepted)
            self.assertEqual(pending["status"], "active")
            self.assertIsNone(pending["final_score"])
            self.assertEqual(complete["status"], "complete")
            self.assertEqual(complete["actions"][-1]["after"]["end_acceptances"], ["S1", "S2"])

    def test_save_names_never_enter_record_or_report_and_timing_does_not_change_replay_hash(self):
        record, _ = fixture(wires=({"action": "play", "point": [2, 0]},))
        before = deepcopy(record)
        first = lab_record.replay_lab_record(record)
        record["session_id"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        record["actions"][0]["elapsed_ms"] = 999
        second = lab_record.replay_lab_record(record)
        self.assertEqual(first.replay_hash, second.replay_hash)
        self.assertNotIn("actions", first.to_dict())
        self.assertNotIn("players", first.to_dict())
        self.assertIn("not a qualified human study", first.to_dict()["claim_limit"])
        checked = lab_record.validate_lab_record_shape(before)
        checked["actions"][0]["action"]["point"][0] = 9
        self.assertEqual(before["actions"][0]["action"]["point"], [2, 0])

    def test_exact_fields_privacy_and_number_shapes_agree_in_both_languages(self):
        base, _ = fixture(wires=({"action": "play", "point": [2, 0]},))
        invalid = []
        mutations = (
            lambda r: r.update(name="private"), lambda r: r.update(native_evaluator_hash="0" * 64),
            lambda r: r.pop("final_score"), lambda r: r.update(board_size=True),
            lambda r: r.update(catalog_version=0), lambda r: r.update(version=True),
            lambda r: r.update(source="network"), lambda r: r.update(session_id="a" * 32),
            lambda r: r["rules"].update(revision="0.2"), lambda r: r["rules"].update(id="static-six"),
            lambda r: r["actions"][0].update(elapsed_ms=0.5), lambda r: r["actions"][0].update(elapsed_ms=2**53),
            lambda r: r["actions"][0]["actor"].update(seat="actual-private-identity"),
            lambda r: r["actions"][0]["action"].update(orientation=0),
            lambda r: r["actions"][0]["after"].update(moves_played=True),
            lambda r: r["actions"][0]["after"]["score"].update(email="private"),
            lambda r: r["actions"][0]["after"].update(end_acceptances=["S2", "S1"]),
            lambda r: r["actions"][0]["captures"].update(waves=[[]]),
            lambda r: r["actions"][0]["captures"].update(original=1),
        )
        for mutate in mutations:
            bad = deepcopy(base)
            mutate(bad)
            with self.assertRaises(ValueError):
                lab_record.validate_lab_record_shape(bad)
            invalid.append(bad)
        self.assertTrue(all(not result["ok"] for result in validate_js(invalid)))
        self.assertTrue(validate_js([base])[0]["ok"])

    def test_integral_float_wire_forms_normalize_without_touching_input_or_shared_parser(self):
        record, _ = fixture("junction-planted", ({"action": "play", "point": [2, 0]},
                                                {"action": "plant", "face": [1, 0], "orientation": 1}))

        def floats(value):
            if type(value) is int:
                return float(value)
            if type(value) is list:
                return [floats(item) for item in value]
            if type(value) is dict:
                return {key: floats(item) for key, item in value.items()}
            return value

        floated = floats(record)
        checked = lab_record.validate_lab_record_shape(floated)
        self.assertEqual(checked, validate_js([floated])[0]["value"])
        self.assertIs(type(checked["version"]), int)
        self.assertIs(type(floated["version"]), float)
        self.assertIs(type(checked["actions"][0]["after"]["accepted"]), bool)
        self.assertEqual(lab_record.replay_lab_record(record).replay_hash, lab_record.replay_lab_record(floated).replay_hash)
        with self.assertRaises(ValueError):
            RulesAction.from_dict({"action": "plant", "face": [1.0, 0.0], "orientation": 1.0})
        for number in (float("nan"), float("inf"), -float("inf"), 0.1, float(2**53), True, "13"):
            bad = deepcopy(record)
            bad["actions"][0]["elapsed_ms"] = number
            with self.subTest(number=number), self.assertRaises(ValueError):
                lab_record.validate_lab_record_shape(bad)

    def test_all_action_row_and_projection_fields_are_replay_checked(self):
        record, _ = fixture(wires=({"action": "play", "point": [2, 0]},
                                   {"action": "construct", "face": [1, 0], "orientation": 0}))
        mutations = (
            lambda r: r["actions"][1]["after"]["score"].update(B=1),
            lambda r: r["actions"][1]["after"]["original_control"].update(W=1),
            lambda r: r["actions"][1]["after"].update(swap_available=True),
            lambda r: r["actions"][1]["after"]["topology"][0].__setitem__(2, 1),
            lambda r: r["actions"][1]["after"].update(resumption_used=True),
        )
        for mutate in mutations:
            bad = deepcopy(record)
            mutate(bad)
            lab_record.validate_lab_record_shape(bad)
            with self.assertRaisesRegex(ValueError, "telemetry mismatch"):
                lab_record.replay_lab_record(bad)
        outside = deepcopy(record)
        outside["actions"][1]["action"]["face"] = [999, 999]
        lab_record.validate_lab_record_shape(outside)
        with self.assertRaisesRegex(ValueError, "illegal recorded transition"):
            lab_record.replay_lab_record(outside)

    def test_cli_is_read_only_and_reports_malformed_records_without_traceback(self):
        valid, _ = fixture(wires=({"action": "play", "point": [2, 0]},))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.json"
            path.write_text(json.dumps(valid))
            before = path.read_bytes()
            command = [sys.executable, str(ROOT / "research" / "harness" / "lab_record.py"), str(path)]
            result = subprocess.run(command, cwd=directory, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["mechanically_verified"])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            valid["initial_seats"]["B"] = []
            path.write_text(json.dumps(valid))
            result = subprocess.run(command, cwd=directory, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)

    def test_import_never_loads_server_personal_or_native_opponent(self):
        script = "import sys; sys.path.insert(0,sys.argv[1]); " \
                 "sys.modules.update({name:None for name in ('server','learning','opponent','lab_opponent')}); " \
                 "import lab_record; print(lab_record.VERSION)"
        result = subprocess.run([sys.executable, "-c", script, str(ROOT / "research" / "harness")],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "2")

    def test_commonjs_and_browser_global_exports_match_without_dom_or_network(self):
        script = r"""
const fs=require('node:fs'), vm=require('node:vm');
const sandbox={window:{},fetch:()=>{throw Error('network forbidden')}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const common=require(process.argv[1]);
if(JSON.stringify(Object.keys(common).sort())!==JSON.stringify(Object.keys(sandbox.window.VardeLabRecord).sort())) throw Error('exports differ');
if(!Object.isFrozen(common)||!Object.isFrozen(sandbox.window.VardeLabRecord)) throw Error('mutable API');
console.log('ok');
"""
        result = subprocess.run(["node", "-e", script, str(ROOT / "web" / "lab-record.js")],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
