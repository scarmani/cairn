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
