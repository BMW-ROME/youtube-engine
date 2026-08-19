"""
scripts/local_image_stub.py

Dev-only stand-in for a local OpenAI-compatible image server (LocalAI-style
/v1/images/generations). Lets core/image_gen.py's OpenAIImageClient run against
REAL HTTP without downloading multi-GB diffusion models:

    - GET  /v1/models                  -> {"object":"list","data":[{"id":...}]}
    - POST /v1/images/generations      -> DALL-E-exact response shape
                                         {"created":..., "data":[{"b64_json": ...}]}

so the SDK parses it natively. Every image is a real, Pillow-generated PNG the
downstream stages (thumbnail_text.py, video_effects.py, video_assembler.py) can
open. When a real backend is available (LocalAI, ComfyUI, A1111 on a GPU box),
just point IMAGE_BASE_URL at it and stop using this script -- the client code
path is identical.

Usage (start in its own terminal/process):
    python scripts/local_image_stub.py              # listens on 127.0.0.1:9091
    $env:STUB_PORT=9099; python scripts/local_image_stub.py

Then in .env (or env vars):  IMAGE_BASE_URL=http://127.0.0.1:9091/v1
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Ensure the repo root is importable (only needed if Pillow probing changes).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODEL = os.environ.get("STUB_MODEL", "sdxl-turbo")


def real_png_bytes(w: int = 512, h: int = 512) -> bytes:
    """A real, structurally valid PNG (gradient) via Pillow so downstream
    Pillow-consuming stages can open it. Falls back to a minimal PNG signature
    stub if Pillow is missing -- thumbnail/effects stages skip in that case."""
    try:
        from PIL import Image
    except ImportError:
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (x * 255 // max(w - 1, 1), y * 255 // max(h - 1, 1), (x + y) % 256)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {
                "object": "list",
                "data": [{
                    "id": MODEL, "object": "model",
                    "created": int(time.time()), "owned_by": "local-image-stub",
                }],
            })
        else:
            self._json(404, {"error": {"message": "not found", "type": "invalid_request_error"}})

    def do_POST(self) -> None:
        if self.path.rstrip("/").endswith("/images/generations"):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) or b"{}"
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {}
            n = int(body.get("n", 1))
            size = str(body.get("size", "512x512"))
            try:
                w, h = (int(x) for x in size.lower().split("x"))
            except ValueError:
                w, h = 512, 512
            png = real_png_bytes(w, h)
            b64 = base64.b64encode(png).decode("ascii")
            self._json(200, {
                "created": int(time.time()),
                "data": [{"b64_json": b64} for _ in range(max(n, 1))],
            })
        else:
            self._json(404, {"error": {"message": "not found", "type": "invalid_request_error"}})

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - stdlib signature
        print(f"[stub] {self.address_string()} {fmt % args}")


def main() -> None:
    port = int(os.environ.get("STUB_PORT", "9091"))
    try:
        real_png_bytes(8, 8)
        print("Pillow available: images will be real, openable PNGs")
    except Exception:
        print("Pillow NOT available: images will be PNG-signature stubs")
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Local image stub listening on http://127.0.0.1:{port}/v1")
    print(f"Serving model: {MODEL!r}")
    print(f"Set IMAGE_BASE_URL=http://127.0.0.1:{port}/v1 and IMAGE_MODEL={MODEL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStub stopped.")
        server.server_close()


if __name__ == "__main__":
    main()