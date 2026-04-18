import json
import os
import re
import time
from queue import Queue
from threading import Thread
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, stream_with_context
from openai import OpenAI
from tinyfish import TinyFish


class Reporter:
    """Emits both human log lines and structured step updates to an optional queue.

    Callers pass a `Reporter` into each pipeline step so they can push fine-grained
    events (one per sub-action or retry) as they happen instead of batching at the
    end.
    """

    def __init__(self, queue: "Optional[Queue[Optional[Dict[str, Any]]]]" = None) -> None:
        self._queue = queue

    def _emit(self, event: Dict[str, Any]) -> None:
        event.setdefault("ts", time.time())
        if self._queue is not None:
            self._queue.put(event)

    def log(self, message: str, step: Optional[int] = None) -> None:
        prefix = f"[Step {step}] " if step else ""
        print(f"{prefix}{message}", flush=True)
        self._emit({"type": "log", "step": step, "message": message})

    def step(self, step: int, status: str, summary: str = "", title: Optional[str] = None) -> None:
        """Update one of the three step status cards.

        status: "running" | "complete" | "error"
        """
        print(f"[Step {step}] {status.upper()}: {summary or title or ''}".rstrip(), flush=True)
        self._emit(
            {
                "type": "step_update",
                "step": step,
                "status": status,
                "title": title,
                "summary": summary,
            }
        )

    def trial(self, trial: Dict[str, Any]) -> None:
        """Emit a single raw trial as soon as it's normalized."""
        self._emit({"type": "trial_added", "trial": trial})

    def scored(self, entry: Dict[str, Any]) -> None:
        """Emit a single scored trial (trial + score) as soon as available."""
        self._emit({"type": "scored_added", "entry": entry})

    def result(self, payload: Dict[str, Any]) -> None:
        self._emit({"type": "result", "payload": payload})

    def done(self) -> None:
        if self._queue is not None:
            self._queue.put({"type": "done", "ts": time.time()})
            self._queue.put(None)


load_dotenv()

app = Flask(__name__)

DEMO_PATIENT = {
    "diagnosis": "stage 3 breast cancer",
    "age": 48,
    "location": "Minneapolis MN",
    "prior_treatments": "chemotherapy",
}

CLINICAL_TRIALS_URL = (
    "https://clinicaltrials.gov/api/v2/studies?"
    "query.cond=breast+cancer&"
    "filter.geo=distance(44.9778,-93.2650,100mi)&"
    "filter.overallStatus=RECRUITING&"
    "pageSize=5&"
    "format=json"
)

FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"


def prewarm_featherless(reporter: "Reporter") -> None:
    """Fire a tiny request at the Featherless model in a background thread so
    that by the time Step 3 runs, the model is already resident on GPU and we
    skip the 30-60s cold-start penalty.

    Non-blocking; failures are logged but never propagate.
    """
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        return

    def _run() -> None:
        try:
            started = time.time()
            reporter.log(
                f"Pre-warming {FEATHERLESS_MODEL} on Featherless in background...",
            )
            client = OpenAI(api_key=api_key, base_url=FEATHERLESS_BASE_URL)
            client.chat.completions.create(
                model=FEATHERLESS_MODEL,
                max_tokens=1,
                temperature=0,
                messages=[{"role": "user", "content": "ping"}],
            )
            elapsed_ms = int((time.time() - started) * 1000)
            reporter.log(
                f"Pre-warm complete in {elapsed_ms} ms — {FEATHERLESS_MODEL} is now hot."
            )
        except Exception as exc:
            reporter.log(f"Pre-warm failed (non-fatal, Step 3 will still run): {exc}")

    Thread(target=_run, daemon=True).start()


def truncate_text(text: Any, max_chars: int = 2000) -> str:
    text = (text or "").strip()
    return text[:max_chars]


def first_non_empty(values: List[Any], default: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def extract_protocol_section(study: Dict[str, Any]) -> Dict[str, Any]:
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    eligibility = protocol.get("eligibilityModule", {})
    contacts = protocol.get("contactsLocationsModule", {})
    design = protocol.get("designModule", {})
    description = protocol.get("descriptionModule", {})
    return {
        "identification": identification,
        "eligibility": eligibility,
        "contacts": contacts,
        "design": design,
        "description": description,
    }


def format_location(location: Dict[str, Any]) -> str:
    parts = [
        location.get("facility"),
        location.get("city"),
        location.get("state"),
        location.get("country"),
    ]
    cleaned = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    return ", ".join(cleaned) if cleaned else ""


def fetch_clinical_trials(reporter: Reporter) -> List[Dict[str, Any]]:
    reporter.step(1, "running", "Querying ClinicalTrials.gov API...", title="ClinicalTrials.gov API")
    reporter.log("Searching ClinicalTrials.gov for recruiting breast cancer studies near Minneapolis MN.", step=1)
    reporter.log(f"Request URL: {CLINICAL_TRIALS_URL}", step=1)

    headers = {
        "Accept": "application/json",
        "User-Agent": "TrialFind-MVP/0.1 (demo)",
    }

    max_attempts = 3
    last_error: Optional[Exception] = None
    response = None
    for attempt in range(1, max_attempts + 1):
        reporter.log(f"HTTP GET attempt {attempt}/{max_attempts}...", step=1)
        try:
            response = requests.get(CLINICAL_TRIALS_URL, headers=headers, timeout=30)
            response.raise_for_status()
            reporter.log(f"HTTP {response.status_code} received ({len(response.content)} bytes).", step=1)
            break
        except Exception as exc:
            last_error = exc
            reporter.log(f"Attempt {attempt} failed: {exc}", step=1)
            if attempt < max_attempts:
                reporter.log(f"Retrying in 2s...", step=1)
                time.sleep(2)
            else:
                raise
    if response is None:
        raise RuntimeError(f"ClinicalTrials.gov request failed: {last_error}")

    payload = response.json()
    studies = payload.get("studies", [])
    reporter.log(f"Parsed JSON response. {len(studies)} study record(s) returned.", step=1)

    normalized = []
    for idx, study in enumerate(studies[:5], start=1):
        sections = extract_protocol_section(study)
        location_list = sections["contacts"].get("locations", [])
        first_location = location_list[0] if location_list else {}
        phase_list = sections["design"].get("phases", [])

        nct_id = first_non_empty(
            [sections["identification"].get("nctId"), study.get("nctId")]
        )
        title = first_non_empty(
            [sections["identification"].get("briefTitle"), study.get("briefTitle")]
        )

        trial_record = {
            "nct_id": nct_id,
            "title": title,
            "eligibility_criteria": truncate_text(
                first_non_empty(
                    [
                        sections["eligibility"].get("eligibilityCriteria"),
                        study.get("eligibilityCriteria"),
                    ]
                )
            ),
            "location": first_non_empty(
                [
                    format_location(first_location),
                    first_location.get("city"),
                    study.get("locationCity"),
                ],
                "Unknown",
            ),
            "phase": first_non_empty(phase_list, "Unknown"),
            "summary": truncate_text(
                first_non_empty(
                    [
                        sections["description"].get("briefSummary"),
                        study.get("briefSummary"),
                    ]
                )
            ),
            "source": "ClinicalTrials.gov",
        }
        normalized.append(trial_record)
        reporter.log(
            f"Normalized trial {idx}/{min(len(studies), 5)}: {nct_id or 'NCT?'} — {title[:80] if title else 'Untitled'}",
            step=1,
        )
        reporter.trial(trial_record)

    reporter.step(
        1,
        "complete",
        f"Got {len(normalized)} trial(s) from ClinicalTrials.gov.",
        title="ClinicalTrials.gov API",
    )
    return normalized


def _looks_like_trial_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    failure_markers = {"failed", "error"}
    status_val = str(row.get("status") or "").strip().lower()
    if status_val in failure_markers:
        return False
    if row.get("error") or row.get("reason"):
        trial_like_keys = {"title", "url", "eligibility_text", "summary_text"}
        if not any(k in row for k in trial_like_keys):
            return False
    return any(
        (isinstance(row.get(k), str) and row.get(k).strip())
        for k in ("title", "url", "eligibility_text", "summary_text")
    )


def parse_tinyfish_result(raw_result: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_result, list):
        return [r for r in raw_result if _looks_like_trial_row(r)]
    if isinstance(raw_result, dict):
        for key in ("trials", "results", "result", "items", "data", "entries"):
            value = raw_result.get(key)
            if isinstance(value, list):
                return [r for r in value if _looks_like_trial_row(r)]
            if isinstance(value, dict):
                nested = parse_tinyfish_result(value)
                if nested:
                    return nested
        for key in ("text", "output", "content"):
            if isinstance(raw_result.get(key), str):
                return parse_tinyfish_result(raw_result[key])
        if _looks_like_trial_row(raw_result):
            return [raw_result]
        return []
    if isinstance(raw_result, str):
        cleaned = raw_result.strip()
        try:
            parsed = json.loads(cleaned)
            return parse_tinyfish_result(parsed)
        except json.JSONDecodeError:
            match = re.search(r"(\[.*\])", cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    return parse_tinyfish_result(parsed)
                except json.JSONDecodeError:
                    return []
    return []


MAYO_SEARCH_URL = (
    "https://www.mayo.edu/research/clinical-trials/search-results"
    "?keyword=breast+cancer"
    "&studySiteStatusesGrouped=Open%2FStatus+Unknown"
)

MAYO_GOAL = """
You are on the Mayo Clinic Research clinical trials search results page for
the keyword "breast cancer", filtered to open/recruiting studies.

Do the following:

1. Identify the first 3 clinical trial result entries on the page.
   Each entry normally has a title link and short descriptive text.
2. For each of those 3 entries, capture:
   - title: the trial title text as shown
   - url: the absolute URL of the trial's detail page (the href of the title link)
   - status: the recruiting/enrolling status shown if visible, else ""
   - location: any visible Mayo site/campus text (e.g. Rochester, Minnesota;
     Phoenix/Scottsdale, Arizona; Jacksonville, Florida). If unclear, use "".
3. OPEN each of those 3 trial URLs (one at a time) and from the detail page
   extract:
   - eligibility_text: the full text of the "Eligibility criteria" or
     "Inclusion/Exclusion Criteria" section. If not found, use "".
   - summary_text: the short description / purpose paragraph near the top of
     the detail page. If not found, use "".

Return ONLY a JSON array of 3 objects. Each object MUST have EXACTLY these
keys and nothing else:
title, url, status, location, eligibility_text, summary_text.

No markdown. No prose. No code fences. Just the raw JSON array.
If fewer than 3 trials are shown on the page, return whatever is available
(1 or 2 items is acceptable).
"""


def fetch_mayo_trials(reporter: Reporter) -> List[Dict[str, Any]]:
    reporter.step(
        2,
        "running",
        "Launching Tinyfish browser agent on Mayo Clinic...",
        title="Mayo Clinic browser agent (Tinyfish)",
    )
    reporter.log(f"Target URL: {MAYO_SEARCH_URL}", step=2)
    api_key = os.getenv("TINYFISH_API_KEY")
    if not api_key:
        raise RuntimeError("TINYFISH_API_KEY is missing.")

    client = TinyFish(api_key=api_key)

    state: Dict[str, Any] = {
        "started_at": time.time(),
        "last_event_at": time.time(),
        "run_id": None,
        "streaming_url": None,
        "final_status": None,
        "result_json": None,
        "error": None,
        "progress_count": 0,
    }

    def _elapsed() -> str:
        return f"{int(time.time() - state['started_at']):>3}s"

    def on_started(evt):
        state["run_id"] = getattr(evt, "run_id", None)
        state["last_event_at"] = time.time()
        reporter.log(f"Agent started (run_id={state['run_id']}, elapsed={_elapsed()}).", step=2)

    def on_streaming_url(evt):
        state["streaming_url"] = getattr(evt, "streaming_url", None)
        state["last_event_at"] = time.time()
        reporter.log(f"Live browser stream available: {state['streaming_url']}", step=2)

    def on_progress(evt):
        state["progress_count"] += 1
        state["last_event_at"] = time.time()
        purpose = (getattr(evt, "purpose", "") or "").strip()
        reporter.log(purpose or "(agent working...)", step=2)

    def on_heartbeat(evt):
        since = int(time.time() - state["last_event_at"])
        reporter.log(f"heartbeat (elapsed {_elapsed()}, idle {since}s)", step=2)

    def on_complete(evt):
        state["final_status"] = getattr(evt, "status", None)
        state["result_json"] = getattr(evt, "result_json", None)
        state["error"] = getattr(evt, "error", None)
        state["last_event_at"] = time.time()
        reporter.log(f"Browser agent complete: {state['final_status']}", step=2)

    stream = client.agent.stream(
        goal=MAYO_GOAL,
        url=MAYO_SEARCH_URL,
        on_started=on_started,
        on_streaming_url=on_streaming_url,
        on_progress=on_progress,
        on_heartbeat=on_heartbeat,
        on_complete=on_complete,
    )

    for _ in stream:
        pass

    raw_results = state["result_json"] or {}
    status = state["final_status"]
    reporter.log(
        f"Final status={status}, {state['progress_count']} progress event(s) observed.",
        step=2,
    )
    try:
        preview = json.dumps(raw_results)[:300]
    except Exception:
        preview = str(raw_results)[:300]
    reporter.log(f"Raw result preview: {preview}", step=2)

    if state["error"]:
        raise RuntimeError(f"Tinyfish agent error: {state['error']}")

    if isinstance(raw_results, dict) and str(raw_results.get("status") or "").lower() == "failed":
        reason = raw_results.get("reason") or raw_results.get("observation") or "unknown"
        raise RuntimeError(f"Tinyfish agent failed: {reason}")

    rows = parse_tinyfish_result(raw_results)
    reporter.log(f"Parsed {len(rows)} trial row(s) from agent output.", step=2)

    normalized = []
    for idx, row in enumerate(rows[:3], start=1):
        if not isinstance(row, dict):
            continue
        title = (row.get("title") or "Untitled Mayo trial").strip()
        url = (row.get("url") or "").strip()
        reporter.log(f"Normalized Mayo trial {idx}: {title[:80]}", step=2)
        eligibility_text = (
            row.get("eligibility_text")
            or row.get("eligibility")
            or row.get("eligibilityCriteria")
            or ""
        )
        summary_text = (
            row.get("summary_text") or row.get("summary") or row.get("description") or ""
        )
        location = (row.get("location") or "Mayo Clinic (site-dependent)").strip()
        trial_record = {
            "nct_id": None,
            "title": title,
            "eligibility_criteria": truncate_text(str(eligibility_text)),
            "location": location,
            "phase": "Unknown",
            "summary": truncate_text(summary_text or url or "Sourced from Mayo Clinic listings."),
            "source": "Mayo Clinic",
            "mayo_url": url,
        }
        normalized.append(trial_record)
        reporter.trial(trial_record)
    reporter.step(
        2,
        "complete",
        f"Got {len(normalized)} trial(s) from Mayo Clinic.",
        title="Mayo Clinic browser agent (Tinyfish)",
    )
    return normalized


def extract_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("["):
        return text
    match = re.search(r"(\[.*\])", text, re.DOTALL)
    if match:
        return match.group(1)
    raise ValueError("No JSON array found in Claude response.")


def score_trials_with_featherless(
    trials: List[Dict[str, Any]], reporter: Reporter
) -> List[Dict[str, Any]]:
    reporter.step(
        3,
        "running",
        f"Scoring {len(trials)} trial(s) with Featherless AI...",
        title="Featherless AI scoring",
    )
    reporter.log(f"Asking {FEATHERLESS_MODEL} to score {len(trials)} trial(s)...", step=3)
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        raise RuntimeError("FEATHERLESS_API_KEY is missing.")

    client = OpenAI(api_key=api_key, base_url=FEATHERLESS_BASE_URL)

    system_prompt = (
        "You are a clinical trial matching assistant whose audience is the "
        "patient themselves, not a clinician. You write in warm, plain, "
        "second-person English ('you', 'your') and gently explain any "
        "necessary medical term the first time it appears in parentheses "
        "(e.g., 'HER2-positive (a type of breast cancer that grows faster)'). "
        "Keep essential clinical terms when they matter — don't oversimplify "
        "to the point of inaccuracy. "
        "Return ONLY a valid JSON array. No markdown, no commentary, no code fences."
    )
    user_prompt = f"""
Patient profile:
{json.dumps(DEMO_PATIENT, indent=2)}

Trials (ordered; use the same index in your output):
{json.dumps(trials, indent=2)}

For EACH trial return an object with EXACTLY these keys:
- trial_index: integer index matching the input list.
- match_score: integer 0-100.
- match_level: one of "high", "medium", "low".
- rationale: 1-2 sentences, written TO the patient ("you"), explaining in
  plain language WHY this trial might or might not be a fit based on their
  profile. Keep key medical terms but briefly explain them. Avoid words
  like "cohort", "adjuvant", "neoadjuvant", "ECOG", "inclusion/exclusion
  criteria" unless you define them inline.
- key_eligibility_factors: array of 2-4 short strings, each phrased as what
  the patient would need to have/be (e.g., "You need to be 18 or older",
  "You should have HER2-positive breast cancer (a specific subtype)").
- potential_exclusions: array of short strings describing things that would
  likely disqualify the patient, phrased plainly (e.g., "You can't join if
  you've had brain metastases (cancer that has spread to the brain)"). Use
  an empty array if none apply.
- plain_english_summary: 2-4 friendly sentences for the patient explaining
  (a) what the trial is testing and why, (b) what participating would look
  like at a high level, and (c) what this could mean for them. Keep it
  approachable — a patient with no medical background should understand
  it — but don't strip out important clinical nouns; briefly define them.
  Avoid hype or false promises.

Return a JSON array with one object per trial. No extra keys. No markdown fences.
"""

    max_attempts = 3
    last_error: Optional[Exception] = None
    scores: List[Dict[str, Any]] = []

    for attempt in range(1, max_attempts + 1):
        reporter.log(f"Scoring request attempt {attempt}/{max_attempts}...", step=3)
        try:
            completion = client.chat.completions.create(
                model=FEATHERLESS_MODEL,
                temperature=0,
                max_tokens=2500,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw_text = completion.choices[0].message.content or ""
            reporter.log(
                f"Received {len(raw_text)} chars from Featherless. Parsing JSON...",
                step=3,
            )
            json_text = extract_json_text(raw_text.strip())
            parsed = json.loads(json_text)
            if not isinstance(parsed, list):
                raise ValueError("Featherless response is not a JSON array.")
            scores = parsed
            reporter.log(f"Parsed {len(scores)} scored trial object(s).", step=3)
            break
        except Exception as exc:
            last_error = exc
            reporter.log(f"Attempt {attempt} failed: {exc}", step=3)
            if attempt < max_attempts:
                reporter.log("Retrying scoring request in 2s...", step=3)
                time.sleep(2)
            else:
                raise

    if not scores and last_error is not None:
        raise last_error

    reporter.step(
        3,
        "complete",
        f"Scored {len(scores)} trial(s).",
        title="Featherless AI scoring",
    )
    return scores


def merge_trials_with_scores(
    raw_trials: List[Dict[str, Any]], scores: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    by_index = {}
    for score in scores:
        try:
            idx = int(score.get("trial_index"))
        except (TypeError, ValueError):
            continue
        by_index[idx] = score

    merged = []
    for idx, trial in enumerate(raw_trials):
        merged.append(
            {
                "trial": trial,
                "score": by_index.get(
                    idx,
                    {
                        "trial_index": idx,
                        "match_score": None,
                        "match_level": "low",
                        "rationale": "No score available.",
                        "key_eligibility_factors": [],
                        "potential_exclusions": [],
                        "plain_english_summary": "Scoring unavailable for this trial.",
                    },
                ),
            }
        )
    return merged


@app.route("/")
def index() -> str:
    return render_template("index.html")


def _run_pipeline(reporter: Reporter) -> Dict[str, Any]:
    started = time.time()
    errors: List[str] = []

    clinical_trials: List[Dict[str, Any]] = []
    mayo_trials: List[Dict[str, Any]] = []
    scored_trials: List[Dict[str, Any]] = []

    reporter.step(1, "pending", "Idle.", title="ClinicalTrials.gov API")
    reporter.step(2, "pending", "Idle.", title="Mayo Clinic browser agent (Tinyfish)")
    reporter.step(3, "pending", "Idle.", title="Featherless AI scoring")
    reporter.log("Pipeline started.")

    prewarm_featherless(reporter)

    try:
        clinical_trials = fetch_clinical_trials(reporter)
    except Exception as exc:
        msg = f"Step 1 failed: {exc}"
        errors.append(msg)
        reporter.log(msg, step=1)
        reporter.step(1, "error", str(exc), title="ClinicalTrials.gov API")

    try:
        mayo_trials = fetch_mayo_trials(reporter)
    except Exception as exc:
        msg = f"Step 2 failed: {exc}"
        errors.append(msg)
        reporter.log(msg, step=2)
        reporter.step(2, "error", str(exc), title="Mayo Clinic browser agent (Tinyfish)")

    raw_trials = clinical_trials + mayo_trials
    reporter.log(
        f"Combined raw trials: {len(raw_trials)} "
        f"(ClinicalTrials.gov={len(clinical_trials)}, Mayo={len(mayo_trials)})"
    )

    if raw_trials:
        try:
            scores = score_trials_with_featherless(raw_trials, reporter)
            scored_trials = merge_trials_with_scores(raw_trials, scores)
            for entry in scored_trials:
                reporter.scored(entry)
        except Exception as exc:
            msg = f"Step 3 failed: {exc}"
            errors.append(msg)
            reporter.log(msg, step=3)
            reporter.step(3, "error", str(exc), title="Featherless AI scoring")
            scored_trials = []
    else:
        reporter.step(3, "error", "No trials to score.", title="Featherless AI scoring")

    elapsed_ms = int((time.time() - started) * 1000)
    reporter.log(f"All steps finished in {elapsed_ms} ms.")
    return {
        "patient_profile": DEMO_PATIENT,
        "raw_trials": raw_trials,
        "scored_trials": scored_trials,
        "meta": {
            "counts": {
                "clinicaltrials_gov": len(clinical_trials),
                "mayo_clinic": len(mayo_trials),
                "total_raw": len(raw_trials),
                "total_scored": len(scored_trials),
            },
            "errors": errors,
            "elapsed_ms": elapsed_ms,
        },
    }


@app.route("/find-trials", methods=["GET"])
def find_trials():
    result = _run_pipeline(Reporter())
    return jsonify(result)


@app.route("/find-trials-stream", methods=["GET"])
def find_trials_stream():
    queue: "Queue[Optional[Dict[str, Any]]]" = Queue()
    reporter = Reporter(queue=queue)

    def worker() -> None:
        try:
            result = _run_pipeline(reporter)
            reporter.result(result)
        except Exception as exc:
            reporter.log(f"Pipeline crashed: {exc}")
        finally:
            reporter.done()

    Thread(target=worker, daemon=True).start()

    @stream_with_context
    def event_stream():
        yield f"data: {json.dumps({'type': 'log', 'message': 'Connected. Starting pipeline...', 'ts': time.time()})}\n\n"
        while True:
            item = queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    app.run(debug=True, port=port)
