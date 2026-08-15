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
  doesn't exist yet.
- [x] Phase 2: Visuals — core/music_mixer.py, core/image_gen.py, both tested with fake clients
  (2026-08-15). Music mixer confirmed: mix success, BACKGROUND_MUSIC disabled skip, and
  mixer-always-fails graceful fallback to voice-only audio. Image gen confirmed: all-succeed
  path, content-filter-rejection-then-sanitize-recovery path, and always-fails-falls-back-to-
  - [x] Phase 3: Assembly — core/thumbnail_text.py (Stage 5), core/video_effects.py (Stage 6, Replicate fallback tested), and core/video_assembler.py (Stage 7: FFmpeg crossfade assembly + - [x] Phase 4: Metadata & Distribution — core/seo_optimizer.py, core/shorts_gen.py, core/uploader.py, core/pipedream_uploader.py all DONE and committed 2026-08-15. seo_optimizer.py (Stage 8): GPT-4o SEO metadata generation — title/description/tags/hashtags/pinned comment/end-screen topics, same ChatClient + retry-then-raise pattern as script_writer.py. shorts_gen.py (Stage 9): extracts SHORTS_PER_VIDEO vertical 9:16 clips from heuristic retention-moment start times (hook/middle/closer spread), FFmpeg crop+scale, one-failure-doesn't-block-others resilience. uploader.py (Stage 10, youtube_api mode): resumable Data API v3 upload, lazy google-* imports so missing deps/creds degrade to a logged None instead of crashing, defaults to privacy=private. pipedream_uploader.py (Stage 10, local/skip/pipedream modes): local writes a .meta.json sidecar for manual upload, skip is a no-op, pipedream POSTs metadata + local path to a webhook (never the raw video bytes). Phase 4 complete.
- [ ] Phase 5: Orchestration — core/pipeline.py, core/freestyle.py, core/orchestrator.py, core/trend_engine.py, remaining config/prompts/*.py (if still wanted), channels/*.py
- [ ] Phase 6: Visibility & Ops — dashboard/, scripts/*, Dockerfile, docker-compose.yml, start_engine.bat

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
- [x] voice_gen.py — Stage 2: Edge-TTS / ElevenLabs, tested with fake synthesizer + concatenator (2026-08-13)
- [x] voice_clone.py — ElevenLabs voice cloning setup, tested with fake client (9 test cases) (2026-08-13)
- [x] music_mixer.py — Stage 3: FFmpeg background music, tested with fake mixer (mix/skip/fallback paths) (2026-08-15)
- [x] image_gen.py — Stage 4: DALL-E 3 with retry/fallback, tested with fake client (success/sanitize-recovery/placeholder-fallback paths) (2026-08-15)
- [ ] thumbnail_text.py — Stage 5: Pillow overlay (next up — Phase 3)
- [ ] video_effects.py — Stage 6: 4 video modes (Phase 3)
- [ ] video_assembler.py — Stage 7: FFmpeg assembly (Phase 3)
- [ ] chapters.py — Stage 7b (Phase 3)
- [ ] shorts_gen.py — Stage 9 (Phase 4)
- [ ] seo_optimizer.py — Stage 8 (Phase 4)
- [ ] uploader.py — Stage 10 (YouTube API) (Phase 4)
- [ ] pipedream_uploader.py — Stage 10 (webhook/local) (Phase 4)
- [ ] trend_engine.py — RSS + trending discovery (Phase 5)
- [ ] pipeline.py — orchestrates all 10 stages (Phase 5)
- [ ] freestyle.py — dynamic channel builder (Phase 5)
- [ ] orchestrator.py — APScheduler + health checks (Phase 5)

### Channels (channels/)
- [ ] base_channel.py (Phase 5)
- [ ] finance_channel.py (Phase 5)
- [ ] mmo_channel.py (Phase 5)
- [ ] tech_channel.py (Phase 5)

### Dashboard (dashboard/)
- [ ] app.py — FastAPI (Phase 6)
- [ ] templates/index.html (Phase 6)
- [ ] static/style.css (Phase 6)

### Scripts (scripts/)
- [x] run_once.py — manual single-video tool, Phase 1 script+voice loop (2026-08-14)
- [ ] start_engine.py — main CLI (Phase 6)
- [ ] setup.py — first-time wizard (Phase 6)
- [ ] setup_voice.py — ElevenLabs wizard (Phase 6)
- [ ] upload_ready.py (Phase 6)
- [ ] quick_upload.py (Phase 6)

### Infra
- [ ] Dockerfile (Phase 6)
- [ ] docker-compose.yml (Phase 6)
- [ ] start_engine.bat (Phase 6)

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
  ElevenLabs-configured-but-unavailable -> Edge-TTS fallback rule.

- 2026-08-13: voice_clone.py written, ElevenLabs voice cloning setup tested with a fake client
  across 9 test cases.

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
  installed) if all 3 attempts are exhausted. Both modules were tested in a standalone sandbox
  with fake ChannelConfig/content_db/script_writer stubs (not the real config/core packages) to
  verify logic without a full repo checkout — recommend a quick real-import smoke test against
  the actual repo before Phase 3 to catch any signature drift.

## Rebuild Rule

Every session: commit and push working code before closing, even if incomplete.
A broken-but-committed module beats a perfect-but-lost one.
