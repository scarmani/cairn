# Rules Laboratory MCTS engineering contract 0.1

Frozen before implementation or measured search outcomes, on substrate
`136312eda4d201b5883a80c87a6b608bd8668035`. Both exact-tip CI checks passed
(34096836729 and 34096839267). The one bounded 5E advisory is complete;
receipt `20260907T073029Z` is advisory, not authority to alter gates.

## Scope and ownership

One 5E engineering unit: a shared generic MCTS core, three immutable recipes,
source-bound production transition/fact cache, and synthetic worker/checkpoint
tests. No actual-game MCTS decision, proof, policy game, or calibration in this
unit. Trusted proof-job integration and its charged bootstrap remain subsequent
gates. All prior source/contracts/corpus/indices remain byte-identical. Only
additive research modules/tests and run documents; no rules/API/browser/save,
Personal model, protected branch, or historical MCTS changes. No merge.

Owners: lab_budget owns `research/harness/lab_mcts.py` and owner synthetic tests;
lab_compatibility owns `research/harness/lab_search_adapter.py` and mechanical
parity/fact tests; lab_plan_review owns independent synthetic invariant tests
and read-only review; root owns synthetic worker/checkpoint integration and
complete verification. All tests use the same frozen contract.

## API

`search(root, provider: TerminalProvider, *, recipe, policy, simulations, seed,
rollout_limit, expand=None, cancelled=None, deadline=None, clock=time.monotonic)`
returns a frozen, detached SearchResult. Canonical data/hash exclude timing.
Expansion rows expose detached complete `.action`, canonical-JSON `.action_id`,
immutable `.facts`, and `.successor()` returning a deep copy. `expand(state)`
returns the complete tuple; without it, the generic core materializes the
provider's complete legal domain with zero structural facts. The core validates
rows against `provider.legal_actions`; the production cache provider reuses the
already generated batch. No nested legality scan is needed for that validation.

Fact fields are `action_kind: str`, `extension_action: bool`,
`captured_original: int`, `captured_junction: int`, `defended_group_count: int`,
and `completed_cells: int`; all counts are exact nonnegative integers.
`captured_enemy_stones` is original plus junction captures. Facts are ordering
descriptors, never scores or proof predicates. Core callback/tree-work counters
and adapter counter deltas remain separate, not inferred from one another.

## Controlled recipes and randomness

Immutable IDs: `lab-uct-0.1`, `lab-reserved-0.1`, `lab-terminal-proof-0.1`.
One core, identical keys, transitions, facts, rewards, rollouts, and ties; only
reserved expansion and exact proof propagation flags differ. No inherited
assumption that historical V3/V4/V5 search was competent.

Use UCT on [0,1] original-root-seat WDL reward with exploration sqrt(2).
At opponent-seat nodes, exploitation is one minus root mean. Consecutive turns
follow actual actor identity, not depth parity or fixed color. Draw reward is
0.5. Map the original root seat through terminal color ownership. Score only
accepted terminals; winning margins are equivalent WDL. Ordinary final choice
is greatest visits, then greatest root mean, then semantic seeded hash. Return
the full oriented action wire, never an orientation-dropping legacy key.

Seeded semantic hashes contain fixed stream labels, complete root/node identity,
user seed, iteration, and action ID as appropriate. No global random, repr or
coordinate-lexicographic tie preference, clock, worker ID, or scheduling input.
Exclude recipe ID and requested budget from RNG streams, preserving common
prefixes when paths agree. The full recipe, provider/source identity, policy,
seed, and requested budget remain in agent/result identity.

Uniform rollouts choose uniformly from the complete legal domain using semantic
seeded ordering. Independently implemented light rollouts use 10% uniform
exploration and otherwise seeded ties among the lexicographically greatest
`(extension_action, captured_enemy_stones, defended_group_count, completed_cells)`.
Every legal action retains positive probability. No settling, depth evaluator,
heuristic terminal, forced losing-seat preference, or fourth architecture.

## Expansion and iteration accounting

UCT control exposes all legal actions, semantic ordering only. Reserved variants
expose `min(A, max(1, ceil(2*sqrt(visits))))`, plus ALL legal administrative
actions: swap, pass, resume, accept, finish-extension. Mandatory actions may
overflow the base schedule. Fill remaining slots by administrative, extension,
capture, defense, immediate fence-completion, other tiers; semantic ties within
tiers. Apply at root and interior; eventual full expansion is preserved. Hidden
actions remain legal and unknown. Record exposed/hidden domains and actual visits.

Statistics and proofs are tree-local, never merged across transpositions. Only
detached transition batches may share a cache. Each iteration descends existing
children and expands at most one new child, then starts its rollout there.
An accepted newly reached tree node counts as one real terminal simulation and
may seed a proof. A previously exact node returns an exact proof without a new
terminal simulation. Each completed iteration has exactly one of those two
outcomes: completed iterations = terminal simulations + exact proof returns.
Record aborted and unused iterations separately, with no double counting.

An already accepted root returns explicit `already-terminal`, no action, zero
iterations, and no invented actor/objective-seat reward. Validate its terminal
schema/score without calling it a simulated decision or admission success.

## Sound exact propagation

Only the terminal-proof arm propagates exact WDL values [-1,0,+1]. A tree node
becomes exact from its OWN accepted score or sound max/min bounds over its
COMPLETE legal child domain; unresolved children retain [-1,+1]. An extremal
child may prove a node value, but unknown root alternatives remain unknown.
Complete optimal-action sets require all root action values exact.

A terminal reached by a rollout does NOT prove its nonterminal starting leaf.
Never promote rollout means, structural facts, or local obligation proofs to
game values. No imported proof/local-solver value callback. Proof propagation,
proof statistical updates, and real terminal backups have distinct counters.
A proven root may stop early, record unused iterations, and choose a known
proven optimal child. It must not label unknown alternatives inferior. The other
two recipes never propagate exact values.

## Integrity, bounds, and telemetry

The generic core imports no engine, native evaluator, local proof, or corpus
module. Root and callback results are detached. Guard full fingerprints with
canonical snapshots/metadata against collisions, conserve seat identities,
validate accepted/actor schemas, exact integer scores, finite JSON, unique action
IDs, and callback/iterable mutation including exception paths. Repeated active
full states are integrity failures, not fabricated draws. Neither D6 corpus keys
nor legacy compatibility keys are valid analysis keys.

Reject malformed configuration before provider/source work: exact positive
integer simulations <=4096, exact integer seed, supported recipe/policy, exact
positive rollout_limit, and a finite deadline when supplied. Synthetic tests may
inject clock/cancellation. `rollout_limit` bounds TOTAL transition actions in an
iteration from decision root, including selected tree path and rollout; accepted
terminal is checked before exhausting the bound. Record tree and rollout actions
separately. Later real research freezes this at 20P, where P is immutable original
board points (vertices or lines), excluding zero-point junctions. Each placement,
construction, planted action, extension, pass, swap, acceptance, or resumption
counts as one transition. Static and dynamic controls use the same original P.
This is research-only; it changes no live termination.

Watchdog, deadline, or cancellation means incomplete with NO selected action,
even if earlier iterations completed. Preserve their counts but never invent a
backup. Provider contradiction, illegality, nonfinite data, or mutation raises
MCTSIntegrityError with detached partial telemetry and no action. Interrupted
wall-time traces need not be byte-equivalent; completed fixed-work semantic
results must be, regardless of worker order or checkpoint/resume.

Detached canonical telemetry includes requested/completed/aborted/unused
iterations, terminal simulations/backups, exact proof returns/propagations,
backup node updates, tree nodes, expansions, callback enumerations/transitions,
rollout lengths, root action visits/means/bounds/exposure, and root/provider/
recipe/agent hashes, status and reason. Adapter resolution/cache work is separately
reported. Machine timing never enters canonical hashes. Proof uses are not
misreported as simulated playouts. No limit manufactures an accepted terminal.

## Shared production transition cache and event facts

`SearchTransitionCache(rules_id, max_batches=2)` provides `.expand(state)`,
`.legal_actions(state)`, `.transition(state, wire)`, `.provider`, `.identity()`,
and `.counters`. Private bounded LRU, no global match cache or mutable escape.
Frozen SearchTransition exposes complete action/action ID, facts, and a detached
successor. All three recipes and both policies use the same cache/fact layer.

Lab10 reuses `engine.lab_actions.legal_transitions` once per batch. Legacy6
enumerates `actions.legal_actions` once, then applies only captured domain members
with `validate=False`; engine transitions remain legality authority. No per-action
rescans or duplicated scoring/capture logic. Count internal legacy enumeration
resolution-work limitations separately from explicit candidate applications.
Mechanical tests compare all transitions with the frozen production provider.

Cache keys contain provider full fingerprint plus canonical snapshot collision
guard: actual geometry, full forbidden history/journal, initial seed/topology,
seats, phases, and capture prefix. Key once per expansion batch; deep isolation
includes legacy mutable Board. Source identity includes the new adapter/facts
and actual fixed rules/actions/cache dependencies. Check import baseline and
decision entry/exit; charged workers also validate source bytes. Full origin
replay is a decision-boundary task, not a per-rollout callback. Frozen certificate
providers remain unchanged.

Capture facts count enemy color-mass decrease per column, not covers or changes
of top control, split original points versus zero-point hubs. Administrative
actions have zero capture/defense/fence facts to avoid pie-color artifacts.
Initially threatened friendly groups have exactly one ordinary liberty and no
strict sky. A one-transition defense retains control of every old group point
and gains >1 ordinary liberties or a strict sky. This is not reply durability.
`completed_cells` means POSITIVE NET actor-owned cell-count gain for Gjerde and
Gjerde-Go, and positive net threshold-four cell-count gain for Majority; it does
not claim a per-cell durability proof. Line-breath cell count is always zero.
No generic area/control increase is called fence completion. Extension/closure
is flagged for actual extend and finish-extension actions. Before-context once
per batch, after-facts from retained successors, no nested legal scans or
center/rim/learned evaluator weights.

## Verification and continuation

Synthetic tests cover all three recipes/both policies, seat/pie/consecutive turns,
resumption, complete-history domains, oriented IDs, enumeration order invariance,
equivalent/unknown/mixed proof bounds, sacrifice, rollout-not-proof, honest counts,
root stopping, watchdog/cancel/deadline, malformed callbacks/generator mutation,
collisions, exposure/overflow/eventual expansion, and common-prefix parity.
Mechanical cache/fact tests cover all16 definitions/n3..6 and constructed capture,
sky, cover, fence, hub, rescue and history isolation. No actual-game MCTS or
terminal proof is called by these engineering tests.

Synthetic worker tests use existing fixed-task/supervisor controls and disposable
ledgers for 1/2/8-worker completed-result equivalence, out-of-order completion,
cancel/resume, source/recipe/manifest tamper, and prior error accounting. Use
comfortable startup allowances; dedicated timeout tests and research caps stay
unchanged. Run full738+suite, scoped Ruff, compileall, both JavaScript syntax
checks, protected hashes, independent review, exact-tip CI.

Then continue trusted real proof-job integration and the predeclared 32-task
charged bootstrap. No real research in5E and no final stop at its checkpoint.
