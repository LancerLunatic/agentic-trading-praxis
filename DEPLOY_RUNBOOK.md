# Cloud Run Deploy Runbook — Track A (Public Read-Only Dashboard)

Copy-paste friendly. Run these on your local machine (PowerShell or bash) with the
`gcloud` CLI installed and authenticated. Replace the values in **Step 0** once and
the rest flow through.

> This deploys the **public dashboard only**, in simulation/mock mode. No live keys
> and no brokerage connection are required for the public demo.

---

## Step 0 — Set your variables

**PowerShell (Windows):**
```powershell
$PROJECT_ID = "your-gcp-project-id"     # e.g. praxis-trading-2026
$REGION     = "us-central1"
$REPO       = "praxis"
$SERVICE    = "praxis-dashboard"
```

**bash (macOS/Linux/WSL):**
```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export REPO="praxis"
export SERVICE="praxis-dashboard"
```

---

## Step 1 — Authenticate & select project
```bash
gcloud auth login
gcloud config set project $PROJECT_ID
```
> Billing must be enabled on the project (do this once in the Console:
> Billing → Link a billing account). This is the one step that needs the web Console.

---

## Step 2 — Enable required APIs
```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

---

## Step 3 — Create the Artifact Registry repo
```bash
gcloud artifacts repositories create $REPO \
  --repository-format=docker \
  --location=$REGION \
  --description="Agentic Trading Praxis images"
```

---

## Step 4 — First deploy, straight from source (simplest path)

This one command builds the image with Cloud Build and deploys to Cloud Run.
`gcloud` reads the `Dockerfile` in the repo root automatically.

**PowerShell (use backticks for line continuation):**
```powershell
gcloud run deploy $SERVICE `
  --source . `
  --region $REGION `
  --allow-unauthenticated `
  --port 8080 `
  --memory 512Mi `
  --cpu 1 `
  --min-instances 0 `
  --max-instances 3
```

**bash:**
```bash
gcloud run deploy $SERVICE \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3
```

When it finishes, gcloud prints a **Service URL** like
`https://praxis-dashboard-xxxxxxxxxx-uc.a.run.app`. Open it in an **incognito
window** — it should load with **no login**. That's the link for recruiters/committee.

---

## Step 5 — Verify
```bash
# health check
curl https://<YOUR-SERVICE-URL>/health
# expect: {"status":"ok","mode":"public-readonly-demo"}
```
Also click through the dashboard: the graph should render and both decision replays
should open.

---

## Step 6 — (Optional) CI/CD: auto-deploy on every push to main

The repo includes `cloudbuild.yaml`. Wire a trigger so each push to `main`
rebuilds and redeploys.

1. Grant the Cloud Build service account permission to deploy to Cloud Run:
```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

2. Connect the GitHub repo and create the trigger (this opens a browser once to
   authorize the Cloud Build GitHub App):
```bash
gcloud builds triggers create github \
  --name="praxis-main-deploy" \
  --repo-name="agentic-trading-praxis" \
  --repo-owner="LancerLunatic" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --substitutions=_REGION=$REGION,_REPO=$REPO,_SERVICE=$SERVICE
```

After this, `git push` to `main` → automatic build + deploy.

---

## Step 7 — (Later) If you add live trading behind auth

The public dashboard never needs secrets. If you later run the *actual* agent
(not the demo) on GCP, store keys in Secret Manager and mount them — never bake
into the image:
```bash
echo -n "YOUR_ROTATED_GEMINI_KEY" | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "YOUR_ALPACA_KEY"        | gcloud secrets create ALPACA_API_KEY --data-file=-
echo -n "YOUR_ALPACA_SECRET"     | gcloud secrets create ALPACA_SECRET_KEY --data-file=-

# grant the runtime service account access, then on deploy add:
#   --set-secrets=GEMINI_API_KEY=GEMINI_API_KEY:latest,ALPACA_API_KEY=ALPACA_API_KEY:latest,ALPACA_SECRET_KEY=ALPACA_SECRET_KEY:latest
```
And keep that service **authenticated** (omit `--allow-unauthenticated`).

---

## Common gotchas
- **"PERMISSION_DENIED: billing"** → enable billing on the project (Console).
- **Build fails on numpy/pandas wheels** → the Dockerfile pins `python:3.12-slim`, which has prebuilt wheels; don't switch the base to 3.14.
- **Port errors** → Cloud Run injects `$PORT`; the Dockerfile already honors it. Keep `--port 8080`.
- **Cold starts** → with `--min-instances 0` the first hit after idle takes a few seconds. For a demo that's fine; set `--min-instances 1` if you want it always warm (small cost).
