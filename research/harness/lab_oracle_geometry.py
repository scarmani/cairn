"""Independent immutable geometry for the revision-0.1 mechanical oracle.

Only standard-library imports. The small rule table is transcribed from the
frozen written laboratory rules, not imported from production metadata.
"""

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from types import MappingProxyType


REVISION = "0.1"
CORNERS = ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))
ORIENTATIONS = MappingProxyType({
    "none": (), "y": ((0, 2, 4), (1, 3, 5)),
    "six": ((0, 1, 2, 3, 4, 5),), "passage": ((0, 3), (1, 4), (2, 5)),
})


@dataclass(frozen=True)
class OracleRule:
    lines: bool
    breath_first: bool
    scoring: str
    family: str = "none"
    construction: str | None = None
    prebuilt: bool = False


RULES = MappingProxyType({
    "line-breath": OracleRule(True, True, "area"),
    "gjerde-majority": OracleRule(True, True, "majority"),
    "breath-connection": OracleRule(False, True, "connection"),
    "junction-y": OracleRule(False, False, "area", "y", "construct"),
    "junction-six": OracleRule(False, False, "area", "six", "construct"),
    "junction-planted": OracleRule(False, False, "area", "y", "plant"),
    "junction-passage": OracleRule(False, False, "area", "passage", "construct"),
    "go-honeycomb": OracleRule(False, False, "area"),
    "go-static-y": OracleRule(False, False, "area", "y", prebuilt=True),
    "go-static-six": OracleRule(False, False, "area", "six", prebuilt=True),
})


def rule_spec(rules, n):
    if not isinstance(rules, str) or rules not in RULES:
        raise ValueError("unsupported oracle ruleset")
    if type(n) is not int or n not in (3, 4, 5, 6):
        raise ValueError("oracle size must be an integer from 3 through 6")
    return RULES[rules]


def face_ids(n):
    return tuple((q, r) for q in range(1 - n, n) for r in range(1 - n, n)
                 if abs(q + r) < n)


def canonical_topology(rules, n, records):
    spec = rule_spec(rules, n)
    if not isinstance(records, (list, tuple)):
        raise ValueError("topology must be a sequence of triples")
    known = frozenset(face_ids(n))
    found = set()
    result = []
    for row in records:
        if (not isinstance(row, (list, tuple)) or len(row) != 3
                or any(type(value) is not int for value in row)):
            raise ValueError("invalid topology triple")
        q, r, orientation = row
        if (q, r) not in known or (q, r) in found:
            raise ValueError("unknown or duplicate construction face")
        if not 0 <= orientation < len(ORIENTATIONS[spec.family]):
            raise ValueError("invalid topology orientation")
        found.add((q, r))
        result.append((q, r, orientation))
    return tuple(sorted(result))


def initial_topology(rules, n, seed):
    spec = rule_spec(rules, n)
    if type(seed) is not int:
        raise ValueError("topology seed must be an integer")
    if not spec.prebuilt:
        return ()
    result = []
    for q, r in face_ids(n):
        orientation = 0
        if spec.family == "y":
            data = json.dumps(["varde-static-y-v1", seed, q, r], separators=(",", ":")).encode("utf-8")
            orientation = hashlib.sha256(data).digest()[0] & 1
        result.append((q, r, orientation))
    return tuple(result)


@dataclass(frozen=True)
class OracleGeometry:
    rules: str
    n: int
    topology: tuple
    points: tuple
    original_points: tuple
    active_centers: frozenset
    faces: object
    neighbors: object
    index: object
    cell_edges: object
    centers: object
    segments: object
    edges: tuple


@lru_cache(maxsize=128)
def _build(rules, n, topology):
    spec = rule_spec(rules, n)
    centers = {face: (3 * face[0], 2 * face[1] + face[0]) for face in face_ids(n)}
    faces = {face: tuple((center[0] + dx, center[1] + dy) for dx, dy in CORNERS)
             for face, center in centers.items()}
    base_edges = {tuple(sorted((corners[i], corners[(i + 1) % 6])))
                  for corners in faces.values() for i in range(6)}
    base_vertices = sorted({point for edge in base_edges for point in edge})
    cell_edges, segments = {}, {}
    if spec.lines:
        edge_points = {edge: (edge[0][0] + edge[1][0], edge[0][1] + edge[1][1])
                       for edge in base_edges}
        if len(set(edge_points.values())) != len(base_edges):
            raise ValueError("ambiguous line coordinates")
        original = tuple(sorted(edge_points.values()))
        incidence = {vertex: [] for vertex in base_vertices}
        for edge, point in edge_points.items():
            for endpoint in edge:
                incidence[endpoint].append(point)
        neighbors = {point: set() for point in original}
        for incident in incidence.values():
            for point in incident:
                neighbors[point].update(other for other in incident if other != point)
        for face, corners in faces.items():
            cell_edges[face] = tuple(edge_points[tuple(sorted((corners[i], corners[(i + 1) % 6])))]
                                     for i in range(6))
        segments = {point: edge for edge, point in edge_points.items()}
    else:
        original = tuple(base_vertices)
        neighbors = {point: set() for point in original}
        for a, b in base_edges:
            neighbors[a].add(b)
            neighbors[b].add(a)
    active = frozenset(centers[(q, r)] for q, r, _ in topology)
    for q, r, orientation in topology:
        center = centers[(q, r)]
        neighbors[center] = set()
        for index in ORIENTATIONS[spec.family][orientation]:
            point = faces[(q, r)][index]
            neighbors[center].add(point)
            neighbors[point].add(center)
    points = original + tuple(sorted(active))
    adjacency = {point: tuple(sorted(neighbors[point])) for point in points}
    edges = tuple(sorted((point, neighbor) for point in points for neighbor in adjacency[point]
                         if point < neighbor))
    return OracleGeometry(
        rules, n, topology, points, original, active,
        MappingProxyType(faces), MappingProxyType(adjacency),
        MappingProxyType({point: index for index, point in enumerate(points)}),
        MappingProxyType(cell_edges), MappingProxyType(centers), MappingProxyType(segments), edges,
    )


def build_geometry(rules, n, topology=()):
    return _build(rules, n, canonical_topology(rules, n, topology))
