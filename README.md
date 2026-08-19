# YouTube Engine

**Autonomous YouTube Content Engine** by **Thee3liteSolutions** — generates scripts,
voice narration, background music, scene images, video effects, thumbnail text overlays,
SEO metadata, YouTube Shorts, and uploads across 7 built-in channels plus an unlimited
**Freestyle** mode for any category you type.

## Channels

| # | Display Name | Codename | Niche | CPM Range | Voice Engine | Video Mode | Post Time (EST) |
|---|-------------|----------|-------|-----------|-------------|-----------|-----------------|
| 1 | Wealth Decoded | `finance` | Finance | $15–22 | Edge-TTS | configurable | 8 AM |
| 2 | Side Hustle Lab | `mmo` | Make Money Online | $15–20 | Edge-TTS | configurable | 12 PM |
| 3 | Future Proof Tech | `tech` | Technology | $12–18 | Edge-TTS | configurable | 4 PM |
| 4 | Trending Pulse | `trending` | Viral/News | — | Edge-TTS | configurable | 10 AM |
| 5 | Thee3lite Speaks | `thee3lite` | Personal Brand | — | Chatterbox | animated | 2 PM |
| 6 | Justice Files | `legal` | Legal/Crime | $12–18 | Edge-TTS | configurable | 6 PM |
| 7 | Dark Truth Tales | `stories` | Dark Stories | $20–25 | Edge-TTS | configurable | 8 PM |
| — | **Freestyle** | `freestyle-{slug}` | Any | — | Edge-TTS | user choice | 12 PM |

## Features

- 7 Pre-Built Channels — Finance, MMO, Tech, Trending, Legal, Stories, and a personal brand channel
- Freestyle Mode — type any category in the CMD and generate a video instantly
- Dual Voice Engines — free Edge-TTS for all channels, local Chatterbox voice cloning for Thee3lite
- Background Music Mixer — ambient music auto-mixed under narration at configurable volume
- 4 Video Effect Modes — Ken Burns (free), Animated ($), AI Video ($$), Sketch (free)
- Thumbnail Text Overlay — bold keyword text burned onto thumbnails via Pillow for higher CTR
- DALL-E 3 Image Generation — with content-filter resilience (auto-sanitize + retry + fallback)
- SEO Optimization — AI-generated titles, descriptions, tags, and hashtags
- YouTube Shorts Generator — auto-generates 3 Shorts per long-form video for subscriber funnel growth
- Retention-Optimized Scripts — algorithm-tuned structure with open loops, hooks, and curiosity gaps
- Monetization Features — affiliate placeholders, pinned comment drafts, end screen suggestions, chapter markers
- 4 Upload Modes — `local`, `skip`, `pipedream`, or direct `youtube_api`
- Resilient Architecture — every optional dependency (Chatterbox, Google, Replicate, httpx) is wrapped in try/except so the system runs even if packages are missing
- APScheduler — automated daily production with per-channel cron (post-time schedule) and retry with backoff
- SQLite Tracking — every video tracked from QUEUED → PUBLISHED (or FAILED)
- Web Dashboard — real-time status at `:8000`
- n8n Integration — importable workflows in `n8n/` for cron-triggered runs, topic replenish, and a webhook receiver for `UPLOAD_MODE=pipedream`
- Docker Ready — one-command deployment with `docker-compose`
- Windows First — `start_engine.bat` launcher with interactive menu

## Prerequisites

| Requirement | Version | Notes |
|------------|---------|-------|
| Python | 3.11+ | Tested on 3.13.7 |
| FFmpeg | 5+ | Must be on PATH |
| Pillow | 10+ | Thumbnail text overlay |
| Docker | 20+ | Optional |
| OpenAI API | — | GPT-4o + DALL-E 3 |

Optional (system runs without these): Chatterbox (local voice cloning), Replicate (animated/AI video), Google API libs (direct YouTube upload).

## Quick Start (Windows)

```batch
cd youtube-engine
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.template .env
:: Edit .env with your OPENAI_API_KEY (required) + optional keys
start_engine.bat
```

Interactive menu options: Run ALL Channels (autopilot), Run ONE Channel, Dashboard Only, Setup & Diagnostics, Freestyle (any category).

### Freestyle Mode
```batch
python scripts/start_engine.py --category "true crime" --topic "Unsolved Mysteries of 2026" --video-mode kenburns
```

### Single Channel Test
```batch
python scripts/run_once.py --channel finance
python scripts/run_once.py --channel tech --topic "GPT-5 Changes Everything"
```

## Quick Start (Docker)
```bash
cd youtube-engine
cp .env.template .env
docker-compose up --build -d
# Dashboard at http://localhost:8000
```

## Project Structure

```
youtube-engine/
├── start_engine.bat
├── docker-compose.yml
├── Dockerfile
├── .env.template
├── requirements.txt
├── README.md
├── BUILD_LOG.md
├── BRAND_INTEGRATION_SNIPPET.md
│
├── config/
│   ├── settings.py              # Global settings (Pydantic)
│   ├── channels.py              # 7 channel definitions (ChannelConfig registry)
│   ├── brand_loader.py          # Shared brand identity fetcher (marketing-ops repo)
│   └── .env.brand.template      # Brand sync env vars (GITHUB_TOKEN, etc.)
│
├── core/
│   ├── pipeline.py              # Master orchestrator — 10-stage content pipeline (channel-agnostic)
│   ├── orchestrator.py          # Scheduler: APScheduler per-channel cron + run_forever loop
│   ├── freestyle.py             # Dynamic channel builder for any category
│   ├── trend_engine.py          # RSS + trending topic discovery
│   ├── brand_aware_prompts.py   # Brand tone/voice + lead-gen CTA wiring for script/seo
│   ├── script_writer.py         # GPT-4o script generation (retention architecture)
│   ├── voice_gen.py             # Edge-TTS + Chatterbox (resilient imports)
│   ├── voice_clone.py           # Chatterbox reference-clip validation/resolution
│   ├── music_mixer.py           # FFmpeg background music mixer
│   ├── image_gen.py             # DALL-E 3 images (sanitize + retry + fallback)
│   ├── thumbnail_text.py        # Pillow text overlay for thumbnails
│   ├── video_effects.py         # KenBurns / Animated / AI Video / Sketch
│   ├── video_assembler.py       # FFmpeg final assembly (1080p H.264) + chapter markers
│   ├── shorts_gen.py            # YouTube Shorts generator (3x per video)
│   ├── seo_optimizer.py         # AI-powered SEO metadata
│   ├── uploader.py              # YouTube API upload (resilient google imports)
│   ├── pipedream_uploader.py    # Pipedream webhook + local-save uploader
│   └── content_db.py            # SQLite tracking database
│
├── dashboard/
│   ├── app.py                   # FastAPI dashboard + REST API
│   ├── templates/index.html
│   └── static/style.css
│
└── scripts/
    ├── start_engine.py          # Main CLI (menu + args + Freestyle)
    ├── setup.py                 # First-time setup wizard (env bootstrap + OAuth)
    ├── setup_voice.py           # Chatterbox voice clone wizard
    ├── run_once.py              # Manual single-video tool
    ├── verify_environment.py    # Pre-flight check (ffmpeg, deps, env vars)
    ├── validate_e2e.py          # $0 end-to-end pipeline validation (patched transport)
    ├── upload_ready.py          # Batch upload ready/ folder
    ├── quick_upload.py          # Quick single-video upload
    ├── test_pipeline_integration.py
    └── test_free_real_apis.py
```

## Pipeline Detail

10 stages tracked in SQLite: QUEUED → SCRIPTING → VOICING → MUSIC → IMAGING → ASSEMBLING → OPTIMIZING → UPLOADING → PUBLISHED (or FAILED)

1. **Script** (GPT-4o) — structured JSON: hook, scenes[], outro, seo_keywords, chapter_timestamps, affiliate_slots. Retention architecture baked into every script.
2. **Voice** (Edge-TTS/ElevenLabs) — free Edge-TTS default, falls back automatically if ElevenLabs unavailable.
3. **Background Music** (FFmpeg) — ambient music auto-selected by niche, mixed via `amix` filter.
4. **Images** (DALL-E 3) — parallel generation, content-filter resilience: sanitize → safety suffix → 2-attempt retry → placeholder.
5. **Thumbnail Text Overlay** (Pillow) — bold keyword text burned onto thumbnail, skipped gracefully if Pillow missing.
6. **Video Effects** — kenburns (free), sketch (free), animated ($ via Replicate), ai_video ($$ via Replicate).
7. **Assembly** (FFmpeg) — crossfade transitions, 1080p H.264 + AAC, faststart flag.
   - 7b. Chapter Markers — auto-generated from scene boundaries.
   - 7c. Affiliate Links — channel-scoped placeholders injected into description.
   - 7d. Pinned Comment — GPT-4o drafted engagement comment.
8. **SEO** (GPT-4o) — title ≤60 chars, description with timestamps/keywords, tags ≤500 chars, hashtags, end screen suggestions.
9. **YouTube Shorts** — 3 auto-generated vertical shorts per video from highest-retention moments (~$0.20/video extra).
10. **Upload** — `local`, `skip`, `pipedream`, or `youtube_api` (OAuth2 resumable).

## Retention Architecture

- **Hook (0–3s)**: bold claim or unanswered question to stop the scroll.
- **Opening (0–60s)**: open loop + pattern interrupt every 60–90s.
- **Body (60s–80%)**: curiosity gaps, micro-value delivery every ~90s.
- **Outro (final 20%)**: payoff resolves the open loop; CTA placed after payoff.

## Monetization Features

- Affiliate link placeholders per channel (e.g. `[AFFILIATE_FINANCE_1]`)
- Pinned comment drafts (GPT-4o, <200 chars, seeds replies)
- Thumbnail text overlay for CTR
- YouTube Shorts funnel back to long-form
- End screen topic suggestions (`end_screen_topics`)
- Auto-generated chapter markers

## Configuration

Copy `.env.template` to `.env`. Only `OPENAI_API_KEY` is required — everything else degrades gracefully if unset. See `.env.template` for the full variable list (voice cloning, video modes, shorts/music toggles, upload settings, per-channel video counts).

### AI Backend: real OpenAI vs. fully local

The chat stages (`script_writer.py`, `seo_optimizer.py`) and the image stage (`image_gen.py`) talk to OpenAI-compatible endpoints. By default they point at real OpenAI (`GPT-4o` + `DALL-E 3`); set the base URLs below to run 100% locally, $0:

| Setting | Default | Local example | Stage |
|---------|---------|---------------|-------|
| `OPENAI_BASE_URL` | blank (= OpenAI) | `http://localhost:11434/v1` (Ollama) | script + SEO chat |
| `LLM_MODEL` | `gpt-4o` | `qwen2.5-coder:3B` (must be in `ollama list`; proven for strict JSON) | chat model sent |
| `IMAGE_BASE_URL` | blank (= DALL-E) | `http://localhost:8080/v1` (LocalAI) | scene images |
| `IMAGE_MODEL` | `dall-e-3` | `sdxl-turbo` (LocalAI registry) | image model sent |

Local servers ignore the Authorization header, so a dummy `OPENAI_API_KEY` is fine. `scripts/verify_environment.py` prints a reachability probe for both backends. Note: Chatterbox is the **voice** stage (TTS) — it replaces ElevenLabs, not DALL-E. Local images come from `IMAGE_BASE_URL`, not from Ollama (Ollama only *reads* images; it can't generate them).

## Resilience Architecture

Runs with only `OPENAI_API_KEY` set:

| Component | Missing? | Behavior |
|-----------|----------|----------|
| ElevenLabs | Not installed / no key | Falls back to Edge-TTS |
| google-auth | Not installed | Loads fine; errors only if `UPLOAD_MODE=youtube_api` |
| Replicate | Not installed / no key | Falls back to kenburns mode |
| httpx | Import fails | Caught with try/except |
| Pillow | Not installed | Thumbnail overlay skipped |
| DALL-E filter rejection | Prompt flagged | Auto-sanitize → retry → gradient placeholder |
| Background music file missing | File not found | Music stage silently skipped |
| Shorts generation fails | API error | Long-form video still completes and uploads |

## Schedule

| Channel | Post Time (EST) |
|---------|-----------|
| Wealth Decoded | 8:00 AM |
| Trending Pulse | 10:00 AM |
| Side Hustle Lab | 12:00 PM |
| Thee3lite Speaks | 2:00 PM |
| Future Proof Tech | 4:00 PM |
| Justice Files | 6:00 PM |
| Dark Truth Tales | 8:00 PM |

Plus: Topic Replenishment (2 AM daily), Failed Retry (every 30 min), Daily Report (11 PM).

## Voice Clone Setup (Chatterbox)
```batch
python scripts/setup_voice.py --clip /path/to/your_voice_sample.wav
```
Chatterbox is Resemble AI's local, open-source (MIT) zero-shot voice clone — no API key, no
per-character cost. It clones directly from a single reference audio clip at generation time;
runs on your own GPU/CPU via the `chatterbox-tts` package. The wizard validates your clip, runs
one test synthesis so you can listen before wiring in, and prints the exact `.env` line
(`CHATTERBOX_VOICE_SAMPLE_PATH` global, or the per-channel `..._THEE3LITE` override).

## YouTube API Setup
Only needed for `UPLOAD_MODE=youtube_api`:
1. `pip install google-auth google-auth-oauthlib google-api-python-client`
2. Create Google Cloud Project, enable YouTube Data API v3
3. Create OAuth2 Desktop app credentials
4. Run `python scripts/setup.py` for the OAuth flow

## Dashboard

`http://localhost:8000` (configurable via `DASHBOARD_PORT`) — dark-themed summary cards
(total/success/failure runs) + recent-runs table, auto-refresh every 15s.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /api/channels | All channel stats (from content_db) |
| GET | /api/videos | List videos (filterable) |
| GET | /api/videos/{id} | Single video detail |
| POST | /api/trigger/{channel} | Trigger video production |
| POST | /api/topics/{channel}/generate | Generate new topics |
| GET | /api/logs | Recent log lines |

Run with `python dashboard/app.py`.

## Estimated Costs

Per video: GPT-4o ~$0.05–0.10, DALL-E 3 ~$0.40–0.55, Edge-TTS free, Chatterbox free (local), Shorts ~$0.20.

Total (free modes, no Shorts): ~$0.50–0.65/video → 7 channels × 1/day ≈ $105–137/month.
With Shorts across all 7 channels: add ~$42/month.

**$0 with local backends**: point `OPENAI_BASE_URL` (Ollama) + `IMAGE_BASE_URL` (LocalAI) at your own machine and the LLM/image costs drop to electricity alone.

## Troubleshooting

- **OPENAI_API_KEY not set**: ensure `.env` exists, UTF-8 no BOM.
- **ModuleNotFoundError: google**: only needed for `youtube_api` upload mode.
- **DALL-E content policy violation**: auto-sanitized and retried; falls back to placeholder after 2 attempts. See `core/image_gen.py` `_FILTER_TRIGGERS`.
- **Chatterbox not working**: run `python scripts/setup_voice.py --clip <your clip>`. It validates the reference clip and runs one test synthesis before wiring in.
- **FFmpeg errors**: verify `ffmpeg -version` works and is on PATH.
- **Background music not mixing**: check `BACKGROUND_MUSIC=true` and `assets/music/` files exist.
- **Shorts not generating**: check `GENERATE_SHORTS=true` and look for `[shorts_gen]` log entries.
- **Thumbnail text not appearing**: verify Pillow installed; check font path in `core/thumbnail_text.py`.
- **Rate limit from OpenAI**: reduce `max_concurrent` in `image_gen.py`, add delay between videos.
- **Upload fails with 403**: verify YouTube API enabled, re-run OAuth flow, check channel ID.

## Adding a New Channel

1. Define in `config/channels.py` (ChannelConfig with codename, display_name, channel_id, category_id, voice_id, video_mode, image_style_prefix)
2. Add `.env` vars: `{NAME}_CHANNEL_ID`, `{NAME}_VIDEO_MODE`, `VIDEOS_PER_DAY_{NAME}`
3. (Optional) Point topic discovery at an RSS feed in `core/trend_engine.py` for this channel's niche.

Or use Freestyle mode to skip all of this — `core/freestyle.py` builds a channel dynamically for any category string.

## License

MIT — Use it, modify it, ship it. No attribution required.

---

*Recovered 2026-08-12 from architecture documentation after original implementation (built via Perplexity Comet browser assistant + Claude during a Max subscription session) was lost when the implementation files were never pushed to version control. This README is the founding spec for the ground-up rebuild — see BUILD_LOG.md for progress tracking.*
