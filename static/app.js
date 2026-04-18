const findBtn = document.getElementById("findTrialsBtn");
const clearLogsBtn = document.getElementById("clearLogsBtn");
const statusText = document.getElementById("statusText");
const errorBox = document.getElementById("errorBox");
const scoredResults = document.getElementById("scoredResults");
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
  scoredResults.innerHTML =
    '<p class="empty-hint">Scored matches will appear here once Step 3 finishes.</p>';
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

function appendRawTrial(trial) {
  if (rawTrialsCount === 0) {
    rawResults.innerHTML = "";
    rawDetails.open = true;
  }
  rawTrialsCount += 1;
  rawCount.textContent = String(rawTrialsCount);
  rawCount.classList.remove("hidden");

  const article = document.createElement("article");
  article.className = "card fade-in";
  article.innerHTML = `
    <h3>${escapeHtml(trial.title)}</h3>
    <p class="meta">
      Source: ${escapeHtml(trial.source)} |
      NCT ID: ${escapeHtml(trial.nct_id || "N/A")} |
      Phase: ${escapeHtml(trial.phase || "Unknown")} |
      Location: ${escapeHtml(trial.location || "Unknown")}
    </p>
    <p><strong>Summary:</strong> ${escapeHtml(trial.summary || "N/A")}</p>
    <p><strong>Eligibility:</strong> ${escapeHtml(trial.eligibility_criteria || "N/A")}</p>
  `;
  rawResults.appendChild(article);
}

function appendScoredTrial({ trial, score }) {
  if (scoredTrialsCount === 0) {
    scoredResults.innerHTML = "";
  }
  scoredTrialsCount += 1;
  scoredCount.textContent = String(scoredTrialsCount);
  scoredCount.classList.remove("hidden");

  const level = (score.match_level || "low").toLowerCase();
  const factors = (score.key_eligibility_factors || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  const exclusions = (score.potential_exclusions || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  const article = document.createElement("article");
  article.className = "card fade-in";
  article.innerHTML = `
    <h3>${escapeHtml(trial.title)}</h3>
    <p class="meta">
      Source: ${escapeHtml(trial.source)} |
      Score: ${escapeHtml(score.match_score)}
      <span class="badge ${escapeHtml(level)}">${escapeHtml(level)}</span>
    </p>
    <p><strong>Summary:</strong> ${escapeHtml(score.plain_english_summary)}</p>
    <p><strong>Rationale:</strong> ${escapeHtml(score.rationale)}</p>
    <p><strong>Key factors:</strong></p>
    <ul>${factors || "<li>None provided</li>"}</ul>
    <p><strong>Potential exclusions:</strong></p>
    <ul>${exclusions || "<li>None provided</li>"}</ul>
  `;
  scoredResults.appendChild(article);
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
    scoredResults.innerHTML = "<p>No scored trials available.</p>";
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
