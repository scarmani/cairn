# Bounded proof production and fixed tasks, revision0.1

Frozen Batch5B engineering contract at
b554a82f49076ed6c0abc7700f0067932dbd6a2a. Approved plan, rules, gates and budgets
remain unchanged. This unit implements a proof producer; tests remain synthetic.
No actual-game proof, corpus generation, MCTS decision or calibration runs here.

## Advisory disposition and scope

Goal cycle20260907T053346Z succeeded via CLI fallback claude-opus-4-8 in181.9s
(186.30s wrapper). The full response and prompt were read against current source.
Accept its bounded producer plus deterministic task-scaffold unit. The adapter
does not supply full-action origin attestation: never infer one from its journal
prefix. This unit carries explicit provider provenance, not invented reachability.
Actual replay attestation and the legacy-six independence qualification policy
remain for the pre-research execution freeze. Generic proof checking is independent
of proof production; shared versus independent mechanics stay disclosed.

An exhausted synthetic proof is an expected partial result, not permission to stop
the whole six-batch run. Stop the affected attempt and preserve its unknowns;
continue unblocked implementation under the survival guide. Never weaken checker,
gate, rules or tests to obtain a complete result. No Aragora tier/quorum rules apply.

Add only research/harness/lab_proof_producer.py, lab_fixed_tasks.py, their new
engine/test_lab_proof_producer.py and test_lab_fixed_tasks.py, plus an independent
test_lab_proof_producer_invariants.py and integration tests if needed. Keep frozen
lab_terminal_cert.py SHA71d14278493e8649681dc4d6782e46b212049c00f6778e98fce3c03d875925a6
and lab_research_adapter.py SHA01a16fa464178272b2a6d8f9a29f486662659ddc56f62da60a0ddb53fbca7996
unchanged. No engine/actions/native/oracle/browser/save/Personal/historical edits.
No worker processes or research ledger jobs in this unit. Use canonical package
imports and repository-relative paths; no paid provider calls beyond the completed
single advisory. Root owns run docs, whole-suite verification and closure.

## Producer behavior

Public entrypoint: produce_certificate(root_state, provider, *, node_limit=10000,
cancelled=None, deadline=None, clock=time.monotonic). It accepts the frozen
TerminalProvider API, not a local predicate or heuristic. The producer and checker
must not share traversal/minimax implementation or private checker helpers.
Public canonical/action/schema/seal helpers may be reused.

- Hard node_limit is an exact integer1..10000. Count every newly inspected state,
  including root/accepted leaves, and report memo hits separately. Generate a
  complete legal action domain at every expanded node. Do not hide alternatives
  through invented forbidden history or domain restrictions.
- Use explicit-stack traversal, not Python recursion as an undeclared horizon.
  Canonical full action IDs fix traversal order; preserve all orientations.
  Memoization uses the complete provider fingerprint and confirms exact canonical
  snapshot equality. A repeated active ancestor or contradictory fingerprint is
  an integrity failure, not a draw or terminal result.
- Compute WDL relative to the named original root actor identity (terminal roots
  need an explicit deterministic seat convention reported in telemetry). At every
  interior node choose max/min by CURRENT actor seat, not alternating ply/color.
  Preserve conserved seat identities through takeover and consecutive actions.
- Read score only after a true accepted terminal and validate exact integer B/W
  scores. Keep margins separate; winning moves with different margins remain WDL
  equivalent. Local obligation results never become game-result values.
- Unknown children retain[-1,+1] and a permitted explicit unresolved reason.
  Partial exact root values do not classify remaining alternatives. It is allowed
  to stop internal expansion once an extremal bound is sound, but NEVER silently
  prune root alternatives or claim complete root classification without exact
  values for every legal root action. Unexpanded legal edges remain explicit.
- If limits/cancellation/deadline prevent even a well-formed root graph, return an
  explicit partial/no-certificate result, never a fabricated root or accepted leaf.
  Otherwise emit a sealed strict TerminalCertificate, including partial graphs.
  A nonaccepted empty legal domain or callback failure is an integrity error.
- All provider callbacks and iterable consumption must preserve input state/wire
  data, including failures. Work on isolated copies. Validate finite JSON, exact
  identity types, action domains, accepted actor envelopes and conserved seats.
  No module-global mutable match/provider cache. Do not trust arbitrary caller
  metadata to elevate a snapshot's provenance.

Result fields are detached and versioned: certificate or null, canonical telemetry,
and separate optional machine timing. Canonical telemetry reports status/reason,
root_class, root actor/objective, complete-root flag, WDL bounds/action sets when
known, actual nodes/transitions/enumerations/memo hits, source/provider identity,
and admission_record:false. It distinguishes its own work from checker work; no
auto-checking hidden inside producer counters. Tests invoke the frozen checker
separately. terminal_simulation_backups is always0.

Root classes: terminal (no decision), forced-administrative (one exact legal admin
action), all-actions-equivalent (complete equal WDLs), discriminating (complete
unequal WDLs), or partial. Administrative kinds are swap, pass, finish-extension,
resume and accept; placement, construction, planting and extension are substantive.
Classifications are mechanical scope labels, not corpus eligibility or depth.

Provider metadata may contain an exact Boolean provenance.full_action_replay.
Carry that as provider-reported provenance with an explicit verification limit;
missing meansfalse. The frozen production/oracle adapters always reportfalse.
The producer does not attest origin/reachability or upgrade arbitrary snapshots.
Malformed provenance types fail; no caller flag can override provider metadata.
Actual full-action replay attestation is not claimed delivered in this unit.

## In-process fixed-task scaffold

Add a separate generic fixed-task executor with strict finite-JSON manifests and
atomic checksummed checkpoints. It is not a research launcher or worker supervisor.
Public APIs and exact schema are frozen by its owner before cross-module tests.
Manifests contain version, complete source/configuration identity, ordered unique
task IDs and JSON task payloads. Task order/IDs/payloads never depend on outcomes
or clock. Reject unknown fields, duplicate IDs, mismatched hashes and incompatible
checkpoint schemas. Do not execute code or load paths named by manifest content.

Run a supplied trusted local callback sequentially; an injected clock/deadline and
explicit cancellation may stop before the next task. This scaffold cannot interrupt
a running callback and must state that limitation. No sleeps, subprocesses, pool,
proof calls on real states or budget-ledger start_job. Future supervisor work is
required before charged tasks; this interface cannot claim deadline enforcement.

Skip only valid completed task IDs bound to the same manifest/task/result hashes;
never reorder remaining tasks. Final canonical completed records follow manifest
order and are byte-equivalent after resume. Put elapsed time and interruption/
attempt accounting outside canonical result hashes. Persist errors/cancellations
explicitly; never turn a failed callback into a score or completed success. Resume
does not automatically retry a recorded integrity failure. Empty or partial task
lists cannot masquerade as a fully completed manifest. Copies returned to callers
cannot mutate the stored manifest/checkpoint or previously completed results.

Use atomic replace plus flush/fsync for file checkpoints; external output directory
is explicit (temporary directories in tests), never default inside the repository.
No actual parallel worker-equivalence claim is made before the supervisor exists.
Synthetic tests cover strict tamper rejection, fixed ordering, interruption/resume,
callback failure, input mutation, detached outputs and timing-independent hashes.

## Verification and continuation

Synthetic producer/checker round trips cover every root class, complete equivalent
action sets, legitimate sacrifice versus rescue, same-seat and changed-seat paths,
color takeover, opposite-seat reply choice, accepted-only leaves, DAG reuse,
cycles/collisions, limits/cancellation/deadline, type aliases, malformed callbacks,
unknowns, non-mutation and deterministic output. Never construct a real-game proof
as a unit-test shortcut. Existing mechanical adapter tests may remain unchanged.

Run all597+ product tests with zero new skips, changed-file Ruff, compileall,
both JS syntax checks, frozen hashes, independent review and exact-tip CI. Commit
specific files, push draft PR23, immediately reread guide/hash and PR feedback,
then continue Batch5. No merge or internal checkpoint stop. Research remains0.
Next work includes full-origin attestation, enforced worker stops and budget
bootstrap/manifest freeze, three MCTS recipes and charged certification/admission.
