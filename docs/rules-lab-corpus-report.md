# Rules Laboratory candidate corpus: structural report

Status: mechanically replayed candidates, **not certified decisions**. No proof,
MCTS decision, comparative game or official research window ran in Batch5D.
The frozen rules and all existing production/search sources are unchanged.

Generated from source parent `47f5a87d7c8a672e06c8398b9333889fd44a7e75` plus
the exact new source hashes in [the artifact index](elves/rules-lab-v1-batch5d-artifacts.json).
The parent is not claimed to contain the new modules. Runtime source verification
checks their actual bytes, not just the Git label.

## Recorded sample

The authoring table was frozen before compilation:16 short templates for each
of16 definitions on both Toy/n3 and Beginner/n4. No policy chose the moves and
no legal alternatives were searched to repair an authored chain.

| Structural disposition | Count | Meaning |
| --- | ---: | --- |
| Candidate | 476 | At least two legal actions; no optimality claim |
| Single action | 32 | Once-resumed ending with one compulsory acceptance |
| Spatial duplicate | 2 | Passage orientations equivalent under the conservative D6 diagram filter |
| Invalid origin | 2 | Rosette's authored cap attempt is rejected at action index5, on both sizes |
| Accepted terminal | 0 | The table contains pending ending decisions, not accepted final roots |

All512 proposals remain visible in the [compact candidate index](elves/rules-lab-v1-candidate-index.json).
The invalid Rosette sequences were not replaced. They are authoring negatives,
not evidence of a broken rule. Labels such as “near fence” or “connection” describe
intended motifs, not a proof that a move is good, necessary or game-optimal.

After deduplication, each definition has14 holdout candidates across the two
sizes. Development has16 each except Rosette and Passage, which have14 each.
These are only candidate counts. Every certified count is0 and admission is
incomplete. The ten lab/static-control definitions have dual mechanical origin
replay; the six legacy definitions retain the explicit shared-mechanics limitation.

## Reproducibility and claim limits

The D6 filter transforms actual graph edges, original/scoring points, junction
spokes, fixed initial geometry, stones and administrative phases together.
It deliberately omits forbidden history and journal order to avoid padding the
corpus with the same diagram. It is never a repetition key or search cache key.
Full origin fingerprints remain separate. Splits are deterministic, hash-salted,
spatially disjoint and frozen before proof or search outcomes.

First compilation took91.429seconds. Full mechanical regeneration and canonical
raw/compact byte comparison finished at222.952seconds total. These are engineering
replay measurements, not proof/MCTS throughput or research-budget projections.

From the repository root, this read-only command regenerates the same canonical
compact index on stdout. Redirect it only to a new external output location if
an artifact is desired; it does not launch research or open a budget ledger.

```sh
python3 - <<'PY'
from research.harness.lab_corpus import compile_corpus
from research.harness.lab_corpus_candidates import authored_candidates, trusted_sources
from research.harness.lab_terminal_cert import canonical_json
m = compile_corpus(authored_candidates(),
    source_parent='47f5a87d7c8a672e06c8398b9333889fd44a7e75',
    trusted_sources=trusted_sources())
print(canonical_json(m.compact_index()))
PY
```

Raw manifest SHA256:`d1dc7d7bd23b036862ddcffe9915fb5b7932147c838f93c4ef29fea9e255f7fc`.
Compact file SHA256:`5b0cedefb4b8ced6ce8786ac5cb197b79d8c9c76117a8eccc5e59eeb8c123561`.
Semantic hashes differ intentionally from whole-file hashes; both are retained.
External raw root:`/Users/armand/Development/varde-research/rules-lab-v1/`.

Verification:738 tests pass in215.425seconds, zero skips (41 additive); scoped
Ruff, Python compilation and both JavaScript syntax checks pass. Independent
source/table/artifact review clean. Exact closure-tip CI is recorded in the run
guide after push, not inferred from local tests.

Next is trusted proof-job integration and the three frozen research MCTS recipes.
The predeclared32-task charged bootstrap is a bounded throughput probe, not a
certificate collection. Comparative matches still require the complete per-rule
independent-corpus and MCTS gates. No balance, depth, beauty or strength claim
follows from this candidate inventory.
