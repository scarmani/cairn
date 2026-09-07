"""Fixed short authoring table; no policy, search, proof, or adaptive repair.

Family labels are intended mechanical motifs, not claims about optimal actions.
Every declared chain survives in the manifest even when an action is illegal.
"""

from pathlib import Path

from research.harness.lab_origin import PRODUCTION_RULESETS, origin_configuration
from research.harness.lab_terminal_cert import canonical_hash

REVISION = "0.1"
TOPOLOGY_SEED = 230507
SIZES = (3, 4)
LINE_RULES = frozenset(("gjerde", "gjerde-go", "line-breath", "gjerde-majority"))
VERTEX_POINTS = ((2, 0), (-2, 0), (1, 1), (1, -1), (-8, 0), (-8, -2),
                 (5, -1), (4, 0), (-1, 1), (-1, -1))
LINE_POINTS = ((3, 1), (-3, -1), (0, 2), (0, -2), (-9, -3), (-12, -2),
               (-15, -3), (-9, -5), (-3, 1), (3, -1))
# Integers address the fixed coordinate table; strings are full administrative
# turns. These templates are independent of any observed legal-action list.
COMMON_TEMPLATES = (
    ("00-opening", "pie-choice", (0,)),
    ("01-separated", "separated-groups", (0, 1)),
    ("02-friendly-contact", "connection", (0, 1, 2)),
    ("03-hostile-contact", "contact", (0, 2, 1)),
    ("04-four-point", "cut-and-liberties", (0, 1, 2, 3)),
    ("05-rim-pair", "rim-connection", (4, 0, 5, 1)),
    ("06-takeover", "post-takeover", (0, "swap", 1, 2)),
    ("07-distributed", "distant-response", (4, 0, 2, 5, 1)),
    ("08-first-ending", "first-ending-seat", (0, 1, "pass", "pass")),
    ("09-second-ending", "second-ending-seat", (0, 2, 1, "pass", "pass", "accept")),
    ("10-resumed", "once-only-resumption", (4, 0, 2, "pass", "pass", "resume")),
    ("11-final-ending", "resumed-ending", (0, 1, 2, 3, "pass", "pass", "resume", "pass", "pass")),
)


def play(point):
    return {"action": "play", "point": list(point)}


def administrative(kind):
    return {"action": kind}


def construction(kind, face, orientation):
    return {"action": kind, "face": list(face), "orientation": orientation}


def _special(rules):
    """Four explicit family-specific chains, never legality-dependent."""
    v = [play(point) for point in VERTEX_POINTS]
    a = administrative
    c = construction
    if rules in LINE_RULES:
        e = [play(point) for point in LINE_POINTS]
        # Central face perimeter:0,2,8,1,3,9. Opponent filler is remote.
        return (
            ("12-three-edges", "near-fence", [e[0], e[4], e[2], e[5], e[8]]),
            ("13-four-edges", "majority-boundary", [e[0], e[4], e[2], e[5], e[8], e[6], e[1]]),
            ("14-mixed-fence", "mixed-boundary", [e[0], e[2], e[8], e[1], e[3]]),
            ("15-six-edges", "completed-fence-shape", [e[0], e[4], e[2], e[5], e[8], e[6],
                                                       e[1], e[7], e[3], a("pass"), e[9]]),
        )
    if rules == "junction-y":
        return (
            ("12-y-even", "empty-junction", [v[0], c("construct", (0, 0), 0)]),
            ("13-y-odd", "orientation", [v[0], c("construct", (0, 0), 1)]),
            ("14-hub-occupied", "opponent-hub-occupation", [v[0], c("construct", (0, 0), 0),
                                                           v[8], play((0, 0))]),
            ("15-hub-reopened", "capture-reopening", [v[0], c("construct", (0, 0), 0),
                                                      v[8], play((0, 0)), v[9]]),
        )
    if rules == "junction-six":
        return (
            ("12-six-center", "empty-junction", [v[0], c("construct", (0, 0), 0)]),
            ("13-six-offset", "offset-junction", [v[0], c("construct", (1, 0), 0)]),
            ("14-six-occupied", "opponent-hub-occupation", [v[0], c("construct", (0, 0), 0), play((0, 0))]),
            ("15-six-two-sites", "two-junctions", [v[0], c("construct", (0, 0), 0),
                                                   c("construct", (1, 0), 0)]),
        )
    if rules == "junction-planted":
        return (
            ("12-planted-even", "planted-junction", [v[0], c("plant", (0, 0), 0)]),
            ("13-planted-odd", "orientation", [v[0], c("plant", (0, 0), 1)]),
            ("14-planted-offset", "offset-junction", [v[0], c("plant", (1, 0), 1), v[8]]),
            ("15-planted-two-sites", "two-junctions", [v[0], c("plant", (0, 0), 0), c("plant", (1, 0), 1)]),
        )
    if rules == "junction-passage":
        return (
            ("12-passage-zero", "passage-orientation", [v[0], c("construct", (0, 0), 0)]),
            ("13-passage-one", "passage-orientation", [v[0], c("construct", (0, 0), 1)]),
            ("14-passage-two", "passage-orientation", [v[0], c("construct", (0, 0), 2)]),
            ("15-passage-occupied", "opponent-hub-occupation", [v[0], c("construct", (0, 0), 1), play((0, 0))]),
        )
    if rules == "breath-run":
        prefix = [v[0], v[2], v[4], v[3]]
        extension = {"action": "extend", "point": [4, 0]}
        return (
            ("12-rescue-option", "rescue-continuation", prefix),
            ("13-rescue-closed", "actor-changing-rescue", prefix + [extension]),
            ("14-rescue-open", "actor-preserving-rescue", prefix + [v[5], v[6], extension]),
            ("15-rescue-finished", "extension-closure", prefix + [v[5], v[6], extension, a("finish-extension")]),
        )
    if rules in ("classic", "rosette"):
        # Occupy all three neighbors before a cap; an isolated re-cover would
        # violate terrain. The exact authored attempt remains explicit if invalid.
        collar = [v[0], v[2], v[4], v[3], v[7]]
        return (
            ("12-collar", "collar-shape", collar),
            ("13-cap", "stack-investment", collar + [v[0]]),
            ("14-alternating-ring", "ring-shape", [v[0], v[2], v[8], v[1], v[9], v[3]]),
            ("15-linked-branches", "group-consolidation", [v[0], v[4], v[2], v[5], v[7], v[1], v[3]]),
        )
    if rules in ("go-static-six", "go-static-y"):
        return (
            ("12-static-hub", "prebuilt-hub-occupation", [v[0], play((0, 0))]),
            ("13-static-contact", "prebuilt-contact", [v[0], play((0, 0)), v[8]]),
            ("14-static-split", "prebuilt-connection", [v[0], v[4], play((0, 0)), v[5], v[8]]),
            ("15-static-ring", "ring-shape", [v[0], v[2], v[8], v[1], v[9], v[3]]),
        )
    return (
        ("12-sole-liberty", "sole-liberty-shape", [v[0], v[2], v[4], v[3]]),
        ("13-two-branches", "connection", [v[0], v[4], v[2], v[5], v[7]]),
        ("14-alternating-ring", "ring-shape", [v[0], v[2], v[8], v[1], v[9], v[3]]),
        ("15-linked-branches", "group-consolidation", [v[0], v[4], v[2], v[5], v[7], v[1], v[3]]),
    )


def authored_candidates():
    """Return512 detached definitions, ordered size/rule/template, without replay."""
    result = []
    for n in SIZES:
        for rules in PRODUCTION_RULESETS:
            points = LINE_POINTS if rules in LINE_RULES else VERTEX_POINTS
            templates = [(name, family, [play(points[x]) if type(x) is int else administrative(x)
                                        for x in chain]) for name, family, chain in COMMON_TEMPLATES]
            templates.extend(_special(rules))
            for name, family, actions in templates:
                result.append({"id": f"{rules}-n{n}-{name}", "template_id": name, "family": family,
                               "configuration": origin_configuration(rules, n, seed=TOPOLOGY_SEED),
                               "actions": actions})
    return result


def definitions_hash():
    return canonical_hash(authored_candidates())


def trusted_sources():
    root = Path(__file__).resolve().parents[2]
    labels = ("research/harness/lab_corpus_candidates.py", "docs/rules-lab-corpus-contract.md")
    return {label: root / label for label in labels}
