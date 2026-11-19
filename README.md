# Video to 3D Studio

A full-stack **video → 3D animation converter** with three modes, a browser studio, a CLI, an optional desktop app, and a subscription layer where the owner never pays.

## Personal use (no payments)

Everything is already configured in `.env`: billing is off, personal mode is on, and one owner account has full access.

```bash
./scripts/personal.sh
```

Open **http://localhost:8000** and sign in with the credentials printed by the script (default `owner@example.com` / `password123`). To change them, edit `OWNER_EMAILS` and `OWNER_PASSWORD` in `.env` and re-run the script — it will update the account. The Plans page becomes a "Personal mode" notice instead of subscription cards.

## Fast & universal input

- **Sparse parallel sampling** — only ~64 frames are decoded via a keyframe-only ffmpeg pass (or parallel seeks for huge files). Processing time is bounded by frame count, **not file size**.
- **URL import** — paste any public URL: direct file, S3/R2/GCS signed link, Google Drive/Dropbox/OneDrive share, or YouTube/TikTok/etc. via `yt-dlp`. SSRF-protected, streamed to disk with progress, optional custom headers.
- Content-adaptive: rotation, VFR, HDR, unusual pixel formats, vertical shorts, sub-second and multi-minute clips.
- Result caching by content fingerprint — repeat jobs are instant.
- Live verification: URL import of a public MP4 completed in **8.5 s**; local sparse extraction of a 60 s 720p clip takes **0.6 s**.

## Quick start (other modes)

```bash
./scripts/dev.sh                 # local: API + built UI at http://localhost:8000
# or
cp .env.example .env && docker compose up --build   # API + Redis worker
```

Register with an address in `OWNER_EMAILS` (default `owner@example.com`) to get the unlimited owner account. In **Studio**, use *Generate sample* to try the pipeline without uploading anything.

## Modes and real outputs

| Mode | Pipeline | Artifacts |
|---|---|---|
| **2.5D Parallax** | Shot detection → depth → phase-correlation camera path → depth-warped render | WebM, MP4, GLB (textured depth mesh), keyframe, depth map, camera path JSON |
| **Avatar Mocap** | MediaPipe pose (or labeled procedural fallback) | Pose JSON, BVH animation |
| **3D Scene** | Shot-aware depth fusion | PLY point cloud, GLB point cloud, depth preview |

Depth is a CPU heuristic by default. On GPU hosts, set `DEPTH_BACKEND=depth_anything` with `torch`/`transformers` installed for real monocular depth. Scene mode produces a point cloud rather than Gaussian splats — the interface is designed for a splatting swap, but that path is not included in this build.

## Plans

| | Free | Pro | Studio | Owner |
|---|---|---|---|---|
| Max video length | **10s** | **1 min** | **2 min** | unlimited |
| Max resolution | 720p | 1080p | 4K | unlimited |
| Modes | Parallax | All | All | All |
| Watermark | Yes | No | No | No |
| Exports | WebM | WebM/MP4/GLB/PLY/BVH/JSON | same + API/batch | everything |
| Batch / API | — | — | Yes | Yes |

Length is validated with `ffprobe` server-side at job creation. Owner accounts bypass all gates and are never charged. Set `BILLING_ENABLED=false` to make a self-hosted instance free for everyone.

## Billing

Stripe Checkout subscriptions with signature-verified webhooks as the source of truth. `POST /api/billing/dev-plan` allows local plan switching when billing is disabled.

## Public API & CLI

```bash
# Create an API key in Plans & Billing (Studio/Owner), then:
curl -H "X-API-Key: v2d_..." -F file=@clip.mp4 -F mode=parallax \
  http://localhost:8000/api/v1/jobs
```

CLI:

```bash
pip install httpx
python cli/v2d.py login --email owner@example.com --password password123
python cli/v2d.py convert clip.mp4 --mode parallax --out ./results
python cli/v2d.py demo --mode scene
python cli/v2d.py jobs
```

Desktop (requires Node + Python deps): `cd desktop && npm install && npm start`.

Android APK (signed, personal-use WebView):

```bash
./android/build.sh
# output: android/V2DStudio.apk
```

On first launch the app asks for the server address (e.g. `http://192.168.1.5:8000` for your PC on the same Wi‑Fi, or your public Render URL). The **Settings** button at the top-right lets you change it later. Verified with `apksigner` and parsed with `androguard`.

## Advertisements

Set `VITE_ADSENSE_ID=ca-pub-...` (plus slot IDs) in `frontend/.env.local` before building to render real AdSense units. Without an AdSense ID the app renders self-hosted sponsor slots (`VITE_AD_LINK`, `VITE_AD_TEXT`). See `frontend/.env.example`.

## Hosting / permanent link

`Dockerfile` builds the UI and bundles it with the API into one container. `deploy/render.yaml` is a one-click Render blueprint; set `CORS_ORIGINS` and `PUBLIC_BASE_URL` to your final domain, then rebuild the APK with that URL. For any other container host, `docker build -t v2d-studio . && docker run -p 8000:8000 -v v2d-data:/data v2d-studio`.

## Architecture

- **Backend:** FastAPI, SQLModel, PBKDF2 auth + HS256 JWT, centralized entitlement checks.
- **Queue:** in-process thread pool by default; set `REDIS_URL` for a durable priority queue with a separate worker (`python -m worker`) and Redis pub/sub progress bridging.
- **Storage:** local filesystem by default; `STORAGE_BACKEND=s3` uploads artifacts to any S3-compatible store and fetches them on demand.
- **Database:** SQLite by default. Schema changes are managed with Alembic (`alembic upgrade head`, run automatically in the Docker app service).
- **Frontend:** React + TypeScript + Vite + react-three-fiber; shader-based depth viewer, PLY point cloud viewer, animated pose viewer.
- **Security:** configurable CORS, rate limiting, request IDs/structured logs, production secret validation, safe error responses, email verification and password reset (outbox at `backend/data/outbox.log`).

## Tests

```bash
cd backend && python -m pytest -q
```

15 tests cover auth, verification/reset, plan limits and owner bypass, all three modes, real export validity, API keys, processing utilities, and S3 storage round-trips (via moto). The Redis queue, worker, and progress bridge were also verified end-to-end against a live Redis instance.

## Upgrades not included

- Real Gaussian splatting / mesh reconstruction for the 3D scene mode.
- FBX export (use the GLB or BVH output and convert in Blender).
- Production email delivery — `notify.py` writes to a local outbox; wire an SMTP/email provider for hosted use.
- A hosted deployment with real Stripe keys and production secrets (supply via `.env`).

Interactive API docs: http://localhost:8000/docs
