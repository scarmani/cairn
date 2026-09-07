# Provisional laboratory opponent, revision 0.1

Recipe: `lab-native-objective-v1`. Frozen before implementation or browser
exposure. These are objective-aware Casual/Standard UI opponents, not admitted
comparative research agents. No strength or game-quality claim is attached.
The legacy evaluator modules, weights, hashes and Personal model are unchanged.

## Evaluation

Let P be the number of original playing points (lines for both line games), and
C the number of original cells for Majority. Every feature is a color
differential, evaluated from the original acting seat's current color.

| Named term | Weight | Definition |
| --- | ---: | --- |
| occupied_objective | 1.00 | Original occupied-point differential / P, except Majority. |
| late_empty_area | 1.00 | Empty-region objective differential / P, enabled at original occupancy ≥ 0.55P; no line-area substitution for Majority. |
| connection_group_tax | -1.00 | Friendly-minus-enemy surviving group count / P, Breath Connection only, including early play. |
| majority_owned | 1.00 | Owned-cell differential / C, Majority only. |
| majority_three_edges | 0.10 | Differential of cells with exactly three own edges and at least one empty edge / C. |
| majority_line_control | 0.10 | Original controlled-line differential / P, Majority only. |
| liberty_health | 0.20 | Per group, original-stone mass × min(distinct liberties, 3)/3, summed differentially / P. This is not a per-group reward. |
| vulnerable_mass | -1.50 | Original-stone mass in one-liberty groups, differential / P. |
| capture_transition | 0.50 | Captured stones / P, applied with the capturing seat's sign; telemetry distinguishes original stones and zero-point junctions. |

There is no center-development, rim, generic construction, sky, style or learned
bonus. Empty construction must earn value through its actual consequences.
Zero-point hubs do not add occupied-objective or liberty-health mass, although
their adjacency can protect original stones. Capturing a hub has a transition
bonus, but never becomes a scored vertex or original-stone capture in telemetry.

Only an accepted terminal receives terminal evaluation:
`10 × sign(score margin) + score margin / scoreable area`, where the denominator
is C for Majority and P otherwise. Pending two-pass endings remain nonterminal.
This static-search evaluator is not a value function for MCTS backups.

## Search and identity

- Casual evaluates every legal action once, then chooses reproducibly among the
  best eight within 0.20/P of the best value using semantic seeded ties.
- Standard evaluates every legal root, then searches all legal replies for the
  best ten substantive candidates plus legal administrative candidates. Reply
  scans include pass and takeover irrespective of the root passing preference.
- At every descendant, recover the original actor's color from seat identity.
  Max/min follows acting identity, not fixed color or depth parity. Takeover is
  a real transition, not a negation shortcut.
- At an ending, the acting seat resumes if behind and legally permitted;
  otherwise it accepts. The other seat still receives its rules decision.
- Root pass is eligible if no substantive action is legal; or placements ≥ P
  and the best substantive one-ply improvement is at most 0.10/P; or the opponent
  passed and the actual objective score is not behind. This is an AI preference,
  not a live-game cutoff. Replies always retain legal passes.

## Shared transitions and public decision

Syntactic candidates cover active empty points, legal turn-phase administration,
and unused face/orientation construction capabilities. Resolve each candidate
exactly once through the real action adapter with validation disabled only because
candidate application itself checks the engine's legality. Do not enumerate legal
placements before resolving them again. Verify action-set parity independently.

A decision-local bounded transition cache includes complete analysis state and
journal identity. Cached mutable successors never escape without cloning.
Immutable geometry may be shared; forbidden history, seats and journals may not be
cross-contaminated. Event facts reuse generated before/after transitions and never
start nested move scans. Cache evictions affect performance, not choices.

Concrete interface: `legal_transitions(state, cache=None)` returns frozen
`LegalTransition` objects exposing `action`, frozen capture facts (original,
junction and total), and `successor()` which returns a fresh `RulesState` clone.
`TransitionCache(max_batches=2)` is a decision-local LRU with transition-attempt,
legal-transition and cache-hit counters. Its key combines `analysis_key()`, the
frozen complete action journal, topology seed and initial topology. Build that
key once per expanded node, not per candidate or static leaf evaluation.

`choose_lab_decision(state, difficulty, seed)` returns an immutable `LabDecision`
with a structured `RulesAction`, reason code/text, transition/node count, cache
statistics, elapsed milliseconds, recipe/hash and `provisional: true`. Its public
dictionary flattens the shared action wire object and excludes evaluator values
and raw weights. The server analyzes a clone and commits only the selected action
through `apply_lab_action`; it never adopts a cached successor or its journal.

`lab_native_public()` reports provisional status, revision, recipe, agent hash and
Casual/Standard support. Non-null Classic/Personal profiles and Advanced/MCTS
difficulty requests remain rejected for laboratory matches.

## Verification boundary

Test all seven games and three static controls, every board size, immutable
cache ownership, final-only planting history, superko, seeded ties, captures,
sole-liberty defense, scoring objectives, both pie identities, pass replies,
both ending decisions, resumption and strict save continuation. Replace the two
API-only unavailable-opponent assertions with successful legal execution while
retaining every original no-Classic/no-Personal isolation assertion. No old test
is skipped or removed. Mechanical oracle and browser lab remain separate units.
