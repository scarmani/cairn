"""Offline Rules Laboratory evidence report; never launches research or a server.

The report is a view of authenticated engineering artifacts, not a substitute
for MCTS admission or human evaluation. Output directories are exclusive and
the final manifest is published only after every payload has been written.
"""

import argparse
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from lab_evidence import DIMENSIONS, canonical_bytes, validate_card  # noqa: E402
from research.harness.lab_proof_task import publish_json  # noqa: E402


FORMAT = "varde-lab-analysis-report"
VERSION = 1
CLAIM_LIMIT = (
    "Engineering scripts and mechanical diagrams only. No admitted comparative "
    "games, strategic-depth finding, human observation or beauty rating."
)
CSS = """
:root{color-scheme:light;--ink:#203b39;--muted:#61716d;--paper:#f6f4ec;
--line:#cdd8d0;--accent:#246d64;--warn:#916221}*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,sans-serif}
header,main,footer{max-width:1240px;margin:auto;padding:30px 34px}
header{padding-top:54px}h1{font-size:clamp(2rem,5vw,3.6rem);line-height:1.12;
letter-spacing:-.04em;max-width:850px;margin:12px 0 20px}h2{line-height:1.2}
.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:12px;font-weight:700}
.lede{max-width:850px;font-size:19px}.note{padding:16px 20px;border-left:4px solid
var(--warn);background:#fff8e8;max-width:1000px}.metrics{display:flex;flex-wrap:wrap;
gap:12px;margin:26px 0}.metric{padding:14px 20px;border:1px solid var(--line);
border-radius:12px;background:#fff;min-width:155px}.metric strong{display:block;
font-size:clamp(20px,3vw,29px);line-height:1.2;overflow-wrap:anywhere}.metric small,.muted{color:var(--muted)}
label{display:block;font-weight:650}select{font:inherit;padding:9px 12px;max-width:100%;
border:1px solid var(--line);border-radius:7px;background:white;color:var(--ink)}
nav{display:flex;gap:18px;flex-wrap:wrap;margin:18px 0}a{color:var(--accent)}
.card{border-top:1px solid var(--line);margin:28px 0;padding-top:18px}
.tag{display:inline-block;background:#e3ece7;border-radius:4px;padding:2px 7px;
font-size:12px;margin:0 6px 6px 0}.columns{display:grid;grid-template-columns:1fr 1fr;
gap:28px}.panel{background:white;border:1px solid var(--line);border-radius:12px;
padding:18px;min-width:0}.panel svg{display:block;width:100%;height:auto;max-height:430px}
details{border-bottom:1px solid var(--line);padding:10px 0}summary{cursor:pointer}
.dimension-value{white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0}
code{overflow-wrap:anywhere;font-size:.88em}table{border-collapse:collapse;width:100%;
margin:16px 0;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid
var(--line);vertical-align:top}.scroll{overflow:auto}figure{margin:0}figcaption{font-size:13px;
color:var(--muted)}.atlas{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
gap:16px}.atlas .panel svg{max-height:280px}[hidden]{display:none!important}
footer{font-size:13px;border-top:1px solid var(--line);padding-bottom:48px}
@media(max-width:700px){header,main,footer{padding:22px 18px}.columns{grid-template-columns:1fr}
.metric{min-width:130px;flex:1}.lede{font-size:17px}h1{font-size:2.2rem}}
"""
SCRIPT = """
'use strict';
const metadata=JSON.parse(document.getElementById('report-state').textContent);
const select=document.getElementById('ruleset-filter');
function filter(){for(const section of document.querySelectorAll('[data-ruleset]')){
section.hidden=select.value!=='all'&&section.dataset.ruleset!==select.value;}}
select.addEventListener('change',filter);filter();
window.render_game_to_text=()=>JSON.stringify({kind:'offline-evidence-report',
selected_ruleset:select.value,visible_cards:[...document.querySelectorAll('.evidence-card[data-ruleset]')]
.filter(x=>!x.hidden).map(x=>x.dataset.ruleset),...metadata});
window.advanceTime=async()=>{};
"""


def _text(value):
    return escape(str(value), quote=True)


def _describe(value):
    if value is None:
        return "Unmeasured"
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)


def render_card(card):
    """Render only schema-valid evidence; escape every user/data-derived string."""
    card = validate_card(card)
    rules = card["ruleset"]
    pieces = [f'<section class="card evidence-card" data-ruleset="{_text(rules)}" id="card-{_text(rules)}">',
              f'<h2>{_text(rules)} <small class="muted">revision {_text(card["revision"])}</small></h2>',
              '<span class="tag">No comparative qualification</span>',
              f'<span class="tag">MCTS: {_text(card["mcts_admission"]["status"])}</span>']
    for key in DIMENSIONS:
        item = card["dimensions"][key]
        pieces.append(
            f'<details><summary>{_text(key.replace("_", " ").title())} · '
            f'{_text(item["status"])}</summary><div class="dimension-value">'
            f'{_text(_describe(item["value"]))}</div><p class="muted">'
            f'{_text(item["uncertainty"])}</p><small>Scope: {_text(item["scope"])}; '
            f'sample size: {_text(item["sample_size"])}; source: {_text(item["source_kind"])}'
            f'</small><p><code>{_text("; ".join(item["provenance"]))}</code></p></details>'
        )
    pieces.append('<p class="muted">Human readability, beauty, replay desire and memorable '
                  'understanding: unmeasured. No qualified human study was conducted.</p></section>')
    return "".join(pieces)


def render_heatmap(stratum, kind):
    """Raw-count map on the original graph; never rotates counts through D6."""
    graph = stratum["base_projection"]["current_graph"]
    points = graph["points"]
    xs = [p[0] for p in points]
    ys = [-math.sqrt(3) * p[1] for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1)
    scale = 340 / span
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    def xy(point):
        return (200 + (point[0] - cx) * scale,
                200 + (-math.sqrt(3) * point[1] - cy) * scale)

    title = kind.replace("-", " ")
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" '
             f'role="img" aria-label="{_text(title)} raw scripted counts"><title>'
             f'{_text(title)} — scripted coverage, both colors</title>',
             '<rect width="400" height="400" rx="8" fill="#fcfbf7"/>']
    for a, b in graph["edges"]:
        x1, y1 = xy(a)
        x2, y2 = xy(b)
        parts.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" '
                     f'y2="{y2:.3f}" stroke="#d6ded9" stroke-width="1.2"/>')
    for point in points:
        x, y = xy(point)
        parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="2" fill="#a6b5ae"/>')
    counts = {}
    for row in stratum["heatmaps"]:
        if row["kind"] == kind:
            point = tuple(row["point"])
            if type(row["count"]) is not int or row["count"] < 1:
                raise ValueError("heatmap counts must be positive integers")
            counts[point] = counts.get(point, 0) + row["count"]
    for point, count in sorted(counts.items()):
        x, y = xy(point)
        radius = min(16, 7 + 2 * math.sqrt(count))
        color = "#ac6928" if kind == "construction" else "#246d64"
        parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{radius:.3f}" '
                     f'fill="{color}" opacity=".87"><title>{_text(point)}: '
                     f'{count} executed actions</title></circle><text x="{x:.3f}" '
                     f'y="{y + 4:.3f}" text-anchor="middle" font-family="sans-serif" '
                     f'font-size="11" fill="white">{count}</text>')
    if not counts:
        parts.append('<text x="200" y="388" text-anchor="middle" fill="#61716d" '
                     'font-family="sans-serif" font-size="12">No event in these scripts</text>')
    return "".join(parts) + "</svg>"


def render_html(bundle, analysis):
    """Self-contained, filterable report with no network or browser game API."""
    from research.harness.lab_record_analysis import render_diagram

    cards = [validate_card(card) for card in bundle["cards"]]
    if any(card["comparative_games"] or card["shortlist"]["qualified"]
           or card["mcts_admission"]["status"] == "admitted"
           or any(row["status"] != "unmeasured" for row in card["human_observations"].values())
           for card in cards):
        raise ValueError("this frozen report cannot publish comparative qualification")
    metadata = {"rulesets": len(cards), "scripted_traces": analysis["distinct_traces"],
                "atlas_classes": len(analysis["atlas"]), "admitted_games": 0,
                "human_observations": 0, "qualified_shortlist": [],
                "bundle_hash": bundle["bundle_hash"], "analysis_hash": analysis["analysis_hash"]}
    options = '<option value="all">All rulesets and controls</option>' + "".join(
        f'<option value="{_text(card["ruleset"])}">{_text(card["ruleset"])}</option>'
        for card in cards)
    body = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Varde · Rules Laboratory evidence</title>',
        '<link rel="icon" href="data:,">',
        f'<style>{CSS}</style></head><body><header>',
        '<div class="eyebrow">Varde · Rules Laboratory · experimental</div>',
        '<h1>A playable laboratory.<br>An honest evidence boundary.</h1>',
        '<p class="lede">Seven new rulesets are implemented. Their strategic quality '
        'has not been established. This report separates checked mechanics, scripted '
        'examples and the research that remains blocked.</p>',
        '<div class="note"><strong>Research gate: certification incomplete.</strong> '
        'The first bootstrap stopped at its task-time guard. No position was certified; '
        'MCTS and comparative matches were not run. This is not evidence of a rules defect.</div>',
        '<div class="metrics">',
        f'<div class="metric"><strong>{len(cards)}</strong><small>rule/control cards</small></div>',
        f'<div class="metric"><strong>{analysis["distinct_traces"]}</strong>'
        '<small>selected scripted traces</small></div>',
        '<div class="metric"><strong>0</strong><small>admitted comparative games</small></div>',
        '<div class="metric"><strong>Unmeasured</strong><small>human beauty & readability</small></div>',
        '</div><label for="ruleset-filter">Inspect a ruleset</label>',
        f'<select id="ruleset-filter">{options}</select>',
        '<nav aria-label="Report sections"><a href="#cards">Evidence cards</a>'
        '<a href="#coverage">Script coverage</a><a href="#atlas">Mechanical atlas</a>'
        '<a href="#limits">Limits & next gate</a></nav></header><main>',
        '<section id="cards"><h2>Evidence cards</h2><p>Every dimension has its own '
        'status, provenance and uncertainty. Missing evidence is not a zero rating.</p>',
        "".join(render_card(card) for card in cards), '</section>',
        '<section id="coverage"><h2>Script coverage, not playing style</h2>',
        f'<p>{len(bundle["record_selection"]["selected"])} final UI scripts are selected '
        f'from {bundle["record_selection"]["audited"]} audited exports. '
        f'The {len(bundle["record_selection"]["excluded"])} superseded Matrix 2 records '
        'are preserved but not counted again. These deliberate scripts do not establish '
        'natural game length, balance or closure. Board size and accepted status are '
        'recorded separately in the analysis JSON.</p>',
    ]
    for row in analysis["strata"]:
        rules = row["rules"]["id"]
        counts = row["counters"]
        body.append(f'<section data-ruleset="{_text(rules)}" class="card"><h3>'
                    f'{_text(rules)} · n={row["board_size"]}</h3><div class="scroll"><table>'
                    '<thead><tr><th>Traces</th><th>Actions</th><th>Placements</th>'
                    '<th>Constructions</th><th>Captured originals / hubs</th>'
                    '<th>Friendly / enemy contacts</th></tr></thead><tbody><tr>'
                    f'<td>{row["distinct_traces"]}</td><td>{counts["rules_actions"]}</td>'
                    f'<td>{counts["placements"]}</td><td>{counts["constructions"]}</td>'
                    f'<td>{row["captures"]["original"]} / {row["captures"]["junction"]}</td>'
                    f'<td>{row["contact"]["friendly"]} / {row["contact"]["enemy"]}</td>'
                    '</tr></tbody></table></div><div class="columns">')
        for kind in ("construction", "enemy-contact"):
            body.append(f'<figure class="panel">{render_heatmap(row, kind)}<figcaption>'
                        f'{_text(kind.replace("-", " ").title())}: raw executed-point '
                        'counts, both colors. Original graph backdrop; newly built centers '
                        'may appear between its vertices. No strategic frequency estimate.'
                        '</figcaption></figure>')
        body.append('</div></section>')
    body.extend(['</section><section id="atlas"><h2>Mechanical motif atlas</h2>',
                 '<p>These are D6 spatial/phase diagram classes of scripted frames, not '
                 'independently discovered strategic motifs. The picture key deliberately '
                 'omits some history and cannot prove strategic equivalence or best play.</p>'])
    for card in cards:
        rules = card["ruleset"]
        rows = [row for row in analysis["atlas"] if row["projection"]["rules_id"] == rules]
        if not rows:
            continue
        body.append(f'<details data-ruleset="{_text(rules)}"><summary>{_text(rules)} · '
                    f'{len(rows)} diagram classes</summary><div class="atlas">')
        for row in rows:
            members = row["members"]
            caption = "; ".join(f'{item["source_id"]} · action {item["action_index"]}' for item in members)
            body.append(f'<figure class="panel">{render_diagram(row["projection"])}'
                        f'<figcaption><code>{_text(row["key"][:16])}</code> · '
                        f'{row["occurrences"]} frame occurrences<p>{_text(caption)}</p>'
                        '</figcaption></figure>')
        body.append('</div></details>')
    body.extend(['</section><section id="limits"><h2>What remains unmeasured</h2>',
                 '<p>The comparative shortlist is empty. Depth, exploit resistance, '
                 'natural closure, behavioral diversity and all human aesthetic measures '
                 'remain open questions. No high-budget recipe has been admitted.</p>',
                 '<p>Further charged research needs a separately predeclared comparable '
                 'measurement continuation. Preserve the existing ledger and interrupted '
                 'task accounting; do not silently increase timeouts, replace difficult '
                 'positions, substitute native-only games or promote scripts into evidence.</p>',
                 '</section></main><footer>', _text(CLAIM_LIMIT),
                 '<p>Evidence source commit: <code>', _text(bundle["source"]["commit"]),
                 '</code>. Tool/input hashes and exact records are in the adjacent JSON files '
                 'and output manifest. All computation and this report stay local. '
                 'PR23 remains draft and unmerged.</p></footer>',
                 '<script type="application/json" id="report-state">',
                 json.dumps(metadata, sort_keys=True, allow_nan=False).replace("<", "\\u003c"),
                 f'</script><script>{SCRIPT}</script></body></html>'])
    return "".join(body)


def _publish_text(path, text):
    """UTF-8 counterpart to immutable publish_json; no overwrite or symlink use."""
    path = Path(path)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("output parent must be a real directory")
    data = text.encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=".report-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def exclusive_output(path):
    """Reject repo-internal outputs and symlink components before any write."""
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("output path cannot contain a symlink")
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("raw report output must remain outside the repository")
    if not path.parent.is_dir():
        raise ValueError("output parent must already exist")
    path.mkdir()
    return path


def artifact_manifest(directory, *, metadata):
    rows = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("unexpected symlink output")
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.lstat().st_mode) or path.is_symlink():
            raise ValueError("unexpected nonregular output")
        data = path.read_bytes()
        rows.append({"path": path.relative_to(directory).as_posix(),
                     "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return {"format": FORMAT, "version": VERSION, "files": rows,
            "metadata": metadata, "claim_limit": CLAIM_LIMIT}


def generate_report(external_root, output_dir, source_commit):
    """Authenticate saved evidence, analyze fixed scripts, publish a local view."""
    from research.harness.lab_evidence_bundle import (
        build_evidence_bundle, load_evidence_inputs, render_evidence_markdown,
        validate_evidence_bundle,
    )
    from research.harness.lab_record_analysis import analyze_records, render_diagram

    paths = ("research/harness/lab_analysis_cli.py", "research/harness/lab_evidence_bundle.py",
             "research/harness/lab_record_analysis.py")

    def tool_hashes():
        return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}

    sources = tool_hashes()
    inputs = load_evidence_inputs(external_root=external_root, source_commit=source_commit)
    input_data = inputs.to_dict()
    bundle = validate_evidence_bundle(build_evidence_bundle(inputs).to_dict())
    entries = [{"record": row["record"], "provenance": row["provenance"],
                "source_sha256": row["sha256"]} for row in input_data["selected_records"]]
    analysis = analyze_records(entries).to_dict()
    html = render_html(bundle, analysis)
    markdown = render_evidence_markdown(bundle)
    if sources != tool_hashes():
        raise ValueError("report tool sources changed during analysis")
    output = exclusive_output(output_dir)
    publish_json(output / "evidence.json", bundle)
    publish_json(output / "analysis.json", analysis)
    _publish_text(output / "evidence.md", markdown)
    _publish_text(output / "index.html", html)
    (output / "atlas").mkdir()
    for row in analysis["atlas"]:
        key = row["key"]
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("invalid atlas content key")
        _publish_text(output / "atlas" / f"{key}.svg", render_diagram(row["projection"]))
    (output / "heatmaps").mkdir()
    for row in analysis["strata"]:
        rules = row["rules"]["id"]
        if rules not in {card["ruleset"] for card in bundle["cards"]}:
            raise ValueError("unknown map ruleset")
        for kind in ("construction", "enemy-contact", "friendly-contact", "original-placement",
                     "junction-placement", "capture-original", "capture-junction"):
            _publish_text(output / "heatmaps" / f'{rules}-n{row["board_size"]}-{kind}.svg',
                          render_heatmap(row, kind))
    if sources != tool_hashes():
        raise ValueError("report tool sources changed before publication")
    manifest = artifact_manifest(output, metadata={
        "evidence_parent": source_commit, "report_sources": sources,
        "bundle_hash": bundle["bundle_hash"], "analysis_hash": analysis["analysis_hash"],
        "selected_scripted_traces": analysis["distinct_traces"],
        "admitted_comparative_games": 0, "human_observations": 0,
        "publication": "manifest-last; interrupted directories are not completed reports",
    })
    publish_json(output / "manifest.json", manifest)
    return {"format": FORMAT, "version": VERSION, "status": "complete",
            "manifest_sha256": hashlib.sha256(canonical_bytes(manifest)).hexdigest(),
            "files": len(manifest["files"]), "bundle_hash": bundle["bundle_hash"],
            "analysis_hash": analysis["analysis_hash"], "claim_limit": CLAIM_LIMIT}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    try:
        result = generate_report(args.external_root, args.output_dir, args.source_commit)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
