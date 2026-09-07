"""Real HTTP boundary tests for the explicitly experimental laboratory API."""

from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import Mock, patch

import server
from lab_spec import LAB_SPECS, STATIC_CONTROL_SPECS
from varde import Game


class QuietHandler(server.VardeHandler):
    def log_message(self, *_args):
        pass


class TestLabHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.worker = threading.Thread(
            target=cls.httpd.serve_forever, kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.worker.join(timeout=2)

    def setUp(self):
        self.old = server.GAME, server.MATCH, server.LAST_DECISION
        server.GAME, server.MATCH, server.LAST_DECISION = Game(3), server.MatchConfig(), None
        self.model_patch = patch.object(server, "MODEL", Mock(status=lambda: {"games_trained": 0}))
        self.model_patch.start()

    def tearDown(self):
        server.GAME, server.MATCH, server.LAST_DECISION = self.old
        self.model_patch.stop()

    def request(self, route, body=None, *, status=200):
        connection = HTTPConnection(*self.httpd.server_address, timeout=20)
        try:
            connection.request(
                "GET" if body is None else "POST", route,
                None if body is None else json.dumps(body),
                {} if body is None else {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, status, (route, body, payload))
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            return payload
        finally:
            connection.close()

    def new(self, rules="junction-y", **settings):
        return self.request("/api/new", {
            "rules": rules, "n": 3, "experimental": True, **settings,
        })

    def act(self, kind, **fields):
        return self.request("/api/action", {"action": kind, **fields})

    def snapshot(self):
        return self.request("/api/snapshot")

    def test_catalog_is_explicit_and_never_exposes_static_controls(self):
        entries = {item["id"]: item for item in self.request("/api/rulesets")["rulesets"]}
        for spec in LAB_SPECS:
            item = entries[spec.id]
            self.assertTrue(item["experimental"])
            self.assertTrue(item["experimental_available"])
            self.assertFalse(item["public_new_game"])
            self.assertEqual(item["rules_revision"], "0.1")
            self.assertEqual(item["analysis_status"], "unmeasured")
            self.assertEqual(item["allowed_sizes"], [3, 4, 5, 6])
            self.assertEqual(item["supported_actions"], list(spec.supported_actions))
            self.assertTrue(item["scoring_description"])
        for spec in STATIC_CONTROL_SPECS:
            self.assertNotIn(spec.id, entries)
            self.request("/api/new", {
                "rules": spec.id, "n": 3, "experimental": True,
            }, status=400)

    def test_opt_in_and_strict_lab_size_do_not_replace_live_match_on_failure(self):
        before = self.snapshot()
        for body in (
            {"rules": "junction-y", "n": 3},
            {"rules": "junction-y", "n": 3, "experimental": False},
            {"rules": "junction-y", "n": 3, "experimental": "true"},
            {"rules": "junction-y", "n": "3", "experimental": True},
            {"rules": "junction-y", "n": True, "experimental": True},
            {"rules": "junction-y", "n": 7, "experimental": True},
        ):
            with self.subTest(body=body):
                self.request("/api/new", body, status=400)
                self.assertEqual(self.snapshot(), before)

    def test_every_lab_has_typed_state_and_full_size_support(self):
        for spec in LAB_SPECS:
            for n in (3, 6):
                with self.subTest(rules=spec.id, n=n):
                    view = self.new(spec.id, n=n)
                    self.assertTrue(view["experimental"])
                    self.assertTrue(view["flat"])
                    self.assertFalse(view["accepted"])
                    self.assertEqual(view["rules_revision"], "0.1")
                    self.assertEqual(view["actor_color"], "B")
                    self.assertEqual(view["actor_seat"], view["match"]["seats"]["B"]["identity"])
                    self.assertEqual(view["placements_played"], 0)
                    self.assertEqual(view["constructions_played"], 0)
                    self.assertEqual(view["topology"], [])
                    self.assertTrue(all(not point["sky"] for point in view["points"]))
                    points = {tuple(point["coord"]): point for point in view["points"]}
                    for coord, point in points.items():
                        self.assertIn("scoring", point)
                        self.assertTrue(point["original"])
                        self.assertFalse(point["center"])
                        self.assertEqual(len(point["neighbors"]), len({tuple(q) for q in point["neighbors"]}))
                        for neighbor in point["neighbors"]:
                            self.assertIn(list(coord), points[tuple(neighbor)]["neighbors"])
                    if spec.construction == "none":
                        self.assertEqual(view["construction_sites"], [])
                    else:
                        self.assertEqual(len(view["construction_sites"]), 3 * n * (n - 1) + 1)
                        self.assertTrue(all(not site["legal_orientations"] for site in view["construction_sites"]))
                    if spec.scoring == "cell-majority":
                        self.assertTrue(all(not p["scoring"] for p in view["points"]))

    def test_construct_face_is_not_center_and_preserves_neutral_topology(self):
        self.new()
        self.request("/api/action", {"action": "construct", "face": [1, 0], "orientation": 1}, status=400)
        self.act("play", point=[-8, 0])
        view = self.act("construct", face=[1, 0], orientation=1)
        self.assertEqual(view["topology"], [[1, 0, 1]])
        self.assertEqual((view["placements_played"], view["constructions_played"]), (1, 1))
        center = next(point for point in view["points"] if point["coord"] == [3, 1])
        self.assertTrue(center["center"])
        self.assertFalse(center["scoring"])
        self.assertEqual(center["stack"], [])
        self.assertEqual(len(center["neighbors"]), 3)
        site = next(site for site in view["construction_sites"] if site["face"] == [1, 0])
        self.assertTrue(site["active"])
        self.assertEqual(site["orientation"], 1)
        self.assertEqual(site["legal_orientations"], [])
        self.assertEqual(site["orientations"], [[0, 2, 4], [1, 3, 5]])
        self.assertEqual(
            {tuple(point) for point in center["neighbors"]},
            {tuple(site["corners"][i]) for i in (1, 3, 5)},
        )
        before = self.snapshot()
        self.request("/api/action", {"action": "construct", "face": [1, 0], "orientation": 0}, status=400)
        self.assertEqual(self.snapshot(), before)
        occupied = self.act("play", point=[3, 1])
        self.assertEqual(occupied["topology"], [[1, 0, 1]])

    def test_plant_is_one_action_with_two_counters_and_no_empty_build(self):
        self.new("junction-planted")
        self.act("play", point=[-8, 0])
        view = self.act("plant", face=[1, 0], orientation=0)
        self.assertEqual(view["moves_played"], 2)
        self.assertEqual((view["placements_played"], view["constructions_played"]), (2, 1))
        center = next(point for point in view["points"] if point["coord"] == [3, 1])
        self.assertEqual(center["stack"], ["W"])
        self.assertFalse(center["scoring"])
        self.assertNotIn("construct", {action["action"] for action in view["legal_actions"]})

    def test_malformed_actions_return_json_errors_and_never_mutate(self):
        self.new()
        self.act("play", point=[-8, 0])
        before = self.snapshot()
        for action in (
            [], {"action": "construct", "point": [0, 0], "orientation": 0},
            {"action": "construct", "face": [0, 0], "orientation": True},
            {"action": "construct", "face": [0, 0], "orientation": 2},
            {"action": "plant", "face": [0, 0], "orientation": 0},
            {"action": "play", "point": [1.5, 1]},
            {"action": "pass", "point": [0, 0]},
            {"action": "extend", "point": [0, 0]},
            {"action": "finish-extension"},
        ):
            with self.subTest(action=action):
                self.assertIn("error", self.request("/api/action", action, status=400))
                self.assertEqual(self.snapshot(), before)

    def test_endpoint_aliases_share_authoritative_ending_and_save_round_trip(self):
        self.new("junction-passage", players={"B": "Ada", "W": "Grace"})
        self.request("/api/play", {"point": [-8, 0]})
        swapped = self.request("/api/swap", {})
        self.assertEqual(swapped["players"], {"B": "Grace", "W": "Ada"})
        self.request("/api/pass", {})
        pending = self.request("/api/pass", {})
        self.assertTrue(pending["finished"])
        self.assertFalse(pending["accepted"])
        first = self.act("accept")
        self.assertNotEqual(first["actor_seat"], pending["actor_seat"])
        self.assertFalse(first["accepted"])
        saved = self.snapshot()
        self.assertEqual(saved["version"], 2)
        self.new("line-breath")
        loaded = self.request("/api/load", saved)
        self.assertEqual(loaded, first)
        self.assertEqual(self.snapshot(), saved)
        resumed = self.request("/api/resume", {})
        self.assertFalse(resumed["finished"])
        self.assertEqual(resumed["match"]["end_acceptances"], [])
        self.request("/api/pass", {})
        self.request("/api/pass", {})
        final = self.act("accept")
        self.assertTrue(final["accepted"])
        self.assertIsNone(final["actor_color"])
        self.assertIsNone(final["actor_seat"])
        self.assertEqual(final["legal_actions"], [])
        self.assertEqual(len(final["match"]["end_acceptances"]), 1)
        accepted_save = self.snapshot()
        self.request("/api/action", {"action": "accept"}, status=400)
        self.request("/api/resume", {}, status=400)
        self.assertEqual(self.snapshot(), accepted_save)

    def test_human_actions_do_not_cross_computer_ownership(self):
        self.new(mode="computer", human_color="W", difficulty="casual")
        before = self.snapshot()
        for route, body in (("/api/action", {"action": "play", "point": [-8, 0]}),
                            ("/api/play", {"point": [-8, 0]}), ("/api/pass", {})):
            self.request(route, body, status=400)
            self.assertEqual(self.snapshot(), before)
        self.new(mode="watch", black_difficulty="casual", white_difficulty="standard")
        view = self.request("/api/state")
        self.assertEqual(view["match"]["seats"]["B"]["difficulty"], "casual")
        self.assertEqual(view["match"]["seats"]["W"]["difficulty"], "standard")
        for seat in view["match"]["seats"].values():
            self.assertIsNone(seat.get("profile"))
        self.request("/api/action", {"action": "play", "point": [-8, 0]}, status=400)

    def test_snapshot_mismatch_is_rejected_atomically(self):
        self.new()
        self.act("play", point=[-8, 0])
        saved = self.snapshot()
        bad = deepcopy(saved)
        bad["match"]["seats"]["B"]["identity"] = "invented"
        self.request("/api/load", bad, status=400)
        self.assertEqual(self.snapshot(), saved)
        bad = deepcopy(saved)
        bad["history"].pop()
        self.request("/api/load", bad, status=400)
        self.assertEqual(self.snapshot(), saved)


if __name__ == "__main__":
    unittest.main()
