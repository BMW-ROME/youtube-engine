"""
dashboard/app.py

Lightweight Flask dashboard for monitoring the YouTube engine pipeline.

Reads the JSON-lines run history written by core/orchestrator.py
(default path: run_history.jsonl) and renders:
  - A table of recent runs (topic, timestamp, success/failure, stages failed)
  - Summary counts (total runs, successes, failures)

Resilience contract:
  - If the history file is missing or unreadable, the dashboard still
    renders with an empty state instead of crashing.
  - Malformed individual lines are skipped and logged, not fatal.

Run with:
    python dashboard/app.py
Then open http://localhost:5000
"""

import json
import logging
import os
from typing import Any, Dict, List

from flask import Flask, render_template_string

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("dashboard")

app = Flask(__name__)

RUN_HISTORY_PATH = os.getenv("RUN_HISTORY_PATH", "run_history.jsonl")

TEMPLATE = """
<!doctype html>
<html>
<head>
  <title>YouTube Engine Dashboard</title>
  <style>
    body { font-family: sans-serif; background: #0d1117; color: #c9d1d9; margin: 2rem; }
    h1 { color: #58a6ff; }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th, td { border: 1px solid #30363d; padding: 8px 12px; text-align: left; }
    th { background: #161b22; }
    .ok { color: #3fb950; font-weight: bold; }
    .fail { color: #f85149; font-weight: bold; }
    .summary { display: flex; gap: 2rem; margin-bottom: 1rem; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem 1.5rem; }
    .card .num { font-size: 1.8rem; font-weight: bold; }
  </style>
</head>
<body>
  <h1>YouTube Engine — Pipeline Dashboard</h1>
  <div class="summary">
    <div class="card"><div class="num">{{ total }}</div>Total runs</div>
    <div class="card"><div class="num" style="color:#3fb950">{{ successes }}</div>Successful</div>
    <div class="card"><div class="num" style="color:#f85149">{{ failures }}</div>Failed</div>
  </div>
  <table>
    <tr><th>Timestamp</th><th>Topic</th><th>Status</th><th>Failed Stages</th></tr>
    {% for run in runs %}
    <tr>
      <td>{{ run.timestamp }}</td>
      <td>{{ run.topic }}</td>
      {% if run.failed_stages %}
        <td class="fail">FAILED</td>
        <td>{{ run.failed_stages | join(', ') }}</td>
      {% else %}
        <td class="ok">SUCCESS</td>
        <td>&mdash;</td>
      {% endif %}
    </tr>
    {% else %}
    <tr><td colspan="4">No runs recorded yet.</td></tr>
    {% endfor %}
  </table>
</body>
</html>
"""


def _load_runs() -> List[Dict[str, Any]]:
    """Load run history, tolerating a missing file or malformed lines."""
    runs: List[Dict[str, Any]] = []
    if not os.path.exists(RUN_HISTORY_PATH):
        logger.warning("Run history file not found at %s", RUN_HISTORY_PATH)
        return runs

    try:
        with open(RUN_HISTORY_PATH, "r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    runs.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping malformed line %d: %s", line_num, exc)
    except Exception as exc:
        logger.error("Failed to read run history: %s", exc)

    runs.reverse()  # most recent first
    return runs


@app.route("/")
def index():
    try:
        runs = _load_runs()
        total = len(runs)
        failures = sum(1 for r in runs if r.get("failed_stages"))
        successes = total - failures
        return render_template_string(
            TEMPLATE, runs=runs, total=total, successes=successes, failures=failures
        )
    except Exception as exc:
        logger.error("Dashboard render failed: %s", exc)
        return f"<h1>Dashboard temporarily unavailable</h1><p>{exc}</p>", 500


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
