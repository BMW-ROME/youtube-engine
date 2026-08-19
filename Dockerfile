# YouTube Engine — Docker image (Edge-TTS voice path; no torch/Chatterbox in base).
#
# Chatterbox (local voice cloning for the thee3lite channel) needs PyTorch
# (~2GB+). To keep the base image lean and the pipeline runnable with just
# the free Edge-TTS path, the base image excludes torch. To enable Chatterbox
# in Docker, uncomment the torch install below (and set CHATTERBOX_VOICE_SAMPLE_PATH
# in your .env, mounting the clip into the container).
FROM python:3.13-slim

# FFmpeg is required by music_mixer (amix), video_assembler (crossfade),
# video_effects (Ken Burns) and shorts_gen.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uncomment to enable Chatterbox voice cloning inside Docker:
# RUN pip install --no-cache-dir torch chatterbox-tts

COPY . .

# Non-root user for safety.
RUN useradd --create-home youtube && chown -R youtube:youtube /app
USER youtube

# Runtime data lives on disk so it survives container restarts.
VOLUME ["/app/output", "/app/run_history.jsonl"]

EXPOSE 8000

# Default: start the scheduler (per-channel cron + topic replenishment + retry).
# Override CMD to [ "python", "dashboard/app.py" ] for dashboard-only mode.
CMD ["python", "-m", "core.orchestrator"]