from __future__ import annotations

import contextlib
import http.server
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from .generator import generate_statistics
from .repository import sync_registry


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, format: str, *args: object) -> None:
        return


def serve_http(output_root: Path, host: str, port: int) -> None:
    output_root = output_root.resolve()
    handler = partial(QuietHTTPRequestHandler, directory=str(output_root))
    with http.server.ThreadingHTTPServer((host, port), handler) as server:
        print(f"http server listening on http://{host}:{port}/")
        server.serve_forever()


def write_rsync_config(
    output_root: Path,
    config_path: Path,
    module: str = "stats",
) -> Path:
    stats_root = (output_root / "stats").resolve()
    stats_root.mkdir(parents=True, exist_ok=True)
    config_path = config_path.resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path = config_path.with_suffix(".pid")
    config_path.write_text(
        "\n".join(
            (
                "use chroot = false",
                "read only = true",
                "list = true",
                f"pid file = {pid_path}",
                "",
                f"[{module}]",
                f"    path = {stats_root}",
                "    comment = dn42 rir statistics",
                "    read only = true",
                "    list = true",
                "",
            )
        ),
        encoding="ascii",
    )
    return config_path


def run_rsync_daemon(
    output_root: Path,
    host: str,
    port: int,
    module: str = "stats",
    config_path: Path | None = None,
) -> subprocess.Popen[bytes]:
    rsync = shutil.which("rsync")
    if rsync is None:
        raise RuntimeError("rsync binary not found")

    config_path = config_path or (output_root / "rsyncd.conf")
    config_path = write_rsync_config(output_root, config_path, module=module)
    return subprocess.Popen(
        [
            rsync,
            "--daemon",
            "--no-detach",
            "--config",
            str(config_path),
            "--address",
            host,
            "--port",
            str(port),
        ]
    )


def daily_scheduler(
    *,
    remote: str,
    branch: str,
    cache_dir: Path,
    output_root: Path,
    daily_at: str,
    stop_event: threading.Event,
) -> threading.Thread:
    def run() -> None:
        while not stop_event.is_set():
            sleep_seconds = seconds_until_next_run(daily_at)
            if stop_event.wait(sleep_seconds):
                break
            try:
                registry_dir = sync_registry(remote, branch, cache_dir)
                generate_statistics(registry_dir, output_root)
            except Exception as error:  # pragma: no cover - service guard
                print(f"daily generation failed: {error}")
                time.sleep(60)

    thread = threading.Thread(target=run, name="daily-generator", daemon=True)
    thread.start()
    return thread


def seconds_until_next_run(daily_at: str) -> float:
    hour_text, minute_text = daily_at.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour not in range(24) or minute not in range(60):
        raise ValueError(f"invalid daily time: {daily_at!r}")

    now = datetime.now(timezone.utc)
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return max(0.0, (next_run - now).total_seconds())


@contextlib.contextmanager
def managed_process(process: subprocess.Popen[bytes] | None):
    try:
        yield process
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
