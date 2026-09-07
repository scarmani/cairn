# Independent laboratory mechanics and bounded local proofs

Engineering contract, frozen before implementation. Revision `0.1`.
This unit supplies mechanical verification tools, not a certified admission
corpus, an admitted agent, or comparative game evidence.

## Independent rules implementation

`research/harness/lab_oracle.py` is stdlib-only and may not import the production
engine, action parser, graph builder, group finder, capture resolver, scorer,
opponents, or MCTS. Its small declarative rule/orientation table is independently
transcribed from `rules-lab-specs.md`; external tests compare it to the registry.
Duplicating these mechanics is intentional: shared implementation would defeat
the purpose of an independent check. No production consumer imports this oracle.

Use immutable `OracleAction`, `OracleGeometry`, `OracleState`, `OracleTransition`
and `OracleImport` results. Queries return immutable collections or detached
results. Geometry may be cached by canonical rule/size/topology; cache eviction
changes neither semantic equality nor caller ownership. Group construction uses
independent union-find components and distinct empty neighbors.

The API comprises independent strict action parsing, `new_state`, `geometry`,
`groups`, `liberties`, `score`, `legal_actions`, `transition`, complete-action
`replay`, and `load_snapshot`. Support all seven laboratory games and three static
controls, n=3–6. Unsupported legacy rules fail explicitly rather than using a
production fallback. Current and historical points use the written coordinate
contract: sorted original vertices followed by sorted active centers; line
coordinates are endpoint sums, with adjacency through shared original endpoints.

Transitions implement Breath-first or capture-first resolution as specified,
original-only opening, permanent neutral construction, atomic planted Y,
topology-aware superko, pass history insertion, pie identity exchange, separate
ending acceptances and once-only resumption. Every original/hub capture remains
separately countable. Area traverses all active nodes but scores only original
points; Majority counts cells with at least four edges; Connection subtracts
surviving groups. No quiet ending, action ceiling, or rule change is introduced.

## Import and provenance

`load_snapshot` independently validates version-2 schema, rules revision, initial
static geometry/seed, action journal, counters, current topology/stones, complete
history and optional current rules-state envelope. Accept both existing format
identifiers, reject malformed/unsupported inputs, and never mutate the input.
Do not call a production loader or repair missing forbidden history.

The game journal omits acceptance actions and the identity requesting earlier
resumption. An import therefore reports mechanical-journal verification and
current-envelope consistency separately from full historical seat-action replay.
It must not fabricate or claim to have observed omitted acceptances. A separate
`replay` of a complete RulesAction sequence can establish that stronger provenance.
Only a replay beginning at an equality-verified fresh initial state reports
`full_action_replay: true`. Replaying a suffix from an imported or constructed
state retains its supplied actor trace but cannot restore omitted historical
actions. Constructed invariant fixtures remain explicitly mechanical, not reachable
research evidence merely because their fields parse.

## Generic local proof plumbing

`research/harness/lab_local_proof.py` accepts immutable declarative goal metadata,
an explicit finite quantifier schedule, pure tri-state predicate callbacks, a
legal-action/transition interface, complete state fingerprint, and actor identity.
It shares no obligation classifier with an agent. Default domains include every
legal action; restricted domains and empty-domain conventions are explicit in
the claim scope. Check an explicitly declared closure immediately after each
transition, before checking which actor would act next. Actor mismatch or an
unresolved horizon returns `unknown`, never a guessed failure.

Return every legal root action exactly once in `proven_actions`,
`disproven_actions`, or `unknown_actions`, retaining all equivalent actions and
construction orientations. EXISTS is proven if any child is proven and disproven
only if all are disproven; FORALL is the dual. Unvisited branches after the shared
default10,000-node ceiling stay unknown. Count root enumeration, entered states,
transition attempts, cache hits, cancellation and exhaustion honestly.

Duplicate legal actions, failed declared-legal transitions, callback/source-state
mutation or invalid predicate output raise an integrity error; no certifiable
result is returned. Start without memoization rather than risk losing path/root
goal context. A future cache must include full forbidden history, topology, seat
phase, root action, predicate/spec hash and any path-dependent monitor state.

Traversal uses explicit DFS frames, so the declared node ceiling is not silently
replaced by Python's recursion limit. Partial legal-enumeration failures retain
their yielded-action count and return no certificate.

Certificates identify rules/input/spec/provider/predicate/oracle hashes, horizon,
quantifiers, each action's result and actor seat/color traces. Their mandatory
claim limit is **local predicate and declared horizon only; not optimal play**.
They never contain unqualified `optimal_actions` or game-result backup values.
Accepted-terminal minimax certification is a separate Batch5 result type. Its
declared objective must match MCTS reward: WDL-equivalent wins must not be rejected
merely for a smaller margin. Preserve accepted scores/margins separately.

## Acceptance and computation boundary

- Independent geometry/group/liberty/capture/scoring/history parity for all10
  definitions, all sizes, color and spatial transforms including stored static Y.
- Empty versus inactive centers, merged distinct liberties, capture reopening,
  orientation consequences, planted non-capture/suicide, original-only area and
  Majority/Connection objectives.
- Strict journals, topology-specific historical widths, malformed histories,
  pass/swap/resumption/acceptance provenance and clone/input isolation.
- Break production geometry/resolution/scoring/parser functions during an oracle
  call and verify the independent implementation still works; deliberate bad
  transition/history data must be detected.
- Synthetic bounded-tree tests for quantifiers, equivalent actions, closure,
  unknown horizons, node ceilings, orientation IDs, mutation and cancellation.
- Full474+ product tests, scoped Ruff, compilation/JS, frozen legacy parity,
  independent review and exact-tip CI. No production rules/server/browser/native
  recipe source changes in this unit.

These ordinary mechanical and synthetic-tree tests do not generate a research
dataset. Actual game proof certification, corpus searches, MCTS calibration and
comparative games are Batch5/6 work charged to the frozen three-window allowance.
None is launched by importing or testing these modules.
