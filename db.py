"""
db.py — Supabase helpers for TrialFind.

All writes use the service role key (bypasses RLS).
Never import this on the frontend — service key stays server-side only.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def _client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

def upsert_patient(profile: Dict[str, Any]) -> str:
    """Insert or update a patient row by email. Returns the patient UUID.

    `profile` keys (all optional except email):
        email, first_name, last_name, age, zip_code,
        diagnosis, cancer_type, stage,
        biomarkers (dict), prior_treatments (list), performance_status,
        comorbidities (list), raw_document_text, alerts_enabled, alert_frequency
    """
    email = profile.get("email")
    if not email:
        raise ValueError("patient profile must include an email address")

    row = {
        "email": email,
        "document_uploaded": bool(profile.get("raw_document_text")),
    }

    # Map every optional field we know about
    optional_fields = [
        "first_name", "last_name", "age", "zip_code",
        "diagnosis", "cancer_type", "stage",
        "biomarkers", "prior_treatments", "performance_status", "comorbidities",
        "raw_document_text", "alerts_enabled", "alert_frequency",
    ]
    for field in optional_fields:
        if field in profile:
            row[field] = profile[field]

    db = _client()
    result = (
        db.table("patients")
        .upsert(row, on_conflict="email")
        .execute()
    )
    return result.data[0]["id"]


def get_patient_by_email(email: str) -> Optional[Dict[str, Any]]:
    db = _client()
    result = db.table("patients").select("*").eq("email", email).maybe_single().execute()
    return result.data


def get_patient_by_id(patient_id: str) -> Optional[Dict[str, Any]]:
    db = _client()
    result = db.table("patients").select("*").eq("id", patient_id).maybe_single().execute()
    return result.data


def mark_patient_searched(patient_id: str) -> None:
    """Stamp last_search_at = now() after a pipeline run."""
    db = _client()
    db.table("patients").update({
        "last_search_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", patient_id).execute()


def get_patients_due_for_search() -> List[Dict[str, Any]]:
    """Return patients with alerts_enabled=true whose search is overdue.

    'Overdue' means last_search_at IS NULL (never searched) or more than
    7 days ago. Used by the weekly cron job.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    db = _client()
    result = (
        db.table("patients")
        .select("*")
        .eq("alerts_enabled", True)
        .or_(f"last_search_at.is.null,last_search_at.lt.{cutoff}")
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# Trial matches
# ---------------------------------------------------------------------------

_SOURCE_MAP = {
    "clinicaltrials.gov": "clinicaltrials",
    "nci cancer.gov": "nci",
    "mayo clinic": "mayo",
}

_SCORE_MAP = {
    "high": "strong",
    "medium": "possible",
    "low": "review",
}


def _map_source(raw_source: str) -> str:
    return _SOURCE_MAP.get((raw_source or "").lower().strip(), "clinicaltrials")


def _map_match_score(match_level: str) -> str:
    return _SCORE_MAP.get((match_level or "").lower().strip(), "review")


def save_trial_matches(patient_id: str, scored_trials: List[Dict[str, Any]]) -> None:
    """Bulk upsert scored trial results for a patient.

    `scored_trials` is the list produced by merge_trials_with_scores() in app.py:
        [{"trial": {...}, "score": {...}}, ...]

    Existing rows (same patient_id + nct_id) are updated in place.
    Trials without an nct_id (e.g. some Mayo rows) are skipped since the
    unique constraint requires it.
    """
    if not scored_trials:
        return

    # Fetch NCT ids we've already stored for this patient so we can flag new ones
    db = _client()
    existing = (
        db.table("trial_matches")
        .select("nct_id")
        .eq("patient_id", patient_id)
        .execute()
    )
    known_nct_ids = {row["nct_id"] for row in (existing.data or [])}

    rows = []
    for entry in scored_trials:
        trial = entry.get("trial") or {}
        score = entry.get("score") or {}

        nct_id = (trial.get("nct_id") or "").strip()
        if not nct_id:
            continue  # can't upsert without the unique key

        rows.append({
            "patient_id": patient_id,
            "nct_id": nct_id,
            "trial_title": trial.get("title"),
            "trial_source": _map_source(trial.get("source", "")),
            "trial_phase": trial.get("phase"),
            "trial_status": "Recruiting",
            "match_score": _map_match_score(score.get("match_level", "")),
            "criteria_breakdown": score,
            "was_new_trial": nct_id not in known_nct_ids,
        })

    if rows:
        db.table("trial_matches").upsert(
            rows, on_conflict="patient_id,nct_id"
        ).execute()


def get_trial_matches_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    db = _client()
    result = (
        db.table("trial_matches")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_new_unnotified_matches(patient_id: str) -> List[Dict[str, Any]]:
    """Trials that are new AND haven't been emailed yet — used by the alert job."""
    db = _client()
    result = (
        db.table("trial_matches")
        .select("*")
        .eq("patient_id", patient_id)
        .eq("was_new_trial", True)
        .eq("patient_notified", False)
        .execute()
    )
    return result.data or []


def mark_trials_notified(match_ids: List[str]) -> None:
    """Stamp patient_notified=true and notified_at=now() for a list of match UUIDs."""
    if not match_ids:
        return
    db = _client()
    db.table("trial_matches").update({
        "patient_notified": True,
        "notified_at": datetime.now(timezone.utc).isoformat(),
    }).in_("id", match_ids).execute()


# ---------------------------------------------------------------------------
# Watched trials
# ---------------------------------------------------------------------------

def upsert_watched_trial(patient_id: str, nct_id: str, title: str = "", status: str = "") -> None:
    db = _client()
    db.table("watched_trials").upsert({
        "patient_id": patient_id,
        "nct_id": nct_id,
        "trial_title": title,
        "trial_status": status,
        "last_status_check": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="patient_id,nct_id").execute()


def get_watched_trials_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    db = _client()
    result = (
        db.table("watched_trials")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_watched_trials_pending_notify() -> List[Dict[str, Any]]:
    """All watched trials with notify_on_open=true — for status-change alerts."""
    db = _client()
    result = (
        db.table("watched_trials")
        .select("*, patients(email, first_name, alerts_enabled)")
        .eq("notify_on_open", True)
        .execute()
    )
    return result.data or []


def update_watched_trial_status(watched_id: str, new_status: str) -> None:
    db = _client()
    db.table("watched_trials").update({
        "trial_status": new_status,
        "last_status_check": datetime.now(timezone.utc).isoformat(),
    }).eq("id", watched_id).execute()


# ---------------------------------------------------------------------------
# Email alert log
# ---------------------------------------------------------------------------

def log_email_alert(
    patient_id: str,
    email: str,
    alert_type: str,
    nct_ids: List[str],
    status: str = "sent",
    error_message: str = "",
) -> None:
    db = _client()
    row: Dict[str, Any] = {
        "patient_id": patient_id,
        "email_to": email,
        "alert_type": alert_type,
        "nct_ids": nct_ids,
        "status": status,
    }
    if error_message:
        row["error_message"] = error_message
    db.table("email_alerts").insert(row).execute()
