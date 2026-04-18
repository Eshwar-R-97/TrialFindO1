# TrialFind MVP

TrialFind is a barebones MVP that:
- pulls recruiting studies from ClinicalTrials.gov
- uses Tinyfish to gather Mayo Clinic trial info
- sends normalized trial data to Claude Sonnet for structured eligibility scoring

## Setup

1. Create and activate a virtual environment:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Add environment variables:
   - `cp .env.example .env`
   - set `ANTHROPIC_API_KEY` and `TINYFISH_API_KEY` in `.env`

## Run

- `python app.py`
- Open [http://127.0.0.1:5050](http://127.0.0.1:5050)
- Click **Find Trials**
- To use a different port: `PORT=8080 python app.py`

## API

- `GET /find-trials`
  - runs Step 1 ClinicalTrials.gov query
  - runs Step 2 Tinyfish Mayo extraction
  - runs Step 3 Claude scoring
  - returns both `raw_trials` and `scored_trials` plus metadata/errors
