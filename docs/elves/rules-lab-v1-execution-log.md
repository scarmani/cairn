# Rules Laboratory execution log

## Run digest

- Phase: staging, Batch 0. No implementation batch completed.
- Base: `b620a11a72097f22e5addbfaf58b56073f9612cd`.
- Branch: `codex/rules-lab-v1`; PR pending creation.
- Next: finish staging and provide fresh launch instructions.
- Active research: none; charged time 0/129,600 seconds.
- Report: preflight markdown pending verification; no overnight result report yet.

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
