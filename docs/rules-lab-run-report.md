# Rules Laboratory: implementation and research boundary

## Outcome

The seven revision-0.1 laboratory variants are playable on draft PR23. The
six existing candidates and three research-only static controls are preserved.
The implementation and independent analysis deliverables are complete; the
research-dependent parts of Batches5–6 remain blocked, not completed.
No PR was merged. No strategic-quality ranking is established.

| Batch | Delivered | Remaining gate |
|---|---|---|
| 1 | Frozen rules, hypotheses, compatibility fixtures and evidence definitions | None |
| 2 | Three scoring variants, graph foundation, factory and strict v2 saves | None |
| 3 | Y, six-spoke, planted-Y and passage games | None |
| 4 | Browser lab, provisional native opponents, local records and mechanical oracle | None |
| 5 | Independent proof tooling, frozen candidate inventory, three MCTS recipes, resumable supervisor and budget ledger | Accepted-terminal certification and per-ruleset MCTS admission |
| 6 | Evidence cards, mechanical record analyzer, heat maps, diagram atlas and reproducible offline report | Admitted comparisons, exploit search and evidence-qualified shortlist |

## Verified engineering

The final local suite passed **937 tests in325.683s**, zero skips:51 additive
tests over the886-test Batch5 baseline. Changed-file Ruff, Python compilation,
both browser JavaScript syntax checks and diff whitespace checks passed.
Independent source and evidence reviews are recorded in the artifact index.
Exact final-tip CI is a separate post-push gate, reported on PR23.

Earlier browser verification exercised33 interaction chains across all seven
new rulesets, orientations, modes, takeover, endings, capture/topology, save/load,
resizing and fullscreen. The final report additionally passed desktop/narrow
filtering, section navigation, details, atlas and semantic-state checks. Screenshots
were inspected; the report had zero browser console errors or warnings.
The narrow coverage table scrolls within its container without page overflow.

Legacy seeded decisions, fixtures and save behavior remain protected. The lab
uses separate objective-aware provisional opponents, not Classic profiles or the
Personal model. No Personal model was written. Research MCTS is not a public
difficulty. Graph construction adds no live-game action or time ceiling.

## What the report contains—and does not

The authenticated report accounts for25 audited browser exports. It selects the
final13 engineering scripts and explicitly excludes12 superseded Matrix2 copies.
The selected scripts contain40 rules actions,25 placements and9 constructions;
planted construction is one action counted in both placement/construction totals.
They include one captured junction and one deliberately accepted scripted ending.
They are not13 natural games, human observations or comparative-agent samples.

Outputs include16 evidence cards,40 D6 spatial/phase diagram classes and49 raw
event heat maps, across seven Toy-board script strata. The93 output files plus
their manifest regenerate byte-for-byte. Spatial diagram classes omit some
history: neither repeated discoveries nor strategically equivalent positions are
inferred. Heat maps count executed scripted events, not learned playing styles.
Objective scores and original-point control are recorded separately.

All cards retain zero certified development/holdout positions, zero admitted
agents and zero comparative games. Strategic depth, exploit resistance, natural
closure and human aesthetic outcomes are unmeasured. The qualified shortlist is
empty. Rule-concept inventories and design hypotheses are separate evidence
types, never ingredients in an aggregate beauty score.

The existing [rules/evidence specification](rules-lab-evidence.md) contains a
finite-state termination argument. It is not an all-position implementation
proof, a practical game-length bound or evidence of satisfying closure.

## Preserved negative result

The [bootstrap report](rules-lab-bootstrap-report.md) is binding. Its first frozen
32-task cohort stopped at a20-second task guard:6 legacy-Toy tasks completed
partial/unknown,8 tasks were interrupted and18 never started. All14 started
process groups were cleaned up. None was independently certified.

This is an operational feasibility negative, not an MCTS admission failure or a
rules defect. MCTS was not run. The6 completed jobs do not establish comparable
runtime for dual-provider certification, Beginner positions or full proofs.
Consequently, the required full-cohort projection with30% safety allowance cannot
be justified. Increasing guards, changing candidates or substituting native-only
matches would change the frozen experiment; none was done.

The one official research ledger charged **20.186600923538208 seconds** of the
129600-second allowance. The remaining allowance is not exhausted, but it is not
permission to bypass the gate. Implementation, tests and old-record analysis are
engineering work, separate from charged proof/calibration/match work.

## Best next steps: proposed continuation, not a launch

1. Review the playable lab and this exact negative result. Keep PR23 draft and
   preserve PR20–22. Do not claim all six research batches completed.
2. Predeclare a small certification-feasibility study. Measure transition,
   producer and independent-checker cost separately on fixed, comparable tasks
   before reserving larger cohorts. Keep timeout/unknown outcomes in the data.
3. In a separately versioned corpus, investigate naturally reachable near-terminal
   positions with genuine competing actions. Preserve the current early-game
   corpus as diagnostic material; do not replace it silently or fabricate superko
   histories. Local capture/rescue certificates remain distinct from accepted-score
   optimality, including legitimate sacrifices and equivalent best actions.
4. Only after useful exact labels are affordable, freeze disjoint development and
   holdout sets and run the three already implemented search recipes. Admit each
   ruleset under both rollout policies before its comparative games. Defer larger
   2048/4096 tiers until measured throughput and decision stability justify them.
5. Then compare construction with static geometry and no-construction controls,
   followed by exploit search. Human readability and beauty still require people.

For design attention only—not a results ranking—the most economical first
questions are Y construction's shared-liberty tempo, Line Breath's simpler scoring,
and planted-Y's commitment cost. Six-spoke, passage, group-penalty and majority
variants remain valid contrasting hypotheses. No candidate is dropped on this
basis, and no replacement corpus or new research job is authorized by this report.

## Reproduction and exact continuation

The report source parent is `e8e428ad31e594c3843ed29eb7ccee6311900f0f`; actual
new report-tool hashes are recorded separately. This avoids claiming those tools
already existed at their evidence parent. Compact links are in
[the Batch6 index](elves/rules-lab-v1-batch6-artifacts.json).

From the PR23 worktree, with the existing external evidence directory available:

```bash
python3 -m research.harness.lab_analysis_cli \
  --external-root /Users/armand/Development/varde-research/rules-lab-v1 \
  --output-dir /Users/armand/Development/varde-research/rules-lab-v1/report-reproduction-new \
  --source-commit e8e428ad31e594c3843ed29eb7ccee6311900f0f
```

The destination must not exist and must be outside the repository. Open its
`index.html`; no network service or research execution is needed. The loader
authenticates fixed inputs before analysis and publishes its manifest last.
Raw records/screenshots remain local; the compact index does not pretend to
redistribute their contents.

Before any research continuation: read the survival guide, verify exact heads,
source/manifest hashes and the unchanged single ledger; reconcile the interrupted
cohort explicitly; obtain a separately approved, predeclared comparable-measurement
plan. Do not reset the ledger, retry the stopped cohort automatically, relax its
guards, tune against holdout, or overwrite the Personal model. The user merges.
