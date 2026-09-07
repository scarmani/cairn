"""Frozen Rules Laboratory specifications, without product registry wiring.

Availability describes the intended audience once implemented, not an assertion
that these games can currently be constructed. Importing this module does not
register rules, alter legacy defaults, or admit an agent for research matches.
"""

from dataclasses import asdict, dataclass
from types import MappingProxyType


LAB_CATALOG_VERSION = 1
LAB_RULES_REVISION = "0.1"
ALLOWED_SIZES = (3, 4, 5, 6)

# Zero-based, counterclockwise from the rightmost corner, matching varde.CORNERS.
HEX_CORNER_OFFSETS = ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))
Y_ORIENTATIONS = ((0, 2, 4), (1, 3, 5))
SIX_ORIENTATIONS = ((0, 1, 2, 3, 4, 5),)
PASSAGE_ORIENTATIONS = ((0, 3), (1, 4), (2, 5))
STATIC_Y_SEED_RECIPE = "sha256-varde-static-y-v1"

BASE_ACTIONS = ("swap", "play", "pass", "resume", "accept")
CONSTRUCT_ACTIONS = BASE_ACTIONS + ("construct",)
PLANTED_ACTIONS = BASE_ACTIONS + ("plant",)

# These are named independent concepts, not an aggregate quality/beauty score.
SHARED_CONCEPTS = (
    "alternating-single-stone-placement",
    "same-color-connected-groups",
    "distinct-empty-neighbor-liberties",
    "situational-superko",
    "original-point-opening-and-pie",
    "two-pass-seat-acceptance-and-once-only-resumption",
)
BREATH_CONCEPTS = SHARED_CONCEPTS + (
    "pre-capture-mover-breath",
    "capture-libertyless-enemy-groups",
)
GO_CONCEPTS = SHARED_CONCEPTS + (
    "capture-libertyless-enemy-groups",
    "post-capture-suicide-rejection",
)
AREA_CONCEPTS = ("occupied-points-and-single-color-empty-regions",)
JUNCTION_CONCEPTS = (
    "one-neutral-permanent-junction-per-original-face",
    "topology-aware-liberties-and-superko",
    "original-vertices-only-area-scoring",
)


@dataclass(frozen=True)
class LabRulesetSpec:
    """Immutable metadata for one frozen laboratory game or static control."""

    id: str
    label: str
    geometry: str
    resolution: str
    scoring: str
    construction: str
    supported_actions: tuple[str, ...]
    description: str
    hypothesis: str
    rule_concepts: tuple[str, ...]
    orientation_sets: tuple[tuple[int, ...], ...] = ()
    experimental_availability: str = "experimental-lab"
    topology_seed_recipe: str | None = None
    majority_threshold: int | None = None
    group_penalty: int = 0
    revision: str = LAB_RULES_REVISION
    allowed_sizes: tuple[int, ...] = ALLOWED_SIZES
    admission_status: str = "unmeasured"

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("a nonempty laboratory ruleset ID is required")
        if self.revision != LAB_RULES_REVISION:
            raise ValueError("unsupported laboratory rules revision")
        if self.experimental_availability not in ("experimental-lab", "research-only"):
            raise ValueError("invalid experimental availability")
        if self.admission_status != "unmeasured":
            raise ValueError("a specification alone cannot establish admission")
        if self.allowed_sizes != ALLOWED_SIZES or type(self.allowed_sizes) is not tuple:
            raise ValueError("laboratory sizes are frozen at 3 through 6")
        for values in (self.supported_actions, self.rule_concepts):
            if type(values) is not tuple or not all(isinstance(v, str) for v in values):
                raise TypeError("metadata collections must be immutable string tuples")
            if len(set(values)) != len(values):
                raise ValueError("metadata collections cannot contain duplicates")
        if type(self.orientation_sets) is not tuple:
            raise TypeError("orientations must be an immutable tuple")
        for orientation in self.orientation_sets:
            if type(orientation) is not tuple or not orientation:
                raise TypeError("each orientation must be a nonempty immutable tuple")
            if any(type(i) is not int or not 0 <= i < 6 for i in orientation):
                raise ValueError("orientation corners must be integers 0 through 5")
            if len(set(orientation)) != len(orientation):
                raise ValueError("orientation cannot repeat a corner")
        if self.majority_threshold is not None and (
            type(self.majority_threshold) is not int or self.majority_threshold != 4
        ):
            raise ValueError("the frozen cell threshold is at least four edges")
        if type(self.group_penalty) is not int or self.group_penalty not in (0, 1):
            raise ValueError("the frozen group penalty is zero or one")

    @property
    def evaluation_id(self):
        return f"{self.id}-{self.revision}"

    @property
    def public_new_game(self):
        """No laboratory specification is an ordinary new-game default."""
        return False

    def public_dict(self):
        """Return detached JSON-ready metadata, not an implementation assertion."""
        payload = asdict(self)
        payload.update(
            evaluation_id=self.evaluation_id,
            public_new_game=self.public_new_game,
        )
        for key in ("supported_actions", "allowed_sizes", "rule_concepts"):
            payload[key] = list(payload[key])
        payload["orientation_sets"] = [list(item) for item in self.orientation_sets]
        return payload


LAB_SPECS = (
    LabRulesetSpec(
        id="line-breath", label="Line Breath", geometry="kagome-lines",
        resolution="breath-first", scoring="line-area", construction="none",
        supported_actions=BASE_ACTIONS,
        description="Breath on Gjerde lines; occupied lines and single-color empty regions score, not cells.",
        hypothesis="Four-neighbor line geometry may support competing connection and cutting choices without regional fences.",
        rule_concepts=BREATH_CONCEPTS + AREA_CONCEPTS,
    ),
    LabRulesetSpec(
        id="gjerde-majority", label="Gjerde Majority", geometry="kagome-lines",
        resolution="breath-first", scoring="cell-majority", construction="none",
        supported_actions=BASE_ACTIONS, majority_threshold=4,
        description="A cell scores one point for a player controlling at least four of its six edges; no regional score.",
        hypothesis="An edge serving two cells may create readable competing commitments, with local-counting collapse as a risk.",
        rule_concepts=BREATH_CONCEPTS + ("at-least-four-of-six-cell-ownership",),
    ),
    LabRulesetSpec(
        id="breath-connection", label="Breath Connection", geometry="honeycomb-vertices",
        resolution="breath-first", scoring="area-minus-groups", construction="none",
        supported_actions=BASE_ACTIONS, group_penalty=1,
        description="Ordinary Breath area score minus one point per surviving friendly connected group.",
        hypothesis="A connection tax may make cuts and distributed settlement consequential without rewarding one giant army exclusively.",
        rule_concepts=BREATH_CONCEPTS + AREA_CONCEPTS + ("one-point-per-surviving-group-penalty",),
    ),
    LabRulesetSpec(
        id="junction-y", label="Y-Junction Go", geometry="honeycomb-junctions",
        resolution="capture-first", scoring="original-vertex-area", construction="empty-y",
        supported_actions=CONSTRUCT_ACTIONS, orientation_sets=Y_ORIENTATIONS,
        description="Spend a turn adding an empty center joined to either alternating set of three corners.",
        hypothesis="Orientable shared junctions may produce connection-and-cutting choices while preserving triangle-free geometry.",
        rule_concepts=GO_CONCEPTS + JUNCTION_CONCEPTS + ("empty-construction-replaces-placement", "two-y-orientations"),
    ),
    LabRulesetSpec(
        id="junction-six", label="Six-Spoke Go", geometry="honeycomb-junctions",
        resolution="capture-first", scoring="original-vertex-area", construction="empty-six",
        supported_actions=CONSTRUCT_ACTIONS, orientation_sets=SIX_ORIENTATIONS,
        description="Spend a turn adding an empty center joined to all six corners; the opponent may occupy it first.",
        hypothesis="Neutral six-way opportunities may make building and occupying distinct decisions, unless routine development erases fights.",
        rule_concepts=GO_CONCEPTS + JUNCTION_CONCEPTS + ("empty-construction-replaces-placement", "six-spoke-junction"),
    ),
    LabRulesetSpec(
        id="junction-planted", label="Planted Y Go", geometry="honeycomb-junctions",
        resolution="capture-first", scoring="original-vertex-area", construction="planted-y",
        supported_actions=PLANTED_ACTIONS, orientation_sets=Y_ORIENTATIONS,
        description="Place a stone at an unused center while creating its chosen Y connections; topology remains after capture.",
        hypothesis="Committing a stone during construction may make contested junction investment meaningful without empty-liberty emergency builds.",
        rule_concepts=GO_CONCEPTS + JUNCTION_CONCEPTS + ("atomic-planted-construction", "two-y-orientations"),
    ),
    LabRulesetSpec(
        id="junction-passage", label="Passage Go", geometry="honeycomb-junctions",
        resolution="capture-first", scoring="original-vertex-area", construction="empty-passage",
        supported_actions=CONSTRUCT_ACTIONS, orientation_sets=PASSAGE_ORIENTATIONS,
        description="Spend a turn adding an empty center joined to one chosen pair of opposite corners.",
        hypothesis="Two-neighbor bridges may yield vulnerable, legible connections, or collapse into forced local sequences.",
        rule_concepts=GO_CONCEPTS + JUNCTION_CONCEPTS + ("empty-construction-replaces-placement", "three-opposite-pair-orientations"),
    ),
)

STATIC_CONTROL_SPECS = (
    LabRulesetSpec(
        id="go-honeycomb", label="Static Honeycomb Go", geometry="honeycomb-vertices",
        resolution="capture-first", scoring="original-vertex-area", construction="none",
        supported_actions=BASE_ACTIONS, experimental_availability="research-only",
        description="Ordinary Go on the original honeycomb, with no junctions or construction actions.",
        hypothesis="The undeveloped-geometry control isolates construction and capture-order effects.",
        rule_concepts=GO_CONCEPTS + AREA_CONCEPTS,
    ),
    LabRulesetSpec(
        id="go-static-six", label="Static Six-Spoke Go", geometry="honeycomb-junctions",
        resolution="capture-first", scoring="original-vertex-area", construction="prebuilt-six",
        supported_actions=BASE_ACTIONS, orientation_sets=SIX_ORIENTATIONS,
        experimental_availability="research-only",
        description="Every original face starts with an empty six-spoke center; only original vertices score.",
        hypothesis="A fully developed control separates six-way connectivity from the choice and tempo of construction.",
        rule_concepts=GO_CONCEPTS + ("fixed-six-spoke-geometry", "original-vertices-only-area-scoring"),
    ),
    LabRulesetSpec(
        id="go-static-y", label="Static Y Go", geometry="honeycomb-junctions",
        resolution="capture-first", scoring="original-vertex-area", construction="prebuilt-y",
        supported_actions=BASE_ACTIONS, orientation_sets=Y_ORIENTATIONS,
        experimental_availability="research-only", topology_seed_recipe=STATIC_Y_SEED_RECIPE,
        description="Every face starts with a seed-frozen empty Y center; no construction or rotation is available.",
        hypothesis="Seed-frozen Y geometry separates heterogeneous connectivity from player-directed geography.",
        rule_concepts=GO_CONCEPTS + ("seed-frozen-y-geometry", "original-vertices-only-area-scoring"),
    ),
)

LAB_REGISTRY = MappingProxyType({spec.id: spec for spec in LAB_SPECS})
STATIC_CONTROL_REGISTRY = MappingProxyType({spec.id: spec for spec in STATIC_CONTROL_SPECS})
EXPERIMENT_SPECS = LAB_SPECS + STATIC_CONTROL_SPECS
EXPERIMENT_REGISTRY = MappingProxyType({spec.id: spec for spec in EXPERIMENT_SPECS})


def _get_spec(registry, rules):
    if not isinstance(rules, str) or rules not in registry:
        raise ValueError("invalid laboratory ruleset")
    return registry[rules]


def get_lab_spec(rules):
    """Look up one of the seven planned browser-laboratory games."""
    return _get_spec(LAB_REGISTRY, rules)


def get_experiment_spec(rules):
    """Look up a laboratory game or one of its three static research controls."""
    return _get_spec(EXPERIMENT_REGISTRY, rules)


def lab_specs_public():
    """Metadata-only catalog; calling this does not expose product choices."""
    return {
        "version": LAB_CATALOG_VERSION,
        "rulesets": [spec.public_dict() for spec in LAB_SPECS],
    }
