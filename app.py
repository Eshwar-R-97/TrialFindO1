import io
import json
import os
import random
import re
import time
from urllib.parse import quote_plus, urlencode
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Lock, Thread
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    request,
    send_from_directory,
    stream_with_context,
)
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
        # Optional async LLM translator that rewrites technical pipeline log
        # lines into patient-friendly one-liners. Set by `_run_pipeline` once
        # the Featherless key is confirmed available. `None` means no-op.
        self.translator: "Optional[FriendlyTranslator]" = None
        # Optional per-trial async scorer. When set, every trial emitted via
        # `reporter.trial(...)` is handed to it immediately and scored in
        # parallel on a background thread pool — so scoring overlaps with
        # the remaining fetch steps instead of being a separate terminal
        # stage. The scorer also owns NCT-id dedupe (see `TrialScorer`).
        self.scorer: "Optional[TrialScorer]" = None

    def _emit(self, event: Dict[str, Any]) -> None:
        event.setdefault("ts", time.time())
        if self._queue is not None:
            self._queue.put(event)

    def log(self, message: str, step: Optional[int] = None) -> None:
        prefix = f"[Step {step}] " if step else ""
        print(f"{prefix}{message}", flush=True)
        self._emit({"type": "log", "step": step, "message": message})

    def friendly(self, message: str, step: Optional[int] = None) -> None:
        """Emit a patient-friendly one-line status update to the UI.

        These are rendered in the live status ticker and are meant to be read
        by the patient in plain language. Backend stdout also gets a copy so
        the friendly summary shows up in server logs.
        """
        prefix = f"[Friendly Step {step}] " if step else "[Friendly] "
        print(f"{prefix}{message}", flush=True)
        self._emit({"type": "friendly_status", "step": step, "message": message})

    def translate(self, raw_message: str, step: Optional[int] = None) -> None:
        """Ask the attached LLM translator (if any) to rewrite `raw_message`
        as a patient-friendly one-liner and emit a `friendly_status` event
        when it finishes. Fire-and-forget; no-op when no translator is set."""
        if self.translator is not None:
            self.translator.translate(raw_message, step)

    def milestone(self, message: str, step: Optional[int] = None) -> None:
        """Log a patient-relevant milestone: write it to the raw log stream
        AND hand it to the LLM translator to produce a friendly one-liner."""
        self.log(message, step=step)
        self.translate(message, step=step)

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
        """Emit a single raw trial as soon as it's normalized.

        If a `TrialScorer` is attached we first hand the trial to it — that
        both dedupes by NCT id and kicks off an async scoring job. Only
        first-time-seen trials make it onto the SSE stream, so the UI never
        sees the same study twice across overlapping sources.
        """
        if self.scorer is not None:
            if not self.scorer.schedule(trial):
                return
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

# Serve the built React app out of `frontend/dist`. During development the
# React app is run via `npm run dev` (Vite on :5173) which proxies the
# `/find-trials*` endpoints back to this Flask server. In production we build
# once (`cd frontend && npm run build`) and Flask serves the static bundle.
_REACT_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
app = Flask(__name__, static_folder=None)


@app.after_request
def _cors_localhost_dev(resp: Response) -> Response:
    """Allow the Vite dev UI (another origin/port) to call Flask when using VITE_API_BASE_URL."""
    path = request.path or ""
    if not (
        path.startswith("/api/")
        or path.startswith("/read-pdf")
        or path.startswith("/patient-profile")
        or path.startswith("/find-trials")
    ):
        return resp
    origin = request.headers.get("Origin")
    if origin and (
        origin.startswith("http://localhost:")
        or origin.startswith("http://127.0.0.1:")
    ):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
        resp.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Requested-With"
        )
        resp.headers["Access-Control-Max-Age"] = "3600"
    return resp


DEMO_PATIENT = {
    "diagnosis": "stage 3 breast cancer",
    "cancer_type": "breast",
    "age": 48,
    "location": "Minneapolis MN",
    "prior_treatments": "chemotherapy",
}

# Set by a successful POST /read-pdf; `_run_pipeline` / Featherless scoring use this
# instead of DEMO_PATIENT until the process restarts.
_active_pdf_patient: Optional[Dict[str, Any]] = None


def _set_active_pdf_patient(extracted_profile: Dict[str, Any]) -> None:
    global _active_pdf_patient
    _active_pdf_patient = extracted_profile


def get_patient_for_pipeline() -> Dict[str, Any]:
    """Patient dict for trial scoring and the final API payload.

    After a PDF upload, mirrors Featherless fields while keeping DEMO_PATIENT
    fallbacks for anything missing.
    """
    if _active_pdf_patient is None:
        return dict(DEMO_PATIENT)
    ext = _active_pdf_patient
    priors = ext.get("prior_treatments")
    if isinstance(priors, list):
        prior_str = ", ".join(str(p) for p in priors if p)
    else:
        prior_str = str(priors or "").strip()
    if not prior_str:
        prior_str = str(DEMO_PATIENT["prior_treatments"])
    age = ext.get("age")
    if age is None:
        age = DEMO_PATIENT["age"]
    zip_c = (ext.get("zip_code") or "").strip()
    location = f"ZIP {zip_c}" if zip_c else str(DEMO_PATIENT["location"])
    diagnosis = (ext.get("diagnosis") or "").strip() or str(DEMO_PATIENT["diagnosis"])
    out: Dict[str, Any] = {
        "diagnosis": diagnosis,
        "age": age,
        "location": location,
        "prior_treatments": prior_str,
    }
    if zip_c:
        out["zip_code"] = zip_c
    for key in (
        "cancer_type",
        "stage",
        "summary",
        "first_name",
        "last_name",
        "email",
        "performance_status",
    ):
        v = ext.get(key)
        if v is not None and v != "":
            out[key] = v
    bio = ext.get("biomarkers")
    if isinstance(bio, dict) and bio:
        out["biomarkers"] = bio
    com = ext.get("comorbidities")
    if isinstance(com, list) and com:
        out["comorbidities"] = com
    return out


def missing_patient_input_ids(ext: Optional[Dict[str, Any]]) -> List[str]:
    """Which inputs the UI should still collect after PDF parse (location, condition, age)."""
    if not ext:
        return []
    need: List[str] = []
    z = re.sub(r"\D", "", str(ext.get("zip_code") or ""))
    if len(z) < 5:
        need.append("zip_code")
    has_dx = (ext.get("diagnosis") or "").strip()
    has_ct = (ext.get("cancer_type") or "").strip()
    if not has_dx and not has_ct:
        need.append("condition")
    if ext.get("age") is None:
        need.append("age")
    return need


_PATIENT_MERGE_KEYS = frozenset(
    {
        "zip_code",
        "age",
        "diagnosis",
        "cancer_type",
        "stage",
        "first_name",
        "last_name",
        "email",
        "performance_status",
        "summary",
        "prior_treatments",
    }
)


def merge_patient_profile_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Apply user edits onto `_active_pdf_patient`. Returns the merged extraction dict."""
    global _active_pdf_patient
    if _active_pdf_patient is None:
        raise RuntimeError("No PDF profile is loaded")
    for key, val in updates.items():
        if key not in _PATIENT_MERGE_KEYS:
            continue
        if val is None:
            continue
        if key == "prior_treatments":
            if isinstance(val, list):
                _active_pdf_patient["prior_treatments"] = [
                    str(x).strip() for x in val if str(x).strip()
                ]
            elif isinstance(val, str) and val.strip():
                _active_pdf_patient["prior_treatments"] = [
                    p.strip() for p in val.split(",") if p.strip()
                ]
            continue
        if key == "age":
            try:
                _active_pdf_patient["age"] = int(val)
            except (TypeError, ValueError):
                pass
            continue
        if key == "zip_code":
            digits = re.sub(r"\D", "", str(val))[:5]
            if len(digits) == 5:
                _active_pdf_patient["zip_code"] = digits
            continue
        if isinstance(val, str):
            _active_pdf_patient[key] = val.strip()
        else:
            _active_pdf_patient[key] = val
    return _active_pdf_patient


# US state abbrev → uppercase full name (for matching NCI / site strings).
_US_STATE_LONG: Dict[str, str] = {
    "MN": "MINNESOTA",
    "TX": "TEXAS",
    "CA": "CALIFORNIA",
    "NY": "NEW YORK",
    "FL": "FLORIDA",
    "IL": "ILLINOIS",
    "PA": "PENNSYLVANIA",
    "OH": "OHIO",
    "GA": "GEORGIA",
    "NC": "NORTH CAROLINA",
    "MI": "MICHIGAN",
    "NJ": "NEW JERSEY",
    "WA": "WASHINGTON",
    "AZ": "ARIZONA",
    "MA": "MASSACHUSETTS",
    "CO": "COLORADO",
    "TN": "TENNESSEE",
    "IN": "INDIANA",
    "MO": "MISSOURI",
    "MD": "MARYLAND",
    "WI": "WISCONSIN",
    "LA": "LOUISIANA",
}


def _expand_state_set(abbrev: str) -> set:
    a = (abbrev or "MN").strip().upper()
    s = {a}
    if len(a) == 2 and a in _US_STATE_LONG:
        s.add(_US_STATE_LONG[a])
    return s


def _lookup_zip_metadata(us_zip: Optional[str]) -> Dict[str, Any]:
    """Lat/lon + state abbreviation from a 5-digit US ZIP (zippopotam.us)."""
    digits = re.sub(r"\D", "", us_zip or "")[:5]
    if len(digits) != 5:
        return {}
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{digits}", timeout=8)
        if not r.ok:
            return {}
        places = r.json().get("places") or []
        if not places:
            return {}
        p = places[0]
        lat = p.get("latitude")
        lng = p.get("longitude")
        st = (p.get("state abbreviation") or "").strip().upper()
        out: Dict[str, Any] = {"state": st}
        try:
            if lat is not None and lng is not None:
                out["lat"] = float(lat)
                out["lon"] = float(lng)
        except (TypeError, ValueError):
            pass
        return out
    except Exception:
        return {}


def _patient_zip_string(patient: Dict[str, Any]) -> str:
    z = patient.get("zip_code")
    if isinstance(z, str) and z.strip():
        return z.strip()
    loc = (patient.get("location") or "").strip()
    if loc.upper().startswith("ZIP "):
        return loc[4:].strip()
    return ""


def search_condition_phrase(patient: Dict[str, Any]) -> str:
    """Free-text condition for ClinicalTrials.gov / NCI / Mayo keyword search."""
    ct = (patient.get("cancer_type") or "").strip()
    if ct:
        low = ct.lower()
        if "cancer" in low or "carcinoma" in low or "lymphoma" in low or "melanoma" in low:
            return ct
        return f"{ct} cancer"
    diag = (patient.get("diagnosis") or "").strip()
    if diag:
        return diag[:240]
    return "breast cancer"


def clinical_trials_gov_studies_url(patient: Dict[str, Any]) -> str:
    """ClinicalTrials.gov v2 studies URL from patient (condition + ~100mi geo)."""
    cond = search_condition_phrase(patient)
    lat, lon = 44.9778, -93.2650  # demo: Minneapolis
    zm = _lookup_zip_metadata(_patient_zip_string(patient))
    if zm.get("lat") is not None and zm.get("lon") is not None:
        lat, lon = zm["lat"], zm["lon"]
    params = {
        "query.cond": cond,
        "filter.geo": f"distance({lat},{lon},100mi)",
        "filter.overallStatus": "RECRUITING",
        "pageSize": "5",
        "format": "json",
    }
    return "https://clinicaltrials.gov/api/v2/studies?" + urlencode(params)


FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
# Featherless plans enforce a per-account concurrency limit (e.g.
# feather_pro_plus = 4 simultaneous requests on llama31-8b). We cap our
# worker pool to this value so we don't get 429s. Override via env var if
# your plan allows more.
FEATHERLESS_MAX_CONCURRENCY = int(os.getenv("FEATHERLESS_MAX_CONCURRENCY", "4"))
# Set to 0/false/no to skip the extra Featherless calls that rewrite log lines
# into patient-friendly one-liners — slightly faster and fewer 429s on small plans.
FEATHERLESS_FRIENDLY_STATUS = os.getenv("FEATHERLESS_FRIENDLY_STATUS", "1")
# PDF profile extraction can use a smaller/faster model than trial scoring.
# Defaults to FEATHERLESS_MODEL when unset.
# Example: same 8B instruct or a lighter endpoint your plan exposes.
FEATHERLESS_PDF_MODEL = os.getenv("FEATHERLESS_PDF_MODEL", "").strip() or None
# Completion budget for the structured patient JSON (smaller = faster generation).
FEATHERLESS_PDF_MAX_TOKENS = int(os.getenv("FEATHERLESS_PDF_MAX_TOKENS", "900"))
# Per-request timeout for Featherless HTTP calls (seconds).
FEATHERLESS_HTTP_TIMEOUT = float(os.getenv("FEATHERLESS_HTTP_TIMEOUT", "120"))


def _featherless_pdf_api_key() -> str:
    """Key for PDF → patient profile calls. Use a dedicated key if set, else main key."""
    pdf = (os.getenv("FEATHERLESS_PDF_API_KEY") or "").strip()
    if pdf:
        return pdf
    return (os.getenv("FEATHERLESS_API_KEY") or "").strip()


# How many Mayo Clinic detail pages to scrape in parallel. We launch one
# Tinyfish browser agent per URL. The default is 2 because Tinyfish plans
# (observed empirically) seem to cap active browser sessions at 2 — going
# higher just causes the 3rd agent to wait server-side for a free slot.
# Bump this in your .env if your plan allows more simultaneous sessions.
MAYO_MAX_CONCURRENCY = int(os.getenv("MAYO_MAX_CONCURRENCY", "2"))

# NCI Clinical Trials Search (CTRP) API — a second, richer source of
# federally-registered oncology trials. Unlike ClinicalTrials.gov this one
# returns per-site phone/email contacts and much more granular eligibility
# criteria out of the box. Requires a free API key registered at
# https://clinicaltrialsapi.cancer.gov/ and sent as `x-api-key`.
NCI_API_URL = "https://clinicaltrialsapi.cancer.gov/api/v2/trials"
NCI_MAX_RESULTS = int(os.getenv("NCI_MAX_RESULTS", "5"))


def prewarm_featherless(reporter: "Reporter") -> None:
    """Fire a tiny request at the Featherless model in a background thread so
    that by the time Step 4 runs, the model is already resident on GPU and we
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
            reporter.log(f"Pre-warm failed (non-fatal, Step 4 will still run): {exc}")

    Thread(target=_run, daemon=True).start()


class FriendlyTranslator:
    """Rewrites technical pipeline log lines into patient-friendly one-liners
    using the small Featherless model, in the background.

    Design notes:
    - Single worker thread so we never burn more than one concurrent slot on
      the Featherless plan (scoring in Step 4 can already use up to
      FEATHERLESS_MAX_CONCURRENCY). Translations silently swallow 429s and
      any other errors so the raw log stream keeps flowing uninterrupted.
    - Results stream back to the UI as `friendly_status` SSE events via the
      given Reporter the moment each one lands.
    - Messages are capped to ~160 chars because they render on a single line
      in the status ticker.
    """

    SYSTEM_PROMPT = (
        "You help a cancer patient follow along as their clinical "
        "trial search runs live on screen. Rewrite the technical pipeline "
        "status below as ONE short, calm, friendly sentence (max 14 words) "
        "that a non-technical patient can understand. Use plain everyday "
        "language. You may keep simple medical terms (e.g. chemotherapy, "
        "HER2, metastatic). Do NOT include IDs, URLs, error codes, raw "
        "numbers from URLs, or jargon like HTTP, JSON, API, payload, "
        "request, retry, or attempt. Never quote the original text. Return "
        "only the rewritten sentence with no prefix, label, or quotes."
    )

    def __init__(self, api_key: str, model: str, reporter: "Reporter") -> None:
        self._model = model
        self._reporter = reporter
        self._client = OpenAI(api_key=api_key, base_url=FEATHERLESS_BASE_URL)
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="friendly"
        )

    def translate(self, raw_message: str, step: Optional[int] = None) -> None:
        """Fire and forget: rewrite `raw_message` and emit `friendly_status`."""
        if not raw_message or not raw_message.strip():
            return
        try:
            self._executor.submit(self._translate_and_emit, raw_message, step)
        except RuntimeError:
            # Executor already shut down — drop silently.
            pass

    def _translate_and_emit(
        self, raw_message: str, step: Optional[int]
    ) -> None:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": raw_message[:500]},
                ],
                max_tokens=40,
                temperature=0.3,
                timeout=15,
            )
            text = (resp.choices[0].message.content or "").strip()
            # Some instruct models love to wrap output in quotes or prepend
            # "Here is ..." — strip both so the ticker stays clean.
            text = text.strip('"').strip("'").strip()
            if text.lower().startswith(("here is", "here's", "sure")):
                after = text.split(":", 1)
                if len(after) == 2:
                    text = after[1].strip().strip('"').strip("'").strip()
            if not text:
                return
            text = text.splitlines()[0].strip()
            if len(text) > 160:
                text = text[:157].rstrip() + "..."
            self._reporter.friendly(text, step=step)
        except Exception:
            # Silent: if the translator can't keep up (429, timeout, etc.)
            # the raw log line is still visible on the backend and the UI
            # falls back gracefully to the last good friendly status.
            pass

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


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


def pick_best_location(
    locations: List[Dict[str, Any]], preferred_state: str = "MN"
) -> Dict[str, Any]:
    """Return the most patient-relevant location from a study's site list.

    Preference order:
    1. A site in the patient's preferred state (2-letter or full name).
    2. The first site that has at least a city + state.
    3. Whatever the first entry is.
    """
    preferred = _expand_state_set(preferred_state)
    if not locations:
        return {}
    for loc in locations:
        state = (loc.get("state") or "").strip().upper()
        if state in preferred:
            return loc
    for loc in locations:
        if (loc.get("city") or "").strip() and (loc.get("state") or "").strip():
            return loc
    return locations[0]


def _normalize_contact(raw: Dict[str, Any], fallback_role: str = "") -> Dict[str, str]:
    """Turn a ClinicalTrials.gov contact dict into our trimmed, display-ready shape."""
    if not isinstance(raw, dict):
        return {}
    name = (raw.get("name") or "").strip()
    role = (raw.get("role") or fallback_role or "").strip()
    phone = (raw.get("phone") or "").strip()
    ext = (raw.get("phoneExt") or "").strip()
    if phone and ext:
        phone = f"{phone} ext. {ext}"
    email = (raw.get("email") or "").strip()
    if not (name or phone or email):
        return {}
    return {"name": name, "role": role, "phone": phone, "email": email}


def extract_ctgov_contacts(
    contacts_module: Dict[str, Any], best_location: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Build the contact list for a ClinicalTrials.gov trial.

    Preference order:
    1. `centralContacts` (study-wide point of contact — "Study Contact"/backup).
    2. The best location's own `contacts` block if nothing at the study level.
    3. An `overallOfficials` entry as a last resort (typically the PI; no phone).
    """
    out: List[Dict[str, str]] = []
    seen: set = set()

    def _add(entry: Dict[str, str]) -> None:
        if not entry:
            return
        key = (entry.get("name", ""), entry.get("phone", ""), entry.get("email", ""))
        if key in seen:
            return
        seen.add(key)
        out.append(entry)

    for raw in contacts_module.get("centralContacts", []) or []:
        _add(_normalize_contact(raw, fallback_role="Study contact"))

    if not out and isinstance(best_location, dict):
        for raw in best_location.get("contacts", []) or []:
            _add(_normalize_contact(raw, fallback_role="Site contact"))

    if not out:
        for raw in contacts_module.get("overallOfficials", []) or []:
            _add(_normalize_contact(raw, fallback_role="Principal investigator"))

    return out


def fetch_clinical_trials(
    reporter: Reporter, patient: Dict[str, Any]
) -> List[Dict[str, Any]]:
    reporter.step(1, "running", "Querying ClinicalTrials.gov API...", title="ClinicalTrials.gov API")
    cond = search_condition_phrase(patient)
    zm = _lookup_zip_metadata(_patient_zip_string(patient))
    pref_state = zm.get("state") or "MN"
    geo_note = (
        f"near {_patient_zip_string(patient) or 'default Minneapolis area'}"
        if zm.get("lat")
        else "near Minneapolis MN (default geo — add ZIP in PDF for local matches)"
    )
    reporter.milestone(
        f"Searching ClinicalTrials.gov for recruiting trials matching “{cond}” ({geo_note}).",
        step=1,
    )
    ct_url = clinical_trials_gov_studies_url(patient)
    reporter.log(f"Request URL: {ct_url}", step=1)

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
            response = requests.get(ct_url, headers=headers, timeout=30)
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
        location_list = sections["contacts"].get("locations", []) or []
        best_location = pick_best_location(location_list, pref_state)
        phase_list = sections["design"].get("phases", [])

        nct_id = first_non_empty(
            [sections["identification"].get("nctId"), study.get("nctId")]
        )
        title = first_non_empty(
            [sections["identification"].get("briefTitle"), study.get("briefTitle")]
        )

        location_str = first_non_empty(
            [
                format_location(best_location),
                best_location.get("city"),
                study.get("locationCity"),
            ],
            "Location not listed",
        )
        sites_count = len(location_list)
        if sites_count > 1:
            location_display = f"{location_str} (+{sites_count - 1} more sites)"
        else:
            location_display = location_str

        contacts = extract_ctgov_contacts(sections["contacts"], best_location)

        trial_record = {
            "nct_id": nct_id,
            "nct_url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
            "title": title,
            "eligibility_criteria": truncate_text(
                first_non_empty(
                    [
                        sections["eligibility"].get("eligibilityCriteria"),
                        study.get("eligibilityCriteria"),
                    ]
                )
            ),
            "location": location_display,
            "sites_count": sites_count,
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
            "contacts": contacts,
        }
        normalized.append(trial_record)
        contact_summary = (
            f"{len(contacts)} contact(s): {contacts[0].get('name') or '—'}"
            if contacts
            else "no contact listed"
        )
        reporter.log(
            f"Normalized trial {idx}/{min(len(studies), 5)}: {nct_id or 'NCT?'} — "
            f"{title[:80] if title else 'Untitled'} — {location_display} — {contact_summary}",
            step=1,
        )
        reporter.translate(
            f"Adding ClinicalTrials.gov trial to your list: "
            f"{title[:140] if title else 'Untitled'} (location: {location_display}).",
            step=1,
        )
        reporter.trial(trial_record)

    reporter.step(
        1,
        "complete",
        f"Got {len(normalized)} trial(s) from ClinicalTrials.gov.",
        title="ClinicalTrials.gov API",
    )
    reporter.translate(
        f"Finished ClinicalTrials.gov — found {len(normalized)} trial(s) near you.",
        step=1,
    )
    return normalized


def _pick_best_nci_site(
    sites: List[Dict[str, Any]], preferred_state: str = "MN"
) -> Dict[str, Any]:
    """Pick the most patient-relevant NCI site.

    Preference: actively recruiting site in the patient's state, else any
    site in the patient's state, else any actively recruiting site, else the
    first site.
    """
    if not sites:
        return {}
    preferred = _expand_state_set(preferred_state)
    in_state = [
        s
        for s in sites
        if (s.get("org_state_or_province") or "").strip().upper() in preferred
    ]
    for s in in_state:
        if (s.get("recruitment_status") or "").upper() == "ACTIVE":
            return s
    if in_state:
        return in_state[0]
    for s in sites:
        if (s.get("recruitment_status") or "").upper() == "ACTIVE":
            return s
    return sites[0]


def _format_nci_location(site: Dict[str, Any]) -> str:
    parts = [
        site.get("org_name"),
        site.get("org_city"),
        site.get("org_state_or_province"),
    ]
    cleaned = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    return ", ".join(cleaned) if cleaned else ""


def _extract_nci_contacts(
    trial: Dict[str, Any], best_site: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Build the contact list for an NCI trial, preferring site-level phone/email
    (which is typically populated) over the mostly-empty central_contact.
    """
    out: List[Dict[str, str]] = []
    seen: set = set()

    def _add(entry: Dict[str, str]) -> None:
        if not entry:
            return
        key = (entry.get("name", ""), entry.get("phone", ""), entry.get("email", ""))
        if key in seen:
            return
        seen.add(key)
        out.append(entry)

    central = trial.get("central_contact") or {}
    if any(central.get(k) for k in ("name", "phone", "email")):
        _add(
            {
                "name": (central.get("name") or "").strip(),
                "role": "Study contact",
                "phone": (central.get("phone") or "").strip(),
                "email": (central.get("email") or "").strip(),
            }
        )

    if isinstance(best_site, dict) and best_site:
        _add(
            {
                "name": (best_site.get("contact_name") or best_site.get("org_name") or "").strip(),
                "role": "Site contact",
                "phone": (best_site.get("contact_phone") or best_site.get("org_phone") or "").strip(),
                "email": (best_site.get("contact_email") or best_site.get("org_email") or "").strip(),
            }
        )

    pi = trial.get("principal_investigator")
    if isinstance(pi, str) and pi.strip():
        _add({"name": pi.strip(), "role": "Principal investigator", "phone": "", "email": ""})

    return [c for c in out if c.get("name") or c.get("phone") or c.get("email")]


def _summarize_nci_eligibility(elig: Dict[str, Any]) -> str:
    """Flatten NCI structured + unstructured eligibility into a readable blob."""
    if not isinstance(elig, dict):
        return ""
    parts: List[str] = []
    structured = elig.get("structured") or {}
    if isinstance(structured, dict):
        pieces = []
        if structured.get("sex"):
            pieces.append(f"Sex: {structured['sex']}")
        min_age = structured.get("min_age") or ""
        max_age = structured.get("max_age") or ""
        if min_age or max_age:
            pieces.append(f"Age: {min_age or '—'} to {max_age or '—'}")
        if structured.get("accepts_healthy_volunteers") is not None:
            pieces.append(
                f"Healthy volunteers: "
                f"{'yes' if structured['accepts_healthy_volunteers'] else 'no'}"
            )
        if pieces:
            parts.append(" · ".join(pieces))

    for entry in elig.get("unstructured") or []:
        desc = (entry.get("description") or "").strip()
        if not desc:
            continue
        tag = "Inclusion" if entry.get("inclusion_indicator") else "Exclusion"
        parts.append(f"[{tag}] {desc}")

    return "\n".join(parts)


def fetch_nci_trials(
    reporter: Reporter, patient: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Pull oncology trials from the NCI CTRP API for the patient's condition + state."""
    reporter.step(2, "running", "Querying NCI Cancer.gov API...", title="NCI Cancer.gov API")

    api_key = os.getenv("NCI_API_KEY")
    if not api_key:
        reporter.log("NCI_API_KEY not set — skipping NCI Cancer.gov source.", step=2)
        reporter.step(
            2, "error", "NCI_API_KEY not configured.", title="NCI Cancer.gov API"
        )
        return []

    cond = search_condition_phrase(patient)
    zm = _lookup_zip_metadata(_patient_zip_string(patient))
    nci_state = (zm.get("state") or "MN").strip().upper()[:2]
    params = {
        "current_trial_status": "Active",
        "keyword": cond,
        "sites.org_state_or_province": nci_state,
        "sites.recruitment_status": "ACTIVE",
        "size": NCI_MAX_RESULTS,
    }
    reporter.milestone(
        f"Searching NCI Cancer.gov for active trials matching “{cond}” in {nci_state}.",
        step=2,
    )
    reporter.log(
        f"Request: GET {NCI_API_URL} (filters: {nci_state}, Active, keyword={cond[:80]})",
        step=2,
    )

    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "User-Agent": "TrialFind-MVP/0.1 (demo)",
    }

    max_attempts = 3
    response = None
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        reporter.log(f"HTTP GET attempt {attempt}/{max_attempts}...", step=2)
        try:
            response = requests.get(NCI_API_URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            reporter.log(
                f"HTTP {response.status_code} received ({len(response.content)} bytes).",
                step=2,
            )
            break
        except Exception as exc:
            last_error = exc
            reporter.log(f"Attempt {attempt} failed: {exc}", step=2)
            if attempt < max_attempts:
                time.sleep(2)
            else:
                raise
    if response is None:
        raise RuntimeError(f"NCI CTRP request failed: {last_error}")

    payload = response.json()
    trials = payload.get("data", []) or []
    reporter.log(
        f"Parsed response. {payload.get('total', len(trials))} total match(es); "
        f"taking first {len(trials)}.",
        step=2,
    )

    normalized: List[Dict[str, Any]] = []
    for idx, trial in enumerate(trials[:NCI_MAX_RESULTS], start=1):
        sites = trial.get("sites") or []
        best_site = _pick_best_nci_site(sites, nci_state)
        location_str = first_non_empty(
            [_format_nci_location(best_site), best_site.get("org_city")],
            "Location not listed",
        )
        if len(sites) > 1:
            location_display = f"{location_str} (+{len(sites) - 1} more sites)"
        else:
            location_display = location_str

        nct_id = (trial.get("nct_id") or "").strip()
        nci_id = (trial.get("nci_id") or "").strip()
        title = first_non_empty(
            [trial.get("brief_title"), trial.get("official_title")], "Untitled NCI study"
        )

        contacts = _extract_nci_contacts(trial, best_site)
        eligibility_blob = _summarize_nci_eligibility(trial.get("eligibility") or {})

        trial_record = {
            "nct_id": nct_id or None,
            "nct_url": (
                f"https://www.cancer.gov/research/participate/clinical-trials-search/v?id={nci_id}"
                if nci_id
                else (f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "")
            ),
            "title": title,
            "eligibility_criteria": truncate_text(eligibility_blob),
            "location": location_display,
            "sites_count": len(sites),
            "phase": first_non_empty([trial.get("phase")], "Unknown"),
            "summary": truncate_text(
                first_non_empty(
                    [trial.get("brief_summary"), trial.get("detail_description")]
                )
            ),
            "source": "NCI Cancer.gov",
            "contacts": contacts,
        }
        normalized.append(trial_record)
        contact_summary = (
            f"{len(contacts)} contact(s): {contacts[0].get('name') or '—'}"
            if contacts
            else "no contact listed"
        )
        reporter.log(
            f"Normalized trial {idx}/{min(len(trials), NCI_MAX_RESULTS)}: "
            f"{nct_id or nci_id or 'NCI?'} — {title[:80]} — {location_display} — {contact_summary}",
            step=2,
        )
        reporter.translate(
            f"Adding NCI Cancer.gov trial to your list: "
            f"{title[:140] if title else 'Untitled'} (location: {location_display}).",
            step=2,
        )
        reporter.trial(trial_record)

    reporter.translate(
        f"Finished NCI Cancer.gov — found {len(normalized)} trial(s) in {nci_state}.",
        step=2,
    )

    reporter.step(
        2,
        "complete",
        f"Got {len(normalized)} trial(s) from NCI Cancer.gov.",
        title="NCI Cancer.gov API",
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
            parsed = _json_decode_first_value(cleaned)
            return parse_tinyfish_result(parsed)
        except ValueError:
            return []
    return []


# Phase A: just pull the list of trial URLs from the search-results page.
# This is fast because it only loads one page and does no per-trial
# navigation. Keyword comes from `search_condition_phrase(patient)` at runtime.
MAYO_SEARCH_GOAL_TEMPLATE = """
You are on the Mayo Clinic Research clinical trials search results page for
the keyword "{keyword_display}", filtered to open/recruiting studies.

Identify the first 3 clinical trial result entries on the page. Each entry
normally has a title link and short descriptive text.

For each of those 3 entries, capture:
- title: the trial title text as shown.
- url: the absolute URL of the trial's detail page (the href of the title
  link). If the href is relative, prepend "https://www.mayo.edu" so the URL
  is absolute.
- status: the recruiting/enrolling status shown if visible, else "".
- location: any visible Mayo site/campus text (e.g. Rochester, Minnesota;
  Phoenix/Scottsdale, Arizona; Jacksonville, Florida). If unclear, use "".

Return ONLY a JSON array of up to 3 objects. Each object MUST have EXACTLY
these keys and nothing else: title, url, status, location.

No markdown. No prose. No code fences. Just the raw JSON array. Do NOT
open the detail pages — another agent will handle that. If fewer than 3
trials are shown, return whatever is available.
"""


def _mayo_search_url(keyword_url_encoded: str) -> str:
    return (
        "https://www.mayo.edu/research/clinical-trials/search-results"
        f"?keyword={keyword_url_encoded}"
        "&studySiteStatusesGrouped=Open%2FStatus+Unknown"
    )


# Phase B: for ONE detail URL, extract the heavy fields. A separate Tinyfish
# agent is spawned per URL and they all run in parallel.
MAYO_DETAIL_GOAL_TEMPLATE = """
You are on a Mayo Clinic Research clinical trial detail page at:
{detail_url}

Trial title (for context): {title}

From this single detail page extract:
- eligibility_text: the full text of the "Eligibility criteria" or
  "Inclusion/Exclusion Criteria" section. If not found, use "".
- summary_text: the short description / purpose paragraph near the top of
  the detail page. If not found, use "".
- contacts: an array of up to 2 contact objects pulled from the
  "Participating Mayo Clinic locations" table (or any similar Study /
  Research Contact block). Each object MUST have these keys:
    {{ "name": string, "role": string, "phone": string, "email": string }}
  Rules:
    - "name" is typically the contact person shown in the Contact column
      (not the principal investigator). If only a PI is visible, you may
      use the PI's name with role "Principal investigator".
    - "role" should be "Study contact" by default, or what the page
      explicitly labels the person.
    - "phone" should be the digits as shown (e.g. "(507) 422-5118" or
      "1-877-240-9479"). Use "" if not visible.
    - "email" should be the exact email if shown, else "".
  If the page shows no contact information, return contacts: [].

Return ONLY a single JSON object (not an array) with EXACTLY these keys and
nothing else: eligibility_text, summary_text, contacts.

No markdown. No prose. No code fences. Just the raw JSON object.
"""


def _run_tinyfish_agent(
    client: "TinyFish",
    goal: str,
    url: str,
    reporter: Reporter,
    tag: str = "agent",
) -> Any:
    """Run a single Tinyfish agent end-to-end and return its `result_json`.

    Streaming events (started / progress / heartbeat / complete) are logged
    via the Reporter with a per-agent tag so parallel agents remain
    distinguishable in the live activity panel.

    Thread-safe: Reporter's queue is thread-safe, and each call creates its
    own stream/state dict — there is no shared mutable state between
    concurrent invocations.
    """
    state: Dict[str, Any] = {
        "started_at": time.time(),
        "last_event_at": time.time(),
        "run_id": None,
        "streaming_url": None,
        "final_status": None,
        "result_json": None,
        "error": None,
        "progress_count": 0,
        # Flipped to True by on_complete so the consumer loop can bail out
        # instead of waiting for the SDK to also close the stream (which
        # tacks ~30 seconds of heartbeats onto every agent otherwise).
        "done": False,
    }

    def _elapsed() -> str:
        return f"{int(time.time() - state['started_at']):>3}s"

    def on_started(evt):
        state["run_id"] = getattr(evt, "run_id", None)
        state["last_event_at"] = time.time()
        reporter.log(
            f"[{tag}] started (run_id={state['run_id']}, elapsed={_elapsed()}).",
            step=3,
        )

    def on_streaming_url(evt):
        state["streaming_url"] = getattr(evt, "streaming_url", None)
        state["last_event_at"] = time.time()
        reporter.log(
            f"[{tag}] live browser stream: {state['streaming_url']}",
            step=3,
        )

    def on_progress(evt):
        state["progress_count"] += 1
        state["last_event_at"] = time.time()
        purpose = (getattr(evt, "purpose", "") or "").strip()
        reporter.log(f"[{tag}] {purpose or '(working…)'}", step=3)

    def on_heartbeat(_evt):
        since = int(time.time() - state["last_event_at"])
        reporter.log(
            f"[{tag}] heartbeat (elapsed {_elapsed()}, idle {since}s)",
            step=3,
        )

    def on_complete(evt):
        state["final_status"] = getattr(evt, "status", None)
        state["result_json"] = getattr(evt, "result_json", None)
        state["error"] = getattr(evt, "error", None)
        state["last_event_at"] = time.time()
        state["done"] = True
        reporter.log(
            f"[{tag}] complete: {state['final_status']}", step=3
        )

    stream = client.agent.stream(
        goal=goal,
        url=url,
        on_started=on_started,
        on_streaming_url=on_streaming_url,
        on_progress=on_progress,
        on_heartbeat=on_heartbeat,
        on_complete=on_complete,
    )
    # Stop consuming the stream as soon as the agent signals completion.
    # Without this we sit in the iterator for ~30 s of trailing heartbeats,
    # which (for parallel runs) is also time we're holding a concurrency
    # slot on the Tinyfish side.
    for _ in stream:
        if state["done"]:
            break
    try:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    except Exception:
        pass

    if state["error"]:
        raise RuntimeError(f"Tinyfish [{tag}] error: {state['error']}")

    raw = state["result_json"] or {}
    if isinstance(raw, dict) and str(raw.get("status") or "").lower() == "failed":
        reason = raw.get("reason") or raw.get("observation") or "unknown"
        raise RuntimeError(f"Tinyfish [{tag}] failed: {reason}")
    return raw


def _parse_mayo_detail_blob(raw: Any) -> Dict[str, Any]:
    """Turn a detail agent's raw result into a plain dict with our fields."""
    if isinstance(raw, str):
        try:
            raw = _json_decode_first_value(raw)
        except ValueError:
            return {}
    if isinstance(raw, list):
        # Some SDK paths wrap a single object in a single-element array.
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        return {}
    # Sometimes the payload lives under output / result / data / text
    for key in ("result", "output", "data", "trial", "details"):
        inner = raw.get(key)
        if isinstance(inner, dict) and any(
            k in inner for k in ("eligibility_text", "summary_text", "contacts")
        ):
            return inner
        if isinstance(inner, str):
            return _parse_mayo_detail_blob(inner)
    return raw


def _build_mayo_trial_record(
    search_entry: Dict[str, Any], detail: Dict[str, Any]
) -> Dict[str, Any]:
    title = (search_entry.get("title") or "Untitled Mayo trial").strip()
    url = (search_entry.get("url") or "").strip()
    location = (search_entry.get("location") or "Mayo Clinic (site-dependent)").strip()

    eligibility_text = (
        detail.get("eligibility_text")
        or detail.get("eligibility")
        or detail.get("eligibilityCriteria")
        or ""
    )
    summary_text = (
        detail.get("summary_text")
        or detail.get("summary")
        or detail.get("description")
        or ""
    )

    contacts_raw = detail.get("contacts") or []
    contacts: List[Dict[str, str]] = []
    if isinstance(contacts_raw, list):
        for c in contacts_raw:
            entry = _normalize_contact(
                c if isinstance(c, dict) else {}, fallback_role="Study contact"
            )
            if entry:
                contacts.append(entry)

    return {
        "nct_id": None,
        "title": title,
        "eligibility_criteria": truncate_text(str(eligibility_text)),
        "location": location,
        "phase": "Unknown",
        "summary": truncate_text(summary_text or url or "Sourced from Mayo Clinic listings."),
        "source": "Mayo Clinic",
        "mayo_url": url,
        "contacts": contacts,
    }


def _fix_mayo_trial_url(url: str) -> str:
    """Mayo agents sometimes return relative hrefs; detail fetch needs an absolute URL."""
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return "https://www.mayo.edu" + u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if "mayo.edu" in u:
        return "https://" + u.lstrip("/")
    return u


def _mayo_keyword_variants(primary_cond: str) -> List[str]:
    """Try the full condition first, then a shorter cancer phrase, then a broad fallback."""
    seen: set = set()
    out: List[str] = []

    def add(label: str) -> None:
        s = (label or "").strip()
        if len(s) < 2:
            return
        key = s.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(s)

    add(primary_cond)
    low = primary_cond.lower()
    for word in (
        "lung",
        "breast",
        "colon",
        "colorectal",
        "prostate",
        "ovarian",
        "pancreatic",
        "melanoma",
        "lymphoma",
        "leukemia",
        "kidney",
        "bladder",
        "liver",
        "sarcoma",
    ):
        if word in low:
            add(f"{word} cancer")
            break
    add("cancer")
    return out[:5]


def _fetch_mayo_search_list(
    client: "TinyFish",
    reporter: Reporter,
    search_url: str,
    search_goal: str,
) -> List[Dict[str, Any]]:
    """Phase A: one agent, returns a list of up to 3 {title,url,status,location}."""
    reporter.log(
        "Phase A: listing top 3 results from Mayo search page (single agent).",
        step=3,
    )
    raw = _run_tinyfish_agent(
        client,
        goal=search_goal,
        url=search_url,
        reporter=reporter,
        tag="search",
    )
    rows = parse_tinyfish_result(raw)
    reporter.log(
        f"Phase A: Tinyfish returned {len(rows)} row(s) after parsing (before URL filter).",
        step=3,
    )
    # Keep only entries that have a usable url to fan out on.
    usable: List[Dict[str, Any]] = []
    seen_urls: set = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        fixed = _fix_mayo_trial_url((r.get("url") or "").strip())
        if not fixed:
            continue
        if fixed in seen_urls:
            continue
        seen_urls.add(fixed)
        usable.append(
            {
                "title": (r.get("title") or "").strip() or "Untitled Mayo trial",
                "url": fixed,
                "status": (r.get("status") or "").strip(),
                "location": (r.get("location") or "").strip(),
            }
        )
    reporter.log(
        f"Phase A done: {len(usable)} trial URL(s) to fan out on.", step=3
    )
    return usable[:3]


def fetch_mayo_trials(
    reporter: Reporter, patient: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Scrape Mayo Clinic trials using two phases:

    Phase A — one agent that lists up to 3 trial URLs from the search page.
    Phase B — one agent per URL, running in parallel, each extracting
              eligibility / summary / contacts from a single detail page.

    Wall-clock time is roughly:  phaseA + max(detail_latency)
    instead of:                  phaseA + sum(detail_latency).
    """
    reporter.step(
        3,
        "running",
        "Launching Tinyfish browser agent on Mayo Clinic (Phase A)...",
        title="Mayo Clinic browser agent (Tinyfish)",
    )
    cond = search_condition_phrase(patient)
    keyword_variants = _mayo_keyword_variants(cond)

    api_key = os.getenv("TINYFISH_API_KEY")
    if not api_key:
        raise RuntimeError("TINYFISH_API_KEY is missing.")

    # Per the SDK (httpx-based), a single TinyFish client is safe to share
    # across threads — each client.agent.stream(...) call opens its own
    # server-side browser session.
    client = TinyFish(api_key=api_key)

    # ── Phase A: get the list of URLs (retry with simpler keywords if empty) ──
    search_entries: List[Dict[str, Any]] = []
    for attempt, kw in enumerate(keyword_variants, start=1):
        kw_url = quote_plus(kw)
        may_url = _mayo_search_url(kw_url)
        may_goal = MAYO_SEARCH_GOAL_TEMPLATE.format(
            keyword_display=kw.replace('"', "'")
        )
        reporter.milestone(
            f"Mayo Clinic search (try {attempt}/{len(keyword_variants)}): “{kw[:80]}”.",
            step=3,
        )
        reporter.log(f"Mayo Phase A target URL: {may_url}", step=3)
        search_entries = _fetch_mayo_search_list(
            client, reporter, may_url, may_goal
        )
        if search_entries:
            break
        reporter.log(
            f"Mayo Phase A: no usable links for keyword {kw[:80]!r} — trying next variant.",
            step=3,
        )

    if not search_entries:
        reporter.log(
            "Mayo Phase A exhausted all keyword variants with 0 trial links. "
            "Common causes: Tinyfish could not parse the search page JSON, "
            "Mayo changed their layout, or the browser session timed out.",
            step=3,
        )
        reporter.step(
            3,
            "complete",
            "Got 0 trial(s) from Mayo Clinic (search returned no links).",
            title="Mayo Clinic browser agent (Tinyfish)",
        )
        return []

    # ── Phase B: fan out detail agents in parallel ─────────────────────
    max_workers = min(len(search_entries), max(1, MAYO_MAX_CONCURRENCY))
    reporter.step(
        3,
        "running",
        f"Phase B: scraping {len(search_entries)} detail page(s) with "
        f"{max_workers} parallel agent(s)...",
        title="Mayo Clinic browser agent (Tinyfish)",
    )
    reporter.log(
        f"Phase B: dispatching {len(search_entries)} parallel Tinyfish "
        f"agent(s) (max_workers={max_workers}, cap={MAYO_MAX_CONCURRENCY}).",
        step=3,
    )

    trial_records: List[Optional[Dict[str, Any]]] = [None] * len(search_entries)
    completed = 0
    t0 = time.time()

    def _run_detail(idx: int, entry: Dict[str, Any]) -> Dict[str, Any]:
        tag = f"detail-{idx + 1}"
        start = time.time()
        goal = MAYO_DETAIL_GOAL_TEMPLATE.format(
            detail_url=entry["url"], title=entry["title"][:120]
        )
        try:
            raw = _run_tinyfish_agent(
                client,
                goal=goal,
                url=entry["url"],
                reporter=reporter,
                tag=tag,
            )
            detail = _parse_mayo_detail_blob(raw)
        except Exception as exc:
            reporter.log(
                f"[{tag}] permanently failed: {exc}", step=3
            )
            detail = {"eligibility_text": "", "summary_text": "", "contacts": []}

        elapsed_ms = int((time.time() - start) * 1000)
        contacts_found = len(detail.get("contacts") or [])
        reporter.log(
            f"[{tag}] finished in {elapsed_ms} ms "
            f"(eligibility={len(str(detail.get('eligibility_text') or ''))} chars, "
            f"contacts={contacts_found}).",
            step=3,
        )
        return detail

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_idx = {
            pool.submit(_run_detail, idx, entry): idx
            for idx, entry in enumerate(search_entries)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            detail = future.result()  # _run_detail never raises

            trial_record = _build_mayo_trial_record(search_entries[idx], detail)
            trial_records[idx] = trial_record
            reporter.trial(trial_record)
            completed += 1
            reporter.step(
                3,
                "running",
                f"Phase B: {completed}/{len(search_entries)} detail page(s) scraped…",
                title="Mayo Clinic browser agent (Tinyfish)",
            )
            reporter.translate(
                f"Read Mayo Clinic trial details: "
                f"{trial_record.get('title', 'Untitled')[:140]}.",
                step=3,
            )

    total_ms = int((time.time() - t0) * 1000)
    reporter.log(
        f"Phase B complete: {completed}/{len(search_entries)} detail "
        f"page(s) in {total_ms} ms (parallel, max_workers={max_workers}).",
        step=3,
    )

    # Return in original search-order for stability (emission order was
    # completion-order, which is fine for the UI).
    normalized = [
        r or _build_mayo_trial_record(search_entries[i], {})
        for i, r in enumerate(trial_records)
    ]
    reporter.step(
        3,
        "complete",
        f"Got {len(normalized)} trial(s) from Mayo Clinic.",
        title="Mayo Clinic browser agent (Tinyfish)",
    )
    reporter.translate(
        f"Finished Mayo Clinic — collected {len(normalized)} trial(s).",
        step=3,
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


SCORING_SYSTEM_PROMPT = (
    "You are a clinical trial matching assistant whose audience is the "
    "patient themselves, not a clinician. You write in warm, plain, "
    "second-person English ('you', 'your') and gently explain any "
    "necessary medical term the first time it appears in parentheses "
    "(e.g., 'HER2-positive (a type of breast cancer that grows faster)'). "
    "Keep essential clinical terms when they matter — don't oversimplify "
    "to the point of inaccuracy. "
    "Return ONLY a single valid JSON object. No markdown, no commentary, "
    "no code fences."
)


def _build_scoring_user_prompt(
    trial: Dict[str, Any], trial_index: int, patient_profile: Dict[str, Any]
) -> str:
    """User prompt for scoring exactly ONE trial.

    The model returns a single JSON object (not an array), which keeps
    the request tiny and lets us run many in parallel.
    """
    return f"""
Patient profile:
{json.dumps(patient_profile, indent=2)}

Trial to evaluate (trial_index = {trial_index}):
{json.dumps(trial, indent=2)}

Return ONE JSON object (not an array) with EXACTLY these keys:
- trial_index: integer — echo back {trial_index}.
- match_score: integer 0-100.
- match_level: one of "high", "medium", "low".
- rationale: 1-2 sentences written TO the patient ("you"), in plain
  language, explaining why this trial might or might not fit them. Keep
  important medical terms but briefly explain them. Avoid words like
  "cohort", "adjuvant", "neoadjuvant", "ECOG", "inclusion/exclusion
  criteria" unless you define them inline.
- key_eligibility_factors: array of 2-4 short strings, each phrased as
  what the patient would need to have/be (e.g., "You need to be 18 or
  older").
- potential_exclusions: array of short strings describing things that
  would likely disqualify them, phrased plainly. Use [] if none apply.
- plain_english_summary: 2-4 friendly sentences for the patient
  explaining (a) what the trial is testing and why, (b) what joining
  would look like at a high level, and (c) what this could mean for
  them. Keep it approachable but include important clinical nouns with
  brief definitions. Avoid hype or false promises.

Return ONE JSON object. No extra keys. No markdown fences.
"""


def _strip_markdown_json_fence(text: str) -> str:
    """Remove ``` / ```json wrappers if the model wrapped JSON in a fence."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()
    if not lines:
        return t
    # Drop opening ``` or ```json
    body: List[str] = []
    for line in lines[1:]:
        if line.strip().startswith("```"):
            break
        body.append(line)
    return "\n".join(body).strip()


def _json_decode_first_value(text: str) -> Any:
    """Decode the first JSON value in `text`, ignoring trailing prose (fixes 'Extra data')."""
    t = _strip_markdown_json_fence(text)
    if not t:
        raise ValueError("Empty model response.")
    decoder = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch not in "{[":
            continue
        try:
            val, _end = decoder.raw_decode(t, i)
            return val
        except json.JSONDecodeError:
            continue
    raise ValueError("No JSON value found in model response.")


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Pull the first well-formed JSON object out of a model response."""
    val = _json_decode_first_value(text)
    if isinstance(val, list) and len(val) == 1 and isinstance(val[0], dict):
        val = val[0]
    if not isinstance(val, dict):
        raise ValueError("Model response JSON was not an object.")
    return val


# --- PDF upload → pypdf JSON → Featherless patient profile (pathology / AVS) ---

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
# Max serialized JSON size sent to Featherless (pages[].text is truncated to fit).
MAX_PDF_JSON_CHARS = 16000

DOCUMENT_READ_SYSTEM_PROMPT = (
    "You receive JSON built from a patient's medical PDF (pypdf text extraction). "
    "It always has `format` and `page_count`. The text is in `full_text` (one "
    "string, preferred when present) **or** in `pages`: an array of "
    "{page_index, text} per page — use whichever fields you are given.\n\n"
    "You are not a doctor. This is not a diagnosis. Your job is to infer a "
    "**trial-matching patient profile** from the document text only.\n\n"
    "Return ONE JSON object with EXACTLY these keys:\n"
    '- summary: string — 2-4 sentences in plain language for the patient.\n'
    '- first_name: string or null — if clearly labeled (e.g. patient name).\n'
    '- last_name: string or null — if clearly labeled.\n'
    '- email: string or null — only if an email appears in the document.\n'
    '- age: integer or null — only if clearly stated (e.g. age, DOB-derived).\n'
    '- zip_code: string or null — US ZIP or postal info if present.\n'
    '- diagnosis: string or null — short clinical diagnosis line if present.\n'
    '- cancer_type: string or null — normalized: breast, lung, colorectal, etc.\n'
    '- stage: string or null — Roman numeral or stage description if stated.\n'
    '- biomarkers: object — string keys and string values, e.g. {"HER2": "positive"}; '
    "{} if none.\n"
    '- prior_treatments: array of strings — chemo, surgery, radiation, etc.; [] if none.\n'
    '- performance_status: string or null — ECOG 0-4 or Karnofsky if mentioned.\n'
    '- comorbidities: array of strings — other conditions; [] if none.\n'
    '- discuss_with_oncologist: string — one sentence reminding them to discuss '
    "this with their oncologist before any trial decisions.\n\n"
    "If the JSON has no usable medical text, say so in summary and use nulls/empty "
    "collections elsewhere.\n"
    "Return JSON only. No markdown fences."
)


def pdf_bytes_to_structured_json(data: bytes) -> Dict[str, Any]:
    """Extract per-page text with pypdf and return a single JSON-serializable dict."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages_out: List[Dict[str, Any]] = []
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        pages_out.append({"page_index": i + 1, "text": raw.strip()})
    full_text = "\n\n".join(p["text"] for p in pages_out if p["text"]).strip()
    return {
        "format": "pypdf_extract_v1",
        "page_count": len(reader.pages),
        "pages": pages_out,
        "full_text": full_text,
    }


def _json_compact(obj: Any) -> str:
    """Compact JSON for fewer input tokens and smaller payloads."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _normalize_extracted_pdf_text(text: str) -> str:
    """Collapse noisy whitespace so more clinical text fits under the char cap."""
    if not text:
        return ""
    t = text.replace("\x00", " ").strip()
    t = re.sub(r"\r\n?", "\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    return t.strip()


def _build_pdf_payload_for_model(doc: Dict[str, Any], max_chars: int) -> Dict[str, Any]:
    """Prefer a single `full_text` blob (less token overhead than per-page JSON).

    If that does not fit `max_chars`, fall back to a normalized `pages` array and
    trim from the last page until the payload fits.
    """
    import copy

    fmt = doc.get("format", "pypdf_extract_v1")
    pages_in = doc.get("pages") or []
    full_raw = (doc.get("full_text") or "").strip()
    full_norm = _normalize_extracted_pdf_text(full_raw) if full_raw else ""
    if not full_norm and pages_in:
        full_norm = _normalize_extracted_pdf_text(
            "\n\n".join((p.get("text") or "").strip() for p in pages_in)
        )

    pages_copy: List[Dict[str, Any]] = []
    for p in pages_in:
        txt = _normalize_extracted_pdf_text((p.get("text") or ""))
        pages_copy.append(
            {"page_index": p.get("page_index", len(pages_copy) + 1), "text": txt}
        )

    def size(obj: Any) -> int:
        return len(_json_compact(obj))

    only_full: Dict[str, Any] = {
        "format": fmt,
        "page_count": len(pages_copy) if pages_copy else (doc.get("page_count") or 0),
        "full_text": full_norm,
    }
    if size(only_full) <= max_chars:
        return only_full

    d: Dict[str, Any] = {
        "format": fmt,
        "page_count": len(pages_copy),
        "pages": copy.deepcopy(pages_copy),
    }
    while size(d) > max_chars:
        pages = d.get("pages") or []
        if not pages:
            d["pages"] = []
            d["page_count"] = 0
            return d
        last = pages[-1]
        txt = last.get("text") or ""
        if len(txt) > 400:
            last["text"] = txt[: len(txt) // 2]
        else:
            pages.pop()
            d["page_count"] = len(pages)

    return d


def featherless_read_prepared_pdf_dict(for_model: Dict[str, Any]) -> Dict[str, Any]:
    """Send already-shrunk pypdf JSON to Featherless; return patient profile fields."""
    api_key = _featherless_pdf_api_key()
    if not api_key:
        raise RuntimeError(
            "Featherless API key not configured "
            "(set FEATHERLESS_PDF_API_KEY or FEATHERLESS_API_KEY)"
        )
    model = FEATHERLESS_PDF_MODEL or FEATHERLESS_MODEL
    client = OpenAI(
        api_key=api_key,
        base_url=FEATHERLESS_BASE_URL,
        timeout=FEATHERLESS_HTTP_TIMEOUT,
    )
    user_body = _json_compact(for_model)
    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=FEATHERLESS_PDF_MAX_TOKENS,
        messages=[
            {"role": "system", "content": DOCUMENT_READ_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Parse this PDF extraction JSON and produce the patient profile JSON.\n"
                    f"{user_body}"
                ),
            },
        ],
        timeout=FEATHERLESS_HTTP_TIMEOUT,
    )
    raw_text = completion.choices[0].message.content or ""
    return _extract_json_object(raw_text)


def featherless_read_document(structured_pdf: Dict[str, Any]) -> Dict[str, Any]:
    """Shrink pypdf output to context limits, then call Featherless."""
    for_model = _build_pdf_payload_for_model(structured_pdf, MAX_PDF_JSON_CHARS)
    return featherless_read_prepared_pdf_dict(for_model)


def _pdf_extraction_public_meta(structured: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight summary for API clients (no full page text)."""
    pages = structured.get("pages") or []
    return {
        "format": structured.get("format"),
        "page_count": structured.get("page_count", len(pages)),
        "total_text_chars": len(structured.get("full_text") or ""),
        "chars_per_page": [len((p or {}).get("text") or "") for p in pages],
    }


def _is_concurrency_or_rate_limit(exc: Exception) -> bool:
    """Detect Featherless 429 / concurrency-limit responses.

    The OpenAI SDK surfaces these as RateLimitError / APIStatusError with
    status_code 429; we also pattern-match the body in case a newer client
    version reshapes the class hierarchy.
    """
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return (
        "429" in text
        or "concurrency_limit_exceeded" in text
        or "concurrency limit" in text
        or "rate limit" in text
    )


def _score_single_trial(
    client: OpenAI,
    trial: Dict[str, Any],
    trial_index: int,
    reporter: Reporter,
    patient_profile: Dict[str, Any],
    max_attempts: int = 5,
) -> Dict[str, Any]:
    """Score a single trial with its own retry loop.

    Retries use exponential backoff + jitter so that if we ever trip the
    plan's concurrency cap (e.g. another pipeline run overlaps), the retries
    spread out instead of thundering on the same slot.

    Thread-safe — Reporter's queue is thread-safe.
    """
    user_prompt = _build_scoring_user_prompt(trial, trial_index, patient_profile)
    last_error: Optional[Exception] = None
    title = (trial.get("title") or "Untitled")[:60]

    for attempt in range(1, max_attempts + 1):
        reporter.log(
            f"Trial {trial_index + 1} ({title}…) — request attempt "
            f"{attempt}/{max_attempts}",
            step=4,
        )
        try:
            completion = client.chat.completions.create(
                model=FEATHERLESS_MODEL,
                temperature=0,
                max_tokens=700,
                messages=[
                    {"role": "system", "content": SCORING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw_text = completion.choices[0].message.content or ""
            parsed = _extract_json_object(raw_text)
            # Always force the index back to what we asked for (the model
            # occasionally echoes it wrong on short context).
            parsed["trial_index"] = trial_index
            return parsed
        except Exception as exc:
            last_error = exc
            rate_limited = _is_concurrency_or_rate_limit(exc)
            # Summarize rather than dumping the whole 429 body into the UI.
            short_msg = "429 concurrency limit exceeded" if rate_limited else str(exc)
            reporter.log(
                f"Trial {trial_index + 1} attempt {attempt} failed: {short_msg}",
                step=4,
            )
            if attempt < max_attempts:
                # Exponential backoff with jitter. Longer for 429s, since
                # the slot is genuinely occupied and short retries will just
                # keep getting rejected.
                base = 3.0 if rate_limited else 1.5
                delay = base * (2 ** (attempt - 1)) + random.uniform(0, 0.75)
                reporter.log(
                    f"Trial {trial_index + 1} backing off {delay:.1f}s before retry.",
                    step=4,
                )
                time.sleep(delay)

    assert last_error is not None
    raise last_error


def _fallback_score(trial_index: int, reason: str) -> Dict[str, Any]:
    return {
        "trial_index": trial_index,
        "match_score": None,
        "match_level": "low",
        "rationale": f"Scoring failed: {reason}",
        "key_eligibility_factors": [],
        "potential_exclusions": [],
        "plain_english_summary": "We couldn't score this trial right now.",
    }


class TrialScorer:
    """Async per-trial scoring pipeline.

    As soon as a fetch step normalizes a trial it is handed to this scorer,
    which:
      1. Dedupes by NCT id so ClinicalTrials.gov / NCI overlap never gets
         scored (or shown) twice.
      2. Assigns a stable monotonic `trial_index` to each accepted trial.
      3. Submits a scoring job to a shared `ThreadPoolExecutor` sized to
         the Featherless plan's concurrency cap.
      4. Emits `scored_added` to the Reporter the instant each score lands.

    This means scoring overlaps with Steps 1-3 instead of being a separate
    terminal stage — the first trial starts getting scored while the Mayo
    browser-agent scrape is still running.
    """

    def __init__(
        self,
        reporter: "Reporter",
        max_workers: int,
        patient_profile: Dict[str, Any],
    ) -> None:
        self._reporter = reporter
        self._patient_profile = patient_profile
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="scorer",
        )
        self._lock = Lock()
        self._seen_nct: set = set()
        self._trials: List[Dict[str, Any]] = []  # in scheduling order
        self._futures: List[Future] = []
        self._scores: Dict[int, Dict[str, Any]] = {}
        self._submitted = 0
        self._completed = 0
        self._started_step4 = False

        api_key = os.getenv("FEATHERLESS_API_KEY")
        if api_key:
            # Shared OpenAI client — thread-safe connection pool under httpx.
            self._client: Optional[OpenAI] = OpenAI(
                api_key=api_key, base_url=FEATHERLESS_BASE_URL
            )
        else:
            self._client = None
            self._reporter.log(
                "FEATHERLESS_API_KEY missing — per-trial scoring disabled.",
                step=4,
            )

    # ── public API ─────────────────────────────────────────────────────

    def schedule(self, trial: Dict[str, Any]) -> bool:
        """Queue `trial` for scoring. Returns False if it's a duplicate."""
        nct = (trial.get("nct_id") or "").strip().upper()
        with self._lock:
            if nct and nct in self._seen_nct:
                return False
            if nct:
                self._seen_nct.add(nct)
            idx = len(self._trials)
            self._trials.append(trial)
            self._submitted += 1
            in_flight = self._submitted - self._completed

        if not self._started_step4:
            self._started_step4 = True
            self._reporter.step(
                4,
                "running",
                "Scoring trials as they arrive…",
                title="Featherless AI scoring",
            )

        title_short = (trial.get("title") or "Untitled")[:60]
        self._reporter.log(
            f"Queued trial {idx + 1} for scoring: {title_short}… "
            f"({in_flight} in flight)",
            step=4,
        )
        self._reporter.step(
            4,
            "running",
            f"{self._completed}/{self._submitted} scored "
            f"({in_flight} in flight)…",
            title="Featherless AI scoring",
        )

        if self._client is None:
            # No key — fabricate a failure score so the UI still renders a row.
            score = _fallback_score(idx, "FEATHERLESS_API_KEY missing")
            self._finalize(idx, trial, score, elapsed_ms=0)
            return True

        future = self._executor.submit(self._score_and_emit, idx, trial)
        with self._lock:
            self._futures.append(future)
        return True

    def wait(self) -> List[Dict[str, Any]]:
        """Block until every scheduled scoring job completes, then return
        the merged `{trial, score}` entries in scheduling order."""
        # Snapshot futures under lock so a late-scheduled trial is still
        # waited on correctly.
        while True:
            with self._lock:
                pending = [f for f in self._futures if not f.done()]
            if not pending:
                break
            for fut in pending:
                try:
                    fut.result()
                except Exception as exc:
                    self._reporter.log(f"Scoring future raised: {exc}", step=4)

        self._executor.shutdown(wait=True)

        out: List[Dict[str, Any]] = []
        with self._lock:
            for idx, trial in enumerate(self._trials):
                score = self._scores.get(idx) or _fallback_score(idx, "missing")
                out.append({"trial": trial, "score": score})
        return out

    @property
    def trials(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._trials)

    @property
    def submitted(self) -> int:
        return self._submitted

    @property
    def completed(self) -> int:
        return self._completed

    # ── internals ──────────────────────────────────────────────────────

    def _score_and_emit(self, idx: int, trial: Dict[str, Any]) -> None:
        start = time.time()
        try:
            score = _score_single_trial(
                self._client,
                trial,
                idx,
                self._reporter,
                self._patient_profile,
            )
        except Exception as exc:
            self._reporter.log(
                f"Trial {idx + 1} permanently failed after retries: {exc}",
                step=4,
            )
            score = _fallback_score(idx, str(exc))
        elapsed_ms = int((time.time() - start) * 1000)
        self._finalize(idx, trial, score, elapsed_ms=elapsed_ms)

    def _finalize(
        self,
        idx: int,
        trial: Dict[str, Any],
        score: Dict[str, Any],
        elapsed_ms: int,
    ) -> None:
        with self._lock:
            self._scores[idx] = score
            self._completed += 1
            completed = self._completed
            submitted = self._submitted
            in_flight = submitted - completed

        level = score.get("match_level") or "—"
        match_score = score.get("match_score")
        self._reporter.log(
            f"Trial {idx + 1} scored ({match_score if match_score is not None else '—'}"
            f" / {level}) in {elapsed_ms} ms.",
            step=4,
        )
        trial_title = (trial.get("title") or "Untitled")[:120]
        self._reporter.translate(
            f"Finished reviewing '{trial_title}' — rated a {level} match for you.",
            step=4,
        )

        # Stream the merged entry the instant the score lands.
        self._reporter.scored({"trial": trial, "score": score})

        self._reporter.step(
            4,
            "running",
            f"{completed}/{submitted} scored ({in_flight} in flight)…",
            title="Featherless AI scoring",
        )


def _serve_index() -> Response:
    index_path = os.path.join(_REACT_DIST, "index.html")
    if not os.path.exists(index_path):
        return Response(
            "React build not found. Run:\n\n"
            "    cd frontend && npm install && npm run build\n\n"
            "then reload this page.",
            status=503,
            mimetype="text/plain",
        )
    return send_from_directory(_REACT_DIST, "index.html")


@app.route("/")
def index() -> Response:
    return _serve_index()


@app.route("/assets/<path:filename>")
def react_assets(filename: str) -> Response:
    assets_dir = os.path.join(_REACT_DIST, "assets")
    return send_from_directory(assets_dir, filename)


@app.route("/api/health", methods=["GET"])
def api_health() -> Response:
    """Lightweight check that Flask is up and /api/* routes are registered."""
    return jsonify({"ok": True, "service": "trialfind-flask"})


# Two paths so dev (Vite proxy) and prod stay reliable: some setups mishandle /api/*.
@app.route("/api/read-pdf", methods=["POST", "OPTIONS"], strict_slashes=False)
@app.route("/read-pdf", methods=["POST", "OPTIONS"], strict_slashes=False)
def api_read_pdf() -> Response:
    """Accept a PDF upload, extract text locally, then interpret via Featherless."""
    # CORS preflight must hit this route, not the SPA catch-all (which used to 404 api/*).
    if request.method == "OPTIONS":
        return Response(status=204)
    try:
        return _api_read_pdf_impl()
    except Exception as exc:
        # Always return JSON so the SPA never gets an empty body on unexpected errors.
        print(f"api_read_pdf unexpected error: {exc}", flush=True)
        return jsonify({"error": f"Server error while reading PDF: {exc}"}), 500


def _api_read_pdf_impl() -> Response:
    if not _featherless_pdf_api_key():
        return jsonify(
            {
                "error": (
                    "Featherless API key not configured. "
                    "Set FEATHERLESS_PDF_API_KEY (PDF upload) and/or FEATHERLESS_API_KEY."
                )
            }
        ), 503
    if "file" not in request.files:
        return jsonify({"error": "Missing file field (use multipart name=file)."}), 400
    upload = request.files["file"]
    if not upload or not upload.filename:
        return jsonify({"error": "No file selected."}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only .pdf files are supported."}), 400
    data = upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "File too large."}), 413
    if len(data) == 0:
        return jsonify({"error": "Empty file."}), 400
    try:
        structured = pdf_bytes_to_structured_json(data)
    except Exception as exc:
        return jsonify({"error": f"Could not read PDF: {exc}"}), 400
    full_text = (structured.get("full_text") or "").strip()
    has_page_text = any(
        (p.get("text") or "").strip() for p in (structured.get("pages") or [])
    )
    if not full_text and not has_page_text:
        return jsonify(
            {
                "error": (
                    "No text could be extracted. Scanned/image-only PDFs need OCR — "
                    "try a text-based export from your hospital portal."
                )
            }
        ), 400
    raw_json_len = len(json.dumps(structured, ensure_ascii=False))
    for_model = _build_pdf_payload_for_model(structured, MAX_PDF_JSON_CHARS)
    json_chars = len(_json_compact(for_model))
    try:
        extracted_profile = featherless_read_prepared_pdf_dict(for_model)
    except ValueError as exc:
        return jsonify({"error": f"Could not parse model response: {exc}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
    _set_active_pdf_patient(extracted_profile)
    return jsonify(
        {
            "extracted_profile": extracted_profile,
            "missing_fields": missing_patient_input_ids(extracted_profile),
            "pdf_extraction": _pdf_extraction_public_meta(structured),
            "meta": {
                "filename": upload.filename,
                "bytes": len(data),
                "text_chars_extracted": len(full_text) if full_text else sum(
                    len((p.get("text") or "")) for p in (structured.get("pages") or [])
                ),
                "json_chars_sent_to_model": json_chars,
                "json_truncated_for_model": raw_json_len > MAX_PDF_JSON_CHARS,
            },
        }
    )


@app.route("/api/patient-profile", methods=["POST", "OPTIONS"], strict_slashes=False)
@app.route("/patient-profile", methods=["POST", "OPTIONS"], strict_slashes=False)
def api_patient_profile() -> Response:
    """Merge user-entered fields into the active PDF profile (same store as /read-pdf)."""
    if request.method == "OPTIONS":
        return Response(status=204)
    try:
        payload = request.get_json(force=True, silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Send a JSON object with profile fields to update."}), 400
        merge_patient_profile_updates(payload)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    merged = _active_pdf_patient or {}
    return jsonify(
        {
            "extracted_profile": merged,
            "missing_fields": missing_patient_input_ids(merged),
        }
    )


# SPA fallback: serve real files from dist when they exist, otherwise serve
# index.html. GET/HEAD only — do not bind POST/OPTIONS here or uploads and
# CORS preflights can match this rule and hit `abort(404)` for api/* paths.
@app.route("/<path:path>", methods=["GET", "HEAD"])
def spa_fallback(path: str) -> Response:
    if path.startswith(("find-trials", "api/")):
        abort(404)
    candidate = os.path.join(_REACT_DIST, path)
    if os.path.isfile(candidate):
        return send_from_directory(_REACT_DIST, path)
    return _serve_index()


def _run_pipeline(reporter: Reporter) -> Dict[str, Any]:
    started = time.time()
    errors: List[str] = []

    clinical_trials: List[Dict[str, Any]] = []
    nci_trials: List[Dict[str, Any]] = []
    mayo_trials: List[Dict[str, Any]] = []
    scored_trials: List[Dict[str, Any]] = []

    reporter.step(1, "pending", "Idle.", title="ClinicalTrials.gov API")
    reporter.step(2, "pending", "Idle.", title="NCI Cancer.gov API")
    reporter.step(3, "pending", "Idle.", title="Mayo Clinic browser agent (Tinyfish)")
    reporter.step(
        4,
        "pending",
        "Will score each trial as soon as it arrives.",
        title="Featherless AI scoring",
    )

    # Spin up the patient-friendly translator for this pipeline run. We hand
    # it to the reporter so any `reporter.milestone(...)` calls downstream
    # automatically fan out a technical log AND a friendly one-liner.
    featherless_key = os.getenv("FEATHERLESS_API_KEY")
    translator: Optional[FriendlyTranslator] = None
    _fs = (FEATHERLESS_FRIENDLY_STATUS or "").strip().lower()
    if featherless_key and _fs not in ("0", "false", "no", "off"):
        translator = FriendlyTranslator(
            featherless_key, FEATHERLESS_MODEL, reporter
        )
        reporter.translator = translator

    reporter.milestone(
        "Starting your clinical trial search across ClinicalTrials.gov, "
        "NCI Cancer.gov, and Mayo Clinic."
    )

    patient = get_patient_for_pipeline()
    if _active_pdf_patient is not None:
        reporter.milestone(
            "Using the patient profile from your uploaded PDF for trial matching."
        )

    prewarm_featherless(reporter)

    # Stand the async per-trial scorer up BEFORE any fetch step runs, and
    # attach it to the reporter. From this point on, every `reporter.trial()`
    # call (inside each fetch function) immediately hands the trial off to
    # the scorer, which scores it on a background thread — overlapping
    # scoring with the remaining fetch work.
    scorer = TrialScorer(
        reporter,
        max_workers=FEATHERLESS_MAX_CONCURRENCY,
        patient_profile=patient,
    )
    reporter.scorer = scorer

    try:
        clinical_trials = fetch_clinical_trials(reporter, patient)
    except Exception as exc:
        msg = f"Step 1 failed: {exc}"
        errors.append(msg)
        reporter.log(msg, step=1)
        reporter.step(1, "error", str(exc), title="ClinicalTrials.gov API")

    try:
        nci_trials = fetch_nci_trials(reporter, patient)
    except Exception as exc:
        msg = f"Step 2 failed: {exc}"
        errors.append(msg)
        reporter.log(msg, step=2)
        reporter.step(2, "error", str(exc), title="NCI Cancer.gov API")

    try:
        mayo_trials = fetch_mayo_trials(reporter, patient)
    except Exception as exc:
        msg = f"Step 3 failed: {exc}"
        errors.append(msg)
        reporter.log(msg, step=3)
        reporter.step(3, "error", str(exc), title="Mayo Clinic browser agent (Tinyfish)")

    if (
        os.getenv("TINYFISH_API_KEY")
        and len(mayo_trials) == 0
        and not any(str(e).startswith("Step 3 failed") for e in errors)
    ):
        errors.append(
            "Mayo Clinic: no trials were returned (0 search links). "
            "Broader keywords are retried automatically; if this persists, check Step 3 in the technical log."
        )

    # All fetch sources done — raw_trials is the deduped, schedule-ordered
    # list that the scorer already owns.
    raw_trials = scorer.trials
    reporter.milestone(
        f"Gathered {len(raw_trials)} unique trial(s) across all three sources — "
        f"waiting on the last few scoring jobs to finish."
    )

    if scorer.submitted == 0:
        reporter.step(4, "error", "No trials to score.", title="Featherless AI scoring")
        scored_trials = []
    else:
        if scorer.completed < scorer.submitted:
            reporter.step(
                4,
                "running",
                f"Waiting for the last {scorer.submitted - scorer.completed} "
                f"trial(s) to finish scoring…",
                title="Featherless AI scoring",
            )
        scored_trials = scorer.wait()
        reporter.step(
            4,
            "complete",
            f"Scored {len(scored_trials)} trial(s) in parallel as they arrived.",
            title="Featherless AI scoring",
        )
        reporter.translate(
            f"AI finished reviewing all {len(scored_trials)} trial(s) — "
            f"your matches are ranked.",
            step=4,
        )

    # Detach the scorer — downstream consumers of the final result payload
    # should not keep a handle into it.
    reporter.scorer = None

    elapsed_ms = int((time.time() - started) * 1000)
    reporter.milestone(
        f"All done in {elapsed_ms / 1000:.1f}s — "
        f"{len(scored_trials)} scored match(es) ready for you to review."
    )

    # Drain the translator's queue politely. We don't block the response on
    # any in-flight rewrites; the pipeline result is already complete and
    # the UI can stop listening the moment `done` fires.
    if translator is not None:
        translator.shutdown()
        reporter.translator = None

    return {
        "patient_profile": patient,
        "raw_trials": raw_trials,
        "scored_trials": scored_trials,
        "meta": {
            "counts": {
                "clinicaltrials_gov": len(clinical_trials),
                "nci_cancer_gov": len(nci_trials),
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
