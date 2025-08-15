# Opus-like MVP (Backend + UI)

- FastAPI API + Redis worker to ingest YouTube, transcribe with Whisper, rank moments, and render clips
- Static file serving at `/static/*` from a shared `/data` volume
- Minimal React UI to create jobs, view moments, and poll rendered clip links

## Run backend
```bash
cp .env.example .env
docker compose up --build
```

## Run frontend
```bash
cd ui
cp .env.example .env
npm install
npm run dev
```
Open http://localhost:5173

### Using the app
1. Paste a YouTube URL in the UI and click **Queue Ingest**.
2. After ANALYZE completes, click **Refresh moments** to see candidates.
3. Select moments and **Render selected**.
4. The **Rendered clips** panel polls and shows links when files are ready.

- Clips are saved to `/data/clips` and served at `http://localhost:8000/static/clips/<clip_id>.mp4`.


### Cloud upload
Set `STORAGE_BACKEND=s3` (or `gcs`) in `.env`, and fill in bucket details.

- **S3**: provide `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `S3_BUCKET`, `S3_PREFIX`.
- **GCS**: provide `GCS_BUCKET`, `GCS_PREFIX`, and either mount `GOOGLE_APPLICATION_CREDENTIALS` or paste JSON into `GCS_SERVICE_ACCOUNT_JSON`.

Rendered files are uploaded as `clips/<clip_id>.mp4`. The worker stores `output_path` as `s3://...` or `gs://...`. The UI has a **Get fresh link** button which calls `GET /clips/{clip_id}/signed_url` to mint a temporary download URL.


## Scheduler (auto-ingest & daily auto-render)
- A `scheduler` service polls channel RSS feeds and enqueues new videos for ingest.
- Subscribe via API:
  ```bash
  curl -X POST http://localhost:8000/channels/subscribe -H 'x-api-key: dev-key' -H 'Content-Type: application/json' -d '{"channel_id":"UC_x5XG1OV2P6uZZ5FSM9Ttw","auto_render_top_k":3,"daily_post_time":"08:00","keywords":["tip","secret"]}'
  ```
- Force a sync now:
  ```bash
  curl -X POST http://localhost:8000/channels/sync_all -H 'x-api-key: dev-key'
  ```

## Auto B‑roll overlays
- Put some short MP4s in `/app/assets/broll` (mount a volume or bake into the image) or set `BROLL_DIR` in `.env`.
- When enabled (in AUTO_RENDER or wired later for manual renders), the worker detects pauses and overlays small PiP B‑roll for ~1–2s while keeping the original audio.


## YouTube uploader
- Set `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` in `.env`. The refresh token must have the `youtube.upload` scope.
- In the UI (Rendered clips), click **Publish to YouTube** to queue an upload job. The worker uses a resumable `videos.insert` upload and stores the resulting `videoId` in the clip's `metrics.youtube`.


## Auto-thumbnails
- After a clip renders, the worker extracts a mid-frame, applies the same crop, and writes a JPEG to `/data/thumbnails/<clip_id>.jpg` (served at `/static/thumbnails/...`). 
- You can also call `POST /clips/{clip_id}/thumbnail` with `{ title?, aspect_ratio? }` to regenerate with an overlaid title.
- The UI shows the thumbnail and a **Download** button.

## Basic analytics (YouTube)
- Nightly at 03:00 UTC the scheduler enqueues `ANALYTICS_REFRESH`. The worker fetches `videos.list?part=statistics` for uploaded clips and appends a daily point to `clip.metrics.youtube_timeseries` (views/likes/comments).
- The UI shows the latest **views** value next to each clip.


## Auto-title suggestions
- `POST /videos/{video_id}/titles` returns up to ~12 suggestions from the transcript (LLM optional via `OPENAI_API_KEY`; set `use_llm=true` in the body).

## Thumbnail A/B testing
- `POST /clips/{clip_id}/thumbnails/ab` with `{ title_a, title_b }` generates two variants and stores them at `/static/thumbnails/<id>_A.jpg` and `_B.jpg`.
- `POST /clips/{clip_id}/thumbnails/ab/start` to toggle A/B testing. The scheduler flips variants daily at 06:00 UTC by calling `THUMB_SET_YT`, which sets the active thumbnail on YouTube.
- Analytics already captures daily stats; you can compare per-day view deltas to pick a winner.


## A/B winner auto-pick
- Daily at **07:00 UTC**, the scheduler evaluates running A/B tests over the last `AB_EVAL_DAYS` (default 4) using daily **view deltas** from analytics.
- It stops the test and sets the winning variant on YouTube automatically.

## Thumbnail style packs
- `POST /clips/{clip_id}/thumbnails/styles` generates a 4-variant pack (S1..S4) from a single title (emoji/no-emoji, caps, etc.).
- `POST /clips/{clip_id}/thumbnails/set` picks a variant as the clip’s thumbnail and (optionally) sets it on YouTube immediately.
- The UI shows a small grid for quick selection.


## Leaderboard & Autopost
- **GET `/analytics/leaderboard`** — returns top clips ranked by 24h view delta (from `metrics.youtube_timeseries`).
- **Autoposts** (`/autoposts`):
  - `POST /autoposts` with `{ platform: 'webhook'|'x', endpoint?, template, daily_time, enabled }`
  - `POST /autoposts/{id}/run_now` triggers immediately.
- Scheduler runs autoposts at the configured `daily_time`. The worker builds a caption from your template and dispatches:
  - **webhook**: POSTs JSON `{ clip_id, title, caption, url, thumbnail_url, youtube }` to your URL.
  - **x**: posts the caption via Tweepy (text + link; video upload not included).
- Env for X posting:
  ```
  TWITTER_API_KEY=
  TWITTER_API_SECRET=
  TWITTER_ACCESS_TOKEN=
  TWITTER_ACCESS_SECRET=
  ```


## CTR proxy & impressions
- The nightly analytics job now also fetches **impressions** per video for **yesterday** via the YouTube Analytics API (`youtubeAnalytics.reports.query`).
- Leaderboard shows a **CTR proxy** ~= `views_24h ÷ impressions_24h`.
- Make sure your OAuth **refresh token** includes the `yt-analytics.readonly` scope (in addition to `youtube.upload`).


## Daily Top 5 email digest
- Create an autopost with platform `email` and the recipients in `endpoint` (comma-separated). Scheduler sends a **Top 5 Clips (24h)** HTML email at your chosen time.
- Configure provider via env:
  - **SendGrid**: `SENDGRID_API_KEY` (+ optional `EMAIL_FROM`)
  - **Mailgun**: `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `EMAIL_FROM`

## TikTok auto-upload
- New endpoint: `POST /clips/{clip_id}/publish/tiktok` with `{ title }` queues an upload via TikTok Open API (`initialize` → `PUT` upload → `publish`).
- Set `TIKTOK_ACCESS_TOKEN` (must be obtained via OAuth with the proper scopes).
- We store `clip.metrics.tiktok = { videoId }` after a successful publish.


## Admin: failed jobs + retry
- New DB table `job_log` captures job type, payload, status, error, attempts.
- API:
  - `GET /admin/jobs?status=error&limit=100` → list recent failures
  - `POST /admin/jobs/{id}/retry` → re-enqueue original payload
  - `DELETE /admin/jobs/{id}` → delete the log entry
- UI section **Admin: Failed jobs** shows errors and provides **Retry/Delete** buttons.

## Export to Docker image
- Build and export a ready-to-load image tarball:
  ```bash
  ./scripts/export_image.sh opuslike v1 opuslike_v1.tar
  docker load -i opuslike_v1.tar
  ```
- Bundle just the compose + env template:
  ```bash
  ./scripts/export_compose.sh opuslike_compose_bundle.tar.gz
  ```


## Health & Metrics
- **GET `/health`** — JSON status for DB, Redis, and storage (MEDIA_ROOT), plus uptime and queue length.
- **GET `/metrics`** — Prometheus text exposition with:
  - `app_db_ok`, `app_redis_ok`, `app_jobs_queue_length`, `app_videos_total`, `app_clips_total`, `app_uptime_seconds`.
- UI shows a **Health** panel and links to `/metrics` for scraping.


## Alerts (Slack / Webhook)
- Configure via **UI → Alerts** or API under `/alerts`.
- **Triggers**:
  - Health status change (`ok` ↔ `degraded`).
  - Redis jobs queue length above configurable threshold (debounced).
- **Scheduler** checks every minute and sends to all enabled channels:
  - **Slack**: posts plain text to the webhook.
  - **Webhook**: POSTs JSON `{ type: 'health_change'|'queue_spike', message, snapshot }`.


## Slack slash-commands
- Set `SLACK_SIGNING_SECRET` in `.env`, then point a Slack Slash Command to `POST https://<your-api>/slack/commands` with command `/opus`.
- Supported:
  - `/opus status` — health + queue length
  - `/opus top` — top 3 by 24h view delta with links
  - `/opus retry <job_id>` — re-enqueue a failed job (uses Admin retry)

## Mobile approvals
- Visit **`/mobile.html`** (served from `ui/public/`) on your phone. Configure `API_URL` and `API_KEY` in local storage if needed:
  - Open the page → browser console → `localStorage.API_URL='https://your-api'` and `localStorage.API_KEY='...'`.
- The page lists pending clips (not yet uploaded), shows suggestions, existing thumbnail variants, and a one-tap **Approve** (saves title, applies thumbnail style if selected, and queues YouTube upload).


## Slack interactive approvals
- Enable **Interactivity** for your Slack app, point to `POST /slack/actions`.
- Use `/opus pending` to list up to 3 pending clips with buttons:
  - **Approve (Unlisted/Public)** — instantly approves with the default suggested title and queues a YouTube upload.
- We verify `SLACK_SIGNING_SECRET` on both `/slack/commands` and `/slack/actions`.

## Magic-link auth for mobile approvals
- Create a token:
  ```bash
  curl -X POST $API/auth/magic -H 'Content-Type: application/json' -d '{"purpose":"approvals","ttl_minutes":1440}'
  ```
  It returns `{ token, expires_at }`.
- Open `/mobile.html?token=<TOKEN>&api=<API_URL>` on your phone. The page stores the token as `localStorage.MAGIC_TOKEN` and uses it instead of `x-api-key` for:
  - `GET /approvals/pending`
  - `POST /approvals/{clip_id}/approve`
