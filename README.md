# Varde

[![Tests](https://github.com/scarmani/varde/actions/workflows/tests.yml/badge.svg)](https://github.com/scarmani/varde/actions/workflows/tests.yml)

Varde — formerly Cairn — is a two-player territory game on a honeycomb lattice. Players surround
territory, cover occupied columns, and use height-dependent sky liberties to
survive capture cascades.

**Naming.** The game was designed under the working title *Cairn* and renamed
**Varde** — the Norwegian word for a summit cairn — because an unrelated 2019
abstract strategy game already ships as *Cairn* (Matagot). Internal
identifiers keep the working name for compatibility: module names, the
`cairn-game` save format, the `~/.cairn` model directory, and historical file
paths. Existing saves and trained models load unchanged.

This repository contains a tested Python reference engine, an instrumented
self-play harness, and a dependency-free local web client for human and
computer play.

## Play locally

```bash
python3 engine/server.py
```

Open <http://127.0.0.1:8000>. The client supports Toy (54), Beginner (96),
Intermediate (150), and Full (216) point boards; proportional stones; legal-move
highlighting; stack inspection; sky indicators; pie-rule takeover; stepwise
capture highlighting; passing and one-time resumption; scoring; fullscreen;
and versioned save/load files.

### Play against the computer

Choose **Vs computer**, select Black or White, choose **Casual** or **Standard**
search, select a playing profile, and start a new game. Casual uses varied
one-ply choices; Standard uses bounded two-ply minimax. The **Personal** profile
adds a persistent learned linear correction to Standard. All levels use the rules engine's
real legality, skies, capture cascades, superko, pie rule, passing, and
resumption. Move explanations are optional and all computation stays local.

Choose **Watch two computers** for independent Black and White difficulties.
Spectator games start paused and provide Play/Pause, exactly-one-action Step,
and Slow/Normal/Fast playback. A loaded spectator save also starts paused.

Personal begins with zero learned weights, so it initially behaves exactly like
Standard. The learning panel runs separate deterministic background self-play
batches of 10, 50, or 200 games and supports progress, cancellation, and reset.
The model is saved atomically at `~/.cairn/advanced-model.json`. Training uses a
20N operational watchdog and discards incomplete training games; playable games
have no move or turn cutoff. Version-1 models are retained, identified in the
UI, and require Reset before clean V2 retraining. Training count is not a
strength claim.

For installed commands:

```bash
python3 -m pip install -e . --no-deps
varde-server
```

### Experimental Rules Laboratory

Enable **Experimental lab** to add seven revision-0.1 choices: Line Breath,
Gjerde Majority, Breath Connection, Y-Junction Go, Six-Spoke Go, Planted Y Go,
and Passage Go. Ordinary choices and defaults remain available unchanged.
The [frozen definitions](docs/rules-lab-specs.md) explain each independent change.

In junction games, click a dashed unused center to preview construction; choose
an orientation and explicitly confirm. With the board focused, arrow keys cycle
orientations, Enter confirms, and Escape cancels. Blue junctions persist after
capture but score zero; only original vertices score. Hover to inspect actual
neighbors, distinct liberties, and construction state.

Hotseat, Vs computer, and paused spectator playback are supported. Laboratory
Casual/Standard opponents are provisional and objective-aware: they do not use
Classic profiles or your Personal model. MCTS admission and comparative game
quality remain unmeasured; playable software is not evidence of strategic depth.

Lab saved games use version 2, while legacy saves remain version 1. Local hotseat
lab records use a separate `varde-lab-playtest` version-2 format. Browser import
checks structure only. Independently replay an exported record with:

```bash
python3 research/harness/lab_record.py /path/to/local-record.json
```

Replay checks the recorded legal actions and state transitions; it does not
qualify the record as a human study or comparative-agent result. Records stay
local and contain neutral seat identifiers rather than player names.

The [Rules Laboratory run report](docs/rules-lab-run-report.md) distinguishes the
completed playable implementation from blocked research: the first bounded
certification bootstrap produced no accepted certificate, so MCTS admission and
comparative matches were not launched. The new offline evidence CLI produces
16 cards, raw scripted-event maps and a mechanical diagram atlas without assigning
unmeasured strategic or human-aesthetic outcomes a score. Reproduction commands
and the exact continuation gate are in that report.

## Verify

```bash
python3 -m unittest discover -s engine -v
python3 -m pytest
python3 engine/selfplay.py 3 100 random
python3 engine/selfplay.py 3 100 greedy
python3 engine/selfplay.py 3 100 epsilon
```

The Batch-6 laboratory verification ran 937 tests with zero skips, including
legacy decision/save parity, immutable junction topology, independent mechanical
oracle checks, and cross-language local-record replay. The suite also covers geometry, terrain,
summits, flat capture, collar-dependent wells, wall stranding, eight-support
twin wells, multi-wave peeling, global mover-suicide, full-stack superko,
opening placement, pie-rule identity, resumption, scoring, serialization,
ruleset metadata, and the browser-facing public state, two computer seats,
legacy saves, deterministic Personal evaluation, model persistence, training
cancellation, frozen ruleset scoring, registry-driven exposure, native tactical
admission, terminal-score MCTS, byte-stable research resume, and the local
human-study record schema.

The `8N` limit used by diagnostic self-play is a watchdog for comparing
policies, not a game rule or playable-program ceiling. Full-superko Varde is
mathematically finite because terrain bounds every stack height and placements
cannot repeat a recorded position. A policy that reaches the watchdog is
reported as a long game; the application does not force it to end.

## Current diagnostic baseline

Seeded n=3 runs, 100 games per policy, cutoff at 8N turns:

| Policy | Finished | Placements | Cap share | Wave depth | Largest wave |
|---|---:|---:|---:|---:|---:|
| Random | 46% | 6.23N mean | 48.2% | max 5 | 53 |
| Greedy | 100% | 2.31N mean | 4.3% | max 1 | 11 |
| 15% epsilon-greedy | 100% | 3.02N mean | 13.6% | max 2 | 37 |

These policies diagnose engine behavior; they do not establish balance or
strategic quality. Greedy termination is partly induced by its rule to pass
when no placement immediately improves area score. Epsilon-greedy is the most
useful current smoke-test baseline: it activates stacking without producing
the random policy's cap-heavy grind.

### Computer-opponent validation

Twenty seeded n=3 computer-vs-computer games per level produced no illegal
actions or crashes. Casual finished 20/20 before the 8N watchdog (median 181.5,
maximum 236 turns). Standard also finished 20/20 naturally; 19 finished before
8N and one finished at 489 turns (9.06N), demonstrating why 8N is reported as
a measurement boundary rather than enforced as a rule. Standard decision p95
was about 30 ms during complete games; fresh-position p95 was about 27 ms at
n=3 and 196 ms at n=5, below the 500/1500 ms targets.

Fresh-position checks after adding Full and the learned evaluator measured p95
decision times of about 26 ms (Standard) and 44 ms (Personal) on Toy, and 411
ms / 682 ms on Full. An eight-game exploratory probe produced 3 wins and 5
losses for Personal against Standard with colors alternated. That sample is
deliberately reported as evidence that the learning loop runs—not as evidence
that Advanced is stronger.

After correcting the reply search and retraining Personal V2 from zero for 200 games, a
fresh 200-game paired gate scored 52.5% overall: 56.33% on Toy, 41.0% on
Beginner, one-sided 95% paired-bootstrap lower bound 47.0%, and average margin
-1.15. All games completed legally, but four strength criteria failed, so
Personal remains experimental. Current fresh-position p95 is about 30/55 ms on
Toy and 388/737 ms on Full for Standard/Personal. Reproduction commands and
the exact model checkpoint are in `research/`.

The V3 evaluator-profile cycle separates search difficulty (Casual/Standard)
from playing style. A deterministic 4,096-candidate MAP-Elites run over five
audit-retained evaluator features produced two shipped styles: **Mason**
(vertical play through covers, stacks, and durable skies) and **Surveyor**
(rim use and broad territorial reach). Both passed 100-pair strength and
behavior gates against Balanced; Raider and Weaver failed their predeclared
gates and are visible but unavailable. Profiles are offered as different, not
stronger — the catalog records `strength_claim: false`. The legacy Advanced
setting now loads as Standard difficulty with the Personal (learned) profile.
Evidence summaries live in `research/results/`.

## Layout

- `docs/varde-rules.md` — standalone rules, revision 1.3 (adds the stagnation ending)
- `docs/design-history.md` — design lineage, retired claims, and playtest gates
- `engine/varde.py` — reference rules engine and versioned snapshots
- `engine/opponent.py` — local Casual/Standard computer opponent with profile weights
- `engine/profiles.py` — versioned evaluator-profile catalog with validation evidence
- `engine/learning.py` — persistent linear model and background self-play trainer
- `engine/test_varde.py` — known-answer position and controller tests
- `engine/selfplay.py` — random, greedy, and epsilon-greedy telemetry
- `engine/server.py` — local JSON API and static-file server
- `research/` — reproducible V2 training, paired evaluation, and checkpoints
- `docs/playtest/` — neutral human-study protocol, briefs, forms, and gates
- `web/` — responsive canvas hotseat client
- `progress.md` — implementation and handoff log

## What remains experimental

The software is playable, but the game design is not declared final. Human
playtests must still evaluate collar strategy, well life versus classical eyes,
the summit-rule variant, saturation avoidance, board size, and swap balance.
The ruleset-promise program now uses independent native search and MCTS as a
computational falsification stage before structured human evaluation. No
variant is promoted until those generated gates and the human study pass.

For a scored human hotseat game, **Start local record** before move one and
**Export JSON** afterward. The recorder captures action timing and resolution
telemetry only in browser memory; it collects no names or device identifiers
and sends nothing to the server. **Import JSON** validates a record locally for
read-only inspection or re-export. The counterbalanced panel schedule and
engine-derived comprehension puzzles are generated with
`research/harness/human_study.py` as documented in the playtest protocol.
