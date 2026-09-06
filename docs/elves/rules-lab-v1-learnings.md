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
- A planted new hub cannot remove any pre-existing enemy liberty. A test reporting
  immediate enemy capture from planting alone signals a topology/resolution error.
- A local survival proof does not show survival is preferable to a sacrifice.
- Scoring variants change units/incentives. Keep objective score and physical
  occupancy separate; no cross-ruleset pooled Elo or implicit beauty metric.

## Review heuristics

- Legacy seeded behavior needs fixtures before shared refactoring, not just
  post-change tests written to agree with the new implementation.
- Preserve negative search evidence; no historical V5 success assumption.

## Retired learnings

None.
