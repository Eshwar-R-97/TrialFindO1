"""
cron.py — TrialFind scheduled jobs.

Run standalone:
    python cron.py

Or hit the Flask endpoint (useful for Vercel cron / external scheduler):
    GET /api/cron/hourly-check

The hourly job checks whether any patient has first_name = 'Maria' and
sends a test alert email to eshwar.rajasekar@gmail.com via Resend.
"""

import os

import resend
from dotenv import load_dotenv

load_dotenv()

ALERT_RECIPIENT = "eshwar.rajasekar@gmail.com"
FROM_ADDRESS = "TrialFind <onboarding@resend.dev>"  # swap for verified domain in production


def send_maria_alert(first_name: str) -> dict:
    resend.api_key = os.getenv("RESEND_API_KEY")
    return resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": ALERT_RECIPIENT,
        "subject": "TrialFind: Trial available for your patient",
        "text": f"{first_name} has an available trial",
    })


def run_hourly_check() -> dict:
    """Check for patients named Maria and send an alert if found."""
    # Import here so this file is usable without a full DB connection during unit tests
    from db import _client

    db = _client()
    result = (
        db.table("patients")
        .select("id, first_name, email")
        .ilike("first_name", "maria")
        .execute()
    )

    matches = result.data or []
    print(f"[cron] hourly-check: found {len(matches)} patient(s) named Maria.")

    alerts_sent = []
    for patient in matches:
        name = patient.get("first_name", "Maria")
        print(f"[cron] Sending alert for patient {patient['id']} ({name})...")
        try:
            response = send_maria_alert(name)
            print(f"[cron] Email sent. Resend id: {response.get('id')}")
            alerts_sent.append({"patient_id": patient["id"], "status": "sent", "resend_id": response.get("id")})
        except Exception as exc:
            print(f"[cron] Failed to send email: {exc}")
            alerts_sent.append({"patient_id": patient["id"], "status": "failed", "error": str(exc)})

    return {"patients_found": len(matches), "alerts": alerts_sent}


if __name__ == "__main__":
    result = run_hourly_check()
    print(result)
