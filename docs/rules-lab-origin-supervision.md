# Full-action origin and bounded worker execution, revision0.1

Frozen Batch5C engineering contract on source
86392fa6d4410286ff7a5da0f7c7f3af5d021b9d. Both exact-tip CI tests pass and all646
local tests pass. The approved plan/rules/claim gates remain unchanged. The single
bounded advisory20260907T060258Z failed exit2 in244.70s (CLI error,240s fallback
timeout, no API). No response accepted or retry; proceed using local judgment
under goal-cycle Hard rule3. This contract does not authorize research outcomes.

## Scope and ownership

Add research/harness/lab_origin.py and lab_supervisor.py, with a small dedicated
worker entry module if process isolation needs it. Add corresponding new tests
and independent integration/invariant tests. Root owns run documents, frozen
contract, whole-suite verification and closure. Owners publish exact APIs/schema
before cross-module tests. No existing source file edits in this unit.

Preserve the frozen checker, adapters, producer and fixed-task scaffold byte for
byte. Preserve engine/varde.py, all production/action/factory/native/oracle/browser/
save/Personal sources, historical artifacts and PR20–22. No new PR, redundant
rollback tag, paid compute, merge, deployment or external service. The existing
Batch5 rollback tag remains valid. Commit/push/CI are internal checkpoints.

Origin tests use short explicitly authored legal action sequences only: no policy
games, actual terminal proof production, corpus selection, MCTS or calibration.
Supervisor tests use synthetic callbacks and disposable external ledgers; they
never touch the official research ledger, run a real-game proof or spend a research
window. Engineering process-stop measurements are not game-throughput evidence.

## Full-action origin records

Implement a strict versioned finite-JSON record from an explicit fresh-game
configuration and a complete ordered list of semantic RulesAction wires. Support
all16 frozen definitions (six legacy, seven lab, three static controls) at n3–6.
Configuration includes exact rules revision, size, topology seed and initial seat
identities; neutral deterministic player labels avoid personal data. Normalize only
documented factory seed semantics, and record that normalization explicitly.

Replay from new_game with explicit research/experimental selection. Do not start
from imported snapshots, caller-created histories, saved suffixes, reconstructed
acceptances or arbitrary state objects. Every placement, oriented construction,
extension/closure, pie takeover, pass, resumption and acceptance must be present
when it actually occurs. Never insert omitted administrative actions to make the
record valid. First/last state, action IDs, before/after actor seat/color and seat
maps, full analysis/fingerprint identity and complete history are hash-bound.

The record serializer is not the verifier: verification independently replays the
supplied actions from the declared factory origin and checks every expected trace,
final snapshot and hash. Reject unknown fields, bool/integer aliases, wrong revisions,
illegal/oriented actions, duplicate or missing indices, altered histories, omitted
acceptances and mismatched source identities. Detached immutable record/result
storage; no mutation of caller actions, root states or frozen provider objects.

For the10 laboratory/control definitions replay the same complete wires using the
independent oracle from its own new_state. Compare the actual shared semantic
snapshot/actor/seat/history projections, not just final score. Both paths must agree
before reporting independent mechanical replay. For the legacy six, explicitly
report independent_mechanics:false with the reason. Their production replay still
proves origin relative to the declared engine but cannot masquerade as independent
mechanics. All16 remain in the future certification schedule; their exact evidence
independence qualification is a pre-research manifest decision, not silently waived
or resolved through an extra unfrozen engine implementation in this unit.

Expose detached verified production root and, where supported, independent root
plus an immutable provenance receipt. A bound provider wrapper may add full-origin
metadata only for the exact verified record/root fingerprint and matching source
hashes. Binding to another state, a tampered receipt, an imported suffix or stale
code must fail. Do not change the frozen adapters' default false provenance.
Producer results continue to call provenance provider-reported and admission:false;
the origin receipt separately identifies what was replayed and by which mechanics.
No replay receipt is an optimal-action certificate or MCTS admission result.

Source identity includes origin implementation and relevant fixed production/
independent dependencies. Runtime verification must hash the actual authoritative
dependency paths, not merely compare two declarations. Never open/execute paths or
commands supplied by record content. Public canonical package imports only.

## Owned process supervision and fixed manifests

Implement a bounded local supervisor around trusted repository callbacks and the
existing validated FixedTaskManifest. Manifest payloads are data, never executable
commands, import targets or source paths. Trusted callback selection and authoritative
runtime dependency paths are supplied by local code, not the manifest. Verify actual
dependency bytes against declared hashes before dispatch and on resume; label the
scope precisely rather than pretending a declaration validates every imported module.

Support worker counts1..8, explicit external output directory, fixed manifest-order
task dispatch, a per-task timeout and cohort timeout/deadline, cancellation and
atomic checkpoints. Worker scheduling/completion order must not change task seeds,
semantic results or canonical output order. Output is detached strict finite JSON;
machine timing, attempt nonce/PID/CPU/accounting and interruptions remain outside
canonical semantic result hashes. Record complete successful results in manifest
order even when worker completion is out of order. Never treat missing results,
callback exceptions, invalid JSON, killed workers or nonzero exits as scores.

Use isolated owned processes, with start/stop handshakes and a bounded TERM→KILL→
reap cleanup path. Cancellation/deadline must stop active callbacks, not merely
prevent the next one. Preserve process/attempt identity before callback entry and
ensure cleanup on every error path. Never signal unrelated processes or rely on a
process name to identify ownership. Test an uncooperative synthetic worker and an
owned same-group descendant; do not claim containment of malicious detached code.
The trusted worker contract forbids detaching or launching unrelated work.

An authoritative checkpoint is bound to full manifest/task/result hashes. Record
attempts before dispatch, completed versus cancelled/timeout/fault states, unresolved
crash residue and cleanup confirmation. Resume skips only validated completions.
Out-of-order completions may be retained but never reordered or duplicated. A
recorded integrity/callback failure blocks automatic retry. A known cancelled or
timed-out attempt may be resumed only via an explicit reconciliation option after
owned workers are confirmed stopped; retain the original attempt and charge. A
foreign active lease/crash residue requires explicit reconciliation, never inferred
absence from a reused PID. Reconciliation cannot delete or rewrite negative evidence.

The existing in-process fixed-task checkpoint schema remains unchanged. Use a new
supervisor schema if parallel accounting requires it; reuse validated manifest and
public canonical helpers, not private persistence internals. Empty/partial results
cannot be reported as a completed manifest. Single-owner lock across coordinator
lifetime; tampered/stale manifests/checkpoints fail before callback entry.

## Budget binding and first-measurement boundary

Require an explicit ResearchBudget instance, unique job identity/category, positive
projection and honest measurement provenance for a supervised block. Reserve the
worker allocation before process creation. Bound cohort execution by the earlier
of its explicit cap and returned window/total deadline, with cleanup time reserved
inside the allowance. Charge failures and cancellations until every owned worker
is stopped/reaped; record worker CPU where measured and explicit unknown where it
cannot be recovered. Never reset the ledger, close a job with live workers or
claim a hard-stop merely because the ledger returned a deadline.

Test with disposable synthetic ledgers only. Verify max8, union-wall accounting,
failed/cancelled charges, window/total fit, restart reconciliation and no launch
after source/manifest/integrity failure. Treat OS overrun as visible integrity/
budget failure, not a negative duration, hidden truncation or fresh allowance.

The first real throughput measurement remains a separate predeclared charged
bootstrap stage. This unit does not launch or pretend to estimate that probe from
game evidence. Before actual research, freeze a tiny hard-bounded initial calibration
block, exact task order, accounting provenance, source hashes and failure policy;
use its measured throughput with1.30 safety before any subsequent cohort. Explain
explicitly that bootstrap sizing is a hard resource reservation, not previously
measured game throughput. No free real-state proof/calibration is permitted.

## Required verification and continuation

Origin: all16 definitions/four sizes, distinctive oriented actions, retained
topology after known capture, same-seat extension and closure, both pie directions,
both ending seats/resumption, omitted/reordered/tampered actions, exact history and
source separation, stale bound providers, strict types and non-mutation. Use existing
authored mechanics fixtures where appropriate without changing their frozen files.

Supervisor: actual short synthetic processes on1/2/8workers, deterministic reversed
completion order, timing-independent canonical output, checkpoint/resume and explicit
interruption reconciliation; source/manifest tamper, callback/input/result faults,
uncooperative workers and descendants, coordinator exceptions/cancellation, ownership
locks, no orphaned worker, budget charging and invalid-projection rejection.
No long sleep or real game task in tests; use bounded handshakes and short waits.

Run the full646+ suite with zero new skips, changed-file Ruff, Python compilation,
both JavaScript syntax checks, protected hashes, independent cumulative review and
exact-tip CI. Preserve any REDs. Commit specific files, push PR23, fully reread
survival guide/hash and poll feedback/CI, then continue the remaining Batch5 work:
charged bootstrap/corpus certification, three frozen MCTS recipes/admission, then
conditional Batch6 evidence. No internal-checkpoint stop or merge.
