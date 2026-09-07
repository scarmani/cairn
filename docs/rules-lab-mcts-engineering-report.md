# Rules Laboratory: MCTS engineering checkpoint

This is implementation evidence, not tactical admission, game strength, or a
comparison of ruleset quality. No recipe has passed the laboratory's independent
corpus gate. The official research allowance remains unused at this checkpoint.

## Implemented

The three frozen recipes share one generic core:

| Recipe | Difference from the control |
| --- | --- |
| `lab-uct-0.1` | Audited UCT control; complete legal expansion, terminal WDL rewards. |
| `lab-reserved-0.1` | Visit-gated expansion with mandatory administrative actions and structural ordering. |
| `lab-terminal-proof-0.1` | Reserved expansion plus sound exact accepted-terminal tree propagation. |

Both uniform and 10%-exploratory light rollouts retain every legal action. Search
tracks the original acting seat through takeover, consecutive turns, acceptance,
and resumption. Neither heuristic position values nor local rescue/capture
obligations become game-result backups. A fortunate terminal rollout does not
prove its nonterminal starting position. Exact proof uses and terminal simulations
are counted separately; interrupted decisions expose no selected action.

The production transition cache is shared across all recipes and both policies.
It reuses the existing single-resolution laboratory transitions and avoids
per-action legal-domain rescans for legacy rules. Complete oriented action wires,
full forbidden history, topology, journal, seats, and ending phases are preserved.
Used expansion successors must match the authoritative transition API. Snapshot,
domain, fact, successor, and terminal-score contradictions fail explicitly.

The cache's effective capacity is immutable and hashed. Its successors are
detached, including legacy mutable geometry. Capture facts distinguish original
stones from zero-point junction stones; covers are not mislabeled captures.
Fence facts are positive net objective cell gains, not durability certificates.
Rosette's defense descriptor is only a one-transition ordering proxy: ring life
differs from ordinary liberties, so this is not a certified-threat classifier.

## Verification

Substrate: `136312eda4d201b5883a80c87a6b608bd8668035`, with both CI checks green
before this unit began. The contract was frozen before implementation at
`a393bb35b943d20ea8bedc9c1ea07eacbf40ac92476438c0a6fc746371239125`.

- Core owner and independent synthetic checks: **51 passed**, 1.016 seconds.
- Mechanical adapter checks: **14 passed**, final run 122.058 seconds. Every
  fresh-position legal transition across all 16 definitions and four board sizes
  matches the frozen reference provider's snapshot and fingerprint.
- Worker/checkpoint integration: **8 passed**, 12.459 seconds. Twelve synthetic
  tasks cover all recipe/policy combinations with two replicates, using one,
  two, and eight workers. Completed canonical results match; timing is separate.
- Scoped Ruff, Python compilation, both JavaScript syntax checks, and diff checks
  pass. Existing tracked product and research source bytes are unchanged from
  the substrate.
- Full product suite: **811 passed**, 306.600 seconds, zero skips (73 additive
  tests; no removals or weakened existing tests). Final exact-tip CI is pending
  the closure push and will be recorded in the survival guide and execution log.

New search tests use synthetic graphs. Mechanical tests exercise real legal
transitions but do not run the new MCTS or terminal-proof search on game positions.
The existing product regression suite retains its historical smoke fixtures.
No official research ledger or window has opened; disposable worker-test ledgers
are engineering fixtures, not hidden research spending.

## Negative engineering evidence retained

Review exposed and corrected expansion-successor substitution, repeated full-state
domain/fact/successor/score contradictions, deadline/cancellation exit gaps,
partial-work accounting, and mutable cache-capacity identity drift. None changes
game rules or relaxes an admission gate.

One finite-seed exploration assertion incorrectly expected every event to appear
in a small sample; it was replaced with an explicit exploration-branch test while
retaining preference and support checks. The first worker integration run passed
seven of eight tests: its remaining test incorrectly expected automatic resume
after pre-dispatch cancellation. The frozen supervisor correctly demanded an
explicit reconciliation. The corrected test first verifies that refusal, supplies
the exact closed cohort receipt, and then requires unchanged completed-result
parity. The original failed log is preserved separately from the passing rerun.

## Next gated work

Add a trusted real-proof worker and immutable job manifests, test that integration,
and close its review/CI gates. Then execute the already predeclared 32-task charged
bootstrap, followed by budget-projected certification and MCTS admission where
the minimum independently certified development/holdout corpus exists.

There are no certified or admitted rulesets yet. Comparative matches remain
blocked per ruleset until admission passes. If certification or MCTS fails, retain
that result and finish honest evidence cards rather than substituting native-only
matches. No ruleset-depth, balance, beauty, or strength claim follows from this
checkpoint. PR23 stays draft and unmerged; PRs20–22 remain unchanged.
