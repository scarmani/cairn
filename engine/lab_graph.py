"""Immutable honeycomb and junction geometry for the experimental laboratory.

This module has no stone, capture, score, turn, or placement-legality authority.
Coordinate tuples are permanent point IDs. ``index`` is snapshot-local: points
are ordered original vertices first, then active centers in coordinate order.
Inactive centers occur in construction metadata only, never in adjacency.
"""

from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from lab_spec import (
    ALLOWED_SIZES,
    HEX_CORNER_OFFSETS,
    PASSAGE_ORIENTATIONS,
    SIX_ORIENTATIONS,
    Y_ORIENTATIONS,
    get_experiment_spec,
)


Point = tuple[int, int]
Face = tuple[int, int]
Topology = tuple[tuple[int, int, int], ...]
GEOMETRY_REVISION = "lab-honeycomb-0.1"
GRAPH_CACHE_MAXSIZE = 256
ORIENTATIONS = MappingProxyType({
    "none": (), "y": Y_ORIENTATIONS, "six": SIX_ORIENTATIONS,
    "passage": PASSAGE_ORIENTATIONS,
})


def _size(n):
    if type(n) is not int or n not in ALLOWED_SIZES:
        raise ValueError("laboratory board size must be an integer from 3 through 6")
    return n


def _family(spoke_family):
    if not isinstance(spoke_family, str):
        raise ValueError("invalid spoke family")
    if spoke_family == "honeycomb":
        return "none"
    if spoke_family not in ORIENTATIONS:
        raise ValueError("invalid spoke family")
    return spoke_family


def _face(face):
    if not isinstance(face, (tuple, list)) or len(face) != 2:
        raise ValueError("face must be a pair of integer axial coordinates")
    if any(type(value) is not int for value in face):
        raise ValueError("face must be a pair of integer axial coordinates")
    return tuple(face)


@lru_cache(maxsize=len(ALLOWED_SIZES))
def _base(n):
    faces = {}
    centers = {}
    adjacency = {}
    for q in range(1 - n, n):
        for r in range(1 - n, n):
            if abs(q + r) >= n:
                continue
            center = (3 * q, 2 * r + q)
            corners = tuple((center[0] + dx, center[1] + dy)
                            for dx, dy in HEX_CORNER_OFFSETS)
            faces[(q, r)] = corners
            centers[(q, r)] = center
            for i, point in enumerate(corners):
                neighbor = corners[(i + 1) % 6]
                adjacency.setdefault(point, set()).add(neighbor)
                adjacency.setdefault(neighbor, set()).add(point)
    original_points = tuple(sorted(adjacency))
    neighbors = {point: tuple(sorted(adjacency[point])) for point in original_points}
    phantoms = {point: 3 - len(neighbors[point]) for point in original_points}
    rim = frozenset(point for point in original_points if phantoms[point] > 0)
    return (
        original_points, MappingProxyType(faces), MappingProxyType(centers),
        MappingProxyType(neighbors), MappingProxyType(phantoms), rim,
    )


def canonical_topology(n, spoke_family, records=()) -> Topology:
    """Sort valid activation records; duplicates are errors, never coalesced."""
    _size(n)
    family = _family(spoke_family)
    if isinstance(records, (str, bytes, dict)):
        raise ValueError("topology must contain activation triples")
    try:
        rows = tuple(records)
    except TypeError as exc:
        raise ValueError("topology must contain activation triples") from exc
    faces = _base(n)[1]
    seen = set()
    canonical = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            raise ValueError("activation must contain q, r, and orientation")
        if any(type(value) is not int for value in row):
            raise ValueError("activation coordinates and orientation must be integers")
        q, r, orientation = row
        face = (q, r)
        if face not in faces:
            raise ValueError("unknown construction face")
        if face in seen:
            raise ValueError("a face may be activated only once")
        if not 0 <= orientation < len(ORIENTATIONS[family]):
            raise ValueError("orientation is invalid for this spoke family")
        seen.add(face)
        canonical.append((q, r, orientation))
    return tuple(sorted(canonical))


@dataclass(frozen=True, slots=True, eq=False, init=False)
class GraphBoard:
    """Read-only geometry snapshot; obtain instances from ``graph_board``."""

    n: int
    spoke_family: str
    topology: Topology
    original_points: tuple[Point, ...]
    scoring_points: frozenset[Point]
    faces: Mapping[Face, tuple[Point, ...]]
    centers: Mapping[Face, Point]
    center_faces: Mapping[Point, Face]
    active_centers: frozenset[Point]
    points: tuple[Point, ...]
    neighbors: Mapping[Point, tuple[Point, ...]]
    index: Mapping[Point, int]
    phantoms: Mapping[Point, int]
    rim: frozenset[Point]
    deep: frozenset[Point]
    _rim_distances: Mapping[Point, int] = field(repr=False)
    geometry_revision: str = field(default=GEOMETRY_REVISION, init=False)

    def __init__(self, *args, **kwargs):
        # A public data constructor could admit mutable or inconsistent maps
        # under an otherwise valid cache identity. Geometry has one authority.
        raise TypeError("construct immutable GraphBoard snapshots with graph_board()")

    @property
    def cache_key(self):
        return (self.geometry_revision, self.n, self.spoke_family, self.topology)

    def __hash__(self):
        return hash(self.cache_key)

    def __eq__(self, other):
        if not isinstance(other, GraphBoard):
            return NotImplemented
        return self.cache_key == other.cache_key

    def __reduce__(self):
        # MappingProxyType itself cannot be pickled; rebuild the canonical graph.
        return (_restore_board, (self.geometry_revision, self.n, self.spoke_family, self.topology))

    def with_junction(self, face, orientation):
        """Return new geometry only; game state decides whether building is legal."""
        q, r = _face(face)
        return graph_board(self.n, self.spoke_family, self.topology + ((q, r, orientation),))

    def dist_to_rim(self):
        """Active-graph distance to the fixed original missing-neighbor rim."""
        return self._rim_distances


@lru_cache(maxsize=GRAPH_CACHE_MAXSIZE)
def _cached_graph(geometry_revision, n, family, topology):
    if geometry_revision != GEOMETRY_REVISION:
        raise ValueError("unsupported geometry revision")
    original_points, faces, centers, base_neighbors, base_phantoms, rim = _base(n)
    neighbors = {point: set(base_neighbors[point]) for point in original_points}
    active_centers = set()
    for q, r, orientation in topology:
        face = (q, r)
        center = centers[face]
        active_centers.add(center)
        neighbors[center] = set()
        for corner_index in ORIENTATIONS[family][orientation]:
            corner = faces[face][corner_index]
            neighbors[corner].add(center)
            neighbors[center].add(corner)
    points = original_points + tuple(sorted(active_centers))
    immutable_neighbors = MappingProxyType({point: tuple(sorted(neighbors[point])) for point in points})
    distances = {point: 0 for point in sorted(rim)}
    queue = deque(sorted(rim))
    while queue:
        point = queue.popleft()
        for neighbor in immutable_neighbors[point]:
            if neighbor not in distances:
                distances[neighbor] = distances[point] + 1
                queue.append(neighbor)
    values = dict(
        n=n, spoke_family=family, topology=topology,
        original_points=original_points, scoring_points=frozenset(original_points),
        faces=faces, centers=centers,
        center_faces=MappingProxyType({point: face for face, point in centers.items()}),
        active_centers=frozenset(active_centers), points=points,
        neighbors=immutable_neighbors,
        index=MappingProxyType({point: i for i, point in enumerate(points)}),
        phantoms=MappingProxyType({point: base_phantoms.get(point, 0) for point in points}),
        rim=rim,
        deep=frozenset(point for point in points if point not in rim
                       and all(neighbor not in rim for neighbor in immutable_neighbors[point])),
        _rim_distances=MappingProxyType({point: distances[point] for point in points}),
        geometry_revision=GEOMETRY_REVISION,
    )
    board = object.__new__(GraphBoard)
    for name, value in values.items():
        object.__setattr__(board, name, value)
    return board


def graph_board(n, spoke_family="none", topology=()) -> GraphBoard:
    """Return cached immutable geometry; ``honeycomb`` aliases family ``none``."""
    _size(n)
    family = _family(spoke_family)
    canonical = canonical_topology(n, family, topology)
    return _cached_graph(GEOMETRY_REVISION, n, family, canonical)


graph_board.cache_info = _cached_graph.cache_info
graph_board.cache_clear = _cached_graph.cache_clear


def _restore_board(geometry_revision, n, spoke_family, topology):
    if geometry_revision != GEOMETRY_REVISION:
        raise ValueError("unsupported pickled laboratory geometry revision")
    return graph_board(n, spoke_family, topology)


def seeded_static_topology(n, spoke_family, seed=0) -> Topology:
    """All-face initial topology; only Y and six have frozen static controls."""
    _size(n)
    family = _family(spoke_family)
    if type(seed) is not int:
        raise ValueError("static topology seed must be an integer")
    if family == "none":
        return ()
    if family not in ("y", "six"):
        raise ValueError("no static control is specified for this spoke family")
    records = []
    for q, r in _base(n)[1]:
        orientation = 0
        if family == "y":
            encoded = json.dumps(["varde-static-y-v1", seed, q, r], separators=(",", ":")).encode("utf-8")
            orientation = hashlib.sha256(encoded).digest()[0] & 1
        records.append((q, r, orientation))
    return tuple(records)


def initial_graph_board(ruleset, n, seed=0) -> GraphBoard:
    """Initial honeycomb/junction graph; fixed Gjerde line boards are separate."""
    spec = get_experiment_spec(ruleset)
    _size(n)
    if type(seed) is not int:
        raise ValueError("initial topology seed must be an integer")
    if spec.geometry == "kagome-lines":
        raise ValueError("line geometry requires its separate fixed line board")
    families = {
        "none": "none", "empty-y": "y", "planted-y": "y", "empty-six": "six",
        "empty-passage": "passage", "prebuilt-y": "y", "prebuilt-six": "six",
    }
    family = families[spec.construction]
    topology = seeded_static_topology(n, family, seed) if spec.construction.startswith("prebuilt-") else ()
    return graph_board(n, family, topology)
