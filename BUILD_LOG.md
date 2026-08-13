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

## Rebuild Checklist

### Foundation
- [x] README.md recovered and pushed (2026-08-12)
- [x] .gitignore, requirements.txt, .env.template scaffolded (2026-08-12)
- [x] config/settings.py — global Pydantic settings, singleton `settings` object (2026-08-13)
- [x] config/channels.py — 7 channel definitions, ChannelConfig dataclass, CHANNELS registry (2026-08-13)

### Prompts (config/prompts/)
- [ ] finance.py
- [ ] mmo.py
- [ ] tech.py
- [ ] trending.py
- [ ] thee3lite.py
- [ ] legal.py
- [ ] stories.py
- [ ] freestyle.py

### Core Pipeline (core/)
- [x] content_db.py — SQLite tracking, tested end-to-end (create/status transitions/metadata/shorts/retry) (2026-08-13)
- [x] script_writer.py — Stage 1: GPT-4o script generation, tested with fake client (success + failure/retry paths) (2026-08-13)
- [x] voice_gen.py — Stage 2: Edge-TTS / ElevenLabs, tested with fake synthesizer + concatenator (2026-08-13)
- [ ] voice_clone.py — ElevenLabs voice cloning setup (next up)
- [ ] music_mixer.py — Stage 3: FFmpeg background music
- [ ] image_gen.py — Stage 4: DALL-E 3 with retry/fallback
- [ ] thumbnail_text.py — Stage 5: Pillow overlay
- [ ] video_effects.py — Stage 6: 4 video modes
- [ ] video_assembler.py — Stage 7: FFmpeg assembly
- [ ] chapters.py — Stage 7b
- [ ] shorts_gen.py — Stage 9
- [ ] seo_optimizer.py — Stage 8
- [ ] uploader.py — Stage 10 (YouTube API)
- [ ] pipedream_uploader.py — Stage 10 (webhook/local)
- [ ] trend_engine.py — RSS + trending discovery
- [ ] pipeline.py — orchestrates all 10 stages
- [ ] freestyle.py — dynamic channel builder
- [ ] orchestrator.py — APScheduler + health checks

### Channels (channels/)
- [ ] base_channel.py
- [ ] finance_channel.py
- [ ] mmo_channel.py
- [ ] tech_channel.py

### Dashboard (dashboard/)
- [ ] app.py — FastAPI
- [ ] templates/index.html
- [ ] static/style.css

### Scripts (scripts/)
- [ ] start_engine.py — main CLI
- [ ] setup.py — first-time wizard
- [ ] setup_voice.py — ElevenLabs wizard
- [ ] run_once.py
- [ ] upload_ready.py
- [ ] quick_upload.py

### Infra
- [ ] Dockerfile
- [ ] docker-compose.yml
- [ ] start_engine.bat

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
  needed). Confirmed:
    - Per-scene synthesis: one synth call per script scene, in order.
    - Concatenation: segments joined into a single final audio file, persisted into
      content_db metadata as `voice_path`.
    - Failure/retry path: synthesis error retried 2 extra times (3 total), then raises
      VoiceGenerationError, marks video FAILED, increments retry_count.
    - Resilience fallback: a channel configured for `voice_engine="elevenlabs"` with no
      API key/voice ID set correctly falls back to EdgeTTSSynthesizer with a warning log,
      exactly matching the Resilience Architecture table in the original README (ElevenLabs
      missing -> falls back to Edge-TTS, pipeline never breaks).
  Real synthesis classes (EdgeTTSSynthesizer using the edge-tts library, ElevenLabsSynthesizer
  using the elevenlabs client, FFmpegConcatenator using the ffmpeg concat demuxer) are included
  and will be exercised for real once run_once.py / start_engine.py wire the pipeline together —
  at that point ffmpeg + edge-tts need to actually be installed per the Prerequisites table.

## Rebuild Rule

Every session: commit and push working code before closing, even if incomplete.
A broken-but-committed module beats a perfect-but-lost one.
