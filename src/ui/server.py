from __future__ import annotations

import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any
import urllib.parse

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import load_settings
from src.core.utils import read_json

STATIC_DIR = Path(__file__).resolve().parent / "static"
PIPELINE_RUNNING = False
PIPELINE_LOGS = []


def safe_read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return None


class WebUIDemoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard HTTP logs in stdout
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/"):
            self.handle_api_get(path, urllib.parse.parse_qs(parsed_url.query))
        else:
            super().do_GET()

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
        payload = json.loads(post_data) if post_data else {}

        if path == "/api/run-pipeline":
            self.handle_run_pipeline(payload)
        else:
            self._send_json({"error": "Endpoint not found"}, status=404)

    def handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        settings = load_settings()

        if path == "/api/status":
            self._send_json({
                "pipeline_running": PIPELINE_RUNNING,
                "artifacts": {
                    "raw_records": settings.paths.raw_records_json.exists(),
                    "clean_baseline": settings.paths.clean_json.exists(),
                    "baseline_metrics": settings.paths.baseline_metrics.exists(),
                    "corrupted_clean": settings.paths.corrupted_clean_json.exists(),
                    "corrupted_metrics": settings.paths.corrupted_metrics.exists(),
                    "repaired_clean": settings.paths.repaired_clean_json.exists(),
                    "repaired_metrics": settings.paths.repaired_metrics.exists(),
                    "corruption_log": settings.paths.corruption_log.exists(),
                },
                "logs": PIPELINE_LOGS[-50:],
            })

        elif path == "/api/three-state-summary":
            baseline_metrics = safe_read_json(settings.paths.baseline_metrics)
            corrupted_metrics = safe_read_json(settings.paths.corrupted_metrics)
            repaired_metrics = safe_read_json(settings.paths.repaired_metrics)

            baseline_quality = safe_read_json(settings.paths.quality_dir / "baseline_quality.json")
            corrupted_quality = safe_read_json(settings.paths.quality_dir / "corrupted_quality.json")
            repaired_quality = safe_read_json(settings.paths.quality_dir / "repaired_quality.json")

            freshness = safe_read_json(settings.paths.freshness_report)

            self._send_json({
                "metrics": {
                    "baseline": baseline_metrics,
                    "corrupted": corrupted_metrics,
                    "repaired": repaired_metrics,
                },
                "quality": {
                    "baseline": baseline_quality,
                    "corrupted": corrupted_quality,
                    "repaired": repaired_quality,
                },
                "freshness": freshness,
            })

        elif path == "/api/data-samples":
            limit = int(query.get("limit", ["10"])[0])
            raw_records = safe_read_json(settings.paths.raw_records_json) or []
            clean_baseline = safe_read_json(settings.paths.clean_json) or []
            corrupted_clean = safe_read_json(settings.paths.corrupted_clean_json) or []
            repaired_clean = safe_read_json(settings.paths.repaired_clean_json) or []

            self._send_json({
                "raw_records": raw_records[:limit],
                "clean_baseline": clean_baseline[:limit],
                "corrupted_clean": corrupted_clean[:limit],
                "repaired_clean": repaired_clean[:limit],
                "counts": {
                    "raw": len(raw_records),
                    "clean": len(clean_baseline),
                    "corrupted": len(corrupted_clean),
                    "repaired": len(repaired_clean),
                }
            })

        elif path == "/api/corruption-log":
            log_data = safe_read_json(settings.paths.corruption_log)
            self._send_json(log_data or [])

        elif path == "/api/answers":
            limit = int(query.get("limit", ["5"])[0])
            baseline_answers = safe_read_json(settings.paths.baseline_answers) or []
            corrupted_answers = safe_read_json(settings.paths.corrupted_answers) or []
            repaired_answers = safe_read_json(settings.paths.repaired_answers) or []

            self._send_json({
                "baseline": baseline_answers[:limit],
                "corrupted": corrupted_answers[:limit],
                "repaired": repaired_answers[:limit],
            })

        else:
            self._send_json({"error": "Unknown API endpoint"}, status=404)

    def handle_run_pipeline(self, payload: dict[str, Any]) -> None:
        global PIPELINE_RUNNING, PIPELINE_LOGS
        if PIPELINE_RUNNING:
            self._send_json({"status": "error", "message": "Pipeline is already running"}, status=400)
            return

        target = payload.get("target", "corruption_flow")
        
        def runner():
            global PIPELINE_RUNNING, PIPELINE_LOGS
            PIPELINE_RUNNING = True
            PIPELINE_LOGS.append(f"--- Starting {target} execution ---")
            
            cmd = [sys.executable, "-m", f"src.pipelines.{target if target in ('phase1', 'corruption_flow') else 'corruption_flow'}"]
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                if process.stdout:
                    for line in process.stdout:
                        PIPELINE_LOGS.append(line.strip())
                process.wait()
                PIPELINE_LOGS.append(f"--- {target} finished with exit code {process.returncode} ---")
            except Exception as exc:
                PIPELINE_LOGS.append(f"--- Error running pipeline: {exc} ---")
            finally:
                PIPELINE_RUNNING = False

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        self._send_json({"status": "started", "target": target})


def run_server(port: int = 8000) -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server_address = ("", port)
    httpd = HTTPServer(server_address, WebUIDemoHandler)
    print(f"==================================================")
    print(f" Web UI Demo running at: http://localhost:{port}")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Web UI server.")
        httpd.server_close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port)
