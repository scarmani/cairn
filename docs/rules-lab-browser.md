# Experimental browser and local records contract

Batch4D implementation contract, revision0.1, frozen at green oracle8c590d4
before browser changes. It implements the approved plan without changing rules,
native weights, oracle logic, saved-game formats or research admission gates.
The bounded advisory failed; no returned prompt or approval is claimed.

## Selection and presentation

- Experimental lab is an explicit new-game switch. Off preserves ordinary
  choices/defaults; on additionally permits the seven experimental_available
  registry entries. Static controls never appear. Loading a lab save enables the
  switch and shows its actual rules without starting another game.
- Lab new requests include experimental:true and omit all profile fields. Keep
  the previous Classic profile selections for later use, but hide profile and
  Personal training controls while lab setup or a lab game is active. Explain
  that Casual/Standard are provisional objective-aware agents; MCTS remains
  unmeasured and absent from public difficulty selection.
- Board-size labels reflect lab units: original vertices, lines, or Majority
  cells/lines. Do not label a72-line Toy game as54points. Preserve legacy labels.
- Projection/radius remains exact. Unused centers are interior construction
  markers, not playable empty points or liberties. Draw actual server edges,
  distinctive zero-point active hubs, and Majority ownership/counts. Flat lab
  games omit stack side glyphs. Do not double already-doubled cell coordinates.

## Interaction and state ownership

- Clicking an unused legal site selects a preview only. Show its exact spokes,
  legal orientation options, explicit Construct/Plant and Cancel. Arrow keys
  cycle available orientations, Enter confirms, Escape cancels when preview is
  active and focus is not in a form control. Never invent a legal orientation.
- Compare typed point/site targets in one nearest-distance scan using CSS-to-
  canvas conversion and deterministic ties. Active hubs are ordinary placement
  targets; unused centers remain construction targets. Clear preview on every
  state transition, replacement or load. Toy–Full, resize and fullscreen remain
  readable/clickable without overlap or a changing lattice extent.
- Inspection shows actual neighbors, distinct group liberties, scoring role,
  activation/orientation and absent-versus-empty state. Use server facts rather
  than reconstructing rules in JavaScript.
- Every lab human action uses the structured /api/action representation, including
  play, construction, planting, pass, takeover, acceptance and resumption. Legacy
  routes remain unchanged. Pending two-pass ending is not final; show actual
  actor, provisional result, and legal Accept/Resume controls. Only accepted
  terminal state is final. Lock input on computer_can_act for lab endings too.
- Preserve atomic computer requests, exact Step, paused new/loaded spectators,
  Play/Pause, local speed and capture-wave ordering. Serialize browser mutations:
  replacement cannot race an in-flight computer/human/new/load request; cancel
  scheduled timers before replacement and reject stale response adoption. Pause
  during a committed request adopts that one action but schedules no successor.
- render_game_to_text includes topology, sites/orientations, legal structured
  actions, separate counters, actual actor/accepted state, preview/inspection,
  provisional native status and unmeasured MCTS evidence.

## Laboratory local-record version2

Preserve version1 human-study records/validators unchanged. Add a separate
`varde-lab-playtest` format at version2, source `browser-local-hotseat`. Start only
from a fresh hotseat lab game before the opening. No names, free text, timestamps,
snapshot blobs, actual server seat identities or network submission. These are
local observations, not a qualified human study or agent research evidence.

Exact top-level fields: format, version, source, session_id (UUID),
rules {id,revision}, board_size, catalog_version, initial_seats {B:S1,W:S2},
status (active/complete), actions, final_score (null unless accepted).
Only the seven public lab IDs at revision0.1 and n3–6 are supported.

Each action row has exactly index, action (shared structured wire),
actor {seat,color}, elapsed_ms, captures {original,junction,waves}, and after.
The after projection contains exactly to_move, actor_color, actor_seat,
seats {B:Sx,W:Sy}, end_acceptances, finished, accepted, resumption_used,
consecutive_passes, swap_available, moves_played, placements_played,
constructions_played, topology, score {B,W}, original_control {B,W}.
Neutral S1/S2 identities follow the actual identity exchange. Accepted actors
are null; pending endings retain the actual actor even if it differs from to_move.
Preserve capture-wave order with canonical point order within each wave.
Classify captured lines by original, not scoring (Majority lines score no area).
Never carry a previous capture wave into an administrative action's record.

`web/lab-record.js` exposes pure detached helpers:
createLabRecord(view,{sessionId,catalogVersion}),
appendLabAction(record,{action,before,after,elapsedMs}), and
validateLabRecordShape(record). No DOM/fetch/model writes. Reject unknown fields,
invalid finite integer/types/orientations/identity mappings/counter structure.
Browser import reports structural validation only, never mechanical certification;
it neither replaces the displayed game nor resumes recording the imported file.
If record append fails after a successful server action, adopt the authoritative
new game view, freeze the last valid record prefix and explain the interruption.
Do not keep a stale displayed board or invent a missing event.

`research/harness/lab_record.py` supplies validate_lab_record_shape and
replay_lab_record plus a repository-relative input-path CLI returning a report
on stdout. Replay uses fresh game_factory/RulesState with S1/S2 identities and
the shared RulesAction/apply_action interface for every recorded action. Check
each pre-action actor, every after field, captures, topology and final status.
Return mechanical verification/action count/accepted state/replay hash separately
from the record. No server, Personal model or native evaluator import/use.

## Verification and isolation

Add strict Python/JS schema parity and real shared-action replay tests. Full
528+ product tests, changed-file Ruff, Python compilation, JS syntax, frozen
legacy fixtures and native/oracle source hashes, independent review and exact-tip
CI must remain green. No old tests are removed, relaxed or skipped.

Real browser chains exercise all seven selections/openings/objectives; every
junction orientation preview/commit/cancel; reachable hub capture/reoccupation;
both takeover directions; human/computer and independent spectator settings;
paused save/load, exact Step/Play/Pause/speed and thinking lock; first acceptance,
other-seat resumption and final acceptance; record export/import/replay;
Toy/Full, resizing/fullscreen, actual text/inspection, screenshots and console.
Preserve legacy Classic/Breath-run and version1 save/record behavior. A minimal
favicon resource may remove the existing404; do not suppress console evidence.

No rules/server/native/oracle changes unless a demonstrated integration defect
needs a separately tested minimal correction. No game corpus certification,
calibration or research matches in this engineering unit. Research charge remains0.
