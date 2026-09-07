# Accepted-terminal certificate interface, revision0.1

Frozen Batch5A engineering contract at ad7269026db64b8177c45185f51fa7748fb18c1a.
The approved plan and evidence layers remain unchanged. This unit adds a
certificate/checker and research state adapters, not a search recipe or corpus.
All proof-graph tests are synthetic; real states are used only for mechanical
adapter transition/key checks. Research remains0 and no window is opened.

## Scope and authority

Add research/harness/lab_terminal_cert.py and lab_research_adapter.py, additive
engine/test_lab_terminal_cert.py and test_lab_research_adapter.py, and a separate
independent invariant test file if useful. Do not edit production rules, actions,
factory/native/oracle/local-proof code, existing MCTS, browser, saves, Personal
models, historical artifacts or donor branches. Source metadata and unit tests
are not research findings. A local-proof certificate never parses as terminal.

The bounded advisory20260907T045202Z succeeded via CLI fallback in180.7s
(184.16s wrapper). It recommends this interface-only unit. No Aragora tier/quorum
contract exists in Varde; template residue is not authority. The pre-batch-5 tag
already exists at the verified head. Pending run-state docs stay with this unit;
do not create a redundant housekeeping commit or rollback tag.

## Shared provider interface

`TerminalProvider` is an immutable callback descriptor, independent of any MCTS
or local goal predicates. It includes provider_id, rules_id, rules_revision,
rules_hash and implementation_hash, plus these callbacks:

- fingerprint(state): canonical SHA-256 of complete state identity;
- snapshot(state): detached finite JSON containing the complete state/history;
- metadata(state): detached initial geometry/seed/provenance metadata;
- actor(state): {seat,color}, both null only when accepted;
- seats(state): bijective {B:identity,W:identity};
- accepted(state): exact boolean, never game.finished alone;
- score(state): exact {B:int,W:int}, queried only for accepted states;
- legal_actions(state): complete iterable of structured JSON action objects;
- transition(state, action_wire): detached successor through real legal mechanics.

Canonical action IDs are sorted-key compact JSON of the complete wire object,
including orientation. Validate finite JSON and duplicate IDs; do not rely on
repr/action coordinates alone. Providers may share legal APIs but cannot restrict
the domain or supply nonterminal value estimates. Checker calls must be guarded
against input mutation using complete snapshots/fingerprints, including failures.

## Certificate schema and meaning

Public APIs: `TerminalCertificate.from_dict`, `TerminalCertificate.to_dict`,
`check_certificate(certificate, root_state, provider, *, node_limit=10000,
cancelled=None)`. Inputs/outputs are detached; exact schema errors and integrity
contradictions fail explicitly. Normal checker resource exhaustion returns an
unverified/unknown report rather than an exact value. Additional pure canonical
hash/seal helpers and value dataclasses are allowed; no real-game proof producer.

The versioned certificate contains: format/version, provider/rules identity and
hashes, implementation hash, complete root snapshot, root fingerprint, root actor,
provider-derived initial/provenance metadata, objective
{kind:"accepted-terminal-wdl",seat:<original identity>}, every root action ID,
per-action WDL bounds, graph/hash, resource counters and an explicit claim limit.
Use -1/0/+1 for loss/draw/win. WDL is distinct from terminal B/W score and margin;
two winning continuations with different margins are equally optimal.

Each graph node contains its fingerprint, actual actor and color-seat map,
accepted flag, claimed WDL bounds, and either:

- accepted leaf: real score, no legal actions, no unresolved reason; or
- expanded nonterminal: the complete legal action domain, each wire/id and a
  child fingerprint or explicit unknown child; or
- unexpanded nonterminal: unknown bounds[-1,+1], with explicit operational or
  not-expanded reason and no claimed exact value/domain.

Allowed unresolved reasons: not-expanded, node-limit, deadline, cancelled,
watchdog. A watchdog or missing child is not a score, draw or terminal backup.
Require a complete enumerated root domain for a complete root classification.
Every referenced node must exist and be reachable; reject duplicate IDs,
dangling edges, contradictory repeated states and cyclic claimed proof graphs.
No file paths, executable payloads or implicit external graph dependencies.

The checker reconstructs states from the supplied root through the provider,
recomputes legal domains and terminal scores, and independently propagates bounds
by current actor seat relative to the named root identity. Same-seat consecutive
turns and color takeover do not alternate minimax polarity. At maximizing nodes,
lower=max(child lower), upper=max(child upper); at minimizing nodes use min.
Unknown children retain[-1,+1]. An extremal proven child can establish a node
value, but cannot make unvisited root alternatives inferior. Never treat
game.finished or one seat's first acceptance as an accepted terminal leaf.

A complete optimal-action set requires every legal root action to have an exact
WDL value. If only the root value is exact, report that separately and retain
unresolved alternatives; do not issue admission labels. Terminal root states may
be mechanically checked but supply no decision and cannot count toward a corpus.
Partial verification is not an admission record. Report recomputed work counters
separately from claimed producer resources; proof terminal_simulation_backups
must be0. Timings never enter canonical hashes. Full-action replay provenance
must match independently provider-derived metadata, not a certificate assertion.

## Research adapters and independence

`production_provider(rules_id)` returns a complete RulesState provider for all
six legacy candidates, seven lab definitions and three research controls.
`independent_provider(rules_id)` returns the corresponding lab_oracle provider
for its ten supported definitions and explicitly rejects unsupported legacy IDs.
Adapters do not run proof searches. Metadata must state that an arbitrary saved
snapshot is not a fully verified complete action trail; this unit cannot claim
corpus admissibility merely from a v2 game journal/current ending envelope.

`ResearchAdapter` provides canonical action IDs, full analysis identity and
bounded isolated cached transitions for production RulesState. Preserve replay
prefix/initial topology/seed in cache ownership, not just a semantic board key.
Use RulesState.analysis_key for legacy too, never its compatibility key(). A
caller must not mutate cached states through returned objects. The certificate
checker uses uncached provider recomputation, not this cache's answer as truth.
Expose resolved transition/cached-hit counters distinctly. No global match cache.

Shared production mechanics versus independent oracle mechanics remain explicit
provenance categories. The legacy-six certificate-independence policy is deferred
for a later pre-outcome freeze; no second full legacy cascade engine is ordered
here, and no legacy candidate is silently omitted or declared independently solved.

## Verification and deferred work

Synthetic tests cover exact/equivalent wins, draws/losses, legitimate sacrifice,
same-seat/changed-seat turns, color takeover, incomplete alternatives, false
terminal flags/scores, wrong minimax polarity, missing/duplicate oriented actions,
tampered graph/hash/metadata, cycles/dangling/unreachable nodes, counter honesty,
node/cancellation exhaustion, mutable/bad providers and input non-mutation.
Mechanical real-state adapter tests cover all16 definitions, orientations,
complete forbidden history, save/replay key separation, pie/endings and detached
cache ownership without invoking any game proof search or calibrated decision.
Full547+ tests, changed-file Ruff, compileall, JS syntax, independent review,
protected-source hashes and exact-tip CI remain required.

Deferred within Batch5: proof producer, immutable recipe implementations and both
rollout policies, pure manifest/scheduler/coordinator with tested worker-stop,
all-sixteen coverage/eligibility freeze, full-action corpus provenance, actual
charged proof/pilot and measured bootstrap, and legacy-six verification strategy.
None is permission to change the frozen gates, omit failed candidates, run
native-only comparisons, merge or stop the launched run after this checkpoint.
