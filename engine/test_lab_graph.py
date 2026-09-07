"""Graph-only geometry checks; no rollout, capture, or score implementation."""

from dataclasses import FrozenInstanceError, replace
import pickle
import unittest

from lab_graph import (
    GEOMETRY_REVISION, GRAPH_CACHE_MAXSIZE, ORIENTATIONS, GraphBoard, canonical_topology,
    graph_board, initial_graph_board, seeded_static_topology,
)
from varde import Board


def point_turn(point):
    x, y = point
    return ((x - 3 * y) // 2, (x + y) // 2)


def face_turn(face):
    q, r = face
    return (-r, q + r)


def point_reflect(point):
    return (point[0], -point[1])


def face_reflect(face):
    q, r = face
    return (q, -q - r)


class TestLabGraph(unittest.TestCase):
    def test_original_geometry_and_rim_match_all_legacy_sizes(self):
        for n in range(3, 7):
            with self.subTest(n=n):
                old = Board(n)
                board = graph_board(n)
                self.assertEqual(len(board.original_points), 6 * n * n)
                self.assertEqual(len(board.faces), 3 * n * (n - 1) + 1)
                self.assertEqual(board.original_points, tuple(old.points))
                self.assertEqual(dict(board.neighbors), old.neighbors)
                self.assertEqual(dict(board.phantoms), old.phantoms)
                self.assertEqual(board.rim, old.rim)
                self.assertEqual(board.deep, old.deep)
                self.assertEqual(dict(board.dist_to_rim()), old.dist_to_rim())
                self.assertEqual(board.scoring_points, frozenset(old.points))
                self.assertEqual(board.geometry_revision, GEOMETRY_REVISION)
                self.assertEqual(board.active_centers, frozenset())
                self.assertFalse(set(board.centers.values()) & set(board.points))
                for face, center in board.centers.items():
                    q, r = face
                    self.assertEqual(center, (3 * q, 2 * r + q))
                    self.assertEqual(board.center_faces[center], face)
                    self.assertEqual(len(board.faces[face]), 6)

    def test_each_activation_has_exact_edges_without_phantom_nodes(self):
        for n in range(3, 7):
            for family, choices in ORIENTATIONS.items():
                if family == "none":
                    continue
                parent = graph_board(n, family)
                for orientation, corners in enumerate(choices):
                    with self.subTest(n=n, family=family, orientation=orientation):
                        child = parent.with_junction((0, 0), orientation)
                        center = child.centers[(0, 0)]
                        expected = tuple(sorted(child.faces[(0, 0)][i] for i in corners))
                        self.assertEqual(child.neighbors[center], expected)
                        self.assertEqual(len(child.points), len(parent.points) + 1)
                        self.assertEqual(child.points[:len(parent.points)], parent.points)
                        self.assertEqual(child.active_centers, frozenset((center,)))
                        self.assertEqual(child.rim, parent.rim)
                        self.assertEqual(child.scoring_points, parent.scoring_points)
                        self.assertEqual(child.phantoms[center], 0)
                        for point in parent.points:
                            added = {center} if point in expected else set()
                            self.assertEqual(set(child.neighbors[point]), set(parent.neighbors[point]) | added)
                            self.assertEqual(child.phantoms[point], parent.phantoms[point])
                        self.assertNotIn(center, parent.neighbors)
                        for point in child.points:
                            self.assertNotIn(point, child.neighbors[point])
                            for neighbor in child.neighbors[point]:
                                self.assertIn(point, child.neighbors[neighbor])
                        inactive = set(child.centers.values()) - child.active_centers
                        self.assertFalse(inactive & set(child.neighbors))
                        self.assertFalse(inactive & set(child.dist_to_rim()))

    def test_canonical_construction_order_and_family_cache_separation(self):
        first = graph_board(3, "y").with_junction((0, 0), 0).with_junction((1, -1), 1)
        second = graph_board(3, "y").with_junction((1, -1), 1).with_junction((0, 0), 0)
        self.assertIs(first, second)
        self.assertIs(graph_board(3, "y", [[1, -1, 1], [0, 0, 0]]), first)
        self.assertEqual(first.topology, ((0, 0, 0), (1, -1, 1)))
        self.assertEqual(canonical_topology(3, "y", iter(first.topology)), first.topology)
        self.assertIs(graph_board(3, "honeycomb"), graph_board(3, "none"))
        y = graph_board(3, "y", ((0, 0, 0),))
        six = graph_board(3, "six", ((0, 0, 0),))
        passage = graph_board(3, "passage", ((0, 0, 0),))
        self.assertEqual(len({y.cache_key, six.cache_key, passage.cache_key}), 3)
        self.assertEqual(tuple(len(b.neighbors[(0, 0)]) for b in (y, six, passage)), (3, 6, 2))
        self.assertEqual(graph_board.cache_info().maxsize, GRAPH_CACHE_MAXSIZE)

    def test_full_geometries_and_local_face_structure(self):
        for n in range(3, 7):
            for family in ("y", "six", "passage"):
                empty = graph_board(n, family)
                topology = tuple((q, r, i % len(ORIENTATIONS[family]))
                                 for i, (q, r) in enumerate(empty.faces))
                board = graph_board(n, family, topology)
                self.assertEqual(len(board.points), len(board.original_points) + len(board.faces))
                self.assertEqual(board.active_centers, frozenset(board.centers.values()))
                self.assertTrue(all(0 <= p <= 1 for p in board.phantoms.values()))
                triangles = {
                    tuple(sorted((point, neighbor, third)))
                    for point in board.points for neighbor in board.neighbors[point]
                    for third in set(board.neighbors[point]) & set(board.neighbors[neighbor])
                }
                self.assertEqual(len(triangles), 6 * len(board.faces) if family == "six" else 0)
                center = board.centers[(0, 0)]
                corners = board.faces[(0, 0)]
                if family == "y":
                    index = next(i for q, r, i in topology if (q, r) == (0, 0))
                    selected = ORIENTATIONS[family][index]
                    for i in selected:
                        cycle = (center, corners[i], corners[(i + 1) % 6], corners[(i + 2) % 6])
                        for a, b in zip(cycle, cycle[1:] + cycle[:1]):
                            self.assertIn(b, board.neighbors[a])
                elif family == "passage":
                    self.assertEqual(len(board.neighbors[center]), 2)
                for point, distance in board.dist_to_rim().items():
                    self.assertEqual(distance == 0, point in board.rim)
                    if distance:
                        self.assertEqual(min(board.dist_to_rim()[nb] for nb in board.neighbors[point]), distance - 1)

    def test_cache_retention_is_bounded(self):
        graph_board.cache_clear()
        base = graph_board(3, "y")
        faces = tuple(base.faces)[:9]
        for mask in range(GRAPH_CACHE_MAXSIZE + 10):
            records = tuple((q, r, 0) for i, (q, r) in enumerate(faces) if mask & (1 << i))
            graph_board(3, "y", records)
        self.assertLessEqual(graph_board.cache_info().currsize, GRAPH_CACHE_MAXSIZE)
        self.assertEqual(base, graph_board(3, "y"))

    def test_rotation_and_reflection_transform_stored_orientations(self):
        for n in range(3, 7):
            for family in ("y", "six", "passage"):
                choices = ORIENTATIONS[family]
                topology = ((-1, 0, 0), (0, 0, 0), (1, -1, len(choices) - 1))
                original = graph_board(n, family, topology)
                for point_map, face_map, index_map in (
                    (point_turn, face_turn, lambda i: (i + 1) % 6),
                    (point_reflect, face_reflect, lambda i: (-i) % 6),
                ):
                    transformed = []
                    for q, r, orientation in topology:
                        q1, r1 = face_map((q, r))
                        selected = tuple(sorted(index_map(i) for i in choices[orientation]))
                        transformed.append((q1, r1, choices.index(selected)))
                    board = graph_board(n, family, transformed)
                    self.assertEqual(set(board.points), {point_map(p) for p in original.points})
                    self.assertEqual(board.rim, frozenset(point_map(p) for p in original.rim))
                    for point in original.points:
                        self.assertEqual(set(board.neighbors[point_map(point)]),
                                         {point_map(p) for p in original.neighbors[point]})

    def test_static_y_frozen_hash_vectors_and_initial_boards(self):
        vectors = ((0, 0, 0, 1), (0, 1, -1, 1), (7, -2, 1, 0),
                   (42, 2, -1, 1), (-3, 0, -2, 0), (123456789, -1, 2, 1))
        for seed, q, r, expected in vectors:
            topologies = [{(a, b): o for a, b, o in seeded_static_topology(n, "y", seed)}
                          for n in range(3, 7)]
            self.assertTrue(all(topology[(q, r)] == expected for topology in topologies))
        for n in range(3, 7):
            y = initial_graph_board("go-static-y", n, seed=7)
            self.assertEqual(y.topology, seeded_static_topology(n, "y", 7))
            self.assertEqual(len(y.active_centers), len(y.faces))
            self.assertEqual(seeded_static_topology(n, "six", -1), seeded_static_topology(n, "six", 999))
            self.assertEqual(initial_graph_board("go-static-six", n).topology, seeded_static_topology(n, "six"))
            for rules, family in (("junction-y", "y"), ("junction-planted", "y"),
                                  ("junction-six", "six"), ("junction-passage", "passage"),
                                  ("go-honeycomb", "none"), ("breath-connection", "none")):
                board = initial_graph_board(rules, n, seed=4)
                self.assertEqual(board.spoke_family, family)
                self.assertEqual(board.topology, ())
            self.assertEqual(seeded_static_topology(n, "none"), ())

    def test_invalid_topology_and_construction_are_not_normalized_away(self):
        for n in (True, 3.0, "3", 2, 7, None):
            with self.subTest(n=n), self.assertRaises(ValueError):
                graph_board(n)
        for family in ("unknown", None, [], 1):
            with self.subTest(family=family), self.assertRaises(ValueError):
                graph_board(3, family)
        invalid = (None, "", {(0, 0): 0}, ((0, 0),), ((0, 0, 0, 0),),
                   ((True, 0, 0),), ((0, 0.0, 0),), ((0, 0, False),),
                   ((3, 0, 0),), ((2, 2, 0),), ((0, 0, -1),), ((0, 0, 2),),
                   ((0, 0, 0), (0, 0, 0)), ((0, 0, 0), (0, 0, 1)))
        for topology in invalid:
            with self.subTest(topology=topology), self.assertRaises(ValueError):
                graph_board(3, "y", topology)
        with self.assertRaises(ValueError):
            graph_board(3, "none", ((0, 0, 0),))
        board = graph_board(3, "y", ((0, 0, 0),))
        for face, orientation in (((0, 0), 0), ((0, 0), 1), ((0,), 0), ((True, 0), 0), ((0, 1), 2)):
            with self.subTest(face=face, orientation=orientation), self.assertRaises(ValueError):
                board.with_junction(face, orientation)
        for rules in ("line-breath", "gjerde-majority", "classic", "not-a-rule"):
            with self.assertRaises(ValueError):
                initial_graph_board(rules, 3)
        for seed in (True, "7", 7.0, None):
            with self.assertRaises(ValueError):
                seeded_static_topology(3, "y", seed)
            with self.assertRaises(ValueError):
                initial_graph_board("junction-y", 3, seed)
        with self.assertRaises(ValueError):
            seeded_static_topology(3, "passage")

    def test_immutable_metadata_snapshot_isolation_and_pickle(self):
        parent = graph_board(3, "y")
        child = parent.with_junction((0, 0), 1)
        with self.assertRaises(FrozenInstanceError):
            child.n = 4
        with self.assertRaises(FrozenInstanceError):
            del child.topology
        with self.assertRaises(TypeError):
            GraphBoard()
        with self.assertRaises(TypeError):
            replace(child, neighbors={})
        for values in (child.faces, child.centers, child.center_faces, child.neighbors,
                       child.index, child.phantoms, child.dist_to_rim()):
            with self.assertRaises(TypeError):
                values["changed"] = 1
        with self.assertRaises(TypeError):
            child.faces[(0, 0)][0] = (99, 99)
        with self.assertRaises(TypeError):
            child.neighbors[(0, 0)][0] = (99, 99)
        self.assertNotIn((0, 0), parent.points)
        self.assertEqual(parent.topology, ())
        self.assertEqual(child.topology, ((0, 0, 1),))
        self.assertIs(pickle.loads(pickle.dumps(child)), child)
        restore, arguments = child.__reduce__()
        with self.assertRaises(ValueError):
            restore("unknown-geometry", *arguments[1:])
        prior_hash = hash(child)
        encoded = pickle.dumps(child)
        graph_board.cache_clear()
        restored = pickle.loads(encoded)
        self.assertEqual(restored, child)
        self.assertEqual(hash(restored), prior_hash)
        self.assertEqual(dict(restored.neighbors), dict(child.neighbors))
        self.assertIsNot(restored, child)


if __name__ == "__main__":
    unittest.main()
