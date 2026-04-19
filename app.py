import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Thread
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, send_from_directory, stream_with_context
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

# Serve the built React app out of `frontend/dist`. During development the
# React app is run via `npm run dev` (Vite on :5173) which proxies the
# `/find-trials*` endpoints back to this Flask server. In production we build
# once (`cd frontend && npm run build`) and Flask serves the static bundle.
_REACT_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
app = Flask(__name__, static_folder=None)

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
# Featherless plans enforce a per-account concurrency limit (e.g.
# feather_pro_plus = 4 simultaneous requests on llama31-8b). We cap our
# worker pool to this value so we don't get 429s. Override via env var if
# your plan allows more.
FEATHERLESS_MAX_CONCURRENCY = int(os.getenv("FEATHERLESS_MAX_CONCURRENCY", "4"))

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


# Patient's preferred state/region — used to pick the most relevant trial site
# out of the (often many) sites a ClinicalTrials.gov study has.
PATIENT_PREFERRED_STATES = {"MINNESOTA", "MN"}


def pick_best_location(locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the most patient-relevant location from a study's site list.

    Preference order:
    1. A site in the patient's preferred state.
    2. The first site that has at least a city + state.
    3. Whatever the first entry is.
    """
    if not locations:
        return {}
    for loc in locations:
        state = (loc.get("state") or "").strip().upper()
        if state in PATIENT_PREFERRED_STATES:
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
        location_list = sections["contacts"].get("locations", []) or []
        best_location = pick_best_location(location_list)
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
        reporter.trial(trial_record)

    reporter.step(
        1,
        "complete",
        f"Got {len(normalized)} trial(s) from ClinicalTrials.gov.",
        title="ClinicalTrials.gov API",
    )
    return normalized


def _pick_best_nci_site(sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick the most patient-relevant NCI site.

    Preference: actively recruiting site in the patient's state, else any
    site in the patient's state, else any actively recruiting site, else the
    first site.
    """
    if not sites:
        return {}
    in_state = [
        s for s in sites
        if (s.get("org_state_or_province") or "").strip().upper()
        in PATIENT_PREFERRED_STATES
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


def fetch_nci_trials(reporter: Reporter) -> List[Dict[str, Any]]:
    """Pull breast-cancer trials with MN sites from the NCI CTRP API."""
    reporter.step(2, "running", "Querying NCI Cancer.gov API...", title="NCI Cancer.gov API")

    api_key = os.getenv("NCI_API_KEY")
    if not api_key:
        reporter.log("NCI_API_KEY not set — skipping NCI Cancer.gov source.", step=2)
        reporter.step(
            2, "error", "NCI_API_KEY not configured.", title="NCI Cancer.gov API"
        )
        return []

    params = {
        "current_trial_status": "Active",
        "keyword": "breast cancer",
        "sites.org_state_or_province": "MN",
        "sites.recruitment_status": "ACTIVE",
        "size": NCI_MAX_RESULTS,
    }
    reporter.log(
        "Searching NCI CTRP for active breast cancer trials recruiting in Minnesota.",
        step=2,
    )
    reporter.log(f"Request: GET {NCI_API_URL} (filters: MN, Active, breast cancer)", step=2)

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
        best_site = _pick_best_nci_site(sites)
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
        reporter.trial(trial_record)

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

# Phase A: just pull the list of trial URLs from the search-results page.
# This is fast because it only loads one page and does no per-trial
# navigation.
MAYO_SEARCH_GOAL = """
You are on the Mayo Clinic Research clinical trials search results page for
the keyword "breast cancer", filtered to open/recruiting studies.

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
            raw = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    raw = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return {}
            else:
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


def _fetch_mayo_search_list(
    client: "TinyFish", reporter: Reporter
) -> List[Dict[str, Any]]:
    """Phase A: one agent, returns a list of up to 3 {title,url,status,location}."""
    reporter.log(
        "Phase A: listing top 3 results from Mayo search page (single agent).",
        step=3,
    )
    raw = _run_tinyfish_agent(
        client,
        goal=MAYO_SEARCH_GOAL,
        url=MAYO_SEARCH_URL,
        reporter=reporter,
        tag="search",
    )
    rows = parse_tinyfish_result(raw)
    # Keep only entries that have a usable url to fan out on.
    usable = [
        {
            "title": (r.get("title") or "").strip() or "Untitled Mayo trial",
            "url": (r.get("url") or "").strip(),
            "status": (r.get("status") or "").strip(),
            "location": (r.get("location") or "").strip(),
        }
        for r in rows
        if isinstance(r, dict) and (r.get("url") or "").strip()
    ]
    reporter.log(
        f"Phase A done: {len(usable)} trial URL(s) to fan out on.", step=3
    )
    return usable[:3]


def fetch_mayo_trials(reporter: Reporter) -> List[Dict[str, Any]]:
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
    reporter.log(f"Target URL: {MAYO_SEARCH_URL}", step=3)

    api_key = os.getenv("TINYFISH_API_KEY")
    if not api_key:
        raise RuntimeError("TINYFISH_API_KEY is missing.")

    # Per the SDK (httpx-based), a single TinyFish client is safe to share
    # across threads — each client.agent.stream(...) call opens its own
    # server-side browser session.
    client = TinyFish(api_key=api_key)

    # ── Phase A: get the list of URLs ──────────────────────────────────
    search_entries = _fetch_mayo_search_list(client, reporter)
    if not search_entries:
        reporter.step(
            3,
            "complete",
            "Got 0 trial(s) from Mayo Clinic.",
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


def _build_scoring_user_prompt(trial: Dict[str, Any], trial_index: int) -> str:
    """User prompt for scoring exactly ONE trial.

    The model returns a single JSON object (not an array), which keeps
    the request tiny and lets us run many in parallel.
    """
    return f"""
Patient profile:
{json.dumps(DEMO_PATIENT, indent=2)}

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


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Pull the first well-formed JSON object out of a model response."""
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON object found in Featherless response.")


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
    max_attempts: int = 5,
) -> Dict[str, Any]:
    """Score a single trial with its own retry loop.

    Retries use exponential backoff + jitter so that if we ever trip the
    plan's concurrency cap (e.g. another pipeline run overlaps), the retries
    spread out instead of thundering on the same slot.

    Thread-safe — Reporter's queue is thread-safe.
    """
    user_prompt = _build_scoring_user_prompt(trial, trial_index)
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


def score_trials_with_featherless(
    trials: List[Dict[str, Any]], reporter: Reporter
) -> List[Dict[str, Any]]:
    """Score all trials in parallel, emitting each result the moment it lands.

    One Featherless chat completion is issued per trial. Each request runs in
    its own worker thread, so total Step-3 wall time is roughly the latency
    of the slowest single request (instead of the sum of all of them).
    """
    reporter.step(
        4,
        "running",
        f"Scoring {len(trials)} trial(s) with Featherless AI in parallel...",
        title="Featherless AI scoring",
    )

    if not trials:
        reporter.step(
            4, "complete", "No trials to score.", title="Featherless AI scoring"
        )
        return []

    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        raise RuntimeError("FEATHERLESS_API_KEY is missing.")

    # The OpenAI Python client is safe to share across threads — it wraps
    # httpx.Client, which uses a thread-safe connection pool.
    client = OpenAI(api_key=api_key, base_url=FEATHERLESS_BASE_URL)

    # Cap parallelism to the Featherless plan's concurrency limit. Firing
    # more requests than the plan allows just wastes retries on 429 errors.
    max_workers = min(len(trials), max(1, FEATHERLESS_MAX_CONCURRENCY))
    reporter.log(
        f"Dispatching {len(trials)} scoring request(s) to "
        f"{FEATHERLESS_MODEL} (max_workers={max_workers}, "
        f"plan cap={FEATHERLESS_MAX_CONCURRENCY}).",
        step=4,
    )

    scores: List[Optional[Dict[str, Any]]] = [None] * len(trials)
    completed = 0
    t0 = time.time()

    def _run_one(idx: int, trial: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        try:
            score = _score_single_trial(client, trial, idx, reporter)
        except Exception as exc:
            reporter.log(
                f"Trial {idx + 1} permanently failed after retries: {exc}",
                step=4,
            )
            score = _fallback_score(idx, str(exc))

        elapsed_ms = int((time.time() - start) * 1000)
        reporter.log(
            f"Trial {idx + 1} scored "
            f"({score.get('match_score', '—')} / {score.get('match_level', '—')}) "
            f"in {elapsed_ms} ms.",
            step=4,
        )
        return score

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_idx = {
            pool.submit(_run_one, idx, trial): idx
            for idx, trial in enumerate(trials)
        }

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            score = future.result()  # _run_one never raises; exceptions become fallbacks
            scores[idx] = score

            # Stream this one merged entry to the UI the instant it's ready,
            # so users see the table fill in as each parallel agent finishes.
            entry = {"trial": trials[idx], "score": score}
            reporter.scored(entry)

            completed += 1
            reporter.step(
                4,
                "running",
                f"Scored {completed}/{len(trials)} trial(s) in parallel…",
                title="Featherless AI scoring",
            )

    total_elapsed_ms = int((time.time() - t0) * 1000)
    reporter.log(
        f"All {len(trials)} trial(s) scored in {total_elapsed_ms} ms total "
        f"(parallel, max_workers={max_workers}).",
        step=4,
    )
    reporter.step(
        4,
        "complete",
        f"Scored {len(trials)} trial(s) in parallel.",
        title="Featherless AI scoring",
    )

    # Return in input-order so merge_trials_with_scores (and anything
    # downstream) sees a stable shape regardless of completion order.
    return [s if s is not None else _fallback_score(i, "missing") for i, s in enumerate(scores)]


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


# SPA fallback: serve real files from dist when they exist, otherwise serve
# index.html. API routes (find-trials, find-trials-stream) take precedence
# because they are registered above with more specific rules.
@app.route("/<path:path>")
def spa_fallback(path: str) -> Response:
    if path.startswith(("find-trials", "api/")):
        abort(404)
    candidate = os.path.join(_REACT_DIST, path)
    if os.path.isfile(candidate):
        return send_from_directory(_REACT_DIST, path)
    return _serve_index()


def _dedupe_trials_by_nct_id(
    trials: List[Dict[str, Any]], reporter: Reporter
) -> List[Dict[str, Any]]:
    """Collapse duplicate studies across sources by their NCT id.

    When two sources return the same NCT id (common for ClinicalTrials.gov
    and NCI CTRP) we keep the first occurrence — earlier sources (ctgov)
    already have patient-location-aware site selection — and drop the
    duplicates. Trials without an nct_id (e.g. Mayo rows) are always kept.
    """
    seen: set = set()
    out: List[Dict[str, Any]] = []
    dropped = 0
    for trial in trials:
        nct = (trial.get("nct_id") or "").strip().upper()
        if nct:
            if nct in seen:
                dropped += 1
                continue
            seen.add(nct)
        out.append(trial)
    if dropped:
        reporter.log(f"De-duplicated {dropped} overlapping trial(s) by NCT id.")
    return out


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
    reporter.step(4, "pending", "Idle.", title="Featherless AI scoring")
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
        nci_trials = fetch_nci_trials(reporter)
    except Exception as exc:
        msg = f"Step 2 failed: {exc}"
        errors.append(msg)
        reporter.log(msg, step=2)
        reporter.step(2, "error", str(exc), title="NCI Cancer.gov API")

    try:
        mayo_trials = fetch_mayo_trials(reporter)
    except Exception as exc:
        msg = f"Step 3 failed: {exc}"
        errors.append(msg)
        reporter.log(msg, step=3)
        reporter.step(3, "error", str(exc), title="Mayo Clinic browser agent (Tinyfish)")

    combined = clinical_trials + nci_trials + mayo_trials
    raw_trials = _dedupe_trials_by_nct_id(combined, reporter)
    reporter.log(
        f"Combined raw trials: {len(raw_trials)} unique "
        f"(ClinicalTrials.gov={len(clinical_trials)}, NCI={len(nci_trials)}, "
        f"Mayo={len(mayo_trials)})"
    )

    if raw_trials:
        try:
            # score_trials_with_featherless() dispatches one parallel request
            # per trial and emits `scored_added` events to the Reporter the
            # moment each one lands, so we don't re-emit here.
            scores = score_trials_with_featherless(raw_trials, reporter)
            scored_trials = merge_trials_with_scores(raw_trials, scores)
        except Exception as exc:
            msg = f"Step 4 failed: {exc}"
            errors.append(msg)
            reporter.log(msg, step=4)
            reporter.step(4, "error", str(exc), title="Featherless AI scoring")
            scored_trials = []
    else:
        reporter.step(4, "error", "No trials to score.", title="Featherless AI scoring")

    elapsed_ms = int((time.time() - started) * 1000)
    reporter.log(f"All steps finished in {elapsed_ms} ms.")
    return {
        "patient_profile": DEMO_PATIENT,
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
