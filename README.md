# NIAT DecisionBridge AI

A full-stack student–parent decision-readiness workflow and counsellor handoff prototype for the NxtWave NIAT Growth Hack Challenge.

## Features
- Student profile and parent/guardian perspective intake.
- Multi-step decision room with separate student and parent concerns.
- LangGraph workflow + OpenAI API integration when `OPENAI_API_KEY` is configured.
- Deterministic demo mode when no API key is configured.
- Source-grounded knowledge snippets with links to NIAT's official website.
- PostgreSQL (Supabase) or local SQLite storage.
- Counsellor pipeline, status updates, lead search, metrics and copyable decision briefs.
- Single-origin React + FastAPI deployment via Docker.

## Run locally

Requirements: Python 3.11+, Node.js 20+.

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (new terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies are not required if you set `VITE_API_URL=http://localhost:8000` in `frontend/.env.local` before running the dev server. For convenience, create that file with:

```env
VITE_API_URL=http://localhost:8000
```

API docs: http://localhost:8000/docs

## Environment variables

- `DATABASE_URL`: PostgreSQL connection URI. If omitted, the backend uses a local SQLite database.
- `OPENAI_API_KEY`: Optional. If absent, deterministic demo analysis runs.
- `OPENAI_MODEL`: Defaults to `gpt-4o-mini`.
- `PORT`: Set automatically by Render.

Never commit `.env`, database credentials, or API keys.

## Free deployment: Render + Supabase + GitHub

1. Create a GitHub repository and push this folder's contents to the repository root.
2. Create a free Supabase project. In Project Settings → Database, copy the **Session pooler** PostgreSQL connection URI for external IPv4-friendly access. SQLAlchemy uses the installed Psycopg 3 driver. Encode special characters in the password. Keep the password private.
3. In Render, choose **New → Blueprint**, connect the GitHub repository and let Render read `render.yaml`.
4. Set `DATABASE_URL` to the Supabase URI in the Render environment settings.
5. Optionally set `OPENAI_API_KEY` and `OPENAI_MODEL`. Without an API key, the app still works in demo mode.
6. Deploy. Render builds the React app inside Docker, serves it through FastAPI, and exposes the site at the generated `onrender.com` URL.
7. Open `/api/health` on the deployed URL. Confirm `status: ok`, then use the app.

### Free-tier caveats
- Render free web services sleep after 15 minutes without traffic and may take around a minute to wake up. Their local filesystem is ephemeral, so use Supabase rather than SQLite for deployed data.
- Supabase Free currently includes a 500 MB database and may pause projects after one week of inactivity. Check the provider's current terms before deployment.
- OpenAI API usage is billed separately. ChatGPT subscriptions do not include API credits. Demo mode is available without an API key.
- Free tiers and quotas can change. Keep usage within provider limits.

## Demo walkthrough
1. Open **New decision room**.
2. Enter a synthetic student profile and email.
3. Choose interests and student concerns.
4. Enter a parent/guardian name and select parent concerns.
5. Review and generate the decision brief.
6. Inspect identified topics, source snippets and recommended human handoff.
7. Open **Lead pipeline**, change status and return to the overview metrics.

## Important scope and safety notes
- This is an independent challenge prototype, not an official NIAT product and not connected to NIAT's CRM or admissions systems.
- Use synthetic data for the recruiter demo. Do not enter real student data without appropriate authorization, notice and consent.
- The knowledge snippets are intentionally conservative. Verify current campus-specific fees, scholarship terms, eligibility, university arrangements, facilities and admissions information with NIAT before using them operationally.
- No placement, salary, scholarship or admission guarantee is made.
- There is no authentication or role-based access control in this challenge MVP. Do not expose real lead data publicly. Add authentication, authorization, audit logging, retention controls and security review before any real-world deployment.

## Project structure

```text
backend/
  app/main.py       FastAPI API, SQLAlchemy models and LangGraph/OpenAI workflow
  requirements.txt
  Dockerfile
frontend/
  src/App.jsx       React user experience
  src/style.css
  package.json
render.yaml         Render Blueprint
.env.example        Environment variable template
```
