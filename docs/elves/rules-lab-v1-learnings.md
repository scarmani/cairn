# Rules Laboratory: reusable learnings

## Repo conventions

- The legacy `cairn` launch directory is not the current git checkout. Use the
  run's isolated `varde-rules-lab-v1` worktree; preserve the shared varde checkout.
- The current rules engine is `engine/varde.py`. Legacy format/model identifiers
  intentionally retain Cairn naming for compatibility.

## Validation and tooling

- CI uses `python -m unittest discover -s engine -v` with Python 3.12. Runtime
  has no external dependencies; no Node application build is required.
- `.gitignore` already excludes `.playwright-mcp/`, `docs/audit/`, and `.aragora/`.

## Product and domain invariants

- Game clones share board geometry. Dynamic adjacency must be immutable and
  topology-keyed, never changed in place on a shared Board instance.
- Existing repetition histories are not complete analysis keys. Include forbidden
  positions and seat/ending/turn state for proof/transposition caches.
- An unordered save history cannot prove that no forbidden entry was omitted.
  New lab saves carry a legal action journal and compare the replayed complete
  history and state; old version-1 saves retain their original loader.
- Shared action repr/order/key changes can perturb historical seeded decisions.
  Keep the legacy key path and expose complete analysis keys separately.
- Dynamic-board cache keys include spoke family: orientation zero is not the
  same graph in Y, six and passage. Original rim metadata must not be recomputed
  as three minus an increased degree. Pickle reconstructs immutable maps by key.
- Bounded geometry caches do not promise permanent interning. A Full Passage
  legality scan can generate267 candidate graphs and evict the current board
  from the256-entry LRU. Test warm-cache identity separately from post-eviction
  canonical/neighbor equality; live clones still share their immutable board.
- A planted new hub cannot remove any pre-existing enemy liberty. A test reporting
  immediate enemy capture from planting alone signals a topology/resolution error.
- A local survival proof does not show survival is preferable to a sacrifice.
- A complete game journal does not recover omitted historical seat acceptances.
  A replayed suffix must not regain a full-action-history provenance flag.
- Python cache keys equate bool/int/float scalar aliases. Validate exact topology
  scalar types before entering an LRU, including when the canonical key is warm.
- Generic bounded proof traversal needs an explicit stack: Python recursion must
  not become an undeclared horizon. Count yielded actions even if enumeration fails.
- Scoring variants change units/incentives. Keep objective score and physical
  occupancy separate; no cross-ruleset pooled Elo or implicit beauty metric.

## Review heuristics

- Legacy seeded behavior needs fixtures before shared refactoring, not just
  post-change tests written to agree with the new implementation.
- Preserve negative search evidence; no historical V5 success assumption.

## Retired learnings

None.
