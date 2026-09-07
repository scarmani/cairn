# Rules Laboratory proof-job runner

Research-only integration for draft PR23. The laboratory browser remains usable
with its provisional native opponents; this runner never touches the displayed
match or a Personal model. It does not expose research MCTS as a public difficulty.

## What the runner establishes

The pinned 5D corpus contains 512 authored origins, of which 476 passed structural
screening. Those counts are not terminal certificates. This runner authenticates
the historical corpus without replaying all origins during job preparation, then
freshly replays each selected origin inside a supervised, charged task.

Production and independent mechanics each produce and check their own certificate.
Only complete, agreeing per-action WDL classifications can certify a candidate.
Equivalent winning actions remain equivalent regardless of their score margins.
Partial proofs, incomplete checks, and operational timeouts remain explicit.
The six legacy mechanics retain their documented independence limitation.

Every large proof/check artifact is immutable, content-addressed canonical JSON
outside the repository. Compact task results bind those references to the exact
origin, task, corpus, and source hashes. Resume audits referenced files before
trusting completed checkpoint records. Timing and CPU records are separate from
canonical semantic results. A file left by a killed task is not a completion.

The generic supervisor reports its limited source-verification scope unchanged;
the CLI separately records its additional committed-source verification. Neither
layer claims MCTS admission or game quality from an operationally successful run.

## Commands and safety boundaries

Run from this repository, or invoke the script by absolute path. All output and
ledger paths must be explicitly outside the repository. Preparation requires a
committed, source-clean implementation; unrelated later documentation commits do
not invalidate an unchanged source ancestor.

```sh
python3 -m research.harness.lab_research_cli --help
python3 -m research.harness.lab_research_cli prepare \
  --stage bootstrap --corpus /absolute/path/batch-5d-corpus.json \
  --output-dir /absolute/path/bootstrap
python3 -m research.harness.lab_research_cli init-budget \
  --ledger /absolute/path/research-budget.json --session UNIQUE_COORDINATOR_ID
python3 -m research.harness.lab_research_cli run \
  --manifest /absolute/path/bootstrap/manifest.json \
  --output-dir /absolute/path/bootstrap \
  --ledger /absolute/path/research-budget.json \
  --session UNIQUE_COORDINATOR_ID --job UNIQUE_JOB_ID
python3 -m research.harness.lab_research_cli audit \
  --manifest /absolute/path/bootstrap/manifest.json \
  --output-dir /absolute/path/bootstrap
python3 -m research.harness.lab_research_cli status \
  --ledger /absolute/path/research-budget.json --session UNIQUE_COORDINATOR_ID
```

The commands above are instructions, not a launch receipt. `init-budget` refuses
to reset an existing ledger. Reuse the same ledger across all permitted windows.
Each coordinator lifetime and supervised job has a fresh identity. Existing
checkpoints require `--resume`; interruptions additionally require an explicit
`--reconcile-json` receipt naming every pending attempt nonce and affected job ID,
the stopped-worker evidence, and its reason. Integrity failures never auto-retry.
SIGINT/SIGTERM request bounded supervisor cancellation and owned cleanup.

The first bootstrap is fixed at 32 development slots, in n3 then n4/frozen-ruleset
order, with 32 producer and 128 checker nodes per mechanics path, eight workers,
20 seconds for the entire task, and a 120-second cohort including cleanup. Budget
admission requires 156 seconds of available capacity. This is a declared hard
reservation, not a throughput estimate. One task timeout stops the cohort; missing
slots are preserved and do not silently become completed samples.

`prepare --stage certification` can freeze the complete candidate task manifest.
Its outer order cycles through all frozen rulesets. Within each ruleset, it
interleaves the n3-development, n3-holdout, n4-development, and n4-holdout buckets
by candidate ordinal; each bucket is sorted by fixed ID. This ordering was
declared before any proof outcome to distribute bounded work across strata.
Actual full-certification execution requires a subsequent measured cohort freeze;
this version of `run` refuses to invent those runtime limits. The frozen 10,000-node
ceiling and the 36-hour, at-most-eight-worker research allowance remain unchanged.
Comparative matches remain blocked until each ruleset's MCTS admission gate passes.

## Verification and current evidence

Engineering verification passed: 886 tests in 311.219 seconds, zero skips,
75 additive tests. Scoped Ruff, Python compilation, both JavaScript syntax checks,
and whitespace checks passed. Independent code/test review is clean. Synthetic
worker tests reproduce canonical results and artifact bytes with one, two, and
eight workers, including explicit cancellation reconciliation and resume.

New tests use synthetic finite graphs, mechanical schema checks, and disposable
accounting ledgers. Preserved negative tests include contradictory action values
in resealed checker reports: audit now binds those claims to the unchanged stored
certificate without rerunning its proof. Full-suite logs, focused logs, and the
explicitly labeled reviewer/owner tool-output transcriptions are hash-linked in
`docs/elves/rules-lab-v1-batch5f-artifacts.json`.

No actual-game proof, new laboratory MCTS run, or official research window has
been launched by this integration unit. Exact-tip CI follows publication; the
separate survival guide records that closure and any later charged launch.
Do not infer launch or admission from these engineering tests or commands.

The frozen implementation contract is
`docs/rules-lab-proof-jobs-contract.md`. Historical corpus, rules, proof interfaces,
MCTS recipes, production behavior, and PRs20–22 remain unchanged.
