# Rules Laboratory specifications, revision 0.1

These definitions implement the specification freeze in the approved
[laboratory plan](plans/rules-lab-v1.md). The catalog itself remains metadata;
the opt-in game factory now implements all seven games and three static controls.
Browser exposure is the next engineering batch. No experimental agent has passed
admission: all ten new entries retain admission status **unmeasured**. Normal
games and the six legacy candidates remain unchanged. No combination of the seven
changes is authorized in this round.

## Board, turns, and scoring conventions

The seven laboratory games and three static controls permit n=3, 4, 5, or 6.
Honeycomb original vertices number 6n²; the original bounded hexagonal faces
number 3n(n−1)+1. Gjerde line positions are the edges of this honeycomb; two line
positions are adjacent when their original edges share a vertex. Original
bounded faces, rather than arbitrary cycles or newly subdivided regions, are
the only construction sites.

All ten games are flat: one stone at an active point, with no stacking, terrain,
sky liberties, cap exceptions, or rescue phases. A group is a maximal connected
same-color set in the active graph. Its ordinary liberties are the **distinct**
adjacent active empty points; touching one point through several edges still
provides only one liberty. Inactive centers provide no connection or liberty.

Breath-first means the placed stone's group must have an ordinary liberty before
enemy captures resolve. Capture-first means remove enemy groups deprived of all
liberties by the placement, then reject the move if the mover remains without a
liberty. The former applies to the three scoring variants; the latter to all
junction games and static controls. Construction introduces no additional capture
exception.

Area means occupied scoreable points plus scoreable empty points in maximal
connected empty regions whose occupied border is nonempty and entirely one color.
Board edges do not supply fictitious liberties or a fictitious opposing border.
An empty board therefore scores zero for both players. For original-vertex area,
flood-fill the entire active graph, including empty junctions, but count only
original vertices. Junctions themselves never earn a point, occupied or empty.
Consequently a new empty center can join empty regions and change their ownership
without creating additional scoreable area.

Keep the existing pie identity exchange, two consecutive passes, separate seat
acceptances, and one permitted resumption. Require the opening stone on an
original vertex for honeycomb/junction games and on an original line position
for line games. No construction is an opening action. A substantive action after
the opening declines pie when applicable. Construction consumes the turn,
resets consecutive passes, and is not quiet merely because it leaves stones
unchanged. Junction games have no quiet-move rule or live action/time ceiling.
These metadata declarations do not change any legacy ending rule.

## Seven separately frozen games

| ID / label | Complete change from its reference | Hypothesis and main failure risk |
| --- | --- | --- |
| `line-breath` / Line Breath | Gjerde line adjacency and Breath-first resolution. Score occupied lines and single-color empty-line area; hexagonal cells have no score. | Additional connections may support attacks, cuts, and expansion; permanent large connections might instead become too safe. |
| `gjerde-majority` / Gjerde Majority | Gjerde-breath placement/capture. A cell scores one point for a player controlling **at least four** of its six original boundary lines; otherwise zero. No regional enclosure, occupied-line, or empty-line score. | Each shared edge contributes to two nearby cells; repetitive fourth-edge counting might dominate. Five- and six-edge ownership still score one, not extra points. |
| `breath-connection` / Breath Connection | Ordinary Breath area, minus exactly one point per surviving friendly group at accepted scoring. Captured groups incur no penalty; nothing else scores differently. | Connection and cutting may become economically meaningful; compulsory consolidation into one army would be adverse evidence. |
| `junction-y` / Y-Junction Go | Instead of a placement, activate an empty face center with one of the two Y orientations. | Three-spoke choices may support contested geography with quadrilateral spaces; emergency eye construction may become too favorable. |
| `junction-six` / Six-Spoke Go | Instead of a placement, activate an empty center connected to all six corners. | Shared construction and occupation may be competing investments; universal development may erase useful tactical distinctions. |
| `junction-planted` / Planted Y Go | Instead of an original-point placement, atomically activate a center, choose a Y orientation, and place the mover's stone there. Ordinary play remains available at an already active empty center. | Committing a stone might temper emergency construction; planted moves could instead become automatic or too rare. |
| `junction-passage` / Passage Go | Instead of a placement, activate an empty center connected to one opposite-corner pair. | Vulnerable two-neighbor bridges may yield legible sacrifices; fights may degenerate into forced short sequences. |

Every junction is neutral and permanent: only stones have color. A face can be
developed once, with no rotation, demolition, upgrades, or recursive subdivision.
The opponent gets the next ordinary turn after empty construction, and can play
at the new center if legal. Occupying a center connects adjacent friendly groups;
an empty center does not connect them. Capturing its stone reopens that liberty
without deleting the point or any spokes.

### Exact orientation vocabulary

Use zero-based corner indices in this counterclockwise order of scaled offsets:
`(2,0), (1,1), (-1,1), (-2,0), (-1,-1), (1,-1)`. They match the existing honeycomb
geometry; an original face `(q,r)` has scaled center `(3q, 2r+q)`.

| Construction | Orientation IDs and connected corner indices |
| --- | --- |
| Y, including planted Y | 0 → `(0,2,4)`; 1 → `(1,3,5)` |
| Six spokes | 0 → `(0,1,2,3,4,5)` |
| Passage | 0 → `(0,3)`; 1 → `(1,4)`; 2 → `(2,5)` |

Rotation/reflection must transform the selected corners as well as the board.
No orientation is privileged by player color. A Y divides one hexagon into three
quadrilateral faces; six spokes divide it into six triangles. The passage creates
two five-sided faces. These geometric facts are mechanical descriptions, not
evidence for tactical strength or beauty.

### Why planted construction cannot immediately capture an enemy

Before construction, the center is absent. Adding it occupied by the mover does
not remove or fill any old empty point, remove any old edge, or merge any enemy
group. Thus every pre-existing enemy liberty remains a liberty. An enemy group
legal before the action cannot become libertyless from planting alone. The
mover may nevertheless commit suicide, which must be rejected. Later ordinary
occupation of an active empty center can remove an existing liberty and capture.
This argument assumes an initially legal position; corrupt fixtures are not a
counterexample. Empty construction likewise removes no liberty, although it can
change scoring-region connectivity.

## Research-only static controls

These share capture-first resolution, original-vertex area, and the original-
vertex opening restriction. They have no construction actions and are not browser
laboratory candidates. Their topology is part of the immutable initial game
configuration and saved state.

| ID | Initial graph |
| --- | --- |
| `go-honeycomb` | The original honeycomb only. |
| `go-static-six` | Every original face already has an empty six-spoke center. |
| `go-static-y` | Every original face already has an empty Y center with seed-frozen orientation. |

Freeze static-Y initialization as `sha256-varde-static-y-v1`: encode the JSON
array `["varde-static-y-v1", seed, q, r]` with UTF-8, no optional whitespace, and
integer seed/axial face coordinates. The orientation is the low bit of the first
SHA-256 digest byte. Store the resulting orientations, not merely the seed.
It is independent of enumeration order, worker scheduling, and player color.
Symmetry fixtures transform the stored topology; regenerating a hash with rotated
coordinates is not a symmetry transformation. These controls separate geometry
from construction tempo; their result units must match the corresponding dynamic
game rather than awarding points for their extra centers.

## Rule economy: independent concepts, not an opaque total

Inventory the following shared concepts separately: alternating stone placement;
connected friendly groups; distinct empty liberties; capture order and suicide;
history-dependent repetition; scoreable points and ownership; original-point
opening with pie identity exchange; two-pass ending with seat acceptances and
once-only resumption. Do not count the same concept repeatedly because it appears
in several implementation functions, and do not turn this inventory into a beauty
rating.

| Family | Additional or replaced concept | Persistent information / global work |
| --- | --- | --- |
| Line Breath | Area on a different fixed graph; replaces cell enclosure | Fixed line graph; group/liberty scans and empty-region ownership |
| Majority | Four-of-six cell ownership replaces area/enclosure | Fixed cell-edge incidence; six-edge local count per cell |
| Connection | One point per group deducted from area | Group count at scoring in addition to existing area calculation |
| Empty junctions | A construction turn, permanent neutral topology, orientation, zero-point centers | Active face/orientation map; dynamic adjacency and topology-aware history |
| Planted junctions | Atomic create-and-occupy replaces the empty-construction option | Same topology and scoring distinctions; no added rescue phase |
| Static controls | Fixed developed geometry; static Y also has frozen setup variation | Initial topology retained throughout; no in-game topology decisions |

All variants retain global repetition checking. Added connectivity can also change
the scope of group and territory scans. Record turn phases, state, exceptions,
and checks individually; fewer words or faster code do not establish better rules.

## Finite-state termination argument and its limits

Let V be the finite number of original points and H the finite number of allowed
faces. Flat states have at most V+H stone positions, each absent/empty/Black/White
as constrained by topology; use `3^(V+H)` as a conservative occupancy bound after
choosing topology. Each face has at most three active orientation choices plus
an inactive state, so `4^H` is a common upper bound on dynamic topologies. A
finite signature space is therefore bounded above by `2 × 4^H × 3^(V+H)` for a
fixed rules revision, including next color. Fixed line games and static controls
have smaller finite bounds.

Every placement/construction must reject a repeated **rules revision + topology
+ stones + next color** signature. No topology can be removed or repeatedly
reoriented. Passing remains administratively legal even when its signature was
seen; two consecutive passes open the ending process. A single pass must either
be followed by a substantive action, or enter that process. Pie occurs at most
once; each ending has finitely many seat acceptances; the game has at most one
resumption. Therefore an infinite legal rules-action sequence would require
infinitely many distinct substantive signatures in a finite set, a contradiction.

This is a rule-level finite-game argument, not a completed implementation proof,
bound on practical game length, or evidence of satisfying closure. Implementation
must test the assumptions, including pass and ending semantics. Do not introduce
a live action ceiling. Research watchdogs report incompletes, never substitute
scores or prove a design defective by themselves.

The superko signature is distinct from an analysis/cache key: the latter also
includes the complete forbidden history, seat identities, and administrative
phase state. Including the full history in the repetition signature would defeat
repetition detection; omitting it from a proof cache can mislabel a legal action.
Version-2 laboratory saves must preserve topology in both the current position
and historical signatures. Legacy version-1 rules and histories remain unchanged.

## Evidence and next verification

Metadata tests establish the frozen definitions, orientation vocabulary,
immutability, detached finite JSON, and isolation from the legacy registry.
Additional engine/integration tests now exercise scoring, distinct liberties,
planted non-capture and suicide, merging, permanent topology after capture,
clone isolation, all spatial symmetries, topology/history round trips, pie, and
separate ending decisions. The [execution log](elves/rules-lab-v1-execution-log.md)
records test counts, independent review and raw-log hashes by checkpoint.
These tests do not constitute an admitted search corpus or comparative games.

All hypotheses above remain unmeasured. Local survival/capture proofs certify only
their declared obligation and horizon. Only accepted-terminal score certification
labels a search choice optimal. Comparative screening requires per-ruleset admitted
MCTS; computer descriptors cannot establish human clarity, beauty, or replay desire.
