# Rules Laboratory evidence contract, revision 0.1

The approved plan is `docs/plans/rules-lab-v1.md`. This document makes the
measurement boundary explicit before outcomes. No result is asserted here.

## Layers that must not be conflated

1. Product tests establish the implementation's specified mechanical behavior.
2. An independent graph oracle checks that behavior without importing the
   production group/capture/scoring algorithms. Legal-transition differential
   tests may compare both implementations; oracle expectation generation must
   not call the production resolver and rename its answer a proof.
3. Bounded local obligations certify only a declared predicate and horizon.
   They report complete equivalent action sets or unknown on exhausted nodes.
4. Accepted-terminal minimax proofs certify game-score-optimal actions over
   all legal continuations in the declared complete scope. Only these label
   an MCTS decision as optimal/suboptimal. A rescue is not necessarily best.
5. Per-ruleset held-out search admission precedes comparative match evidence.
6. Human readability, beauty, replay demand and memorable understanding require
   actual human observations; machines cannot fill these evidence slots.

`engine/lab_evidence.py` defines seven independent card dimensions and explicit
statuses. `unmeasured` means null value and zero observations, not a zero rating.
All other statuses require provenance and an explicit uncertainty statement.
Human-only fields additionally require typed human-observation provenance and
a positive observation count; computer samples cannot authorize them.
An exact constructed mechanical assertion can have zero sampled games; report
its proof scope rather than pretending it came from a match sample.

## Freeze and qualification

- Frozen architecture IDs: `lab-uct-0.1`, `lab-reserved-0.1`,
  `lab-terminal-proof-0.1`. Complete recipe and implementation hashes belong in
  manifests. Local proof guidance is not part of any recipe.
- Both `uniform` and independently implemented `light` rollouts; accepted-terminal
  backups only. Exact solved game results have separate counters from simulations.
- Budgets 64/256/1024/2048; four deterministic replicates per position/policy.
- At least eight independently certified positions in each hash-disjoint split
  per ruleset, including distinctive and administrative choices. Duplicate or
  symmetry-equivalent copies do not manufacture eight independent positions.
- Freeze certification-complete eligibility before candidate testing. Missing
  certification stays visible and blocks that ruleset; never fabricate forbidden
  histories or exclude inconvenient recipe outcomes.
- One global recipe: equal ruleset-weighted development high-rung admission,
  then measured latency, then recipe ID. Holdout qualification is separate for
  each ruleset and requires both policies, pooled 80%, cell floor 3/4, monotonic
  last two rungs, and zero integrity failures.
- Optional 4096 is conditional on admitted 2048 missing stability versus 1024
  (85% top action or 0.80 top-three Jaccard) and a measured budget fit.
- No tuning after holdout. Preserve rejected recipes and incomplete task blocks.

## Quantities and uncertainty

Keep rules actions, stone placements, constructions, original scoreable vertices,
active graph vertices, objective score, occupied area and surviving stones in
separate fields. Construction is not a stone placement except for planted hubs,
which increment both counters. A pass is a rules action, not a placement.

Win/draw/loss comparisons are within a ruleset and revision, with original seat
and post-pie color recorded separately. Do not pool games with different score
units, agent qualification, rules revisions, or development/held-out seeds.
Use paired resampling by seed (both color games remain together) for uncertainty.
At least 100 completed admitted-agent games precede any comparative headline;
this sample floor alone is never sufficient qualification.

No single aggregate beauty score or cross-ruleset Elo. The shortlist reports
nondominated tradeoffs among admitted depth evidence, exploit resistance, closure
and rule economy, and can be empty. Design-priority hypotheses are separately
labeled provisional when match evidence is absent.

## Compute and artifact integrity

`research/harness/lab_budget.py` owns the research-only external ledger. Product
tests use simulated clocks. Certification, calibration, incomplete/failed/cancelled
research and games consume the union of active-job elapsed wall intervals, up to
three resumable 12-hour windows. Record worker CPU separately; never multiply
the allowance by worker count. No cohort starts unless measured projection ×1.30
fits both the current window and total remainder. Use at most eight workers.

Task IDs, seed derivation and round-robin blocks are fixed independent of results.
Canonical semantic records exclude machine timing; timings live in linked sidecars.
Resume validates manifests/source/rules/agent hashes before reusing results.
Incompletes and illegal/crashed/cancelled work receive explicit accounting, not
imputed game scores. A shared integrity failure blocks all dependent research.

Raw outputs live outside the repository. Commit compact manifests, summaries,
counterexamples and hash links. Preserve all historical artifacts byte-for-byte.

## Shared-surface survey before wiring

At the launch base, 145 import/constructor reference lines occur in the engine
directory alone, across tests, server, opponents, training and native/MCTS.
Research harnesses add further consumers. Batch 1 adds modules only.
Before Batch 2/4 wiring, enumerate exact callers again and distinguish product
factory consumers from legacy fixture generators; never blindly replace every
`Game(...)` in historical research or tests.

The production Board is shared by Game clones. Only immutable canonical topology
snapshots may be shared by graph games. Existing version-1 saves remain governed
by the legacy loader; new version-2 lab snapshots require explicit validation and
full topology/history preservation. Legacy seeded decisions are frozen before
any shared action/factory changes in `research/fixtures/rules-lab-legacy-v1.json`.
