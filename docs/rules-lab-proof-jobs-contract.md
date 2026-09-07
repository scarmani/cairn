# Trusted proof jobs and charged bootstrap, revision 0.1

Batch 5F contract, prepared on pushed source
`7f882f27edd11a7e2192b18f62c911f7de6e2b04`, before candidate implementation.
The 811-test local suite and independent 5E review pass. Both exact-tip CI checks
must pass before code implementation. The plan, rules, corpus, proof semantics,
three MCTS recipes, admission gates, and research budget remain unchanged.

The one bounded advisory `20260907T083606Z` completed through CLI fallback
`claude-opus-4-8` in 188.4 seconds. Its useful recommendation is this integration
unit. Its contradictory production-certificate/oracle-check instruction is
rejected: each mechanics path produces and checks its own certificate; only
semantic action-value claims are compared across paths. No second consultation.

## Scope, reuse, and ownership

Add `research/harness/lab_proof_jobs.py` for pinned corpus input and immutable job
manifests; `lab_proof_task.py` for actual trusted proof execution and external
receipts; and a repository-relative `lab_research_cli.py` for prepare/run/status/
audit operations. Add focused and independent synthetic integration tests.
Use the existing public origin, provider, producer, checker, fixed-task,
supervisor, and budget APIs. Do not copy their traversal or process supervision.

Root owns CLI, this contract, full verification, run documentation, and closure.
lab_budget owns job specifications/manifests and their tests. lab_compatibility
owns proof-task execution/artifact persistence and its tests. lab_plan_review owns
independent synthetic invariants and read-only cumulative review. Agree public
schemas before cross-module implementation. No further provider calls by agents.

All prior source, tests, historical evidence, and contracts remain byte-identical.
Do not edit live games, `engine/varde.py`, server/browser behavior, saves, Personal
models, CI workflows, or PRs 20–22. No new PR or rollback tag. No merge.

Engineering tests use synthetic finite graphs and disposable external accounting
only. Short mechanical replay validation may use frozen authored origins, but
actual-game proof/search/certification is prohibited until review and exact-tip CI
close. Test logs must distinguish synthetic orchestration from real research.

## Corpus trust and immutable tasks

The authoritative candidate corpus was fully regenerated in 5D. Preserve:

- External raw SHA-256:
  `d1dc7d7bd23b036862ddcffe9915fb5b7932147c838f93c4ef29fea9e255f7fc`.
- Semantic manifest hash:
  `e6331d93f1a2cf887eedc8c7c95f01585808cdc7a09b0b903433d765da9b64b8`.
- Tracked compact-index SHA-256:
  `5b0cedefb4b8ced6ce8786ac5cb197b79d8c9c76117a8eccc5e59eeb8c123561`.

The external input path is an explicit trusted CLI argument. Verify these fixed
physical and semantic pins, strict schema, compact-index correspondence, and
actual authoritative source bytes. Never execute import targets, commands, or
paths found in corpus or task data. A hash-verified historical corpus can be read
without rerunning all 512 origins for every manifest; each selected origin is
replayed afresh inside its charged task. Do not silently treat structure-only
parsing as new mechanical or terminal certification.

Manifests bind the actual committed source tip, closed dependency hashes, corpus
and selected-row identities, full origin data, exact limits, and fixed task order.
Prepare rejects source drift. Run/resume reject source or manifest drift before
dispatch, and callbacks verify sources at entry and exit, including failures.
Runtime output-directory configuration comes from the trusted coordinator, not
an executable manifest. Machine paths and timings do not enter semantic results.

Bootstrap order is sizes n3 then n4, each in the frozen 16-ruleset provider order.
For each cell choose the lexicographically first eligible development candidate.
Exactly 32 task slots, including explicit missing slots if a cell has none.
No holdout, substitutions, adaptive ordering, or outcome-dependent retries.
The pure selector may accept synthetic indexed rows in tests; production callers
must pass the authenticated frozen corpus. Missing rows are not certificates.

Support subsequent predeclared fixed certification manifests without executing
them in this engineering unit. Complete candidate order remains round-robin by
frozen ruleset order, collectively across sizes/splits, never sorted by outcomes.
Full producer/checker caps may not exceed 10,000 nodes. Corpus candidates and
split membership never change based on certification success or runtime.

## Per-task execution and proof meaning

1. Validate exact task schema/types and row/origin/source identities. Freshly
   `verify_origin` from the explicit original configuration and full action trail.
   Compare its receipt, root fingerprint, actor/seat state, and complete root
   legal domain against the frozen row. No imported continuation or added history.
2. Bind the production provider to the verified production root. Independently
   bind the oracle provider/root where supported. Each exact-root provenance
   attestation stays specific to that root and source bundle.
3. For the production path call `produce_certificate`, then `check_certificate`
   on the production root/provider. Separately repeat both operations on the
   independent root/provider. Do not use the production cache as checker truth.
   A production certificate must never be supplied to the oracle provider.
4. Preserve complete producer and checker canonical artifacts, separate work
   counters, provider identities, explicit unknowns, and machine timings.
   Resource exhaustion is unverified/unknown, not a false proof or a score.
5. Compare checked claims in semantic action-ID space and original-seat WDL.
   When both reports are verified, contradictory root bounds or overlapping
   action claims with disjoint WDL bounds are an integrity failure. Complete
   classification requires identical legal domains, exact values for every root
   action, and identical equivalent optimal sets on both mechanics paths.
6. Only a nonterminal decision with at least two legal actions, verified full
   origin, and complete independently agreeing classification can be marked
   `independently_certified`. This is candidate certification, never MCTS
   admission or game quality. A partial exact root is insufficient. Legacy six
   remain `unqualified-shared-mechanics` even when production results are exact.

No forced pass, extra search ordering, local tactical goals, nonterminal values,
or guessed continuations are introduced. Task node caps bound each mechanics
path independently. Supervisor hard deadlines remain external operational stops;
missing task results stay incomplete. No deadline becomes a terminal score.

## Artifacts, deterministic results, and accounting

Large proofs live outside the repository as atomically written content-addressed
canonical JSON. Flush/fsync and immutable same-content reuse; mismatching existing
content fails closed. Returned compact references include relative content ID,
byte length, and SHA-256. The trusted local artifact store validates containment
and never resolves a manifest-provided executable/source path.

Keep timing/CPU/attempt identities in separate operational records, not in proof
or semantic-result hashes. Completed canonical results and artifact bytes must
match across worker counts and reconciled checkpoint/resume. A proof file left by
a killed worker is an orphan/partial stage, not a completed job or corpus label.
Audit all referenced artifacts before reporting successful completion or resume;
missing/corrupt receipts fail closed without automatic proof reruns.

Actual task replay, proof, checking, result persistence, failure handling, and
owned cleanup/observation are charged through `run_supervised` and ResearchBudget.
Preparation only authenticates frozen bytes and fixes tasks; it does not perform
real proof or throughput measurements. No unofficial calibration before launch.
Only one explicit official ledger is used; never reset it or create a fresh
allowance on resume. Foreign sessions and interrupted cohorts need the existing
explicit reconciliation. Integrity/callback failures are not automatically retried.

The CLI is inert without an explicit command. Prepare writes manifests only to
an explicit external output directory. Run requires explicit ledger/session/job
identity and validates the reviewed source commit. Status reports both accounting
and incomplete work. Audit reads proof references and exact canonical hashes,
never upgrades the admission status based merely on a job's successful exit.

## Frozen bootstrap and subsequent gate

After this unit's full verification, independent review, push, and exact-tip CI:

- 32 fixed tasks, up to 8 workers, 20 seconds per task.
- 32 producer nodes and 128 checker nodes per mechanics path.
- 120-second cohort hard cap including cleanup and observation.
- Reserve 156 seconds of window/total capacity (120 × 1.30).
- Charge every task attempt and preserve timeouts, unknowns, failures, and missing
  tasks. A timeout stops the cohort as the existing supervisor specifies; it does
  not authorize replacing tasks or claiming that all 32 slots ran.

This is a declared hard resource reservation, not a measured-throughput claim.
Subsequent projections must use measured comparable work with 30% safety; never
extrapolate wide full proofs from cheap administrative endings. No MCTS recipe
or comparative game may run without its frozen certification/admission gates.

## Verification and continuation

Test strict pins/types/schema, source and artifact tampering, worker-boundary
origin/source checks, dual-provider isolation, incompatible certificates, exact
equivalent sets versus unknowns, contradictory checked values, missing providers,
node caps, immutable artifacts, timing exclusion, process ordering on 1/2/8
workers, explicit cancellation/resume, and truthful partial accounting. All
proof/search tests in this unit are synthetic; preserve all first failures.

Run the full 811+ product suite with zero added skips, scoped Ruff, compileall,
both JavaScript syntax checks, protected hashes, independent review, and CI.
Commit specific files and push; immediately reread guide/hash/feedback and close
the exact-tip gate. Then continue into the charged bootstrap and remaining
Batch 5/6 work. An internal engineering checkpoint is not a final stop.
