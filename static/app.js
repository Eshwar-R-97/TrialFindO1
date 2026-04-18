const findBtn = document.getElementById("findTrialsBtn");
const clearLogsBtn = document.getElementById("clearLogsBtn");
const statusText = document.getElementById("statusText");
const errorBox = document.getElementById("errorBox");
const scoredTbody = document.getElementById("scoredTbody");
const scoredTableWrap = document.getElementById("scoredTableWrap");
const scoredEmpty = document.getElementById("scoredEmpty");
const scoredCount = document.getElementById("scoredCount");
const rawResults = document.getElementById("rawResults");
const rawCount = document.getElementById("rawCount");
const rawDetails = document.getElementById("rawDetails");
const logPanel = document.getElementById("logPanel");

let rawTrialsCount = 0;
let scoredTrialsCount = 0;

const BADGE_LABELS = {
  idle: "IDLE",
  pending: "PENDING",
  running: "RUNNING",
  complete: "COMPLETE",
  error: "FAILED",
};

function setStatus(message) {
  statusText.textContent = message;
}

function clearResults() {
  scoredTbody.innerHTML = "";
  scoredTableWrap.classList.add("hidden");
  scoredEmpty.classList.remove("hidden");
  scoredEmpty.textContent = "Scored matches will appear here once Step 3 finishes.";
  rawResults.innerHTML = "";
  rawTrialsCount = 0;
  scoredTrialsCount = 0;
  rawCount.textContent = "0";
  scoredCount.textContent = "0";
  rawCount.classList.add("hidden");
  scoredCount.classList.add("hidden");
  rawDetails.open = false;
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function clearLogs() {
  logPanel.innerHTML = "";
  logPanel.classList.add("empty");
}

function resetStepCards() {
  document.querySelectorAll(".step-card").forEach((card) => {
    card.dataset.status = "idle";
    card.querySelector(".step-badge").textContent = BADGE_LABELS.idle;
    card.querySelector(".step-summary").textContent = "Waiting to start.";
  });
}

function updateStepCard({ step, status, summary, title }) {
  const card = document.querySelector(`.step-card[data-step="${step}"]`);
  if (!card) return;
  card.dataset.status = status;
  const badge = card.querySelector(".step-badge");
  badge.textContent = BADGE_LABELS[status] || status.toUpperCase();
  if (title) {
    card.querySelector(".step-title").textContent = title;
  }
  if (summary) {
    card.querySelector(".step-summary").textContent = summary;
  }
}

function escapeHtml(value) {
  if (!value && value !== 0) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function classifyLog(message, step) {
  const lower = (message || "").toLowerCase();
  if (lower.includes("failed") || lower.includes("crashed") || lower.startsWith("error")) {
    return "error";
  }
  if (step === 1) return "step-1";
  if (step === 2) return "step-2";
  if (step === 3) return "step-3";
  return "system";
}

function formatTimestamp(epochSeconds) {
  const d = epochSeconds ? new Date(epochSeconds * 1000) : new Date();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function appendLog({ message, step, ts }) {
  logPanel.classList.remove("empty");
  const line = document.createElement("span");
  line.className = `log-line ${classifyLog(message, step)}`;
  const stepTag = step ? `<span class="step-tag">[Step ${step}]</span>` : "";
  line.innerHTML =
    `<span class="ts">${formatTimestamp(ts)}</span>` +
    stepTag +
    `<span class="msg">${escapeHtml(message)}</span>`;
  logPanel.appendChild(line);
  logPanel.scrollTop = logPanel.scrollHeight;
}

function firstSentence(text, maxLen = 160) {
  if (!text) return "";
  const match = String(text).match(/^.*?[.!?](?:\s|$)/);
  const first = (match ? match[0] : String(text)).trim();
  return first.length > maxLen ? first.slice(0, maxLen - 1) + "…" : first;
}

function trialSourceUrl(trial) {
  if (trial.nct_url) return trial.nct_url;
  if (trial.nct_id) return `https://clinicaltrials.gov/study/${trial.nct_id}`;
  if (trial.mayo_url) return trial.mayo_url;
  return "";
}

function trialLocationLabel(trial) {
  const loc = (trial.location || "").trim();
  if (loc && loc.toLowerCase() !== "unknown") return loc;
  return "Location not listed";
}

function eligibilitySnippet(text, maxLen = 220) {
  if (!text) return "Not provided.";
  const cleaned = String(text).replace(/\s+/g, " ").trim();
  return cleaned.length > maxLen ? cleaned.slice(0, maxLen - 1) + "…" : cleaned;
}

function appendRawTrial(trial) {
  if (rawTrialsCount === 0) {
    rawResults.innerHTML = "";
    rawDetails.open = true;
  }
  rawTrialsCount += 1;
  rawCount.textContent = String(rawTrialsCount);
  rawCount.classList.remove("hidden");

  const sourceUrl = trialSourceUrl(trial);
  const linkHtml = sourceUrl
    ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">View source ↗</a>`
    : "";

  const details = document.createElement("details");
  details.className = "trial-card fade-in";
  details.innerHTML = `
    <summary class="trial-summary">
      <div class="trial-summary-top">
        <span class="trial-source-tag">${escapeHtml(trial.source || "Unknown")}</span>
        <h3 class="trial-title">${escapeHtml(trial.title || "Untitled trial")}</h3>
      </div>
      <div class="trial-summary-meta">
        <span>📍 ${escapeHtml(trialLocationLabel(trial))}</span>
        <span>🧪 Phase: ${escapeHtml(trial.phase || "Unknown")}</span>
        ${trial.nct_id ? `<span>ID: ${escapeHtml(trial.nct_id)}</span>` : ""}
      </div>
      <p class="trial-quick">${escapeHtml(firstSentence(trial.summary) || "No short summary available.")}</p>
    </summary>
    <div class="trial-body">
      <p><strong>Full summary:</strong> ${escapeHtml(trial.summary || "Not provided.")}</p>
      <p><strong>Eligibility criteria:</strong> ${escapeHtml(trial.eligibility_criteria || "Not provided.")}</p>
      ${linkHtml ? `<p>${linkHtml}</p>` : ""}
    </div>
  `;
  rawResults.appendChild(details);
}

function scoreNumeric(score) {
  const n = Number(score?.match_score);
  return Number.isFinite(n) ? n : -1;
}

function buildScoredRows({ trial, score }) {
  const level = (score.match_level || "low").toLowerCase();
  const scoreNum = score.match_score ?? "–";
  const sourceUrl = trialSourceUrl(trial);
  const linkHtml = sourceUrl
    ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">View source ↗</a>`
    : "";
  const factors = (score.key_eligibility_factors || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  const exclusions = (score.potential_exclusions || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  const main = document.createElement("tr");
  main.className = "trial-row";
  main.dataset.score = String(scoreNumeric(score));
  main.innerHTML = `
    <td class="col-score">
      <span class="score-chip level-${escapeHtml(level)}">
        ${escapeHtml(scoreNum)}<small>${escapeHtml(level)}</small>
      </span>
    </td>
    <td class="col-source">
      <span class="trial-source-tag">${escapeHtml(trial.source || "Unknown")}</span>
    </td>
    <td class="col-title">
      <span class="cell-title">${escapeHtml(trial.title || "Untitled trial")}</span>
      ${trial.nct_id ? `<span class="cell-sub">${escapeHtml(trial.nct_id)}</span>` : ""}
    </td>
    <td class="col-summary">${escapeHtml(firstSentence(score.plain_english_summary) || "—")}</td>
    <td class="col-location">${escapeHtml(trialLocationLabel(trial))}</td>
    <td class="col-elig">${escapeHtml(eligibilitySnippet(trial.eligibility_criteria, 140))}</td>
  `;

  const detail = document.createElement("tr");
  detail.className = "trial-detail-row hidden";
  detail.innerHTML = `
    <td colspan="6">
      <div class="trial-detail-body">
        <p><strong>Plain-English summary:</strong> ${escapeHtml(score.plain_english_summary || "Not provided.")}</p>
        <p><strong>Why this might or might not fit you:</strong> ${escapeHtml(score.rationale || "Not provided.")}</p>
        <div class="detail-grid">
          <div>
            <p class="detail-label">Key things you'd need</p>
            <ul>${factors || "<li>None provided</li>"}</ul>
          </div>
          <div>
            <p class="detail-label">Things that could disqualify you</p>
            <ul>${exclusions || "<li>None provided</li>"}</ul>
          </div>
        </div>
        <p><strong>Full eligibility text:</strong> ${escapeHtml(trial.eligibility_criteria || "Not provided.")}</p>
        <p><strong>Phase:</strong> ${escapeHtml(trial.phase || "Unknown")}
          ${linkHtml ? ` &nbsp;•&nbsp; ${linkHtml}` : ""}
        </p>
      </div>
    </td>
  `;

  main.addEventListener("click", () => {
    const opened = main.classList.toggle("open");
    detail.classList.toggle("hidden", !opened);
  });

  return { main, detail };
}

function appendScoredTrial(entry) {
  if (scoredTrialsCount === 0) {
    scoredEmpty.classList.add("hidden");
    scoredTableWrap.classList.remove("hidden");
  }
  scoredTrialsCount += 1;
  scoredCount.textContent = String(scoredTrialsCount);
  scoredCount.classList.remove("hidden");

  const { main, detail } = buildScoredRows(entry);
  main.classList.add("fade-in");
  const newScore = Number(main.dataset.score);

  // Insert in score-descending order so the best matches bubble to the top.
  const existingRows = scoredTbody.querySelectorAll("tr.trial-row");
  let inserted = false;
  for (const row of existingRows) {
    if (Number(row.dataset.score) < newScore) {
      scoredTbody.insertBefore(main, row);
      scoredTbody.insertBefore(detail, main.nextSibling);
      inserted = true;
      break;
    }
  }
  if (!inserted) {
    scoredTbody.appendChild(main);
    scoredTbody.appendChild(detail);
  }

  // Auto-open the top scorer for visibility.
  if (scoredTrialsCount === 1 || Number(scoredTbody.querySelector("tr.trial-row").dataset.score) === newScore) {
    const topRow = scoredTbody.querySelector("tr.trial-row");
    const topDetail = topRow.nextElementSibling;
    if (topRow && topDetail && !topRow.classList.contains("open")) {
      topRow.classList.add("open");
      topDetail.classList.remove("hidden");
    }
  }
}

function finishRun({ data, errorMessage } = {}) {
  findBtn.disabled = false;
  if (errorMessage) {
    errorBox.textContent = errorMessage;
    errorBox.classList.remove("hidden");
    setStatus("Failed.");
    return;
  }
  if (!data) return;
  if (rawTrialsCount === 0) {
    rawResults.innerHTML = "<p>No raw trials found.</p>";
  }
  if (scoredTrialsCount === 0) {
    scoredEmpty.textContent = "No scored trials available.";
    scoredEmpty.classList.remove("hidden");
    scoredTableWrap.classList.add("hidden");
  }
  const errors = data.meta?.errors || [];
  if (errors.length) {
    errorBox.textContent = `Partial failures: ${errors.join(" | ")}`;
    errorBox.classList.remove("hidden");
  }
  const elapsed = data.meta?.elapsed_ms || 0;
  const seconds = (elapsed / 1000).toFixed(1);
  setStatus(
    `Done in ${seconds}s. Raw trials: ${data.meta?.counts?.total_raw || 0}. Scored: ${
      data.meta?.counts?.total_scored || 0
    }.`
  );
}

function findTrials() {
  clearResults();
  clearLogs();
  resetStepCards();
  findBtn.disabled = true;
  setStatus("Running Step 1 → Step 2 → Step 3... (streaming live activity below)");

  const source = new EventSource("/find-trials-stream");
  let finalPayload = null;

  source.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (err) {
      appendLog({ message: `Could not parse event: ${event.data}` });
      return;
    }

    if (data.type === "log") {
      appendLog({ message: data.message, step: data.step, ts: data.ts });
    } else if (data.type === "step_update") {
      updateStepCard({
        step: data.step,
        status: data.status,
        summary: data.summary,
        title: data.title,
      });
    } else if (data.type === "trial_added") {
      appendRawTrial(data.trial);
    } else if (data.type === "scored_added") {
      appendScoredTrial(data.entry);
    } else if (data.type === "result") {
      finalPayload = data.payload;
    } else if (data.type === "done") {
      source.close();
      finishRun({ data: finalPayload });
    }
  };

  source.onerror = () => {
    source.close();
    appendLog({ message: "Connection to stream closed." });
    if (finalPayload) {
      finishRun({ data: finalPayload });
    } else {
      finishRun({ errorMessage: "Stream connection failed before completion." });
    }
  };
}

findBtn.addEventListener("click", findTrials);
clearLogsBtn.addEventListener("click", clearLogs);
clearLogs();
