# Varde Rules Laboratory: Seven Variants and Evidence-Graded Evaluation

Approved scope, frozen for this run on 2026-09-06. Staging does not authorize
implementation until the separate launch step. This document records the user's
approved plan; operational details live in `docs/elves/rules-lab-v1-survival-guide.md`.

## 1. Summary and frozen rules

Build an explicitly experimental browser laboratory for all seven newly discussed
variants, preserve the six existing candidates, and develop a stronger evaluation
system that distinguishes correctness, strategic evidence, rule economy, and
aesthetic hypotheses. The outcome is a ranked shortlist of up to three promising
candidates, not a forced flagship selection.

Use up to three resumable 12-hour local-compute windows. Competent MCTS is a
prerequisite for comparative match evidence. Mechanical testing, browser
implementation, and analysis tooling can proceed independently; if MCTS remains
inadmissible, comparative matches remain blocked.

### New variants

Freeze each at revision `0.1`; do not combine their changes during this round.

| ID | Rules |
| --- | --- |
| `line-breath` | Gjerde's line adjacency and Breath resolution; score occupied lines plus single-color-bordered empty-line regions. Cells score nothing. |
| `gjerde-majority` | Gjerde-breath placement and capture; each cell scores one point for a player controlling at least four of its six edges. No regional enclosure score. |
| `breath-connection` | Ordinary Breath, with one point subtracted from each player's area score for every separate surviving friendly group. |
| `junction-y` | Instead of placing, construct an empty center connected to one of the two alternating sets of three hexagon corners. |
| `junction-six` | Instead of placing, construct an empty center connected to all six corners. |
| `junction-planted` | Place a stone at an unused center and simultaneously create its chosen Y connections. |
| `junction-passage` | Instead of placing, construct an empty center connected to one of the three opposite-corner pairs. |

### Shared junction rules

- Use ordinary Go resolution: remove libertyless enemy groups after placement,
  then reject suicide.
- Construction sites are the original bounded hexagonal faces. Each permits one
  permanent junction.
- Inactive centers are absent, not empty liberties. Active centers and edges are
  neutral and remain after captures.
- Empty construction consumes the whole turn. Planted construction is one atomic
  placement.
- No rotation, demolition, upgrades, recursive subdivision, stacking, or rescue turns.
- Only original vertices score. Determine empty regions on the complete active
  graph, but count only original vertices within them.
- Require an original-vertex stone as the opening; retain pie takeover, two-pass
  ending, and the existing once-only resumption procedure.
- Construction resets consecutive passes and counts as a substantive action.
  Introduce no quiet-move or live-game action ceiling.

Retain Classic, Rosette, Breath, Breath-run, Gjerde-breath, and Gjerde-Go unchanged
as comparisons. Archived/broken variants remain preserved and loadable but are
not reopened as ordinary playable candidates.

Add research-only static controls: ordinary Go on the original honeycomb, fully
developed six-spoke geometry, and fully developed Y geometry with seed-frozen
orientations. These distinguish the effects of connectivity from the act of
constructing it.

## 2. Implementation and playable laboratory

### Engine and compatibility

Start an isolated branch, `codex/rules-lab-v1`, from verified `main` at
`b620a11a72097f22e5addbfaf58b56073f9612cd`. Open a new draft PR during staging.
Preserve PRs #20–22, their branches, and historical evidence unchanged; do not merge.

- Introduce a game factory and graph-aware implementation behind the existing
  rules-action interface. Reuse existing flat capture and scoring primitives
  where applicable; preserve legacy rules behavior and seeded decisions.
- Represent original vertices, potential centers, and corner order with stable
  identifiers. Store junction activation/orientation in game state.
- Keep topology immutable per snapshot, with adjacency cached by canonical
  topology. Searching or cloning one position must never change another.
- Distinguish two keys:
  - Repetition signature: rules revision, topology, stones, and next color.
  - Analysis/cache key: repetition state plus forbidden-position history, seat
    identities, and ending/turn-phase state.
- Extend legal actions with construction and planted-construction actions,
  including orientation. The server, agents, replay system, and browser must
  consume the same legal-action representation.
- Keep existing saves in version 1. Use version 2 for new laboratory rules,
  preserving topology and topology-aware history. Continue loading both legacy
  format identifiers; reject malformed or unsupported experimental saves explicitly.

### Browser and API

- Add an "Experimental lab" switch. Normal defaults and existing ruleset choices
  remain unchanged.
- Extend `/api/rulesets` with experimental availability, rules revision, supported
  actions, scoring description, and analysis status.
- Extend new-game creation to select laboratory rules explicitly. Add `/api/action`
  for structured laboratory actions while preserving existing endpoints.
- Show unused construction sites separately from playable intersections. Preview
  spokes and orientation before committing; support mouse and keyboard
  orientation selection.
- Display scoring vertices and zero-point junctions distinctly. Inspection must
  show actual neighbors, distinct liberties, and construction state.
- Support hotseat, human-versus-computer, and independent computer seats with
  existing spectator playback, explanations, saving, and loading. Loaded
  spectator games start paused.
- Provide Casual and Standard objective-aware laboratory opponents, visibly
  marked provisional. Do not silently apply Classic profiles or the user's
  Personal model to new rules.
- Keep research MCTS out of normal difficulty selection; expose its admission
  status in the lab's evidence view.
- Extend local play records and `render_game_to_text` with topology, orientation,
  legal construction actions, and separate placement/construction counters.
- Research workers use separate games and processes and never modify or lock the
  displayed match for their computations.

## 3. Improved analysis and MCTS admission

### Evidence model

Produce a per-ruleset evidence card rather than one aggregate "beauty score."

| Dimension | Report |
| --- | --- |
| Correctness | Resolution/scoring invariants, repetition, termination argument, counterexamples |
| Rule economy | Independent concepts, turn phases, persistent state, exceptions, and required global checks |
| Tactical structure | Certified alternatives, connection/capture consequences, and decision sensitivity |
| Strategic depth | Search-budget gains, stable decisions, exploit resistance, and cross-agent agreement |
| Strategic variety | Reproducible styles, opening families, sacrifices, reversals, and distant responses |
| Closure | Actions and placements to finish, cleanup burden, stagnation, and research incompletes |
| Aesthetic potential | Representative diagrams and recurring motifs, explicitly labeled computer-derived hypotheses |

Every entry carries provenance, sample size, uncertainty, and an evidence status:
verified, observed, provisional, unmeasured, or contradicted. Missing evidence is
never represented as a zero rating.

### Exact analysis

Build an independently implemented graph oracle for small positions and bounded
proof tasks.

- Verify empty-center liberties, group merging, capture reopening, orientation
  effects, scoring-region changes, and superko.
- Return complete equivalent action sets and `unknown` when a node limit prevents proof.
- Keep local obligations separate from game-optimal decisions. A certified group
  rescue proves survival within its horizon; it does not prove that rescue is
  preferable to sacrifice.
- Use only accepted-terminal score-certified positions to label MCTS choices
  optimal or suboptimal.
- Never manufacture superko histories merely to hide inconvenient legal alternatives.
- Freeze disjoint development and holdout corpora before evaluating candidate
  search recipes. Require at least eight independently certified positions in
  each split per ruleset, including its distinctive actions and ending decisions.
  If that minimum cannot be certified, admission remains incomplete.
- Retain nonterminal tactical positions as diagnostic material, with explicit
  proof scope and horizon.

### Bounded MCTS repair program

Develop both broader analysis tools and an MCTS repair track, but require
per-ruleset MCTS admission before comparative match screening.

Predeclare three research recipes:

1. Audited UCT control: correct seat perspective, semantic seeded ties, complete
   state keys, and terminal-only rewards.
2. Reserved expansion: the same control with visit-gated expansion, mandatory
   administrative actions, rules-derived action ordering, and cached legal transitions.
3. Terminal-proof MCTS: reserved expansion plus sound propagation of exact
   accepted-terminal game results. Local rescue/capture proofs never become
   game-result values.

Use the existing `ceil(2 × sqrt(visits))` exposure schedule, preserving eventual
expansion. Test uniform and independently implemented light rollouts. Reuse
transition facts within each state; do not introduce heuristic nonterminal
backups or import failed V5 guidance as an assumed improvement.

- Development ladder: 64, 256, 1,024, and 2,048 simulations, four deterministic
  replicates per position and policy.
- Select one recipe by highest high-budget certified admission, then lower
  measured latency, then recipe ID.
- Holdout requirements: at least 80% optimal-action admission, at least three of
  four hits per position/policy cell, nondecreasing aggregate admission across the
  final two rungs, and zero integrity failures.
- Both rollout policies must pass before results are treated as policy-robust.
- Run 4,096 only if 2,048 passes admission but misses 85% top-action agreement or
  0.80 top-three Jaccard agreement with 1,024, and measured projections fit the
  remaining budget.
- Any rollout watchdog produces an incomplete result, never a substitute value.
  Exact solved results are recorded separately from terminal simulation backups.
- No post-holdout tuning or automatic extra architecture search. Preserve failures
  and require a later plan for further redesign.

MCTS admission remains a prerequisite, not proof of strategic strength or game quality.

## 4. Ordered research execution and ratings

### Implementation order

1. Freeze rules, hypotheses, controls, compatibility fixtures, and evidence definitions.
2. Implement the three scoring variants and the graph-aware foundation.
3. Implement Y and six-spoke junctions, followed by planted junctions and passages.
4. Complete the browser lab, replay/export, objective-aware opponents, and mechanical oracle.
5. Freeze search corpora and run the MCTS program.
6. Run admitted comparative tests, generate evidence cards, and produce the shortlist.

Use the Elves staging/launch separation: prepare the branch, draft PR, run-control
documents, and preflight first; launch unattended work through a separate launch
step. The implementation phase is separate from the 36-hour research-compute allowance.

### Compute scheduling

- Use at most eight local workers.
- Charge proof certification, agent calibration, and research games against the
  three 12-hour windows.
- MCTS may consume the entire allowance if necessary. Do not substitute
  unqualified native-only matches for the requested independent-agent prerequisite.
- Before launching a cohort, project runtime from measured throughput with a
  30% safety allowance.
- Schedule fixed, outcome-independent task blocks. Preserve completed work at
  each window boundary and resume exact manifests.
- Never extend beyond 36 hours automatically. Incomplete cohorts remain visible
  but cannot support headline comparisons.

### Comparative program, conditional on admission

For each eligible ruleset:

- Run an exploratory screen of 10 paired n=4 seeds and five paired n=5 seeds,
  with colors alternated, against the frozen objective-aware native agent.
- Use Toy only for tactical fixtures and operational smoke. Add Full-board
  legality and usability smoke.
- Record original-seat results separately from post-swap color results.
- Measure both fixed-work behavior and calibrated fixed-time performance. Record
  transitions, rollout actions, nodes, latency, and terminal-backup counts.
- Compare construction variants with their static-geometry controls. Track
  construction timing, orientation, opponent occupation of constructed centers,
  capture reopening, and deliberately undeveloped faces.
- Record captures per placement, construction per action, group survival,
  occupied area, and objective score separately. Scoring changes must not create
  an apparent improvement solely through different units.

For up to three exploratory survivors, subject to remaining time:

- Run 40 fresh paired n=4 seeds and 10 fresh paired n=5 seeds, 100 games per candidate.
- Conduct bounded exploit search against the frozen admitted baseline, including
  attack-only, defense-only, connection, denial, build-first, and never-build
  policies where applicable.
- Reuse the existing quality-diversity infrastructure for 16 deterministic policy
  candidates per survivor, screened on two paired seeds; test the two strongest
  exploits on ten fresh paired seeds.
- Keep development, selection, and confirmation seeds disjoint.

### Shortlist procedure

- Exclude mechanically broken variants from the playable shortlist; preserve
  their reports and counterexamples.
- Treat confirmed exploit strategies as adverse evidence. A weak agent or a
  research watchdog alone does not establish a rules defect.
- Rank evidence maturity first, then consider the tradeoff between demonstrated
  strategic choices and rule burden.
- Show nondominated candidates across depth evidence, exploit resistance,
  closure, and rule economy. Use fewer independent rules as the final tiebreaker.
- Select at most three; allow fewer or none. Candidates lacking admitted match
  evidence receive a clearly separate, provisional design-priority ranking.
- Require at least 100 completed admitted-agent games before any comparative
  headline. Report paired confidence intervals; never pool rules revisions or
  differently qualified agents.
- Do not infer human readability, beauty, replay desire, or memorable strategic
  understanding from computer metrics. Those remain unmeasured until actual
  player observations exist.

## 5. Acceptance, artifacts, and stop conditions

### Required tests

- All seven rules definitions, scoring boundaries, group penalties, and equivalent orientations.
- Distinct shared liberties; inactive versus empty centers; captures leaving
  permanent topology; planted construction creating no immediate enemy capture.
- Y quadrilateral structure, six-spoke triangulation, opposite-pair passages,
  rotations/reflections, and color symmetry.
- Clone isolation, legal-transition parity, complete superko history, cache-key
  separation, and save/load replay.
- Pie ownership, construction after the opening, passing, both seats' ending
  decisions, and once-only resumption.
- Oracle unknowns, equivalent optimal actions, legitimate sacrifices, proof
  propagation, honest simulation counts, and terminal-only backups.
- Deterministic semantic results across workers and checkpoint/resume. Store
  machine-dependent timing separately from canonical result hashes.
- Full product suite, changed-file Ruff, Python compilation, JavaScript syntax,
  and CI on the final tip.

Use the web-game testing workflow to exercise every new ruleset through real
browser interactions. Inspect screenshots, rendered text state, exports, and
console errors after construction, orientation, capture, takeover, playback,
save/load, resizing, and fullscreen.

### Deliverables

- Experimental browser lab with seven playable variants.
- Versioned rules and agent specifications.
- Reproducible CLI, manifests, raw game records, optional move telemetry, and
  audited summaries.
- Per-variant evidence cards, construction/contact heat maps, symmetry-reduced
  motif atlas, and representative successful and failed positions.
- Ranked shortlist with explicit confidence and unresolved questions.
- Draft PR, verification report, and exact continuation instructions for any
  uncompleted stage.

Keep raw research output outside the repository; commit compact hash-linked
evidence and documentation.

Stop affected research immediately on illegal actions, mutation, corrupted saves,
false proofs, or nonterminal backups. Stop all dependent runs if the defect is
shared. Preserve negative results, do not alter rules inside a frozen round, do
not overwrite Personal learning models, and do not merge any PR.
