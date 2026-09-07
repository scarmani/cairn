# Rules Laboratory execution log

## Run digest

- Phase: launched, Batches1–3 complete locally; Batch3 closure push/CI next.
- Base: `b620a11a72097f22e5addbfaf58b56073f9612cd`.
- Branch: `codex/rules-lab-v1`; draft PR #23.
- Next: browser/API, provisional opponents and mechanical oracle; three batches remain.
- Active research: none; charged time 0/129,600 seconds.
- Report: staging preflight markdown/artifact hashes and local checkpoint HTML at
  `/tmp/elves-report-varde-rules-lab-v1-checkpoint-2026-09-06.html`; no research results.

## Batch 3 closure: 2026-09-06

Delivered all four junction games and three static controls through the explicit
factory. Unit B adds atomic planted Y and empty opposite-pair passages using
existing immutable geometry and capture-first resolution. Empty-build and planted
capabilities are distinct; journals/counters/repetition contain only actual final
rules states. Hubs persist and can be reoccupied after capture, never score a point.

Verification:386 tests pass in64.481s, zero skips (363 prior +23 additive in unitB;
46 new tests across Batch3). Full legacy fixture parity remains exact. The7 root
planted integration tests and independent off-center fixture failed before the
missing constructors were implemented. Final scoped production/atomicity review,
independent18-test mechanics review and16-test integration review are clean.
Ruff, Python compilation, JS syntax and whitespace checks pass. Reference engine,
legacy opponent, server and browser remain byte-unchanged from approved base.

Raw full-suite log `batch-3b-tests.log`, SHA256
`87218b8e86e6bf3f59b488666133fb03132bc1cb778a514bbfdc9cffd205a781`.
No browser feature was exposed in this batch; the unchanged public path retains
the inspected Batch2 browser baseline. Actual new-lab browser interactions belong
to Batch4, not claimed verified here. Specs/engine docs now distinguish implemented
mechanics from unmeasured search admission. No research seconds charged.

Regression confidence HIGH: isolated lab paths, legal replay/symmetry/atomicity
fixtures, exact old behavior, fullsuite and independent review. UnitA checkpoint
3c4f151 is pushed with both CI checks green. Close this UnitB push/check loop and
continue Batch4 without stopping or merging. The unrelated #10010 task released
Claude capacity; no active advisory/research/server process belongs to this run.

## Batch 3 unit B contract: 2026-09-06

Implementation review update: planted/passage thin path and16 root integration
tests pass. A new Full Passage subcase exposed an invalid permanent-interning
assumption in the old pickle test:267 candidate graphs may evict the current
geometry from boundedLRU256. Kept the exact warm-cache identity assertion and
added post-scan canonical/neighbor equality plus an explicit eviction round trip.
Independent reviewer confirms no geometry defect or weakened clone/save contract;
rerun16tests passed1.29s. Final mechanics/full regression closure remains pending.

Bounded advisory succeeded in336.5s via CLI fallback claude-opus-4-8; receipt
`.aragora/goal_cycles/20260907T022500Z/`. Sanity-checked against live3c4f151:
keep existing geometry, add only missing LabGame capabilities and tests. Use the
repo's actual unittest/CI commands, not advisory pytest wording. Prove the
no-immediate-capture consequence in invariant tests; do not replace real Go
resolution with an asserted rule or add a separate action generator. Advisory
language about a checkpoint does not authorize stopping. Process tree absent;
Claude capacity released to task019f2b0a pending its own terminal release.

Unit A is pushed at3c4f15193c2b71c97c8be9fe154521924819fb2d. Both exact-tip
CI checks pass (1m46s,2m45s), no new PR feedback. Full compatibility verification
rerun returns the identical103-position/218-decision/24-save content hash.
SDK capacity released explicitly; the Unit B advisory is the only active local
advisory process and remains bounded. A subsequent unrelated task requests the
capacity afterward; finish this advisory then release, with no further Claude
launch until it releases. No engineering or research authorization is transferred.

Behaviors: planted Y creates topology and its stone as one atomic legal action;
passages create empty centers with one of three opposite-pair orientations.
One plant increments moves, placements and constructions each once, records only
the occupied final repetition signature, and produces one plant journal event.
Adding a planted hub cannot remove old enemy liberties; legal positions therefore
permit no immediate enemy capture from planting alone. Normal later captures
retain the hub and spokes. Neither construction type can open the game.

Build on: existing LabGame graph preparation/commit, immutable GraphBoard and
shared RulesAction parsing/replay. Use the existing capture-first flat resolver;
separate empty-build capability from all topology-changing rules so planted
games never expose empty construction. No new resolver or legacy path rewrite.

Acceptance: test-first legal sequences for friendly merging through occupied
neighbors, enemy atari preservation, suicide/orientation filtering, later capture
and reoccupation, off-center face-versus-point IDs, all rotations/reflections,
strict journal/counter/history validation, complete-seat ending replay, all sizes,
zero mutation on failure and exact legacy parity. Full suite, scoped independent
review, Ruff/syntax and exact-tip CI before completing Batch3.

Blast radius: lab_game.py and additive lab tests only; factory/actions already
support structured plant actions. No browser/server/reference engine, learning
model or historical evidence changes. Baseline363 tests, zero skips. No proof,
calibration or research games in this unit; research charge remains zero.

## Batch 3 unit A checkpoint: 2026-09-06

Y/six construction and all three static controls now use the immutable graph
factory with capture-first Go, original-vertex opening/scoring, permanent neutral
topology, substantive construction counters, and topology-width-aware historical
replay. Legal short sequences demonstrate added/shared liberties, occupied-hub
merging, capture reopening, suicide rejection, and spatial/color symmetry.
Both save identifiers, pie seats, separate ending acceptances and resumption pass.

Three scoped independent implementation/mechanics/integration reviews report no
remaining blockers. Test-first integration cases failed before implementation;
all 363 tests now pass in64.829s, zero skips (340 prior +23 additive). Changed-file
Ruff, compilation, JS syntax, whitespace and frozen legacy parity pass. Reference
engine/server/browser remain unchanged; browser exposure is still Batch 4.

Clone isolation allowed immutable history tuples to be shared rather than deeply
copied. Engineering Full-board 12-placement clone microbenchmark improved from
1.07672041 to0.01698750ms (best of three 100-clone repeats). This is not a search
performance or strength measurement. Journal dictionaries remain independently copied.

Raw test log outside git: `batch-3a-tests.log`, SHA256
`df287042aadb0629266becf1d88fa2f34df0db3d2f83cbe38d4761d22195a6ed`.
Research charged0/129600s. No research/server/advisory process belongs to this run.
SDK task019f807d currently holds Claude capacity; honor its explicit release
before the next bounded advisory. Local checkpoint closure is unblocked.

Confidence HIGH for this engine unit: legal replay fixtures, strict save tamper
tests, complete legacy parity, full suite and independent review. Planted/passage
remain unimplemented; Batch 3 is not complete. Push/check this internal checkpoint
and continue, without changing the plan, launching research or merging.

## Batch 3 contract and ordered units: 2026-09-06

Batch 2 tip `3a2eb58730d24e771dda0c5669ef47dd107f3898` is pushed; both CI tests
pass (1m45s,2m40s), plan hash unchanged, no review blockers. Rollback tag
`elves/rules-lab-v1/pre-batch-3` created at this tip. Bounded advisory succeeded
in181.5s via CLI `claude-opus-4-8`, `.aragora/goal_cycles/20260907T020236Z/`.
Use its Y/six-first unit followed by planted/passage, as ordered in the plan.
Each internal checkpoint validates/reviews/pushes but does not complete Batch 3
or permit stopping. Four batches still require completion.

Behaviors: neutral permanent graph construction, first original-vertex opening,
capture-first Go, all orientations, static seeded controls, original-only area,
topology-aware full journal/history, legal pie/pass/resumption/acceptance.
Build on: immutable graph factory, shared RulesAction, isolated LabGame and v2
journal loader. No browser/server changes until Batch 4. No new rule/revision.
Acceptance: explicit short legal replay fixtures for added liberties, shared
liberty deduplication, merging, capture reopening, planted no-capture consequence,
suicide, original-only scoring, counters and topology persistence; save tamper
rejection, full parity, full tests, independent review and exact-tip CI.
Risk: historical graph widths and permanent orientation, scoring over zero-point
hubs, expensive cloning. Engineering clone microbenchmark found1.077ms per Full
12-placement snapshot due to recursively copying immutable history tuples;
shallow copying immutable members is permissible if alias-isolation tests remain.
No certification/calibration/research games launched: research charged0.

## Batch 2 closure: 2026-09-06

Delivered isolated `LabGame` for three scoring rules, explicit opt-in factory,
immutable cached graph geometry (stable coordinate IDs, all spoke families,
frozen static-Y initialization and pickle reconstruction), structured actions,
complete analysis keys and seat-aware research snapshot envelopes. Reference
engine, server and browser source remain byte-unchanged from approved base.

Version-2 saves include replayable journals as well as complete typed histories.
Loading certifies that legal replay reproduces the supplied state/history/counters;
omitted or invented forbidden entries are rejected. This closes the completeness
gap of unordered-history-only validation without changing legacy version-1 saves.

Independent review resolved impossible ending envelopes test-first: initial
decider must be the actual next color, first acceptance hands off once, and after
resumption exactly one acceptance by the authorized seat is terminal. Also
rejected mutable construction-face lists in otherwise frozen action objects.
Three independent scoped reviews now report no blockers.

Verification: 340 tests in 61.001 seconds, zero skips (299 prior +41 additive);
103 legacy positions, 218 seeded choices and 24 saves replay identically. Changed
Python Ruff, compileall, JS syntax and whitespace checks pass. No old product
tests changed. Construction's implementation status is not frozen as a permanent
invalid-ID test: the new test uses genuinely unsupported/legacy-only IDs.

The required web-game client verified isolated Classic startup, a real canvas
opening at (-2,0), and pie takeover. All three screenshots opened and semantic
states inspected; Black changes from player-1 to player-2 while White remains
to move and the board is unchanged. Zero console/page errors; port8773 server
stopped, disposable Personal path never trained or written. Artifact hashes are
in `docs/elves/rules-lab-v1-batch2-artifacts.json`.

Regression confidence HIGH: exact frozen parity plus full suite, branch-owned
additive modules, independent save/key/scoring reviews, and live browser check.
No research/proof/calibration jobs: charged time remains 0/129600 seconds.
No merge. Next is commit/push and exact-tip feedback/CI closure, then Batch 3.

## Batch 2 contract: 2026-09-06

Batch 1 pushed at `4af29e434a5eee6a5cb92ef8467297295e77dcd7`; both GitHub
test checks pass (2m03s and 2m40s), no new reviews/comments, plan hash unchanged.
Rollback tag: `elves/rules-lab-v1/pre-batch-2`.

Bounded advisory completed successfully in 514.5 seconds using the CLI fallback
`claude-opus-4-8`; receipt `.aragora/goal_cycles/20260907T013611Z/`. Accepted its
isolation-first sequencing and preservation checks. Its suggested foundation-only
unit is an internal step, not permission to omit Batch 2 scoring/saves or stop the
launched run. No plan/gate changes. Reviewer capacity explicitly released to the
separate Evergreen task; no further Claude/reviewer launch until its release.

Behaviors: three frozen scoring variants using existing Breath resolution;
strict revisioned version-2 game snapshots; immutable topology-keyed graph
geometry; opt-in game factory; history/seat/phase-complete analysis keys.
Build on: `lab_spec.py`, flat `resolve`, `groups_of`, board geometry, Game's pie
and ending semantics, and existing `RulesState`. Leave reference varde.py unchanged.
Acceptance: all scoring boundaries, group penalties, geometry n=3–6, clone/cache
isolation, strict save/history rejection, legacy v1 and seeded parity, full tests.
Blast radius: new lab modules plus additive shared action-interface capabilities;
server/browser remain unwired until Batch 4. Dynamic construction rules/actions
become playable only in Batch 3. Independent review targets save validation and
cache omissions. No research computation or comparative claims in this batch.

## Batch 1 closure: 2026-09-06

Delivered seven immutable revision-0.1 specifications and three static controls,
named hypotheses and concept inventories, typed evidence cards with strict human
observation and admission gates, an atomic locked three-window budget ledger,
and deterministic round-robin scheduling. Live engine/server/browser remain untouched.

Compatibility freeze: 103 reachable positions, 218 seeded Casual/Standard choices,
24 saves (six rulesets × n=3–6) replayed under both legacy format identifiers,
and 16 historical artifact digests. Fixture content hash:
`0797f216e00869ce6f3dbc5644f3367f89923904451657700a3a30bd57896dc6`.
Generation was guarded against the unchanged approved-base source hashes.

Independent reviews found and resolved four gaps test-first: machine evidence
could fill human-only fields, unmeasured cards could authorize shortlist membership,
malformed hashes/counters could pass schema validation, and saves covered only Toy.
Reviewers reran the affected tests and reported no remaining blockers.

Verification: 299 tests pass, zero skips (254 baseline +45 additive tests); changed
Python Ruff, compilation, JavaScript syntax and diff whitespace checks pass.
Raw final log: external `rules-lab-v1/batch-1-tests-final.log`. No old tests weakened.
Regression confidence HIGH for Batch 1 isolation: only additive modules/tests/docs,
plus this run's metadata. Six legacy products still behave identically.

One bounded Fable cycle succeeded in 123.0 seconds; receipt at
`.aragora/goal_cycles/20260907T011308Z/`. Namespaced rollback tag
`elves/rules-lab-v1/pre-batch-1` points to launch tip 31f9c23. Research charged 0;
no certification, calibration or match work launched. Commit/push and exact-tip CI
poll follow this closure; continuation remains mandatory. No merge authorized.

## Batch 1 launch contract: 2026-09-06

User explicitly launched the staged run. Verified clean owned tip 31f9c23 locally
and on PR23, both CI checks successful, unchanged plan hash, no new review request.
Continuation guard is active; staging pause no longer applies.

Behaviors: immutable seven-rule/three-control specification; evidence statuses
with provenance/uncertainty and no false zero ratings; legacy decision/save
compatibility corpus captured before shared changes; persistent bounded research
clock and deterministic allocation metadata. No research games/certification yet.
Build on: current registry/actions/Game serialization, native opponent API,
research manifest hashing and atomic checkpoint patterns. Preserve all old artifacts.
Acceptance: specs match the frozen plan, unknown/invalid definitions rejected,
historical source digests recorded, all parity fixtures replay exactly, budget
projection/overlap/restart/cancellation accounting tested, full suite remains green.
Blast radius: new lab modules/docs/tests/fixtures only; existing product consumers
unchanged. Shared wiring is deferred to Batch 2 after parity freeze. Risk low now,
high for later graph/actions integration. Baseline 254 tests, zero skips.

## Staging validation and review: 2026-09-06T23:29Z

Contract status: staging-only scope delivered; closure push/check poll still required
before final task handoff. Plan hash unchanged:
`71517f521ca4da1ab17acc817381e52f3f05e872700ece6ec96c9ae0a59dec6c`.

Verification: 254/254 unittest tests pass in 25.285 seconds (zero skipped), Python
compileall and JavaScript syntax exit 0, Ruff available (no changed Python to lint).
Both initial-tip GitHub test checks passed. No PR comments/reviews at initial poll.
Tooling-only browser failure: missing matching executable, repaired by installing
Chromium v1234. Installer removed v1228 cache automatically; record the
`PLAYWRIGHT_SKIP_BROWSER_GC=1` mitigation rather than repeating implicit cleanup.
The actual bundled-client smoke then verified startup, legal opening at (-1,1),
and pie takeover (player-2 becomes Black, player-1 White, move number unchanged).
Opened all three screenshots and inspected all three text states; no console/page
errors. Isolated server PID90760, port8769, disposable model path, exited cleanly.

Fable advisory: one bounded CLI goal cycle succeeded in 104.7 seconds. Accepted
staging-only sequence; discarded stale advice to require HEAD still equal base
after our own staging commit. No changed scope, duplicate commit/PR, or extra call.
Another local task requested temporary reviewer-capacity hold; no additional
consult was launched; the existing consult completed and capacity was later released.

Independent read-only reviewer found no blocking scope or safety issue at a065f6d.
Two pre-outcome clarifications were added to Batch 1 run controls: one global
recipe with equal per-ruleset development weighting followed by per-ruleset
holdout gates, and deterministic round-robin ruleset/control blocks. These resolve
operational ambiguity without editing the approved plan or changing any rule/gate.
Final independent closure review also found no blockers: all seven artifact hashes
match, test log confirms 254 passes, port8769 is closed, and final-tip CI is
explicitly not claimed before the push/check completes.

Regression attestation: seven initial additive run-control files, plus one compact
artifact index in closure; no engine, tests, browser, saves, model, or historical
research artifact changed. Shared product surfaces modified: zero consumers.
Baseline 254 tests; current 254, delta 0 removed/0 skipped. Confidence HIGH for
staging isolation because cumulative paths are documentation/session metadata
only and real baseline browser behavior was inspected, not merely syntax-tested.

Initial commit: `a065f6dbaa8a40a4dba8fb8f17553d234f8751a0`, pushed and draft PR23
opened immediately. No implementation tag yet; Batch 1 creates its namespaced
pre-batch tag on fresh launch. Total engineering/staging elapsed about 25 minutes;
research elapsed 0. Raw logs/screenshots/states and advisory copied outside git.
Run-state documents updated; old `progress.md` and historical Elves docs untouched.

Next: push closure docs, re-read survival guide, verify current PR checks/feedback,
then stop at the user's mandatory launch separation. No seven-variant deliverable
or comparative result is claimed complete.

## Session setup: 2026-09-06

Contract: stage the user-approved plan in an isolated worktree, publish a draft
PR, capture baseline/preflight, review controls, and stop before implementation.
Build on: Elves run templates, existing Python unittest/CI, action adapter,
rules registry, save compatibility, and deterministic research harness.
Blast radius: additive run documentation/session JSON only; no product surfaces.

Live survey: shared checkout remains clean on `codex/ruleset-evidence-run` at
`5bfea5e86977cd4a91ed8335ee97847bfda02545`; local and GitHub main both match the
approved base. New worktree `/Users/armand/Development/varde-rules-lab-v1` created
from that exact SHA. Old prunable worktree entries left untouched. GitHub auth
works. 347 GiB free; 16 physical cores; 128 GiB RAM. Use at most eight workers.

Protected research heads:

- PR20/v3: `315443366ddeb499d294f47221e89c2c1dbca4d7`.
- PR21/v4: `808c31720730fcf23bbc02c4549bd7151bdab3ec`.
- PR22/v5: `65df6469d46b375ef031625094a93569d73db468`.

All three remain draft/unmerged. No changes to their refs or historical files.
Install doctor: newer Elves v2.37.2 advertised; active v1.12.0 not updated.
No new global/app settings, automations, or Personal model changes.

Planned batches (engineering estimates exclude research; revise estimates from
measured work without changing scope or outcome-dependent task order):

1. Freeze rules/hypotheses/controls/compatibility/evidence definitions: 1–2 hours.
2. Three scoring variants and graph-aware foundation: 2–4 hours.
3. Y/six, then planted/passage: 2–4 hours.
4. Browser lab, replay/export, native opponents, mechanical oracle: 4–8 hours.
5. Freeze independent corpora and run MCTS: 2–4 hours tooling plus charged compute.
6. Conditional matches, cards, atlas, shortlist: 2–4 hours tooling plus remaining compute.

Research is three 12-hour elapsed windows total, not 36 hours per worker.
Proof certification is charged even if performed while engineering remains.
All hypotheses must be frozen before corresponding measurement. Comparative
matches are blocked per ruleset until its complete MCTS gate passes.

Staging acceptance remains open pending PR, test/syntax/browser preflight and
review. No product code or generated evidence has been changed. All seven new
variants remain unimplemented at this staging point.
