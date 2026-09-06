# Rules Laboratory execution log

## Run digest

- Phase: staging complete, mandatory fresh-launch pause. No implementation batch completed.
- Base: `b620a11a72097f22e5addbfaf58b56073f9612cd`.
- Branch: `codex/rules-lab-v1`; draft PR #23.
- Next: fresh launch reads guide, verifies tip/CI/hash, and starts Batch 1.
- Active research: none; charged time 0/129,600 seconds.
- Report: staging preflight markdown/artifact hashes and local checkpoint HTML at
  `/tmp/elves-report-varde-rules-lab-v1-checkpoint-2026-09-06.html`; no research results.

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
