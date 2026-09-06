# READ THIS FILE FIRST AFTER ANY COMPACTION OR RESTART

## Mission

Implement the approved Rules Laboratory: seven independently frozen experimental
rulesets, playable browser support, honest evidence cards, and gated research
leading to at most three candidates. No human-beauty claims from machine metrics.

## Run Control

- Run mode: finite; staging now, separate launch required.
- Stop policy: staging gate, then plan completion, research-budget exhaustion,
  explicit user stop, or genuine blocker/integrity failure.
- User intent: "Use the Elves staging/launch separation" and "do not merge any PR."
- Checkpoint due by: none; no invented return time.
- Checkpoint semantics: 12-hour research windows are resumable boundaries; save
  and reconcile resources, then continue automatically to the next allowed window.
- May continue after checkpoint: yes, within three windows and 36 charged hours.
- Actual stop conditions: stop staging after preflight; after launch, continue
  all unblocked implementation and analysis, but never bypass admission or budgets.
- Workspace ownership: only `/Users/armand/Development/varde-rules-lab-v1` on
  `codex/rules-lab-v1`. Leave the shared `/Users/armand/Development/varde` untouched.
- Branch tip at start (collision tripwire): `b620a11a72097f22e5addbfaf58b56073f9612cd`.
  Record every own commit; an unexpected writer/tip stops the run.
- Merge policy: user-merges only. No merges, rebases, force pushes, or destructive cleanup.
- Final-response policy: allowed only at the recorded Stop Gate or genuine blocker.
- Every completed batch: update log/session/guide, commit specific files, push,
  re-read this guide, verify plan hash, poll all new PR feedback and checks.
- Never pause for surveys, feedback requests, or update prompts.
- No autonomous scout expansion beyond the approved research architectures/rules.

## Session Budget

Staged 2026-09-06. Engineering and product verification are separate from research.
Research: at most three resumable 43,200-second windows (129,600 seconds total),
maximum eight workers. Charge elapsed wall time for the union of active proof,
calibration, and research jobs, including failed/cancelled work; also record worker
CPU time. No parallel window multiplication. Persist start/stop timestamps so a
crash cannot reset the clock. Before a cohort, measured projection × 1.30 must fit
both the active window and total remainder. Do not launch a full cohort just to
cross a boundary. Persist completed fixed blocks and resume their exact manifest.

No research window has opened. Research charged: 0 / 129,600 seconds.
Six planned batches remain. Estimates are planning ranges, not launch guarantees.

## Stop Gate

- Planned batches remaining: 6.
- Stop allowed right now: no; finish staging preflight and PR review first.
- Why: the separate launch gate is not yet ready.
- Next required action: finish Batch 0 staging; do not implement Batch 1 now.

## Current Phase

Status: Staging. Active batch: 0, run controls and baseline verification.
Just completed: isolated worktree from verified main; approved plan saved.
Single next action: publish the draft PR and verify the baseline.

## Active Compute

No research, paid, or remote compute launched by this run. Temporary local
preflight commands must be logged and shut down before staging handoff.

## Non-Negotiables

- Preserve existing six candidates, public defaults, seeded decisions, saves,
  Personal model, and PRs #20–22 with historical evidence unchanged.
- Legacy saves remain version 1; new lab saves use version 2. Never silently
  reinterpret unsupported saves, profiles, history, or topology.
- Repetition signature is not an analysis key. Analysis must include complete
  forbidden history, seat identity, and administrative phase state.
- Neutral topology is immutable per snapshot; inactive centers are absent.
- No live cutoff or quiet-move rule for junction games; watchdogs are research-only.
- Local obligation proof is not optimal-move proof. Never fabricate history to
  hide legal alternatives; only accepted-terminal score certification labels optimality.
- No nonterminal heuristic backups; exact terminal proofs separately counted.
- Per-ruleset admitted MCTS precedes comparative screening. Missing evidence is
  unmeasured, not zero. Failed admission may exhaust the entire research budget.
- Stop dependent research on integrity failure. Preserve negative results.
- Do not weaken/delete/skip existing tests to manufacture green results.
- No paid compute, deployment, user-model writes, or PR merges.

## Next Exact Batch

After a fresh launch only: Batch 1, freeze specifications and compatibility.
Build on the registry in `engine/varde.py`, `engine/actions.py`, existing saves,
native/MCTS research interfaces, and `research/harness/evaluate_rulesets.py`.
First contract must inventory consumers and freeze baseline decisions before
touching shared surfaces. Create branch-namespaced rollback tags, e.g.
`elves/rules-lab-v1/pre-batch-1`; never overwrite other runs' tags.

Acceptance: seven revision-0.1 specs, controls, hypotheses/evidence statuses,
compatibility fixtures, protected-artifact hashes, independent oracle boundary,
and exact research-budget accounting agreed in code/docs/tests. No match claims.
Risk: preserving existing behavior while introducing graph and structured-action paths.

## Paths and Ownership

- Plan: `docs/plans/rules-lab-v1.md` (SHA-256 recorded in session JSON).
- Session: `.elves-session.json` (new dedicated run; do not reuse old run files).
- Learnings: `docs/elves/rules-lab-v1-learnings.md`.
- Execution log: `docs/elves/rules-lab-v1-execution-log.md`.
- Preflight: `docs/elves/rules-lab-v1-preflight.md`.
- Launch prompt: `docs/elves/rules-lab-v1-launch.md`.
- Raw artifacts: `/Users/armand/Development/varde-research/rules-lab-v1/`, outside git.
- PR: pending creation, base `main`; do not alter PR20–22.
- No constitution or `.ai-docs` manifest found at the verified base; recheck at launch.

## Tool Configuration and Review

Python stdlib engine/server; use `CI=true python3 -m unittest discover -s engine -v`.
Compile: `python3 -m compileall -q engine research`; JS: `node --check web/game.js`.
Lint: Ruff on changed Python files, not a pre-existing unrelated lint cleanup.
No configured standalone typecheck/build beyond syntax and tests; no deployment.
Browser: develop-web-game skill, bundled Playwright client, screenshots, rendered
text, exports and console review for actual changed interaction chains.
Use an isolated localhost server, never the user's displayed match or Personal model.
Review all PR feedback/checks after pushes. Elves requires independent read-only
review; include cumulative regression review for shared game/server/action changes.
Run one bounded Fable goal cycle per conductor decision; advice cannot change
frozen rules/gates. Fail-closed consult outage means no guessed approval/retry loop.
Notification: PR and current task only; no third-party channel configured.

## Launch Readiness

- [x] Plan and run documents saved; dedicated branch/worktree owned.
- [ ] Draft PR opened; branch push verified.
- [ ] Baseline tests/syntax/tooling/browser preflight recorded.
- [ ] Review and final-tip CI checked; critical failures cleared.
- [x] Fresh launch prompt prepared; 0 research time charged.

## Effort Standard

After launch, implement and verify the full approved scope, not just a first
green slice. Give validation and independent review equal attention to coding.
Use measured runtime to schedule research, never optimistic estimates to bypass gates.

## Forbidden Stop Reasons

After launch, a clean commit, green CI, an opened PR, a batch boundary, user
silence, or the volume of remaining work is not permission to stop. Only the
explicit Stop Gate or genuine blockers apply. Staging's fresh-launch pause is
intentional and does not grant later per-batch pauses.

## Post-Checkpoint Control Loop

After each commit/push, read this guide and verify the plan hash; reconcile
active jobs and charged time; poll PR comments/checks; identify the next exact
unblocked batch. Continue unless the Stop Gate explicitly permits stopping.
Never silently leave a local worker or server running at a final handoff.

## After Any Compaction

Read guide → session JSON → learnings → plan → log → relevant durable docs.
Confirm git ownership, tip, plan hash, resources, and charged research clock.
After launch, checkpoints/green tests/a PR/user silence are not reasons to stop.
When MCTS cannot qualify, finish honest cards/tooling but keep dependent games
blocked. No substitution of native-only comparisons. Keep one current state here;
chronology belongs in the log. Final handoff retains exact continuation and evidence
for any incomplete stage. Do not remove these run files during staging.
