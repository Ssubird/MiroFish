"""Support helpers for the project-local Letta runtime."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlparse

import requests

from ...config import Config, PROJECT_ROOT


LOCAL_PG_PORT = 55433
LOCAL_PG_USER = "letta"
LOCAL_DB_NAME = "letta"
HTTP_TIMEOUT_SECONDS = 5
STARTUP_TIMEOUT_SECONDS = 45
POLL_INTERVAL_SECONDS = 0.5


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    pg_data: Path
    pg_log: Path
    letta_log: Path
    pg_bin: Path
    letta_cli: Path
    alembic_cli: Path
    alembic_ini: Path


def runtime_paths() -> RuntimePaths:
    workspace_root = Path(PROJECT_ROOT).resolve().parent
    runtime_root = Path(Config.LOTTERY_WORLD_STATE_ROOT).resolve() / ".letta_runtime"
    pg_bin = workspace_root / "tools" / "postgresql17-user" / "bin"
    alembic_ini = find_alembic_ini(workspace_root)
    paths = RuntimePaths(
        root=runtime_root,
        pg_data=runtime_root / "postgres",
        pg_log=runtime_root / "postgres" / "server.log",
        letta_log=runtime_root / "letta-server.log",
        pg_bin=pg_bin,
        letta_cli=Path(PROJECT_ROOT).resolve() / "backend" / ".venv-letta" / "Scripts" / "letta.exe",
        alembic_cli=Path(PROJECT_ROOT).resolve() / "backend" / ".venv-letta" / "Scripts" / "alembic.exe",
        alembic_ini=alembic_ini,
    )
    require_runtime_paths(paths)
    return paths


def find_alembic_ini(workspace_root: Path) -> Path:
    matches = sorted((workspace_root / "tmp").glob("letta-*-src/alembic.ini"))
    if not matches:
        raise RuntimeError("Letta source migrations not found under E:\\MoFish\\tmp")
    return matches[-1]


def require_runtime_paths(paths: RuntimePaths) -> None:
    require_path(paths.pg_bin / "pg_ctl.exe", "PostgreSQL pg_ctl.exe")
    require_path(paths.pg_bin / "initdb.exe", "PostgreSQL initdb.exe")
    require_path(paths.pg_bin / "psql.exe", "PostgreSQL psql.exe")
    require_path(paths.pg_bin / "createdb.exe", "PostgreSQL createdb.exe")
    require_path(paths.letta_cli, "Letta CLI")
    require_path(paths.alembic_cli, "Alembic CLI")
    require_path(paths.alembic_ini, "Letta alembic.ini")


def require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{label} not found: {path}")


def is_local_base_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def openapi_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/openapi.json"


def server_port(base_url: str) -> int:
    parsed = urlparse(base_url)
    if parsed.port:
        return int(parsed.port)
    return 443 if parsed.scheme == "https" else 80


def server_ready(base_url: str) -> bool:
    try:
        response = requests.get(openapi_url(base_url), timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException:
        return False
    return response.ok


def wait_for_http(base_url: str, label: str, log_path: Path) -> None:
    deadline = time.time() + STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        if server_ready(base_url):
            return
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"{label} did not become ready. Log tail:\n{tail(log_path)}")


def tcp_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def wait_for_tcp(host: str, port: int, label: str) -> None:
    deadline = time.time() + STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        if tcp_open(host, port):
            return
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"{label} did not become ready on {host}:{port}")


def clear_stale_pid(pid_path: Path) -> None:
    if not pid_path.exists():
        return
    lines = pid_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    pid = int(lines[0]) if lines and lines[0].isdigit() else 0
    if pid and process_alive(pid):
        return
    pid_path.unlink(missing_ok=True)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def run_command(
    command: list[str],
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: int = 60,
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or "no output"
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{detail}")
    return completed.stdout


def creation_flags() -> int:
    flags = 0
    for name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
        flags |= getattr(subprocess, name, 0)
    return flags


def tail(path: Path, lines: int = 40) -> str:
    if not path.exists():
        return "(no log output)"
    content = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(content[-lines:]) or "(no log output)"
