"""One-command deploy & restart: push code updates to 22.100 from the local machine.

Usage:
    python scripts/deploy_and_restart.py              # build, push, restart
    python scripts/deploy_and_restart.py --no-restart # build, push, skip restart
    python scripts/deploy_and_restart.py --zip-only   # only build the zip

Steps:
    1. Package project files into a deploy zip
    2. Start a temporary HTTP file server
    3. Call POST /admin/update on 22.100 (downloads zip, swaps code, restarts)
    4. Poll /health until the service comes back up
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from orchestrator.logging.json_logger import get_logger

logger = get_logger("deploy_and_restart")

REMOTE_HOST = "192.168.22.100"
REMOTE_PORT = 8081
SERVE_PORT = 9999
DEPLOY_ZIP = "RASAgent_deploy.zip"
HEALTH_TIMEOUT = 120

INCLUDE_DIRS = [
    "orchestrator",
    "router",
    "router_service",
    "scripts",
    "worker",
    "workflows",
    "offline_packages",
]
INCLUDE_FILES = [
    "requirements.txt",
    ".env.example",
    "VERSION",
    "build_info.json",
]
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pyc",
    ".git",
    ".cursor",
    "artifacts",
}


def _should_exclude(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return any(ex in parts or any(p.endswith(ex) for p in parts)
               for ex in EXCLUDE_PATTERNS)


def _generate_build_info() -> dict:
    """Capture version, git commit, and build timestamp for /admin/version."""
    import json as _json
    from datetime import datetime, timezone

    info: dict = {"build_time": datetime.now(timezone.utc).isoformat()}

    version_file = os.path.join(PROJECT_ROOT, "VERSION")
    if os.path.isfile(version_file):
        with open(version_file) as f:
            info["version"] = f.read().strip()

    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=PROJECT_ROOT,
        )
        if r.returncode == 0:
            info["commit"] = r.stdout.strip()
    except Exception:
        pass

    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, timeout=5,
            cwd=PROJECT_ROOT,
        )
        if r.returncode == 0:
            info["tag"] = r.stdout.strip()
    except Exception:
        pass

    path = os.path.join(PROJECT_ROOT, "build_info.json")
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(info, f, indent=2)
    return info


def build_zip(output_path: str) -> str:
    """Create a deployment zip from the project."""
    _generate_build_info()

    if os.path.exists(output_path):
        os.remove(output_path)

    count = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in INCLUDE_DIRS:
            src = os.path.join(PROJECT_ROOT, d)
            if not os.path.isdir(src):
                continue
            for root, dirs, files in os.walk(src):
                dirs[:] = [dd for dd in dirs if dd not in EXCLUDE_PATTERNS]
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, PROJECT_ROOT)
                    if _should_exclude(rel):
                        continue
                    zf.write(full, rel)
                    count += 1

        for f in INCLUDE_FILES:
            full = os.path.join(PROJECT_ROOT, f)
            if os.path.isfile(full):
                zf.write(full, f)
                count += 1

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info("Zip built: %s (%d files, %.1f MB)", output_path, count, size_mb,
                extra={"action": "build_zip", "step": "done"})
    return output_path


def get_local_ip(remote_host: str, remote_port: int) -> str:
    """Detect the local IP that can reach the remote host."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((remote_host, remote_port))
        return s.getsockname()[0]
    finally:
        s.close()


def start_file_server(directory: str, port: int) -> http.server.HTTPServer:
    """Start a background HTTP file server."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    srv = http.server.HTTPServer(("0.0.0.0", port), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def call_update(remote_host: str, remote_port: int, zip_url: str,
                restart: bool = True) -> dict:
    """POST /admin/update on the remote service."""
    import httpx

    url = f"http://{remote_host}:{remote_port}/admin/update"
    payload = {"zip_url": zip_url, "restart": restart}

    logger.info("Calling %s", url, extra={"action": "call_update", "step": "start"})
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    logger.info("Update response: %s", data,
                extra={"action": "call_update", "step": "done"})
    return data


def wait_for_health(remote_host: str, remote_port: int,
                    timeout: int = HEALTH_TIMEOUT) -> bool:
    """Poll /health until the service is back up."""
    import httpx

    url = f"http://{remote_host}:{remote_port}/health"
    logger.info("Waiting for service at %s (timeout %ds)...", url, timeout,
                extra={"action": "health_poll", "step": "start"})

    deadline = time.time() + timeout
    interval = 3.0
    while time.time() < deadline:
        time.sleep(interval)
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info("Service healthy: %s", data,
                                extra={"action": "health_poll", "step": "ok"})
                    return True
        except Exception:
            pass
        interval = min(interval * 1.3, 10.0)

    logger.error("Service did not come back within %ds", timeout,
                 extra={"action": "health_poll", "step": "timeout"})
    return False


def main():
    parser = argparse.ArgumentParser(description="Deploy & restart router_service on 22.100")
    parser.add_argument("--no-restart", action="store_true",
                        help="Push code but don't restart the service")
    parser.add_argument("--zip-only", action="store_true",
                        help="Only build the deploy zip, don't push")
    parser.add_argument("--serve-port", type=int, default=SERVE_PORT)
    parser.add_argument("--remote-host", default=REMOTE_HOST)
    parser.add_argument("--remote-port", type=int, default=REMOTE_PORT)
    args = parser.parse_args()

    remote_host = args.remote_host
    remote_port = args.remote_port
    serve_port = args.serve_port

    print("=" * 56)
    print("  Deploy & Restart  ->  22.100 router_service")
    print("=" * 56)

    # Step 1: build zip
    zip_path = os.path.join(PROJECT_ROOT, DEPLOY_ZIP)
    print(f"\n[1/4] Building deploy zip ...")
    build_zip(zip_path)
    print(f"  OK  {DEPLOY_ZIP} ({os.path.getsize(zip_path) / 1024 / 1024:.1f} MB)")

    if args.zip_only:
        print("\n  --zip-only: done.")
        return

    # Step 2: start file server
    print(f"\n[2/4] Starting file server on :{serve_port} ...")
    srv = start_file_server(PROJECT_ROOT, serve_port)
    local_ip = get_local_ip(remote_host, remote_port)
    zip_url = f"http://{local_ip}:{serve_port}/{DEPLOY_ZIP}"
    print(f"  OK  Serving at {zip_url}")

    try:
        # Step 3: call /admin/update
        restart = not args.no_restart
        print(f"\n[3/4] Calling /admin/update on {remote_host}:{remote_port} ...")
        result = call_update(remote_host, remote_port, zip_url, restart=restart)
        if not result.get("success"):
            print(f"  FAIL  {result.get('error', 'unknown error')}")
            sys.exit(1)
        print(f"  OK  {result.get('message', '')}")

        # Step 4: wait for service
        if restart:
            print(f"\n[4/4] Waiting for service to restart ...")
            if wait_for_health(remote_host, remote_port):
                print("  OK  Service is back up and healthy!")
            else:
                print("  WARN  Service did not respond in time. Check manually.")
                sys.exit(1)
        else:
            print("\n[4/4] Skipped (--no-restart)")

    finally:
        srv.shutdown()

    print("\n" + "=" * 56)
    print("  Deploy complete!")
    print("=" * 56)


if __name__ == "__main__":
    main()
