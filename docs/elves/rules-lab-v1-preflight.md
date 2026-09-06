# Rules Laboratory staging preflight

Status: STAGED / FRESH LAUNCH REQUIRED. This is not an implementation or research
completion report. Verification captured 2026-09-06; check the exact closure tip
on PR #23 after its push and again before launch.

## Identity and scope

- Main/base: `b620a11a72097f22e5addbfaf58b56073f9612cd`, verified locally and on GitHub.
- Worktree: `/Users/armand/Development/varde-rules-lab-v1`.
- Branch: `codex/rules-lab-v1`; draft [PR #23](https://github.com/scarmani/varde/pull/23).
- Staging changes are documentation/session state only.
- Research allowance unused: 0/36 hours. No local research workers started.
- Existing checkout and draft PRs #20–22 left unchanged.

## Checks

- GitHub authentication and branch push: PASS; initial staging commit `a065f6d`.
- Resource capacity: 347 GiB free, 16 physical cores, 128 GiB memory; limit eight workers.
- Existing ephemeral ignores: PASS; no redundant ignore edit needed.
- Skill install advisory: newer release available; no automatic update performed.
- `CI=true python3 -m unittest discover -s engine -v`: PASS, 254 tests in
  25.285 seconds, zero skipped. This is the measured base count, not the larger
  historical test totals from unmerged research branches.
- `python3 -m compileall -q engine research`: PASS, exit 0.
- `node --check web/game.js`: PASS, exit 0.
- Browser smoke: PASS using the web-game skill's bundled Playwright client;
  loaded Classic/Toy, clicked a legal opening, and invoked pie takeover. Three
  screenshots opened and inspected; semantic states show correct move/seat
  progression, and no console or page errors were emitted.
- Browser isolation: localhost:8769, `VARDE_MODEL_PATH` pointing at a disposable
  `/tmp` path; no training call or user model write. Server PID 90760 stopped cleanly;
  no listener remains on that port.
- Standalone typecheck/build/deployment: not configured in this stdlib web app.
- Changed-file Ruff: N/A, no Python files changed. Ruff 0.14.14 available.
- Python 3.13.0 and Node 25.9.0 available; CI also checks Python 3.12.
- Survival-guide validator: PASS after completing required run-control headings.
- Bounded Fable goal cycle: PASS, CLI `claude-fable-5`, 104.7 seconds. It recommends
  staging only. Its initial-HEAD assertion was stale after our own commit; corrected
  against live history, not treated as a collision. No duplicate PR/commit or retry.
- Independent staging review: no blockers. Freeze global recipe selection scope
  and deterministic ruleset-interleaved blocks in Batch 1 before outcomes.
- CI: both tests checks passed on initial tip `a065f6d`; exact closure-tip status
  must be polled on PR #23. No issue comments, inline comments, or reviews at the
  initial post-push poll. No merge or approval performed.
- Sleep prevention: Codex environment exemption; no machine power settings changed.
- Notifications: current task and PR, not a newly configured external channel.
- Interactive prompts: prohibited by survival-guide run controls; no global setting changes.

## Tooling repair and artifacts

The first browser attempt failed before launch because the installed Playwright
package lacked its matching Chromium executable. Installed the package's Chromium
v1234 runtime and reran successfully. The installer automatically garbage-collected
the old v1228 cached browser/headless shell; future install commands should set
`PLAYWRIGHT_SKIP_BROWSER_GC=1` to avoid incidental cache removal. No product edits.

Raw preflight artifacts are outside git at
`/Users/armand/Development/varde-research/rules-lab-v1/preflight/`.
The committed `rules-lab-v1-preflight-artifacts.json` links their SHA-256 hashes.
This is operational browser verification, not proof certification, calibration,
or comparative research; the charged research clock remains exactly zero.

## Known limitations

All seven new variants, graph oracle, improved MCTS, and evidence cards are future
batches. No claim about game promise, strength, balance, or beauty is made here.
