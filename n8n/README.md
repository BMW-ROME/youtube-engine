# n8n Integration

n8n orchestrates the self-hosted YouTube Engine. It does **not** host AI models —
it calls the engine's dashboard API (FastAPI, default `http://localhost:8000`) to
trigger runs and replenish topic queues, and it receives upload metadata as a
webhook. If you want images from self-hosted Stable Diffusion, point a later
HTTP Request node in n8n at LocalAI / ComfyUI / A1111 on your GPU box.

## Workflows (in this folder)

| File | Purpose | Trigger |
|---|---|---|
| `pipeline-trigger.workflow.json` | Fire one production run per channel on YouTube-ready posting schedule | Cron, 1 node per channel |
| `topic-replenish.workflow.json` | Replenish the QUEUED topic pool for all 7 channels | Cron `0 2 * * *` (ET) |
| `upload-webhook.workflow.json` | Receive `UPLOAD_MODE=pipedream` metadata from the pipeline (never the raw video bytes) | Webhook `POST /webhook/youtube-engine/upload` |

Posting schedule per channel (`America/New_York` timezone, matches the engine's
per-channel `post_time_est`):

| Hour (ET) | Channel |
|---|---|
| 08:00 | finance |
| 10:00 | trending |
| 12:00 | mmo |
| 14:00 | thee3lite |
| 16:00 | tech |
| 18:00 | legal |
| 20:00 | stories |

## Import

1. Start the dashboard: `python scripts/start_engine.py` (or `uvicorn dashboard.app:app --host 0.0.0.0 --port 8000`).
2. Open n8n → **Workflows → Import from File** → select each `*.workflow.json`.
3. Set the n8n instance environment variable `ENGINE_URL` so the HTTP nodes know
   where the engine lives (no trailing slash):
   ```
   ENGINE_URL=http://127.0.0.1:8000
   ```
   If unset, nodes default to `http://localhost:8000`. Docker-compose users: from
   inside the n8n container use `http://dashboard:8000` (the dashboard service name).
4. Activate the workflows (toggle top right). Existing executions show up under **Executions**.

## Wiring the upload webhook

The engine's `pipedream` upload mode POSTs metadata (title, description, tags,
channel, thumbnail path, local video path) to a webhook URL. Point it at n8n in
`.env`:

```
UPLOAD_MODE=pipedream
PIPEDREAM_WEBHOOK_URL=http://<n8n-host>:5678/webhook/youtube-engine/upload
```

`PIPEDREAM_WEBHOOK_URL` is now honored automatically by every caller
(`core/pipeline.py` falls back to it via the `orchestrator`, `dashboard` trigger
endpoint, and `start_engine.py` — no per-caller wiring needed). The raw video is
never sent; only metadata plus the local file path, which an external tool
(drive sync, manual uploader, etc.) can use.

The webhook workflow replies `200 {"ok": true, ...}` so the pipeline's
`requests.post(...).raise_for_status()` succeeds. Attach whatever nodes you need
after **Normalize Payload** (Slack ping, Google Drive copy, YouTube Studio link
out, etc.).

## Notes

- n8n supports environment variables in expressions via `$env.VAR` — the HTTP node
  URLs already use `{{ $env.ENGINE_URL || 'http://localhost:8000' }}`.
- If your n8n version is older than 1.x, the Cron (v2), Webhook (v2) and
  Split-in-Batches (v3) node schemas may need a one-click upgrade after import;
  node names/connections are unchanged.
- `core/pipeline.py` stage 10 (`pipedream_uploader.py`) is non-fatal — a webhook
  outage logs an error and never aborts the pipeline.