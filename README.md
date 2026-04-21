# Automated Apply Public

Local, auditable automation for discovering jobs on public company career pages, filtering eligible roles in Italy and Ireland, and supporting assisted form filling with human review.

## Scope

- searches public career pages and known ATS platforms;
- accepts remote roles in Italy or Ireland;
- accepts onsite or hybrid roles only in Ireland;
- restricts salary currencies to EUR or USD when compensation is listed;
- generates tailored resumes only from grounded local candidate evidence;
- blocks automatic submission when confidence is low, fields are unknown, or human review is still required.

## Safe Publication

This public copy does not include:

- the candidate's real profile;
- the real experience inventory;
- the operational list of target companies;
- local reputation notes;
- runtime-collected job links;
- resumes, attachments, local databases, caches, or browser profiles.

User-specific files must be created locally from the templates in `data/`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

## Configuration

Create these files locally from the templates:

- `data/candidate_profile.yaml`
- `data/experience_inventory.yaml`
- `data/target_sources.yaml`
- `data/company_ratings.yaml`
- `data/blacklist.yaml`
- `data/sample_posts.json`

## Commands

```powershell
python -m app.main init-db
python -m app.main scan-company-sites --max-jobs 50
python -m app.main review-jobs
python -m app.main tailor-resumes --limit 1
python -m app.main apply --mode fill_only
python -m unittest discover -s tests
```

## Structure

- `app/`: automation, extraction, classification, autofill, and persistence.
- `scripts/`: local shortcuts for scanning, applying, and Claude CLI usage.
- `tests/`: coverage for deterministic rules, extraction, and safe runtime behavior.
- `data/`: public templates only; real user files are ignored by Git.
