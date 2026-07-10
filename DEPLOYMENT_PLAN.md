# Implementation Plan — Deploy Agentic Trading Praxis to Google Cloud with a Public Decision-Logic Dashboard

Prepared for: LancerLunatic / `agentic-trading-praxis`
Repo state reviewed at commit: `eeb5538` (2026-07-10 06:31 EDT)
Audience for the live dashboard: hiring managers + college Praxis committee
Goal: Host the Python LangGraph app on GCP and expose a **publicly viewable** view of the multi-agent decision logic (data provider → analyst → evaluator → risk manager → executor).

---

## 0. The single most important thing to know first

**LangGraph Studio is NOT a public dashboard.** Studio always requires a LangSmith login + API key and connects to a *running, authenticated* LangGraph Server. You cannot hand a committee member a URL that opens Studio with zero login. ([LangChain self-host docs](https://docs.langchain.com/langsmith/deploy-standalone-server), [LangGraph local-test docs](https://github.com/langchain-ai/langgraph/blob/main/docs/docs/cloud/deployment/test_locally.md))

Also, the self-hosted LangGraph Server (even the free "Lite" tier, ~1M node executions/yr) still requires a LangSmith API key at startup **and** its own Redis + Postgres. ([Self-Hosted Lite](https://langchain-ai.github.io/langgraphjs/concepts/self_hosted/), [free tier discussion](https://github.com/langchain-ai/langgraph/discussions/1604))

**Recommended architecture:** Deploy the app to **Cloud Run** and build a **small custom public dashboard** (FastAPI + static page) that (a) renders your graph topology as a diagram and (b) replays saved decision traces/telemetry. This gives reviewers a real, no-login window into the decision matrix — exactly what a hiring/praxis audience needs — without exposing Studio, live keys, or a live-trading endpoint. Studio stays as your *private* dev tool.

---

## ✅ What changed since the last review (good progress)

- The current `.env` **no longer contains live keys** — both `GEMINI_API_KEY` and `LANGSMITH_API_KEY` are now empty/placeholder. Nice.

## ⚠️ Phase 0 — Security remediation (STILL REQUIRED before deploy)

1. **The old keys are still recoverable from git history.** They live in commits `2d30c7d ("refining")` and `4dad1f6 ("my first finance agent for praxis")`. Anyone can run `git show 4dad1f6:.env` and read them. Clearing the working-tree file does **not** remove them from history.
   - **Rotate both keys now** in Google AI Studio (Gemini) and LangSmith. Treat them as compromised.
   - **Purge `.env` from history** and stop tracking it going forward:
     ```bash
     pip install git-filter-repo
     git filter-repo --path .env --invert-paths --force
     git rm --cached .env 2>/dev/null; echo ".env" >> .gitignore
     git commit -am "chore: stop tracking .env"
     git push --force --all
     ```
2. **Committed junk is still tracked** — remove it:
   ```bash
   git rm -r --cached .langgraph_api __pycache__ agents/__pycache__ core/__pycache__
   printf '\n.langgraph_api/\n__pycache__/\n*.pyc\n' >> .gitignore
   git commit -am "chore: untrack build/runtime artifacts"
   ```
3. In production, load all secrets from **GCP Secret Manager** — never bake keys into the image or repo.

---

## Phase 1 — Make the repo build-ready (local)

Confirmed third-party runtime deps from the code: `langgraph`, `langchain-core`, `langchain-google-genai`, `langsmith`, `alpaca-trade-api`, `pydantic`, `numpy`, `pandas`, `requests`, `python-dotenv`. Test-only: `pytest`.

1. **Add a pinned `requirements.txt`** (+ optional `requirements-dev.txt` for pytest).
2. **Pin a Python base image.** Committed `.pyc` files are CPython 3.14; unless you truly need 3.14, target a stable `python:3.12-slim` (broadest wheel support for numpy/pandas/pydantic) and confirm the app runs on it.
3. **Add a `Dockerfile`** (slim base → copy `requirements.txt` → `pip install` → copy app → run entrypoint).
4. **Add `.dockerignore`** (`.git`, `.agents`, `.langgraph_api`, `__pycache__`, `tests`, `*.md`).
5. **Verify locally in Docker** before touching GCP: `docker build` + `docker run`, hit `/health`.

---

## Phase 2 — GCP project + foundations

1. Create/select a GCP project; enable billing.
2. Enable APIs: `run`, `artifactregistry`, `cloudbuild`, `secretmanager`. ([Cloud Run + LangGraph guide](https://smarttechnotes.com/langgraph-cloudrun/))
3. Create an **Artifact Registry** Docker repo (e.g. `us-central1`).
4. Create a least-privilege **service account** for Cloud Run (Secret Manager accessor, Artifact Registry reader).
5. Store secrets in **Secret Manager**: `GEMINI_API_KEY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, (optional) `LANGSMITH_API_KEY`.

---

## Phase 3 — Choose deployment track

### ✅ Track A (RECOMMENDED): Cloud Run app + custom public dashboard
Best fit for "public review of decision logic," lowest cost, no LangSmith dependency for viewers, no live-trading risk.

- Wrap the graph in a small **FastAPI** app:
  - `GET /health` → readiness probe.
  - `GET /` → public dashboard (static HTML/JS): graph diagram + gallery of saved decision runs.
  - `GET /graph` → graph topology (Mermaid/JSON) generated from `main.py`'s compiled `app` via `app.get_graph().draw_mermaid()`.
  - `GET /runs`, `GET /runs/{id}` → **pre-recorded, sanitized** trace/telemetry JSON from `core/telemetry.py` output + `simulation.py` results. No live keys, no live orders.
- Run in **mock/simulation mode** in the cloud — the code already falls back to the Black-Scholes mock + mock executor when Alpaca creds are absent, so nothing real trades from a public URL.
- Deploy: `gcloud run deploy --source . --region us-central1 --allow-unauthenticated` → public HTTPS URL. ([Medium Cloud Run guide](https://medium.com/@chirazchahbeni/deploying-streaming-ai-agents-with-langgraph-fastapi-and-google-cloud-run-5e32232ef1fb))
- Dashboard content that impresses a technical committee: the Reflector Loop, the confidence gate (retry to analyst when confidence < 0.7, max 3 reflections — per `main.py`), Greeks/margin risk rules, and a replay of a real decision with evaluator critiques.

### Track B: Full self-hosted LangGraph Server on Cloud Run (private Studio access)
Use only if you specifically want to demo *Studio itself*.
- Requires **Redis + Postgres** (Memorystore + Cloud SQL, or containers) and a **LangSmith API key** at startup. ([Self-hosted deploy](https://langchain-ai.github.io/langgraph/how-tos/deploy-self-hosted/))
- `pip install langgraph-cli` → `langgraph build -t <image>` → push to Artifact Registry → deploy to Cloud Run with a **VPC connector** to reach the DBs. ([GCP deploy walkthrough](https://www.youtube.com/watch?v=CcVCUUVyRPU)) Your `langgraph.json` already points at `./main.py:app`, so it's build-ready for this path.
- Reviewers would still need a LangSmith login to open Studio → **does not satisfy the "public, no-login" requirement.** Keep this private; pair it with Track A for the public part.

**Recommendation: Track A for the public dashboard; optionally keep Track B private for your own use.**

---

## Phase 4 — Public dashboard build (Track A detail)

1. Export graph topology from the compiled `app` → Mermaid.
2. Curate 2–3 **sanitized sample runs** from `simulation.py` + telemetry logs (strip any account values you don't want public).
3. Build a single page (server-rendered or light JS): architecture diagram, node-by-node explanation, interactive run replay.
4. Add a "How it works" section mapped 1:1 to `PROJECT.md` milestones.
5. (Optional) Custom domain via Cloud Run domain mapping.

---

## Phase 5 — CI/CD + ops

1. **Cloud Build trigger** on `main` → build image → auto-deploy to Cloud Run. (Now that the git connector is on, this can wire straight to your GitHub repo.)
2. Cloud Run min instances = 0 (scale-to-zero, cheap); set sane memory/CPU.
3. Logging/monitoring via Cloud Logging; keep telemetry sampling from `core/telemetry.py`.
4. Add a "Live demo" link in the `README` for recruiters.

---

## Phase 6 — Verification & handoff

1. Confirm the public URL loads with **no login** in an incognito window.
2. Confirm **no secrets** are reachable and **no live orders** can be triggered from the public URL.
3. Share the URL + repo (now key-free in history) with the committee.

---

## Cost expectation (qualitative)
Cloud Run scale-to-zero + Artifact Registry + Secret Manager for a low-traffic demo is very inexpensive; Track B adds Postgres/Redis cost. No LangGraph enterprise license is needed to self-host (core is MIT). ([self-host cost thread](https://community.latenode.com/t/understanding-langgraph-server-deployment-costs-and-self-hosting-options/33992))

---

## What Perplexity Computer can do FOR you vs. what needs you

| Task | Who | Notes |
|---|---|---|
| Generate pinned `requirements.txt` (+ dev) | ✅ Computer | From your actual imports |
| Write the `Dockerfile` + `.dockerignore` | ✅ Computer | Cloud Run-ready |
| Write the FastAPI wrapper + `/health`, `/graph`, `/runs` | ✅ Computer | Track A |
| Build the public dashboard (HTML/JS + Mermaid + run replay) | ✅ Computer | Can build & preview it |
| Export graph topology as Mermaid/JSON | ✅ Computer | From your `main.py` |
| Write `cloudbuild.yaml` + full `gcloud` runbook | ✅ Computer | Copy-paste scripts |
| Provide exact `git filter-repo` / `.gitignore` purge commands | ✅ Computer | You run them (needs your push) |
| **Rotate the leaked API keys** | ❌ You | Google AI Studio + LangSmith |
| **Create GCP project, enable billing, run `gcloud`** | ❌ You | Requires your Google login & billing |
| **Enter real secrets into Secret Manager** | ❌ You | I provide commands; you enter values |
| Decide Track A vs. B (or both) | 🤝 Together | Recommend A public, B private optional |

Sources: [LangChain self-host standalone server](https://docs.langchain.com/langsmith/deploy-standalone-server) · [Self-Hosted Lite concepts](https://langchain-ai.github.io/langgraphjs/concepts/self_hosted/) · [LangGraph on Cloud Run (Smart Tech Notes)](https://smarttechnotes.com/langgraph-cloudrun/) · [LangGraph + FastAPI + Cloud Run (Medium)](https://medium.com/@chirazchahbeni/deploying-streaming-ai-agents-with-langgraph-fastapi-and-google-cloud-run-5e32232ef1fb) · [Deploy LangGraph on GCP (YouTube)](https://www.youtube.com/watch?v=CcVCUUVyRPU)
