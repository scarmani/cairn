/* Pure local laboratory records. Import validation is structural, not replay. */
(function expose(root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.VardeLabRecord = api;
})(typeof window === "object" ? window : null, function factory() {
  "use strict";
  const RULES = new Set(["line-breath", "gjerde-majority", "breath-connection", "junction-y", "junction-six", "junction-planted", "junction-passage"]);
  const BUILD = {"junction-y": ["construct", 2], "junction-six": ["construct", 1], "junction-planted": ["plant", 2], "junction-passage": ["construct", 3]};
  const TOP = ["format", "version", "source", "session_id", "rules", "board_size", "catalog_version", "initial_seats", "status", "actions", "final_score"];
  const AFTER = ["to_move", "actor_color", "actor_seat", "seats", "end_acceptances", "finished", "accepted", "resumption_used", "consecutive_passes", "swap_available", "moves_played", "placements_played", "constructions_played", "topology", "score", "original_control"];
  const COLORS = ["B", "W"], SEATS = ["S1", "S2"];
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const canonical = (value) => {
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
    if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
    return JSON.stringify(value);
  };
  const equal = (left, right) => canonical(left) === canonical(right);
  const coordOrder = (a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] ?? 0) - (b[2] ?? 0);
  const fail = (message) => { throw new Error(message); };
  function fields(value, expected, label) {
    if (!value || typeof value !== "object" || Array.isArray(value)
        || !equal(Object.keys(value).sort(), [...expected].sort())) fail(`Invalid ${label} fields`);
  }
  function integer(value, label, minimum = 0) {
    if (!Number.isSafeInteger(value) || value < minimum) fail(`Invalid ${label} integer`);
  }
  function point(value) {
    if (!Array.isArray(value) || value.length !== 2) fail("Invalid coordinate");
    value.forEach((coordinate) => integer(coordinate, "coordinate", -Number.MAX_SAFE_INTEGER));
  }
  function score(value, label) {
    fields(value, COLORS, label);
    Object.values(value).forEach((number) => integer(number, label, label === "score" ? -Number.MAX_SAFE_INTEGER : 0));
  }
  function seats(value) {
    fields(value, COLORS, "seats");
    if (!equal(Object.values(value).sort(), SEATS)) fail("Only bijective S1/S2 neutral seats are allowed");
  }
  function actionShape(value, rules) {
    if (!value || typeof value !== "object" || typeof value.action !== "string") fail("Invalid action");
    const kind = value.action;
    if (kind === "construct" || kind === "plant") {
      fields(value, ["action", "face", "orientation"], "construction");
      point(value.face);
      integer(value.orientation, "orientation");
      const [expected, count] = BUILD[rules] || [null, 0];
      if (kind !== expected || value.orientation >= count) fail("Action or orientation unavailable for these rules");
    } else if (kind === "play") {
      fields(value, ["action", "point"], "placement"); point(value.point);
    } else if (["pass", "swap", "accept", "resume"].includes(kind)) {
      fields(value, ["action"], "administrative action");
    } else fail("Unsupported lab record action");
    return kind;
  }
  function afterShape(value, rules) {
    fields(value, AFTER, "after projection"); seats(value.seats);
    if (!COLORS.includes(value.to_move)) fail("Invalid next color");
    ["finished", "accepted", "resumption_used", "swap_available"].forEach((key) => {
      if (typeof value[key] !== "boolean") fail(`Invalid ${key} flag`);
    });
    ["consecutive_passes", "moves_played", "placements_played", "constructions_played"].forEach((key) => integer(value[key], key));
    if (value.consecutive_passes > 2 || value.finished !== (value.consecutive_passes === 2)) fail("Inconsistent ending/pass projection");
    const accepts = value.end_acceptances;
    if (!Array.isArray(accepts) || accepts.some((seat) => !SEATS.includes(seat))
        || !equal(accepts, [...new Set(accepts)].sort())) fail("Invalid neutral acceptance list");
    if (value.accepted) {
      if (!value.finished || value.actor_color !== null || value.actor_seat !== null) fail("Accepted state must have no next actor");
      if (accepts.length !== (value.resumption_used ? 1 : 2)) fail("Invalid terminal acceptance count");
    } else {
      if (!COLORS.includes(value.actor_color) || value.actor_seat !== value.seats[value.actor_color]) fail("Invalid acting neutral seat");
      if (!value.finished && (accepts.length || value.actor_color !== value.to_move)) fail("Invalid live actor or acceptance");
      if (value.finished && accepts.length > 1) fail("Too many pending acceptances");
    }
    if (!Array.isArray(value.topology)) fail("Invalid topology");
    const count = (BUILD[rules] || [null, 0])[1], faces = new Set();
    value.topology.forEach((row) => {
      if (!Array.isArray(row) || row.length !== 3) fail("Invalid topology row");
      point(row.slice(0, 2)); integer(row[2], "orientation");
      const face = JSON.stringify(row.slice(0, 2));
      if (row[2] >= count || faces.has(face)) fail("Invalid or duplicate topology face");
      faces.add(face);
    });
    if (!equal(value.topology, [...value.topology].sort(coordOrder)) || value.topology.length !== value.constructions_played) fail("Noncanonical topology or construction count");
    score(value.score, "score"); score(value.original_control, "original control");
  }
  function capturesShape(value) {
    fields(value, ["original", "junction", "waves"], "captures");
    integer(value.original, "original captures"); integer(value.junction, "junction captures");
    if (!Array.isArray(value.waves)) fail("Invalid capture waves");
    const seen = new Set();
    value.waves.forEach((wave) => {
      if (!Array.isArray(wave) || !wave.length) fail("Invalid empty capture wave");
      wave.forEach((coordinate) => {
        point(coordinate);
        const key = JSON.stringify(coordinate);
        if (seen.has(key)) fail("Duplicate captured coordinate");
        seen.add(key);
      });
      if (!equal(wave, [...wave].sort(coordOrder))) fail("Capture wave points must be canonical");
    });
    if (seen.size !== value.original + value.junction) fail("Capture totals and wave coordinates differ");
  }
  function validateLabRecordShape(record) {
    fields(record, TOP, "lab record");
    if (record.format !== "varde-lab-playtest" || record.version !== 2) fail("Unsupported lab record");
    if (record.source !== "browser-local-hotseat" || typeof record.session_id !== "string" || !UUID.test(record.session_id)) fail("Invalid local source or UUID");
    fields(record.rules, ["id", "revision"], "rules");
    if (!RULES.has(record.rules.id) || record.rules.revision !== "0.1") fail("Unsupported lab rules/revision");
    integer(record.board_size, "board size"); integer(record.catalog_version, "catalog version", 1);
    if (![3, 4, 5, 6].includes(record.board_size)) fail("Unsupported lab board size");
    seats(record.initial_seats);
    if (!equal(record.initial_seats, {B: "S1", W: "S2"})) fail("Initial neutral seats must be B:S1/W:S2");
    if (!["active", "complete"].includes(record.status) || !Array.isArray(record.actions)) fail("Invalid record status or action list");
    let previous = null, currentSeats = record.initial_seats;
    const counters = {moves_played: 0, placements_played: 0, constructions_played: 0};
    record.actions.forEach((row, index) => {
      fields(row, ["index", "action", "actor", "elapsed_ms", "captures", "after"], "action row");
      integer(row.index, "action index");
      if (row.index !== index) fail("Nonsequential action index");
      const kind = actionShape(row.action, record.rules.id);
      fields(row.actor, ["seat", "color"], "actor");
      const actor = previous ? {seat: previous.actor_seat, color: previous.actor_color} : {seat: "S1", color: "B"};
      if (!equal(row.actor, actor) || actor.seat === null) fail("Action actor differs from recorded predecessor");
      if (index === 0 && kind !== "play") fail("First action must be original placement");
      integer(row.elapsed_ms, "elapsed time"); capturesShape(row.captures);
      if (!["play", "plant"].includes(kind) && !equal(row.captures, {original: 0, junction: 0, waves: []})) fail("Administrative or empty construction action cannot capture");
      const after = row.after;
      afterShape(after, record.rules.id);
      const expectedSeats = kind === "swap" ? {B: currentSeats.W, W: currentSeats.B} : currentSeats;
      if (!equal(after.seats, expectedSeats)) fail("Unexplained neutral seat reassignment");
      counters.moves_played += Number(["play", "plant", "construct", "pass"].includes(kind));
      counters.placements_played += Number(["play", "plant"].includes(kind));
      counters.constructions_played += Number(["construct", "plant"].includes(kind));
      Object.keys(counters).forEach((key) => { if (after[key] !== counters[key]) fail("Action/counter structure differs"); });
      currentSeats = after.seats; previous = after;
    });
    const complete = previous !== null && previous.accepted;
    if ((record.status === "complete") !== complete) fail("Completion requires accepted terminal");
    if (complete) {
      score(record.final_score, "score");
      if (!equal(record.final_score, previous.score)) fail("Final score differs from last accepted score");
    } else if (record.final_score !== null) fail("Active record cannot have final score");
    return copy(record);
  }
  function identities(view) {
    if (!view || view.experimental !== true || view.match?.mode !== "hotseat" || !RULES.has(view.rules)) fail("Recording requires a hotseat laboratory game");
    const ids = {};
    COLORS.forEach((color) => {
      const seat = view.match.seats?.[color];
      if (seat?.kind !== "human" || typeof seat.identity !== "string" || !seat.identity) fail("Recording requires two human seats");
      ids[color] = seat.identity;
    });
    if (ids.B === ids.W || (!view.accepted && view.actor_seat !== ids[view.actor_color])) fail("Invalid actual actor identity");
    return ids;
  }
  function projection(view, neutral) {
    const ids = identities(view);
    const translate = (identity) => {
      const color = COLORS.find((item) => ids[item] === identity);
      if (!color) fail("Unknown current acceptance identity");
      return neutral[color];
    };
    const output = {};
    AFTER.forEach((key) => {
      if (!["seats", "end_acceptances", "actor_seat"].includes(key)) output[key] = copy(view[key]);
    });
    output.seats = copy(neutral);
    output.actor_seat = view.actor_seat === null ? null : translate(view.actor_seat);
    if (!Array.isArray(view.match.end_acceptances)) fail("Missing seat acceptances");
    output.end_acceptances = view.match.end_acceptances.map(translate).sort();
    afterShape(output, view.rules);
    return output;
  }
  function createLabRecord(view, {sessionId, catalogVersion}) {
    identities(view);
    if (/^[0-9a-f]{32}$/.test(sessionId)) sessionId = `${sessionId.slice(0, 8)}-${sessionId.slice(8, 12)}-${sessionId.slice(12, 16)}-${sessionId.slice(16, 20)}-${sessionId.slice(20)}`;
    const initial = projection(view, {B: "S1", W: "S2"});
    if (initial.moves_played || initial.placements_played || initial.constructions_played || initial.topology.length
        || initial.finished || initial.accepted || initial.resumption_used || initial.swap_available
        || initial.consecutive_passes || initial.actor_color !== "B" || initial.end_acceptances.length
        || !Array.isArray(view.points) || !view.points.length || view.points.some((point) => !Array.isArray(point.stack) || point.stack.length)) fail("Start requires a fresh game before the opening");
    return validateLabRecordShape({
      format: "varde-lab-playtest", version: 2, source: "browser-local-hotseat", session_id: sessionId,
      rules: {id: view.rules, revision: view.rules_revision}, board_size: view.n,
      catalog_version: catalogVersion, initial_seats: {B: "S1", W: "S2"},
      status: "active", actions: [], final_score: null,
    });
  }
  function appendLabAction(record, {action, before, after, elapsedMs}) {
    const next = validateLabRecordShape(record);
    if (next.status === "complete") fail("Accepted record cannot continue");
    [before, after].forEach((view) => {
      identities(view);
      if (view.rules !== next.rules.id || view.rules_revision !== next.rules.revision || view.n !== next.board_size) fail("Displayed game differs from record");
    });
    const kind = actionShape(action, next.rules.id);
    const previous = next.actions.at(-1)?.after;
    const neutral = previous?.seats || next.initial_seats;
    const projectedBefore = projection(before, neutral);
    if (previous && !equal(previous, projectedBefore)) fail("Displayed game differs from recorded prefix");
    if (!previous) createLabRecord(before, {sessionId: next.session_id, catalogVersion: next.catalog_version});
    const idsBefore = identities(before), idsAfter = identities(after);
    const expectedIds = kind === "swap" ? {B: idsBefore.W, W: idsBefore.B} : idsBefore;
    if (!equal(idsAfter, expectedIds)) fail("Actual identities changed outside the recorded action");
    const nextNeutral = kind === "swap" ? {B: neutral.W, W: neutral.B} : neutral;
    const projectedAfter = projection(after, nextNeutral);
    if (before.legal_actions !== undefined
        && (!Array.isArray(before.legal_actions) || !before.legal_actions.some((item) => equal(item, action)))) fail("Action was not in the authoritative legal action list");
    integer(elapsedMs, "elapsed time");
    const afterPoints = new Map(after.points.map((point) => [JSON.stringify(point.coord), point]));
    const captured = {original: 0, junction: 0, waves: []};
    const removed = new Set();
    before.points.forEach((point) => {
      if (typeof point.original !== "boolean") fail("Missing original-point classification");
      const key = JSON.stringify(point.coord), advanced = afterPoints.get(key);
      if (!advanced) fail("Permanent topology point disappeared");
      if (point.stack.length && !advanced.stack.length) {
        captured[point.original ? "original" : "junction"] += 1;
        removed.add(key);
      }
    });
    if (["play", "plant"].includes(kind)) {
      if (!Array.isArray(after.capture_waves)) fail("Missing capture wave telemetry");
      captured.waves = after.capture_waves.map((wave) => copy(wave).sort(coordOrder));
    }
    capturesShape(captured);
    const wavePoints = captured.waves.flat().map((point) => JSON.stringify(point));
    if (!equal([...removed].sort(), wavePoints.sort())) fail("Capture waves differ from removed stones");
    next.actions.push({index: next.actions.length, action: copy(action),
      actor: {seat: projectedBefore.actor_seat, color: before.actor_color}, elapsed_ms: elapsedMs,
      captures: captured, after: projectedAfter});
    next.status = after.accepted ? "complete" : "active";
    next.final_score = after.accepted ? copy(after.score) : null;
    return validateLabRecordShape(next);
  }
  return Object.freeze({createLabRecord, appendLabAction, validateLabRecordShape});
});
