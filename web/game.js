const canvas = document.querySelector("#game");
const ctx = canvas.getContext("2d");
const turnStatus = document.querySelector("#turn-status");
const message = document.querySelector("#message");
const passButton = document.querySelector("#pass-btn");
const swapButton = document.querySelector("#swap-btn");
const resumeButton = document.querySelector("#resume-btn");
const finishExtButton = document.querySelector("#finish-ext-btn");
const acceptButton = document.querySelector("#accept-btn");
const experimentalCheckbox = document.querySelector("#experimental-lab");
const constructionControls = document.querySelector("#construction-controls");
const constructionTitle = document.querySelector("#construction-title");
const orientationSelect = document.querySelector("#construction-orientation");
const confirmConstructionButton = document.querySelector("#confirm-construction-btn");
const cancelConstructionButton = document.querySelector("#cancel-construction-btn");
const labEvidence = document.querySelector("#lab-evidence");
const labEvidenceNote = document.querySelector("#lab-evidence-note");
const labInspector = document.querySelector("#lab-inspector");
const labInspectorNote = document.querySelector("#lab-inspector-note");
const sizeSelect = document.querySelector("#board-size");
const rulesSelect = document.querySelector("#ruleset");
const modeSelect = document.querySelector("#game-mode");
const colorSelect = document.querySelector("#human-color");
const difficultySelect = document.querySelector("#difficulty");
const profileSelect = document.querySelector("#profile");
const blackDifficultySelect = document.querySelector("#black-difficulty");
const blackProfileSelect = document.querySelector("#black-profile");
const whiteDifficultySelect = document.querySelector("#white-difficulty");
const whiteProfileSelect = document.querySelector("#white-profile");
const explainCheckbox = document.querySelector("#explain-moves");
const aiNote = document.querySelector("#ai-note");
const profileNote = document.querySelector("#profile-note");
const spectatorControls = document.querySelector("#spectator-controls");
const playButton = document.querySelector("#play-btn");
const stepButton = document.querySelector("#step-btn");
const speedSelect = document.querySelector("#playback-speed");
const playbackNote = document.querySelector("#playback-note");
const trainingGamesSelect = document.querySelector("#training-games");
const trainButton = document.querySelector("#train-btn");
const cancelTrainingButton = document.querySelector("#cancel-training-btn");
const resetTrainingButton = document.querySelector("#reset-training-btn");
const trainingStatus = document.querySelector("#training-status");
const newButton = document.querySelector("#new-btn");
const rulesetNote = document.querySelector("#ruleset-note");
const startRecordButton = document.querySelector("#start-record-btn");
const importRecordButton = document.querySelector("#import-record-btn");
const importRecordFile = document.querySelector("#import-record-file");
const exportRecordButton = document.querySelector("#export-record-btn");
const clearRecordButton = document.querySelector("#clear-record-btn");
const playtestStatus = document.querySelector("#playtest-status");
const loadButton = document.querySelector("#load-btn");
const saveButton = document.querySelector("#save-btn");
const trainingControls = document.querySelector("#training-controls");
const originalSizeLabels = new Map(Array.from(sizeSelect.options, (option) => [option.value, option.textContent]));

let game = null;
let projected = new Map();
let projectedSites = new Map();
let hoverKey = null;
let animation = null;
let lastFrame = performance.now();
let thinking = false;
let computerSequence = 0;
let actionInFlight = false;
let replacementInFlight = false;
let visual = null;
let watchPlaying = false;
let training = null;
let trainingPoll = null;
let profileCatalog = null;
let rulesetCatalog = null;
let playtestRecord = null;
let playtestImported = false;
let playtestLastActionAt = performance.now();
let playtestInterrupted = false;
let gameEpoch = 0;
let constructionPreview = null;
let hoverTarget = null;
let lastOrdinaryRuleset = "classic";

const savedSpeed = Number(
  localStorage.getItem("varde-playback-speed")
  ?? localStorage.getItem("cairn-playback-speed"),
);
const playbackSpeed = [1200, 500, 100].includes(savedSpeed) ? savedSpeed : 500;
speedSelect.value = String(playbackSpeed);

const BOARD_SCALE = 1.1;
const STONE_RADIUS_PER_SCALE = 0.8291732589425476;

const keyOf = (coord) => `${coord[0]},${coord[1]}`;

async function request(path, body = null) {
  const options = body === null ? {} : {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  };
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    if (window.location.protocol === "file:") {
      throw new Error(
        "Open Varde through its local server: run `python3 engine/server.py`, then visit http://127.0.0.1:8000.",
      );
    }
    throw new Error(
      "Cannot reach the Varde server. Run `python3 engine/server.py`, then reload http://127.0.0.1:8000.",
    );
  }
  const contentType = response.headers.get("Content-Type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    try {
      payload = await response.json();
    } catch (error) {
      // Fall through to the actionable protocol error below.
    }
  }
  if (payload === null) {
    if (response.status === 404 && path.startsWith("/api/")) {
      throw new Error(
        "The running Varde server is out of date. Stop it, run `python3 engine/server.py` again, then reload this page.",
      );
    }
    throw new Error(`The Varde server returned an invalid response for ${path}.`);
  }
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

function profileById(profileId) {
  return profileCatalog?.profiles?.find((profile) => profile.id === profileId);
}

function rulesetById(rulesetId) {
  return rulesetCatalog?.rulesets?.find((ruleset) => ruleset.id === rulesetId);
}

function isLabGame() { return game?.experimental === true; }
function isLabSetup() { return rulesetById(rulesSelect.value)?.experimental === true; }
function labContext() { return isLabGame() || isLabSetup(); }
function canCreateRuleset(ruleset) {
  return Boolean(ruleset && (ruleset.public_new_game || (
    experimentalCheckbox.checked && ruleset.experimental === true
    && ruleset.experimental_available === true
  )));
}
function labLegalAction(kind, point = null, orientation = null) {
  return game?.legal_actions?.find((action) => (
    action.action === kind
    && (point === null || keyOf(action.point || action.face) === keyOf(point))
    && (orientation === null || action.orientation === orientation)
  ));
}
function humanInputLocked() {
  return !game || thinking || actionInFlight || Boolean(
    isLabGame() ? game.match?.computer_can_act : game.match?.computer_turn,
  );
}

function localSessionId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const values = new Uint32Array(4);
  crypto.getRandomValues(values);
  return Array.from(values, (value) => value.toString(16).padStart(8, "0")).join("");
}

function updatePlaytestControls() {
  const canStart = Boolean(
    game
    && game.match?.mode === "hotseat"
    && game.moves_played === 0
    && (rulesetById(game.rules)?.status === "candidate" || (isLabGame() && window.VardeLabRecord))
    && !playtestRecord && !actionInFlight,
  );
  startRecordButton.disabled = !canStart;
  exportRecordButton.disabled = !playtestRecord;
  clearRecordButton.disabled = !playtestRecord;
  if (!playtestRecord) {
    if (game?.match?.mode !== "hotseat") {
      playtestStatus.textContent = "Recording is available only for two-player hotseat games";
    } else if (game.moves_played) {
      playtestStatus.textContent = "Start requires a fresh game before move one";
    } else {
      playtestStatus.textContent = "Ready before move one · local export · no names or network submission";
    }
    return;
  }
  const label = playtestInterrupted ? "Recording interrupted · last valid prefix frozen"
    : playtestImported
    ? `Imported ${playtestRecord.status}${playtestRecord.format === "varde-lab-playtest" ? " · structure checked only, not mechanically certified" : ""}`
    : playtestRecord.status === "complete" ? "Complete" : "Recording";
  playtestStatus.textContent = `${label} · ${playtestRecord.actions.length} action${playtestRecord.actions.length === 1 ? "" : "s"} · export stays on this device`;
}

function startPlaytestRecord() {
  if (
    !game
    || game.match?.mode !== "hotseat"
    || game.moves_played !== 0
    || actionInFlight
    || (!isLabGame() && rulesetById(game.rules)?.status !== "candidate")
  ) return;
  if (isLabGame()) {
    try {
      playtestRecord = window.VardeLabRecord.createLabRecord(game, {
        sessionId: localSessionId(), catalogVersion: rulesetCatalog.version,
      });
      playtestImported = false;
      playtestInterrupted = false;
      playtestLastActionAt = performance.now();
      updatePlaytestControls();
    } catch (error) { message.textContent = error.message; }
    return;
  }
  playtestRecord = {
    format: "varde-human-playtest",
    version: 1,
    session_id: localSessionId(),
    source: "browser-local-hotseat",
    rules: {
      id: game.rules,
      revision: rulesetById(game.rules).evaluation_id,
    },
    board_size: game.n,
    catalog_version: rulesetCatalog.version,
    native_evaluator_hash: rulesetCatalog.native_evaluators?.hash || null,
    status: "active",
    actions: [],
    final_score: null,
    resumption_used: false,
    ended_by_stagnation: false,
  };
  playtestImported = false;
  playtestInterrupted = false;
  playtestLastActionAt = performance.now();
  updatePlaytestControls();
}

function clearPlaytestRecord() {
  playtestRecord = null;
  playtestImported = false;
  playtestInterrupted = false;
  playtestLastActionAt = performance.now();
  updatePlaytestControls();
}

function actionKind(path) {
  return ({
    "/api/play": "play",
    "/api/pass": "pass",
    "/api/swap": "swap",
    "/api/extend": "extend",
    "/api/finish-extensions": "finish-extension",
    "/api/resume": "resume",
  })[path];
}

function capturePlaytestAction(path, body, before, next, actionAt) {
  if (playtestInterrupted) return;
  if (playtestRecord?.format === "varde-lab-playtest") {
    if (playtestImported || path !== "/api/action") return;
    playtestRecord = window.VardeLabRecord.appendLabAction(playtestRecord, {
      action: body, before, after: next,
      elapsedMs: Math.max(0, Math.round(actionAt - playtestLastActionAt)),
    });
    playtestLastActionAt = performance.now();
    updatePlaytestControls();
    return;
  }
  const kind = actionKind(path);
  if (!playtestRecord || playtestImported || !kind) return;
  if (playtestRecord.status === "complete" && kind !== "resume") return;
  if (kind === "resume") playtestRecord.status = "active";
  const waves = next.capture_waves || [];
  const stonesBefore = before.points.reduce(
    (count, point) => count + point.stack.length, 0,
  );
  const stonesAfter = next.points.reduce(
    (count, point) => count + point.stack.length, 0,
  );
  const placed = kind === "play" || kind === "extend" ? 1 : 0;
  playtestRecord.actions.push({
    index: playtestRecord.actions.length,
    kind,
    point: body.point ? [...body.point] : null,
    actor_color: before.to_move,
    elapsed_ms: Math.max(0, Math.round(actionAt - playtestLastActionAt)),
    move_before: before.moves_played,
    move_after: next.moves_played,
    captured: Math.max(0, stonesBefore + placed - stonesAfter),
    capture_waves: waves.map((wave) => wave.map((point) => [...point])),
    score_after: {...next.score},
  });
  playtestLastActionAt = performance.now();
  playtestRecord.resumption_used = Boolean(next.resumption_used);
  playtestRecord.ended_by_stagnation = Boolean(next.no_progress_end);
  if (next.finished) {
    playtestRecord.status = "complete";
    playtestRecord.final_score = {...next.score};
  } else {
    playtestRecord.status = "active";
    playtestRecord.final_score = null;
  }
  updatePlaytestControls();
}

function exportPlaytestRecord() {
  if (!playtestRecord) return;
  const blob = new Blob(
    [JSON.stringify(playtestRecord, null, 2)],
    {type: "application/json"},
  );
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `varde-playtest-${playtestRecord.session_id}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function assertImportedPlaytestRecord(record) {
  const pii = new Set([
    "name", "email", "phone", "address", "birthday", "birthdate", "age",
    "gender", "race", "ethnicity", "employer", "location", "ip", "user_agent",
  ]);
  const inspect = (value) => {
    if (Array.isArray(value)) {
      value.forEach(inspect);
    } else if (value && typeof value === "object") {
      Object.entries(value).forEach(([key, item]) => {
        if (pii.has(key.toLowerCase())) throw new Error(`Forbidden identity field: ${key}`);
        inspect(item);
      });
    }
  };
  inspect(record);
  const allowed = new Set([
    "format", "version", "session_id", "source", "rules", "board_size",
    "catalog_version", "native_evaluator_hash", "status", "actions",
    "final_score", "resumption_used", "ended_by_stagnation",
  ]);
  if (
    !record
    || typeof record !== "object"
    || Object.keys(record).length !== allowed.size
    || Object.keys(record).some((key) => !allowed.has(key))
    || record.format !== "varde-human-playtest"
    || record.version !== 1
    || record.source !== "browser-local-hotseat"
    || !/^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/.test(record.session_id)
    || !Number.isInteger(record.board_size)
    || !Number.isInteger(record.catalog_version)
    || !/^[0-9a-f]{64}$/.test(record.native_evaluator_hash)
    || !Array.isArray(record.actions)
    || !["active", "complete"].includes(record.status)
    || typeof record.resumption_used !== "boolean"
    || typeof record.ended_by_stagnation !== "boolean"
  ) throw new Error("Invalid Varde playtest record");
  const rules = rulesetById(record.rules?.id);
  if (
    !record.rules
    || Object.keys(record.rules).length !== 2
    || !Object.hasOwn(record.rules, "id")
    || !Object.hasOwn(record.rules, "revision")
    || !rules
    || rules.status !== "candidate"
    || record.rules.revision !== rules.evaluation_id
  ) throw new Error("Unknown or mismatched rules revision");
  const actionFields = new Set([
    "index", "kind", "point", "actor_color", "elapsed_ms", "move_before",
    "move_after", "captured", "capture_waves", "score_after",
  ]);
  const actionKinds = new Set([
    "play", "pass", "swap", "extend", "finish-extension", "resume",
  ]);
  const validScore = (score) => (
    score
    && typeof score === "object"
    && Object.keys(score).length === 2
    && Number.isInteger(score.B)
    && Number.isInteger(score.W)
  );
  if (
    (record.status === "complete" && !validScore(record.final_score))
    || (record.status === "active" && record.final_score !== null)
  ) throw new Error("Invalid final score");
  record.actions.forEach((action, index) => {
    const pointRequired = action?.kind === "play" || action?.kind === "extend";
    const validPoint = Array.isArray(action?.point)
      && action.point.length === 2
      && action.point.every(Number.isInteger);
    if (
      !action
      || typeof action !== "object"
      || Object.keys(action).length !== actionFields.size
      || Object.keys(action).some((key) => !actionFields.has(key))
      || action.index !== index
      || !actionKinds.has(action.kind)
      || !["B", "W"].includes(action.actor_color)
      || !Number.isInteger(action.elapsed_ms)
      || action.elapsed_ms < 0
      || !Number.isInteger(action.move_before)
      || action.move_before < 0
      || !Number.isInteger(action.move_after)
      || action.move_after < 0
      || !Number.isInteger(action.captured)
      || action.captured < 0
      || !Array.isArray(action.capture_waves)
      || !validScore(action.score_after)
      || (pointRequired ? !validPoint : action.point !== null)
    ) throw new Error(`Invalid action ${index}`);
  });
  return record;
}

function populateRulesetSelect(catalog) {
  const selected = rulesSelect.value || "classic";
  const visible = catalog.rulesets.filter((ruleset) => !ruleset.experimental || experimentalCheckbox.checked);
  rulesSelect.replaceChildren(...visible.map((ruleset) => {
    const option = document.createElement("option");
    option.value = ruleset.id;
    option.disabled = !canCreateRuleset(ruleset);
    const suffix = ruleset.experimental ? " — experimental" : ruleset.public_new_game ? "" : ` — ${ruleset.status}`;
    option.textContent = `${ruleset.label}${suffix}`;
    return option;
  }));
  rulesSelect.value = visible.some((spec) => spec.id === selected) ? selected : lastOrdinaryRuleset;
}

function updateRulesetSetup({coerceSize = false} = {}) {
  const ruleset = rulesetById(rulesSelect.value);
  if (!ruleset) return;
  for (const option of sizeSelect.options) {
    const size = Number(option.value);
    option.disabled = ruleset.allowed_sizes
      ? !ruleset.allowed_sizes.includes(size)
      : size < ruleset.min_size || size > ruleset.max_size;
    if (ruleset.experimental && size <= 6) {
      const name = ["", "", "", "Toy", "Beginner", "Intermediate", "Full"][size];
      const lines = 9 * size * size - 3 * size;
      const cells = 3 * size * (size - 1) + 1;
      const unit = ruleset.id === "gjerde-majority" ? `${cells} cells · ${lines} lines`
        : ruleset.geometry === "kagome-lines" ? `${lines} lines` : `${6 * size * size} original vertices`;
      option.textContent = `${name} (${unit})`;
    } else {
      option.textContent = originalSizeLabels.get(option.value);
    }
  }
  const selectedSize = Number(sizeSelect.value);
  if (coerceSize && (selectedSize < ruleset.min_size || selectedSize > ruleset.max_size)) {
    sizeSelect.value = String(Math.min(4, ruleset.max_size));
  }
  const status = ruleset.status === "candidate" ? "evaluation candidate" : ruleset.status;
  const reason = ruleset.archival_reason ? ` ${ruleset.archival_reason}` : "";
  rulesetNote.textContent = `${ruleset.label} ${ruleset.evaluation_id} · ${status}. ${ruleset.description}${reason}`;
  newButton.disabled = !canCreateRuleset(ruleset) || actionInFlight;
  updateSetupVisibility();
}

function installRulesetCatalog(catalog) {
  rulesetCatalog = catalog;
  populateRulesetSelect(catalog);
  updateRulesetSetup();
}

function populateProfileSelect(select, prefix) {
  const selected = select.value || "balanced";
  select.replaceChildren(...profileCatalog.profiles.map((profile) => {
    const option = document.createElement("option");
    option.value = profile.id;
    option.disabled = !profile.available;
    option.textContent = `${prefix}${profile.label}${profile.available ? "" : " — unavailable"}`;
    return option;
  }));
  select.value = profileById(selected)?.available ? selected : "balanced";
}

function installProfileCatalog(catalog) {
  profileCatalog = catalog;
  populateProfileSelect(profileSelect, "Profile: ");
  populateProfileSelect(blackProfileSelect, "Black profile: ");
  populateProfileSelect(whiteProfileSelect, "White profile: ");
  updateProfileNote();
}

function describeProfile(profileId) {
  const profile = profileById(profileId);
  if (!profile) return "Profile information unavailable.";
  if (profile.id === "personal") {
    const model = training?.model || game?.learning || profile;
    const count = model.games_trained ?? profile.training_count ?? 0;
    if (!count) {
      return "Personal is untrained and currently equivalent to Balanced.";
    }
    return `Personal adds your local model trained on ${count} game${count === 1 ? "" : "s"}.`;
  }
  return profile.description;
}

function updateProfileNote() {
  if (!profileNote) return;
  if (modeSelect.value === "watch") {
    profileNote.textContent = `Black — ${describeProfile(blackProfileSelect.value)} White — ${describeProfile(whiteProfileSelect.value)}`;
  } else {
    profileNote.textContent = describeProfile(profileSelect.value);
  }
}

function syncSetupControls() {
  if (!game?.match) return;
  if (isLabGame() && !experimentalCheckbox.checked) {
    experimentalCheckbox.checked = true;
    populateRulesetSelect(rulesetCatalog);
  }
  if (game.rules) rulesSelect.value = game.rules;
  updateRulesetSetup();
  modeSelect.value = game.match.mode;
  if (game.match.human_color) colorSelect.value = game.match.human_color;
  difficultySelect.value = game.match.difficulty;
  if (game.match.profile) profileSelect.value = game.match.profile;
  if (game.match.seats?.B?.difficulty) {
    blackDifficultySelect.value = game.match.seats.B.difficulty;
  }
  if (game.match.seats?.B?.profile) {
    blackProfileSelect.value = game.match.seats.B.profile;
  }
  if (game.match.seats?.W?.difficulty) {
    whiteDifficultySelect.value = game.match.seats.W.difficulty;
  }
  if (game.match.seats?.W?.profile) {
    whiteProfileSelect.value = game.match.seats.W.profile;
  }
  explainCheckbox.checked = game.match.explain;
  updateSetupVisibility();
}

function updateSetupVisibility() {
  const versus = modeSelect.value === "computer";
  const watch = modeSelect.value === "watch";
  document.querySelectorAll(".versus-setting").forEach((element) => {
    element.hidden = !versus;
  });
  document.querySelectorAll(".watch-setting").forEach((element) => {
    element.hidden = !watch;
  });
  document.querySelectorAll(".any-computer-setting").forEach((element) => {
    element.hidden = !(versus || watch);
  });
  spectatorControls.hidden = !watch;
  const lab = labContext();
  if (lab) {
    profileSelect.hidden = true;
    blackProfileSelect.hidden = true;
    whiteProfileSelect.hidden = true;
    document.querySelector("#profile-controls").hidden = true;
  }
  trainingControls.hidden = lab;
  labEvidence.hidden = !lab;
  labInspector.hidden = !isLabGame();
  document.querySelector("#sky-legend").hidden = isLabGame();
  document.querySelectorAll(".lab-legend").forEach((element) => {
    element.hidden = !isLabGame() || !game.construction_sites?.length;
  });
  document.querySelector("#inspection-hint").textContent = isLabGame()
    ? "Hover to inspect actual connections · press F for fullscreen"
    : "Hover to inspect stacks · press F for fullscreen";
  labEvidenceNote.textContent = "Casual and Standard are provisional objective-aware opponents. MCTS admission is unmeasured; no comparative game evidence. Classic profiles and Personal learning are not used.";
  updateProfileNote();
}

function captureWaveDuration() {
  return game?.match?.mode === "watch" && Number(speedSelect.value) === 100 ? 80 : 500;
}

function stopPlayback({cancelWait = true} = {}) {
  watchPlaying = false;
  playButton.textContent = "Play";
  playbackNote.textContent = "Paused";
  if (cancelWait) computerSequence += 1;
  if (!actionInFlight) thinking = false;
  updateControls();
}

function setGame(next, schedule = true) {
  game = next;
  constructionPreview = null;
  hoverTarget = null;
  hoverKey = null;
  constructionControls.hidden = true;
  sizeSelect.value = String(game.n);
  animation = game.capture_waves.length
    ? {
      waves: game.capture_waves,
      elapsed: 0,
      index: 0,
      duration: captureWaveDuration(),
    }
    : null;
  message.textContent = "";
  syncSetupControls();
  const decision = game.computer_decision;
  aiNote.textContent = decision?.reason_text || "";
  updateControls();
  draw();
  if (schedule) scheduleComputerMove();
}

function updateControls() {
  if (!game) return;
  // During play the whole-region score is misleading (one stone can
  // "border" the entire open board), so show outright control instead.
  const control = game.control || game.score;
  const rulesTag = game.rules && game.rules !== "classic" ? ` · ${game.rules}` : "";
  const controlText = `Black ${control.B} · White ${control.W}${rulesTag}`;
  const scoreText = `Black ${game.score.B} · White ${game.score.W}${rulesTag}`;
  const lab = isLabGame();
  const labControl = game.original_control || control;
  const currentText = lab
    ? `Current score: ${scoreText} · original control ${labControl.B}–${labControl.W}`
    : controlText;
  const setTurnText = (primary, secondary) => {
    const small = document.createElement("small");
    small.textContent = secondary;
    turnStatus.replaceChildren(document.createTextNode(primary), small);
  };
  if (thinking) {
    setTurnText("Computer is thinking…", currentText);
  } else if (lab && game.finished && !game.accepted) {
    const lead = game.score.B === game.score.W ? "Tied score"
      : `${game.score.B > game.score.W ? "Black" : "White"} leads`;
    setTurnText(
      `${game.current_player} · ${game.actor_color === "B" ? "Black" : "White"} decides`,
      `${lead} · pending acceptance · ${scoreText}`,
    );
  } else if (lab ? game.accepted : game.finished) {
    const result = game.score.B === game.score.W
      ? "Draw"
      : `${game.score.B > game.score.W ? "Black" : "White"} wins`;
    const ending = game.no_progress_end ? " · ended by stagnation" : "";
    setTurnText(result, `${scoreText}${ending}`);
  } else {
    setTurnText(
      `${game.current_player} · ${(lab ? game.actor_color : game.to_move) === "B" ? "Black" : "White"} to move`,
      `${currentText} · ${lab ? `${game.placements_played} placements · ${game.constructions_played} constructions` : `move ${game.moves_played + 1}`}`,
    );
  }
  const extendOnly = ["breath-rescue", "breath-run"].includes(game.rules);
  if (
    !thinking && !game.finished && !game.match?.computer_turn
    && game.points?.some((p) => p.extension)
  ) {
    message.textContent = extendOnly
      ? "Amber points are free rescues — but taking any replaces your move this turn."
      : "Free extension available — the amber point rescues your group without costing your move.";
  }
  finishExtButton.hidden = !game.extension_only_turn;
  finishExtButton.disabled = thinking || Boolean(game.match?.computer_turn);
  const computerTurn = humanInputLocked();
  passButton.disabled = lab ? computerTurn || !labLegalAction("pass")
    : game.finished || game.moves_played === 0 || computerTurn;
  swapButton.hidden = lab ? !labLegalAction("swap") : !game.swap_available || computerTurn;
  swapButton.disabled = lab && computerTurn;
  resumeButton.hidden = lab ? !labLegalAction("resume") : !game.resumption_available;
  resumeButton.disabled = computerTurn || Boolean(game.match?.computer_can_act);
  acceptButton.hidden = !lab || !labLegalAction("accept");
  acceptButton.disabled = computerTurn;
  confirmConstructionButton.disabled = computerTurn || !constructionPreview;
  orientationSelect.disabled = computerTurn;
  newButton.disabled = actionInFlight || !canCreateRuleset(rulesetById(rulesSelect.value));
  loadButton.disabled = actionInFlight;
  saveButton.disabled = actionInFlight;
  document.querySelectorAll(".controls select, .controls input").forEach((element) => {
    element.disabled = actionInFlight;
  });
  canvas.style.cursor = computerTurn ? "wait" : "default";
  const watch = game.match?.mode === "watch";
  spectatorControls.hidden = !watch;
  playButton.disabled = !watch || replacementInFlight || !game.match?.computer_can_act;
  stepButton.disabled = !watch || watchPlaying || thinking || actionInFlight || !game.match?.computer_can_act;
  if (watch && !game.match?.computer_can_act && watchPlaying) {
    stopPlayback({cancelWait: false});
  }
  updatePlaytestControls();
}

async function scheduleComputerMove(forceOne = false) {
  if (!game?.match?.computer_can_act || thinking || actionInFlight) return;
  const watch = game.match.mode === "watch";
  if (watch && !watchPlaying && !forceOne) return;
  const sequence = ++computerSequence;
  const epoch = gameEpoch;
  thinking = true;
  updateControls();
  const waves = game.capture_waves?.length || 0;
  const waveDelay = watch
    ? Math.max(forceOne ? 0 : Number(speedSelect.value), waves * captureWaveDuration())
    : Math.max(350, waves * 520);
  await new Promise((resolve) => setTimeout(resolve, waveDelay));
  // A canceled timer no longer owns thinking state; a replacement game may
  // already have scheduled its own computer action.
  if (sequence !== computerSequence || epoch !== gameEpoch) return;
  try {
    actionInFlight = true;
    updateControls();
    const next = await request("/api/computer", {});
    if (epoch !== gameEpoch) return;
    actionInFlight = false;
    thinking = false;
    setGame(next, !forceOne && (!watch || watchPlaying));
  } catch (error) {
    actionInFlight = false;
    thinking = false;
    if (watch) stopPlayback({cancelWait: false});
    message.textContent = error.message;
    updateControls();
  }
}

async function humanAction(path, body = {}) {
  if (humanInputLocked()) return;
  const before = game;
  const epoch = gameEpoch;
  const actionAt = performance.now();
  try {
    actionInFlight = true;
    updateControls();
    const next = await request(path, body);
    if (epoch !== gameEpoch) return;
    actionInFlight = false;
    let recordError = null;
    try {
      capturePlaytestAction(path, body, before, next, actionAt);
    } catch (error) {
      playtestInterrupted = true;
      recordError = `Game action succeeded, but recording stopped: ${error.message}. The last valid record prefix is still exportable.`;
    }
    setGame(next);
    if (recordError) message.textContent = recordError;
  } catch (error) {
    actionInFlight = false;
    message.textContent = error.message;
    updateControls();
  }
}

async function replaceGame(path, body) {
  if (actionInFlight) return;
  stopPlayback();
  const epoch = ++gameEpoch;
  constructionPreview = null;
  constructionControls.hidden = true;
  actionInFlight = true;
  replacementInFlight = true;
  updateControls();
  try {
    const next = await request(path, body);
    if (epoch !== gameEpoch) return;
    actionInFlight = false;
    clearPlaytestRecord();
    setGame(next, false);
  } catch (error) {
    if (epoch === gameEpoch) message.textContent = error.message;
  } finally {
    if (epoch === gameEpoch) {
      actionInFlight = false;
      replacementInFlight = false;
      thinking = false;
      updateControls();
    }
  }
  // A rejected load leaves the old game intact. Restore its automatic human-
  // versus-computer turn, while spectator games remain deliberately paused.
  if (game?.match.mode !== "watch") scheduleComputerMove();
}

function makeProjection() {
  const cart = game.points.map((p) => ({
    key: keyOf(p.coord),
    x: p.coord[0],
    y: -p.coord[1] * Math.sqrt(3),
  }));
  const xs = cart.map((p) => p.x);
  const ys = cart.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 58;
  const baseScale = Math.min(
    (canvas.width - 2 * pad) / Math.max(1, maxX - minX),
    (canvas.height - 2 * pad) / Math.max(1, maxY - minY),
  );
  const scale = baseScale * BOARD_SCALE;
  const offsetX = (canvas.width - (maxX - minX) * scale) / 2;
  const offsetY = (canvas.height - (maxY - minY) * scale) / 2;
  const spacing = 2 * scale;
  const stoneRadius = STONE_RADIUS_PER_SCALE * scale;
  visual = {
    scale,
    spacing,
    stoneRadius,
    lineWidth: Math.max(1.5, Math.min(3, spacing * 0.05)),
    hitRadius: spacing * 0.48,
  };
  projected = new Map(cart.map((p) => [p.key, {
    x: offsetX + (p.x - minX) * scale,
    y: offsetY + (p.y - minY) * scale,
  }]));
  // Gjerde: points are lines of the hex grid; their endpoints live at
  // twice the vertex coordinates, in the same space as the sums.
  visual.projectRaw = (x, y) => ({
    x: offsetX + (x - minX) * scale,
    y: offsetY + (-y * Math.sqrt(3) - minY) * scale,
  });
  projectedSites = new Map((game.construction_sites || []).filter((site) => !site.active)
    .map((site) => [keyOf(site.face), visual.projectRaw(...site.center)]));
}

function previewSite() {
  return constructionPreview && game?.construction_sites?.find(
    (site) => keyOf(site.face) === keyOf(constructionPreview.face),
  );
}

function selectConstruction(site) {
  if (humanInputLocked() || site.active || !site.legal_orientations.length) return;
  constructionPreview = {face: [...site.face], orientation: site.legal_orientations[0], kind: site.kind};
  hoverTarget = {kind: "site", key: keyOf(site.face)};
  orientationSelect.replaceChildren(...site.legal_orientations.map((orientation) => {
    const option = document.createElement("option");
    option.value = String(orientation);
    option.textContent = `Orientation ${orientation + 1} · corners ${site.orientations[orientation].map((index) => index + 1).join("–")}`;
    return option;
  }));
  constructionTitle.textContent = `${site.kind === "plant" ? "Plant" : "Construct"} at face ${site.face.join(", ")}`;
  confirmConstructionButton.textContent = site.kind === "plant" ? "Plant junction" : "Construct junction";
  constructionControls.hidden = false;
  canvas.focus({preventScroll: true});
  updateControls();
  draw();
  fitFullscreen();
}

function cancelConstruction() {
  constructionPreview = null;
  constructionControls.hidden = true;
  draw();
  fitFullscreen();
}

async function confirmConstruction() {
  const site = previewSite();
  if (humanInputLocked() || !site) return;
  const action = labLegalAction(site.kind, site.face, constructionPreview.orientation);
  if (!action) { cancelConstruction(); return; }
  await humanAction("/api/action", action);
}

function drawLabCells() {
  for (const cell of game.cells || []) {
    const center = visual.projectRaw(...cell.center);
    if (cell.owner) {
      ctx.beginPath();
      ctx.arc(center.x, center.y, visual.stoneRadius * 1.25, 0, Math.PI * 2);
      ctx.fillStyle = cell.owner === "B" ? "rgba(37,41,35,.15)" : "rgba(255,253,248,.62)";
      ctx.fill();
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `650 ${Math.max(8, visual.stoneRadius * 0.65)}px system-ui`;
    ctx.fillStyle = "#4e5149";
    ctx.fillText(`${cell.counts.B}:${cell.counts.W}`, center.x, center.y);
    if (cell.owner) {
      ctx.font = `700 ${Math.max(8, visual.stoneRadius * 0.56)}px system-ui`;
      ctx.fillText(`${cell.owner} +1`, center.x, center.y + visual.stoneRadius * 0.68);
    }
  }
}

function drawConstructionSites() {
  for (const site of game.construction_sites || []) {
    if (site.active) continue;
    const pos = projectedSites.get(keyOf(site.face));
    const selected = keyOf(site.face) === (constructionPreview && keyOf(constructionPreview.face));
    ctx.save();
    ctx.beginPath();
    ctx.setLineDash([visual.stoneRadius * 0.19, visual.stoneRadius * 0.17]);
    ctx.arc(pos.x, pos.y, visual.stoneRadius * (selected ? 0.60 : 0.42), 0, Math.PI * 2);
    ctx.strokeStyle = site.legal_orientations.length ? "rgba(48,94,137,.85)" : "rgba(83,89,94,.38)";
    ctx.lineWidth = Math.max(1.2, visual.lineWidth * 0.8);
    ctx.stroke();
    ctx.restore();
  }
  const site = previewSite();
  if (!site) return;
  const center = visual.projectRaw(...site.center);
  ctx.save();
  ctx.strokeStyle = "#287e8b";
  ctx.lineWidth = Math.max(2, visual.lineWidth * 1.5);
  ctx.setLineDash([visual.stoneRadius * 0.3, visual.stoneRadius * 0.16]);
  for (const index of site.orientations[constructionPreview.orientation]) {
    const corner = projected.get(keyOf(site.corners[index]));
    ctx.beginPath();
    ctx.moveTo(center.x, center.y);
    ctx.lineTo(corner.x, corner.y);
    ctx.stroke();
  }
  if (site.kind === "plant") {
    ctx.beginPath();
    ctx.arc(center.x, center.y, visual.stoneRadius, 0, Math.PI * 2);
    ctx.fillStyle = game.actor_color === "B" ? "rgba(37,41,35,.4)" : "rgba(255,253,248,.7)";
    ctx.fill();
    ctx.stroke();
  }
  ctx.restore();
}

function inspectionData() {
  if (!isLabGame()) return null;
  const target = hoverTarget || (constructionPreview && {kind: "site", key: keyOf(constructionPreview.face)});
  if (!target) return null;
  if (target.kind === "site") {
    const site = game.construction_sites.find((item) => keyOf(item.face) === target.key);
    if (!site) return null;
    return {kind: "site", face: site.face, center: site.center, active: site.active,
      legal_orientations: site.legal_orientations, orientation: site.orientation,
      construction_kind: site.kind, corners: site.corners, orientations: site.orientations,
      role: "Inactive center: absent from the graph, not an empty liberty."};
  }
  const point = game.points.find((item) => keyOf(item.coord) === target.key);
  if (!point) return null;
  const site = game.construction_sites?.find((item) => item.active && keyOf(item.center) === target.key);
  return {kind: "point", coord: point.coord, occupied: point.stack.at(-1) || null,
    original: point.original, scoring: point.scoring, center: point.center,
    neighbors: point.neighbors, distinct_group_liberties: point.group_libs,
    legal: point.legal, construction: site ? {face: site.face, permanent: true, orientation: site.orientation} : null,
    adjacent_cells: game.cells?.filter((cell) => cell.edges.some((edge) => keyOf(edge) === target.key))
      .map((cell) => ({face: cell.face, counts: cell.counts, owner: cell.owner})) || [],
  };
}

function updateLabInspector() {
  const info = inspectionData();
  if (!info) {
    labInspectorNote.textContent = "Hover over an intersection or a construction site to inspect its actual connections.";
  } else if (info.kind === "site") {
    const options = info.legal_orientations.length
      ? `legal orientations ${info.legal_orientations.map((index) => index + 1).join(", ")}` : "no construction is legal now";
    labInspectorNote.textContent = `Face ${info.face.join(",")} · center ${info.center.join(",")} · ${info.role} ${options}`;
  } else {
    const role = info.center ? "permanent junction · 0 points"
      : game.rules === "gjerde-majority" ? "original line · cells score, lines do not"
        : `original scoring ${game.points[0]?.segment ? "line" : "vertex"}`;
    const liberties = Number.isInteger(info.distinct_group_liberties)
      ? ` · ${info.distinct_group_liberties} distinct group liberties` : "";
    const construction = info.construction ? ` · orientation ${info.construction.orientation + 1}` : "";
    const cells = info.adjacent_cells.map((cell) => `cell ${cell.face.join(",")} B${cell.counts.B}/W${cell.counts.W}${cell.owner ? ` (${cell.owner} +1)` : " (unowned)"}`).join("; ");
    labInspectorNote.textContent = `${info.coord.join(",")} · ${info.occupied || "empty"} · ${role}${construction}${liberties} · neighbors ${info.neighbors.map((point) => `(${point.join(",")})`).join(" ")}${cells ? ` · ${cells}` : ""}`;
  }
}

function roundedRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function draw() {
  if (!game) return;
  makeProjection();
  const gradient = ctx.createRadialGradient(470, 290, 40, 470, 320, 620);
  gradient.addColorStop(0, "#f7edcf");
  gradient.addColorStop(1, "#d8c69f");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.lineCap = "round";
  if (isLabGame()) drawLabCells();
  const lineMode = game.points[0]?.segment != null;
  if (lineMode) {
    // Gjerde: draw the hex grid's lines themselves. Unclaimed lines
    // are faint; claimed lines are thick strokes in the stone colors.
    for (const point of game.points) {
      const [va, vb] = point.segment;
      const pa = visual.projectRaw(va[0] * 2, va[1] * 2);
      const pb = visual.projectRaw(vb[0] * 2, vb[1] * 2);
      const top = point.stack.at(-1);
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      if (!top) {
        ctx.strokeStyle = "rgba(83,71,50,.30)";
        ctx.lineWidth = Math.max(1, visual.lineWidth * 0.6);
      } else {
        ctx.strokeStyle = top === "B" ? "#252923" : "#f7f3e8";
        ctx.lineWidth = Math.max(4, visual.stoneRadius * 0.85);
      }
      ctx.stroke();
      if (top === "W") {
        ctx.strokeStyle = "#777369";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }
  } else {
    ctx.strokeStyle = "rgba(83,71,50,.48)";
    ctx.lineWidth = visual.lineWidth;
    for (const [a, b] of game.edges) {
      const pa = projected.get(keyOf(a));
      const pb = projected.get(keyOf(b));
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
    }
  }

  // Phantom edges: every rim point is missing a neighbor, and forgetting
  // that is the single most punishing misread in the game. Draw a stub
  // toward off-board space with a bar across its end: no liberty here.
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;
  for (const point of game.points) {
    if (!point.phantoms) continue;
    const pos = projected.get(keyOf(point.coord));
    const away = Math.atan2(pos.y - centerY, pos.x - centerX);
    for (let i = 0; i < point.phantoms; i += 1) {
      const angle = away + (i - (point.phantoms - 1) / 2) * 0.7;
      const sx = pos.x + Math.cos(angle) * visual.stoneRadius * 0.9;
      const sy = pos.y + Math.sin(angle) * visual.stoneRadius * 0.9;
      const ex = pos.x + Math.cos(angle) * visual.stoneRadius * 1.8;
      const ey = pos.y + Math.sin(angle) * visual.stoneRadius * 1.8;
      ctx.strokeStyle = "rgba(140,60,45,.5)";
      ctx.lineWidth = Math.max(1, visual.lineWidth * 0.6);
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(ex, ey);
      ctx.stroke();
      const bar = visual.stoneRadius * 0.45;
      ctx.beginPath();
      ctx.moveTo(ex + Math.cos(angle + Math.PI / 2) * bar,
                 ey + Math.sin(angle + Math.PI / 2) * bar);
      ctx.lineTo(ex + Math.cos(angle - Math.PI / 2) * bar,
                 ey + Math.sin(angle - Math.PI / 2) * bar);
      ctx.stroke();
    }
  }
  ctx.strokeStyle = "rgba(83,71,50,.48)";
  ctx.lineWidth = visual.lineWidth;

  const activeWave = animation && animation.index < animation.waves.length
    ? new Set(animation.waves[animation.index].map(keyOf))
    : new Set();

  if (isLabGame()) drawConstructionSites();

  for (const point of game.points) {
    const key = keyOf(point.coord);
    const pos = projected.get(key);
    const top = point.stack.at(-1);
    if (point.legal) {
      ctx.beginPath();
      ctx.arc(
        pos.x,
        pos.y,
        top ? visual.stoneRadius * 1.33 : visual.stoneRadius * 0.67,
        0,
        Math.PI * 2,
      );
      ctx.strokeStyle = point.extension
        ? "rgba(191,111,42,.95)"
        : "rgba(74,112,70,.75)";
      ctx.lineWidth = top ? visual.lineWidth : Math.max(1.5, visual.lineWidth * 0.7);
      ctx.stroke();
    }
    if (!top) {
      if (!lineMode && !(isLabGame() && point.center)) {
        ctx.beginPath();
        ctx.arc(
          pos.x,
          pos.y,
          visual.stoneRadius * (point.rim ? 0.22 : 0.27),
          0,
          Math.PI * 2,
        );
        ctx.fillStyle = point.deep ? "#725f3f" : "#8b7958";
        ctx.fill();
      }
    } else {
      const radius = visual.stoneRadius;
      if (!lineMode) {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = top === "B" ? "#252923" : "#f7f3e8";
        ctx.fill();
        ctx.strokeStyle = top === "B" ? "#050605" : "#777369";
        ctx.lineWidth = Math.max(1.5, visual.lineWidth * 0.75);
        ctx.stroke();

        const shown = isLabGame() && game.flat ? [] : point.stack.slice(-5);
        shown.forEach((color, index) => {
          ctx.fillStyle = color === "B" ? "#292d27" : "#f7f3e8";
          ctx.fillRect(
            pos.x + radius * 1.13,
            pos.y + radius * 0.53 - index * radius * 0.33,
            radius * 0.6,
            Math.max(2, radius * 0.27),
          );
        });
        if (point.stack.length > 1) {
          ctx.fillStyle = top === "B" ? "#fff" : "#222";
          ctx.font = `700 ${Math.max(8, radius * 0.67)}px system-ui`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(String(point.stack.length), pos.x, pos.y + 1);
        }
      }
      // Liberty warnings (flat rulesets): red ring at one liberty,
      // amber at two — the bookkeeping the lattice punishes hardest.
      if (point.group_libs === 1 || point.group_libs === 2) {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, radius * 1.18, 0, Math.PI * 2);
        ctx.strokeStyle = point.group_libs === 1
          ? "rgba(196,49,32,.9)"
          : "rgba(214,138,32,.75)";
        ctx.lineWidth = Math.max(
          1.5, visual.lineWidth * (point.group_libs === 1 ? 1.1 : 0.7),
        );
        ctx.stroke();
      }
    }
    if (isLabGame() && point.center) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, visual.stoneRadius * (top ? 1.09 : 0.63), 0, Math.PI * 2);
      ctx.strokeStyle = "#466a8d";
      ctx.lineWidth = Math.max(1.5, visual.lineWidth * 0.7);
      ctx.stroke();
      if (!top) {
        ctx.fillStyle = "#466a8d";
        ctx.font = `650 ${Math.max(8, visual.stoneRadius * 0.68)}px system-ui`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("0", pos.x, pos.y);
      }
    }
    if (point.sky) {
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y - visual.stoneRadius * 1.87);
      ctx.lineTo(pos.x + visual.stoneRadius * 0.4, pos.y - visual.stoneRadius * 1.33);
      ctx.lineTo(pos.x - visual.stoneRadius * 0.4, pos.y - visual.stoneRadius * 1.33);
      ctx.closePath();
      ctx.fillStyle = "#c67c25";
      ctx.fill();
    }
    if (activeWave.has(key)) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, visual.stoneRadius * 1.67, 0, Math.PI * 2);
      ctx.strokeStyle = "#e4572e";
      ctx.lineWidth = Math.max(3, visual.lineWidth * 2);
      ctx.stroke();
    }
  }

  if (isLabGame()) updateLabInspector();
  else if (hoverKey) drawInspector(hoverKey);
}

function drawInspector(key) {
  const point = game.points.find((p) => keyOf(p.coord) === key);
  if (!point) return;
  roundedRect(18, 18, 242, 78, 12);
  ctx.fillStyle = "rgba(255,253,247,.94)";
  ctx.fill();
  ctx.strokeStyle = "rgba(70,61,45,.25)";
  ctx.stroke();
  ctx.fillStyle = "#252822";
  ctx.textAlign = "left";
  ctx.font = "700 14px system-ui";
  ctx.fillText(`Point ${point.coord[0]}, ${point.coord[1]}`, 32, 43);
  ctx.font = "12px system-ui";
  const stack = point.stack.length ? point.stack.join(" → ") : "empty";
  ctx.fillText(`Stack: ${stack} · height ${point.stack.length}`, 32, 65);
  ctx.fillStyle = "#66675f";
  const libsNote = Number.isInteger(point.group_libs)
    ? ` · group liberties: ${point.group_libs}`
    : "";
  const rimNote = point.phantoms ? " · rim (phantom neighbor)" : "";
  ctx.fillText(
    `${point.legal ? "Legal" : "Not legal"}`
    + `${point.sky ? " · sky liberty" : ""}${libsNote}${rimNote}`,
    32, 84,
  );
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * canvas.width / rect.width,
    y: (event.clientY - rect.top) * canvas.height / rect.height,
  };
}

function nearestPoint(event) {
  const target = nearestTarget(event);
  return target?.kind === "point" ? target.key : null;
}

function nearestTarget(event) {
  if (!visual) return null;
  const mouse = canvasPoint(event);
  let best = null;
  let distance = Infinity;
  for (const [key, pos] of projected) {
    const d = Math.hypot(mouse.x - pos.x, mouse.y - pos.y);
    if (d < distance) { best = {kind: "point", key}; distance = d; }
  }
  for (const [key, pos] of projectedSites) {
    const d = Math.hypot(mouse.x - pos.x, mouse.y - pos.y);
    if (d < distance) { best = {kind: "site", key}; distance = d; }
  }
  return distance <= visual.hitRadius ? best : null;
}

canvas.addEventListener("mousemove", (event) => {
  hoverTarget = nearestTarget(event);
  hoverKey = nearestPoint(event);
  draw();
});
canvas.addEventListener("mouseleave", () => { hoverKey = null; hoverTarget = null; draw(); });
canvas.addEventListener("click", async (event) => {
  if (humanInputLocked()) return;
  const target = nearestTarget(event);
  if (isLabGame() && target?.kind === "site") {
    const site = game.construction_sites.find((item) => keyOf(item.face) === target.key);
    if (site) selectConstruction(site);
    return;
  }
  const key = nearestPoint(event);
  const point = game.points.find((p) => keyOf(p.coord) === key);
  if (!point || !point.legal || game.finished) return;
  // A free extension keeps the turn: clicking its marked point is
  // strictly better than playing there, so it takes precedence.
  if (point.extension) {
    await humanAction("/api/extend", {point: point.coord});
    return;
  }
  // Mid extension-only turn, ordinary placements wait for End turn.
  if (game.extension_only_turn) return;
  await humanAction(isLabGame() ? "/api/action" : "/api/play",
    isLabGame() ? {action: "play", point: point.coord} : {point: point.coord});
});

newButton.addEventListener("click", async () => {
  if (!game || actionInFlight || !canCreateRuleset(rulesetById(rulesSelect.value))) return;
  const warning = playtestRecord
    ? "Start a new game and clear the current local playtest record? Export it first if you need it."
    : "Start a new game?";
  if ((game.moves_played || playtestRecord) && !confirm(warning)) return;
  const body = {
      n: Number(sizeSelect.value),
      rules: rulesSelect.value,
      mode: modeSelect.value,
      human_color: colorSelect.value,
      difficulty: difficultySelect.value,
      black_difficulty: blackDifficultySelect.value,
      white_difficulty: whiteDifficultySelect.value,
      explain: explainCheckbox.checked,
  };
  if (isLabSetup()) {
    body.experimental = true;
  } else {
    body.profile = profileSelect.value;
    body.black_profile = blackProfileSelect.value;
    body.white_profile = whiteProfileSelect.value;
  }
  await replaceGame("/api/new", body);
});
passButton.addEventListener("click", async () => humanAction(
  isLabGame() ? "/api/action" : "/api/pass", isLabGame() ? {action: "pass"} : {},
));
swapButton.addEventListener("click", async () => humanAction(
  isLabGame() ? "/api/action" : "/api/swap", isLabGame() ? {action: "swap"} : {},
));
resumeButton.addEventListener("click", async () => humanAction(
  isLabGame() ? "/api/action" : "/api/resume", isLabGame() ? {action: "resume"} : {},
));
acceptButton.addEventListener("click", async () => {
  if (isLabGame()) await humanAction("/api/action", {action: "accept"});
});
finishExtButton.addEventListener("click", async () =>
  humanAction("/api/finish-extensions"));
modeSelect.addEventListener("change", updateSetupVisibility);
rulesSelect.addEventListener("change", () => {
  if (!isLabSetup()) lastOrdinaryRuleset = rulesSelect.value;
  updateRulesetSetup({coerceSize: true});
});
experimentalCheckbox.addEventListener("change", () => {
  if (!rulesetCatalog) return;
  populateRulesetSelect(rulesetCatalog);
  updateRulesetSetup({coerceSize: true});
});
orientationSelect.addEventListener("change", () => {
  const site = previewSite();
  const orientation = Number(orientationSelect.value);
  if (!site || !site.legal_orientations.includes(orientation)) return;
  constructionPreview.orientation = orientation;
  draw();
});
confirmConstructionButton.addEventListener("click", confirmConstruction);
cancelConstructionButton.addEventListener("click", cancelConstruction);
profileSelect.addEventListener("change", updateProfileNote);
blackProfileSelect.addEventListener("change", updateProfileNote);
whiteProfileSelect.addEventListener("change", updateProfileNote);
startRecordButton.addEventListener("click", startPlaytestRecord);
importRecordButton.addEventListener("click", () => {
  if (
    playtestRecord
    && !confirm("Replace the current local playtest record? Export it first if you need it.")
  ) return;
  importRecordFile.click();
});
importRecordFile.addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const parsed = JSON.parse(await file.text());
    playtestRecord = parsed?.format === "varde-lab-playtest"
      ? window.VardeLabRecord.validateLabRecordShape(parsed)
      : assertImportedPlaytestRecord(parsed);
    playtestImported = true;
    playtestInterrupted = false;
    message.textContent = "";
    updatePlaytestControls();
  } catch (error) {
    message.textContent = error.message;
  }
  event.target.value = "";
});
exportRecordButton.addEventListener("click", exportPlaytestRecord);
clearRecordButton.addEventListener("click", () => {
  if (confirm("Clear the local playtest record?")) clearPlaytestRecord();
});

playButton.addEventListener("click", () => {
  if (replacementInFlight) return;
  if (watchPlaying) {
    stopPlayback();
    return;
  }
  if (!game?.match?.computer_can_act) return;
  watchPlaying = true;
  playButton.textContent = "Pause";
  playbackNote.textContent = `${speedSelect.options[speedSelect.selectedIndex].text} playback`;
  updateControls();
  scheduleComputerMove();
});

stepButton.addEventListener("click", () => scheduleComputerMove(true));

speedSelect.addEventListener("change", () => {
  localStorage.setItem("varde-playback-speed", speedSelect.value);
  if (watchPlaying) {
    playbackNote.textContent = `${speedSelect.options[speedSelect.selectedIndex].text} playback`;
  }
});

saveButton.addEventListener("click", async () => {
  if (!game || actionInFlight) return;
  try {
    const snapshot = await request("/api/snapshot");
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "varde-game.json";
  link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) { message.textContent = error.message; }
});
loadButton.addEventListener("click", () => {
  if (actionInFlight) return;
  if (
    playtestRecord
    && !confirm("Load a game and clear the current local playtest record? Export it first if you need it.")
  ) return;
  document.querySelector("#load-file").click();
});
document.querySelector("#load-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (actionInFlight) { event.target.value = ""; return; }
  try {
    await replaceGame("/api/load", JSON.parse(await file.text()));
  }
  catch (error) { message.textContent = error.message; }
  event.target.value = "";
});

function renderTraining(status) {
  training = status;
  const model = status.model || game?.learning || {games_trained: 0};
  const count = model.games_trained || 0;
  const attempts = model.games_attempted || 0;
  if (status.running) {
    trainingStatus.textContent = `Training ${status.completed}/${status.total} · ${count} learned · ${attempts} attempted`;
  } else if (status.error) {
    trainingStatus.textContent = `Training stopped: ${status.error}`;
  } else if (status.cancel_requested && status.completed < status.total) {
    trainingStatus.textContent = `Canceled after ${status.completed}/${status.total} · ${count} learned · ${attempts} attempted`;
  } else if (model.needs_retraining) {
    trainingStatus.textContent = `Legacy Personal model: ${count} game${count === 1 ? "" : "s"} retained · Reset before V2 retraining`;
  } else if (!count) {
    trainingStatus.textContent = "Personal: untrained · equivalent to Balanced";
  } else {
    trainingStatus.textContent = `Personal V2: ${count} trained · ${attempts} attempted`;
  }
  trainButton.disabled = Boolean(status.running);
  cancelTrainingButton.disabled = !status.running;
  resetTrainingButton.disabled = Boolean(status.running);
  updateProfileNote();
}

async function refreshTraining() {
  try {
    const status = await request("/api/training");
    renderTraining(status);
    if (status.running) {
      clearTimeout(trainingPoll);
      trainingPoll = setTimeout(refreshTraining, 500);
    }
  } catch (error) {
    trainingStatus.textContent = error.message;
  }
}

trainButton.addEventListener("click", async () => {
  if (labContext()) return;
  try {
    renderTraining(await request("/api/training/start", {
      games: Number(trainingGamesSelect.value),
    }));
    clearTimeout(trainingPoll);
    trainingPoll = setTimeout(refreshTraining, 300);
  } catch (error) {
    trainingStatus.textContent = error.message;
  }
});

cancelTrainingButton.addEventListener("click", async () => {
  if (labContext()) return;
  try {
    renderTraining(await request("/api/training/cancel", {}));
    clearTimeout(trainingPoll);
    trainingPoll = setTimeout(refreshTraining, 300);
  } catch (error) {
    trainingStatus.textContent = error.message;
  }
});

resetTrainingButton.addEventListener("click", async () => {
  if (labContext()) return;
  if (!confirm("Reset Personal learning to zero games?")) return;
  try {
    renderTraining(await request("/api/training/reset", {}));
  } catch (error) {
    trainingStatus.textContent = error.message;
  }
});

document.addEventListener("keydown", async (event) => {
  if (event.isComposing || event.target.closest?.("button, input, select, textarea, [contenteditable]")) return;
  if (constructionPreview) {
    const site = previewSite();
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      if (humanInputLocked() || !site) return;
      const choices = site.legal_orientations;
      const delta = ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1;
      const index = choices.indexOf(constructionPreview.orientation);
      constructionPreview.orientation = choices[(index + delta + choices.length) % choices.length];
      orientationSelect.value = String(constructionPreview.orientation);
      draw();
      return;
    }
    if (event.key === "Escape") { event.preventDefault(); cancelConstruction(); return; }
    if (event.key === "Enter") { event.preventDefault(); await confirmConstruction(); return; }
  }
  if (event.key.toLowerCase() === "f") {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.querySelector(".game-card").requestFullscreen();
    } catch (error) { message.textContent = error.message; }
  }
});

function fitFullscreen() {
  if (document.fullscreenElement) {
    const card = document.querySelector(".game-card");
    const controlsHeight = Array.from(card.children).filter((item) => item !== canvas)
      .reduce((height, item) => height + item.getBoundingClientRect().height, 0);
    const width = Math.min(window.innerWidth, Math.max(240, window.innerHeight - controlsHeight) * canvas.width / canvas.height);
    canvas.style.width = `${width}px`;
    canvas.style.marginInline = "auto";
  } else {
    canvas.style.width = "";
    canvas.style.marginInline = "";
  }
  draw();
}
window.addEventListener("resize", fitFullscreen);
document.addEventListener("fullscreenchange", fitFullscreen);

function advanceTime(ms) {
  if (animation) {
    animation.elapsed += ms;
    animation.index = Math.floor(animation.elapsed / animation.duration);
    if (animation.index >= animation.waves.length) animation = null;
  }
  draw();
}
window.advanceTime = advanceTime;
window.get_playtest_record = () => (
  playtestRecord ? JSON.parse(JSON.stringify(playtestRecord)) : null
);
window.export_playtest_record = exportPlaytestRecord;

function frame(now) {
  const delta = Math.min(100, now - lastFrame);
  lastFrame = now;
  if (animation) advanceTime(delta);
  requestAnimationFrame(frame);
}

window.render_game_to_text = () => JSON.stringify({
  coordinate_system: "engine integer coordinates; canvas origin is visual only",
  board_size: game?.n,
  rules: game?.rules,
  to_move: game?.to_move,
  current_player: game?.current_player,
  move: game ? game.moves_played + 1 : null,
  finished: game?.finished,
  experimental: game?.experimental || false,
  rules_revision: game?.rules_revision,
  actor_color: game?.actor_color ?? null,
  actor_seat: game?.actor_seat ?? null,
  accepted: game?.accepted ?? null,
  placements_played: game?.placements_played,
  constructions_played: game?.constructions_played,
  original_control: game?.original_control,
  topology: game?.topology,
  construction_sites: game?.construction_sites,
  legal_actions: game?.legal_actions,
  cells: game?.cells,
  construction_preview: constructionPreview ? {
    ...constructionPreview,
    spokes: previewSite()?.orientations[constructionPreview.orientation].map((index) => previewSite().corners[index]),
  } : null,
  inspection: inspectionData(),
  native_opponent: game?.native_opponent,
  mcts_admission: game?.mcts_admission,
  thinking,
  swap_available: game?.swap_available,
  resumption_available: game?.resumption_available,
  resumption_used: game?.resumption_used,
  extension_only_turn: game?.extension_only_turn,
  score: game?.score,
  match: game?.match,
  computer_decision: game?.computer_decision,
  playback: {
    playing: watchPlaying,
    speed_ms: Number(speedSelect.value),
    action_in_flight: actionInFlight,
    replacement_in_flight: replacementInFlight,
  },
  training: labContext() ? null : training,
  playtest: playtestRecord ? {
    format: playtestRecord.format,
    status: playtestRecord.status,
    actions: playtestRecord.actions.length,
    rules_revision: playtestRecord.rules.revision,
    local_only: true,
    imported: playtestImported,
    interrupted: playtestInterrupted,
  } : null,
  profiles: profileCatalog && !labContext() ? {
    version: profileCatalog.version,
    catalog_hash: profileCatalog.catalog_hash,
    available: profileCatalog.profiles.filter((profile) => profile.available).map((profile) => profile.id),
    selected: {
      versus: profileSelect.value,
      black: blackProfileSelect.value,
      white: whiteProfileSelect.value,
    },
    description: profileNote?.textContent,
  } : null,
  rulesets: rulesetCatalog ? {
    version: rulesetCatalog.version,
    available: rulesetCatalog.rulesets.filter(canCreateRuleset).map((ruleset) => ruleset.id),
    experimental_enabled: experimentalCheckbox.checked,
    selected: rulesSelect.value,
    selected_status: rulesetById(rulesSelect.value)?.status,
    selected_revision: rulesetById(rulesSelect.value)?.evaluation_id,
    selected_native_evaluator: rulesetById(rulesSelect.value)?.native_evaluator_revision,
    native_evaluator_hash: rulesetCatalog.native_evaluators?.hash,
    description: rulesetNote?.textContent,
  } : null,
  visual: visual ? {
    board_scale: BOARD_SCALE,
    spacing: visual.spacing,
    stone_radius: visual.stoneRadius,
    diameter_ratio: 2 * visual.stoneRadius / visual.spacing,
    hit_radius: visual.hitRadius,
    targets: isLabGame() ? [
      ...Array.from(projected, ([key, point]) => ({kind: "point", key, canvas: point})),
      ...Array.from(projectedSites, ([key, point]) => ({kind: "site", key, canvas: point})),
    ] : undefined,
  } : null,
  legal_points: game?.points.filter((p) => p.legal).map((p) => p.coord),
  legal_extensions: game?.points.filter((p) => p.extension).map((p) => p.coord),
  occupied: game?.points.filter((p) => p.stack.length).map((p) => ({coord: p.coord, stack: p.stack, sky: p.sky,
    ...(isLabGame() ? {original: p.original, scoring: p.scoring, center: p.center, neighbors: p.neighbors, group_libs: p.group_libs} : {}),
  })),
  capture_animation_wave: animation?.index ?? null,
});

Promise.all([
  request("/api/profiles"),
  request("/api/rulesets"),
  request("/api/state"),
]).then(([profiles, rulesets, initial]) => {
  installProfileCatalog(profiles);
  installRulesetCatalog(rulesets);
  if (initial.match.mode === "watch") stopPlayback();
  setGame(initial, initial.match.mode !== "watch");
}).catch((error) => { message.textContent = error.message; });
refreshTraining();
requestAnimationFrame(frame);
