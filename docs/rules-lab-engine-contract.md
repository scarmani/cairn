# Laboratory engine integration contract

This implements the frozen revision-0.1 definitions; it does not change a rule.
The reference `engine/varde.py` remains unchanged. New server/browser wiring is
deferred to Batch4. The three scoring variants, four construction games and three
static controls are implemented behind the explicit opt-in factory and covered
by mechanical and compatibility tests; none is a new ordinary browser default.

## Ownership and shared surfaces

- `lab_graph.py`: immutable geometry only, no capture or turn authority.
- `lab_game.py`: laboratory game state, flat resolution, scoring, repetition,
  construction transitions and version-2 serialization as implemented by batch.
- `game_factory.py`: explicit experiment/research selection and version dispatch.
- `actions.py`: the single structured legal-action representation and seat-aware
  ending adapter. Old `key()` and old action representations remain compatible;
  a separate complete `analysis_key()` is used by new research.
- `server.py`: later factory consumer, not a second rules implementation.

Legacy opponent reply scans call `resolve` directly. Laboratory opponents must
use the common laboratory transition API at both plies, never merely pass a new
rules ID into the old evaluator. The user Personal model is not a lab evaluator.

## Geometry identity

Original vertex coordinates and axial face coordinates are stable IDs. Centers
are `(3q, 2r+q)`, disjoint from original vertices. Dense indices are snapshot
indices, not permanent node identities. Each snapshot exposes original vertices,
all construction sites, active centers, ordered corner incidence and actual
adjacency separately. An inactive center does not occur in adjacency or state.

The bounded geometry cache includes board size, geometry revision, spoke family
and canonical `(q,r,orientation)` records. The same orientation integer means
different edges in Y, six and passage families. Duplicate/unknown faces and
noninteger or out-of-range orientations are errors, not normalization hints.

All shared collections are immutable, including map values; attributes cannot
be reassigned. Construction returns a new snapshot. Outer rim/phantom metadata
is inherited geometrically from the original board, not recomputed as three
minus an increased degree. Pickle reconstructs through the canonical factory.
Cache eviction can create an equal but nonidentical board object. Canonical keys,
adjacency and snapshot isolation, not permanent interning, are the cross-process
contract. A live clone directly shares its immutable source board.

## Position identity and saves

Repetition includes rules ID/revision, size, canonical topology, flat stones and
next color. Analysis additionally includes the complete forbidden history, seats,
pie state, ending acceptances, resumption and all turn-phase state. A hash of the
current stones alone is never a safe search/transposition key.

Version-1 saves retain the legacy loader. Version-2 laboratory saves include a
complete action journal as well as topology-aware history. Replay from the
declared initial geometry validates the supplied current position, all history
entries, turn counters and administration; a missing earlier history entry must
not be silently repaired. This is stronger than structural validation of an
unordered history set, which cannot detect omitted forbidden positions.

Journal events use the shared action names and coordinate/orientation semantics.
Ordinary play increments placement count; empty construction increments
construction count; planting increments both but consumes one substantive action.
Pass consumes a turn but neither counter. Pie, acceptance and resumption remain
separate administrative actions. Game-level journal replay and seat-level ending
state are distinct: two passes are not an accepted-terminal result.

Unsupported revisions, malformed points/stacks/topology, Boolean-as-integer
counters, unknown action phases, incompatible history, and invented extension or
stagnation state are rejected explicitly. Both existing format identifiers are
accepted with the correct version. No live move, time or quiet-action ceiling is
introduced by validation or search safety mechanisms.

Constructed mechanical test positions may exercise local invariants directly.
They must not be exported as reachable journal-certified game evidence unless
their legal replay actually establishes that provenance.

## Batch 4 public API contract (frozen before wiring)

Laboratory creation requires `experimental: true` and one of the seven lab IDs.
Static controls remain research-only and never appear in the public catalog.
Existing catalog entries and legacy request/response/save semantics are preserved.
New catalog entries have `experimental: true`, `experimental_available: true`,
`public_new_game: false`, `status: "experimental"`, `rules_revision: "0.1"`,
allowed sizes 3–6, supported actions, scoring description and
`analysis_status: "unmeasured"`. Ordinary browser choices remain unchanged.

`POST /api/action` takes exactly a `RulesAction.to_dict()` object: placement uses
`point`, construction/planting use axial `face` and integer `orientation`, and
administrative actions have only `action`. Laboratory play/pass/swap/resume
aliases use that same adapter; none duplicates game or ending logic. Invalid
actions and wrong-seat human actions fail without mutating the displayed match.

Laboratory public state adds:

- `experimental`, `rules_revision`, and `flat: true`;
- `accepted`, `actor_color`, and `actor_seat` (null actors after acceptance);
- `placements_played`, `constructions_played`, and canonical `topology`;
- `legal_actions`, using the shared structured action wire representation;
- `construction_sites`, each with `face`, `center`, ordered `corners`, `active`,
  `orientation` (null if unused), `legal_orientations`, action `kind`, and all
  allowed `orientations` as corner-index arrays;
- point flags `original`, `scoring`, `center`, and actual `neighbors`;
- separate original-point control, all-active-point control, and objective score.

Inactive centers are not points or liberties. Active sites retain their orientation
but have no legal construction orientations. Scoring variants have no construction
sites. Every lab point has `sky: false`; ordinary liberties are distinct empty
actual neighbors. Majority lines are original but not individually scoreable:
its objective is cell ownership, exposed separately. `finished` means the two-pass
ending has begun, not that the result is accepted. Ending controls use actor identity.
`current_player` is the acting seat's name, null after acceptance; `to_move` retains
the engine color. `cells` contains Majority objects with axial `face`, doubled
coordinate `center`, six line-coordinate `edges`, per-color `counts`, and nullable
`owner`. Other lab games have an empty cells list. `original_control` is distinct
from all-active `control`; neither is substituted for the objective `score`.

One persistent `RulesState` is authoritative for lab seat identities, ending
acceptances, next ending decider and accepted-terminal state. `MatchConfig` holds
seat presentation/settings and references that state. A takeover swaps complete
Seat objects exactly once. Do not reuse legacy ending shortcuts which skip human
decisions or synthesize extra acceptances after resumption.

Version-2 server snapshots are `RulesState.to_dict()` plus `match`; loading
cross-validates seat identities, names, acceptance state and mode. The rules-state
loader still validates the complete game journal. Version-1 loading is unchanged.

Lab computers use only Casual/Standard and no Classic/Personal profile. Explicit
profile requests are rejected; absent profile data remains absent/null, never
silently normalized to Balanced. All three match configurations are representable.
`/api/computer` uses the provisional `lab-native-objective-v1` recipe described in
`rules-lab-native-agent.md`. It analyzes an isolated rules-state clone and commits
exactly one returned action through the shared adapter. The public decision and
catalog identify the recipe and source hash; neither implies MCTS admission.
Browser laboratory exposure remains a subsequent unit. No Personal model is read
as a lab evaluator or overwritten.
