# BUILD LOG

Tracking the rebuild of the YouTube Engine from the recovered architecture spec (README.md).
Original build was done via Perplexity Comet browser assistant + Claude during a Max
subscription period. Implementation files were never pushed to GitHub, so only the README
survived when the subscription lapsed. This log tracks the rebuild, module by module, with
every working piece committed here as it's completed — no work should ever live only inside
a chat session again.

## Status Legend
- [ ] Not started
- [~] In progress
- [x] Working, committed

## Phased Rebuild Plan (added 2026-08-14)

Coaching note: the original checklist below lists modules in pipeline order (Stage 1 -> 10),
but that's documentation order, not build order. We build in phases instead, each one proving
the previous phase's output actually works before adding the next layer on top of it.

- [x] Phase 0: Unblock the Pipeline — SKIPPED. Audit on 2026-08-14 confirmed script_writer.py
  does NOT import config/prompts/ at all — the Retention Architecture system prompt is baked
  directly into the module, and channel context comes from ChannelConfig (niche, display_name,
  image_style_prefix, affiliate_placeholder). The config/prompts/ directory is dead spec, not
  a real blocker. Phase 1 was already unblocked.
- [x] Phase 1: Prove the Loop — scripts/run_once.py written (2026-08-14). Chains content_db ->
  script_writer -> voice_gen for one channel/topic. Supports --dry-run (fake clients, zero API
  cost) and real-client mode. Stops after voice generation (status=MUSIC) since music_mixer.py
  didn't exist yet at that point.
- [x] Phase 2: Visuals — core/music_mixer.py, core/image_gen.py, both tested with fake clients
  (2026-08-15). Music mixer confirmed: mix success, BACKGROUND_MUSIC disabled skip, and
  mixer-always-fails graceful fallback to voice-only audio. Image gen confirmed: all-succeed
  path, content-filter-rejection-then-sanitize-recovery path, and always-fails-falls-back-to
  gradient-placeholder path.
- [x] Phase 3: Assembly — core/thumbnail_text.py (Stage 5, Pillow text overlay), core/video_effects.py
  (Stage 6, KenBurns/Sketch/Animated/AI modes with Replicate fallback), and core/video_assembler.py
  (Stage 7: FFmpeg crossfade assembly + chapter markers). All committed and tested (2026-08-15).
  Chapter marker logic lives inside video_assembler.build_chapter_markers() — the standalone
  core/chapters.py from the original spec was never needed.
- [x] Phase 4: Metadata & Distribution — core/seo_optimizer.py (Stage 8), core/shorts_gen.py
  (Stage 9), core/uploader.py (Stage 10, youtube_api mode), core/pipedream_uploader.py (Stage 10,
  local/skip/pipedream modes). All done and committed 2026-08-15. Phase 4 complete.
- [x] Phase 5: Orchestration — core/pipeline.py (master 10-stage chain), core/freestyle.py (dynamic
  channel builder), core/orchestrator.py (scheduler: run_once + APScheduler per-channel cron
  + run_forever interval fallback), core/trend_engine.py (RSS topic discovery). Committed 2026-08-16/18.
  config/prompts/*.py was dropped (Phase 0 kill — dead spec). The channels/*.py package
  (base_channel + subclasses) was ALSO dropped: channel definitions live in config/channels.py
  (ChannelConfig registry) and freestyle.py builds channels dynamically — a parallel class
  hierarchy would be a second, conflicting source of channel truth. Phase 5 complete.
- [x] Phase 6: Visibility & Ops — dashboard/ (FastAPI app + templates/index.html + static/style.css),
  scripts/ (start_engine.py CLI, run_once.py, setup.py, setup_voice.py, verify_environment.py,
  upload_ready.py, quick_upload.py, validate_e2e.py, test_pipeline_integration.py,
  test_free_real_apis.py), Dockerfile, docker-compose.yml, start_engine.bat. Phase 6 complete.

## Status Summary (2026-08-18)

All 10 pipeline stages, the scheduler layer, the monitoring dashboard, and the full CLI
are committed to main. Remaining roadmap items are tracked per-item below — most surfaced
as deliberate drops (dead spec) rather than unfinished work.

## Rebuild Checklist

### Foundation
- [x] README.md recovered and pushed (2026-08-12)
- [x] .gitignore, requirements.txt, .env.template scaffolded (2026-08-12)
- [x] config/settings.py — global Pydantic settings, singleton `settings` object (2026-08-13)
- [x] config/channels.py — 7 channel definitions, ChannelConfig dataclass, CHANNELS registry (2026-08-13)

### Prompts (config/prompts/)
- [x] N/A — not needed. script_writer.py's RETENTION_SYSTEM_PROMPT + ChannelConfig fields
  cover this entirely. Revisit only if per-channel prompt customization beyond
  niche/display_name/image_style_prefix/affiliate_placeholder is needed later.

### Core Pipeline (core/)
- [x] content_db.py — SQLite tracking, tested end-to-end (create/status transitions/metadata/shorts/retry) (2026-08-13)
- [x] script_writer.py — Stage 1: GPT-4o script generation, tested with fake client (success + failure/retry paths) (2026-08-13)
- [x] voice_gen.py — Stage 2: Edge-TTS / Chatterbox, tested with fake synthesizer + concatenator (2026-08-13, Chatterbox 2026-08-17)
- [x] voice_clone.py — reference-clip validation + resolution for Chatterbox (local, zero-shot cloning), tested (2026-08-13, rewritten 2026-08-17)
- [x] music_mixer.py — Stage 3: FFmpeg background music, tested with fake mixer (mix/skip/fallback paths) (2026-08-15)
- [x] image_gen.py — Stage 4: DALL-E 3 with retry/fallback, tested with fake client (success/sanitize-recovery/placeholder-fallback paths) (2026-08-15)
- [x] thumbnail_text.py — Stage 5: Pillow text overlay (2026-08-15, Phase 3)
- [x] video_effects.py — Stage 6: 4 video modes (2026-08-15, Phase 3)
- [x] video_assembler.py — Stage 7: FFmpeg assembly + chapter markers (2026-08-15, Phase 3)
- [x] chapters.py — Stage 7b: absorbed into video_assembler.build_chapter_markers(); standalone module never needed
- [x] shorts_gen.py — Stage 9 (2026-08-15, Phase 4)
- [x] seo_optimizer.py — Stage 8 (2026-08-15, Phase 4)
- [x] uploader.py — Stage 10 (YouTube Data API upload) (2026-08-15, Phase 4)
- [x] pipedream_uploader.py — Stage 10 (webhook/local/skip) (2026-08-15, Phase 4)
- [x] trend_engine.py — RSS + trending topic discovery, seeds content_db QUEUED rows (2026-08-18, Phase 5)
- [x] pipeline.py — orchestrates all 10 stages (2026-08-16, Phase 5)
- [x] freestyle.py — dynamic channel builder for arbitrary categories (2026-08-16, Phase 5)
- [x] orchestrator.py — run_once + run_forever + APScheduler per-channel cron (2026-08-16/18, Phase 5)
- [x] brand_aware_prompts.py — brand tone/voice + lead-gen CTA wiring for script_writer/seo_optimizer, wraps config/brand_loader.py (2026-08-17)

### Channels (channels/)
- [x] base_channel.py / finance_channel.py / mmo_channel.py / tech_channel.py — DROPPED BY DESIGN.
  Channel definitions live in config/channels.py (ChannelConfig registry); freestyle.py builds
  channels dynamically. A parallel channels/ package would duplicate channel truth. RSS topic
  discovery is implemented in core/trend_engine.py instead.

### Dashboard (dashboard/)
- [x] app.py — FastAPI dashboard with templates/index.html + static/style.css (2026-08-15 as Flask,
  rewritten to FastAPI 2026-08-18 per original spec). Serves on settings.dashboard_port (default 8000).
- [x] templates/index.html (2026-08-18)
- [x] static/style.css (2026-08-18)

### Scripts (scripts/)
- [x] run_once.py — manual single-video tool, Phase 1 script+voice loop (2026-08-14)
- [x] start_engine.py — main CLI (menu + args + Freestyle) (2026-08-16, Phase 6)
- [x] setup.py — first-time wizard (.env bootstrap + diagnostics + OAuth flow) (2026-08-18, Phase 6)
- [x] setup_voice.py — Chatterbox voice cloning wizard (2026-08-16, Phase 6)
- [x] upload_ready.py — batch upload of ready/ videos using .meta.json sidecars (2026-08-18, Phase 6)
- [x] quick_upload.py — quick single-video upload (2026-08-18, Phase 6)
- [x] verify_environment.py — pre-flight check for binaries/packages/env vars (2026-08-16, Phase 6)
- [x] validate_e2e.py — real $0 end-to-end validation, httpx-level OpenAI transport patch (2026-08-17, Phase 6)
- [x] test_pipeline_integration.py — pipeline integration test (2026-08-16)
- [x] test_free_real_apis.py — $0 real-API tests via local Ollama (2026-08-16)

### Infra
- [x] Dockerfile (2026-08-18, Phase 6)
- [x] docker-compose.yml (2026-08-18, Phase 6)
- [x] start_engine.bat (2026-08-16, Phase 6)

## Notes

- 2026-08-13: settings.py and channels.py written. Added `pydantic-settings` to requirements.txt
  (was missing from the original spec's dependency list but required for BaseSettings).
  channels.py pulls video_mode/videos_per_day from settings + os.getenv per-channel overrides,
  matching the .env.template variable names exactly. YouTube category_id values are best-guess
  placeholders — verify against actual YouTube category taxonomy before going live.

- 2026-08-13: content_db.py written and smoke-tested in an isolated sandbox (fresh SQLite file,
  full lifecycle: create -> status transitions -> metadata patch -> shorts -> youtube info ->
  failed/retry path). All operations confirmed working, not just syntax-checked.

- 2026-08-13: script_writer.py written and tested with fake ChatClient implementations (no real
  OpenAI key/cost used). Confirmed success path (parse, validate, persist) and failure/retry path
  (3 attempts, FAILED status, retry_count increment). Retention Architecture baked into the
  system prompt per the original spec.

- 2026-08-13: voice_gen.py written and tested with fake Synthesizer + AudioConcatenator
  implementations (no real edge-tts network call, no ffmpeg binary, no ElevenLabs account
  needed). Confirmed per-scene synthesis, concatenation, failure/retry path, and the
  Chatterbox-configured-but-unavailable -> Edge-TTS fallback rule.

- 2026-08-14: Coaching audit — built a phased execution plan (Phase 0-6) instead of working
  straight down the checklist. Phase 0 audit found config/prompts/ is not actually imported by
  script_writer.py, so that entire checklist section was marked N/A rather than built for no
  reason. scripts/run_once.py written to prove content_db -> script_writer -> voice_gen work
  together end-to-end (supports --dry-run for zero-cost testing). This is the first script that
  actually chains multiple pipeline stages together rather than testing one module in isolation.

- 2026-08-15: Phase 2 (Visuals) complete. music_mixer.py mixes background music under narration
  via ffmpeg's amix filter at low volume (0.12), with a niche-to-music-folder mapping covering
  all 7 channels. Gracefully skips if BACKGROUND_MUSIC is off or no track exists for the niche,
  and gracefully degrades to voice-only audio if ffmpeg mixing fails after retries — music is an
  enhancement, never a pipeline blocker. image_gen.py generates one DALL-E 3 image per scene
  using channel.image_style_prefix for visual consistency, with the exact resilience chain from
  the README: sanitize regex strips common filter-trigger words -> safety suffix appended on the
  final attempt -> gradient PNG placeholder (via Pillow, with a stub fallback if Pillow isn't
  installed) if all 3 attempts are exhausted.

- 2026-08-16: Phase 3 (Assembly) + Phase 4 (Metadata & Distribution) complete, then pipeline.py
  landed with the master 10-stage orchestration. The integration test (test_pipeline_integration.py)
  caught 6 broken stage imports and a missing content_db.init_db()/get_next_topic — all fixed.
  This is why every module above is committed; the "Rebuild Rule" below protected us here.

- 2026-08-16: Phase 5 (Orchestration) mostly complete — core/pipeline.py, core/freestyle.py,
  core/orchestrator.py, plus scripts/start_engine.py (Phase 6 CLI) and start_engine.bat. A real
  sys.path bug was fixed in scripts/run_once.py and scripts/setup_voice.py (ModuleNotFoundError:
  No module named 'core' when run as documented — Python only auto-adds the script's own
  directory to sys.path, not its parent).

- 2026-08-17: MIGRATION — ElevenLabs -> Chatterbox for voice cloning (Thee3lite Speaks channel).
  Chatterbox is Resemble AI's local, open-source (MIT), zero-shot voice cloning model: no API
  key, no per-character cost, runs on local GPU/CPU — matching this project's local-first infra
  preference. voice_gen.py: ChatterboxSynthesizer replaces ElevenLabsSynthesizer. voice_clone.py:
  rewritten from 'upload samples to remote API' to 'validate + resolve a local reference audio
  file path'. config/settings.py: elevenlabs_* fields replaced with chatterbox_*. config/channels.py:
  thee3lite's voice_engine=chatterbox. requirements.txt: elevenlabs swapped for chatterbox-tts.
  All Edge-TTS fallback paths preserved and tested (6 scenarios).

- 2026-08-17: Brand integration — core/brand_aware_prompts.py (wraps config/brand_loader.py,
  a marketing-ops repo fetcher) wired into script_writer.py + seo_optimizer.py per
  BRAND_INTEGRATION_SNIPPET.md. Brand tone/voice goes into the script system prompt; SEO prompt
  gets brand tone + a lead-gen CTA appended to description and pinned comment (skipped when the
  marketing-ops lead_capture.yaml CTA is still an unconfigured placeholder). Never blocks
  generation if brand data is unavailable.

- 2026-08-17: scripts/validate_e2e.py — real $0 end-to-end validation: runs the ACTUAL repo's
  core.pipeline.run_pipeline() with only the OpenAI network transport faked (httpx-level
  monkeypatch on the real openai SDK). img fix: the fake DALL-E image must be a real, structurally
  valid PNG (Pillow-generated), or thumbnail_text.py correctly rejects it — which made the stage
  genuinely exercised for the first time. Verified: a real openai client through the patched
  transport returns bytes that Image.open().convert('RGBA') opens successfully.

- 2026-08-18: Doc reconciliation pass — BUILD_LOG.md and README.md synchronized with the
  committed code state (Phase 5/6 checked off, tree corrected, voice/dashboard/APScheduler
  wording fixed). Tracked real drift fixes: .env.template voice section rewritten for Chatterbox,
  flask omitted from requirements (dashboard is FastAPI), DASHBOARD_PORT canonicalized to 8000,
  config/.brand_cache/ + .vs/ gitignored, verify_environment.py updated for Chatterbox.

- 2026-08-18: Phase 5/6 completion work — core/trend_engine.py (feedparser RSS topic discovery,
  dedupes against content_db, seeds QUEUED rows), APScheduler per-channel cron in orchestrator.py
  (matches README Schedule: per-channel post times, 2 AM topic replenishment, 30-min failed
  retry, 11 PM report; run_forever kept as interval fallback), FastAPI dashboard rewrite with
  /api/channels, /api/videos, /api/logs, /api/trigger, Dockerfile + docker-compose.yml (no torch
  in base image), scripts/setup.py, scripts/upload_ready.py, scripts/quick_upload.py. The
  channels/ package was dropped by design (redundant with config/channels.py + freestyle.py).

- 2026-08-18: AI Backend made configurable — the pipeline previously hardcoded the real OpenAI
  endpoints and never connected to a local LLM (a dummy OPENAI_API_KEY only satisfied settings
  validation, it didn't route anywhere). Now: OPENAI_BASE_URL (chat) + LLM_MODEL point
  script_writer.py + seo_optimizer.py at a local Ollama (/v1/chat/completions); IMAGE_BASE_URL
  + IMAGE_MODEL point image_gen.py at a LocalAI-style /v1/images/generations (same payload
  shape as DALL-E, zero adapter code). Both clients build OpenAI(base_url=...) from settings;
  default None keeps the real OpenAI behavior. Chat model names must match `ollama list`;
  image model names must exist in the image server's registry. Clarification logged here: the
  DALL-E stage needs a REAL image backend (LocalAI chosen) — Chatterbox is the VOICE stage
  (TTS, replaced ElevenLabs) and Ollama only reads images (multimodal), it cannot generate them.
  Also fixed: run_pipeline now defaults the SEO stage to the shared OpenAIChatClient() instead
  of silently skipping stage 8 when no client dict is injected (stage 10 upload is gated on
  seo_result, so uploads could never fire in real runs); the --model flag in
  test_free_real_apis.py now actually applies (sets LLM_MODEL before stage import);
  verify_environment.py gained non-fatal backend reachability probes.

- 2026-08-18: FULLY LOCAL end-to-end proof — a run_pipeline() with ZERO fakes or transport
  patching: script + SEO from local Ollama (LLM_MODEL=qwen2.5-coder:3B, the model proven to
  satisfy the strict JSON schema), 10 scene images from scripts/local_image_stub.py (a ~1KB
  OpenAI-shaped /v1/images/generations dev server returning real Pillow PNGs — stands in for
  LocalAI/ComfyUI until a GPU box with real diffusion models is available; IMAGE_BASE_URL is
  the only thing that changes), real Edge-TTS voice, real ffmpeg kenburns effects + assembly,
  real Pillow thumbnail overlay, upload=local sidecar. Result: success=True, failed=[], a
  6 MB MP4 (output/videos/14.mp4) with complete SEO metadata incl. the marketing-ops brand CTA.
  This validates the whole local-first architecture without spending a cent.

- 2026-08-18: n8n integration pieces — core/pipeline.py stage 10 now falls back to
  settings.pipedream_webhook_url when no explicit webhook_url is injected
  (config.get("webhook_url") or settings.pipedream_webhook_url), so UPLOAD_MODE=pipedream
  works from EVERY caller (orchestrator, dashboard /api/trigger, start_engine) by just
  setting PIPEDREAM_WEBHOOK_URL in .env — previously the webhook POST target would have
  been None outside scripts that passed a webhook_url explicitly. Verified end-to-end
  with a local HTTP receiver (pipedream_sent, status 200, full metadata payload).
  Added n8n/ with three importable workflows: pipeline-trigger.workflow.json (per-channel
  cron -> POST /api/trigger/{channel}, EST schedule, $env.ENGINE_URL with localhost
  default), topic-replenish.workflow.json (2 AM cron -> loop -> POST
  /api/topics/{channel}/generate), upload-webhook.workflow.json (POST
  /webhook/youtube-engine/upload -> normalize -> Respond 200). All three validated:
  valid JSON, no dangling connections. n8n/README.md covers import + ENGINE_URL +
  UPLOAD_MODE=pipedream wiring + the n8n-is-an-orchestrator-not-a-model-host note
  (self-hosted SD is called by n8n, not hosted by it).

- 2026-08-18: Dependency incompatibility fixes — two real breaks surfaced when running on
  system Python (openai 1.44.0 + httpx 0.28.1):
  (1) httpx 0.28.0 removed the `proxies` constructor arg; openai 1.x (<1.59) still passes
  `proxies` into its internal httpx client -> `TypeError: Client.__init__() got an unexpected
  keyword argument 'proxies'` on any OpenAI(...) construction. Fixed by pinning
  `openai[aiohttp]>=3,<4` + `httpx>=0.28,<1` in requirements.txt (openai 3.x uses httpx2 and
  is httpx-0.28-compatible).
  (2) openai 3.x eagerly imports `aiohttp.SocketTimeoutError` at import time
  (openai/_vendor/httpx_aiohttp) but only declares aiohttp as the `[aiohttp]` extra
  (>=3.14.1); plain `openai` crashed on aiohttp<3.14 (system had 3.9.1). Fixed by declaring
  `openai[aiohttp]` so pip installs aiohttp>=3.14.x. Verified on system Python after upgrade:
  client constructs, live Ollama chat round-trip returns the strict-JSON script/SEO shape,
  and an image round-trip via scripts/local_image_stub.py returns a valid PNG.
  Also moved chatterbox-tts to the requirements.txt OPTIONAL block — it was uncommented
  (required) but pulls torch-2.6 + gradio/diffusers/librosa/audio stack (~multi-GB), which is
  why the venv never had it and the README treats it as optional (Edge-TTS is default voice).

- 2026-08-19: Video Library dashboard + hybrid transcript RAG.
  Content-card dashboard: new GET /videos page (dashboard/templates/cards.html) — dark-themed
  card grid of produced videos (thumbnail via a resolution chain from output/images, channel/
  status/video_mode badges, created/published dates, 'Watch media' + YouTube links), plus a
  traversal-safe GET /media route that serves local thumbnails/videos exclusively from
  settings.content_path (FileResponse, containment guard). No new dependencies.
  Transcript RAG (core/rag_index.py + scripts/index_rag.py + dashboard /search page and
  /api/search + /api/ask): transcripts are extracted from content_db metadata_json["script"]
  (hook + per-scene narration + outro), chunked, and stored in output/rag.db (SQLite FTS5
  virtual table + optional Ollama embeddings via settings.embeddings_base_url/api/embeddings,
  pure-Python cosine). Embedding failure degrades to FTS-only keyword search (verified against
  a dead endpoint); empty stores return empty results instead of crashing. ask() chains the
  proven strict-JSON chat client (script_writer.OpenAIChatClient, qwen2.5-coder) and returns
  {answer, sources[]}. SEO metadata is now also persisted into metadata_json["seo"] by
  pipeline.py (mirrors the script persist at script_writer.py) so cards show real titles/
  descriptions and RAG can search them later. Orchestrator.run_once auto-indexes each produced
  video behind settings.rag_enabled (core/orchestrator._index_result). Live-verified against
  the existing local content.db: 10 videos indexed (12/10/5 chunks each) with live vectors,
  hybrid search on 'index funds' ranks video 14 scenes semantically, and ask() returned a
  coherent strict-JSON answer with sources.

- 2026-08-19: Optimum-quality final encode. ffprobe audit of output/videos/14.mp4 found the
  headline spec (1080p H.264 + AAC + faststart) was met but the real output was NOT optimum:
  multi-clip xfade assembly was emitting yuv444p, and audio was AAC 24 kHz mono ~72 kbps
  (edge-tts native, re-encoded untouched). video_assembler.py now emits broadcast-safe
  yuv420p + settings-driven CRF 16 / preset slow + audio upsampled/mixed to 48 kHz stereo at
  160 kbps on BOTH encode branches (single-clip and crossfade) via a shared _encode_args().
  video_effects.py kenburns/sketch now use scale=1920:1080:force_original_aspect_ratio=
  increase,crop=1920:1080 so any backend aspect is center-cropped, never stretched. New
  settings: VIDEO_CRF (16), VIDEO_PRESET (slow), VIDEO_AUDIO_BITRATE (160k),
  VIDEO_AUDIO_SAMPLERATE (48000), VIDEO_AUDIO_CHANNELS (2). Verified by ffprobe on a rebuilt
  video: yuv420p, aac 48000 Hz stereo >=160k, 1920x1080 30fps.

- 2026-08-19: Post-audit correctness sweep (part 1 - config/docs). Fixed dashboard
  /api/search reporting "vectors active" on FTS-only results (vector_available was
  `any(vector) or bool(hits)`; rag_index already marks each hit with the real global
  vector flag, so the `or bool(hits)` made every non-empty FTS result lie). Added the
  missing APSCHEDULER_ENABLED=true line to .env.template (orchestrator.py:48 reads it,
  the template only referenced it in a comment). Added PyYAML to requirements.txt
  (core/brand_aware_prompts.py imports yaml unguarded, so the brand/CTA feature was
  silently dead on default installs) and guarded that import for minimal runs.
  .gitignore now covers assets/music/*.wav (music_mixer globs mp3 + wav). docker-compose
  no longer file-binds the gitignored run_history.jsonl (Docker created a DIRECTORY at
  that path, silently dropping history); it now directory-binds ./data:/app/data with
  RUN_HISTORY_PATH=/app/data/run_history.jsonl. README project tree + single-channel
  quick-start refreshed (adds index_rag.py, local_image_stub.py, cards.html, search.html,
  app.js; run_once.py marked legacy, validate_e2e.py promoted).

- 2026-08-19: Post-audit correctness sweep (part 2 - $0 pipeline test). The old
  "every dependency faked, costs nothing" docstring in test_pipeline_integration.py
  was only true for SEO: the script (OpenAI/Ollama), voice (Edge-TTS), and images
  (DALL-E/LocalAI) stages still called their real backends, so the test burned real
  API calls. Now ALL stages are injected with fakes (FakeScriptClient,
  FakeSynthesizer, FakeConcatenator, FakeMixer, FakeImageClient,
  FakePlaceholderGenerator) via a shared _fake_clients() helper; the fake PNG/WAV
  bytes are real formats so the real ffmpeg effect + assembly stages still decode
  them. UPLOAD_MODE is forced to "local" so nothing leaves the machine (ffmpeg is
  the only remaining real binary dependency). Also hardened test 3 to use a
  dedicated "__retry_test__" channel so pre-existing FAILED rows in the real
  content.db can't break it. Full 10-stage happy path + SEO-outage survival path +
  retry-queue test all pass with zero network calls.

## Rebuild Rule

Every session: commit and push working code before closing, even if incomplete.
A broken-but-committed module beats a perfect-but-lost one.


## Stage 10: Pipeline Orchestration (completed)

- [x] `core/pipeline.py` — Master orchestrator chaining all 10 stages (script, voice, music, images, thumbnail, effects, assembly, seo, shorts, upload). Each stage wrapped in try/except; failures are logged and stored in `PipelineResult.failed_stages` instead of crashing the run. `script` and `assembly` are REQUIRED stages — their failure aborts the pipeline; all others degrade gracefully and are skipped. Lazy imports per stage so a broken/missing module doesn't block the rest of the pipeline from loading. Committed to main.

All 10 stages of the pipeline now have code committed to `core/`. Next: build `orchestrator.py`/scheduler layer for automated recurring runs, plus dashboard/monitoring and end-to-end testing.

## Stage 11: Scheduler / Orchestrator (completed)

- [x] `core/orchestrator.py` — Scheduler layer on top of `core/pipeline.py`. Supports `run_once()` for single manual runs, APScheduler per-channel cron matching the README Schedule (post times, 2 AM topic replenishment, 30-min failed retry, 11 PM daily report), and `run_forever()` for a plain interval loop fallback (default `PIPELINE_INTERVAL_SECONDS`). Pulls next topic from `core.content_db` when available, falling back to a static topic rotation if the DB is unavailable so the scheduler never stalls. Persists a JSON-lines run history (`run_history.jsonl`) after every run for later review. Orchestrator-level try/except wraps every run in addition to pipeline.py's own per-stage resilience, so one bad run never kills the scheduler process. Committed to main.

Next (done): dashboard/monitoring view for run history + failed stages, and end-to-end testing of the full chain (script -> upload).

## Stage 12: Monitoring Dashboard (completed)

- [x] `dashboard/app.py` — FastAPI dashboard that reads the JSON-lines run history produced by `core/orchestrator.py` (`run_history.jsonl`) and renders a dark-themed table of recent runs plus summary cards (total/success/failure counts). Exposes the REST API from the README spec: `/health`, `/api/channels`, `/api/videos`, `/api/videos/{id}`, `/api/trigger/{channel}`, `/api/topics/{channel}/generate`, `/api/logs`, with 15s auto-refresh. Missing history file or malformed lines are handled gracefully (empty state / line skipped + logged) rather than crashing. Run locally with `python dashboard/app.py` on `settings.dashboard_port` (default 8000, configurable via `DASHBOARD_PORT`). Committed to main.

Next: run the full chain against real APIs with credentials in place (OPENAI_API_KEY + a configured channel), verify `youtube_api` upload mode end-to-end (the least exercised code path — needs real OAuth), and deploy the orchestrator via the Docker profile for scheduled production runs.