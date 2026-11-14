# Deployment guide: Google Cloud Run

This guide prepares the Earth System Trend Detective for hosting as **one container on Google Cloud Run**. FastAPI serves the API at `/api/*` and the built React app at `/app/` from the same origin.

> **Status: not deployed.** Nothing in this guide has been run against a cloud project. The container and its safety checks are verified locally and in CI (see [What is verified](#what-is-verified)). Hosted Earth Engine authentication, proxy-header behaviour on Cloud Run, performance and cost are **not verified** until someone with authorisation deploys and validates them. Deploying, enabling billing, creating service accounts and granting IAM roles are separate, explicitly authorised operations.

## 1. Architecture

```
Browser ──HTTPS──▶ Cloud Run service (1 instance, 1 worker)
                    ├── /app/*      built React app (static files)
                    ├── /api/v2/*   unified API ──▶ NASA POWER (HTTPS)
                    │                           ──▶ Google Earth Engine (keyless ADC)
                    │                           ──▶ OpenStreetMap Nominatim (≤ 1 request/s)
                    └── /docs       interactive API documentation
```

* **One instance, one worker.** The result caches, in-flight request sharing, the per-client rate limiter and the Nominatim throttle all live in process memory. More instances would multiply outbound load and split the caches.
* **No credentials in the image.** The container authenticates to Earth Engine as the Cloud Run service's attached service account through Application Default Credentials (keyless).

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| A Google Cloud project with billing enabled | Cloud Run, Artifact Registry and Cloud Build are billed services; see [section 8](#8-cost-control). Enabling billing is an owner decision. |
| The project registered for Earth Engine | Register it at the Earth Engine Code Editor or Cloud Console and choose the correct use (noncommercial or commercial). Eligibility and pricing for each use are set by Google. Confirm them before launch. |
| `gcloud` CLI, authenticated as someone allowed to deploy | Used only by the person performing the authorised deployment. |
| Docker (optional) | To build and test the image locally (`docker build -t estd .`). |

## 3. Required APIs

Enable these in the target project (`gcloud services enable …`):

| API | Why |
|---|---|
| `run.googleapis.com` | Cloud Run |
| `artifactregistry.googleapis.com` | Stores the container image |
| `cloudbuild.googleapis.com` | Only if images are built in Google Cloud instead of pushed from a workstation or CI |
| `earthengine.googleapis.com` | Earth Engine API calls from the service |

## 4. Runtime identity (keyless, least privilege)

Create a dedicated service account for the service, for example `estd-runtime@PROJECT_ID.iam.gserviceaccount.com`. **Do not create a key for it.** Cloud Run provides its credentials through the metadata server.

Grant only what the backend needs. It reads public Earth Engine catalog data and writes nothing:

| Role (on the project) | Purpose |
|---|---|
| Earth Engine Resource Viewer (`roles/earthengine.viewer`) | Read access to Earth Engine |
| Service Usage Consumer (`roles/serviceusage.serviceUsageConsumer`) | Use the project's enabled Earth Engine API and quota |

Check these roles against Google's current "Earth Engine service accounts" guide before granting them; Google's recommended roles may change. Do not grant Owner, Editor or Earth Engine writer roles. The person deploying also needs `iam.serviceAccounts.actAs` on this service account (for example through Service Account User on that account only).

### Earth Engine configuration for the service

| Variable | Value |
|---|---|
| `EE_PROJECT_ID` | The registered project ID |
| `EE_USE_APPLICATION_DEFAULT_CREDENTIALS` | `true` (keyless) |
| `EE_SERVICE_ACCOUNT_KEY_FILE` | **unset** (setting both is rejected) |

A key file (`EE_SERVICE_ACCOUNT_KEY_FILE`) is supported only for hosts without workload identity. If it is ever used, mount it from a secret manager. Never build it into the image or commit it.

## 5. Secure initial configuration

| Variable | Initial value | Reason |
|---|---|---|
| `EE_PROJECT_ID` | registered project | Enables NDVI, precipitation and soil moisture |
| `EE_USE_APPLICATION_DEFAULT_CREDENTIALS` | `true` | Keyless identity |
| `RATE_LIMIT_PER_MINUTE` | for example `30` | Protects Earth Engine quota. With proxy trust off (below), this limit is shared by all users of the instance. |
| `API_KEYS` | unset for a public demo, or set from Secret Manager for a team-only service | Keys block anonymous visitors, so this is a team decision |
| `TRUST_PROXY_HEADERS` | `false` | See [section 6](#6-client-identification-behind-cloud-run) |
| `CORS_ALLOW_ORIGINS` | leave default or empty | Not needed: the app is single-origin |
| `FRONTEND_DIST_DIR` | set by the image (`/srv/frontend`) | Do not override |
| Scientific policy settings | **leave unset** | Defaults are the agreed project policy; see `backend/.env.example` |

Every setting, with its default, is listed in [`backend/.env.example`](backend/.env.example). Pass values with `--set-env-vars` (non-secret) and `--set-secrets` (API keys). Never put secret values in the repository, in images, or in command history that others can read.

## 6. Client identification behind Cloud Run

`X-Forwarded-For` is client-controlled. The backend uses it only when **all** of these hold:

1. `TRUST_PROXY_HEADERS=true`
2. The direct peer is listed in `TRUSTED_PROXY_IPS`
3. The header has at least `TRUSTED_PROXY_HOPS` entries

It then takes the entry written by the outermost trusted proxy (counted from the right), ignoring anything the client prepended. Malformed or short headers fall back to the direct peer. Misconfigurations are reported in `/api/v2/status` and ignored.

On Cloud Run the direct peer is Google's front end, whose addresses are not a fixed list you can configure. The only option would be `TRUSTED_PROXY_IPS=*` with `TRUSTED_PROXY_HOPS=1`, which assumes Google's front end appends the real client address as the last entry and that no other path reaches the container.

**That assumption is NOT VERIFIED for this service.** Until it is confirmed on the deployed service (for example by comparing the header with a known client address), keep `TRUST_PROXY_HEADERS=false`. The consequence is that IP-based rate limiting cannot tell users apart: it acts as one shared limit for the instance. That is safe against header spoofing, but one heavy user can use up the limit for everyone. If per-user limits matter, use `API_KEYS` (keys are identified individually) or verify the header behaviour first. If a Google external Application Load Balancer is placed in front, the header gains another entry; re-verify and adjust `TRUSTED_PROXY_HOPS`.

## 7. Cloud Run resource settings

| Setting | Recommended | Why |
|---|---|---|
| Max instances | `1` | Per-process caches, rate limiter and Nominatim throttle; also caps cost |
| Min instances | `0` (cheapest; cold starts) or `1` for a scheduled demo window | An idle minimum instance is billed |
| Request timeout | `300` seconds | Soil-moisture and comparison requests can take up to 180 s |
| Concurrency | `20` | Earth Engine work is limited inside the app (2 concurrent operations, 20 s queue); more parallel requests only wait |
| CPU / memory | 1 vCPU / 1 GiB (measure, then adjust) | NumPy, SciPy and the Earth Engine client. Not load-tested. |
| Port | `8080` (Cloud Run sets `PORT`) | The image listens on `$PORT` |
| Startup probe | HTTP `GET /` | `/` does not depend on Earth Engine. `/health` initialises Earth Engine and returns 503 when it is unavailable, so use it as a readiness check during validation, not as a liveness probe. |
| Ingress / authentication | Decide explicitly | `--allow-unauthenticated` makes the service public, which is a separate authorised decision |

Example (for the authorised operator; placeholders in capitals):

```bash
gcloud run deploy estd \
  --image=REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/estd:GIT_SHA \
  --region=REGION \
  --service-account=estd-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --max-instances=1 --min-instances=0 --concurrency=20 --timeout=300 \
  --cpu=1 --memory=1Gi \
  --set-env-vars=EE_PROJECT_ID=PROJECT_ID,EE_USE_APPLICATION_DEFAULT_CREDENTIALS=true,RATE_LIMIT_PER_MINUTE=30
```

Tag every image with the Git commit SHA so each revision can be traced and rolled back.

## 8. Cost control

Do not assume the deployment is free. Check the current pricing and free tiers for Cloud Run, Artifact Registry, Cloud Build, network egress and Earth Engine before launch.

* `--max-instances=1` caps compute spend. `--min-instances=0` avoids paying for idle time.
* Set a billing budget with alerts on the project before going public.
* Keep few image versions in Artifact Registry (storage is billed). Add a cleanup policy.
* Earth Engine charges depend on how the project is registered (noncommercial or commercial). Confirm eligibility and quotas.
* The app's own limits (rate limit, 2 concurrent Earth Engine operations, result caching for one hour) reduce Earth Engine usage but are not a spending cap.

## 9. Rollback

* Each deployment creates a new revision. To roll back, send all traffic to the previous good revision:
  `gcloud run services update-traffic estd --region=REGION --to-revisions=PREVIOUS_REVISION=100`
* Keep the previous image tag in Artifact Registry until the new revision is validated.
* For a configuration-only problem, redeploy the previous revision's settings. Environment changes also create a new revision.
* If credentials are suspected to be misused, remove the service account's roles first, then investigate.

## 10. Post-deployment validation

Run these against the deployed URL before announcing it:

| Check | Expected |
|---|---|
| `GET /api/v2/status` | `auth_mode` is `application_default_credentials`; no warnings about configuration; `client_identification.mode` is `direct_peer_only` unless proxy trust was verified and enabled |
| `GET /health` | `200` with `"earth_engine": "ready"`. After this call, `/api/v2/status` shows `credentials_verified: true`. Only now is hosted Earth Engine authentication verified. |
| `GET /app/` | The app loads and navigation works for every section |
| Live analyses at Yangon (16.8661, 96.1951), 2015–2024 | All six variables return results; compare the temperature slope with a local run |
| Compare Datasets and Relationships | Each returns results or a clear per-dataset outcome |
| Place search | Works; repeated searches are served from the cache |
| Rate limit | Exceeding `RATE_LIMIT_PER_MINUTE` returns 429 with `Retry-After` |
| Logs | No credentials, keys or tokens appear in Cloud Logging |
| Proxy headers (only if you intend to enable trust) | Confirm what `X-Forwarded-For` contains for a known client before setting `TRUST_PROXY_HEADERS=true` |

## 11. Known limitations

* **Single instance.** Caches and limits are per process and are lost on restart or scale-to-zero.
* **Nominatim.** The backend sends at most one request per second, with an identifying User-Agent, and caches results for 24 hours, following the [OSMF Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/). Running several instances would break the one-request-per-second guarantee. That needs a shared limiter or a geocoding service whose terms allow the traffic. Heavy public use may still exceed what the public Nominatim service accepts; coordinate entry is always available.
* **Earth Engine capacity.** Two concurrent Earth Engine operations with a 20-second queue serve a handful of simultaneous users. More users receive a clear 503 "busy" message. Not load-tested.

## What is verified

| Item | Status |
|---|---|
| Image builds from a clean checkout (multi-stage, Node 22 build, Python 3.12 runtime, non-root, one worker, no reload) | VERIFIED locally and in CI |
| Container serves `/app/`, assets, snapshots, `/api/v2/status`, `/api/v2/variables` and `/docs` from one origin | VERIFIED (smoke test) |
| No `.env`, keys, tests, virtual environments or Node tooling in the image | VERIFIED (smoke test) |
| Missing, conflicting or unavailable Earth Engine credentials fail safely (503, no secrets in responses) | VERIFIED (smoke test, mocked unit tests) |
| Spoofed `X-Forwarded-For` cannot bypass rate limiting | VERIFIED (unit and smoke tests) |
| Live NASA POWER analysis through the container | VERIFIED locally (Yangon temperature) |
| Keyless Earth Engine authentication on Cloud Run | **NOT VERIFIED** |
| `X-Forwarded-For` format on Cloud Run | **NOT VERIFIED** |
| Performance, memory sizing and cost on Cloud Run | **NOT VERIFIED** |
