Original prompt: yes to all in best order proceed and execute according to your recommendation

## 2026-07-12

- Preserved the imported prototype as Git baseline `9e14357`.
- Stabilization in progress: rules/engine truth, capture-wave telemetry, serialization,
  player identity, reproducible tests, then a locally playable web interface.
- Engine now rejects an opening pass, models swap ownership, round-trips versioned
  snapshots, and records capture cascades wave by wave.
- Rules prose has been rewritten to incorporate the collar and peel findings directly.
- Added a dependency-free local HTTP API and responsive canvas hotseat client.
- First browser pass found and fixed horizontal board centering; opening state exposed
  all 54 legal n=3 points with no console errors.
- Browser flow verified opening placement, pie-rule takeover, two-pass ending,
  resumption, save/load across board sizes, fullscreen, and capture highlighting.
  Full-flow and capture screenshots showed no console errors.
- Instrumented 100-game n=3 baselines completed for random, greedy, and 15%
  epsilon-greedy policies; exact results are recorded in README and design history.
- Final verification: 35 unittest and pytest cases pass; editable installation works;
  final Playwright opening-move state and screenshot have no console errors.

## TODO

- Human playtest the n=3 client and record usability/strategy observations.
- After human validation, add MCTS for the summit and saturation experiments.

## Computer opponent implementation

- Approved plan: local Casual and Standard rule-aware opponents, color choice,
  optional rationales, pie-rule handling, and computer-game save/load support.
- Opponent engine implementation in progress; MCTS remains intentionally deferred.
- Opponent engine and server integration now pass focused tests: automatic computer
  opening, turn locking, swap ownership, rationale visibility, and compatible saves.
- Browser controls and automatic computer-turn sequencing implemented; visual and
  end-to-end interaction verification remains.
- The 8N boundary remains a self-play watchdog only. A temporary 6N forced-pass
  policy was rejected because full-superko Varde already terminates mathematically;
  long bot games must be measured honestly, not shortened by an extra rule.
- Browser verification completed for both human colors, human and computer swap
  paths, thinking-state locking, rationales, capture animation, automatic
  resumption, compatible save/load, and unchanged hotseat play.
- Bot audit: Casual 20/20 ended below 8N; Standard 20/20 ended naturally, with
  19 below 8N and one at 489 turns. Decision latency stayed inside both budgets.

## Expanded boards, spectator mode, and learning AI

- Approved plan recorded in the task: Toy/Beginner/Intermediate/Full boards,
  proportional rendering at the former n=5 ratio, 10% larger lattice, two-computer
  playback, and a persistent Advanced linear evaluator trained by background self-play.
- Added n=6/216-point support and exact renamed labels. Canvas geometry now derives
  stones, glyphs, rings, line widths, fonts, and hit targets from projected spacing.
- Replaced one computer owner with two serializable seats. Complete identities,
  difficulty, and deterministic seed move together under pie-rule takeover; legacy
  version-1 saves with a top-level `computer` section still load.
- Added Advanced search, normalized color-symmetric features, atomic model persistence,
  background training/cancel/reset service, and training-only 20N watchdog. Live games
  still have no turn cutoff.
- Added paused spectator Play/Pause/Step and 1200/500/100 ms speed controls plus
  independent Black/White difficulty selectors. Loaded spectator saves start paused.
- Final automated checkpoint: 60 pytest cases and `node --check web/game.js` pass.
  Playwright covered all four board sizes, paused load, exact Step, Play/Pause and
  speed, both human colors, takeover, hit-testing, training/cancel/reset, fullscreen,
  and a two-wave Fast capture in 155 ms with no console errors.
- Fresh-position p95 was 26/44 ms on Toy and 411/682 ms on Full for
  Standard/Advanced. Eight deterministic training games persisted finite weights;
  a small color-alternated held-out sample was 3 wins and 5 losses versus Standard,
  so no strength improvement is claimed.
- Final evaluator audit separated strict skies from capped ordinary empty-point
  liberties, preventing a real sky from being counted twice while retaining its
  group-life and dedicated sky-weight effects.

## Corrected search and Advanced Learning V2

- Corrected every shared two-ply path to score an opponent pass, including the
  pie-rule value, and added legal White takeover as a Black-opening reply.
- Replaced the global computer-ending decision with persisted per-seat
  acceptances. In spectator games the first accepting AI no longer prevents the
  other seat from using the rules' one permitted resumption.
- Added the bounded height, rim, and group-consolidation features and migrated
  the model format to nine-weight V2 without deleting legacy six-weight models.
- Made training use margin targets, time-weighted samples, learner-only opening
  exploration, a global attempt ordinal, and a fixed master seed. Split batches
  are reproducibly equivalent to a single batch and discarded attempts still
  advance the cursor.
- Replaced the temporary-path research scripts with repository-relative,
  parameterized training, paired evaluation, benchmark, and larger-board smoke
  harnesses. Historical checkpoints are clearly isolated from production.

## Evaluator Profiles V3 and quality-diversity search

- Began the approved finite implementation on `feat/evaluator-profiles-v3`.
- Baseline is clean at `1da66f7`: 72 pytest cases, JavaScript syntax, and Python
  compilation pass; `engine/varde.py` is protected as an explicit no-change surface.
- Decomposed the run into evaluator parity/features, profile compatibility/API,
  browser experience, deterministic MAP-Elites, evidence/curation, and final gates.
- A bounded Fable goal cycle reinforced parity-first architecture. Its unrelated
  direct-to-main suggestion was rejected; product work remains on the owned branch.
- Batch 1 complete: Balanced now uses a named immutable weight map while exact
  seeded actions, scores, and node counts remain unchanged on all board sizes and
  special actions. Ten V3 structural/transition measurements are bounded,
  color-symmetric, non-mutating, and reuse supplied transitions without nested scans.
- A first implementation paid V3 telemetry cost at every node; focused latency
  evidence caught it and the disabled fast path restored roughly 28 ms Toy / 397 ms
  Full Standard decisions. The Personal nine-feature schema remains exact.
- Batch 2 complete: computer seats now store independent Casual/Standard
  difficulty and evaluator profile, legacy Advanced normalizes to Standard +
  Personal, version-1 saves and complete-seat takeover remain compatible, and
  `GET /api/profiles` exposes catalog availability without raw weights.
- The packaged catalog started with Balanced and Personal available; the
  declared archive/evidence run has since frozen Mason and Surveyor as
  available (see the Batch 5–6 entry below). No provisional style was shipped
  by weakening its descriptor gate.
- Batch 3 complete: dynamic browser selectors separate Casual/Standard search
  from profile style, independent spectator choices remain paused, unavailable
  archive profiles are visibly disabled, and Personal learning reports untrained
  equivalence or its local training count.
- Browser evidence covers actual selector submission, both pie-rule takeover
  directions, automatic continuation, legacy Advanced migration, profile-aware
  rationales without raw score, semantic state, opened screenshots, and zero
  console errors.
- Batch 4 complete: the repository-relative four-axis MAP-Elites harness uses
  candidate-owned random streams, 128-candidate frozen halls, strict in-order
  reduction, and atomic checkpoints containing pending work and complete evidence.
- Ten harness tests prove deterministic mutation/binning/replacement, hall
  selection, byte-identical interruption/resume across worker counts,
  cancellation, tamper detection, and incomplete accounting. A real two-process
  smoke completed 4 candidates / 32 games with no illegal or incomplete result.
- Batches 5–6 complete: the 2,000-position audit retained five transition
  features (capturing moves, max capture, covers, hostile covers, summits) and
  kept five structural features as zero-weight telemetry on latency grounds;
  the 4,096-candidate / 32,768-game MAP-Elites run (one permitted refinement
  included) filled 219 of 256 cells with six honest watchdog rejections.
- Final 100-pair gates shipped two of four curated styles: Mason (76.75%
  overall against Balanced, verticality effect 1.264) and Surveyor (51.75%,
  edge-reach effect 3.008). Raider was omitted because its held-out engagement
  moved in the wrong direction; Weaver was omitted below the strength floor.
  Profiles are described as different, not stronger; the catalog records
  `strength_claim: false`, availability reasons, and every stage hash. Compact
  evidence lives in `research/results/v3-final-evidence-summary.json` and
  `research/results/v3-final-benchmark.json`; the raw archive is retained
  outside the repository by sha256.
- A final browser pass on the frozen catalog verified human and spectator play
  with Mason and Surveyor, human and AI pie takeover with complete seat
  exchange, paused spectator loads, playback controls, capture-wave animation,
  save/load with legacy Advanced migration, trained/untrained Personal
  displays, and zero console errors.

## Ruleset promise evaluation program

- Repaired Gjerde fenced-cell scoring: unclaimed exterior lines now leave a
  field open. The prior one-line 37-0 n=4 result is regression-tested away for
  both Gjerde resolution orders, and all pre-repair quantitative conclusions
  are explicitly invalidated.
- Added a versioned ruleset registry covering stable IDs/revisions, candidate,
  control, archived, and broken status, geometry/scoring, board limits,
  descriptions, and archival reasons. Existing save IDs and tuple order remain
  unchanged.
- Added `GET /api/rulesets`; public new games reject research-only or broken
  variants while version-1 saves for those variants still load. Gjerde n=7/n=8
  saves now load through the same registry limits used by new games.
- The browser derives its rules choices and board limits from the registry,
  visibly disables unavailable variants, explains why, and preserves disabled
  selections when an old save is loaded.
- Batch 1 validation: 167 tests, Python/JavaScript syntax, API smoke, semantic
  Playwright state, opened screenshots, archived-save loading, and zero console
  errors all pass.
- Added six hash-pinned ruleset-native evaluator revisions while preserving the
  literal Classic Balanced search path. Non-Classic static evaluation no longer
  rewards Classic-only sky or development artifacts.
- Tactical admission fixtures cover collars, cyclic Rosette life and
  entombment, Breath cavities/cuts, Breath-run chase/self-squeeze, Gjerde fence
  completion/denial, and Gjerde-Go eyes/ko exposure. Native decisions are
  deterministic, legal, non-mutating, superko-aware, and save-compatible.
- Batch 2 validation reaches 177 tests; representative Full vertex decisions
  remain below one second in the local acceptance sample, while primary n=4
  Gjerde decisions remain below half a second.
- Added a deterministic common action layer for placement, pass, pie takeover,
  free extension, extension completion, resumption, and separate ending
  acceptance. Seat identities remain correct through takeover and both AIs get
  their first-ending decision.
- Added seeded, terminal-score-only UCT with action-uniform and light
  epsilon-greedy rollouts. A corrected 250-simulation smoke covered all six
  candidates and both policies with legal actions, no source mutation, no
  crashes, and no incomplete rollout; policy-sensitive results remain
  explicitly provisional.
- Batch 3 validation reaches 185 tests. MCTS is research-only and introduces no
  action ceiling or forced ending into live games.
- Added a repository-relative paired ruleset evaluator with native/MCTS agent
  families, explicit budgets and policies, action telemetry, health/depth
  summaries, atomic checkpoint/resume, cancellation, and research-only
  incomplete accounting. Results pin source, registry, evaluator, and agent
  hashes; insufficient or single-family samples cannot unlock a claim.
- Batch 4 validation reaches 193 tests. Worker-count/interruption equivalence is
  byte-proven for every final artifact, actual process-worker native and MCTS
  smokes complete legally, and promotion remains blocked.
- Added a hash-pinned human-study package generator with 8/10/12-participant
  crossover schedules, engine-derived comprehension puzzles, separate survey
  dimensions, emergence coding, and retention prompts. Gjerde puzzle evidence
  includes the repaired open-boundary case.
- Added an opt-in hotseat recorder that exports pseudonymous, monotonic-time
  action and resolution JSON locally without a collection endpoint. Browser
  save/load, watch disabling, two-pass ending, resumption, screenshots, and
  console state pass. Batch 5 validation reaches 200 tests.
- Committed a source/hash-pinned 12-game cross-family operational smoke for all
  frozen candidates. Every game completed legally, while extreme wipe and one
  stagnation observation remain explicitly non-claim; promotion is blocked.
- Published the exact evidence matrix and next compute commands. All declared
  overnight, depth, exploit, human, retention, outside-play, and final promotion
  gates remain visibly unrun. Local read-only record import rejects identity
  fields. Batch 6 validation reaches 201 tests and final readiness review.

## Breath-run browser startup repair

- Reproduced the reported half-loaded page against the live port-8000 process.
  The process predated `GET /api/rulesets` while serving the current JavaScript
  from disk, so the endpoint returned an HTML 404 and Safari surfaced an opaque
  “The string did not match the expected pattern” JSON error.
- Preserved the live 131-move Gjerde-Go snapshot, restarted the server from
  current main, and restored the snapshot before testing a new game.
- Verified an isolated Beginner Breath-run game versus Standard/Balanced as
  White: the computer opened, the pie choice remained human-owned, a canvas
  placement succeeded, and the computer replied with no console errors.
- Hardened browser API parsing so file launches, unreachable servers, stale API
  processes, and invalid responses produce actionable startup instructions.
- Breath-run now automatically passes the turn after a rescue when that chain
  has no further legal extension. A player can still stop manually while a
  continuation exists; the forced finish is compressed across live play,
  computer play, and the shared research action layer.
- Legacy saves captured after the final rescue but before the old manual finish
  are normalized on load, so restoring a game cannot reintroduce the dead-end
  button press.

## Rules Laboratory launch — 2026-09-06

- Draft PR23 launched explicitly; no merges. Batches1–2 freeze compatibility and
  implement three scoring variants behind an opt-in factory, immutable graph
  geometry, structured actions, complete analysis keys and replay-validated v2
  saves. Existing engine/server/browser source and v1 behavior remain unchanged.
- 340 tests pass; all218 frozen decisions and24 save cases retain exact parity.
- Bundled web-game client checked isolated Classic startup, opening and pie;
  three screenshots/text states inspected with zero errors. Server stopped.
- Four junction games, browser laboratory, oracle and gated research remain
  subsequent batches. No research time consumed; no game-quality claim made.

## Rules Laboratory Batch 3 internal checkpoint — 2026-09-06

- Y/six construction and three static controls are playable through the opt-in
  factory. Topology persists through captures; only original vertices score.
- Added legal-sequence tests for liberties, merging, suicide and capture reopening,
  strict topology/history replay, symmetry, pie and both-seat endings.
- 363 tests pass, zero skips; frozen legacy decisions/saves unchanged. Independent
  scoped reviews clean. No browser exposure yet; planted/passage are next in Batch 3.
- Research charged zero; this checkpoint does not end the launched six-batch run.

## Rules Laboratory Batch 3 complete — 2026-09-06

- Planted Y and opposite-pair passages complete the seven opt-in engine games.
  Planting is one action with one placement and one construction; no empty
  intermediate position enters the history. Empty building remains unavailable
  in planted rules. Later captures preserve every activated connection.
- 386 tests pass in64.481s, zero skips; scoped independent reviews clean.
  Added Full Passage cache-eviction coverage without changing production caching.
- Browser laboratory, objective-aware provisional opponents and independent
  mechanical oracle are next. Research remains unlaunched and comparisons blocked.
