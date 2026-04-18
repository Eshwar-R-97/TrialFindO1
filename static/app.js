const findBtn = document.getElementById("findTrialsBtn");
const statusText = document.getElementById("statusText");
const errorBox = document.getElementById("errorBox");
const scoredResults = document.getElementById("scoredResults");
const rawResults = document.getElementById("rawResults");

function setStatus(message) {
  statusText.textContent = message;
}

function clearResults() {
  scoredResults.innerHTML = "";
  rawResults.innerHTML = "";
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
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

function renderScoredTrials(scoredTrials) {
  if (!scoredTrials.length) {
    scoredResults.innerHTML = "<p>No scored trials available.</p>";
    return;
  }

  scoredResults.innerHTML = scoredTrials
    .map(({ trial, score }) => {
      const level = (score.match_level || "low").toLowerCase();
      const factors = (score.key_eligibility_factors || [])
        .map((item) => `<li>${escapeHtml(item)}</li>`)
        .join("");
      const exclusions = (score.potential_exclusions || [])
        .map((item) => `<li>${escapeHtml(item)}</li>`)
        .join("");

      return `
        <article class="card">
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
        </article>
      `;
    })
    .join("");
}

function renderRawTrials(rawTrials) {
  if (!rawTrials.length) {
    rawResults.innerHTML = "<p>No raw trials found.</p>";
    return;
  }

  rawResults.innerHTML = rawTrials
    .map(
      (trial) => `
      <article class="card">
        <h3>${escapeHtml(trial.title)}</h3>
        <p class="meta">
          Source: ${escapeHtml(trial.source)} |
          NCT ID: ${escapeHtml(trial.nct_id || "N/A")} |
          Phase: ${escapeHtml(trial.phase || "Unknown")} |
          Location: ${escapeHtml(trial.location || "Unknown")}
        </p>
        <p><strong>Summary:</strong> ${escapeHtml(trial.summary || "N/A")}</p>
        <p><strong>Eligibility:</strong> ${escapeHtml(trial.eligibility_criteria || "N/A")}</p>
      </article>
    `
    )
    .join("");
}

async function findTrials() {
  clearResults();
  findBtn.disabled = true;
  setStatus("Running Step 1 -> Step 2 -> Step 3 on backend...");

  try {
    const response = await fetch("/find-trials");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    renderScoredTrials(data.scored_trials || []);
    renderRawTrials(data.raw_trials || []);

    const errors = data.meta?.errors || [];
    if (errors.length) {
      errorBox.textContent = `Partial failures: ${errors.join(" | ")}`;
      errorBox.classList.remove("hidden");
    }

    setStatus(
      `Done. Raw trials: ${data.meta?.counts?.total_raw || 0}. Scored trials: ${
        data.meta?.counts?.total_scored || 0
      }.`
    );
  } catch (error) {
    errorBox.textContent = `Request failed: ${error.message}`;
    errorBox.classList.remove("hidden");
    setStatus("Failed.");
  } finally {
    findBtn.disabled = false;
  }
}

findBtn.addEventListener("click", findTrials);
