# TrialFind

TrialFind is a clinical trial matching app that takes a patient's medical profile (uploaded as a PDF or entered manually) and finds relevant recruiting studies from three sources: **ClinicalTrials.gov**, **NCI Cancer.gov**, and **Mayo Clinic**, and more can be added. An AI model then scores each trial for patient compatibility and streams results in real time.

Built for the O1 Hackathon hosted in Minneapolis, MN by Ahmed Shahkhan, Adil Arya, and Eshwar Rajasekar.

---

## How It Works

1. **Upload a medical document** (PDF) — the app extracts a structured patient profile using Featherless AI
2. **Fill in any missing fields** — age, diagnosis, ZIP code, biomarkers, etc.
3. **Click "Find Trials"** — the pipeline runs across three trial sources in parallel:
   - Step 1: ClinicalTrials.gov REST API (public)
   - Step 2: NCI Cancer.gov API
   - Step 3: Mayo Clinic (browser automation via TinyFish)
4. **AI scoring streams in** — each trial is scored for match level, with rationale, as results arrive

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Backend | Python + Flask |
| AI | Featherless API (OpenAI-compatible endpoint) |
| Browser Agent | TinyFish (Mayo Clinic scraping) |
| Database | Supabase (PostgreSQL) |
| Streaming | Server-Sent Events (SSE) |

---

## API Keys You Need

### Required

| Service | How to Get | Environment Variable |
|---|---|---|
| **Featherless** | Sign up at [featherless.ai](https://featherless.ai) | `FEATHERLESS_API_KEY` |
| **TinyFish** | Sign up at [tinyfish.io](https://tinyfish.io) | `TINYFISH_API_KEY` |
| **NCI CTS API** | Register free at [clinicaltrialsapi.cancer.gov](https://clinicaltrialsapi.cancer.gov) | `NCI_API_KEY` |
| **Supabase URL** | Create a project at [supabase.com](https://supabase.com) | `SUPABASE_URL` |
| **Supabase Anon Key** | Found in your Supabase project settings → API | `SUPABASE_ANON_KEY` |
| **Supabase Service Key** | Found in your Supabase project settings → API | `SUPABASE_SERVICE_KEY` |

### Optional (Not Required to Run Core Features)

| Service | Purpose | Environment Variable | Notes |
|---|---|---|---|
| `TINYFISH_API_KEY_2` / `_3` | More parallel Mayo scrapes | Optional | Add extra keys to scrape more trials concurrently |
| `TINYFISH_SESSIONS_PER_KEY` | Sessions per TinyFish key | Optional | Default: `2` |
| `MAYO_MAX_CONCURRENCY` | Cap parallel Mayo agents | Optional | Defaults to sessions × number of keys |
| `MAYO_MAX_TRIALS` | Max Mayo trials to scrape | Optional | Useful for faster testing |
| **Resend API** | Email alerts (`cron.py`) | `RESEND_API_KEY` | **Not needed** — only used by the scheduled email alert feature in `cron.py`, which is not part of the main trial-finding pipeline |

> **ClinicalTrials.gov** requires no API key — it is a public endpoint.

---

## Setup

### 1. Clone and configure environment

```bash
git clone <your-repo-url>
cd TrialFindO1
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
# Required
FEATHERLESS_API_KEY=your_featherless_key_here
TINYFISH_API_KEY=your_tinyfish_key_here
NCI_API_KEY=your_nci_cts_key_here
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key_here
SUPABASE_SERVICE_KEY=your_supabase_service_role_key_here

# Optional: extra TinyFish keys for more parallel Mayo scrapes
TINYFISH_API_KEY_2=
TINYFISH_API_KEY_3=

# Optional: dev proxy bypass (uncomment if you get 404s in dev mode)
# VITE_API_BASE_URL=http://127.0.0.1:5050
```

### 2. Install backend dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Running Locally

### Development mode (recommended for local work)

Run **two terminals** simultaneously:

**Terminal 1 — Flask backend:**
```bash
source .venv/bin/activate
python app.py
# Runs at http://127.0.0.1:5050
```

**Terminal 2 — Vite dev server:**
```bash
cd frontend
npm run dev
# Runs at http://localhost:5173 (proxies API calls to :5050)
```

Then open **http://localhost:5173** in your browser.

### Production mode (single server)

Build the frontend once, then serve everything from Flask:

```bash
cd frontend
npm run build
cd ..
python app.py
```

Then open **http://127.0.0.1:5050** in your browser.

To use a different port:
```bash
PORT=8080 python app.py
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the React SPA |
| `GET` | `/api/health` | Health check |
| `POST` | `/read-pdf` | Upload a PDF → extract patient profile via Featherless |
| `POST` | `/patient-profile` | Update profile with user-entered fields |
| `GET` | `/find-trials` | Run full matching pipeline (blocking) |
| `GET` | `/find-trials-stream` | Run pipeline with real-time SSE streaming |
| `GET` | `/api/cron/hourly-check` | Trigger scheduled email alerts *(optional feature)* |

---

## What Is Not Necessary

The following pieces of code and services are **not required** to run the core trial-matching feature. You can ignore or remove them entirely:

### `cron.py` — Scheduled Email Alerts
- Sends email alerts to a hardcoded recipient when new trial matches are found
- Requires a **Resend API key** (not included in `.env.example`)
- Triggered via `GET /api/cron/hourly-check`
- **Not called by the frontend** — safe to ignore completely

### `db.py` + Supabase Patient Records
- Persists patient profiles to a Supabase database table
- The trial-finding pipeline reads the patient profile from **in-memory app state**, not the database
- If you remove Supabase, the app still finds and scores trials; you just lose cross-session patient record persistence
- The frontend Supabase client (`frontend/src/lib/supabase.ts`) is initialized but not actively used in the main flow

### `static/` and `templates/` folders
- These are **legacy Flask templates** from an earlier version of the app
- The current app uses the React frontend in `frontend/`
- Safe to delete

### Multiple TinyFish Keys (`TINYFISH_API_KEY_2`, `_3`)
- Only needed if you want to scrape more than 2 Mayo Clinic detail pages in parallel
- A single `TINYFISH_API_KEY` is sufficient for basic use

### `MAYO_MAX_TRIALS` / `MAYO_MAX_CONCURRENCY`
- Performance tuning only
- Not setting these just means the app uses sensible defaults

---

## Project Structure

```
TrialFindO1/
├── app.py                  # Flask backend — full pipeline (PDF parsing, trial fetching, AI scoring, SSE)
├── db.py                   # Supabase helpers — optional, for patient record persistence
├── cron.py                 # Email alert scheduler — optional, not core to trial matching
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── assets/                 # SVG brand icons
├── static/                 # Legacy compiled assets — not used, safe to ignore
├── templates/              # Legacy Flask templates — not used, safe to ignore
└── frontend/               # React TypeScript frontend
    ├── src/
    │   ├── App.tsx         # Main layout
    │   ├── components/     # UI components (upload, profile form, results table, etc.)
    │   ├── hooks/          # useTrialStream — SSE state management
    │   ├── lib/            # API URL helpers, Supabase client
    │   └── types.ts        # Shared TypeScript types
    ├── vite.config.ts      # Dev proxy config (5173 → 5050)
    └── package.json
```

---

## Troubleshooting

**Empty results / 404 on API calls in dev mode**
Uncomment `VITE_API_BASE_URL=http://127.0.0.1:5050` in `.env` — this bypasses the Vite proxy and calls Flask directly.

**Mayo Clinic step is slow**
Add a second TinyFish key (`TINYFISH_API_KEY_2`) to double parallel scraping capacity, or set `MAYO_MAX_TRIALS=6` to cap how many detail pages are fetched.

**PDF extraction returns empty fields**
The PDF must be machine-readable (not a scanned image). Medical summaries, discharge notes, or pathology reports work best.
