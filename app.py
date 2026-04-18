import json
import os
import re
import time
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from openai import OpenAI
from tinyfish import TinyFish

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

FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"


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


def fetch_clinical_trials() -> List[Dict[str, Any]]:
    print("Step 1: Searching ClinicalTrials.gov...")
    headers = {
        "Accept": "application/json",
        "User-Agent": "TrialFind-MVP/0.1 (demo)",
    }
    response = requests.get(CLINICAL_TRIALS_URL, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    studies = payload.get("studies", [])
    print(f"Step 1: received {len(studies)} raw studies from API")

    normalized = []
    for study in studies[:5]:
        sections = extract_protocol_section(study)
        location_list = sections["contacts"].get("locations", [])
        first_location = location_list[0] if location_list else {}
        phase_list = sections["design"].get("phases", [])

        normalized.append(
            {
                "nct_id": first_non_empty(
                    [sections["identification"].get("nctId"), study.get("nctId")]
                ),
                "title": first_non_empty(
                    [sections["identification"].get("briefTitle"), study.get("briefTitle")]
                ),
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
        )
    print(f"Step 1 complete: {len(normalized)} trials from ClinicalTrials.gov")
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


def fetch_mayo_trials() -> List[Dict[str, Any]]:
    print("Step 2: Launching Tinyfish browser agent on Mayo Clinic...")
    print(f"Step 2: target URL => {MAYO_SEARCH_URL}")
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
        print(f"Step 2 [{_elapsed()}]: agent started run_id={state['run_id']}")

    def on_streaming_url(evt):
        state["streaming_url"] = getattr(evt, "streaming_url", None)
        state["last_event_at"] = time.time()
        print(f"Step 2 [{_elapsed()}]: live browser stream => {state['streaming_url']}")

    def on_progress(evt):
        state["progress_count"] += 1
        state["last_event_at"] = time.time()
        purpose = getattr(evt, "purpose", "") or ""
        print(f"Step 2 [{_elapsed()}]: progress #{state['progress_count']}: {purpose}")

    def on_heartbeat(evt):
        since = int(time.time() - state["last_event_at"])
        print(f"Step 2 [{_elapsed()}]: heartbeat (idle {since}s since last event)")

    def on_complete(evt):
        state["final_status"] = getattr(evt, "status", None)
        state["result_json"] = getattr(evt, "result_json", None)
        state["error"] = getattr(evt, "error", None)
        state["last_event_at"] = time.time()
        print(f"Step 2 [{_elapsed()}]: COMPLETE status={state['final_status']}")

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
    print(f"Step 2: final status={status}, progress_events={state['progress_count']}")
    try:
        preview = json.dumps(raw_results)[:500]
    except Exception:
        preview = str(raw_results)[:500]
    print(f"Step 2: raw result preview => {preview}")

    if state["error"]:
        raise RuntimeError(f"Tinyfish agent error: {state['error']}")

    if isinstance(raw_results, dict) and str(raw_results.get("status") or "").lower() == "failed":
        reason = raw_results.get("reason") or raw_results.get("observation") or "unknown"
        raise RuntimeError(f"Tinyfish agent failed: {reason}")

    rows = parse_tinyfish_result(raw_results)
    print(f"Step 2: parsed {len(rows)} row(s) from agent output")

    normalized = []
    for row in rows[:3]:
        if not isinstance(row, dict):
            continue
        title = (row.get("title") or "Untitled Mayo trial").strip()
        url = (row.get("url") or "").strip()
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
        normalized.append(
            {
                "nct_id": None,
                "title": title,
                "eligibility_criteria": truncate_text(str(eligibility_text)),
                "location": location,
                "phase": "Unknown",
                "summary": truncate_text(summary_text or url or "Sourced from Mayo Clinic listings."),
                "source": "Mayo Clinic",
                "mayo_url": url,
            }
        )
    print(f"Step 2 complete: {len(normalized)} trials from Mayo Clinic")
    return normalized


def extract_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("["):
        return text
    match = re.search(r"(\[.*\])", text, re.DOTALL)
    if match:
        return match.group(1)
    raise ValueError("No JSON array found in Claude response.")


def score_trials_with_featherless(trials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    print("Step 3: Sending normalized trial data to Featherless for scoring...")
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        raise RuntimeError("FEATHERLESS_API_KEY is missing.")

    client = OpenAI(api_key=api_key, base_url=FEATHERLESS_BASE_URL)

    system_prompt = (
        "You are a clinical trial matching assistant. "
        "Return ONLY a valid JSON array. No markdown, no commentary."
    )
    user_prompt = f"""
Patient profile:
{json.dumps(DEMO_PATIENT, indent=2)}

Trials (ordered; use the same index in your output):
{json.dumps(trials, indent=2)}

For EACH trial return an object with EXACTLY these keys:
- trial_index (integer index matching input list)
- match_score (integer 0-100)
- match_level (one of: high, medium, low)
- rationale (string)
- key_eligibility_factors (array of strings)
- potential_exclusions (array of strings)
- plain_english_summary (string)

Return a JSON array with one object per trial. No extra keys. No markdown fences.
"""

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
    json_text = extract_json_text(raw_text.strip())
    scores = json.loads(json_text)
    if not isinstance(scores, list):
        raise ValueError("Featherless response is not a JSON array.")
    print(f"Step 3 complete: Featherless scored {len(scores)} trial entries")
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


@app.route("/find-trials", methods=["GET"])
def find_trials():
    started = time.time()
    errors = []

    clinical_trials = []
    mayo_trials = []
    raw_trials = []
    scored_trials = []

    try:
        clinical_trials = fetch_clinical_trials()
    except Exception as exc:
        errors.append(f"Step 1 failed: {exc}")
        print(errors[-1])

    try:
        mayo_trials = fetch_mayo_trials()
    except Exception as exc:
        errors.append(f"Step 2 failed: {exc}")
        print(errors[-1])

    raw_trials = clinical_trials + mayo_trials

    if raw_trials:
        try:
            scores = score_trials_with_featherless(raw_trials)
            scored_trials = merge_trials_with_scores(raw_trials, scores)
        except Exception as exc:
            errors.append(f"Step 3 failed: {exc}")
            print(errors[-1])
            scored_trials = []

    elapsed_ms = int((time.time() - started) * 1000)
    response_body = {
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
    return jsonify(response_body)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    app.run(debug=True, port=port)
